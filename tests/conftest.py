"""Fixtures every test gets: no real settings or hub, and spawn commands
that don't depend on which harness versions this machine has installed."""

import json
import os
from pathlib import Path

import pytest

from agent_swarm import tmux


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_SWARM_CONFIG", str(tmp_path / "no-such-node.toml"))
    for flavor in tmux.SPAWNABLE_FLAVORS:
        monkeypatch.delenv(f"AGENT_SWARM_{flavor.upper()}_COMMAND", raising=False)
    # The harness session ids too: tests run inside Claude Code or Codex.
    for var in ("AGENT_SWARM_URL", "AGENT_MSG_URL", "AGENT_SWARM_TOKEN", "AGENT_SWARM_NODE",
                "AGENT_SWARM_TABS",
                "CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CODEX_SESSION_ID",
                "CLAUDE_MODEL", "ANTHROPIC_MODEL", "CODEX_MODEL", "PI_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "no-codex-home"))
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
