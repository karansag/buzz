"""How full an agent's context window is, as its own harness shows it.

The harnesses print it in their footer, so the hub reads it from the same
screen capture it already takes every tick. That works for agents on any
machine, with no transcript access. Only the last few lines count, so an agent
talking about "ctx:90%" in the conversation cannot set its own number.

  Claude Code  a status line that prints "ctx:5%" (not in Claude's default
               status line; the owner's has it). Without one, no figure.
  Codex        "Context 55% used" (older builds: "41% context left")
  Pi           "13.1%/1.0M (auto)": percent, then the model's window
  agy          prints no context figure in its footer

`parse` returns {"percent": used, "window": "1.0M" or None}, or None when the
screen shows no figure (percent is None when the harness shows "?/131k").
"""

from __future__ import annotations

import re

FOOTER_LINES = 6

_CLAUDE = re.compile(r"\bctx:\s*(\d+(?:\.\d+)?)%")
_CODEX_USED = re.compile(r"\bContext (\d+(?:\.\d+)?)% used\b")
_CODEX_LEFT = re.compile(r"\b(\d+(?:\.\d+)?)% context left\b")
_PI = re.compile(r"(?<![\w.])(\?|\d+(?:\.\d+)?%)/(\d+(?:\.\d+)?[kKmM])\b")


def parse(flavor: str | None, screen: str | None) -> dict | None:
    if not screen:
        return None
    footer = [ln for ln in screen.splitlines() if ln.strip()][-FOOTER_LINES:]
    for line in reversed(footer):
        if flavor == "claude" and (m := _CLAUDE.search(line)):
            return _figure(float(m[1]))
        if flavor == "codex":
            if m := _CODEX_USED.search(line):
                return _figure(float(m[1]))
            if m := _CODEX_LEFT.search(line):
                return _figure(100 - float(m[1]))
        if flavor == "pi" and (m := _PI.search(line)):
            return _figure(None if m[1] == "?" else float(m[1].rstrip("%")), m[2].upper())
    return None


def _figure(percent: float | None, window: str | None = None) -> dict | None:
    if percent is not None and not 0 <= percent <= 100:
        return None
    return {"percent": percent, "window": window}
