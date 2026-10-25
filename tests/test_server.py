"""HTTP-layer tests against an in-memory app + FastAPI TestClient.

Delivery is monkeypatched to avoid touching real tmux.
"""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_swarm import nodes, server, tmux


WEB_ROOT = Path(__file__).parents[1] / "web"


def portal_source():
    """Return authored dashboard sources, not Vite's generated bundle."""

    paths = [WEB_ROOT / "styles.css", *sorted((WEB_ROOT / "src").glob("*.js"))]
    return "\n".join(path.read_text() for path in paths)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    calls = []
    retries = []

    def fake_deliver(
        pane,
        text,
        message_prefix=None,
        submit_key=tmux.DEFAULT_SUBMIT_KEY,
        flavor=None,
        retry_submit=True,
    ):
        calls.append((pane, text, message_prefix, submit_key, flavor))
        retries.append(retry_submit)
        return True, None

    window_names = []
    pane_tags = []

    def fake_tag_pane(pane, handle):
        pane_tags.append((pane, handle))
        return True, None

    def fake_rename_window(pane, name):
        window_names.append((pane, name))
        return True, None

    monkeypatch.setattr(tmux, "deliver", fake_deliver)
    monkeypatch.setattr(tmux, "rename_window", fake_rename_window)
    monkeypatch.setattr(tmux, "tag_pane", fake_tag_pane)
    # 0:0.0 and 0:1.0 run agents; 0:2.0 exists but holds a bare shell.
    monkeypatch.setattr(tmux, "list_panes", lambda: {"0:0.0", "0:1.0", "0:2.0"})
    monkeypatch.setattr(tmux, "live_agent_panes", lambda: {"0:0.0", "0:1.0"})
    # Fake panes are their own ids, all from one tmux server; an unknown
    # target resolves to nothing, as tmux would.
    monkeypatch.setattr(
        tmux, "resolve_pane",
        lambda target: (target, target) if target in tmux.list_panes() else None,
    )
    monkeypatch.setattr(tmux, "server_id", lambda: "srv-1")
    monkeypatch.setattr(tmux, "server_start_time", lambda: 0.0)
    # Existing and live panes derive from this one table.
    monkeypatch.setattr(
        tmux, "pane_table",
        lambda: {
            "0:0.0": {"label": "0:0.0", "command": "claude", "title": ""},
            "0:1.0": {"label": "0:1.0", "command": "claude", "title": ""},
            "0:2.0": {"label": "0:2.0", "command": "bash", "title": ""},
        },
    )
    monkeypatch.setattr(
        tmux, "capture_pane", lambda pane: (f"screen of {pane}\n$ ", None)
    )

    spawns = []

    def fake_spawn_window(session=tmux.AGENTS_SESSION, command=None):
        spawns.append((session, command))
        pane = f"agents:{len(spawns)}.0"
        return tmux.Created(pane, pane, "srv-1"), None

    monkeypatch.setattr(tmux, "spawn_window", fake_spawn_window)
    kills = []

    def fake_kill_pane(pane):
        kills.append(pane)
        return True, None

    monkeypatch.setattr(tmux, "kill_pane", fake_kill_pane)
    app = server.create_app(tmp_path / "db.sqlite", monitor=False)
    c = TestClient(app, client=("127.0.0.1", 50000))
    c._calls = calls
    c._retries = retries
    c._spawns = spawns
    c._kills = kills
    c._window_names = window_names
    c._pane_tags = pane_tags
    return c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_unregister_preserves_history_and_tasks_and_frees_handle(client):
    client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "marten"})
    client.post("/register", json={"tmux_pane": "0:1.0", "requested_user": "ibis"})
    assert client.post("/tasks", json={"title": "Keep working", "assignee": "marten"}).status_code == 200
    client.post("/send", json={"tmux_pane": "0:0.0", "recipient": "ibis", "content": "hello"})
    messages = client.get("/messages").json()
    tasks = client.get("/tasks").json()
    response = client.delete("/recipients/marten")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "user_id": "marten"}
    assert [entry["user_id"] for entry in client.get("/recipients").json()["recipients"]] == ["ibis"]
    assert client.get("/messages").json() == messages
    assert client.get("/tasks").json() == tasks
    assert client._kills == []
    assert client.delete("/recipients/marten").status_code == 404
    response = client.post("/register", json={"tmux_pane": "0:2.0", "requested_user": "marten"})
    assert response.status_code == 200
    assert response.json()["user_id"] == "marten"


