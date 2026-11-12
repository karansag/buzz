from __future__ import annotations

from argparse import Namespace
from types import SimpleNamespace

import httpx
import pytest

from agent_swarm import client, config, tmux


def test_unregister_defaults_to_current_pane(monkeypatch):
    calls = []
    monkeypatch.setattr(client, "current_pane", lambda: "marin:1.2")
    monkeypatch.setattr(
        client, "whoami_lookup", lambda who: {"user_id": "marten" if who["pane"] == "marin:1.2" else None}
    )
    monkeypatch.setattr(client, "base_url", lambda: "http://localhost:8765")

    def delete(url, headers, timeout):
        calls.append((url, timeout))
        return SimpleNamespace(text='{"ok":true}', is_success=True)

    monkeypatch.setattr(client.httpx, "delete", delete)
    assert client.main(["unregister"]) == 0
    assert calls == [("http://localhost:8765/recipients/marten", 5)]


def test_unregister_explicit_handle_propagates_failure(monkeypatch):
    monkeypatch.setattr(client, "current_pane", lambda: None)
    monkeypatch.setattr(client.httpx, "delete", lambda url, headers, timeout: SimpleNamespace(text="not registered", is_success=False))
    assert client.main(["unregister", "--user", "marten"]) == 1


def test_unregister_without_identity_does_not_delete(monkeypatch, capsys):
    monkeypatch.setattr(client, "current_pane", lambda: None)
    assert client.main(["unregister"]) == 2
    assert "pass --user HANDLE" in capsys.readouterr().err


def test_current_pane_targets_tmux_pane_env(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output, text, check, timeout):
        calls.append(cmd)
        return SimpleNamespace(stdout="%177\n")

    monkeypatch.setenv("TMUX_PANE", "%177")
    monkeypatch.setattr(tmux.subprocess, "run", fake_run)

    # The stable pane id, not the positional session:window.pane.
    assert tmux.current_pane() == "%177"
    assert calls == [
        ["tmux", "display-message", "-p", "-t", "%177", "#{pane_id}"]
    ]


def test_current_pane_without_tmux_pane_env_uses_tmux_current_target(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output, text, check, timeout):
        calls.append(cmd)
        return SimpleNamespace(stdout="%5\n")

    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.setattr(tmux.subprocess, "run", fake_run)

    assert tmux.current_pane() == "%5"
    assert calls == [["tmux", "display-message", "-p", "#{pane_id}"]]


def test_flavor_defaults_cover_pi_and_hermes():
    assert tmux.submit_key_for_flavor("pi") == "Enter"
    assert tmux.submit_key_for_flavor("hermes") == "C-m"
    assert tmux.infer_flavor("pi") == "pi"
    assert tmux.infer_flavor("pi-coding-agent") == "pi"
    assert tmux.infer_flavor("hermes-agent") == "hermes"
    assert tmux.infer_flavor("github-copilot/gpt-5.5") == "generic"


def _paste_calls(pane, text):
    return [
        ["tmux", "load-buffer", "-b", ANY_BUF, "-"],
        ["tmux", "paste-buffer", "-p", "-d", "-b", ANY_BUF, "-t", pane],
    ]


class _AnyBuf(str):
    def __eq__(self, other):
        return isinstance(other, str) and other.startswith("agent-swarm-")


ANY_BUF = _AnyBuf()


def _fake_run(calls):
    def fake_run(cmd, capture_output, text, check, timeout, input=None):
        calls.append(cmd)
        return SimpleNamespace(stdout="")
    return fake_run


def test_deliver_pastes_then_submits_with_configured_key(monkeypatch):
    calls = []
    monkeypatch.setattr(tmux.subprocess, "run", _fake_run(calls))
    monkeypatch.setattr(tmux, "_composer_holds_text", lambda pane: False)
    monkeypatch.setattr(tmux.time, "sleep", lambda seconds: None)

    assert tmux.deliver("session-a:9.0", "hello", submit_key="Enter", flavor="pi") == (
        True,
        None,
    )
    assert calls == _paste_calls("session-a:9.0", "hello") + [
        ["tmux", "send-keys", "-t", "session-a:9.0", "Enter"],
    ]


def test_deliver_retries_submit_once_when_composer_still_holds_text(monkeypatch):
    calls = []
    monkeypatch.setattr(tmux.subprocess, "run", _fake_run(calls))
    monkeypatch.setattr(tmux, "_composer_holds_text", lambda pane: True)
    clock = _FakeClock()
    monkeypatch.setattr(tmux.time, "sleep", clock.sleep)
    monkeypatch.setattr(tmux.time, "monotonic", clock.monotonic)

    assert tmux.deliver(
        "session-a:9.0", "[agent-msg from manatee] hello", submit_key="Enter"
    ) == (True, None)
    assert calls.count(["tmux", "send-keys", "-t", "session-a:9.0", "Enter"]) == 2


