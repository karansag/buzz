"""Read an agent's current model off its screen, and switch it.

Each harness shows its model in its own way, and changes it in its own way:

- Claude Code: `/model` opens a numbered picker ("Select model"). Up/Down
  move the cursor and `s` applies the pick for this session only (Enter would
  also save it as the default for every new session).
- Codex: `/model` opens a numbered picker ("Select Model and Effort"). Enter
  picks the model, then a reasoning-level screen opens, where `s` applies it
  for this session only (Enter would save it to config.toml).
- Pi: `/model provider/id` switches directly, without saving a default.

A switch drives that UI through the node (paste, keys, screen captures), so it
works for agents on any machine, and checks every step on the screen before
the next key: it never presses a confirm key unless the cursor is on the
requested model. It ends by reading the model back off the screen.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import nodes

SWITCHABLE = ("claude", "codex", "pi")

# How long to wait for each screen change, and how often to look.
STEP_TIMEOUT = 8.0
POLL = 0.25
# Status lines and pickers live at the bottom of the screen.
FOOTER_LINES = 6

# --- reading the model off the screen -------------------------------------

_CLAUDE_FAMILIES = "Opus|Sonnet|Haiku|Fable"
# The banner ("Opus 5.5 · Claude Ultra") and a status line that shows the
# model in brackets ("[Opus 5.5 | wk:95%]").
_CLAUDE_BANNER = re.compile(rf"\b({_CLAUDE_FAMILIES}) (\d+(?:\.\d+)*) · Claude\b")
_CLAUDE_STATUS = re.compile(rf"\[({_CLAUDE_FAMILIES}) (\d+(?:\.\d+)*)\b")
_CODEX_EFFORTS = "minimal|low|medium|high|xhigh|extra high|max|ultra"
# Codex's status line starts with the model and its reasoning level:
# "GPT-6-Astra medium · ~/agent-swarm · Context 0% used ...".
_CODEX_STATUS = re.compile(rf"^\s*(\S.*?)\s+({_CODEX_EFFORTS})\s+·")
# Pi's footer ends with "(provider) id" and, for reasoning models, "• level".
_PI_FOOTER = re.compile(r"\(([\w.-]+)\)\s+(\S+)(?:\s+•\s+\S+)?\s*$")


def _claude_id(family: str, version: str) -> str:
    """"Opus", "5.5" -> "claude-opus-5-5", the API id `claude --model` takes."""
    return f"claude-{family.lower()}-{version.replace('.', '-')}"


_codex_names: tuple[tuple[str, float], dict[str, str]] | None = None


def _codex_display_names() -> dict[str, str]:
    """Codex picker label (lowercased) -> model slug, from Codex's model cache.

    The monitor reads every Codex screen each tick, so the parsed file is
    kept until it changes.
    """
    global _codex_names
    path = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "models_cache.json"
    try:
        key = (str(path), path.stat().st_mtime)
        if _codex_names is not None and _codex_names[0] == key:
            return _codex_names[1]
        models = json.loads(path.read_text())["models"]
        names = {
            m["display_name"].lower(): m["slug"]
            for m in models
            if isinstance(m.get("display_name"), str) and isinstance(m.get("slug"), str)
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    _codex_names = (key, names)
    return names


def _codex_slug(label: str) -> str:
    known = _codex_display_names()
    return known.get(label.lower()) or re.sub(r"\s+", "-", label.strip().lower())


def screen_model(flavor: str | None, screen: str | None) -> str | None:
    """The model the harness on this screen says it runs, or None if it doesn't say.

    Ids come back in the form each harness's --model takes: Claude's API id
    ("claude-sonnet-5-5"), Codex's slug ("gpt-6-astra"), Pi's "provider/id".
    Only the harness's own banner and status lines count, never conversation
    text, so an agent talking about models does not relabel itself.
    """
    if not screen:
        return None
    lines = [ln for ln in screen.splitlines() if ln.strip()]
    footer = lines[-FOOTER_LINES:]
    if flavor == "claude":
        for line in reversed(footer):
            if m := _CLAUDE_STATUS.search(line):
                return _claude_id(*m.groups())
        for line in reversed(lines):
            if m := _CLAUDE_BANNER.search(line):
                return _claude_id(*m.groups())
        return None
    if flavor == "codex":
        for line in reversed(footer):
            if m := _CODEX_STATUS.match(line):
                slug = _codex_slug(m.group(1))
                if slug.startswith("gpt") or slug in _codex_display_names().values():
                    return slug
        return None
    if flavor == "pi":
        for line in reversed(footer):
            if m := _PI_FOOTER.search(line):
                return f"{m.group(1)}/{m.group(2)}"
        return None
    return None


# What each harness prints when a switch takes effect.
_CONFIRMED = {
    "claude": re.compile(rf"Set model to ({_CLAUDE_FAMILIES}) (\d+(?:\.\d+)*)"),
    "codex": re.compile(r"Model changed to (\S+)"),
    "pi": re.compile(r"^\s*Model: (\S+)\s*$"),
}


def confirmed_model(flavor: str, screen: str) -> str | None:
    """The model named by the last switch confirmation on screen, if any.

    Pi's confirmation leaves out the provider ("Model: meta/x"), so its id
    is partial; same_model accounts for that.
    """
    pattern = _CONFIRMED.get(flavor)
    if pattern is None:
        return None
    found = None
    for line in screen.splitlines():
        if m := pattern.search(line):
            found = m
    if found is None:
        return None
    if flavor == "claude":
        return _claude_id(*found.groups())
    return found.group(1)


# --- matching a requested model ------------------------------------------

def same_model(flavor: str, wanted: str, seen: str | None) -> bool:
    """Whether the model read off the screen is the one asked for.

    A Claude alias ("sonnet") matches any model of that family.
    """
    if seen is None:
        return False
    wanted, seen = wanted.lower(), seen.lower()
    if flavor == "claude" and wanted == "default":
        return True
    if flavor == "claude" and "-" not in wanted:
        return seen.startswith(f"claude-{wanted}-")
    if flavor == "pi" and "/" in wanted and seen == wanted.split("/", 1)[1]:
        return True
    return seen == wanted


@dataclass
class Row:
    number: int
    label: str
    cursor: bool
    default: bool = False


# "❯ 4.  Sonnet 5.5 ✔           Most efficient ..." / "› 1. GPT-6.1-Sol (current)  Latest ..."
_ROW = re.compile(r"^\s*([›❯>])?\s*(\d+)\.\s+(\S.*?)(?:\s{2,}.*)?$")
_MARKS = re.compile(r"\s*(✔|\((?:current|default|recommended)\))")


def picker_rows(screen: str, title: str) -> list[Row] | None:
    """The numbered rows under the last `title` line, or None if no such picker shows."""
    lines = screen.splitlines()
    starts = [i for i, ln in enumerate(lines) if title.lower() in ln.lower()]
    if not starts:
        return None
    rows = []
    for line in lines[starts[-1] + 1:]:
        m = _ROW.match(line)
        if m:
            label = _MARKS.sub("", m.group(3)).strip()
            rows.append(Row(int(m.group(2)), label, bool(m.group(1)), "(default)" in m.group(3)))
        elif rows and line.strip():
            break
    return rows


def row_matches(flavor: str, wanted: str, label: str) -> bool:
    label = label.lower()
    wanted = wanted.lower()
    if flavor == "claude":
        if wanted == "default":
            return label == "default"
        if "-" in wanted:
            # An API id: "claude-sonnet-5-5" is the row "Sonnet 5.5".
            m = re.fullmatch(rf"claude-({_CLAUDE_FAMILIES.lower()})-(\d+(?:-\d+)*)", wanted)
            return bool(m) and label == f"{m.group(1)} {m.group(2).replace('-', '.')}"
        return label == wanted or label.startswith(f"{wanted} ")
    return _codex_slug(label) == wanted


# --- driving the switch ---------------------------------------------------

class SwitchFailed(Exception):
    """The switch stopped. `screen` is the last screen seen, for the report."""

    def __init__(self, message: str, screen: str | None = None):
        super().__init__(message)
        self.screen = screen


@dataclass
class Pane:
    """One agent's pane, reached through its node."""
    node: nodes.Node
    pane: str
    tmux_server: str | None
    submit_key: str
    flavor: str

    def screen(self) -> str:
        text, err = self.node.capture(self.pane, self.tmux_server)
        if err is not None or text is None:
            raise SwitchFailed(f"could not read the pane: {err}")
        return text

    def type(self, text: str, retry_submit: bool) -> None:
        r = self.node.deliver(
            nodes.new_op_id(), self.pane, self.tmux_server, text,
            submit_key=self.submit_key, flavor=self.flavor, retry_submit=retry_submit,
        )
        if r.status != "ok":
            raise SwitchFailed(f"could not type {text!r}: {r.error or r.status}")

    def key(self, key: str) -> None:
        r = self.node.send_key(nodes.new_op_id(), self.pane, self.tmux_server, key)
        if r.status != "ok":
            raise SwitchFailed(f"could not press {key}: {r.error or r.status}")