def test_register_without_user_id_assigns_cute_name(client):
    from agent_swarm import names

    r = client.post(
        "/register",
        json={
            "tmux_pane": "0:0.0",
            "agent_id": "00000000-0000-4000-8000-000000000001",
            "model": "claude-opus-4-7",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["assigned"] is True
    # A bare pool name: what the agent is and where it runs are columns.
    assert body["user_id"] in names.POOL
    assert body["node"] == tmux.local_node()
    assert body["agent_id"] == "00000000-0000-4000-8000-000000000001"
    assert body["model"] == "claude-opus-4-7"
    assert body["flavor"] == "claude"
    assert body["submit_key"] == "C-m"
    # The handle goes in a pane option; the title stays the harness's own.
    assert "status_title" not in body
    assert client._pane_tags[-1] == ("0:0.0", body["user_id"])


def test_register_rejects_explicit_user_id(client):
    r = client.post("/register", json={"tmux_pane": "0:0.0", "user_id": "explicit"})
    assert r.status_code == 422


def test_register_reuses_name_for_same_agent_id(client):
    first = client.post(
        "/register",
        json={"tmux_pane": "0:0.0", "agent_id": "agent-1"},
    ).json()
    second = client.post(
        "/register",
        json={"tmux_pane": "0:1.0", "agent_id": "agent-1"},
    ).json()
    assert second["user_id"] == first["user_id"]


def test_register_keeps_contact_preferences(client):
    r = client.post(
        "/register",
        json={
            "tmux_pane": "0:0.0",
            "flavor": "codex",
            "instructions": "use /queue before each message so my message doesn't interrupt",
            "message_prefix": "/queue ",
        },
    )
    body = r.json()
    assert body["flavor"] == "codex"
    assert body["instructions"].startswith("use /queue")
    assert body["message_prefix"] == "/queue "
    assert body["submit_key"] == "Enter"


@pytest.mark.parametrize(
    ("flavor", "submit_key"),
    [
        ("hermes", "C-m"),
        ("pi", "Enter"),
    ],
)
def test_register_known_harness_flavor_defaults(client, flavor, submit_key):
    r = client.post(
        "/register",
        json={"tmux_pane": "0:0.0", "flavor": flavor},
    )
    body = r.json()
    assert body["flavor"] == flavor
    assert body["submit_key"] == submit_key


def test_register_allows_submit_key_override_over_flavor_default(client):
    r = client.post(
        "/register",
        json={"tmux_pane": "0:0.0", "flavor": "codex", "submit_key": "C-m"},
    )
    body = r.json()
    assert body["flavor"] == "codex"
    assert body["submit_key"] == "C-m"


@pytest.mark.parametrize(
    ("model", "expected_flavor", "expected_submit_key"),
    [
        ("hermes-agent", "hermes", "C-m"),
        ("pi-coding-agent", "pi", "Enter"),
    ],
)
def test_register_infers_harness_flavor_from_model(
    client, model, expected_flavor, expected_submit_key
):
    r = client.post(
        "/register",
        json={"tmux_pane": "0:0.0", "model": model},
    )
    body = r.json()
    assert body["flavor"] == expected_flavor
    assert body["submit_key"] == expected_submit_key


def test_register_includes_protocol_brief(client):
    first = client.post(
        "/register",
        json={
            "tmux_pane": "0:1.0",
            "agent_id": "uuid-a",
            "model": "claude-x",
            "instructions": "use /queue before each message so my message doesn't interrupt",
        },
    ).json()
    r = client.post("/register", json={"tmux_pane": "0:2.0"})
    brief = r.json()["protocol_brief"]
    assert r.json()["user_id"] in brief
    assert "[agent-msg from" in brief
    assert first["user_id"] in brief
    # peer metadata appears for context
    assert "claude-x" in brief and "uuid-a" in brief
    assert "use /queue before each message" in brief
    assert "flavor=claude" in brief
    assert "submit=C-m" in brief


def test_register_then_send_delivers_and_records(client):
    sender = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    recipient = client.post(
        "/register",
        json={
            "tmux_pane": "0:1.0",
            "flavor": "codex",
            "message_prefix": "/queue ",
        },
    ).json()["user_id"]

    r = client.post(
        "/send",
        json={
            "tmux_pane": "0:0.0",
            "recipient": recipient,
            "context": "mathy",
            "content": "hello",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["delivered_to_pane"] == "0:1.0"

    pane, text, message_prefix, submit_key, flavor = client._calls[-1]
    assert pane == "0:1.0"
    assert message_prefix == "/queue "
    assert submit_key == "Enter"
    assert flavor == "codex"
    assert sender in text and "mathy" in text and "hello" in text


@pytest.mark.parametrize(
    ("flavor", "expected_submit_key"),
    [
        ("hermes", "C-m"),
        ("pi", "Enter"),
    ],
)
def test_send_passes_harness_flavor_delivery_preferences(
    client, flavor, expected_submit_key
):
    sender = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    recipient = client.post(
        "/register",
        json={"tmux_pane": "0:1.0", "flavor": flavor},
    ).json()["user_id"]

    r = client.post(
        "/send",
        json={
            "tmux_pane": "0:0.0",
            "recipient": recipient,
            "context": "smoke",
            "content": "hello",
        },
    )

    assert r.status_code == 200
    pane, text, message_prefix, submit_key, delivered_flavor = client._calls[-1]
    assert pane == "0:1.0"
    assert message_prefix is None
    assert submit_key == expected_submit_key
    assert delivered_flavor == flavor
    assert sender in text and "smoke" in text and "hello" in text


def test_send_rejects_unregistered_sender_pane(client):
    recipient = client.post("/register", json={"tmux_pane": "0:1.0"}).json()["user_id"]
    r = client.post(
        "/send",
        json={"tmux_pane": "0:9.0", "recipient": recipient, "content": "hello"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "sender not registered"


def test_send_unknown_recipient_404_but_still_recorded(client):
    sender = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    r = client.post(
        "/send",
        json={"tmux_pane": "0:0.0", "recipient": "ghost", "content": "??"},
    )
    assert r.status_code == 404
    mid = r.json()["detail"]["message_id"]
    assert mid > 0

    msgs = client.get("/messages", params={"user": "ghost"}).json()["messages"]
    assert len(msgs) == 1
    assert msgs[0]["sender"] == sender
    assert msgs[0]["delivered"] == 0
    assert msgs[0]["delivery_error"] == "recipient not registered"


def test_messages_history(client):
    recipient = client.post("/register", json={"tmux_pane": "0:1.0"}).json()["user_id"]
    sender = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    for i in range(3):
        client.post(
            "/send",
            json={"tmux_pane": "0:0.0", "recipient": recipient, "content": f"m{i}"},
        )
    msgs = client.get("/messages", params={"user": recipient}).json()["messages"]
    assert [m["content"] for m in msgs] == ["m2", "m1", "m0"]
    assert all(m["sender"] == sender for m in msgs)


def test_portal_page_served_at_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "<title>Buzz</title>" in r.text
    assert '/static/portal.js' in r.text
    assert '/static/portal.css' in r.text
    assert client.get("/static/portal.js").headers["content-type"].startswith(
        "text/javascript"
    )
    assert client.get("/static/portal.css").headers["content-type"].startswith(
        "text/css"
    )


def test_portal_versions_assets_by_content_and_does_not_cache_html(client, tmp_path, monkeypatch):
    import re
    from agent_swarm import server

    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "portal.js").write_text("first build")
    (assets / "portal.css").write_text("styles")
    monkeypatch.setattr(server, "PORTAL_STATIC_PATH", assets)
    def versions(response):
        return dict(re.findall(r'/static/(portal\.(?:js|css))\?v=([0-9a-f]+)', response.text))
    first = client.get("/")
    assert first.headers["cache-control"] == "no-store"
    before = versions(first)
    assert set(before) == {"portal.js", "portal.css"}
    assert versions(client.get("/")) == before
    (assets / "portal.js").write_text("other build")
    after = versions(client.get("/"))
    assert after["portal.js"] != before["portal.js"]
    assert after["portal.css"] == before["portal.css"]


def test_portal_task_drag_drop_contract(client):
    portal = portal_source()
    assert 'const draggable = t.status !== "done";' in portal
    assert "draggable=${draggable}" in portal
    assert 'Math.hypot(p.x - b.x, p.y - b.y) < 24' in portal
    assert 'if (task.assignee === assignee)' in portal
    assert 'window.addEventListener("dragend", clearDrop)' in portal
    assert 'aria-live="polite"' in portal


def test_portal_task_honeycomb_contract(client):
    portal = portal_source()
    assert "task comb · ${waiting.length} waiting · ${carriedCount} carried" in portal
    assert "taskCellsRef.current.push" in portal
    assert "placeTaskCell(" in portal
    assert "taskCellClearsTeams" in portal
    assert "occupiedTaskCells" in portal
    assert "taskCells: () => taskCellsRef.current" in portal
    assert "extras.slice(0, 4).forEach" in portal
    assert "shipmentsRef.current.push" in portal
    assert "shipped · ${done}" in portal
    assert 'ctx.fillText("owner", ownerNode.x, 253)' in portal


def test_portal_team_contract(client):
    portal = portal_source()
    # Teams are managed from the sidebar's teams view (create, drag
    # membership, pick a queen) and mirrored in the hive canvas as labeled
    # outlines.
    assert "function TeamManage" in portal
    assert "<${NewTeam} refresh=${refresh} />" in portal
    assert "application/x-agent-swarm-agent" in portal
    assert "/team`" in portal
    assert "{ queen, objective: objective.trim() || null }" in portal
    assert "teamBoxesRef" in portal
    assert "assign #${dragTaskRef.current} to team ${targetBox.name}" in portal
    assert "move ${dragBeeRef.current} to team ${targetBox.name}" in portal
    assert "depends_on" in portal
    # Team boxes can be dragged into place (persisted per browser) and
    # bees outside a team are kept out of team outlines.
    assert "agent-swarm-hive-team-pos" in portal
    assert "release to place team" in portal
    assert "bee.r.team_id === box.id" in portal


def test_portal_dead_pane_overrides_stale_activity(client):
    portal = portal_source()
    assert 'if (!r.pane_alive) return "stopped";' in portal
    assert "class=${`status ${st.cls}`}" in portal
    assert ".status.working" in portal
    assert ".status.attention" in portal


def test_portal_conversation_history_has_full_width_resize_handle(client):
    portal = portal_source()
    assert 'class="history-resizer"' in portal
    assert 'aria-label="Resize conversation history"' in portal
    assert "setPointerCapture" in portal
    assert 'e.key === "ArrowUp"' in portal
    assert ".history-resizer {" in portal
    assert "width: 100%; height: 18px" in portal
    assert "touch-action: none" in portal
    assert "resize: none" in portal


def test_portal_pins_owner_thread_and_keeps_peer_threads_stable(client):
    portal = portal_source()
    # Thread ranks are retained in refs, rather than recomputed from each
    # thread's most recent timestamp whenever polling replaces state.
    assert "const threadOrder = useRef(new Map());" in portal
    assert "const nextThreadOrder = useRef(0);" in portal
    assert "const ownerThread = pairKey(\"owner\", user);" in portal
    assert "if (a === ownerThread) return -1;" in portal
    assert "return threadOrder.current.get(a) - threadOrder.current.get(b);" in portal
    assert ".map(([, msgs]) => msgs);" in portal


def test_portal_unread_is_agent_to_owner_only(client):
    portal = portal_source()
    assert 'm.id > since && m.sender === u && m.recipient === "owner"' in portal
    assert 'class="team-mate-unread"' in portal


def test_portal_bees_identify_their_harness_by_color_and_glyph(client):
    portal = portal_source()
    assert "export const HARNESSES" in portal
    for flavor in ("claude", "codex", "pi", "hermes", "generic"):
        assert f'key: "{flavor}"' in portal
    assert "const harness = harnessStyle(r.flavor)" in portal
    assert "ctx.fillStyle = harness.color" in portal
    # the mark rides in the name label (shape + color), not a plate on the body
    assert "harness plate" not in portal
    assert "ctx.fillText(harness.mark, labelLeft, labelY)" in portal
    assert "labelLeft + markW + markGap" in portal
    assert 'class="harness-legend"' in portal
    assert 'aria-label="Bee harness legend"' in portal
    assert "harness: harness.key" in portal
    # the legend teaches every spawnable harness even with no live agent;
    # generic appears only when a generic agent is running
    assert "legendHarnesses" in portal
    assert 'h.key !== "generic" || generic' in portal


def test_portal_spawn_has_no_permission_choice(client):
    portal = portal_source()
    assert "permissions:" not in portal
    # "default model" sends no model, so the harness gets no model flag
    assert "model: model === DEFAULT_MODEL ? null : model }" in portal


def test_state_reports_agents_liveness_and_ordered_messages(client, monkeypatch):
    a = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    monkeypatch.setattr(tmux, "resolve_pane", lambda target: (target, target))
    b = client.post("/register", json={"tmux_pane": "0:9.0"}).json()["user_id"]
    for i in range(2):
        client.post(
            "/send",
            json={"tmux_pane": "0:0.0", "recipient": b, "content": f"m{i}"},
        )

    state = client.get("/api/state").json()
    alive = {r["user_id"]: r["pane_alive"] for r in state["recipients"]}
    assert alive[a] is True
    assert alive[b] is False  # pane 0:9.0 is not in the fake live-pane set
    assert [m["content"] for m in state["messages"]] == ["m0", "m1"]
    assert state["now"] >= state["messages"][-1]["ts"]


def test_state_defaults_activity_to_unknown_without_monitor_data(client):
    user = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    state = client.get("/api/state").json()
    act = next(r["activity"] for r in state["recipients"] if r["user_id"] == user)
    assert act == {"status": "unknown", "detail": None, "since": None}


def test_state_carries_seeded_activity(client):
    user = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    client.app.state.activity_registry[user] = {
        "hash": "abc", "changed_at": 1.0, "status": "needs_attention",
        "detail": "Do you want to proceed?", "since": 2.0, "notified": True,
    }
    state = client.get("/api/state").json()
    act = next(r["activity"] for r in state["recipients"] if r["user_id"] == user)
    assert act == {
        "status": "needs_attention",
        "detail": "Do you want to proceed?",
        "since": 2.0,
    }


def test_peek_returns_pane_capture(client):
    user = client.post("/register", json={"tmux_pane": "0:1.0"}).json()["user_id"]
    r = client.get(f"/api/peek/{user}")
    assert r.status_code == 200
    body = r.json()
    assert body["tmux_pane"] == "0:1.0"
    assert body["text"].startswith("screen of 0:1.0")
    assert body["error"] is None


def test_peek_unknown_agent_404(client):
    r = client.get("/api/peek/ghost")
    assert r.status_code == 404


def test_owner_send_delivers_to_pane_and_records(client):
    user = client.post("/register", json={"tmux_pane": "0:1.0"}).json()["user_id"]
    r = client.post("/owner/send", json={"recipient": user, "content": "status update please"})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    pane, text, *_ = client._calls[-1]
    assert pane == "0:1.0"
    assert "[agent-msg from owner]" in text and "status update please" in text
    assert 'agent-swarm send --to owner --message "..."' in text

    msgs = client.get("/messages", params={"user": user}).json()["messages"]
    assert msgs[0]["sender"] == "owner"
    assert msgs[0]["content"] == "status update please"


def test_owner_send_preserves_multiline_content_and_context(client):
    user = client.post("/register", json={"tmux_pane": "0:1.0"}).json()["user_id"]
    content = "First, inspect the failure.\nThen run the focused test."
    r = client.post(
        "/owner/send",
        json={"recipient": user, "content": content, "context": "investigation"},
    )
    assert r.status_code == 200

    _, delivered, *_ = client._calls[-1]
    assert "[agent-msg from owner · investigation]" in delivered
    assert 'agent-swarm send --to owner --message' in delivered
    assert content in delivered

    msgs = client.get("/messages", params={"user": user}).json()["messages"]
    assert msgs[0]["content"] == content
    assert msgs[0]["context"] == "investigation"


def test_owner_send_retry_with_same_client_id_delivers_once(client):
    user = client.post("/register", json={"tmux_pane": "0:1.0"}).json()["user_id"]
    body = {"recipient": user, "content": "deploy it", "client_id": "c-1"}
    first = client.post("/owner/send", json=body).json()
    # The answer was lost on the way back; the dashboard sends it again.
    again = client.post("/owner/send", json=body).json()
    assert first["status"] == again["status"] == "delivered"
    assert again["message_id"] == first["message_id"]
    assert len(client._calls) == 1
    msgs = client.get("/messages", params={"user": user}).json()["messages"]
    assert [m["content"] for m in msgs] == ["deploy it"]
    # A new message gets a new id and is delivered.
    client.post("/owner/send", json={**body, "client_id": "c-2"})
    assert len(client._calls) == 2


def test_owner_send_retry_after_definite_failure_delivers(client, monkeypatch):
    user = client.post("/register", json={"tmux_pane": "0:1.0"}).json()["user_id"]
    body = {"recipient": user, "content": "deploy it", "client_id": "c-1"}
    monkeypatch.setattr(tmux, "deliver", lambda *a, **k: (False, "no such pane"))
    assert client.post("/owner/send", json=body).json()["status"] == "failed"
    monkeypatch.setattr(tmux, "deliver", lambda *a, **k: (True, None))
    assert client.post("/owner/send", json=body).json()["status"] == "delivered"


def test_owner_send_retry_while_first_attempt_in_flight_does_not_paste(client, tmp_path):
    from agent_swarm import db
    user = client.post("/register", json={"tmux_pane": "0:1.0"}).json()["user_id"]
    other = db.connect(tmp_path / "db.sqlite")
    mid = db.record_message(other, "owner", user, None, "deploy it", status="pending", client_id="c-1")
    r = client.post("/owner/send", json={"recipient": user, "content": "deploy it", "client_id": "c-1"}).json()
    assert r["status"] == "unknown" and r["message_id"] == mid
    assert client._calls == []


def test_owner_send_unknown_recipient_404(client):
    r = client.post("/owner/send", json={"recipient": "ghost", "content": "hi"})
    assert r.status_code == 404


def test_agent_can_reply_to_owner_without_tmux_delivery(client):
    user = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    n_calls = len(client._calls)
    r = client.post(
        "/send",
        json={"tmux_pane": "0:0.0", "recipient": "owner", "content": "done with the refactor"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["delivered_to_pane"] is None
    assert len(client._calls) == n_calls  # nothing injected anywhere

    msgs = client.get("/messages", params={"user": "owner"}).json()["messages"]
    assert msgs[0]["sender"] == user
    assert msgs[0]["delivered"] == 1


def test_protocol_brief_mentions_owner_and_tasks(client):
    brief = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["protocol_brief"]
    assert "'owner' is the human operator" in brief
    assert "Terminal-only output does not reach the owner" in brief
    assert "as Markdown" in brief
    assert "task-update" in brief
    assert "task-create" in brief


def test_create_task_notifies_assignee(client):
    user = client.post("/register", json={"tmux_pane": "0:1.0"}).json()["user_id"]
    r = client.post("/tasks", json={"title": "fix the build", "assignee": user})
    assert r.status_code == 200
    task = r.json()["task"]
    assert task["status"] == "open"
    assert task["assignee"] == user
    assert task["worktree"] is None

    pane, text, *_ = client._calls[-1]
    assert pane == "0:1.0"
    assert f"task #{task['id']}" in text and "fix the build" in text
    assert "task/" in text and "--worktree" in text
    assert "picked_up" in text and "done" in text  # tells the agent how to update

    state = client.get("/api/state").json()
    assert state["tasks"][0]["id"] == task["id"]


def test_create_task_unregistered_assignee_404(client):
    r = client.post("/tasks", json={"title": "x", "assignee": "ghost"})
    assert r.status_code == 404


def test_task_status_flow_open_picked_up_done(client):
    tid = client.post("/tasks", json={"title": "ship it"}).json()["task"]["id"]
    r = client.patch(
        f"/tasks/{tid}",
        json={"status": "picked_up", "worktree": "/tmp/repo-task-1"},
    )
    assert r.json()["task"]["status"] == "picked_up"
    assert r.json()["task"]["worktree"] == "/tmp/repo-task-1"
    r = client.patch(f"/tasks/{tid}", json={"status": "done", "note": "ran the suite"})
    assert r.json()["task"]["status"] == "done"
    assert client.patch(f"/tasks/{tid}", json={"worktree": ""}).status_code == 422
    assert client.patch(f"/tasks/{tid}", json={"status": "bogus"}).status_code == 422
    assert client.patch("/tasks/999", json={"status": "done"}).status_code == 404


def test_spawn_creates_window_and_registers_agent(client):
    r = client.post("/agents/spawn", json={"flavor": "claude"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["tmux_pane"] == "agents:1.0"
    assert body["command"] == "claude --permission-mode auto"
    assert client._spawns[-1] == (tmux.AGENTS_SESSION, "claude --permission-mode auto")

    recipients = client.get("/recipients").json()["recipients"]
    spawned = next(x for x in recipients if x["user_id"] == body["user_id"])
    assert spawned["flavor"] == "claude"
    assert spawned["submit_key"] == "C-m"
    assert client._window_names[-1] == ("agents:1.0", body["user_id"])
    assert client._pane_tags[-1] == ("agents:1.0", body["user_id"])


def test_spawn_pi_launches_pi_binary(client):
    r = client.post("/agents/spawn", json={"flavor": "pi"})
    assert r.status_code == 200
    assert client._spawns[-1] == (tmux.AGENTS_SESSION, "pi")
    assert r.json()["model"] is None


def test_spawn_codex_runs_yolo_and_permission_choice_is_gone(client, codex_catalog):
    r = client.post("/agents/spawn", json={"flavor": "codex", "model": "gpt-5.6-luna"})
    assert r.status_code == 200
    assert client._spawns[-1] == (
        tmux.AGENTS_SESSION, "codex -c check_for_update_on_startup=false --model gpt-5.6-luna --yolo"
    )
    # The old permission field is refused, not silently ignored.
    assert client.post(
        "/agents/spawn", json={"flavor": "claude", "autonomy": "supervised"}
    ).status_code == 422


def test_spawn_with_model_passes_cli_flag_and_records_model(client):
    r = client.post("/agents/spawn", json={"flavor": "claude", "model": "opus"})
    assert r.status_code == 200
    assert client._spawns[-1] == (
        tmux.AGENTS_SESSION,
        "claude --model opus --permission-mode auto",
    )
    body = r.json()
    assert body["model"] == "opus"
    spawned = next(
        x for x in client.get("/recipients").json()["recipients"]
        if x["user_id"] == body["user_id"]
    )
    assert spawned["model"] == "opus"


def test_spawn_ignores_unknown_model(client):
    r = client.post("/agents/spawn", json={"flavor": "claude", "model": "totally-made-up"})
    assert r.status_code == 200
    # Falls back to the default command; nothing bogus is recorded or launched.
    assert client._spawns[-1] == (
        tmux.AGENTS_SESSION, "claude --permission-mode auto"
    )
    assert r.json()["model"] is None


def test_spawn_rejects_unknown_and_unspawnable_flavors(client):
    assert client.post("/agents/spawn", json={"flavor": "skynet"}).status_code == 422
    # generic is no longer spawnable (a bare shell is not a working agent).
    assert client.post("/agents/spawn", json={"flavor": "generic"}).status_code == 422


def test_spawn_options_lists_harnesses_and_models(client):
    r = client.get("/api/spawn-options")
    assert r.status_code == 200
    harnesses = {h["flavor"]: h["models"] for h in r.json()["harnesses"]}
    assert set(harnesses) == {"claude", "codex", "pi", "hermes"}
    assert "opus" in harnesses["claude"]
    assert harnesses["hermes"] == []


def test_stop_kills_live_agent_pane(client):
    user = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    r = client.post(f"/agents/{user}/stop")
    assert r.status_code == 200
    assert r.json()["already_stopped"] is False
    assert client._kills == ["0:0.0"]


def test_stop_is_idempotent_for_stopped_agent(client):
    user = client.post("/register", json={"tmux_pane": "0:2.0"}).json()["user_id"]
    r = client.post(f"/agents/{user}/stop")
    assert r.status_code == 200
    assert r.json()["already_stopped"] is True
    assert client._kills == []


def test_stop_rejects_unknown_agent(client):
    assert client.post("/agents/ghost/stop").status_code == 404


def test_stop_reports_tmux_failure(client, monkeypatch):
    user = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    monkeypatch.setattr(tmux, "kill_pane", lambda pane: (False, "permission denied"))
    r = client.post(f"/agents/{user}/stop")
    assert r.status_code == 500
    assert r.json()["detail"]["detail"] == "permission denied"


def test_terminal_text_is_typed_bare(client):
    user = client.post(
        "/register",
        json={"tmux_pane": "0:0.0", "flavor": "claude", "message_prefix": "@@ "},
    ).json()["user_id"]
    r = client.post(f"/agents/{user}/terminal", json={"text": "/fast"})
    assert r.status_code == 200
    # No message envelope and no prefix: the harness must see a slash command.
    assert client._calls[-1][:3] == ("0:0.0", "/fast", None)
    # A second Enter would pick from a menu the command opened.
    assert client._retries[-1] is False
    assert all(m["content"] != "/fast" for m in client.get("/api/state").json()["messages"])


def test_terminal_key_is_pressed(client, monkeypatch):
    pressed = []
    monkeypatch.setattr(tmux, "send_key", lambda pane, key: pressed.append((pane, key)) or (True, None))
    user = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    assert client.post(f"/agents/{user}/terminal", json={"key": "Escape"}).status_code == 200
    assert pressed == [("0:0.0", "Escape")]
    assert client._calls == []


def test_terminal_rejects_bad_requests_and_dead_panes(client):
    user = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    for body in ({}, {"text": "x", "key": "Up"}, {"text": "  "}, {"key": "C-c"}):
        assert client.post(f"/agents/{user}/terminal", json=body).status_code == 422
    shell = client.post("/register", json={"tmux_pane": "0:2.0"}).json()["user_id"]
    assert client.post(f"/agents/{shell}/terminal", json={"text": "/fast"}).status_code == 409
    assert client.post("/agents/ghost/terminal", json={"text": "/fast"}).status_code == 404
    assert client._calls == []


def test_state_reports_compact_command_by_flavor(client):
    client.post("/register", json={"tmux_pane": "0:0.0", "flavor": "hermes"})
    client.post("/register", json={"tmux_pane": "0:1.0"})
    commands = sorted(
        str(r["compact_command"]) for r in client.get("/api/state").json()["recipients"]
    )
    assert commands == ["/compress", "None"]


def test_reassigning_task_notifies_new_assignee(client):
    a = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    b = client.post("/register", json={"tmux_pane": "0:1.0"}).json()["user_id"]
    tid = client.post("/tasks", json={"title": "review PR", "assignee": a}).json()["task"]["id"]
    n_calls = len(client._calls)

    r = client.patch(f"/tasks/{tid}", json={"assignee": b})
    assert r.json()["task"]["assignee"] == b
    assert len(client._calls) == n_calls + 1
    pane, text, *_ = client._calls[-1]
    assert pane == "0:1.0"

    # status-only updates don't re-notify
    client.patch(f"/tasks/{tid}", json={"status": "picked_up"})
    assert len(client._calls) == n_calls + 1


def test_register_grants_a_free_requested_name(client):
    r = client.post(
        "/register",
        json={
            "tmux_pane": "0:0.0",
            "agent_id": "agent-jax",
            "model": "claude-opus-4-7",
            "requested_user": "jax",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "jax"
    assert body["requested_user"] == "jax"
    assert body["renamed_from"] is None
    # `assigned` means "the server chose this handle", not "a handle was given".
    assert body["assigned"] is False


def test_register_normalizes_requested_name(client):
    body = client.post(
        "/register",
        json={"tmux_pane": "0:0.0", "requested_user": "  JAX  "},
    ).json()
    assert body["user_id"] == "jax"


def test_register_rejects_malformed_requested_name(client):
    for bad in ("has space", "-leading", "Ünicode", "", "x" * 49):
        r = client.post(
            "/register", json={"tmux_pane": "0:0.0", "requested_user": bad}
        )
        assert r.status_code == 400, bad


def test_register_rejects_reserved_requested_name(client):
    r = client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "owner"})
    assert r.status_code == 400
    assert "reserved" in r.json()["detail"]["error"]


def test_register_conflicts_when_another_agent_holds_the_name(client):
    client.post(
        "/register", json={"tmux_pane": "0:0.0", "agent_id": "a1", "requested_user": "jax"}
    )
    r = client.post(
        "/register",
        json={"tmux_pane": "0:1.0", "agent_id": "a2", "requested_user": "jax"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["requested_user"] == "jax"


def test_register_is_idempotent_for_the_same_agent_and_name(client):
    first = client.post(
        "/register", json={"tmux_pane": "0:0.0", "agent_id": "a1", "requested_user": "jax"}
    ).json()
    second = client.post(
        "/register", json={"tmux_pane": "0:0.0", "agent_id": "a1", "requested_user": "jax"}
    ).json()
    assert first["user_id"] == second["user_id"] == "jax"
    assert second["renamed_from"] is None


def test_requesting_a_name_renames_an_existing_agent(client):
    first = client.post(
        "/register", json={"tmux_pane": "0:0.0", "agent_id": "a1"}
    ).json()
    assert first["assigned"] is True
    second = client.post(
        "/register",
        json={"tmux_pane": "0:0.0", "agent_id": "a1", "requested_user": "jax"},
    ).json()
    assert second["user_id"] == "jax"
    assert second["renamed_from"] == first["user_id"]
    handles = [r["user_id"] for r in client.get("/recipients").json()["recipients"]]
    assert "jax" in handles
    assert first["user_id"] not in handles


def test_rename_carries_message_history(client):
    old = client.post("/register", json={"tmux_pane": "0:0.0", "agent_id": "a1"}).json()
    client.post("/register", json={"tmux_pane": "0:1.0", "agent_id": "a2"})
    peer = [
        r["user_id"]
        for r in client.get("/recipients").json()["recipients"]
        if r["user_id"] != old["user_id"]
    ][0]
    client.post(
        "/send",
        json={"tmux_pane": "0:0.0", "recipient": peer, "content": "before rename"},
    )
    client.post(
        "/register",
        json={"tmux_pane": "0:0.0", "agent_id": "a1", "requested_user": "jax"},
    )
    messages = client.get("/messages").json()["messages"]
    senders = {m["sender"] for m in messages}
    assert "jax" in senders
    assert old["user_id"] not in senders


def test_reregister_without_model_keeps_stored_flavor_in_pane_title(client):
    client.post(
        "/register",
        json={"tmux_pane": "0:0.0", "agent_id": "a1", "model": "claude-opus-4-7"},
    )
    body = client.post(
        "/register",
        json={"tmux_pane": "0:0.0", "agent_id": "a1", "requested_user": "jax"},
    ).json()
    assert body["flavor"] == "claude"


def _register(client, pane, **extra):
    return client.post("/register", json={"tmux_pane": pane, **extra}).json()["user_id"]


def test_recipients_report_liveness(client, monkeypatch):
    # Registration sees the pane; the subsequent snapshot no longer contains it.
    monkeypatch.setattr(tmux, "resolve_pane", lambda target: (target, target))
    live = _register(client, "0:1.0")
    shell = _register(client, "0:2.0")
    gone = _register(client, "9:9.9")
    rows = {r["user_id"]: r for r in client.get("/recipients").json()["recipients"]}
    assert rows[live]["alive"] and rows[live]["offline_reason"] is None
    assert not rows[shell]["alive"] and "bare shell" in rows[shell]["offline_reason"]
    assert not rows[gone]["alive"] and "no longer exists" in rows[gone]["offline_reason"]


def test_send_to_bare_shell_pane_is_refused_and_recorded(client):
    _register(client, "0:0.0")
    shell = _register(client, "0:2.0")
    before = len(client._calls)
    r = client.post(
        "/send",
        json={"tmux_pane": "0:0.0", "recipient": shell, "content": "hello"},
    )
    assert r.status_code == 409
    assert "bare shell" in r.json()["detail"]["error"]
    assert len(client._calls) == before  # nothing typed into the shell
    msg = client.get("/messages", params={"limit": 1}).json()["messages"][0]
    assert msg["recipient"] == shell and not msg["delivered"]
    assert "bare shell" in msg["delivery_error"]


def test_owner_send_to_gone_pane_is_refused(client, monkeypatch):
    # Registration sees the pane; the subsequent snapshot no longer contains it.
    monkeypatch.setattr(tmux, "resolve_pane", lambda target: (target, target))
    gone = _register(client, "9:9.9")
    r = client.post("/owner/send", json={"recipient": gone, "content": "hi"})
    assert r.status_code == 409
    assert "no longer exists" in r.json()["detail"]["error"]


def test_register_brief_tags_offline_peers(client):
    shell = _register(client, "0:2.0")
    brief = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["protocol_brief"]
    assert f"- {shell} (" in brief and "OFFLINE" in brief
    assert "refused until they restart" in brief


def test_prune_keeps_shell_panes_unless_asked(client, monkeypatch):
    # Registration sees the pane; the subsequent snapshot no longer contains it.
    monkeypatch.setattr(tmux, "resolve_pane", lambda target: (target, target))
    live = _register(client, "0:1.0")
    shell = _register(client, "0:2.0")
    gone = _register(client, "9:9.9")

    r = client.post("/recipients/prune", json={}).json()
    assert r["removed"] == [gone] and r["kept_offline"] == [shell]
    ids = {x["user_id"] for x in client.get("/recipients").json()["recipients"]}
    assert ids == {live, shell}

    r = client.post("/recipients/prune", json={"include_shells": True}).json()
    assert r["removed"] == [shell] and r["kept_offline"] == []
    ids = {x["user_id"] for x in client.get("/recipients").json()["recipients"]}
    assert ids == {live}


def test_closing_a_task_requires_a_verification_note(client):
    client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "marten"})
    tid = client.post("/tasks", json={"title": "Ship it", "assignee": "marten"}).json()["task"]["id"]

    r = client.patch(f"/tasks/{tid}", json={"status": "done"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "note" in detail["error"]
    # The refusal carries the same guidance the agent was given up front.
    assert "how to use it" in detail["note"]
    assert client.get("/tasks").json()["tasks"][0]["status"] == "open"

    # A note supplied with the close is enough, and it is kept on the task.
    r = client.patch(
        f"/tasks/{tid}",
        json={"status": "done", "note": "Run `agent-swarm tasks`; note shows on the card."},
    )
    assert r.status_code == 200
    task = r.json()["task"]
    assert task["status"] == "done"
    assert task["note"].startswith("Run `agent-swarm tasks`")


def test_a_note_left_earlier_satisfies_the_close(client):
    tid = client.post("/tasks", json={"title": "Two steps"}).json()["task"]["id"]
    client.patch(f"/tasks/{tid}", json={"note": "Open the dashboard and expand the task."})
    assert client.patch(f"/tasks/{tid}", json={"status": "done"}).status_code == 200


def test_blank_note_does_not_count_as_a_note(client):
    tid = client.post("/tasks", json={"title": "Whitespace"}).json()["task"]["id"]
    r = client.patch(f"/tasks/{tid}", json={"status": "done", "note": "   "})
    assert r.status_code == 422


def test_reopening_and_other_updates_never_need_a_note(client):
    tid = client.post("/tasks", json={"title": "Reopen me"}).json()["task"]["id"]
    client.patch(f"/tasks/{tid}", json={"status": "done", "note": "verified by hand"})
    assert client.patch(f"/tasks/{tid}", json={"status": "open"}).status_code == 200
    assert client.patch(f"/tasks/{tid}", json={"status": "picked_up"}).status_code == 200


def test_assignment_message_and_brief_tell_agents_to_leave_a_note(client):
    client.post("/register", json={"tmux_pane": "0:1.0", "requested_user": "ibis"})
    brief = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["protocol_brief"]
    assert "--note" in brief and "required" in brief

    client.post("/tasks", json={"title": "Do a thing", "assignee": "ibis"})
    delivered = client._calls[-1][1]
    assert "--note" in delivered
    assert "how to use it" in delivered


def test_task_card_links_to_the_assigned_agent_and_shows_the_note():
    portal = portal_source()
    # The assignee is a link into that agent's page, not plain text.
    assert "picked up by" in portal
    assert "focusHash(t.assignee)" in portal
    # And the note is readable from the card.
    assert "how to verify" in portal
    assert "tnote-body" in portal


def test_set_model_label_is_display_only(client):
    user = client.post("/register", json={"tmux_pane": "0:0.0", "model": "claude-sonnet-4-6"}).json()["user_id"]

    r = client.post(f"/agents/{user}/model", json={"model": "  claude-opus-4-7 "})
    assert r.status_code == 200
    assert r.json()["recipient"]["model"] == "claude-opus-4-7"
    state = client.get("/api/state").json()
    assert next(x for x in state["recipients"] if x["user_id"] == user)["model"] == "claude-opus-4-7"

    r = client.post(f"/agents/{user}/model", json={"model": ""})
    assert r.status_code == 200 and r.json()["recipient"]["model"] is None

    assert client.post("/agents/nobody/model", json={"model": "x"}).status_code == 404


def test_status_is_shown_on_the_dashboard_state(client):
    jax = client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "jax"}).json()
    r = client.post("/status", json={"tmux_pane": "0:0.0", "text": "  working on\n#12:  pane ids "})
    assert r.status_code == 200
    assert r.json()["status"] == "working on #12: pane ids"
    client.post("/status", json={"tmux_pane": "0:0.0", "text": "done: pane ids"})
    # Repeating the current status adds nothing.
    client.post("/status", json={"tmux_pane": "0:0.0", "text": "done: pane ids"})
    agent = next(
        x for x in client.get("/api/state").json()["recipients"]
        if x["user_id"] == jax["user_id"]
    )
    assert [s["text"] for s in agent["summaries"]] == ["done: pane ids", "working on #12: pane ids"]
    assert {s["source"] for s in agent["summaries"]} == {"agent"}


def test_status_from_unregistered_pane_is_refused(client):
    r = client.post("/status", json={"tmux_pane": "0:1.0", "text": "hi"})
    assert r.status_code == 404
    r = client.post("/status", json={"tmux_pane": "0:1.0", "text": ""})
    assert r.status_code == 422


def test_monitor_records_harness_pane_titles_as_summaries(client, monkeypatch):
    client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "jax"})
    title = {"t": "⠂ Fix the flaky upload test"}
    monkeypatch.setattr(
        tmux, "pane_table",
        lambda: {"0:0.0": {"label": "0:0.0", "command": "claude", "title": title["t"]}},
    )
    tick = client.app.state.monitor_tick
    asyncio.run(tick())
    # The spinner turning into Claude's idle mark is not a new topic.
    title["t"] = "✳ Fix the flaky upload test"
    asyncio.run(tick())
    client.post("/status", json={"tmux_pane": "0:0.0", "text": "working on #7"})
    asyncio.run(tick())  # unchanged title stays behind the agent's own line
    title["t"] = "Summarize open PRs | marin"
    asyncio.run(tick())
    summaries = client.get("/api/state").json()["recipients"][0]["summaries"]
    assert [(s["text"], s["source"]) for s in summaries] == [
        ("Summarize open PRs", "title"),
        ("working on #7", "agent"),
        ("Fix the flaky upload test", "title"),
    ]


def test_unregister_forgets_summaries(client):
    client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "jax"})
    client.post("/status", json={"tmux_pane": "0:0.0", "text": "working"})
    assert client.delete("/recipients/jax").status_code == 200
    client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "jax"})
    assert client.get("/api/state").json()["recipients"][0]["summaries"] == []


def _connect_node(client, name):
    """A second reachable machine whose tmux is the same fake as the local one."""
    from agent_swarm import nodes

    node = nodes.LocalNode(name)
    client.app.state.nodes.add(node)
    return node


def test_register_records_the_node_it_came_from(client):
    _connect_node(client, "macbook")
    r = client.post(
        "/register",
        json={"tmux_pane": "0:0.0", "agent_id": "a-node", "node": "macbook"},
    )
    assert r.status_code == 200
    assert r.json()["node"] == "macbook"
    user = r.json()["user_id"]
    # Registering again from the same node keeps the row where it is; the
    # node is never derived from the handle.
    r = client.post("/register", json={"tmux_pane": "0:0.0", "agent_id": "a-node", "node": "macbook"})
    assert r.json()["user_id"] == user
    assert r.json()["node"] == "macbook"
    row = next(x for x in client.get("/recipients").json()["recipients"] if x["user_id"] == user)
    assert row["node"] == "macbook"
    brief = client.post("/register", json={"tmux_pane": "0:1.0"}).json()["protocol_brief"]
    assert f"{user} (" in brief and "node=macbook" in brief


def test_agent_reregistering_from_another_node_moves_with_its_handle(client):
    _connect_node(client, "macbook")
    user = client.post(
        "/register", json={"tmux_pane": "0:0.0", "agent_id": "a-move", "node": "macbook"}
    ).json()["user_id"]
    r = client.post("/register", json={"tmux_pane": "0:1.0", "agent_id": "a-move"})
    assert r.json()["user_id"] == user
    assert r.json()["node"] == tmux.local_node()


def test_register_and_send_refuse_an_unknown_node(client):
    r = client.post("/register", json={"tmux_pane": "0:0.0", "node": "nowhere"})
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "unknown node"
    assert tmux.local_node() in r.json()["detail"]["known"]
    client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "jax"})
    r = client.post(
        "/send", json={"tmux_pane": "0:0.0", "node": "nowhere", "recipient": "jax", "content": "x"}
    )
    assert r.status_code == 422


def test_same_pane_id_on_two_nodes_is_two_agents(client):
    _connect_node(client, "macbook")
    a = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    b = client.post("/register", json={"tmux_pane": "0:0.0", "node": "macbook"}).json()["user_id"]
    assert a != b
    rows = {r["user_id"]: r for r in client.get("/recipients").json()["recipients"]}
    assert rows[a]["node"] == tmux.local_node() and rows[b]["node"] == "macbook"
    # The sender is resolved on its own node, so a message from the MacBook
    # pane comes from b, not a.
    client.post("/send", json={"tmux_pane": "0:0.0", "node": "macbook", "recipient": a, "content": "hi"})
    assert client.get("/messages").json()["messages"][0]["sender"] == b


def test_agents_on_a_disconnected_node_read_offline_and_are_never_pruned(client):
    _connect_node(client, "macbook")
    user = client.post(
        "/register", json={"tmux_pane": "0:0.0", "node": "macbook", "requested_user": "puffin"}
    ).json()["user_id"]
    client.app.state.nodes.remove("macbook")
    row = next(x for x in client.get("/recipients").json()["recipients"] if x["user_id"] == user)
    assert row["alive"] is False
    assert row["offline_reason"] == "recipient offline: node macbook is not connected"
    client.post("/register", json={"tmux_pane": "0:1.0", "requested_user": "otter"})
    r = client.post("/send", json={"tmux_pane": "0:1.0", "recipient": "puffin", "content": "hi"})
    assert r.status_code == 409
    assert "node macbook is not connected" in r.json()["detail"]["error"]
    assert client._calls == []
    # Unreachable is not confirmed gone: prune must leave the registration.
    assert client.post("/recipients/prune", json={"include_shells": True}).json()["removed"] == []
    assert client.post("/agents/puffin/stop").status_code == 409
    peek = client.get("/api/peek/puffin").json()
    assert peek["text"] is None and "not connected" in peek["error"]


def test_spawn_on_a_named_node_registers_the_agent_there(client):
    _connect_node(client, "macbook")
    r = client.post("/agents/spawn", json={"flavor": "claude", "node": "macbook"})
    assert r.status_code == 200
    assert r.json()["node"] == "macbook"
    row = next(x for x in client.get("/recipients").json()["recipients"] if x["user_id"] == r.json()["user_id"])
    assert row["node"] == "macbook"
    assert client.post("/agents/spawn", json={"flavor": "claude", "node": "nowhere"}).status_code == 422


def test_register_without_a_node_records_this_machine(client):
    r = client.post("/register", json={"tmux_pane": "0:0.0"})
    assert r.json()["node"] == tmux.local_node()


def test_spawn_assigns_a_bare_name_on_this_machine(client, codex_catalog):
    from agent_swarm import names

    r = client.post("/agents/spawn", json={"flavor": "codex", "model": "gpt-6-astra"})
    assert r.status_code == 200
    user = r.json()["user_id"]
    assert user in names.POOL
    row = next(x for x in client.get("/recipients").json()["recipients"] if x["user_id"] == user)
    assert row["node"] == tmux.local_node()
    assert row["model"] == "gpt-6-astra"


def test_legacy_suffixed_handles_reserve_their_bare_name_over_http(client, monkeypatch):
    from agent_swarm import names

    # Every pool name but two is taken; one of the two survives only as a
    # legacy suffixed handle, so the other must be the one handed out.
    monkeypatch.setattr(names, "POOL", ["otter", "ferret"])
    client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "otter-codex-gpt5-workstation"})
    assert client.post("/register", json={"tmux_pane": "0:1.0"}).json()["user_id"] == "ferret"
    # Both bases are taken now, so exhaustion suffixes whichever base the
    # RNG picks; either is correct as long as neither bare name is reused.
    r = client.post("/agents/spawn", json={"flavor": "claude"})
    assert r.status_code == 200
    assert r.json()["user_id"] in {"otter-2", "ferret-2"}


