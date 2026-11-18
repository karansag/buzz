"""Read an agent's current model off its screen, and switch it.

Each harness shows its model in its own way, and changes it in its own way:

- Claude Code: `/model` opens a numbered picker ("Select model"). Up/Down
  move the cursor and `s` applies the pick for this session only (Enter would
  also save it as the default for every new session). In a short pane the
  list scrolls: it shows a few rows around the cursor, marks a row with
  hidden rows above it "↑ 3.", and folds the rest below into "… +4 models".
  A long label can wrap onto a second line. The last row, "▸ More models",
  has no number and opens a submenu; the switch never picks it. Once the
  conversation holds tokens, applying a pick asks for confirmation first
  ("Switch model? ... the full history gets re-read"), because the new model
  re-reads everything and the prompt cache is lost; `s` there opens that
  dialog rather than switching. Installing the PreModelSwitch hook that
  hooks/install writes stops it ever appearing; when it does appear anyway
  (another machine's Claude Code), the switch accepts it, but only when the
  dialog names the model that was asked for.
- Codex: `/model` opens a numbered picker ("Select Model and Effort"). Enter
  picks the model, then a reasoning-level screen opens, where `s` applies it
  for this session only (Enter would save it to config.toml).
- Pi: `/model` opens a filtered picker. It first lists only the owner's
  saved models ("scoped"); Tab shows Pi's whole catalog ("all"). Typing the
  full "provider/id" narrows the list, Enter picks the row under the cursor
  for this session only (Ctrl+S would save it as the default). `/model
  provider/id` is not used: Pi's autocomplete can swap a near match from the
  saved list in for the typed id.

- Antigravity (agy): its /model picker saves the pick as the default for
  every new agy session, and nothing applies it to one session only. So a
  switch restarts the agent instead, only while the screen shows it idle:
  `/quit`, then `agy --conversation ID --model M` in the same pane. That
  resumes the same conversation; a launch --model is not saved. The footer
  shows the model ("Gemini 4 Argon · medium"), the id is agy's own
  ("gemini-4-argon-medium").

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

from . import nodes, restore, tmux

SWITCHABLE = ("claude", "codex", "pi", "agy")

# How long to wait for each screen change, and how often to look.
STEP_TIMEOUT = 8.0
POLL = 0.25
# Status lines and pickers live at the bottom of the screen.
FOOTER_LINES = 6
# Most cursor moves a scrolled picker gets to bring a hidden row into view.
MAX_SCROLL = 30

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
# Pi's footer: context use ("7.1%/131k"), "(auto)" compaction, then
# "(provider) id" and, for reasoning models, "• level". A narrow pane drops
# the provider and cuts the end of a long id.
# agy's footer: its key hint, then the model and effort on the right:
# "? for shortcuts        Gemini 4 Neon · high" (busy: "esc to cancel").
_AGY_FOOTER = re.compile(r"^\s*(\? for shortcuts|esc to cancel)\s{2,}(\S.*?) · (\w+)\s*$")
AGY_IDLE = "? for shortcuts"
_PI_FOOTER = re.compile(
    r"\d+(?:\.\d+)?%/\S+(?:\s+\(auto\))?\s+(?:\(([\w.-]+)\)\s+)?(\S+)(?:\s+•\s+\S+)?\s*$"
)


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


def _agy_id(name: str, effort: str) -> str:
    """"Gemini 4 Argon", "medium" -> "gemini-4-argon-medium", agy's model id.

    agy's catalog maps its labels ("Gemini 4 Argon (Medium)") to ids; without
    it, the label is turned into an id the same way agy names most models.
    """
    label = f"{name} ({effort})".lower()
    for model, shown in tmux.agy_catalog():
        if shown.lower() == label:
            return model
    return re.sub(r"\s+", "-", f"{name} {effort}".strip().lower())


def agy_footer(screen: str) -> tuple[bool, str] | None:
    """(idle, model id) from agy's footer, or None if it is not on screen."""
    lines = [ln for ln in screen.splitlines() if ln.strip()]
    for line in reversed(lines[-FOOTER_LINES:]):
        if m := _AGY_FOOTER.match(line):
            return m.group(1) == AGY_IDLE, _agy_id(m.group(2), m.group(3))
    return None


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
                provider, model = m.groups()
                return f"{provider}/{model}" if provider else _pi_full_id(model)
        return None
    if flavor == "agy":
        found = agy_footer(screen)
        return found[1] if found else None
    return None