def test_deliver_without_retry_submits_once(monkeypatch):
    # A menu row under the cursor looks like unsent text; no second key.
    calls = []
    monkeypatch.setattr(tmux.subprocess, "run", _fake_run(calls))
    monkeypatch.setattr(tmux, "_composer_holds_text", lambda pane: True)
    monkeypatch.setattr(tmux.time, "sleep", lambda s: None)

    assert tmux.deliver(
        "session-a:9.0", "/model", submit_key="Enter", retry_submit=False
    ) == (True, None)
    assert calls.count(["tmux", "send-keys", "-t", "session-a:9.0", "Enter"]) == 1


def test_deliver_does_not_retry_after_composer_clears(monkeypatch):
    calls = []
    monkeypatch.setattr(tmux.subprocess, "run", _fake_run(calls))
    monkeypatch.setattr(tmux, "_composer_holds_text", lambda pane: False)
    monkeypatch.setattr(tmux.time, "sleep", lambda seconds: None)

    assert tmux.deliver(
        "session-a:9.0", "[agent-msg from manatee] hello", submit_key="Enter"
    ) == (True, None)
    assert calls.count(["tmux", "send-keys", "-t", "session-a:9.0", "Enter"]) == 1


def test_deliver_reports_tmux_failure(monkeypatch):
    def failing_run(cmd, capture_output, text, check, timeout, input=None):
        raise tmux.subprocess.CalledProcessError(1, cmd, stderr="can't find pane")

    monkeypatch.setattr(tmux.subprocess, "run", failing_run)
    assert tmux.deliver("session-a:9.0", "hello") == (False, "can't find pane")


def test_cmd_register_uses_detected_current_pane(monkeypatch, capsys):
    monkeypatch.setattr(tmux, "process_in_pane", lambda pane: None)
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return SimpleNamespace(text='{"ok": true}', is_success=True)

    monkeypatch.setattr(client, "current_pane", lambda: "session-a:9.0")
    monkeypatch.setenv("AGENT_SWARM_NODE", "testbox")
    monkeypatch.setattr(client.httpx, "post", fake_post)

    args = Namespace(
        pane=None,
        name=None,
        agent_id=None,
        model=None,
        flavor=None,
        instructions=None,
        message_prefix=None,
        submit_key=None,
    )

    assert client.cmd_register(args) == 0
    # The node travels with every registration and is stored on the row.
    assert captured["json"] == {"tmux_pane": "session-a:9.0", "node": "testbox"}
    assert capsys.readouterr().out == '{"ok": true}\n'