def test_rows_from_before_nodes_belong_to_this_machine(tmp_path):
    from agent_swarm import db

    conn = db.connect(tmp_path / "old.sqlite")
    db.register(conn, "otter", "%1", tmux_server="srv-1", pane_label="0:0.0")
    conn.execute("UPDATE recipients SET node=NULL")
    conn.commit()
    conn.close()
    app = server.create_app(tmp_path / "old.sqlite", monitor=False)
    rows = TestClient(app, client=("127.0.0.1", 50000)).get("/recipients").json()["recipients"]
    assert rows[0]["node"] == tmux.local_node()


def test_registering_again_without_agent_id_keeps_the_handle(client):
    # Identity falls back to the pane on its node; a second register from the
    # same pane must find the row rather than allocate and evict.
    first = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    again = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    assert again == first
    _connect_node(client, "macbook")
    remote = client.post("/register", json={"tmux_pane": "0:0.0", "node": "macbook"}).json()["user_id"]
    assert remote != first
    assert client.post("/register", json={"tmux_pane": "0:0.0", "node": "macbook"}).json()["user_id"] == remote
    handles = {r["user_id"] for r in client.get("/recipients").json()["recipients"]}
    assert handles == {first, remote}


def test_whoami_resolves_the_pane_on_its_own_node(client):
    _connect_node(client, "macbook")
    local = client.post("/register", json={"tmux_pane": "0:0.0"}).json()["user_id"]
    remote = client.post("/register", json={"tmux_pane": "0:0.0", "node": "macbook"}).json()["user_id"]
    assert client.get("/whoami", params={"tmux_pane": "0:0.0"}).json()["user_id"] == local
    r = client.get("/whoami", params={"tmux_pane": "0:0.0", "node": "macbook"}).json()
    assert r["user_id"] == remote and r["node"] == "macbook"
    assert client.get("/whoami", params={"tmux_pane": "0:1.0"}).json()["user_id"] is None
    assert client.get("/whoami", params={"tmux_pane": "0:0.0", "node": "nowhere"}).status_code == 422


