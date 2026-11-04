"""Custom launch commands survive config updates and all launch paths."""

import shlex
import subprocess
import tomllib

import pytest

from agent_swarm import config, restore, tmux


def write_commands(text):
    config.config_path().write_text(text)


@pytest.mark.parametrize("flavor", tmux.SPAWNABLE_FLAVORS)
def test_env_overrides_file_and_defaults_for_every_harness(monkeypatch, flavor):
    write_commands(f'[harness_commands]\n{flavor} = "/file/wrapper --flag"\n')
    assert tmux.spawn_launch_command(flavor) == "/file/wrapper --flag"
    monkeypatch.setenv(f"AGENT_SWARM_{flavor.upper()}_COMMAND", " /env/wrapper --other ")
    assert tmux.spawn_launch_command(flavor) == "/env/wrapper --other"
    monkeypatch.setenv(f"AGENT_SWARM_{flavor.upper()}_COMMAND", "  ")
    assert tmux.spawn_launch_command(flavor) == "/file/wrapper --flag"
    write_commands(f'[harness_commands]\n{flavor} = "/edited/wrapper"\n')
    assert tmux.spawn_launch_command(flavor) == "/edited/wrapper"


@pytest.mark.parametrize("text", [
    '', '[harness_commands]\nclaude = "  "', '[harness_commands]\nclaude = 123',
    'harness_commands = "wrong type"', 'invalid toml [',
])
def test_missing_blank_or_invalid_file_values_use_defaults(text):
    write_commands(text)
    assert tmux.spawn_launch_command("claude") == "claude --permission-mode auto"


def test_config_rewrites_keep_commands_without_persisting_env_overrides(monkeypatch):
    write_commands('[harness_commands]\nclaude = "/path with spaces/wrapper"\ncodex = "my-codex"\n')
    monkeypatch.setenv("AGENT_SWARM_CLAUDE_COMMAND", "/environment/wrapper")
    config.load()  # remembers the hostname in a file with no node yet
    expected = {"claude": "/path with spaces/wrapper", "codex": "my-codex"}
    assert tomllib.loads(config.config_path().read_text())["harness_commands"] == expected
    config.write("http://hub:8765", "token", "laptop")  # buzz join
    saved = tomllib.loads(config.config_path().read_text())
    assert saved["harness_commands"] == expected
    assert saved["token"] == "token"
    assert config.config_path().stat().st_mode & 0o777 == 0o600


def test_custom_command_keeps_shell_syntax_and_model_is_quoted(monkeypatch):
    monkeypatch.setenv("AGENT_SWARM_PI_COMMAND", 'env ACCOUNT="personal account" "/path with spaces/pi"')
    command = tmux.spawn_launch_command("pi", "~anthropic/claude-opus-latest")
    assert shlex.split(command) == [
        "env", "ACCOUNT=personal account", "/path with spaces/pi",
        "--model", "~anthropic/claude-opus-latest",
    ]
    assert tmux.spawn_launch_command("pi", "bogus; touch /tmp/unwanted") == (
        'env ACCOUNT="personal account" "/path with spaces/pi"')


@pytest.mark.parametrize("flavor, flag", [("claude", "--model"), ("codex", "--model"),
                                           ("pi", "--model"), ("hermes", "-m")])
def test_custom_command_only_appends_model_and_never_probes(monkeypatch, flavor, flag):
    monkeypatch.setenv(f"AGENT_SWARM_{flavor.upper()}_COMMAND", "/custom/wrapper --own-flag")
    monkeypatch.setattr(tmux.HARNESS_SPAWN[flavor], "_models", ["test-model"])
    def unexpected_probe(*args):
        pytest.fail("custom commands must not be probed or get optional flags")
    monkeypatch.setattr(tmux, "harness_accepts", unexpected_probe)
    assert tmux.spawn_launch_command(flavor, "test-model") == f"/custom/wrapper --own-flag {flag} test-model"


@pytest.mark.parametrize("flavor, args", [
    ("claude", ["--resume", "session; id", "--model", "model; name"]),
    ("codex", ["resume", "session; id", "--model", "model; name"]),
    ("pi", ["--session", "session; id"]),
    ("hermes", ["--resume", "session; id", "-m", "model; name"]),
])
def test_restore_and_restart_use_custom_command(monkeypatch, flavor, args):
    # restart also builds its launch through restore.resume_command.
    monkeypatch.setenv(f"AGENT_SWARM_{flavor.upper()}_COMMAND", '"/custom wrapper" --own-flag')
    command = restore.resume_command({"flavor": flavor, "agent_id": "session; id", "model": "model; name"})
    assert shlex.split(command) == ["/custom wrapper", "--own-flag", *args]


def test_absolute_command_bypasses_shell_account_picker(monkeypatch, tmp_path):
    wrapper = tmp_path / "fake claude"
    wrapper.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    wrapper.chmod(0o700)
    monkeypatch.setenv("AGENT_SWARM_CLAUDE_COMMAND", f"{shlex.quote(str(wrapper))} --custom")
    command = tmux.spawn_launch_command("claude", "opus")
    result = subprocess.run(
        ["/bin/sh", "-c", 'claude() { echo "ACCOUNT PICKER"; }; ' + command],
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.splitlines() == ["--custom", "--model", "opus"]
