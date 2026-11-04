"""The swarm supervisor: a prompt-driven, hub-wide role, plus the digest it
reads and the throttled nudge that tells it something changed."""

import asyncio

from agent_swarm import digest, server
from tests.test_server import client  # noqa: F401  (reuse the app fixture)


def _register(client, pane, name):
    r = client.post("/register", json={"tmux_pane": pane, "requested_user": name})
    assert r.status_code == 200
    return r.json()["user_id"]


def _pasted(client, pane):
    return [text for p, text, *_ in client._calls if p == pane]


# ---- role -------------------------------------------------------------------


def test_appoint_delivers_prompt_and_shows_on_state(client):
    sup = _register(client, "0:0.0", "heron")
    _register(client, "0:1.0", "vole")
    assert client.get("/supervisor").json() == {"supervisor": None}

    r = client.put("/supervisor", json={"user_id": "heron", "objective": "watch the release"})
    assert r.status_code == 200
    body = r.json()
    assert body["supervisor"]["user_id"] == sup
    assert body["delivery"]["status"] == "delivered"
    prompt = _pasted(client, "0:0.0")[-1]
    assert "[agent-msg from owner · supervisor]" in prompt
    assert "swarm supervisor" in prompt and "watch the release" in prompt
    assert "vole" in prompt  # the live roster is in the prompt
    assert "buzz digest" in prompt and "buzz spawn" in prompt

    state = client.get("/api/state").json()
    assert state["supervisor"]["user_id"] == "heron"
    assert state["supervisor"]["objective"] == "watch the release"


def test_appoint_requires_registered_agent_and_owner(client):
    r = client.put("/supervisor", json={"user_id": "nobody"})
    assert r.status_code == 404
    # A node token may not appoint.
    _register(client, "0:0.0", "heron")
    token = client.post("/nodes/laptop/token").json()["token"]
    r = client.put("/supervisor", json={"user_id": "heron"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_clear_tells_the_agent_and_handles_absence(client):
    assert client.delete("/supervisor").status_code == 404
    _register(client, "0:0.0", "heron")
    client.put("/supervisor", json={"user_id": "heron"})
    r = client.delete("/supervisor")
    assert r.status_code == 200
    assert r.json()["was"]["user_id"] == "heron"
    assert "ended your swarm supervisor role" in _pasted(client, "0:0.0")[-1]
    assert client.get("/supervisor").json() == {"supervisor": None}


def test_unregister_clears_the_role(client):
    _register(client, "0:0.0", "heron")
    client.put("/supervisor", json={"user_id": "heron"})
    assert client.delete("/recipients/heron").status_code == 200
    assert client.get("/supervisor").json() == {"supervisor": None}


def test_reappointing_replaces_the_holder(client):
    _register(client, "0:0.0", "heron")
    _register(client, "0:1.0", "vole")
    client.put("/supervisor", json={"user_id": "heron"})
    client.put("/supervisor", json={"user_id": "vole"})
    assert client.get("/supervisor").json()["supervisor"]["user_id"] == "vole"


def test_hub_is_a_reserved_handle(client):
    r = client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "hub"})
    assert r.status_code == 400


# ---- digest endpoint ---------------------------------------------------------


def test_digest_lists_new_traffic_and_task_changes_with_a_cursor(client):
    _register(client, "0:0.0", "heron")
    _register(client, "0:1.0", "vole")
    client.post("/send", json={"tmux_pane": "0:1.0", "recipient": "heron", "content": "first"})
    first_id = client.get("/messages").json()["messages"][0]["id"]
    client.post("/tasks", json={"title": "Fix the build", "assignee": "vole"})
    client.post("/owner/send", json={"recipient": "vole", "content": "how is it going?"})
    client.post("/send", json={"tmux_pane": "0:1.0", "recipient": "owner", "content": "nearly there"})

    d = client.get("/digest").json()
    text = d["text"]
    assert text.startswith("swarm digest")
    assert "agents: 2 live" in text
    assert "#1 open · vole · Fix the build" in text
    assert "vole → heron: first" in text
    assert "owner → vole: how is it going?" in text
    assert "vole → owner: nearly there" in text
    assert "3 with owner, 1 agent to agent" in text  # the task assignment notice is from the owner too
    assert text.splitlines()[-1] == f"next: buzz digest --after-message {d['cursor']['message_id']}"
    assert d["cursor"]["message_id"] > first_id

    # The cursor is exact: nothing before it is repeated.
    again = client.get("/digest", params={"after_message": first_id}).json()
    assert "first" not in again["text"]
    assert "nearly there" in again["text"]
    assert again["text"].startswith(f"swarm digest") and f"since message #{first_id}" in again["text"]
    # Task assignment pasted a message too; it is in the window.
    assert "task #1" in again["text"]

    # A cursor at the newest message yields an empty digest with the same cursor.
    latest = client.get("/digest", params={"after_message": d["cursor"]["message_id"]}).json()
    assert "messages: 0 new" in latest["text"]
    assert latest["cursor"]["message_id"] == d["cursor"]["message_id"]