def _pi_full_id(shown: str) -> str | None:
    """The shortlisted "provider/id" for an id Pi showed without its provider.

    A cut-off id matches by prefix. None unless exactly one entry fits.
    """
    entries = [m for m in tmux.pi_models() if "/" in m]
    for fits in (lambda id_: id_ == shown, lambda id_: id_.startswith(shown)):
        found = [m for m in entries if fits(m.split("/", 1)[1])]
        if len(found) == 1:
            return found[0]
        if found:
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


# Claude Code's confirmation before a switch in a conversation that already
# holds tokens, shown instead of switching:
#   Switch model?
#   Your next response will be slower and use more tokens
#   This conversation is cached for the current model. Switching to Sonnet 5.5
#   means the full history gets re-read.
#   ❯ 1. Yes, switch to Sonnet 5.5
#     2. No, go back
CACHE_CONFIRM_TITLE = "Switch model?"
_CACHE_CONFIRM_YES = re.compile(r"^\s*(?:[\u276f\u203a>]\s*)?\d*\.?\s*Yes, switch to (.+?)\s*$")
# "This conversation is cached for the current model. Switching to Sonnet 5.5
# means the full history gets re-read." wraps, so the sentence and the label
# can end the line.
_CACHE_CONFIRM_BODY = re.compile(
    r"Switching to (.+?)(?:\s+means the full history gets re-read)?\s*$")


def cache_confirm_model(screen: str) -> str | None:
    """The model Claude Code's switch confirmation would switch to, if it shows.

    Reads the label from its "Yes, switch to ..." row, or from the sentence
    above when a narrow pane wraps that row.
    """
    lines = screen.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == CACHE_CONFIRM_TITLE), None)
    if start is None:
        return None
    for line in lines[start + 1:]:
        if m := _CACHE_CONFIRM_YES.match(line):
            return _MARKS.sub("", m.group(1)).strip()
        if m := _CACHE_CONFIRM_BODY.search(line):
            return _MARKS.sub("", m.group(1)).strip()
    return None


def confirm_names(flavor: str, wanted: str, label: str) -> bool:
    """Whether a confirmation that names `label` is confirming the model asked for.

    "Default" is no model name, so any Claude model label stands for it: the
    dialog names what the default resolves to today.
    """
    if row_matches(flavor, wanted, label):
        return True
    return (flavor == "claude" and wanted.lower() == "default"
            and re.fullmatch(rf"(?:{_CLAUDE_FAMILIES}) \d+(?:\.\d+)*", label) is not None)


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
    if flavor == "agy" and re.fullmatch(r"[a-z]+", wanted):
        # A family alias ("argon") matches any effort of that family.
        return f"-{wanted}-" in f"-{seen}-"
    return seen == wanted


@dataclass
class Row:
    number: int
    label: str
    cursor: bool
    default: bool = False
    more: bool = False  # Claude's "▸ More models" submenu row, never a model


# "❯ 4.  Sonnet 5.5 ✔           Most efficient ..." / "› 1. GPT-6.1-Sol (current)  Latest ..."
# A scrolled Claude picker puts "↑" or "↓" where the cursor would be.
_ROW = re.compile(r"^\s*(?:([›❯>])|[↑↓])?\s*(\d+)\.\s+(\S.*?)(?:\s{2,}.*)?$")
_MORE_ROW = re.compile(r"^\s*([›❯>])?\s*▸\s+(\S.*?)\s*$")
# "… +4 models": rows below the visible part of a scrolled picker.
_FOLDED = re.compile(r"^\s*…\s*\+\d+ models?\s*$")
_MARKS = re.compile(r"\s*(✔|\((?:current|default|recommended)\))")