def test_whoami_ignores_a_pane_from_an_earlier_tmux(client, monkeypatch):
    client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "jax"})
    monkeypatch.setattr(tmux, "server_id", lambda: "srv-2")
    assert client.get("/whoami", params={"tmux_pane": "0:0.0"}).json()["user_id"] is None


class _AnsweringNode(nodes.LocalNode):
    """A reachable node whose deliveries end however the test says."""

    def __init__(self, name, result, db_path):
        super().__init__(name)
        self.result, self.db_path, self.seen = result, db_path, []

    def deliver(self, op_id, pane, tmux_server, text, **kw):
        import sqlite3

        # The message row must already exist, pending, under this op id.
        with sqlite3.connect(self.db_path) as c:
            row = c.execute("SELECT status FROM messages WHERE id=?", (int(op_id),)).fetchone()
        self.seen.append((op_id, pane, tmux_server, row[0] if row else None))
        return self.result


def test_delivery_is_recorded_before_dispatch_and_an_unknown_result_is_kept(client, tmp_path):
    node = _AnsweringNode("macbook", nodes.Result("unknown", "socket closed"), tmp_path / "db.sqlite")
    client.app.state.nodes.add(node)
    client.post("/register", json={"tmux_pane": "0:0.0", "node": "macbook", "requested_user": "puffin"})
    client.post("/register", json={"tmux_pane": "0:1.0", "requested_user": "otter"})
    r = client.post("/send", json={"tmux_pane": "0:1.0", "recipient": "puffin", "content": "hi"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False and body["status"] == "unknown"
    assert body["delivery_error"] == "socket closed"
    # The node saw the pending row, keyed by the message id, before pasting.
    assert node.seen == [(str(body["message_id"]), "0:0.0", "srv-1", "pending")]
    msg = client.get("/messages").json()["messages"][0]
    assert msg["status"] == "unknown" and msg["delivered"] == 0
    assert msg["delivery_error"] == "socket closed"
    # The owner path records the same way.
    r = client.post("/owner/send", json={"recipient": "puffin", "content": "hello"})
    assert r.json()["status"] == "unknown"
    assert len(node.seen) == 2


def test_failed_and_delivered_results_settle_the_message(client, tmp_path):
    node = _AnsweringNode("macbook", nodes.Result("failed", "pane vanished"), tmp_path / "db.sqlite")
    client.app.state.nodes.add(node)
    client.post("/register", json={"tmux_pane": "0:0.0", "node": "macbook", "requested_user": "puffin"})
    r = client.post("/owner/send", json={"recipient": "puffin", "content": "x"})
    assert r.json()["status"] == "failed" and r.json()["ok"] is False
    node.result = nodes.Result("ok")
    r = client.post("/owner/send", json={"recipient": "puffin", "content": "y"})
    assert r.json()["status"] == "delivered" and r.json()["ok"] is True
    statuses = [(m["status"], m["delivered"]) for m in client.get("/messages").json()["messages"]]
    assert statuses == [("delivered", 1), ("failed", 0)]


def test_refused_and_owner_bound_messages_carry_a_status(client):
    client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "jax"})
    client.post("/register", json={"tmux_pane": "0:2.0", "requested_user": "shell"})
    client.post("/send", json={"tmux_pane": "0:0.0", "recipient": "owner", "content": "to you"})
    client.post("/send", json={"tmux_pane": "0:0.0", "recipient": "shell", "content": "to a shell"})
    client.post("/send", json={"tmux_pane": "0:0.0", "recipient": "ghost", "content": "to no one"})
    statuses = {m["recipient"]: m["status"] for m in client.get("/messages").json()["messages"]}
    assert statuses == {"owner": "delivered", "shell": "failed", "ghost": "failed"}