def test_digest_keeps_the_supervisors_own_threads_out_of_the_listing(client):
    _register(client, "0:0.0", "heron")
    _register(client, "0:1.0", "vole")
    client.put("/supervisor", json={"user_id": "heron"})
    client.post("/send", json={"tmux_pane": "0:1.0", "recipient": "heron", "content": "psst"})
    client.post("/send", json={"tmux_pane": "0:1.0", "recipient": "owner", "content": "report"})
    text = client.get("/digest").json()["text"]
    assert "you are the supervisor: heron" in text
    assert "vole → owner: report" in text
    assert "psst" not in text
    assert "in your own threads not repeated here" in text


def test_digest_shows_attention_and_working_agents(client, monkeypatch):
    client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "heron", "flavor": "claude"})
    _register(client, "0:1.0", "vole")
    client.post("/status", json={"tmux_pane": "0:1.0", "text": "working on #3: the thing"})
    screens = {
        "0:0.0": "Do you want to run rm -rf build?\n❯ 1. Yes\n  2. No\nEsc to cancel",
        "0:1.0": "streaming output",
    }
    monkeypatch.setattr(server.tmux, "capture_pane", lambda pane: (screens[pane], None))
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(server.time, "time", lambda: clock["t"])
    tick = client.app.state.monitor_tick
    for _ in range(4):  # static screens: the prompt is attention, the other idle
        asyncio.run(tick())
        clock["t"] += 30
    text = client.get("/digest").json()["text"]
    assert "needs attention: heron — Do you want to run rm -rf build?" in text
    assert "idle: vole" in text


# ---- nudge -------------------------------------------------------------------


def test_nudge_is_throttled_and_only_about_other_peoples_traffic(client, monkeypatch):
    _register(client, "0:0.0", "heron")
    _register(client, "0:1.0", "vole")
    client.put("/supervisor", json={"user_id": "heron"})
    monkeypatch.setenv("AGENT_SWARM_SUPERVISOR_INTERVAL", "300")
    tick = client.app.state.monitor_tick
    clock = {"t": client.get("/supervisor").json()["supervisor"]["since"]}
    monkeypatch.setattr(server.time, "time", lambda: clock["t"])

    pasted_before = len(_pasted(client, "0:0.0"))
    # Traffic the supervisor is party to does not trigger a nudge.
    client.post("/send", json={"tmux_pane": "0:1.0", "recipient": "heron", "content": "to you"})
    clock["t"] += 301
    asyncio.run(tick())
    assert len(_pasted(client, "0:0.0")) == pasted_before + 1  # the message itself only

    # Traffic between others does, but not before the interval has passed again.
    client.post("/send", json={"tmux_pane": "0:1.0", "recipient": "owner", "content": "done with it"})
    asyncio.run(tick())
    assert len(_pasted(client, "0:0.0")) == pasted_before + 1
    clock["t"] += 301
    asyncio.run(tick())
    nudge = _pasted(client, "0:0.0")[-1]
    assert nudge.startswith("[agent-msg from hub · digest] Since your last digest: 1 new message(s).")
    assert "buzz digest --after-message" in nudge
    cursor = int(nudge.split("--after-message ")[1].split("`")[0])
    # The named cursor reads exactly that traffic.
    assert "vole → owner: done with it" in client.get("/digest", params={"after_message": cursor}).json()["text"]
    # Recorded as from the hub, so the dashboard shows it.
    recorded = client.get("/messages", params={"user": "heron", "limit": 1}).json()["messages"][0]
    assert recorded["sender"] == "hub" and recorded["context"] == "digest"

    # Nothing new: no nudge, even after the interval.
    clock["t"] += 301
    asyncio.run(tick())
    assert _pasted(client, "0:0.0")[-1] == nudge

    # A task change alone is enough.
    clock["t"] += 1
    client.post("/tasks", json={"title": "Follow up"})
    clock["t"] += 301
    asyncio.run(tick())
    assert "1 task change(s)" in _pasted(client, "0:0.0")[-1]