def wait_for(
    pane: Pane, check: Callable[[str], object], what: str,
    timeout: float | None = None, sleep: Callable[[float], None] = time.sleep,
):
    """Capture until `check(screen)` is truthy; return that value."""
    deadline = time.monotonic() + (STEP_TIMEOUT if timeout is None else timeout)
    screen = ""
    while True:
        screen = pane.screen()
        found = check(screen)
        if found:
            return found
        if time.monotonic() >= deadline:
            raise SwitchFailed(f"timed out waiting for {what}", screen)
        sleep(POLL)


PICKERS = {
    # flavor: (picker title, key that applies the pick for this session only)
    "claude": ("Select model", "s"),
    "codex": ("Select Model and Effort", "Enter"),
}
CODEX_EFFORT_TITLE = "Select Reasoning Level"


def _select(
    pane: Pane, title: str, choose: Callable[[list[Row]], Row | None], what: str,
    sleep: Callable[[float], None],
) -> None:
    """Move the cursor of the picker titled `title` onto the row `choose` picks.

    Closes the picker with Escape if there is no such row or the cursor
    does not get there.
    """
    def rows_with_cursor(screen: str) -> list[Row] | None:
        # A screen caught mid-redraw can show the rows without the cursor.
        rows = picker_rows(screen, title)
        return rows if rows and any(r.cursor for r in rows) else None

    rows = wait_for(pane, rows_with_cursor, f"the {title!r} picker", sleep=sleep)
    target = choose(rows)
    if target is None:
        pane.key("Escape")
        raise SwitchFailed(f"{what} is not in the picker (it lists: {', '.join(r.label for r in rows)})")
    for _ in range(len(rows) + 1):
        cursor = next(r for r in rows if r.cursor)
        if cursor.number == target.number:
            return
        pane.key("Down" if target.number > cursor.number else "Up")
        try:
            rows = wait_for(
                pane,
                lambda s: (r := rows_with_cursor(s)) and not any(
                    c.cursor and c.number == cursor.number for c in r) and r,
                "the picker's cursor to move", sleep=sleep,
            )
        except SwitchFailed:
            pane.key("Escape")
            raise
    pane.key("Escape")
    raise SwitchFailed(f"the cursor did not reach {target.label}")


