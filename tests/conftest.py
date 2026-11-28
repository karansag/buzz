"""Shared fixtures. Every test gets isolated settings and no real hub;
`client` and `hub` give a test app with a faked tmux."""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_swarm import server, tmux


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_SWARM_CONFIG", str(tmp_path / "no-such-node.toml"))
    for flavor in tmux.SPAWNABLE_FLAVORS:
        monkeypatch.delenv(f"AGENT_SWARM_{flavor.upper()}_COMMAND", raising=False)
    # The harness session ids too: tests run inside Claude Code or Codex.
    for var in ("AGENT_SWARM_URL", "AGENT_MSG_URL", "AGENT_SWARM_TOKEN", "AGENT_SWARM_NODE",
                "AGENT_SWARM_TABS",
                "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CODEX_SESSION_ID", "PI_SESSION_ID",
                "ANTIGRAVITY_CONVERSATION_ID",
                "CLAUDE_MODEL", "ANTHROPIC_MODEL", "CODEX_MODEL", "PI_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ANTIGRAVITY_APP_DATA_DIR", str(tmp_path / "no-agy-home"))
    # `agy models` asks Google's servers; tests get no catalog unless they fake one.
    monkeypatch.setattr(tmux, "_agy_models_output", lambda: "")
    monkeypatch.setattr(tmux, "_agy_models", None)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "no-codex-home"))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / "no-pi-home"))
    # And the process tree: `register` reads its harness from the ancestry.
    monkeypatch.setattr(tmux, "ancestors", lambda pid=None: [])


@pytest.fixture(autouse=True)
def _no_optional_harness_flags(monkeypatch):
    """Tests that care about optional harness flags opt in by patching harness_accepts."""
    monkeypatch.setattr(tmux, "harness_accepts", lambda binary, flag: False)


@pytest.fixture
def codex_catalog():
    """A Codex model cache in the test's CODEX_HOME, as Codex writes it."""
    home = Path(os.environ["CODEX_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    models = [
        {"slug": "gpt-5.6-luna", "visibility": "list", "priority": 9},
        {"slug": "gpt-6.1-sol", "visibility": "list", "priority": 1},
        {"slug": "gpt-reserve", "visibility": "hide", "priority": 4},
        {"slug": "gpt-6-astra", "visibility": "list", "priority": 2},
    ]
    (home / "models_cache.json").write_text(json.dumps({"models": models}))
    return ["gpt-6.1-sol", "gpt-6-astra", "gpt-5.6-luna"]


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
        tmux, "capture_pane", lambda pane, colors=False: (f"screen of {pane}\n$ ", None)
    )

    spawns = []
    spawn_cwds = []

    def fake_spawn_window(session=tmux.AGENTS_SESSION, command=None, cwd=None):
        spawns.append((session, command))
        spawn_cwds.append(cwd)
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
    c._spawn_cwds = spawn_cwds
    c._kills = kills
    c._window_names = window_names
    c._pane_tags = pane_tags
    return c


@pytest.fixture()
def hub(tmp_path, monkeypatch):
    monkeypatch.setattr(tmux, "server_id", lambda: "srv-1")
    monkeypatch.setattr(tmux, "resolve_pane", lambda t: (t, t))
    monkeypatch.setattr(
        tmux, "pane_table",
        lambda: {"%1": {"label": "a:0.0", "command": "claude", "title": ""}},
    )
    monkeypatch.setattr(tmux, "deliver", lambda *a, **k: (True, None))
    monkeypatch.setattr(tmux, "tag_pane", lambda *a: (True, None))
    return server.create_app(tmp_path / "db.sqlite", monitor=False)
