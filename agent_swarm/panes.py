"""One-time move of registrations from positional addresses to tmux pane ids.

Rows stored before pane ids hold `session:window.pane` (or, from some
clients, a bare %N with no record of which tmux server issued it). Neither
is trustworthy on its own: positions get reused and renumbered, so the pane
at a stored address today may hold a different agent. A row is bound to a
pane id only when the pane agrees with it; everything else is left offline
until the agent registers again (it can reclaim its handle with --name).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import tmux


@dataclass(frozen=True)
class Decision:
    user_id: str
    pane_id: str | None  # None: leave offline until it re-registers
    label: str | None
    reason: str
    gone: bool = False  # no pane is left at the stored address at all


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


def plan(
    rows: list[dict], table: dict[str, dict[str, str]], server_start: float | None
) -> list[Decision]:
    """Decide, for each legacy row, which pane id (if any) it really owns."""
    candidates = []
    for row in rows:
        stored = row["tmux_pane"]
        if stored.startswith("%"):
            # A bare id is only this server's if it was registered after the
            # server started; an older one may name a different pane now.
            fresh = server_start is not None and row["registered_at"] >= server_start
            pane_id = stored if fresh and stored in table else None
            why_missing = "pane id is from an earlier tmux session" if not fresh else "pane is gone"
        else:
            pane_id = next((pid for pid, p in table.items() if p["label"] == stored), None)
            why_missing = "pane is gone"
        if pane_id is None:
            candidates.append((row, None, None, why_missing, 0))
            continue
        pane = table[pane_id]
        titled = pane["title"] == tmux.status_title(row["user_id"], row.get("flavor"))
        if titled:
            candidates.append((row, pane_id, pane, "pane title names this agent", 2))
        elif harness_matches(row.get("flavor"), pane["command"]):
            candidates.append((row, pane_id, pane, f"pane runs {pane['command']}, matching {row.get('flavor')}", 1))
        elif pane["command"] in tmux.SHELL_COMMANDS:
            candidates.append((row, None, None, "pane is a bare shell now; can't tell whose it was", 0))
        else:
            candidates.append((row, None, None, f"pane now runs {pane['command']}, not {row.get('flavor')}", 0))

    # Two rows may claim one pane; the stronger evidence, then the later
    # registration, wins.
    best: dict[str, tuple] = {}
    for c in candidates:
        row, pane_id, _, _, score = c
        if pane_id is None:
            continue
        cur = best.get(pane_id)
        if cur is None or (score, row["registered_at"]) > (cur[4], cur[0]["registered_at"]):
            best[pane_id] = c

    decisions = []
    for row, pane_id, pane, reason, _ in candidates:
        if pane_id is not None and best[pane_id][0] is not row:
            decisions.append(Decision(row["user_id"], None, None, f"{best[pane_id][0]['user_id']} holds that pane"))
        elif pane_id is not None:
            decisions.append(Decision(row["user_id"], pane_id, pane["label"], reason))
        else:
            decisions.append(Decision(row["user_id"], None, None, reason, gone=reason == "pane is gone"))
    return decisions