def codex_effort(screen: str) -> str | None:
    """The reasoning level on Codex's status line ("medium"), if it shows one."""
    lines = [ln for ln in screen.splitlines() if ln.strip()]
    for line in reversed(lines[-FOOTER_LINES:]):
        if m := _CODEX_STATUS.match(line):
            return m.group(2)
    return None


def _effort_row(effort: str | None, rows: list[Row]) -> Row | None:
    """The row for the agent's current reasoning level, else the model's default."""
    if effort is not None:
        for row in rows:
            label = row.label.lower()
            if label == effort or (effort == "xhigh" and label == "extra high"):
                return row
    return next((r for r in rows if r.default), None)


def switch(pane: Pane, wanted: str, sleep: Callable[[float], None] = time.sleep) -> str:
    """Switch the agent in `pane` to `wanted`, for its current session only.

    Returns the model read back off the screen afterwards. Raises
    SwitchFailed if any step does not show up on the screen as expected; an
    open picker is closed again with Escape. Escape is never pressed when no
    picker is open, because in Claude Code and Codex it interrupts a turn.
    """
    if pane.flavor == "pi":
        # Pi's command autocomplete can take the first Enter; the retried
        # submit sends the command.
        pane.type(f"/model {wanted}", retry_submit=True)
    elif pane.flavor in PICKERS:
        title, apply_key = PICKERS[pane.flavor]
        effort = codex_effort(pane.screen()) if pane.flavor == "codex" else None
        # No retried Enter: the picker row under the cursor looks like unsent text.
        pane.type("/model", retry_submit=False)
        _select(
            pane, title,
            lambda rows: next((r for r in rows if row_matches(pane.flavor, wanted, r.label)), None),
            wanted, sleep,
        )
        pane.key(apply_key)
        if pane.flavor == "codex":
            # Enter took the model; the reasoning level comes next. Keep the
            # agent's level, or the model's default when that level is not
            # offered; `s` applies it for this session only.
            try:
                _select(pane, CODEX_EFFORT_TITLE, lambda rows: _effort_row(effort, rows),
                        "a reasoning level", sleep)
            except SwitchFailed:
                # Escape on the level screen goes back to the model list.
                if picker_rows(pane.screen(), title):
                    pane.key("Escape")
                raise
            pane.key("s")
    else:
        raise SwitchFailed(f"switching models is not supported for {pane.flavor}")

    def shows_wanted(screen: str) -> str | None:
        seen = screen_model(pane.flavor, screen)
        if same_model(pane.flavor, wanted, seen):
            return seen
        if same_model(pane.flavor, wanted, confirmed_model(pane.flavor, screen)):
            return seen if seen else wanted
        return None

    return wait_for(pane, shows_wanted, f"the screen to show {wanted}", sleep=sleep)