def test_no_nudge_when_disabled_or_supervisor_offline(client, monkeypatch):
    _register(client, "0:0.0", "heron")
    _register(client, "0:1.0", "vole")
    client.put("/supervisor", json={"user_id": "heron"})
    clock = {"t": client.get("/supervisor").json()["supervisor"]["since"]}
    monkeypatch.setattr(server.time, "time", lambda: clock["t"])
    client.post("/send", json={"tmux_pane": "0:1.0", "recipient": "owner", "content": "hi"})
    tick = client.app.state.monitor_tick
    n = len(_pasted(client, "0:0.0"))

    monkeypatch.setattr(server.tmux, "pane_table", lambda: {
        "0:0.0": {"label": "0:0.0", "command": "bash", "title": ""},  # the agent exited
        "0:1.0": {"label": "0:1.0", "command": "claude", "title": ""},
    })
    clock["t"] += 301
    asyncio.run(tick())
    assert len(_pasted(client, "0:0.0")) == n  # supervisor's pane is not live


def test_interval_zero_disables_nudges(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SWARM_SUPERVISOR_INTERVAL", "0")
    from fastapi.testclient import TestClient
    from agent_swarm import tmux

    calls = []
    monkeypatch.setattr(tmux, "deliver", lambda pane, text, **kw: (calls.append((pane, text)), (True, None))[1])
    monkeypatch.setattr(tmux, "list_panes", lambda: {"0:0.0", "0:1.0"})
    monkeypatch.setattr(tmux, "live_agent_panes", lambda: {"0:0.0", "0:1.0"})
    monkeypatch.setattr(tmux, "resolve_pane", lambda t: (t, t) if t in tmux.list_panes() else None)
    monkeypatch.setattr(tmux, "server_id", lambda: "srv-1")
    monkeypatch.setattr(tmux, "server_start_time", lambda: 0.0)
    monkeypatch.setattr(tmux, "pane_table", lambda: {
        "0:0.0": {"label": "0:0.0", "command": "claude", "title": ""},
        "0:1.0": {"label": "0:1.0", "command": "claude", "title": ""},
    })
    monkeypatch.setattr(tmux, "capture_pane", lambda pane: ("$ ", None))
    monkeypatch.setattr(tmux, "tag_pane", lambda pane, handle: (True, None))
    monkeypatch.setattr(tmux, "rename_window", lambda pane, name: (True, None))
    c = TestClient(server.create_app(tmp_path / "db.sqlite", monitor=False), client=("127.0.0.1", 50000))
    c.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "heron"})
    c.post("/register", json={"tmux_pane": "0:1.0", "requested_user": "vole"})
    c.put("/supervisor", json={"user_id": "heron"})
    clock = {"t": c.get("/supervisor").json()["supervisor"]["since"]}
    monkeypatch.setattr(server.time, "time", lambda: clock["t"])
    c.post("/send", json={"tmux_pane": "0:1.0", "recipient": "owner", "content": "hi"})
    n = len(calls)
    clock["t"] += 100000
    asyncio.run(c.app.state.monitor_tick())
    assert len(calls) == n