def test_cmd_task_update_records_worktree(monkeypatch, capsys):
    monkeypatch.setattr(tmux, "process_in_pane", lambda pane: None)
    captured = {}

    def fake_patch(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        return SimpleNamespace(text='{"ok": true}', is_success=True)

    monkeypatch.setattr(client.httpx, "patch", fake_patch)
    monkeypatch.setattr(client, "current_pane", lambda: "%3")
    monkeypatch.setattr(client, "local_node", lambda: "testbox")
    args = Namespace(
        id=7,
        status="picked_up",
        assignee=None,
        worktree="/tmp/repo-task-7",
        depends_on=None,
        note=None,
    )

    assert client.cmd_task_update(args) == 0
    assert captured["url"].endswith("/tasks/7")
    # A path only means something on the machine it is on, and the update is
    # signed by the pane it came from.
    assert captured["json"] == {
        "status": "picked_up",
        "worktree": "/tmp/repo-task-7",
        "worktree_node": "testbox",
        "tmux_pane": "%3",
        "node": "testbox",
    }
    assert capsys.readouterr().out == '{"ok": true}\n'


def test_cmd_task_create_files_task(monkeypatch, capsys):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        return SimpleNamespace(text='{"ok": true, "task": {"id": 8}}', is_success=True)

    monkeypatch.setattr(client, "current_pane", lambda: None)  # outside tmux: no acting pane
    monkeypatch.setattr(client.httpx, "post", fake_post)
    args = Namespace(
        title="Investigate flaky build",
        description="CI failed twice",
        assignee="stoat",
        depends_on="3,5",
    )

    assert client.cmd_task_create(args) == 0
    assert captured["url"].endswith("/tasks")
    assert captured["json"] == {
        "title": "Investigate flaky build",
        "description": "CI failed twice",
        "assignee": "stoat",
        "depends_on": [3, 5],
    }
    assert capsys.readouterr().out == '{"ok": true, "task": {"id": 8}}\n'


def test_cmd_register_sends_requested_name(monkeypatch, capsys):
    monkeypatch.setattr(tmux, "process_in_pane", lambda pane: None)
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["json"] = json
        return SimpleNamespace(text='{"ok": true}', is_success=True)

    monkeypatch.setattr(client, "current_pane", lambda: "session-a:9.0")
    monkeypatch.setenv("AGENT_SWARM_NODE", "testbox")
    monkeypatch.setattr(client.httpx, "post", fake_post)

    args = Namespace(
        pane=None,
        name="jax",
        agent_id=None,
        model=None,
        flavor=None,
        instructions=None,
        message_prefix=None,
        submit_key=None,
    )

    assert client.cmd_register(args) == 0
    assert captured["json"] == {
        "tmux_pane": "session-a:9.0",
        "node": "testbox",
        "requested_user": "jax",
    }
    capsys.readouterr()


def test_live_agent_panes_excludes_bare_shells(monkeypatch):
    def fake_run(cmd, capture_output, text, check, timeout):
        return SimpleNamespace(stdout=(
            "%1\ta:0.0\tclaude\tt\n%2\ta:0.1\tbash\tt\n%3\tb:2.0\tnode\tt\n%4\tc:0.0\tzsh\tt\n"
        ))

    monkeypatch.setattr(tmux.subprocess, "run", fake_run)
    assert tmux.live_agent_panes() == {"%1", "%3"}
    assert tmux.pane_table()["%3"] == {"label": "b:2.0", "command": "node", "title": "t", "cwd": ""}


def test_offline_reason_distinguishes_gone_from_shell():
    existing, live = {"a:0.0", "a:0.1"}, {"a:0.0"}
    assert tmux.offline_reason("a:0.0", existing, live) is None
    assert "bare shell" in tmux.offline_reason("a:0.1", existing, live)
    assert "no longer exists" in tmux.offline_reason("z:9.9", existing, live)


def test_base_url_accepts_legacy_environment_name(monkeypatch):
    monkeypatch.delenv("AGENT_SWARM_URL", raising=False)
    monkeypatch.setenv("AGENT_MSG_URL", "http://legacy.example:9999")
    assert client.base_url() == "http://legacy.example:9999"


def test_base_url_prefers_new_environment_name(monkeypatch):
    monkeypatch.setenv("AGENT_MSG_URL", "http://legacy.example:9999")
    monkeypatch.setenv("AGENT_SWARM_URL", "http://new.example:8765")
    assert client.base_url() == "http://new.example:8765"


def test_cmd_task_update_forwards_the_closing_note(monkeypatch, capsys):
    captured = {}

    def fake_patch(url, json, headers, timeout):
        captured["json"] = json
        return SimpleNamespace(text='{"ok": true}', is_success=True)

    monkeypatch.setattr(client, "current_pane", lambda: None)  # outside tmux: no acting pane
    monkeypatch.setattr(client.httpx, "patch", fake_patch)
    args = Namespace(
        id=42,
        status="done",
        assignee=None,
        worktree=None,
        depends_on=None,
        note="Run the suite; see tests/test_server.py.",
    )

    assert client.cmd_task_update(args) == 0
    assert captured["json"] == {
        "status": "done",
        "note": "Run the suite; see tests/test_server.py.",
    }
    capsys.readouterr()


class _FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def monotonic(self):
        return self.now


def test_deliver_returns_as_soon_as_the_submit_lands(monkeypatch):
    calls = []
    clock = _FakeClock()
    checks = iter([True, True, False])  # the composer clears on the third poll
    monkeypatch.setattr(tmux.subprocess, "run", _fake_run(calls))
    monkeypatch.setattr(tmux, "_composer_holds_text", lambda pane: next(checks))
    monkeypatch.setattr(tmux.time, "sleep", clock.sleep)
    monkeypatch.setattr(tmux.time, "monotonic", clock.monotonic)

    assert tmux.deliver("s:0.0", "hello", submit_key="Enter") == (True, None)
    assert calls.count(["tmux", "send-keys", "-t", "s:0.0", "Enter"]) == 1
    # Three polls, not the whole verify window.
    assert clock.now < 0.5 < tmux.SUBMIT_VERIFY_DELAY


def test_deliver_retries_only_after_the_whole_verify_window(monkeypatch):
    calls = []
    clock = _FakeClock()
    monkeypatch.setattr(tmux.subprocess, "run", _fake_run(calls))
    monkeypatch.setattr(tmux, "_composer_holds_text", lambda pane: True)
    monkeypatch.setattr(tmux.time, "sleep", clock.sleep)
    monkeypatch.setattr(tmux.time, "monotonic", clock.monotonic)

    tmux.deliver("s:0.0", "hello", submit_key="Enter")
    assert calls.count(["tmux", "send-keys", "-t", "s:0.0", "Enter"]) == 2
    assert clock.now >= tmux.SUBMIT_VERIFY_DELAY


@pytest.mark.parametrize(
    "title, summary",
    [
        ("✳ PR 9130 review", "PR 9130 review"),
        ("⠐ Naming variety", "Naming variety"),
        ("Summarize open pull requests | marin", "Summarize open pull requests"),
        ("✳ Claude Code", None),
        ("agent-swarm: jax (claude)", None),
        ("", None),
    ],
)
def test_title_summary_reads_harness_titles(title, summary):
    assert tmux.title_summary(title) == summary


def test_title_summary_ignores_the_default_host_title():
    assert tmux.title_summary(tmux.socket.gethostname()) is None


def _fake_tree(monkeypatch, pane_pid, parents):
    """A fake process table: `parents` maps pid -> ppid."""
    monkeypatch.setattr(tmux, "_tmux_out", lambda *a, **k: f"{pane_pid}\n")
    ps_out = "".join(f"{pid} {ppid}\n" for pid, ppid in parents.items())
    monkeypatch.setattr(
        tmux.subprocess, "run",
        lambda cmd, **k: SimpleNamespace(stdout=ps_out, returncode=0),
    )


def test_a_process_under_the_pane_is_in_it(monkeypatch):
    _fake_tree(monkeypatch, pane_pid=100, parents={300: 200, 200: 100, 100: 1})
    assert tmux.process_in_pane("%5", pid=300) is True


def test_a_shared_daemon_is_not_in_the_pane_its_env_names(monkeypatch):
    # The Codex daemon hangs off launchd, not off the pane that started it.
    _fake_tree(monkeypatch, pane_pid=100, parents={400: 390, 390: 1, 100: 1})
    assert tmux.process_in_pane("%5", pid=400) is False


def test_process_in_pane_is_unknown_without_tmux(monkeypatch):
    monkeypatch.setattr(tmux, "_tmux_out", lambda *a, **k: None)
    assert tmux.process_in_pane("%5", pid=1) is None


def _fake_server(monkeypatch, answer):
    """Stub /whoami (returning `answer`) and /send; returns the recorded calls."""
    calls = {"get": [], "post": []}

    def get(url, params, headers, timeout):
        calls["get"].append(params)
        return SimpleNamespace(is_success=True, json=lambda: answer)

    def post(url, json, headers, timeout):
        calls["post"].append(json)
        return SimpleNamespace(is_success=True, text='{"ok": true}')

    monkeypatch.setattr(client.httpx, "get", get)
    monkeypatch.setattr(client.httpx, "post", post)
    monkeypatch.setattr(client, "local_node", lambda: "laptop")
    return calls


def test_harness_session_id_comes_from_the_environment(monkeypatch):
    assert client.harness_session_id() is None
    monkeypatch.setenv("CODEX_THREAD_ID", "codex-thread")
    assert client.harness_session_id() == "codex-thread"
    monkeypatch.delenv("CODEX_THREAD_ID")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "claude-session")
    assert client.harness_session_id() == "claude-session"


