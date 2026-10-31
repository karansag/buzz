"""Pure tests for choosing which agents `agent-swarm restart` restarts."""

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
        "tapir": "cd /w && codex resume t-tapir -c check_for_update_on_startup=false --yolo --no-daemon",
        "busy": "it is working (--force restarts it anyway)",
        "gone": "no harness is running in its pane",
        "anon": "no session id, so it could not be resumed",
    }


def test_flavor_force_and_named_handles():
    assert list(by_handle(restart.plan(AGENTS, LIVE, "n1", SERVER, flavor="codex"))) == ["tapir"]
    forced = by_handle(restart.plan(AGENTS, LIVE, "n1", SERVER, handles=["busy"], force=True))
    assert forced == {"busy": "cd /w && claude --resume sid --permission-mode auto"}
    named = by_handle(restart.plan(AGENTS, LIVE, "n1", SERVER, handles=["far", "nobody"]))
    assert named == {"far": "its pane is not in this machine's tmux (node n2)", "nobody": "not registered"}


def test_own_pane_is_handed_to_the_tmux_server(monkeypatch):
    calls = []
    monkeypatch.setattr(restart.subprocess, "run", lambda argv, **kw: calls.append(argv))
    item = restart.Restart("otter", "%1", "/repo", "claude --resume s")
    assert restart.apply(item, own_pane="%7") is None
    assert [c[1] for c in calls] == ["respawn-pane", "send-keys", "send-keys"]
    assert calls[0] == ["tmux", "respawn-pane", "-k", "-t", "%1", "-c", "/repo"]
    calls.clear()
    assert restart.apply(item, own_pane="%1") is None
    assert len(calls) == 1 and calls[0][1:3] == ["run-shell", "-b"]
    assert "respawn-pane -k -t %1" in calls[0][3] and "claude --resume s" in calls[0][3]