def test_worktree_is_recorded_with_the_node_it_is_on(client):
    _connect_node(client, "macbook")
    client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "jax"})
    task = client.post("/tasks", json={"title": "t", "assignee": "jax"}).json()["task"]
    r = client.patch(f"/tasks/{task['id']}", json={"worktree": "/Users/k/repo-7", "worktree_node": "macbook"})
    assert r.json()["task"]["worktree_node"] == "macbook"
    # Unsaid, the path is on the server's own machine.
    r = client.patch(f"/tasks/{task['id']}", json={"worktree": "/home/k/repo-7"})
    assert r.json()["task"]["worktree_node"] == tmux.local_node()
    # Clearing the path clears where it was.
    r = client.patch(f"/tasks/{task['id']}", json={"worktree": None})
    assert r.json()["task"]["worktree"] is None and r.json()["task"]["worktree_node"] is None


def test_an_exception_during_delivery_leaves_the_message_unknown(client, tmp_path):
    class Exploding(nodes.LocalNode):
        def deliver(self, *a, **k):
            raise TimeoutError("socket read timed out")

    client.app.state.nodes.add(Exploding("macbook"))
    client.post("/register", json={"tmux_pane": "0:0.0", "node": "macbook", "requested_user": "puffin"})
    r = client.post("/owner/send", json={"recipient": "puffin", "content": "x"})
    assert r.status_code == 200
    assert r.json()["status"] == "unknown"
    assert "TimeoutError" in r.json()["delivery_error"]
    msg = client.get("/messages").json()["messages"][0]
    assert msg["status"] == "unknown" and "TimeoutError" in msg["delivery_error"]


