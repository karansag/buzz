"""Pure tests for the harness spawn command builder."""

from agent_swarm import tmux


CODEX_STARTUP = "codex -c check_for_update_on_startup=false"


def test_each_harness_has_one_launch_and_no_permission_choice():
    # claude runs in auto mode, codex gets --yolo (its sandbox would block
    # the tmux socket and the agent-swarm API), and the default model passes
    # no model flag at all.
    assert tmux.spawn_launch_command("claude") == "claude --permission-mode auto"
    assert tmux.spawn_launch_command("codex") == f"{CODEX_STARTUP} --yolo"
    assert tmux.spawn_launch_command("pi") == "pi"
    assert tmux.spawn_launch_command("hermes") == "hermes --yolo --accept-hooks"


def test_known_model_appends_harness_flag(codex_catalog):
    assert (
        tmux.spawn_launch_command("claude", "opus")
        == "claude --model opus --permission-mode auto"
    )
    assert (
        tmux.spawn_launch_command("codex", "gpt-6-astra")
        == f"{CODEX_STARTUP} --model gpt-6-astra --yolo"
    )
    # hermes uses -m rather than --model.
    tmux.HARNESS_SPAWN["hermes"].models.append("_probe")
    try:
        assert (
            tmux.spawn_launch_command("hermes", "_probe")
            == "hermes -m _probe --yolo --accept-hooks"
        )
    finally:
        tmux.HARNESS_SPAWN["hermes"].models.remove("_probe")


def test_pi_pattern_is_shell_quoted():
    # Leading ~ must be quoted so the shell does not tilde-expand it.
    cmd = tmux.spawn_launch_command("pi", "~anthropic/claude-opus-latest")
    assert cmd == "pi --model '~anthropic/claude-opus-latest'"


def test_unknown_model_falls_back_to_bare_binary():
    assert tmux.spawn_launch_command("claude", "not-a-real-model") == "claude --permission-mode auto"
    assert tmux.spawn_launch_command("claude", "") == "claude --permission-mode auto"


def test_unspawnable_flavor_returns_none():
    assert tmux.spawn_launch_command("generic") is None
    assert tmux.spawn_launch_command("nonsense") is None


def test_spawn_options_shape(codex_catalog):
    opts = {o["flavor"]: o["models"] for o in tmux.spawn_options()}
    assert set(opts) == {"claude", "codex", "pi", "hermes"}
    assert opts["claude"] == ["opus", "sonnet", "haiku", "fable"]
    # Codex's own picker list, in its priority order, hidden models left out.
    assert opts["codex"] == codex_catalog


def test_codex_models_without_a_cache_offer_only_the_default():
    assert tmux.codex_models() == []
    assert tmux.spawn_launch_command("codex", "gpt-6-astra") == f"{CODEX_STARTUP} --yolo"


def test_codex_models_survive_a_malformed_cache(codex_catalog, tmp_path):
    import os
    from pathlib import Path

    cache = Path(os.environ["CODEX_HOME"]) / "models_cache.json"
    for text in ("not json", "[]", '{"models": 3}', '{"models": [1]}'):
        cache.write_text(text)
        assert tmux.codex_models() == []


def test_local_node_prefers_the_node_override(monkeypatch):
    monkeypatch.setenv("AGENT_SWARM_NODE", "hub")
    assert tmux.local_node() == "hub"
    monkeypatch.delenv("AGENT_SWARM_NODE")
    monkeypatch.setattr(tmux.socket, "gethostname", lambda: "workstation.local")
    assert tmux.local_node() == "workstation"


def test_codex_spawn_skips_the_shared_daemon_when_codex_supports_it(monkeypatch):
    monkeypatch.setattr(tmux, "harness_accepts", lambda binary, flag: (binary, flag) == ("codex", "--no-daemon"))
    assert tmux.spawn_launch_command("codex").endswith(" --no-daemon")
    assert "--no-daemon" not in tmux.spawn_launch_command("claude")


def test_codex_spawn_leaves_out_flags_an_older_codex_rejects():
    # The autouse fixture reports every optional flag as unsupported.
    assert "--no-daemon" not in tmux.spawn_launch_command("codex")


def test_harness_accepts_probes_the_binary(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output, text, timeout):
        calls.append(cmd)
        return type("R", (), {"returncode": 0 if "--new" in cmd[2] else 2})()

    monkeypatch.undo()  # drop the autouse stub; test the real probe
    monkeypatch.setenv("SHELL", "/bin/zsh")
    monkeypatch.setattr(tmux.subprocess, "run", fake_run)
    tmux.harness_accepts.cache_clear()
    assert tmux.harness_accepts("fakeharness", "--new") is True
    assert tmux.harness_accepts("fakeharness", "--old") is False
    assert tmux.harness_accepts("fakeharness", "--new") is True  # cached
    # Through the login shell, so the binary is found on the user's PATH even
    # when the server itself runs with launchd's bare one.
    assert calls == [
        ["/bin/zsh", "-lc", "fakeharness --new --help"],
        ["/bin/zsh", "-lc", "fakeharness --old --help"],
    ]
    tmux.harness_accepts.cache_clear()