def _picker_lines(screen: str, title: str) -> list[str] | None:
    lines = screen.splitlines()
    starts = [i for i, ln in enumerate(lines) if title.lower() in ln.lower()]
    return lines[starts[-1] + 1:] if starts else None


def picker_rows(screen: str, title: str) -> list[Row] | None:
    """The rows under the last `title` line, or None if no such picker shows.

    Only the rows on screen; `rows_folded_below` says whether more follow.
    """
    lines = _picker_lines(screen, title)
    if lines is None:
        return None
    rows: list[Row] = []
    label_column = None
    for line in lines:
        m = _ROW.match(line)
        if m:
            label = _MARKS.sub("", m.group(3)).strip()
            rows.append(Row(int(m.group(2)), label, bool(m.group(1)), "(default)" in m.group(3)))
            label_column = m.start(3)
        elif rows and (more := _MORE_ROW.match(line)):
            rows.append(Row(rows[-1].number + 1, more.group(2), bool(more.group(1)), more=True))
            label_column = None
        elif label_column is not None and len(line) - len(line.lstrip()) > label_column:
            continue  # the second line of a wrapped label or description
        elif rows and line.strip():
            break
    return rows


def rows_folded_below(screen: str, title: str) -> bool:
    """Whether the picker folds rows below the visible ones ("… +4 models")."""
    lines = _picker_lines(screen, title) or []
    return any(_FOLDED.match(line) for line in lines)


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
    # The harness's session id. agy's switch resumes it under the new model.
    session: str | None = None

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

    def text(self, text: str) -> None:
        """Type `text` without submitting it."""
        r = self.node.send_key(nodes.new_op_id(), self.pane, self.tmux_server, text, literal=True)
        if r.status != "ok":
            raise SwitchFailed(f"could not type {text!r}: {r.error or r.status}")


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

    def move(key: str, rows: list[Row]) -> tuple[list[Row], str]:
        cursor = next(r for r in rows if r.cursor)
        pane.key(key)
        try:
            return wait_for(
                pane,
                lambda s: (r := rows_with_cursor(s)) and not any(
                    c.cursor and c.number == cursor.number for c in r) and (r, s),
                "the picker's cursor to move", sleep=sleep,
            )
        except SwitchFailed:
            pane.key("Escape")
            raise

    def choose_model(rows: list[Row]) -> Row | None:
        return choose([r for r in rows if not r.more])

    rows, screen = wait_for(pane, lambda s: (r := rows_with_cursor(s)) and (r, s),
                            f"the {title!r} picker", sleep=sleep)
    seen = {r.number: r.label for r in rows if not r.more}
    target = choose_model(rows)
    # A scrolled picker shows only some rows. Walk down while rows are
    # folded below, then up while the top rows are hidden, until the wanted
    # row comes into view.
    for key, hidden in (
        ("Down", lambda rows, screen: rows_folded_below(screen, title)),
        ("Up", lambda rows, screen: min(r.number for r in rows) > 1),
    ):
        for _ in range(MAX_SCROLL):
            if target is not None or not hidden(rows, screen):
                break
            rows, screen = move(key, rows)
            seen.update((r.number, r.label) for r in rows if not r.more)
            target = choose_model(rows)
    if target is None:
        pane.key("Escape")
        listed = ", ".join(seen[n] for n in sorted(seen))
        raise SwitchFailed(f"{what} is not in the picker (it lists: {listed})")
    for _ in range(len(seen) + 1):
        cursor = next(r for r in rows if r.cursor)
        if cursor.number == target.number:
            return
        rows, screen = move("Down" if target.number > cursor.number else "Up", rows)
    pane.key("Escape")
    raise SwitchFailed(f"the cursor did not reach {target.label}")


# Pi's picker: "Scope: all | scoped", "tab scope (all/scoped)", the query
# line "> text", then rows "→ ✓ meta/x [openrouter]" (→ is the cursor, ✓ the
# current model; a local model may add its name in parentheses, and the
# default model ends with "· default").
PI_PICKER = "tab scope (all/scoped)"
_PI_ROW = re.compile(r"^\s*(→)?\s*(?:✓\s*)?(\S.*?)(?: \([^()]*\))? \[([^\]\s]+)\](?:\s+·.*)?\s*$")