def test_messages_left_pending_by_a_previous_run_become_unknown(tmp_path):
    from agent_swarm import db

    conn = db.connect(tmp_path / "old.sqlite")
    stuck = db.record_message(conn, "owner", "otter", None, "in flight", "pending")
    done = db.record_message(conn, "owner", "otter", None, "landed", "delivered")
    conn.close()
    app = server.create_app(tmp_path / "old.sqlite", monitor=False)
    by_id = {m["id"]: m for m in TestClient(app, client=("127.0.0.1", 50000)).get("/messages").json()["messages"]}
    assert by_id[stuck]["status"] == "unknown"
    assert "stopped before" in by_id[stuck]["delivery_error"]
    assert by_id[done]["status"] == "delivered"


def test_a_node_that_cannot_observe_its_tmux_is_unavailable_not_empty(client):
    class Blind(nodes.LocalNode):
        def snapshot(self):
            raise nodes.Unavailable("tmux restarting")

    client.app.state.nodes.add(Blind("macbook"))
    client.post("/register", json={"tmux_pane": "0:0.0", "node": "macbook", "requested_user": "puffin"})
    row = next(x for x in client.get("/recipients").json()["recipients"] if x["user_id"] == "puffin")
    assert row["alive"] is False and row["observed"] is False
    assert "cannot observe its tmux" in row["offline_reason"]
    client.post("/register", json={"tmux_pane": "0:1.0", "requested_user": "otter"})
    assert client.post("/send", json={"tmux_pane": "0:1.0", "recipient": "puffin", "content": "hi"}).status_code == 409
    assert client.post("/recipients/prune", json={"include_shells": True}).json()["removed"] == []
    assert client.post("/agents/puffin/stop").status_code == 409
    peek = client.get("/api/peek/puffin")
    assert peek.status_code == 200
    asyncio.run(client.app.state.monitor_tick())
    state = client.get("/api/state").json()
    assert next(r for r in state["recipients"] if r["user_id"] == "puffin")["activity"]["status"] == "stopped"