def test_with_both_ids_set_the_nearest_harness_wins(monkeypatch):
    # A Codex agent that launched `claude -p`: inside it, Claude is the caller.
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "claude-session")
    monkeypatch.setenv("CODEX_THREAD_ID", "codex-thread")
    monkeypatch.setattr(tmux, "ancestors", lambda pid=None: [
        (3, "/bin/zsh -c x"), (2, "claude -p hi"), (1, "codex --no-daemon --yolo"),
    ])
    assert client.harness_session_id() == "claude-session"
    monkeypatch.setattr(tmux, "ancestors", lambda pid=None: [
        (3, "/bin/zsh -c x"), (2, "codex exec hi"), (1, "/Users/k/.local/share/claude/versions/2.1.280"),
    ])
    assert client.harness_session_id() == "codex-thread"


def test_attached_command_sends_its_session_and_verified_pane(monkeypatch):
    # A harness whose commands run inside its own pane.
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-a")
    monkeypatch.setattr(client, "current_pane", lambda: "%5")
    monkeypatch.setattr(tmux, "process_in_pane", lambda pane, pid=None: True)
    calls = _fake_server(monkeypatch, {"user_id": "otter", "identified_by": "session"})
    assert client.main(["send", "--to", "owner", "--message", "hi"]) == 0
    assert calls["get"][0] == {"node": "laptop", "tmux_pane": "%5", "agent_id": "sess-a", "pane_verified": "true",
                               "pane_in_tree": "true", "harness": "claude"}
    assert calls["post"][0]["agent_id"] == "sess-a" and calls["post"][0]["pane_verified"] is True
    # Inside its own pane: the hub may move the registration to this session.
    assert calls["post"][0]["pane_in_tree"] is True and calls["post"][0]["harness"] == "claude"