def pi_picker(screen: str) -> tuple[str, list[Row]] | None:
    """Pi's open model picker as (query, rows), or None if it is not open.

    Rows are labelled "provider/id" and numbered from 1 in screen order.
    """
    lines = screen.splitlines()
    starts = [i for i, ln in enumerate(lines) if PI_PICKER in ln]
    if not starts:
        return None
    query, rows = None, []
    for line in lines[starts[-1] + 1:]:
        if query is None:
            if line.lstrip().startswith(">"):
                query = line.lstrip()[1:].strip()
            continue
        if m := _PI_ROW.match(line):
            rows.append(Row(len(rows) + 1, f"{m.group(3)}/{m.group(2)}", bool(m.group(1))))
        elif rows and line.strip():
            break
    return (query, rows) if query is not None else None


def _pi_select(pane: Pane, wanted: str, sleep: Callable[[float], None]) -> None:
    """Pick `wanted` ("provider/id") in Pi's model picker and press Enter.

    Looks in the saved models first, then in the whole catalog. Closes the
    picker with Escape if the model is in neither.
    """
    # A picker left open would take "/model" as its search, and Enter would
    # pick whatever row that matches.
    if pi_picker(pane.screen()):
        pane.key("Escape")
        wait_for(pane, lambda s: not pi_picker(s), "Pi's old picker to close", sleep=sleep)

    def fresh(screen: str) -> bool:
        # Only a just-opened picker has an empty search; text typed anywhere
        # else would be sent to the model as a message.
        found = pi_picker(screen)
        return bool(found) and found[0] == ""

    # Pi's command autocomplete can take the first Enter. No automatic
    # retry: a second Enter in the open picker would pick its current row.
    pane.type("/model", retry_submit=False)
    try:
        wait_for(pane, fresh, "Pi's model picker", timeout=2.0, sleep=sleep)
    except SwitchFailed:
        pane.key("Enter")
        wait_for(pane, fresh, "Pi's model picker", sleep=sleep)
    pane.text(wanted)

    def settled(screen: str):
        # The list once it is filtered by the whole query, cursor drawn.
        found = pi_picker(screen)
        if found and found[0] == wanted and (not found[1] or any(r.cursor for r in found[1])):
            return found[1] or "empty"
        return None

    def exact(rows) -> Row | None:
        return next((r for r in rows or [] if r.label.lower() == wanted.lower()), None)

    def escape(message: str, screen: str | None = None):
        pane.key("Escape")
        raise SwitchFailed(message, screen)

    try:
        rows = wait_for(pane, settled, f"Pi's picker to list {wanted}", sleep=sleep)
    except SwitchFailed as e:
        escape(str(e), e.screen)
    if exact(rows if rows != "empty" else []) is None:
        # Not saved: Tab switches the list to Pi's whole catalog. Only color
        # marks which list shows, so wait a moment for the row to appear.
        pane.key("Tab")
        try:
            rows = wait_for(pane, lambda s: (r := settled(s)) and r != "empty" and exact(r) and r,
                            f"{wanted} in Pi's full catalog", timeout=2.0, sleep=sleep)
        except SwitchFailed as e:
            escape(f"Pi does not list {wanted}, in its saved models or its whole catalog. If the model is "
                   "new, restart the agent so Pi reloads its catalog.", e.screen)
    target = exact(rows)
    for _ in range(len(rows) + 1):
        cursor = next(r for r in rows if r.cursor)
        if cursor.number == target.number:
            pane.key("Enter")
            return
        pane.key("Down" if target.number > cursor.number else "Up")
        try:
            rows = wait_for(
                pane,
                lambda s: (r := settled(s)) and r != "empty" and not any(
                    c.cursor and c.number == cursor.number for c in r) and r,
                "the picker's cursor to move", sleep=sleep,
            )
        except SwitchFailed as e:
            escape(str(e), e.screen)
    escape(f"the cursor did not reach {wanted}")


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