def test_a_failing_capture_does_not_end_the_monitor_tick(client):
    class Jumpy(nodes.LocalNode):
        def capture(self, pane, tmux_server):
            raise RuntimeError("tmux hiccup")

    client.app.state.nodes.add(Jumpy("macbook"))
    client.post("/register", json={"tmux_pane": "0:0.0", "node": "macbook", "requested_user": "puffin"})
    client.post("/register", json={"tmux_pane": "0:1.0", "requested_user": "otter"})
    asyncio.run(client.app.state.monitor_tick())
    by_user = {r["user_id"]: r["activity"]["status"] for r in client.get("/api/state").json()["recipients"]}
    assert by_user["puffin"] == "unknown"  # alive, but nothing could be read
    assert by_user["otter"] == "working"


def test_worktree_paths_from_before_nodes_belong_to_this_machine(tmp_path):
    from agent_swarm import db

    conn = db.connect(tmp_path / "old.sqlite")
    task = db.create_task(conn, "old work")
    db.update_task(conn, task["id"], worktree="/home/k/repo-1")
    conn.execute("UPDATE tasks SET worktree_node=NULL")
    conn.commit()
    conn.close()
    app = server.create_app(tmp_path / "old.sqlite", monitor=False)
    t = TestClient(app, client=("127.0.0.1", 50000)).get("/tasks").json()["tasks"][0]
    assert t["worktree_node"] == tmux.local_node()