def test_daemon_command_sends_by_session_without_a_pane(monkeypatch, capsys):
    # A Claude Code background host or Codex app-server: no TMUX_PANE, so the
    # pane is tmux's active-pane guess and unverified. The session id decides.
    monkeypatch.delenv("TMUX_PANE", raising=False)
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-b")
    monkeypatch.setattr(client, "current_pane", lambda: "%49")
    monkeypatch.setattr(tmux, "process_in_pane", lambda pane, pid=None: False)
    calls = _fake_server(monkeypatch, {"user_id": "stoat", "identified_by": "session"})
    assert client.main(["send", "--to", "owner", "--message", "hi"]) == 0
    assert calls["post"][0]["agent_id"] == "thread-b" and calls["post"][0]["pane_verified"] is False
    assert "pane_in_tree" not in calls["post"][0]


def test_daemon_command_with_an_unregistered_session_is_refused(monkeypatch, capsys):
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-unknown")
    monkeypatch.setattr(client, "current_pane", lambda: "%98")
    monkeypatch.setattr(tmux, "process_in_pane", lambda pane, pid=None: False)
    calls = _fake_server(monkeypatch, {"user_id": None, "detail": "this session is not registered"})
    assert client.main(["send", "--to", "owner", "--message", "hi"]) == 2
    assert calls["post"] == []  # nothing sent as the agent in %98
    assert "not registered" in capsys.readouterr().err


def test_without_a_session_id_a_borrowed_pane_is_refused(monkeypatch, capsys):
    monkeypatch.setenv("TMUX_PANE", "%98")
    monkeypatch.setattr(client, "current_pane", lambda: "%98")
    monkeypatch.setattr(tmux, "process_in_pane", lambda pane, pid=None: False)
    calls = _fake_server(monkeypatch, {"user_id": None, "detail": "x"})
    assert client.main(["send", "--to", "owner", "--message", "hi"]) == 2
    assert calls["post"] == []
    assert "not running inside tmux pane %98" in capsys.readouterr().err


