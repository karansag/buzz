"""The dashboard's terminal view gets the pane's colors; screen checks get plain text."""

import shutil
import subprocess
import time
import uuid

import pytest

from agent_swarm import nodes, tmux


@pytest.fixture
def isolated_tmux(monkeypatch):
    if not shutil.which("tmux"):
        pytest.skip("tmux is not installed")
    sock = "capture-test-" + uuid.uuid4().hex
    original = subprocess.run

    def run(argv, **kwargs):
        if argv[0] == "tmux":
            argv = ["tmux", "-L", sock, "-f", "/dev/null", *argv[1:]]
        return original(argv, **kwargs)

    monkeypatch.setattr(tmux.subprocess, "run", run)
    try:
        yield run
    finally:
        run(["tmux", "kill-server"], capture_output=True)


def test_capture_keeps_colors_only_when_asked(isolated_tmux):
    run = isolated_tmux
    run(["tmux", "new-session", "-d", "-s", "t", "-x", "80", "-y", "10",
         "printf 'plain \\033[31mred\\033[0m \\033[38;5;174mpink\\033[0m\\n'; exec sleep 30"],
        check=True, timeout=10)
    pane = run(["tmux", "display-message", "-p", "-t", "t", "#{pane_id}"],
               capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    deadline = time.monotonic() + 5
    while "pink" not in (tmux.capture_pane(pane)[0] or "") and time.monotonic() < deadline:
        time.sleep(0.1)
    plain, err = tmux.capture_pane(pane)
    assert err is None and "plain red pink" in plain and "\x1b" not in plain
    colored, err = tmux.capture_pane(pane, colors=True)
    assert err is None and "\x1b[31mred" in colored and "\x1b[38;5;174mpink" in colored


def test_remote_terminal_view_asks_the_node_for_colors_instead_of_the_plain_observation():
    node = nodes.RemoteNode("mac", 1, loop=None, send=None, close=None, interval=2.0)
    node._last = {"tmux_server": "srv", "captures": {"%1": "plain screen"}}
    node._last_at = time.monotonic()
    calls = []
    node._call = lambda kind, ttl, **args: calls.append((kind, args)) or {
        "status": "ok", "data": {"text": "\x1b[31mred\x1b[0m"}}
    assert node.capture("%1", "srv") == ("plain screen", None)
    assert calls == []
    assert node.capture("%1", "srv", colors=True) == ("\x1b[31mred\x1b[0m", None)
    assert calls == [("capture", {"pane": "%1", "tmux_server": "srv", "colors": True})]


def test_a_remote_screen_for_the_trust_check_never_waits_on_the_node():
    node = nodes.RemoteNode("mac", 1, loop=None, send=None, close=None, interval=2.0)
    node._call = lambda *a, **k: pytest.fail("a message send must not wait on a capture round trip")
    assert node.screen("%1", "srv") is None  # nothing observed yet
    node._last = {"tmux_server": "srv", "captures": {"%1": "screen"}}
    assert node.screen("%1", "srv") == "screen"
    assert node.screen("%1", "other-server") is None
    assert node.screen("%2", "srv") is None