def test_importing_the_server_module_builds_no_app():
    # Building the app opens the configured database and runs the startup
    # reconciliation; that belongs to the serving process alone.
    assert not hasattr(server, "app")


def test_spawn_and_stop_report_unknown_outcomes_distinctly(client, monkeypatch):
    import subprocess

    def timed_out_launch(session=tmux.AGENTS_SESSION, command=None):
        raise tmux.Uncertain(
            "launch command did not report back: timed out",
            tmux.Created("agents:9.0", "agents:9.0", "srv-1"),
        )

    monkeypatch.setattr(tmux, "spawn_window", timed_out_launch)
    r = client.post("/agents/spawn", json={"flavor": "claude"})
    assert r.status_code == 200
    assert r.json()["launch"] == "unknown" and r.json()["tmux_pane"] == "agents:9.0"
    user = r.json()["user_id"]

    def no_window(session=tmux.AGENTS_SESSION, command=None):
        raise tmux.Uncertain("window creation did not report back: timed out")

    monkeypatch.setattr(tmux, "spawn_window", no_window)
    r = client.post("/agents/spawn", json={"flavor": "claude"})
    assert r.status_code == 502 and r.json()["detail"]["status"] == "unknown"

    monkeypatch.setattr(
        tmux, "pane_table",
        lambda: {"agents:9.0": {"label": "agents:9.0", "command": "claude", "title": ""}},
    )

    def kill_timed_out(pane):
        raise tmux.Uncertain("kill did not report back: timed out")

    monkeypatch.setattr(tmux, "kill_pane", kill_timed_out)
    r = client.post(f"/agents/{user}/stop")
    assert r.status_code == 502 and r.json()["detail"]["status"] == "unknown"


def test_portal_shows_machines_and_unknown_deliveries():
    portal = portal_source()
    # Messages are judged by their status, never by the delivered flag, and
    # the composer reads the answer's status rather than trusting HTTP 200.
    assert 'm.status === "unknown"' in portal and "m.delivered ?" not in portal
    assert "deliveryOutcome(r.ok, body)" in portal and 'throw new Error("delivery failed")' not in portal
    # An unknown outcome is resent only on purpose, as a new message.
    assert "may already have it" in portal and "send again" in portal
    # Machines: a strip of nodes and a spawn target.
    assert "function MachineBar" in portal and 'title="machine"' in portal and "body.node = target.node" in portal


def test_dashboard_decisions_pass_their_own_tests():
    """The dashboard's pure decisions (delivery outcome, spawn target) are
    tested by Node's test runner; run them here so one suite covers both."""
    import shutil
    import subprocess

    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    proc = subprocess.run(
        ["node", "--test", *sorted(str(p) for p in (WEB_ROOT / "test").glob("*.test.js"))],
        cwd=WEB_ROOT.parent, capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_owner_can_trash_task_but_dependencies_are_protected(client):
    c = client
    parent = c.post('/tasks', json={'title': 'parent'}).json()['task']
    child = c.post('/tasks', json={'title': 'child', 'depends_on': [parent['id']]}).json()['task']
    assert c.delete(f"/tasks/{parent['id']}").status_code == 409
    assert c.delete(f"/tasks/{child['id']}").status_code == 200
    assert c.delete(f"/tasks/{parent['id']}").status_code == 200
    assert c.delete(f"/tasks/{parent['id']}").status_code == 404


def test_node_cannot_trash_tasks(client):
    c = client
    task = c.post('/tasks', json={'title': 'keep'}).json()['task']
    issued = c.post('/nodes/test-trash/token').json()
    response = c.delete(f"/tasks/{task['id']}", headers={'Authorization': f"Bearer {issued['token']}"})
    assert response.status_code == 403


def test_owner_reminder_follows_per_agent_conversation_inactivity(client, monkeypatch):
    clock = [10000.0]
    monkeypatch.setattr(server.time, 'time', lambda: clock[0])
    a = client.post('/register', json={'tmux_pane': '0:0.0'}).json()['user_id']
    b = client.post('/register', json={'tmux_pane': '0:1.0'}).json()['user_id']
    def send(user, text='hello'):
        assert client.post('/owner/send', json={'recipient': user, 'content': text}).status_code == 200
        return client._calls[-1][1]
    hint = 'Reply via `agent-swarm send --to owner'
    assert hint in send(a)
    clock[0] += 60
    assert send(a, 'follow-up') == '[agent-msg from owner] follow-up'
    assert hint in send(b)  # independent conversation
    clock[0] += 24 * 60
    # An agent reply keeps the established exchange active.
    assert client.post('/send', json={'tmux_pane': '0:0.0', 'recipient': 'owner', 'content': 'reply'}).status_code == 200
    clock[0] += 2 * 60
    assert hint not in send(a)
    clock[0] += 25 * 60
    assert hint in send(a)  # exactly 25 quiet minutes
    clock[0] += 1
    client.post('/register', json={'tmux_pane': '0:0.0'})
    assert hint in send(a)  # fresh registration gets its first reminder


def test_unsuccessful_owner_delivery_does_not_suppress_reminder(client, monkeypatch):
    user = client.post('/register', json={'tmux_pane': '0:0.0'}).json()['user_id']
    calls = []
    def fail(pane, body, *args, **kwargs):
        calls.append(body)
        return False, 'paste failed'
    monkeypatch.setattr(tmux, 'deliver', fail)
    for _ in range(2):
        r = client.post('/owner/send', json={'recipient': user, 'content': 'hello'})
        assert r.json()['status'] == 'failed'
    assert all('Reply via `agent-swarm send --to owner' in body for body in calls)


@pytest.mark.parametrize("existing", [False, True])
def test_register_refuses_missing_pane_without_changing_identity(client, existing):
    if existing:
        client.post("/register", json={"tmux_pane": "0:0.0", "agent_id": "session-1"})
    before = client.get("/recipients").json()
    response = client.post("/register", json={
        "tmux_pane": "%115", "agent_id": "session-1", "requested_user": "quokka"
    })
    assert response.status_code == 404
    assert "does not resolve" in response.json()["detail"]["error"]
    assert client.get("/recipients").json() == before


def test_agent_history_is_independent_and_pages_without_gaps(client, tmp_path):
    from agent_swarm import db
    conn = db.connect(tmp_path / "db.sqlite")
    ids = [db.record_message(conn, "owner", "old-agent", None, str(i), "delivered") for i in range(7)]
    # Equal and out-of-order timestamps must not affect cursor pagination.
    conn.execute("UPDATE messages SET ts=1 WHERE recipient='old-agent'")
    conn.commit()
    for i in range(301):
        db.record_message(conn, "busy", "owner", None, "noise", "delivered")
    assert not any(m["recipient"] == "old-agent" for m in client.get("/api/state").json()["messages"])
    url = "/api/agents/old-agent/messages"
    first = client.get(url, params={"limit": 3}).json()
    assert [m["id"] for m in first["messages"]] == ids[-3:][::-1]
    assert first["has_more"]
    second = client.get(url, params={"limit": 3, "before": ids[-3]}).json()
    assert [m["id"] for m in second["messages"]] == ids[1:4][::-1]
    last = client.get(url, params={"limit": 3, "before": ids[1]}).json()
    assert [m["id"] for m in last["messages"]] == ids[:1]
    assert not last["has_more"]
    newer = client.get(url, params={"limit": 3, "after": ids[0]}).json()
    assert [m["id"] for m in newer["messages"]] == ids[1:4]
    assert newer["has_more"]
    assert client.get(url, params={"before": 1, "after": 2}).status_code == 422
    assert client.get(url, params={"limit": -1}).status_code == 422
    assert client.get(url, params={"limit": 501}).status_code == 422
    assert client.get(url, headers={"X-Forwarded-For": "100.1.2.3"}).status_code == 401
    conn.close()