def test_register_refuses_a_pane_the_caller_is_not_in(monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-c")
    monkeypatch.setattr(client, "current_pane", lambda: "%49")
    monkeypatch.setattr(tmux, "process_in_pane", lambda pane, pid=None: False)
    calls = _fake_server(monkeypatch, {})
    assert client.main(["register", "--name", "explainer"]) == 2
    assert calls["post"] == []
    assert "--pane" in capsys.readouterr().err


def test_register_with_an_explicit_pane_binds_it_and_the_session(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-c")
    monkeypatch.setattr(client, "current_pane", lambda: "%49")
    monkeypatch.setattr(tmux, "process_in_pane", lambda pane, pid=None: False)
    calls = _fake_server(monkeypatch, {})
    assert client.main(["register", "--name", "explainer", "--pane", "%64"]) == 0
    assert calls["post"][0]["tmux_pane"] == "%64" and calls["post"][0]["agent_id"] == "sess-c"


def test_explicit_agent_id_beats_the_environment(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "from-env")
    monkeypatch.setattr(client, "current_pane", lambda: "%5")
    monkeypatch.setattr(tmux, "process_in_pane", lambda pane, pid=None: True)
    calls = _fake_server(monkeypatch, {})
    assert client.main(["register", "--agent-id", "explicit"]) == 0
    assert calls["post"][0]["agent_id"] == "explicit"


def test_registered_user_asks_the_server_for_this_pane_on_this_node(monkeypatch):
    # Matching the pane id alone would confuse this pane with one of the same
    # id on another machine, so the CLI hands the full address to the server.
    captured = {}
    monkeypatch.setattr(client, "base_url", lambda: "http://localhost:8765")
    monkeypatch.setattr(client, "local_node", lambda: "laptop")

    def get(url, params, headers, timeout):
        captured["url"], captured["params"] = url, params
        return SimpleNamespace(is_success=True, json=lambda: {"user_id": "laptop-agent"})

    monkeypatch.setattr(client.httpx, "get", get)
    monkeypatch.setattr(tmux, "process_in_pane", lambda pane, pid=None: True)
    assert client.registered_user("%1") == "laptop-agent"
    assert captured["url"] == "http://localhost:8765/whoami"
    assert captured["params"] == {"tmux_pane": "%1", "node": "laptop", "pane_verified": "true", "pane_in_tree": "true"}
    monkeypatch.setattr(client.httpx, "get", lambda url, params, headers, timeout: SimpleNamespace(is_success=False))
    assert client.registered_user("%1") is None


def test_settings_come_from_env_then_file_then_defaults(monkeypatch, tmp_path):
    from agent_swarm import config

    monkeypatch.setenv("AGENT_SWARM_CONFIG", str(tmp_path / "node.toml"))
    monkeypatch.setattr(config.socket, "gethostname", lambda: "laptop.local")
    assert config.load() == config.Settings("http://127.0.0.1:8765", None, "laptop")
    path = config.write("http://workstation:8765/", "s3cret", "macbook")
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert config.load() == config.Settings("http://workstation:8765", "s3cret", "macbook")
    assert client.base_url() == "http://workstation:8765"
    assert client._headers() == {"Authorization": "Bearer s3cret"}
    assert tmux.local_node() == "macbook"
    monkeypatch.setenv("AGENT_SWARM_URL", "http://other:1")
    monkeypatch.setenv("AGENT_SWARM_NODE", "override")
    assert config.load().hub == "http://other:1" and config.load().node == "override"


def test_join_writes_settings_and_checks_the_hub(monkeypatch, tmp_path, capsys):
    from agent_swarm import config

    monkeypatch.setenv("AGENT_SWARM_CONFIG", str(tmp_path / "node.toml"))
    seen = {}

    def get(url, headers=None, timeout=5):
        seen[url] = headers
        return SimpleNamespace(is_success=True, status_code=200, json=lambda: {"kind": "node", "node": "macbook"})

    monkeypatch.setattr(client.httpx, "get", get)
    assert client.main(["join", "http://hub:8765", "--token", "tok", "--node", "macbook"]) == 0
    assert seen["http://hub:8765/nodes/me"] == {"Authorization": "Bearer tok"}
    assert config.load() == config.Settings("http://hub:8765", "tok", "macbook")
    assert '"hub_reachable": true' in capsys.readouterr().out


def test_node_token_asks_the_hub_and_prints_the_join_command(monkeypatch, capsys):
    monkeypatch.setattr(client, "base_url", lambda: "http://hub:8765")
    monkeypatch.setattr(
        client.httpx, "post",
        lambda url, headers, timeout: SimpleNamespace(
            is_success=True, json=lambda: {"ok": True, "name": "macbook", "token": "tok"}
        ),
    )
    assert client.main(["node-token", "macbook"]) == 0
    out, err = capsys.readouterr()
    assert '"token": "tok"' in out
    assert "buzz join http://hub:8765 --token tok --node macbook" in err


def test_node_token_guesses_a_reachable_hub_address_for_a_loopback_hub(monkeypatch, capsys):
    from agent_swarm import config

    monkeypatch.setattr(client, "base_url", lambda: "http://127.0.0.1:8765")
    monkeypatch.setattr(config.socket, "gethostname", lambda: "workstation.local")
    monkeypatch.setattr(
        client.httpx, "post",
        lambda url, headers, timeout: SimpleNamespace(
            is_success=True, json=lambda: {"ok": True, "name": "macbook", "token": "t k"}
        ),
    )
    assert client.main(["node-token", "macbook"]) == 0
    err = capsys.readouterr().err
    assert "buzz join http://workstation:8765 --token 't k' --node macbook" in err
    assert "guessed" in err


def test_join_verifies_the_token_names_this_node(monkeypatch, tmp_path, capsys):
    from agent_swarm import config

    monkeypatch.setenv("AGENT_SWARM_CONFIG", str(tmp_path / "node.toml"))
    answers = {"/health": SimpleNamespace(is_success=True, status_code=200)}

    def get(url, headers=None, timeout=5):
        return answers[url.split("8765", 1)[1]]

    monkeypatch.setattr(client.httpx, "get", get)
    answers["/nodes/me"] = SimpleNamespace(is_success=False, status_code=401)
    assert client.main(["join", "http://hub:8765", "--token", "bad", "--node", "macbook"]) == 1
    assert "rejected the token" in capsys.readouterr().err
    answers["/nodes/me"] = SimpleNamespace(is_success=True, status_code=200, json=lambda: {"kind": "node", "node": "laptop"})
    assert client.main(["join", "http://hub:8765", "--token", "tok", "--node", "macbook"]) == 1
    assert "belongs to node 'laptop'" in capsys.readouterr().err
    answers["/nodes/me"] = SimpleNamespace(is_success=True, status_code=200, json=lambda: {"kind": "node", "node": "macbook"})
    assert client.main(["join", "http://hub:8765", "--token", "tok", "--node", "macbook"]) == 0
    assert '"enrolled": true' in capsys.readouterr().out
    assert config.load() == config.Settings("http://hub:8765", "tok", "macbook")


def test_a_hostname_derived_node_name_is_remembered(monkeypatch):
    # macOS renames the host with the network; agents must keep one node name.
    monkeypatch.setattr(config.socket, "gethostname", lambda: "Karans-MBP.local")
    assert config.load().node == "karans-mbp"
    monkeypatch.setattr(config.socket, "gethostname", lambda: "Karans-MacBook-Pro.local")
    assert config.load().node == "karans-mbp"
    assert 'node = "karans-mbp"' in config.config_path().read_text()


def test_remembering_the_name_keeps_the_file_and_ignores_env_overrides(monkeypatch):
    config.config_path().write_text('hub = "http://hub.example:8765"\ntoken = "t0k"\n')
    monkeypatch.setenv("AGENT_SWARM_URL", "http://override.example:9")
    monkeypatch.setattr(config.socket, "gethostname", lambda: "box")
    assert config.load().node == "box"
    saved = config.config_path().read_text()
    assert 'hub = "http://hub.example:8765"' in saved and 'token = "t0k"' in saved
    assert "override" not in saved


def test_an_explicit_node_name_is_not_written(monkeypatch):
    monkeypatch.setenv("AGENT_SWARM_NODE", "pinned")
    assert config.load().node == "pinned"
    assert not config.config_path().exists()


def test_an_unwritable_settings_file_does_not_break_the_cli(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_SWARM_CONFIG", str(tmp_path / "ro" / "node.toml"))
    (tmp_path / "ro").mkdir()
    (tmp_path / "ro").chmod(0o500)
    monkeypatch.setattr(config.socket, "gethostname", lambda: "box")
    try:
        assert config.load().node == "box"
    finally:
        (tmp_path / "ro").chmod(0o700)


def test_ambiguous_nested_sessions_are_an_error_not_a_guess(monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "claude-session")
    monkeypatch.setenv("CODEX_THREAD_ID", "codex-thread")
    monkeypatch.setattr(tmux, "ancestors", lambda pid=None: [(3, "/bin/zsh -c x"), (1, "launchd")])
    monkeypatch.setattr(client, "current_pane", lambda: "%5")
    monkeypatch.setattr(tmux, "process_in_pane", lambda pane, pid=None: True)
    calls = _fake_server(monkeypatch, {"user_id": "otter", "identified_by": "session"})
    assert client.main(["send", "--to", "owner", "--message", "hi"]) == 2
    assert calls["post"] == []
    assert "--agent-id" in capsys.readouterr().err
    # An explicit id bypasses detection.
    assert client.main(["register", "--agent-id", "chosen"]) == 0
    assert calls["post"][-1]["agent_id"] == "chosen"


def test_task_commands_keep_unverified_identity_for_server_refusal(monkeypatch):
    # Not in the pane and no session: crediting tmux's active agent would be wrong.
    monkeypatch.setattr(client, "current_pane", lambda: "%49")
    monkeypatch.setattr(tmux, "process_in_pane", lambda pane, pid=None: False)
    assert client._acting_fields()["pane_verified"] is False
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sess-x")
    fields = client._acting_fields()
    assert fields["agent_id"] == "sess-x" and fields["pane_verified"] is False


def test_process_in_pane_refuses_a_dead_pane_on_a_reachable_server(monkeypatch):
    monkeypatch.setattr(tmux, "_tmux_out", lambda *args: None)
    monkeypatch.setattr(tmux, "server_id", lambda: "running-server")
    assert tmux.process_in_pane("%115") is False


def test_harness_of_names_each_harness_process():
    assert client.harness_of("claude --permission-mode bypassPermissions") == "claude"
    assert client.harness_of("/home/k/.local/share/claude/versions/2.1.280") == "claude"
    assert client.harness_of(
        "/n/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x/bin/codex --yolo"
    ) == "codex"
    assert client.harness_of("pi") == "pi"
    assert client.harness_of("node /n/bin/pip install x") is None
    assert client.harness_of("/bin/bash -c buzz register") is None


def _register_under(monkeypatch, *ancestry):
    monkeypatch.setattr(tmux, "ancestors", lambda pid=None: [(9, "/bin/bash -c x"), *enumerate(ancestry)])
    monkeypatch.setattr(client, "current_pane", lambda: "%5")
    monkeypatch.setattr(tmux, "process_in_pane", lambda pane, pid=None: True)
    return _fake_server(monkeypatch, {})


def test_register_takes_flavor_and_model_from_pi(monkeypatch):
    monkeypatch.setenv("PI_MODEL", "gpt-6.1-sol")
    calls = _register_under(monkeypatch, "pi", "tmux")
    assert client.main(["register"]) == 0
    assert calls["post"][0]["flavor"] == "pi" and calls["post"][0]["model"] == "gpt-6.1-sol"


def test_register_takes_codex_model_from_its_config(monkeypatch, tmp_path):
    home = tmp_path / "codex"
    home.mkdir()
    (home / "config.toml").write_text('model = "gpt-6-sol"\n\n[profiles.x]\nmodel = "other"\n')
    monkeypatch.setenv("CODEX_HOME", str(home))
    calls = _register_under(monkeypatch, "/x/codex/bin/codex --yolo")
    assert client.main(["register"]) == 0
    assert calls["post"][0]["flavor"] == "codex" and calls["post"][0]["model"] == "gpt-6-sol"


def test_register_under_pi_inside_claude_is_pi(monkeypatch):
    # A pi started from a Claude Code pane: the nearest harness is the caller.
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "outer-claude")
    calls = _register_under(monkeypatch, "pi", "claude --model opus")
    assert client.main(["register", "--model", "x-1"]) == 0
    assert calls["post"][0]["flavor"] == "pi" and calls["post"][0]["model"] == "x-1"


def test_register_flag_beats_detection_and_claude_sends_no_guessed_model(monkeypatch):
    calls = _register_under(monkeypatch, "claude")
    assert client.main(["register"]) == 0
    assert calls["post"][0]["flavor"] == "claude" and "model" not in calls["post"][0]
    assert client.main(["register", "--flavor", "hermes"]) == 0
    assert calls["post"][1]["flavor"] == "hermes"


def test_send_passes_reply_reference(monkeypatch):
    monkeypatch.setattr(client, 'caller', lambda pane=None: {'pane':'%1'})
    monkeypatch.setattr(client, '_identify_or_explain', lambda who: True)
    monkeypatch.setattr(client, '_identity_payload', lambda who: {'tmux_pane':'%1'})
    calls = _fake_server(monkeypatch, {})
    assert client.main(['send','--to','owner','--message','answer','--reply-to','42']) == 0
    assert calls['post'][0]['reply_to'] == 42
    assert calls['post'][0]['content'] == 'answer'


def test_notify_sends_text_context_and_registered_identity(monkeypatch):
    monkeypatch.setattr(client, 'caller', lambda pane=None: {'pane': '%1'})
    monkeypatch.setattr(client, '_identify_or_explain', lambda who: True)
    monkeypatch.setattr(client, '_identity_payload', lambda who: {'tmux_pane': '%1'})
    calls = _fake_server(monkeypatch, {})
    assert client.main(['notify', 'Fake job done', '--context', 'fake-job']) == 0
    assert calls['post'][0] == {'tmux_pane': '%1', 'content': 'Fake job done', 'context': 'fake-job'}


def test_notify_reports_rate_limit_without_retrying(monkeypatch, capsys):
    monkeypatch.setattr(client, 'caller', lambda pane=None: {})
    monkeypatch.setattr(client, '_identify_or_explain', lambda who: True)
    monkeypatch.setattr(client, '_identity_payload', lambda who: {'agent_id': 'fake-session'})
    urls = []

    def reject(url, **kwargs):
        urls.append(url)
        return httpx.Response(429, json={'detail': 'notification limit reached; send a normal message instead'})

    monkeypatch.setattr(httpx, 'post', reject)
    assert client.main(['notify', 'Fake result']) == 1
    assert len(urls) == 1 and urls[0].endswith('/notify')
    assert 'send a normal message instead' in capsys.readouterr().out
