"""How an agent's registered flavor relates to the command its pane runs.

Used when a pane has to be judged by what is in it, e.g. matching a saved
pane to an agent while bundling a machine.
"""

from __future__ import annotations

import re

from . import tmux


def harness_matches(flavor: str | None, command: str) -> bool:
    """Does a pane's foreground command look like this agent's harness?"""
    if not command or command in tmux.SHELL_COMMANDS:
        return False
    flavor = (flavor or "generic").lower()
    if flavor == "claude":
        # Claude Code's process shows up as its version number, e.g. 2.1.280.
        return command in {"claude", "node"} or re.fullmatch(r"\d+(\.\d+)+", command) is not None
    if flavor == "codex":
        return command in {"codex", "node"} or command.startswith("codex")
    if flavor == "agy":
        return command == "agy"
    return True
