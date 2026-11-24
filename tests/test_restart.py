"""Pure tests for choosing which agents `buzz restart` restarts."""

import pytest

from agent_swarm import restart, tmux

SERVER = "100:1700000000"


@pytest.fixture(autouse=True)
def no_harness_probe(monkeypatch):
    monkeypatch.setattr(tmux, "harness_accepts", lambda binary, flag: True)


def pane(pane_id, command="claude", cwd="/w"):
    return {"session": "s", "window": 0, "window_name": "w", "layout": "L", "pane": 0,
            "pane_id": pane_id, "cwd": cwd, "command": command}


def agent(handle, pane_id, status="idle", flavor="claude", agent_id="sid", node="n1", server=SERVER):
    return {"user_id": handle, "tmux_pane": pane_id, "tmux_server": server, "node": node,
            "flavor": flavor, "agent_id": agent_id, "model": None, "activity": {"status": status}}


LIVE = [pane("%1", cwd="/repo"), pane("%2", "node"), pane("%3"), pane("%4", "bash"), pane("%5")]
AGENTS = [
    agent("otter", "%1", agent_id="s-otter"),
    agent("tapir", "%2", flavor="codex", agent_id="t-tapir"),
    agent("busy", "%3", status="working"),
    agent("gone", "%4"),                      # its harness exited: a bare shell
    agent("anon", "%5", agent_id=None),
    agent("far", "%9", node="n2"),
]


def by_handle(items):
    return {i.handle: (i.skip or i.launch) for i in items}


def test_all_restarts_idle_resumable_agents_on_this_machine_and_says_why_not():
    got = by_handle(restart.plan(AGENTS, LIVE, "n1", SERVER))
    assert got == {
        "otter": "cd /repo && claude --resume s-otter --permission-mode auto",
        "tapir": "cd /w && codex resume t-tapir -c check_for_update_on_startup=false -c notice.hide_rate_limit_model_nudge=true --yolo --no-daemon",
        "busy": "activity is working; only observed-idle agents restart by default (--force overrides)",
        "gone": "no harness is running in its pane; `buzz restore gone` resumes it there",
        "anon": "no session id, so it could not be resumed",
    }


def test_flavor_force_and_named_handles():
    assert list(by_handle(restart.plan(AGENTS, LIVE, "n1", SERVER, flavor="codex"))) == ["tapir"]
    forced = by_handle(restart.plan(AGENTS, LIVE, "n1", SERVER, handles=["busy"], force=True))
    assert forced == {"busy": "cd /w && claude --resume sid --permission-mode auto"}
    named = by_handle(restart.plan(AGENTS, LIVE, "n1", SERVER, handles=["far", "nobody"]))
    assert named == {"far": "its pane is not in this machine's tmux (node n2)", "nobody": "not registered"}


@pytest.mark.parametrize("status", ["working", "needs_attention", "unknown", "stopped", "future_state", None, ""])
def test_default_restart_rejects_every_unobserved_or_nonidle_activity(status):
    row = agent("probe", "%1", status=status)
    planned = restart.plan([row], [pane("%1")], "n1", SERVER)[0]
    assert planned.skip is not None
    assert "only observed-idle" in planned.skip
    assert "--force" in planned.skip
    forced = restart.plan([row], [pane("%1")], "n1", SERVER, force=True)[0]
    assert forced.skip is None


@pytest.mark.parametrize("activity", [None, {}])
def test_missing_activity_is_skipped_and_force_can_override(activity):
    row = agent("probe", "%1")
    if activity is None:
        row.pop("activity")
    else:
        row["activity"] = activity
    assert "unknown (no activity report)" in restart.plan([row], [pane("%1")], "n1", SERVER)[0].skip
    assert restart.plan([row], [pane("%1")], "n1", SERVER, force=True)[0].skip is None


def test_force_keeps_pane_and_session_safety_checks():
    planned = {p.handle:p for p in restart.plan(AGENTS, LIVE, "n1", SERVER,
                                               handles=["gone", "anon", "far"], force=True)}
    assert "no harness" in planned["gone"].skip
    assert "no session id" in planned["anon"].skip
    assert "not in this machine" in planned["far"].skip


def test_restart_cli_all_uses_the_hub_and_limits_a_node_to_its_own_agents(monkeypatch, capsys):
    import httpx

    from agent_swarm import client

    rows = [
        {**agent("puffin", "%1", flavor="pi"), "alive": True},
        {**agent("far", "%1", flavor="pi", node="n2"), "alive": True},
        {**agent("other", "%2", flavor="claude"), "alive": True},
        {**agent("stopped", "%3", flavor="pi"), "alive": False},
    ]
    gets = []
    posts = []
    monkeypatch.setattr(client, "base_url", lambda: "http://hub")
    monkeypatch.setattr(client, "_headers", lambda: {"Authorization": "Bearer fake-node"})
    monkeypatch.delenv("TMUX_PANE", raising=False)

    def get(url, **kw):
        gets.append((url, kw["headers"]))
        data = {"recipients": rows} if url.endswith("/recipients") else {"kind": "node", "node": "n1"}
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))

    def post(url, **kw):
        posts.append((url, kw["json"]))
        return httpx.Response(200, json={"status": "restarted", "node": "n1"})

    monkeypatch.setattr(client.httpx, "get", get)
    monkeypatch.setattr(client.httpx, "post", post)
    assert client.main(["restart", "--all", "--flavor", "pi", "--force", "--apply"]) == 0
    assert gets == [(f"http://hub/{path}", {"Authorization": "Bearer fake-node"})
                    for path in ("recipients", "nodes/me")]
    assert posts == [("http://hub/agents/puffin/restart", {"force": True, "dry_run": False})]
    assert "restarted puffin on n1" in capsys.readouterr().out


def test_local_respawn_checks_the_server_and_running_pane_before_launching(monkeypatch):
    from agent_swarm import nodes

    row = {"command": "pi", "cwd": "/a folder"}
    monkeypatch.setattr(tmux, "server_id", lambda: SERVER)
    monkeypatch.setattr(tmux, "pane_table", lambda: {"%1": row})
    calls = []

    def record(kind):
        def operation(*args, **kwargs):
            calls.append((kind, args, kwargs))
            return True, None
        return operation

    monkeypatch.setattr(tmux, "respawn_pane", record("respawn"))
    monkeypatch.setattr(tmux, "type_line", record("type"))
    local = nodes.LocalNode("n1")
    assert not local.respawn("old", "%1", "old-server", "/a folder", "pi --session id").ok
    assert not local.respawn("changed", "%1", SERVER, "/old", "pi --session id").ok
    assert not calls
    assert local.respawn("valid", "%1", SERVER, "/a folder", "pi --session id").ok
    assert calls == [("respawn", ("%1", "/a folder"),
                      {"launch": "cd '/a folder' && pi --session id"})]