def agy_model(wanted: str, current: str | None) -> str | None:
    """The agy model id for `wanted`: an id agy lists, one of its labels, or a
    family alias ("argon"), which keeps the current effort when agy offers it,
    else takes medium, else the first listed. None if agy has no such model."""
    catalog = tmux.agy_catalog() or [(m, m) for m in tmux.AGY_FALLBACK_MODELS]
    wanted = wanted.strip().lower()
    for model, label in catalog:
        if wanted in (model, label.lower()):
            return model
    family = [model for model, _ in catalog if re.fullmatch(r"[a-z]+", wanted) and f"-{wanted}-" in f"-{model}-"]
    effort = current.rsplit("-", 1)[-1] if current else None
    for pick in (effort, "medium"):
        found = next((m for m in family if pick and m.endswith(f"-{pick}")), None)
        if found:
            return found
    return family[0] if family else None


def _agy_restart(pane: Pane, wanted: str, sleep: Callable[[float], None]) -> str:
    """Restart an idle agy agent in its pane on another model; returns the model id."""
    screen = pane.screen()
    footer = agy_footer(screen)
    if footer is None:
        raise SwitchFailed("agy's footer is not on screen; is a menu open?", screen)
    idle, current = footer
    if not idle:
        # /quit would end the turn it is working on.
        raise SwitchFailed("agy is busy; switching restarts it, so wait until it is idle", screen)
    if not pane.session:
        raise SwitchFailed("no agy conversation id is registered for this agent, so it could not be resumed")
    model = agy_model(wanted, current)
    if model is None:
        listed = ", ".join(m for m, _ in tmux.agy_catalog()) or ", ".join(tmux.AGY_FALLBACK_MODELS)
        raise SwitchFailed(f"agy has no model {wanted} (it lists: {listed})", screen)
    if model == current:
        return model
    command = restore.resume_command({"flavor": "agy", "agent_id": pane.session, "model": model})
    pane.type("/quit", retry_submit=False)

    def shell(_screen: str) -> bool:
        try:
            snap = pane.node.snapshot()
        except nodes.Unavailable:
            return False
        return pane.pane in snap.existing and pane.pane not in snap.live

    wait_for(pane, shell, "agy to exit to the shell", sleep=sleep)
    pane.type(command, retry_submit=False)
    return model


def switch(pane: Pane, wanted: str, sleep: Callable[[float], None] = time.sleep) -> str:
    """Switch the agent in `pane` to `wanted`, for its current session only.

    Returns the model read back off the screen afterwards. Raises
    SwitchFailed if any step does not show up on the screen as expected; an
    open picker is closed again with Escape. Escape is never pressed when no
    picker is open, because in Claude Code and Codex it interrupts a turn.
    """
    timeout = None
    if pane.flavor == "agy":
        wanted = _agy_restart(pane, wanted, sleep)
        timeout = 45.0  # agy starts up again first
    elif pane.flavor == "pi":
        _pi_select(pane, wanted, sleep)
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

    accepted = None

    def shows_or_accepts(screen: str) -> str | None:
        """The model once the switch shows, after accepting the confirmation.

        Claude Code asks before switching models mid-conversation. Only a
        dialog that names the requested model is accepted, and its
        "Yes, switch to ..." row is focused, so Enter takes it. Pressed once
        per dialog: the screen lags a key, and a second Enter would land on
        the prompt behind it.
        """
        nonlocal accepted
        if (seen := shows_wanted(screen)) is not None:
            return seen
        label = cache_confirm_model(screen) if pane.flavor == "claude" else None
        if label is None:
            accepted = None
            return None
        if not confirm_names(pane.flavor, wanted, label):
            raise SwitchFailed(
                f"Claude Code asked to confirm switching to {label}, not {wanted}", screen)
        if accepted != label:
            pane.key("Enter")
            accepted = label
        return None

    return wait_for(pane, shows_or_accepts, f"the screen to show {wanted}", timeout=timeout, sleep=sleep)