def test_nudge_delivery_runs_off_the_event_loop(client, monkeypatch):
    """A remote node's send waits on a future scheduled on the server's loop,
    so a nudge sent from the monitor coroutine itself would deadlock until
    the timeout and end unknown. The fake below makes the same round trip."""
    from agent_swarm import nodes

    class LoopBoundNode(nodes.LocalNode):
        loop = None

        def deliver(self, op_id, pane, tmux_server, text, **kw):
            future = asyncio.run_coroutine_threadsafe(asyncio.sleep(0), self.loop)
            try:
                future.result(timeout=1)
            except TimeoutError:
                return nodes.Result("unknown", "the loop was blocked")
            return super().deliver(op_id, pane, tmux_server, text, **kw)

    node = LoopBoundNode("macbook")
    client.app.state.nodes.add(node)
    client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "heron", "node": "macbook"})
    _register(client, "0:1.0", "vole")
    client.put("/supervisor", json={"user_id": "heron"})
    clock = {"t": client.get("/supervisor").json()["supervisor"]["since"]}
    monkeypatch.setattr(server.time, "time", lambda: clock["t"])
    client.post("/send", json={"tmux_pane": "0:1.0", "recipient": "owner", "content": "hi"})
    clock["t"] += 301

    async def run():
        node.loop = asyncio.get_running_loop()
        await client.app.state.monitor_tick()

    asyncio.run(run())
    nudge = client.get("/messages", params={"user": "heron", "limit": 1}).json()["messages"][0]
    assert nudge["sender"] == "hub"
    assert nudge["status"] == "delivered", nudge["delivery_error"]


# ---- renderer ----------------------------------------------------------------


def _agent(user_id, alive=True, status="idle", detail=None, since=None, summary=None, team_id=None):
    return {
        "user_id": user_id, "alive": alive, "team_id": team_id,
        "activity": {"status": status, "detail": detail, "since": since},
        "summaries": [{"text": summary, "source": "agent", "ts": 0}] if summary else [],
    }


def test_render_caps_messages_and_marks_failures():
    now = 1_000_000.0
    msgs = [
        {"id": i, "sender": "a", "recipient": "b", "context": None, "content": f"m{i}",
         "ts": now - 100 + i, "status": "delivered", "delivery_error": None}
        for i in range(1, 51)
    ]
    msgs.append({"id": 51, "sender": "a", "recipient": "c", "context": "t", "content": "lost",
                 "ts": now, "status": "unknown", "delivery_error": "socket dropped"})
    out = digest.render(now, [_agent("a"), _agent("b", alive=False)], [], msgs, 0, now - 3600)
    text = out["text"]
    assert "agents: 1 live (1 idle), 1 offline" in text
    assert "messages: 51 new (0 with owner, 51 agent to agent, 1 failed/unknown)" in text
    assert "… 11 older new message(s) left out; newest 40 follow" in text
    assert "m11" not in text and "b: m12\n" in text
    assert "a → c [t] (unknown: socket dropped): lost" in text
    assert out["cursor"]["message_id"] == 51
    assert out["counts"] == {"messages": 51, "failed": 1, "tasks": 0}


def test_render_tasks_changed_waiting_and_notes():
    now = 1_000_000.0
    tasks = [
        {"id": 3, "title": "Ship it", "status": "done", "assignee": "a", "team_id": None,
         "note": "Run the thing and look at the screen", "created_at": now - 900, "updated_at": now - 10},
        {"id": 2, "title": "Old waiting task", "status": "open", "assignee": None, "team_id": None,
         "note": None, "created_at": now - 90000, "updated_at": now - 90000},
        {"id": 1, "title": "Team job", "status": "picked_up", "assignee": None, "team_id": 7,
         "note": None, "created_at": now - 500, "updated_at": now - 5},
    ]
    out = digest.render(now, [], tasks, [], 0, now - 3600, teams=[{"id": 7, "name": "crew"}])
    text = out["text"]
    assert "tasks: 2 changed, 1 in progress, 1 open and unassigned" in text
    assert "#1 picked_up · team crew · Team job (5s ago)" in text
    assert "#3 done · a · Ship it (10s ago)\n      verify: Run the thing and look at the screen" in text
    assert "waiting: #2 Old waiting task (1d old)" in text
    assert out["counts"]["tasks"] == 2


def test_nudge_text_names_the_cursor():
    text = digest.nudge_text({"messages": 3, "failed": 1, "tasks": 2}, 120)
    assert text.startswith("Since your last digest: 3 new message(s) (1 failed/unknown), 2 task change(s).")
    assert "--after-message 120" in text