def _run_sequence(monkeypatch, outcomes):
    """Fake subprocess.run for tmux.deliver: one outcome per tmux call, in order."""
    import subprocess

    calls = []
    outcomes = iter(outcomes)

    def run(cmd, **kw):
        calls.append(cmd[1])
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(tmux.subprocess, "run", run)
    monkeypatch.setattr(tmux.time, "sleep", lambda s: None)
    monkeypatch.setattr(tmux, "_await_submit", lambda pane, timeout: True)
    return calls


def test_deliver_is_failed_only_while_nothing_reached_the_pane(monkeypatch):
    import subprocess

    calls = _run_sequence(monkeypatch, [subprocess.CalledProcessError(1, "tmux", stderr="no server")])
    assert tmux.deliver("%1", "hi") == (False, "no server")
    assert calls == ["load-buffer"]
    calls = _run_sequence(monkeypatch, [None, subprocess.CalledProcessError(1, "tmux", stderr="can't find pane")])
    assert tmux.deliver("%1", "hi") == (False, "can't find pane")
    assert calls == ["load-buffer", "paste-buffer"]


def test_deliver_is_uncertain_once_the_paste_may_have_landed(monkeypatch):
    import subprocess

    import pytest

    _run_sequence(monkeypatch, [None, subprocess.TimeoutExpired("tmux", 5)])
    with pytest.raises(tmux.Uncertain, match="paste did not report back"):
        tmux.deliver("%1", "hi")
    _run_sequence(monkeypatch, [None, None, subprocess.TimeoutExpired("tmux", 5)])
    with pytest.raises(tmux.Uncertain, match="submit key failed"):
        tmux.deliver("%1", "hi")
    calls = _run_sequence(monkeypatch, [None, None, None])
    assert tmux.deliver("%1", "hi") == (True, None)
    assert calls == ["load-buffer", "paste-buffer", "send-keys"]


def test_spawn_window_is_uncertain_when_tmux_does_not_report_back(monkeypatch):
    import subprocess

    import pytest

    outcomes = iter([
        subprocess.CompletedProcess([], 0, "", ""),  # has-session
        subprocess.CompletedProcess([], 0, "%7\tagents:3.0\t4242:1700000000\n", ""),  # new-window
        subprocess.TimeoutExpired("tmux", 5),  # send-keys
    ])
    monkeypatch.setattr(tmux.subprocess, "run", lambda cmd, **kw: _raise_or(next(outcomes)))
    with pytest.raises(tmux.Uncertain) as info:
        tmux.spawn_window(command="claude")
    # The window's identity comes from the creating command itself.
    assert info.value.created == tmux.Created("%7", "agents:3.0", "4242:1700000000")
    outcomes = iter([
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CalledProcessError(1, "tmux", stderr="no space"),
    ])
    assert tmux.spawn_window(command="claude") == (None, "no space")


def _raise_or(outcome):
    if isinstance(outcome, Exception):
        raise outcome
    return outcome


def test_spawn_window_reports_the_pane_with_the_server_that_made_it(monkeypatch):
    import subprocess

    outcomes = iter([
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 0, "%8\tagents:4.0\t4242:1700000000\n", ""),
        subprocess.CompletedProcess([], 0, "", ""),
    ])
    monkeypatch.setattr(tmux.subprocess, "run", lambda cmd, **kw: _raise_or(next(outcomes)))
    assert tmux.spawn_window(command="claude") == (tmux.Created("%8", "agents:4.0", "4242:1700000000"), None)
    outcomes = iter([
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 0, "garbage\n", ""),
    ])
    assert tmux.spawn_window(command="claude") == (None, "tmux did not report the new pane")


def test_login_shell_falls_back_to_the_account_shell(monkeypatch):
    monkeypatch.delenv("SHELL", raising=False)  # launchd gives none
    assert tmux.login_shell().startswith("/")


def test_spawn_window_starts_in_the_home_directory(monkeypatch):
    # A node under launchd runs in /, and tmux would start the window there.
    import subprocess
    from pathlib import Path

    calls = []
    outcomes = iter([
        subprocess.CompletedProcess([], 1, "", ""),  # has-session: no session yet
        subprocess.CompletedProcess([], 0, "%9\tagents:0.0\t4242:1700000000\n", ""),
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 0, "%10\tagents:1.0\t4242:1700000000\n", ""),
    ])
    def run(cmd, **kw):
        calls.append(cmd)
        return next(outcomes)
    monkeypatch.setattr(tmux.subprocess, "run", run)
    home = str(Path.home())
    tmux.spawn_window()
    tmux.spawn_window()
    created = [c for c in calls if c[1] in ("new-session", "new-window")]
    assert [c[1] for c in created] == ["new-session", "new-window"]
    assert all(c[c.index("-c") + 1] == home for c in created)
