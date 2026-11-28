"""FastAPI server. Endpoints: /register, /send, /messages, /recipients, /health,
plus the live web portal at / (backed by /api/state and /api/peek)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import os
import re
import sqlite3
import weakref
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import threading
from dataclasses import dataclass

import orjson
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import activity, attachments, boards, bundle, db, digest, handoff, model_switch, names, nodes, notifications, restart, restore, team_view, tmux

log = logging.getLogger("agent_swarm.monitor")

_JSON_SCALARS = {str, int, bool, type(None)}


def _plain_json(value: dict) -> bool:
    """Check without copying the JSON tree or walking the contents of strings.

    orjson silently writes NaN and infinity as null and handles some Python
    types on its own. Let FastAPI keep its original behavior for those values.
    The fast encoder already rejects non-string keys and out-of-range ints.
    """
    pending = [value]
    while pending:
        item = pending.pop()
        kind = type(item)
        if kind is dict:
            pending.extend(item.values())
        elif kind is list:
            pending.extend(item)
        elif kind not in _JSON_SCALARS and (kind is not float or not math.isfinite(item)):
            return False
    return True


def _read_json(value: dict) -> Response:
    if _plain_json(value):
        try:
            return Response(orjson.dumps(value), media_type="application/json")
        except orjson.JSONEncodeError:
            pass
    return JSONResponse(jsonable_encoder(value))


# Default activity shown when the monitor is off or hasn't observed an agent
# yet. The dashboard must tolerate this shape.
UNKNOWN_ACTIVITY = {"status": "unknown", "detail": None, "error": None, "since": None, "context": None}

DB_PATH = Path(os.environ.get("AGENT_SWARM_DB", "~/.agent-swarm/db.sqlite")).expanduser()
PORTAL_PATH = Path(__file__).parent / "portal.html"
PORTAL_STATIC_PATH = Path(__file__).parent / "static"

# Reserved handle for the human operator. Never assigned to an agent
# (the name pool contains only animals). Messages sent to it are recorded
# for the dashboard instead of being injected into a tmux pane.
OWNER = "owner"
# The server itself, when it signs a message (the supervisor's digest nudges).
HUB = "hub"

# What a note needs, said where a worker meets it when it matters: the error it
# gets if it tries to close without one. Task messages only say a note is
# required, so they stay short.
NOTE_GUIDANCE = (
    "Say how to verify it: how to use the feature or reproduce the fix, and "
    "where to look - the command, endpoint, screen or files that changed."
)

# The dashboard shows each agent's latest status line, so the owner can see
# what everyone is doing (and did last) without a task to go by.
STATUS_GUIDANCE = (
    "Keep `buzz status` current as the work moves (\"testing #12\", "
    "\"waiting on review\") and end with \"done: #12\"; the owner's "
    "dashboard shows each agent's latest line."
)


# Where a request comes from decides what it may do. The owner is whoever
# reaches the server over loopback (the dashboard, the CLI on the hub
# machine). A node is a machine that presents its enrolment token; it may do
# what an agent does, on its own behalf, and nothing the owner does.
@dataclass(frozen=True)
class Principal:
    kind: str  # "owner" or "node"
    node: str | None = None  # the node's name, or the Tailscale login an owner came in with


LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

# Tailscale Serve proxies to the hub from loopback and adds these headers,
# stripping any the client sent, so from the loopback peer they are the
# proxy's word about who is on the other end.
TAILSCALE_LOGIN_HEADER = "tailscale-user-login"
FORWARDED_HEADERS = ("x-forwarded-for", "forwarded")


def owner_logins() -> frozenset[str]:
    """Tailscale logins allowed to act as the owner through the proxy. Empty
    means any login Serve vouches for, which on a single-user tailnet is
    the one person; name logins here on a shared tailnet."""
    raw = os.environ.get("AGENT_SWARM_OWNER_LOGINS", "")
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


TAB_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,23}")


def extra_tabs() -> list[dict[str, str]]:
    """Other pages to show as dashboard tabs, from AGENT_SWARM_TABS:
    comma-separated name=url pairs, e.g. "usage=http://127.0.0.1:8531".
    The hub serves each page under /tabs/<name>/, so the dashboard shows it
    from its own origin (the Mac app blocks frames from other origins).
    Entries with a bad name or a non-http(s) url are skipped."""
    tabs = []
    for entry in os.environ.get("AGENT_SWARM_TABS", "").split(","):
        name, _, url = entry.strip().partition("=")
        name, url = name.strip().lower(), url.strip()
        if (TAB_NAME.fullmatch(name) and url.startswith(("http://", "https://"))
                and name not in {t["name"] for t in tabs}):
            tabs.append({"name": name, "url": url})
    return tabs


class RegisterReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tmux_pane: str = Field(min_length=1)
    agent_id: str | None = Field(
        default=None,
        description="Stable session identifier (e.g. Claude conversation UUID). "
        "This is the agent's 'real' identity across model changes.",
    )
    requested_user: str | None = Field(
        default=None,
        description="Preferred handle. Granted when it is free and well-formed; "
        "a handle held by another agent is a 409 rather than a silent "
        "reassignment. Omit to let the server pick from the name pool.",
    )
    model: str | None = Field(
        default=None,
        description="Model label for telemetry only (e.g. 'claude-opus-4-7'). "
        "Not used for identity.",
    )
    flavor: str | None = Field(
        default=None,
        description="Optional delivery flavor; controls default submit key behavior.",
    )
    node: str | None = Field(
        default=None,
        description="Machine the agent's pane lives on; the CLI sends "
        "$AGENT_SWARM_NODE or its short hostname. Recorded as metadata and "
        "defaults to the server's own machine.",
    )
    instructions: str | None = Field(
        default=None,
        description="Optional human guidance for peers talking to this agent.",
    )
    message_prefix: str | None = Field(
        default=None,
        description="Optional literal prefix inserted before each delivered message.",
    )
    submit_key: str | None = Field(
        default=None,
        description="Optional tmux submit key override (defaults to C-m).",
    )


class RetireReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_ids: list[str] = Field(min_length=1)


class PruneReq(BaseModel):
    include_shells: bool = Field(
        default=False,
        description="Also drop registrations whose pane exists but only runs a bare shell.",
    )


class PinReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pinned: bool


class OwnerNoteReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=1000)


class ActorFields(BaseModel):
    """Who is calling, as the CLI reports it; see _resolve_caller.

    The owner's dashboard sends none of these. An agent's CLI sends its pane,
    node and session, and what follows goes out in that agent's name rather
    than the owner's: a node token must never be able to speak as the human.
    """

    tmux_pane: str | None = Field(
        default=None,
        description="The caller's pane, when it has one. A session in a "
        "background host has none and is identified by agent_id alone.",
    )
    node: str | None = Field(
        default=None,
        description="Machine the caller's pane lives on; the CLI sends "
        "$AGENT_SWARM_NODE or its short hostname. Omitted means the server's own.",
    )
    agent_id: str | None = Field(
        default=None,
        description="The caller's harness session id (CLAUDE_CODE_SESSION_ID, "
        "CODEX_THREAD_ID). When given it identifies the caller; the pane is only "
        "a fallback for a registration that has no session id yet.",
    )
    pane_verified: bool | None = Field(
        default=None,
        description="True when the CLI checked that it runs inside tmux_pane "
        "(or the pane was given explicitly). Only a verified pane may vouch for "
        "an unknown session id.",
    )
    pane_in_tree: bool | None = Field(
        default=None,
        description="True only when the CLI found the pane's own process among "
        "its ancestors (an explicit --pane does not count). With a matching "
        "harness, it lets the pane's registration move to a new session id.",
    )
    harness: str | None = Field(
        default=None,
        description="Which harness the session id came from: claude or codex.",
    )


class StatusReq(ActorFields):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=200)


class SendReq(ActorFields):
    model_config = ConfigDict(extra="forbid")

    recipient: str = Field(min_length=1)
    content: str = Field(min_length=1)
    reply_to: int | None = Field(default=None, gt=0)
    context: str | None = None


class OwnerSendReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient: str = Field(min_length=1)
    content: str = ""
    reply_to: int | None = Field(default=None, gt=0)
    context: str | None = None
    attachments: list[str] = Field(
        default_factory=list,
        max_length=attachments.MAX_PER_MESSAGE,
        description="Names returned by POST /attachments. The recipient agent "
        "gets each as an absolute file path appended to the message.",
    )
    client_id: str | None = Field(
        default=None, min_length=1, max_length=100,
        description="The dashboard's own id for this message. Sending the same "
        "id again (a retry after a lost answer) returns the first attempt's "
        "outcome instead of delivering a second copy.",
    )


class BoardPostReq(ActorFields):
    body: str
    subject: str | None = Field(default=None, max_length=120)
    reply_to: int | None = Field(default=None, gt=0, le=2**63 - 1)
    client_id: str | None = Field(default=None, min_length=1, max_length=200)


class NotifyReq(ActorFields):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=notifications.MAX_TEXT_LENGTH)
    context: str | None = None


class RestartReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = False
    dry_run: bool = True


RESTART_WAIT = 30.0


class SwitchReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: Literal["claude", "codex", "pi", "agy"] = Field(description="The harness to move the agent to.")
    model: str | None = Field(default=None, description="Optional model for the new harness.")
    max_chars: int = Field(default=handoff.DEFAULT_MAX_CHARS, ge=2000, le=2_000_000,
                           description="How much conversation to carry over, in characters.")
    force: bool = Field(default=False, description="Switch even when the agent is already on that harness.")
    dry_run: bool = Field(default=False, description="Report the plan without writing or launching.")


class SpawnReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flavor: Literal["claude", "codex", "pi", "agy", "hermes"] = "claude"
    model: str | None = Field(
        default=None,
        description="Optional harness model. Only honored when it is one of "
        "the harness's known models; otherwise the harness default is used.",
    )
    node: str | None = Field(
        default=None,
        description="Machine to spawn on. Omitted means the server's own.",
    )
    cwd: str | None = Field(
        default=None,
        description="Folder to start in: one of the machine's AGENT_SWARM_SPAWN_DIRS. "
        "Omitted means the first of them, or the home folder when none are set.",
    )


class TeamReorderReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: list[int] = Field(min_length=0)


class TeamCreateReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)


class TeamUpdateReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    queen: str | None = None
    objective: str | None = Field(
        default=None,
        description="Coordination objective delivered with a queen promotion.",
    )


class AgentTeamReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: int | None = None


class SupervisorReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1)
    objective: str | None = Field(
        default=None,
        description="What the owner wants watched or driven; delivered with the role prompt.",
    )


class TerminalReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, max_length=4000)
    key: str | None = None


class SwitchModelReq(ActorFields):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(
        min_length=1, max_length=200,
        description="The model to switch to, as the harness names it: a Claude "
        "alias or id (sonnet, claude-opus-5-5), a Codex slug, Pi's provider/id, an "
        "agy id or family (gemini-4-argon-medium, argon).",
    )


class AgentModelReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(
        default=None,
        max_length=120,
        description="Model label shown on the dashboard, e.g. claude-opus-4-7. "
        "Display only: the running agent is not switched. Blank clears it.",
    )


# Both appointed roles end the same way: they are prompts, not permissions.
ROLE_FOOTER = "This role is a prompt, not server authority. The owner keeps every right and can"


def _queen_prompt(team: dict, objective: str, previous_queen: str | None = None) -> str:
    teammates = [m for m in team["members"] if m != team["queen"]]
    roster = ", ".join(teammates) if teammates else "(no teammates yet)"
    handover = (
        f"The previous queen was {previous_queen}; a handover is coming. "
        "Start with `buzz team`.\n\n"
        if previous_queen else ""
    )
    return (
        f"The owner has made you Queen of team '{team['name']}'. "
        f"Your teammates: {roster}.\n\n"
        f"Objective: {objective}\n\n"
        f"{handover}"
        "You are the owner's coordination point for this team until the owner "
        "ends or changes the role. Now tell each teammate, with context "
        "queen-status: you coordinate this team for this objective, their task "
        "coordination goes through you, and they should read the team board "
        "with `buzz board` at task boundaries.\n\n"
        "Split the objective into concrete tasks. Create and assign them with "
        "buzz task-create and buzz task-update; record ordering with "
        "--depends-on <ids> so the task board shows the dependency graph. Tasks "
        "the owner assigns to the team come to you: reassign or split them "
        "among teammates. Watch progress with `buzz team`: each member's state, "
        "status line and open tasks, which tasks are ready, blocked or stale, "
        "and who is free; `buzz team --since 2h` shows only what changed. Post "
        "team-wide decisions, findings and shared context with `buzz board post` "
        "instead of messaging each teammate, and point them at a post by number "
        "(`buzz board show N`). Normally coordinate rather than implement. "
        "Require repository workers to use branch task/<id> in a dedicated "
        "worktree and record it on the task. Track progress, dependencies, "
        "stopped agents, commits, tests, and integration; integrate one branch "
        "at a time. Keep the owner informed of material progress and decisions, "
        "and ask before changing scope or the definition of done. Coordinate "
        f"only your own team.\n\n{ROLE_FOOTER} replace or demote you at any time."
    )


def _supervisor_prompt(user_id: str, objective: str, peers: list[dict]) -> str:
    live = [p["user_id"] for p in peers if p.get("alive") and p["user_id"] != user_id]
    roster = ", ".join(live) if live else "(no other live agents right now)"
    return (
        f"The owner has made you the swarm supervisor: the one agent the owner "
        f"asks about the whole swarm. Live agents now: {roster}.\n\n"
        f"Objective: {objective}\n\n"
        "What you do:\n"
        "- Answer the owner. When asked what is going on, run `buzz digest` "
        "(`--minutes N` for a window, or `--after-message ID` from the end of your "
        "last digest) and reply in a few lines: what changed, who needs attention, "
        "what is done, what is stalled. For one task, read `buzz tasks` and "
        "the messages tagged `task #N` (`buzz messages --user <handle>`); "
        "if that does not say, ask the assignee with `buzz send` and "
        "relay the answer.\n"
        "- Delegate when asked. `buzz task-create \"title\" --description ... "
        "--assignee <handle>` files work; the assignee is notified in your "
        "name. Prefer an idle agent of a suitable harness. If none is free, "
        "`buzz spawn --flavor claude|codex|pi|agy|hermes` starts one; assign "
        "to the handle it prints. Record ordering with --depends-on.\n"
        "- Watch the swarm. The hub sends you a message from `hub` tagged `digest` "
        "when there is new traffic or task changes you were not party to; read the "
        "digest it names and tell the owner only what matters. An agent whose pane "
        "shows an approval prompt appears as `needs attention`; you cannot answer "
        "the prompt, but tell the owner which agent and why.\n"
        "- Admin. `buzz stop <handle>` kills an agent's pane: ask the owner "
        "first unless they already told you to. Never delete tasks or change team "
        "membership on your own.\n\n"
        "Report facts, not guesses: a delivery marked unknown may or may not have "
        "arrived, so say so and never resend on your own. Keep replies to the owner "
        "short; send them with `buzz send --to owner`. "
        "Set `buzz status \"supervising: ...\"` so the dashboard shows the "
        f"role.\n\n{ROLE_FOOTER} end the role at any time."
    )


def _protocol_brief(
    user_id: str, peers: list[dict], owner_note: str | None = None, on_team: bool = False
) -> str:
    """A one-shot primer the agent sees in its register response.

    Tells the agent what inbound messages look like so a line appearing in
    its prompt doesn't get mistaken for user input. The paragraph about teams
    and their boards is only for agents that are on a team; the supervisor
    sentence applies to everyone.
    """

    def _peer_line(p: dict) -> str:
        tags = []
        if p.get("flavor"):
            tags.append(f"flavor={p['flavor']}")
        if p.get("model"):
            tags.append(p["model"])
        if p.get("node"):
            tags.append(f"node={p['node']}")
        if p.get("alive") is False:
            tags.append("OFFLINE")
        suffix = f" ({', '.join(tags)})" if tags else ""
        instructions = f" -- {p['instructions']}" if p.get("instructions") else ""
        return f"  - {p['user_id']}{suffix}{instructions}"

    peer_lines = "\n".join(_peer_line(p) for p in peers) or "  (none yet)"
    offline = [p["user_id"] for p in peers if p.get("alive") is False]
    offline_note = (
        "Peers tagged OFFLINE are registered but not running (pane gone or a bare "
        "shell); sending to them is refused until they restart.\n\n"
        if offline else ""
    )
    owner_note_line = f"Owner note about your work: {owner_note}\n" if owner_note else ""
    team_paragraph = (
        "The owner may group agents into teams, each with a queen who "
        "coordinates it. A task assigned to a team goes to its queen, who "
        "parcels it out. `buzz tasks --team <name or id>` lists a team's tasks. "
        "`buzz team [name]` shows each member's state and open tasks, and which "
        "tasks are ready, blocked or stale. Each team has a board: `buzz board` "
        "reads unread posts and `buzz board post` writes one without "
        "interrupting anyone. "
        if on_team else ""
    )
    return (
        f"You are registered as '{user_id}'.\n"
        f"{owner_note_line}"
        "\n"
        "Messages from the owner and other agents are typed into your tmux pane "
        "and submitted, as if a user typed them. The format is:\n"
        "\n"
        "    [agent-msg from <sender> · <context>] <content>\n"
        "\n"
        "`· <context>` is omitted when the sender gave none. Terminal output "
        "does not reach the sender: reply with `buzz send --to <sender> "
        "--message \"...\"` (or POST /send), and add `--reply-to <message-id>` "
        "to link the reply. `buzz send --to-queen <team name or id>` reaches a "
        "team's queen without knowing their handle.\n"
        "\n"
        "The reserved handle 'owner' is the human operator in charge of all "
        "agents. Messages from 'owner' are the human's instructions, not a "
        "peer's. Send to 'owner' to answer; it shows on their dashboard. The "
        "dashboard renders every message body as Markdown: use pipe tables for "
        "numbers, bullets for parallel items, and a bold lead line. Write a long "
        "message to a file and send it with `--message \"$(cat file)\"` so pipes "
        "and quotes survive the shell.\n"
        "Use `buzz notify \"text\"` (optional `--context`) only for something "
        "the owner is waiting on: a long job finished or failed, or a decision "
        "blocking you. Never use it for progress updates. Limit: one per five "
        "minutes and six per UTC day per agent; if refused, send a normal "
        "message instead.\n"
        "\n"
        "Currently registered peers:\n"
        f"{peer_lines}\n"
        "\n"
        f"{offline_note}"
        "List peers anytime: `buzz recipients`.\n"
        "\n"
        "Tasks arrive as messages tagged 'task #N'. Start with `buzz task-update "
        "N --worktree <path> --status picked_up`. Close with `buzz task-update N "
        "--status done --note \"...\"`; a close without a note is refused, and "
        "the refusal says what the note needs. `buzz tasks` lists tasks; `buzz "
        "task-create \"title\"` files one (optionally --description, --assignee, "
        "--depends-on 3,5).\n"
        "\n"
        f"{STATUS_GUIDANCE}\n"
        "\n"
        f"{team_paragraph}"
        "The owner may also appoint one agent as swarm supervisor, the agent "
        "they ask about the whole swarm; `buzz supervisor` says who, if "
        "anyone, holds it."
    )


def create_app(
    db_path: Path = DB_PATH, monitor: bool = True, trust_loopback: bool | None = None
) -> FastAPI:
    conn = db.connect(db_path)
    boards.clamp_cursors(conn)
    if trust_loopback is None:
        trust_loopback = os.environ.get("AGENT_SWARM_TRUST_LOOPBACK", "1") != "0"
    # Every machine whose tmux this server can drive. The local one is always
    # here; others come and go with their connection.
    attachments_root = Path(db_path).expanduser().resolve().parent / "attachments"
    fleet = nodes.NodeRegistry(nodes.LocalNode(tmux.local_node(), attachments_root))
    # Rows from before nodes were recorded were all registered against this
    # server's own tmux, so they belong to this machine; likewise worktree
    # paths recorded before they carried a node.
    db.fill_missing_node(conn, fleet.local.name)
    db.fill_missing_worktree_node(conn, fleet.local.name)
    # Nothing is in flight at startup, so a pending message was dispatched
    # by a server that stopped before recording its result: unknown. This
    # holds only while one hub process uses the database; a second one
    # starting alongside would mark the first's in-flight rows.
    abandoned = db.abandon_pending_messages(
        conn, "the server stopped before the delivery result was recorded"
    )
    if abandoned:
        log.warning("%d message(s) left pending by the previous run are now unknown", abandoned)

    # Per-agent activity state, mutated by the monitor loop and read by
    # /api/state. Keyed by user_id; see agent_swarm.activity.step for the shape.
    registry: dict[str, dict] = {}
    retirement_lock = threading.Lock()
    restart_lock = threading.Lock()
    restarting: set[str] = set()
    interval = float(os.environ.get("AGENT_SWARM_MONITOR_INTERVAL", "5.0"))
    grace = float(os.environ.get("AGENT_SWARM_ATTENTION_GRACE", "60.0"))

    # How often the supervisor is told about traffic it was not party to.
    # Every nudge is a paste into its pane, so this is deliberately coarse.
    supervisor_interval = float(os.environ.get("AGENT_SWARM_SUPERVISOR_INTERVAL", "300"))

    def _nudge_supervisor(now: float, alive: set[str]) -> None:
        """One short message when enough time has passed and something changed.

        The cursor moves every interval, nudge or not, so a quiet spell is
        never reported late, and an unknown delivery is never resent.
        """
        sup = db.get_supervisor(conn)
        if not sup or supervisor_interval <= 0 or sup["user_id"] not in alive:
            return
        last = sup.get("nudged_at") or sup["since"]
        if now - last < supervisor_interval:
            return
        msgs = db.fetch_messages_after(conn, sup["cursor"])
        counts = digest.changed(msgs, db.list_tasks(conn), last, sup["user_id"])
        newest = max([sup["cursor"], *(m["id"] for m in msgs)])
        db.set_supervisor_cursor(conn, newest, now)
        if counts["messages"] or counts["tasks"]:
            try:
                _deliver_as(HUB, sup["user_id"], digest.nudge_text(counts, sup["cursor"]), "digest")
            except HTTPException as exc:
                log.warning("supervisor nudge not delivered: %s", exc.detail)

    async def _monitor_tick():
        recipients = db.list_recipients(conn)
        # One look at each node's tmux per tick, all nodes at once. The node
        # object is held for the whole tick so a reconnect mid-tick cannot
        # swap it out; a node that fails to answer, or is not connected,
        # leaves its agents stopped rather than failing the tick.
        held = {name: fleet.get(name) for name in {r["node"] for r in recipients}}

        async def _observe(node: nodes.Node | None) -> nodes.PaneSnapshot | None:
            if node is None:
                return None
            try:
                return await asyncio.to_thread(node.snapshot)
            except nodes.Unavailable as e:
                log.warning("node %s could not be observed: %s", node.name, e)
                return None
            except Exception:
                log.exception("snapshot of node %s failed", node.name)
                return None

        snaps = dict(zip(held, await asyncio.gather(*(_observe(n) for n in held.values()))))
        observations = []
        for r in recipients:
            pane, node, snap = r["tmux_pane"], held[r["node"]], snaps[r["node"]]
            # An id from an earlier tmux server now names some other pane.
            alive = (
                snap is not None and pane in snap.live and _stale(r, snap.server) is None
            )
            capture = colored = None
            if alive:
                # Claude Code and Codex title their pane with the current topic.
                topic = tmux.title_summary(snap.title(pane) or "")
                if topic:
                    db.record_summary(conn, r["user_id"], topic, "title")
                # Remember where the harness runs: resuming its session after
                # the pane is gone starts it there again.
                cwd = snap.cwd(pane)
                if cwd and cwd != r.get("cwd"):
                    db.set_cwd(conn, r["user_id"], cwd)
                # Subprocess capture must not block the event loop, and one
                # pane's failure must not end the tick for the others.
                # With colors, for the error check; the rest reads it plain.
                try:
                    text, err = await asyncio.to_thread(
                        node.capture, pane, r.get("tmux_server"), True
                    )
                except Exception:
                    log.exception("capture of %s on %s failed", pane, node.name)
                    text, err = None, "capture failed"
                colored = text if err is None else None
                capture = activity.strip_colors(colored) if colored is not None else None
                # Keep the model label in step with what the harness shows,
                # whoever changed it (/model typed in the pane, a switch).
                seen = model_switch.screen_model(r.get("flavor"), capture)
                if seen and seen != r.get("model"):
                    db.set_recipient_model(conn, r["user_id"], seen)
            observations.append(
                activity.Observation(r["user_id"], r.get("flavor"), alive, capture, colored)
            )
        now = time.time()
        notes = activity.step(registry, observations, now, interval, grace)
        for note in notes:
            db.record_message(
                conn,
                sender=note.user_id,
                recipient=OWNER,
                context="attention",
                content=f"needs attention: {note.detail}",
                status="delivered",
            )
        # Off the loop: a nudge pastes into a pane, which blocks (local tmux
        # subprocesses) or waits on this very loop (a remote node's send).
        await asyncio.to_thread(_nudge_supervisor, now, {o.user_id for o in observations if o.pane_alive})

    retention_days = float(
        os.environ.get(
            "AGENT_SWARM_ATTACHMENT_RETENTION_DAYS", attachments.DEFAULT_RETENTION_DAYS
        )
    )
    # 0 (or less) keeps sent images forever; unsent drafts are still swept.
    retention = retention_days * attachments.DAY if retention_days > 0 else None
    message_days = float(os.environ.get("AGENT_SWARM_MESSAGE_RETENTION_DAYS", "120"))

    def _cleanup() -> dict:
        """Daily cleanup: old messages first, then images nothing needs."""
        now = time.time()
        messages = 0
        if message_days > 0:
            messages = db.delete_messages_before(conn, now - message_days * attachments.DAY)
        # Images carried only by the messages just deleted are now unreferenced
        # and, being older than the orphan grace, go in the same pass.
        images = attachments.sweep(
            attachments_root, db.attachment_last_used(conn), now, retention
        )
        if messages or images:
            log.info("cleanup removed %d message(s), %d image(s)", messages, len(images))
        return {"messages": messages, "images": images}

    async def _cleanup_loop():
        while True:
            try:
                await asyncio.to_thread(_cleanup)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("cleanup failed")
            await asyncio.sleep(attachments.DAY)

    async def _monitor_loop():
        while True:
            try:
                await _monitor_tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A failed tick is logged and skipped, never fatal to the loop.
                log.exception("monitor tick failed")
            await asyncio.sleep(interval)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Background work (monitor, daily cleanup) is off in tests.
        tasks = (
            [asyncio.create_task(_monitor_loop()), asyncio.create_task(_cleanup_loop())]
            if monitor else []
        )
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="agent-swarm", version="0.1.0", lifespan=lifespan)

    logins = owner_logins()

    @app.middleware("http")
    async def _authenticate(request: Request, call_next):
        """Attach a Principal, or refuse.

        A bearer token names a node, wherever it comes from. Otherwise the
        real socket peer decides (the server runs without proxy-header
        rewriting, so it is never a forwarded address):

        - loopback, not forwarded: the owner, while AGENT_SWARM_TRUST_LOOPBACK
          is not 0 (the dashboard and CLI on the hub machine)
        - loopback, forwarded by Tailscale Serve with its identity header:
          the owner (any login unless AGENT_SWARM_OWNER_LOGINS names who).
          Serve is tailnet-only and vouches for the login; Serve strips
          client-supplied identity headers, so from loopback the header is
          the proxy's word, and its presence alone marks a proxied request
        - loopback, forwarded without an identity: refused, whatever the
          proxy; an identity from a non-loopback peer is refused too

        Health stays open so a node can check the hub is up.
        """
        if request.url.path == "/health":
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            node = db.node_for_token(conn, auth[7:].strip())
            if node is None:
                return JSONResponse(
                    {"detail": {"error": "unknown token; enrol the machine with `buzz node-token`"}},
                    status_code=401,
                )
            request.state.principal = Principal("node", node)
            return await call_next(request)
        peer_is_loopback = bool(request.client) and request.client.host in LOOPBACK_HOSTS
        login = request.headers.get(TAILSCALE_LOGIN_HEADER, "").strip().lower()
        # An identity header is itself a sign of the proxy: it never falls
        # through to the plain-loopback owner path.
        proxied = bool(login) or any(h in request.headers for h in FORWARDED_HEADERS)
        if peer_is_loopback and proxied:
            if not login:
                return JSONResponse(
                    {"detail": {"error": "forwarded request without a Tailscale identity",
                                "hint": "the hub accepts proxied requests only from Tailscale Serve"}},
                    status_code=401,
                )
            if logins and login not in logins:
                return JSONResponse(
                    {"detail": {"error": f"{login} is not an owner login", "hint": "AGENT_SWARM_OWNER_LOGINS"}},
                    status_code=403,
                )
            request.state.principal = Principal("owner", login)
        elif peer_is_loopback and trust_loopback:
            request.state.principal = Principal("owner")
        else:
            return JSONResponse(
                {"detail": {"error": "authentication required", "hint": "set AGENT_SWARM_TOKEN or run `buzz join`"}},
                status_code=401,
            )
        return await call_next(request)

    def _require_owner(request: Request) -> None:
        if request.state.principal.kind != "owner":
            raise HTTPException(
                status_code=403,
                detail={"error": "owner only", "detail": "a node token cannot do this"},
            )

    def _resolve_caller(
        node: nodes.Node, tmux_pane: str | None, agent_id: str | None, pane_verified: bool | None,
        pane_in_tree: bool | None = None, harness: str | None = None,
    ) -> tuple[str | None, str, str | None, tuple]:
        """Who is calling: (user_id, how, why_not, (pane, label)).

        A harness session id is the caller's identity wherever its commands
        run; Claude Code and Codex can run a session's tools in a background
        host with no TMUX_PANE, or a stale one, so the pane alone can't say.
        A known id is resolved before the pane is even looked at, so a stale
        or unresolvable pane can't reject a valid session. An id held by an
        agent on another node is refused, not resolved.

        An unknown id never falls back to whatever agent holds the pane: a
        daemon-hosted session naming someone else's pane would take that
        agent's identity. Only a pane the CLI verified it runs inside may
        vouch for it, and only by adopting the id onto a registration that
        has none (one made before session ids were sent); a pane registered
        under a different id is refused with how to re-register, unless the
        CLI found the pane's own process among its ancestors (pane_in_tree)
        and its harness is the registration's flavor: then it is the same
        agent after a /clear or a fresh session in its pane, and the
        registration moves to the new id, as `buzz register` would.
        A background host is never inside the pane's process tree. Without an
        id, a pane the CLI says it is not in is refused; an older CLI, which
        says nothing (None), is identified by its pane as before.
        """
        agent_id = (agent_id or "").strip() or None
        if agent_id:
            by_id = db.lookup_user_by_agent_id(conn, agent_id)
            if by_id:
                # Session ids are public (`buzz recipients` lists them), so
                # an id held on another machine is a refusal, never this caller.
                if (db.get_recipient(conn, by_id) or {}).get("node") != node.name:
                    return None, "session", f"this session belongs to {by_id} on another node", (tmux_pane, None)
                if not (pane_in_tree and tmux_pane):
                    return by_id, "session", None, (tmux_pane, None)
                # The caller runs inside its pane. If the session's agent is
                # live in another pane, this is a copy of that session
                # (`claude --resume` of a live agent): it is whoever holds
                # this pane, never the agent it copied.
                pane, label, server = _pane_ref(tmux_pane, node)
                if not _live_elsewhere(by_id, node.name, pane, server):
                    return by_id, "session", None, (pane, label)
                pane_user = db.lookup_user_by_pane(conn, node.name, pane, server)
                return pane_user, "pane", None if pane_user else (
                    f"this session is {by_id}'s, which is live in another pane; run "
                    "`buzz register` here to register this pane as its own agent"
                ), (pane, label)
        if not tmux_pane:
            why = "this session is not registered" if agent_id else "no pane and no session id"
            return None, "session" if agent_id else "pane", f"{why}; run `buzz register` from the agent's pane", (None, None)
        if pane_verified is False:
            # Refused before resolving: the pane isn't the caller's to vouch for.
            return None, "session" if agent_id else "pane", (
                f"the caller is not running inside pane {tmux_pane}"
                + (" and its session is not registered" if agent_id else " and sent no session id")
                + "; run this from the agent's own pane, or pass --pane"
            ), (tmux_pane, None)
        # Resolved once: on a remote node every resolve is a round trip.
        pane, label, server = _pane_ref(tmux_pane, node)
        where = (pane, label)
        pane_user = db.lookup_user_by_pane(conn, node.name, pane, server)
        if not agent_id:
            return pane_user, "pane", None if pane_user else "this pane is not registered", where
        if pane_user is None:
            return None, "session", "this session is not registered; run `buzz register`", where
        if not pane_verified:
            return None, "session", (
                f"this session is not registered, and the caller is not verified to be in pane "
                f"{tmux_pane} (held by {pane_user}); register from the agent's own pane, or pass --pane"
            ), where
        registration = db.get_recipient(conn, pane_user) or {}
        held = (registration.get("agent_id") or "").strip()
        same_harness = bool(harness) and harness.lower() == (registration.get("flavor") or "").lower()
        if held and held != agent_id and pane_in_tree and same_harness:
            if db.adopt_agent_id(conn, pane_user, agent_id, node=node.name, tmux_pane=pane,
                                 tmux_server=server, replacing=held):
                log.warning("moved %s from session %s to %s (same pane %s, harness %s)",
                         pane_user, held[:8], agent_id[:8], pane, harness)
                return pane_user, "session", None, where
        if held and held != agent_id:
            return None, "session", (
                f"pane {tmux_pane} is registered to {pane_user} under a different session id. If this "
                f"is {pane_user}, run `buzz register` from this pane (without --name) to move "
                "its existing handle to this session; that is safe when this shell's TMUX_PANE is "
                f"{tmux_pane}. Otherwise register from your own pane"
            ), where
        if not db.adopt_agent_id(conn, pane_user, agent_id, node=node.name, tmux_pane=pane, tmux_server=server):
            # Lost a race, or the id is already someone else's: re-check.
            now = db.lookup_user_by_agent_id(conn, agent_id)
            current = db.get_recipient(conn, pane_user) or {}
            if (now != pane_user or current.get("node") != node.name
                    or current.get("tmux_pane") != pane or current.get("tmux_server") != server):
                return None, "session", (
                    f"could not record this session on {pane_user} (its registration changed); "
                    "retry, or run `buzz register`"
                ), where
        return pane_user, "pane", None, where

    def _caller(
        node: nodes.Node, tmux_pane: str | None, agent_id: str | None, pane_verified: bool | None,
        pane_in_tree: bool | None = None, harness: str | None = None,
    ) -> str:
        user_id, _, why_not, _ = _resolve_caller(
            node, tmux_pane, agent_id, pane_verified, pane_in_tree, harness
        )
        if user_id is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "sender not registered", "detail": why_not, "tmux_pane": tmux_pane},
            )
        return user_id

    def _claimed_node(request: Request, node: str | None) -> nodes.Node:
        """The node a request says it is on, checked against who is asking.

        A node token may only speak for its own machine; the owner may name
        any node (the dashboard spawning on a laptop, say).
        """
        principal = request.state.principal
        if principal.kind == "node" and (node or fleet.local.name) != principal.node:
            raise HTTPException(
                status_code=403,
                detail={"error": "node mismatch", "claimed": node, "authenticated": principal.node},
            )
        return _node_or_422(node)

    def _watch_list(node_name: str) -> list[dict]:
        """The panes a node should capture every tick: its registered agents."""
        return [
            {"pane": r["tmux_pane"], "tmux_server": r.get("tmux_server")}
            for r in db.list_recipients(conn)
            if r.get("node") == node_name
        ]

    def _refresh_watch(node_name: str) -> None:
        node = fleet.get(node_name)
        if isinstance(node, nodes.RemoteNode):
            node.set_watch(_watch_list(node_name))

    # Registry membership changes from HTTP worker threads (rotate, revoke)
    # and from the event loop (a node connecting); the lock keeps a token
    # check and the publication it permits together.
    fleet_lock = threading.Lock()

    def _disconnect(name: str, reason: str) -> None:
        """Drop a node from the registry, fencing its connection if it has one."""
        with fleet_lock:
            node = fleet.get(name)
            if isinstance(node, nodes.RemoteNode):
                node.fence(reason)
            fleet.remove(name)

    def _own_row_or_403(request: Request, user_id: str) -> dict | None:
        """The recipient row, after checking a node token may touch it.

        A node may change only agents on its own machine. Moving an agent
        between machines, or clearing someone else's registration, is the
        owner's to do.
        """
        row = db.get_recipient(conn, user_id)
        principal = request.state.principal
        if row is not None and principal.kind == "node" and row.get("node") != principal.node:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "agent belongs to another node",
                    "user_id": user_id,
                    "node": row.get("node"),
                    "authenticated": principal.node,
                },
            )
        return row

    def _agent_or_404(user_id: str) -> dict:
        recipient = db.get_recipient(conn, user_id)
        if recipient is None:
            raise HTTPException(status_code=404, detail={"error": "unknown agent"})
        return recipient

    def _node_failure(error: str, result) -> HTTPException:
        """502 when the node's outcome is unknown, 500 when it reported failure."""
        return HTTPException(
            status_code=502 if result.status == "unknown" else 500,
            detail={"error": error, "status": result.status, "detail": result.error},
        )

    def _actor(request: Request, req: ActorFields) -> str:
        """Whose name a resulting message goes out in.

        No pane and no session means the dashboard, which only the owner
        reaches. Otherwise the agent is resolved like any caller (session id
        first, see _resolve_caller). A node token with neither has no agent
        to speak as, and may not speak as the owner.
        """
        principal = request.state.principal
        if req.tmux_pane is None and not (req.agent_id or "").strip():
            if principal.kind == "owner":
                return OWNER
            raise HTTPException(
                status_code=403,
                detail={"error": "a node must say which agent is acting", "hint": "send tmux_pane or agent_id"},
            )
        acting_node = _claimed_node(request, req.node)
        actor, _, why_not, _ = _resolve_caller(
            acting_node, req.tmux_pane, req.agent_id, req.pane_verified, req.pane_in_tree, req.harness
        )
        if actor is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "acting agent is not registered", "detail": why_not, "tmux_pane": req.tmux_pane},
            )
        return actor

    app.state.cleanup = _cleanup
    app.state.monitor_tick = _monitor_tick
    app.mount(
        "/static",
        StaticFiles(directory=PORTAL_STATIC_PATH),
        name="portal-static",
    )
    # Same dict the monitor loop mutates; exposed so tests can seed it.
    app.state.activity_registry = registry
    app.state.nodes = fleet

    @app.post("/register")
    def register(req: RegisterReq, request: Request):
        node = _claimed_node(request, req.node)
        pane, label, server = _pane_ref(req.tmux_pane, node)
        if server is None:
            raise HTTPException(status_code=404, detail={
                "error": f"pane {req.tmux_pane} does not resolve on node {node.name}; "
                         "register from the agent's live pane or supply its --pane explicitly"
            })
        flavor_hint = req.flavor or (tmux.infer_flavor(req.model) if req.model else None)
        existing_id = None
        session = req.agent_id or None
        if session:
            if db.is_retired(conn, agent_id=session):
                raise HTTPException(status_code=409, detail={"error": "this agent session has been retired"})
            existing_id = db.lookup_user_by_agent_id(conn, session)
            if existing_id is not None:
                # A node naming another machine's agent is refused outright.
                _own_row_or_403(request, existing_id)
            if existing_id and _live_elsewhere(existing_id, node.name, pane, server):
                # A copy of a live agent's session in another pane: this pane
                # is its own agent. It does not record the id, which would
                # replace the live agent's (one row per session id).
                log.warning("pane %s runs a copy of %s's live session %s; not taking its record",
                            pane, existing_id, session[:8])
                existing_id = None
                session = None
        if existing_id is None:
            existing_id = db.lookup_user_by_pane(conn, node.name, pane, server)
        if existing_id is None and server is not None and label and flavor_hint:
            existing_id = db.lookup_user_by_restored_label(
                conn, node.name, label, flavor_hint, server
            )

        if existing_id is not None:
            _own_row_or_403(request, existing_id)

        def _reservation_allows(handle: str | None) -> None:
            """A handle reserved for a named agent is that agent's alone.

            The registering agent has to say it is that one: leaving the id
            out does not make the handle anybody's, or a second agent on the
            same machine could take it.
            """
            row = db.get_recipient(conn, handle) if handle else None
            if row and row.get("reserved") and row.get("agent_id"):
                if session != row["agent_id"]:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "that handle is reserved for another agent",
                            "requested_user": handle,
                            "hint": f"register with --agent-id {row['agent_id']} to claim it",
                        },
                    )

        requested = None
        if req.requested_user is not None:
            try:
                requested = names.normalize_requested(req.requested_user)
            except names.InvalidName as e:
                raise HTTPException(
                    status_code=400,
                    detail={"error": str(e), "requested_user": req.requested_user},
                ) from e
            # A handle whose agent is offline can be reclaimed, so a restarted
            # agent gets its name and history back from a new pane; but only
            # on the machine it was on, unless the owner is doing it.
            if db.is_retired(conn, archive_id=requested):
                raise HTTPException(status_code=409, detail={"error": "this handle is a retired archive"})
            _own_row_or_403(request, requested)
            if (
                db.name_taken_by_other(
                    conn, requested, session, node.name, pane, server
                )
                and _is_alive(requested)
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "name already taken by another agent",
                        "requested_user": requested,
                    },
                )

        _reservation_allows(requested or existing_id)

        renamed_from = None
        if requested is not None:
            # Honor the request, moving an already-registered agent's history
            # over when it is asking for a different handle than it holds.
            if existing_id is not None and existing_id != requested:
                if db.get_recipient(conn, requested) is not None:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": f"this pane is registered as {existing_id}; "
                            f"unregister it before claiming {requested}",
                            "requested_user": requested,
                        },
                    )
                db.rename_recipient(conn, existing_id, requested)
                renamed_from = existing_id
            user_id = requested
        elif existing_id is not None:
            user_id = existing_id
        else:
            # A brand new registration has no stored flavor to fall back on,
            # so what the agent just told us is the whole picture.
            user_id = names.pick_unused(conn)
        # A re-register that omits both model and flavor must not downgrade a
        # known harness to 'generic': the write COALESCEs, but only over NULL,
        # so fall back to what is already stored before defaulting.
        current = db.get_recipient(conn, user_id)
        flavor = flavor_hint or (current["flavor"] if current else None) or tmux.infer_flavor(None)
        submit_key = req.submit_key or tmux.submit_key_for_flavor(flavor)
        db.register(
            conn,
            user_id,
            pane,
            session,
            req.model,
            flavor,
            req.instructions,
            req.message_prefix,
            submit_key,
            tmux_server=server,
            pane_label=label,
            # The node is wherever the pane was just resolved, so an agent that
            # re-registers from another machine moves with its handle.
            node=node.name,
        )
        # Whatever it was before, this row is a live registration now.
        db.clear_reservation(conn, user_id)
        node.tag_pane(nodes.new_op_id(), pane, server, user_id)
        _refresh_watch(node.name)
        registered = db.get_recipient(conn, user_id)
        peers = [r for r in _annotated_recipients() if r["user_id"] != user_id]
        return {
            "ok": True,
            "user_id": user_id,
            "tmux_pane": pane,
            "pane_label": label,
            "node": registered["node"] if registered else req.node,
            "agent_id": registered["agent_id"] if registered else session,
            "model": registered["model"] if registered else req.model,
            "flavor": registered["flavor"] if registered else flavor,
            "instructions": registered["instructions"] if registered else req.instructions,
            "message_prefix": registered["message_prefix"] if registered else req.message_prefix,
            "submit_key": (
                registered["submit_key"] if registered and registered["submit_key"] else tmux.DEFAULT_SUBMIT_KEY
            ),
            "assigned": requested is None,
            "requested_user": requested,
            "renamed_from": renamed_from,
            "owner_note": registered.get("owner_note") if registered else None,
            "protocol_brief": _protocol_brief(
                user_id, peers, registered.get("owner_note") if registered else None,
                on_team=bool(registered and registered.get("team_id") is not None),
            ),
        }

    def _node_or_422(name: str | None) -> nodes.Node:
        """The node a request says its pane is on; the server's own when unsaid."""
        node = fleet.get(name)
        if node is None:
            raise HTTPException(
                status_code=422,
                detail={"error": "unknown node", "node": name, "known": fleet.names()},
            )
        return node

    def _node_of(r: dict) -> nodes.Node | None:
        """The node holding a registered agent's pane, or None if unreachable."""
        return fleet.get(r.get("node"))

    def _try_snapshot(node: nodes.Node | None) -> nodes.PaneSnapshot | None:
        """A node's snapshot, or None when it is absent or cannot observe
        its tmux right now. None means nothing is known, not nothing there."""
        if node is None:
            return None
        try:
            return node.snapshot()
        except nodes.Unavailable as e:
            log.warning("node %s could not be observed: %s", node.name, e)
            return None

    def _pane_ref(target: str, node: nodes.Node) -> tuple[str, str, str | None]:
        """(pane id, session:window.pane label, tmux server) for a pane target.

        Clients send either form; both are resolved to the pane's id now, while
        the positional one still means what the client meant. Without tmux the
        target is kept as given, tied to no server.
        """
        try:
            resolved = node.resolve(target)
        except nodes.Unavailable as e:
            raise HTTPException(status_code=503, detail={"error": str(e), "retry": True}) from e
        if resolved is None:
            return target, target, None
        # The server id travels with the pane from the node's own look, never
        # from an observation cached earlier.
        return resolved.pane, resolved.label, resolved.tmux_server

    def _offline(
        r: dict, node: nodes.Node | None, snap: nodes.PaneSnapshot | None
    ) -> str | None:
        if r.get("reserved"):
            # A handle held for an agent that was imported from another hub.
            return ("recipient offline: imported from another hub; it has not "
                    "registered here yet")
        if node is None:
            return f"recipient offline: node {r['node']} is not connected"
        if snap is None:
            return f"recipient offline: node {r['node']} cannot observe its tmux right now"
        return tmux.offline_reason(
            r["tmux_pane"], snap.existing, snap.live, stale=_stale(r, snap.server)
        )

    def _stale(r: dict, server: str | None) -> str | None:
        """Why a row's pane id no longer identifies its pane, or None."""
        if server is None:
            return None  # no tmux to compare against
        bound = r.get("tmux_server")
        if bound == db.UNBOUND:
            return "its pane could not be verified when pane ids were introduced"
        if bound is not None and bound != server:
            return "its pane is from an earlier tmux session"
        if bound is None and r["tmux_pane"].startswith("%"):
            return "its pane id was never tied to a tmux session"
        return None

    def _annotated_recipients() -> list[dict]:
        rows = db.list_recipients(conn)
        held = {name: fleet.get(name) for name in {r["node"] for r in rows}}
        snaps = {name: _try_snapshot(node) for name, node in held.items()}
        for r in rows:
            snap = snaps[r["node"]]
            # Only an observed node can confirm a pane is gone or a shell.
            r["observed"] = snap is not None
            r["offline_reason"] = _offline(r, held[r["node"]], snap)
            r["alive"] = r["offline_reason"] is None
            # Show where the pane is right now; fall back to where it last was.
            if r["alive"] and snap.label(r["tmux_pane"]):
                r["pane_label"] = snap.label(r["tmux_pane"])
            r["pane_label"] = r.get("pane_label") or r["tmux_pane"]
        return rows

    def _is_alive(user_id: str) -> bool:
        return any(r["user_id"] == user_id and r["alive"] for r in _annotated_recipients())

    def _live_elsewhere(user_id: str, node_name: str, pane: str, server: str | None) -> bool:
        """True when `user_id` is registered on another pane that is still live.

        A session id is then not proof of identity: `claude --resume` or
        `--continue` in a second pane runs a live agent's session there too,
        and the copy must not take that agent's record.
        """
        row = db.get_recipient(conn, user_id) or {}
        here = (node_name, pane, server)
        if (row.get("node"), row.get("tmux_pane"), row.get("tmux_server")) == here:
            return False
        return _is_alive(user_id)

    def _reach(
        sender: str, recipient: dict, context, content, files: list[str] | None = None
    ) -> nodes.Node:
        """The node to deliver through, or a 409 recording why not.

        The node object is returned rather than looked up again afterwards,
        so the delivery goes to the connection that was just checked.
        """
        node = _node_of(recipient)
        reason = _offline(recipient, node, _try_snapshot(node))
        if reason is None:
            return node
        mid = db.record_message(
            conn, sender, recipient["user_id"], context, content,
            status="failed", delivery_error=reason, attachments=files,
        )
        raise HTTPException(
            status_code=409,
            detail={"error": reason, "recipient": recipient["user_id"], "message_id": mid},
        )

    @app.get("/recipients")
    def recipients(include_retired_sessions: bool = False):
        result = {"recipients": _annotated_recipients()}
        if include_retired_sessions:
            result["retired_sessions"] = [r["agent_id"] for r in db.retired_agents(conn) if r["agent_id"]]
        return result

    @app.get("/whoami")
    def whoami(
        request: Request,
        tmux_pane: str | None = None,
        node: str | None = None,
        agent_id: str | None = None,
        pane_verified: bool | None = None,
        pane_in_tree: bool | None = None,
        harness: str | None = None,
    ):
        """Which agent, if any, the caller is: by its harness session id when
        it sends one, else by its pane (see _resolve_caller).

        The pane is resolved on its own node and matched with that node's
        tmux server, so the same pane id on another machine, or from an
        earlier tmux, is never mistaken for this one.
        """
        owner_node = _claimed_node(request, node)
        user_id, how, why_not, (pane, label) = _resolve_caller(
            owner_node, tmux_pane, agent_id, pane_verified, pane_in_tree, harness
        )
        return {
            "user_id": user_id, "node": owner_node.name,
            "tmux_pane": pane, "pane_label": label,
            "identified_by": how if user_id else None, "detail": why_not,
            "owner_note": (db.get_recipient(conn, user_id) or {}).get("owner_note") if user_id else None,
        }

    @app.post("/recipients/prune")
    def prune_recipients(req: PruneReq, _: None = Depends(_require_owner)):
        """Drop registrations that can't come back on their own.

        By default only panes that no longer exist are removed: a pane that
        still exists but runs a bare shell keeps its registration, so an agent
        restarted in that pane gets the same identity back.
        """
        removed, kept_offline = [], []
        for r in _annotated_recipients():
            if r["alive"]:
                continue
            # A reservation has no pane to lose; it is dropped by name, with
            # unregister, not swept up here.
            if r.get("reserved"):
                kept_offline.append(r["user_id"])
                continue
            # Unobserved is not gone: only a node that answered can confirm
            # a pane is missing, so an agent on a node that is disconnected
            # or could not read its tmux is always kept.
            if not r["observed"]:
                kept_offline.append(r["user_id"])
                continue
            gone = "no longer exists" in r["offline_reason"]
            if gone or req.include_shells:
                db.delete_recipient(conn, r["user_id"])
                removed.append(r["user_id"])
                _refresh_watch(r["node"])
            else:
                kept_offline.append(r["user_id"])
        return {"ok": True, "removed": removed, "kept_offline": kept_offline}

    @app.post("/recipients/retire")
    def retire_recipients(req: RetireReq, _: None = Depends(_require_owner)):
        """Archive stopped agents. The bulk action never stops a running pane."""
        retired, live, unknown, failures = [], [], [], {}
        for user_id in dict.fromkeys(req.user_ids):
            try:
                _retire(user_id, stop_live=False)
            except HTTPException as exc:
                if exc.status_code == 404:
                    unknown.append(user_id)
                elif exc.detail.get("live"):
                    live.append(user_id)
                else:
                    failures[user_id] = exc.detail["error"]
            else:
                retired.append(user_id)
        return {"ok": True, "retired": retired, "kept_live": live, "unknown": unknown,
                "failures": failures}

    @app.delete("/recipients/{user_id}")
    def unregister(user_id: str, request: Request):
        row = _own_row_or_403(request, user_id)
        if not db.delete_recipient(conn, user_id):
            raise HTTPException(status_code=404, detail="recipient not registered")
        if row:
            _refresh_watch(row["node"])
        return {"ok": True, "user_id": user_id}

    def _reply_original(reply_to: int | None) -> dict | None:
        if reply_to is None:
            return None
        original = db.get_message(conn, reply_to)
        if original is None:
            raise HTTPException(status_code=422, detail={"error": f"no message {reply_to}"})
        return original

    def _queen_target(spec: str) -> tuple[str, dict | None]:
        """Resolve a `queen:<team>` recipient to the team's current queen.

        <team> is a team id or a name, case-insensitive. Any other recipient
        passes through unchanged. Nothing is stored for a team that cannot be
        resolved: there is no agent to attach the message to.
        """
        if not spec.lower().startswith("queen:"):
            return spec, None
        team = _find_team(spec[len("queen:"):].strip())
        if not team["queen"]:
            raise HTTPException(status_code=409, detail={
                "error": "team has no queen", "team": team["name"], "team_id": team["id"]})
        return team["queen"], {"id": team["id"], "name": team["name"]}

    def _find_team(ref: str) -> dict:
        """A team by name (case-insensitive) or id; 404 or 409 otherwise."""
        teams = db.list_teams(conn)
        named = [t for t in teams if t["name"].casefold() == ref.casefold()]
        found = [t for t in teams if str(t["id"]) == ref.lstrip("0")] or named
        if not found:
            raise HTTPException(status_code=404, detail={
                "error": "no such team", "team": ref,
                "detail": "give a team name or id; `GET /teams` lists them"})
        if len(found) > 1:
            raise HTTPException(status_code=409, detail={
                "error": "team name is ambiguous", "team": ref,
                "detail": "use the team id: " + ", ".join(f"{t['id']} ({t['name']})" for t in found)})
        return found[0]

    def _deliver_as(
        sender: str,
        recipient_id: str,
        content: str,
        context: str | None,
        files: list[str] | None = None,
        client_id: str | None = None,
        reply_original: dict | None = None,
    ):
        """Deliver a message in `sender`'s name to an agent's pane.

        The owner's dashboard sends as `owner`; a task assigned by an agent
        arrives from that agent, so a node token can never sign as the human.
        """
        files = files or []
        recipient = db.get_recipient(conn, recipient_id)
        if recipient is None:
            _missing_recipient(sender, recipient_id, context, content, files,
                               reply_original["id"] if reply_original else None)
        node = _reach(sender, recipient, context, content, files)
        mid, status, err = _dispatch(node, sender, recipient, context, content, files, client_id, reply_original)
        return {
            "ok": status == "delivered", "status": status,
            "message_id": mid, "delivery_error": err,
        }

    def _missing_recipient(sender, recipient, context, content, files=None, reply_to=None):
        detail = {"error": "recipient not registered", "recipient": recipient}
        # A stale address must not create history on a name we just freed.
        if not db.was_retired(conn, recipient) and not db.is_retired(conn, archive_id=recipient):
            detail["message_id"] = db.record_message(
                conn, sender, recipient, context, content, status="failed",
                delivery_error=detail["error"], attachments=files, reply_to=reply_to,
            )
        raise HTTPException(status_code=404, detail=detail)

    # Node result -> message status.
    MESSAGE_STATUS = {"ok": "delivered", "failed": "failed", "unknown": "unknown"}

    def _replayed(m: dict) -> tuple[int, str, str | None]:
        """An earlier attempt's (id, status, error), for a repeated client id."""
        if m["status"] == "pending":
            return m["id"], "unknown", "an earlier attempt of this message is still being delivered"
        return m["id"], m["status"], m.get("delivery_error")
    OWNER_REPLY_IDLE_SECONDS = 25 * 60

    board_delivery_locks = weakref.WeakValueDictionary()
    board_delivery_lock = threading.Lock()

    def _board_lock(user_id):
        with board_delivery_lock:
            lock = board_delivery_locks.get(user_id)
            if lock is None:
                lock = threading.Lock()
                board_delivery_locks[user_id] = lock
            return lock

    def _dispatch(
        node: nodes.Node,
        sender: str,
        recipient: dict,
        context: str | None,
        content: str,
        files: list[str] | None = None,
        client_id: str | None = None,
        reply_original: dict | None = None,
    ) -> tuple[int, str, str | None]:
        """Record a message, then paste it into the recipient's pane.

        The row exists before the paste, with the message id as the
        operation id, so a result that never comes back leaves a message
        marked unknown rather than a paste with no record. Unknown is never
        retried here: the agent may already have it. Nor is a client id seen
        before: that request's outcome is returned without a second paste.
        """
        reply_note = ""
        if reply_original:
            snippet = " ".join(reply_original["content"].split()) or "(files)"
            snippet = snippet[:60] + ("…" if len(snippet) > 60 else "")
            reply_note = (f'(in reply to message {reply_original["id"]} from {reply_original["sender"]}: "{snippet}"; '
                          f'buzz messages --id {reply_original["id"]} shows all of it)\n\n')
        files = files or []
        try:
            mid = db.record_message(
                conn, sender, recipient["user_id"], context, content,
                status="pending", attachments=files, client_id=client_id, reply_to=reply_original["id"] if reply_original else None,
            )
        except db.DuplicateMessage as dup:
            return _replayed(dup.existing)
        # Attachment names travel as names; the node renders them as paths on
        # the machine the pane is on, fetching them from the hub if remote.
        reminder = sender == OWNER and db.owner_reply_reminder_due(
            conn, recipient["user_id"], since=recipient["registered_at"],
            now=time.time(), idle_seconds=OWNER_REPLY_IDLE_SECONDS,
        )
        if err := _blocking_prompt_error(node, recipient):
            db.set_message_status(conn, mid, "failed", err)
            return mid, "failed", err
        user_id, team_id = recipient["user_id"], recipient.get("team_id")
        lock = _board_lock(user_id) if team_id is not None else contextlib.nullcontext()
        with lock:
            hint = None
            if team_id is not None:
                try:
                    hint = boards.hint(conn, team_id, user_id)
                except sqlite3.Error:
                    log.exception("could not read board hint for %s", user_id)
            suffix = "\n\n" + hint[1] if hint else ""
            body = tmux.format_message(sender, context, reply_note + content + suffix,
                                       owner_reply_reminder=reminder)
            try:
                result = node.deliver(
                    str(mid),
                    recipient["tmux_pane"],
                    recipient.get("tmux_server"),
                    body,
                    attachments=files,
                    message_prefix=recipient.get("message_prefix"),
                    submit_key=recipient.get("submit_key") or tmux.DEFAULT_SUBMIT_KEY,
                    flavor=recipient.get("flavor"),
                )
            except Exception as e:  # noqa: BLE001 - anything at all after dispatch is unknown
                log.exception("delivery of message %d to %s raised", mid, recipient["user_id"])
                result = nodes.Result("unknown", f"{type(e).__name__}: {e}")
            status = MESSAGE_STATUS[result.status]
            db.set_message_status(conn, mid, status, result.error)
            # An unknown paste may already be visible. Avoid a duplicate
            # footer on the next message; a definite failure can try again.
            if hint and result.status in {"ok", "unknown"}:
                try:
                    boards.mark_hint(conn, team_id, user_id, hint[0])
                except sqlite3.Error:
                    log.exception("could not record board hint for %s", user_id)
        return mid, status, result.error

    def _blocking_prompt_error(node: nodes.Node, recipient: dict) -> str | None:
        """Error message if the recipient's pane shows a modal prompt, or None.

        The Enter that submits a message would accept the prompt's default
        (No, exit on Claude's trust prompt; a model downgrade on Codex's
        rate-limit / Luna Reserve modals). Unknown screens count as no prompt:
        delivery then reports its own errors. A remote agent's screen is the
        node's latest observation, a few seconds old.
        """
        try:
            screen = node.screen(recipient["tmux_pane"], recipient.get("tmux_server"))
        except Exception:  # noqa: BLE001 - the delivery that follows reports a broken node
            return None
        if not screen:
            return None
        if trust := activity.trust_prompt(screen):
            return (f"not delivered: {recipient['user_id']} is waiting at {trust}. Answer it in its "
                    "pane first; a pasted message would answer it, and Claude's default there is No, exit.")
        if downgrade := activity.downgrade_prompt(screen):
            return (f"not delivered: {recipient['user_id']} is waiting at {downgrade}. Answer it in its "
                    "pane first; a pasted message would accept the model downgrade.")
        return None

    @app.post("/notify")
    def notify(req: NotifyReq, request: Request):
        node = _claimed_node(request, req.node)
        sender = _caller(node, req.tmux_pane, req.agent_id, req.pane_verified, req.pane_in_tree, req.harness)
        if not req.content.strip() or "\0" in req.content:
            raise HTTPException(status_code=422, detail="notification text must be nonempty and contain no NUL characters")
        try:
            mid = db.record_notification(conn, sender, req.content, req.context)
        except notifications.NotificationLimit as exc:
            raise HTTPException(status_code=429, detail=str(exc),
                                headers={"Retry-After": str(exc.retry_after)}) from exc
        return {"ok": True, "status": "delivered", "message_id": mid}

    @app.post("/send")
    def send(req: SendReq, request: Request):
        node = _claimed_node(request, req.node)
        sender = _caller(node, req.tmux_pane, req.agent_id, req.pane_verified, req.pane_in_tree, req.harness)
        original = _reply_original(req.reply_to)
        target, via_team = _queen_target(req.recipient)
        req = req.model_copy(update={"recipient": target})
        if req.recipient == OWNER:
            # Messages to the human are recorded for the dashboard, not
            # injected into a pane.
            mid = db.record_message(
                conn, sender, OWNER, req.context, req.content, status="delivered", reply_to=req.reply_to
            )
            return {"ok": True, "status": "delivered", "message_id": mid,
                    "delivered_to_pane": None, "delivery_error": None}
        recipient = db.get_recipient(conn, req.recipient)
        if recipient is None:
            _missing_recipient(sender, req.recipient, req.context, req.content, reply_to=req.reply_to)
        node = _reach(sender, recipient, req.context, req.content)
        mid, status, err = _dispatch(node, sender, recipient, req.context, req.content, reply_original=original)
        return {
            "ok": status == "delivered",
            "status": status,
            "message_id": mid,
            "delivered_to_pane": recipient["tmux_pane"],
            "delivery_error": err,
            **({"recipient": target, "team": via_team} if via_team else {}),
        }

    @app.put("/agents/{user_id}/owner-note")
    def owner_note(user_id: str, req: OwnerNoteReq, _: None = Depends(_require_owner)):
        recipient = db.set_owner_note(conn, user_id, " ".join(req.text.split()))
        if recipient is None:
            raise HTTPException(status_code=404, detail={"error": "unknown agent"})
        return {"ok": True, "owner_note": recipient["owner_note"]}

    @app.post("/status")
    def set_status(req: StatusReq, request: Request):
        """An agent says, in a line, what it is working on."""
        node = _claimed_node(request, req.node)
        user_id = _caller(node, req.tmux_pane, req.agent_id, req.pane_verified, req.pane_in_tree, req.harness)
        text = " ".join(req.text.split())
        if not text:
            raise HTTPException(status_code=422, detail={"error": "status is empty"})
        db.record_summary(conn, user_id, text, "agent")
        return {"ok": True, "user_id": user_id, "status": text}

    @app.get("/messages")
    def messages(user: str | None = None, limit: int = 50, id: int | None = None):
        if id is not None:
            # One message by id, e.g. the one an owner reply points at.
            found = db.get_message(conn, id)
            if found is None:
                raise HTTPException(status_code=404, detail={"error": f"no message {id}"})
            return {"messages": [found]}
        return _read_json({"messages": db.fetch_messages(conn, user, limit)})

    @app.get("/api/chats")
    def owner_chats(q: str = Query("", max_length=1000), queens: bool = False,
                    _: None = Depends(_require_owner)):
        """One row per owner conversation; `queens` keeps current team queens."""
        agents = None
        if queens:
            agents = sorted({t["queen"] for t in db.list_teams(conn) if t.get("queen")})
        return _read_json({"chats": db.owner_chats(conn, q, agents)})

    @app.get("/api/agents/{user_id}/messages")
    def agent_messages(user_id: str, limit: int = Query(300, ge=1, le=500),
                       before: int | None = Query(None, ge=1),
                       after: int | None = Query(None, ge=0),
                       around: int | None = Query(None, ge=1),
                       _: None = Depends(_require_owner)):
        if sum(option is not None for option in (before, after, around)) > 1:
            raise HTTPException(status_code=422, detail="Use only one of before, after or around")
        return _read_json(db.agent_messages_page(conn, user_id, limit, before, after, around))

    @app.post("/api/messages/{message_id}/pin")
    def pin_message(message_id: int, req: PinReq, _: None = Depends(_require_owner)):
        if not db.set_pinned(conn, message_id, req.pinned):
            raise HTTPException(status_code=404, detail={"error": f"no message {message_id}"})
        return {"ok": True, "pins": db.list_pins(conn)}

    @app.get("/api/agents/{user_id}/messages/count")
    def agent_messages_count(user_id: str, after: int = Query(..., ge=0), before: int = Query(..., ge=1),
                             _: None = Depends(_require_owner)):
        if before <= after:
            raise HTTPException(status_code=422, detail="before must be greater than after")
        return {"count": db.count_agent_messages_between(conn, user_id, after, before)}

    @app.get("/api/agents/{user_id}/messages/search")
    def search_agent_messages(user_id: str, q: str = Query("", max_length=1000),
                              limit: int = Query(100, ge=1, le=500),
                              offset: int = Query(0, ge=0),
                              _: None = Depends(_require_owner)):
        return db.search_agent_messages(conn, user_id, q, limit, offset)

    @app.post("/owner/send")
    def owner_send(req: OwnerSendReq, _: None = Depends(_require_owner)):
        content = req.content.strip()
        if not content and not req.attachments:
            raise HTTPException(
                status_code=422, detail={"error": "message needs text or an image"}
            )
        unknown = [
            name for name in req.attachments
            if attachments.resolve(attachments_root, name) is None
        ]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail={"error": "unknown attachment", "attachments": unknown},
            )
        if req.client_id and (earlier := db.message_by_client_id(conn, OWNER, req.client_id)):
            # A retry after a lost answer: report the first attempt, even if
            # the recipient has gone offline since.
            mid, status, err = _replayed(earlier)
            return {"ok": status == "delivered", "status": status,
                    "message_id": mid, "delivery_error": err}
        return _deliver_as(OWNER, req.recipient, content, req.context, req.attachments, req.client_id, _reply_original(req.reply_to))

    @app.post("/attachments")
    async def attachments_upload(request: Request, _: None = Depends(_require_owner)):
        """Store raw file bytes; raster images are inline, other files download."""
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > attachments.MAX_BYTES:
            raise HTTPException(status_code=413, detail={"error": "file too large"})
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > attachments.MAX_BYTES:
                raise HTTPException(status_code=413, detail={"error": "file too large"})
        from urllib.parse import unquote
        filename = unquote(request.headers.get("x-attachment-filename", "")) or None
        try:
            name = await asyncio.to_thread(attachments.save, attachments_root, bytes(data), filename)
        except ValueError as exc:
            status = 413 if len(data) > attachments.MAX_BYTES else 415
            raise HTTPException(status_code=status, detail={"error": str(exc)})
        return {
            "ok": True,
            "name": name,
            "url": f"/attachments/{name}",
            "path": str(attachments_root / name),
        }

    @app.get("/attachments/{name}")
    def attachments_get(name: str):
        path = attachments.resolve(attachments_root, name)
        if path is None:
            raise HTTPException(status_code=404, detail={"error": "unknown attachment"})
        return FileResponse(
            path,
            media_type=attachments.media_type(name),
            filename=None if attachments.is_image(name) else attachments.download_name(name),
            headers={
                "Cache-Control": "private, max-age=31536000, immutable",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/teams/{team_ref}/tasks")
    def team_tasks(team_ref: str):
        """The team's work: tasks held by any member, and tasks assigned to the team."""
        team = _find_team(team_ref)
        tasks = team_view.team_tasks(team, db.list_tasks(conn))
        return {"team": {"id": team["id"], "name": team["name"], "queen": team["queen"]}, "tasks": tasks}

    def _board_summary_for(request, caller, team_id):
        try:
            actor = _actor(request, caller)
            return boards.summary(conn, team_id, actor)
        except (HTTPException, boards.BoardError):
            return None

    @app.get("/teams/{team_ref}/view")
    def team_view_get(team_ref: str, request: Request, caller: ActorFields = Depends(),
                      stale_hours: float = team_view.STALE_HOURS, since: float | None = None):
        """The team for its queen: each member's state, status line and open
        tasks; each open task's dependencies and whether it can move; and flags
        (free members, tasks on offline or sleep-prone machines, stale work).
        `since` (epoch seconds) keeps only members and tasks that changed after it."""
        team = _find_team(team_ref)
        members = team["members"]
        view = team_view.build(
            time.time(), team, _recipients_with_activity(), db.list_tasks(conn),
            db.last_sent(conn, members, team["queen"]) if team["queen"] else {},
            db.last_sent(conn, members), fleet.local.name, stale_hours, since,
        )
        if (stats := _board_summary_for(request, caller, team["id"])) is not None:
            view["board"] = stats
            view["text"] += "\n" + boards.summary_line(stats)
        return view


    def _board_team_id(ref: str, actor: str) -> int:
        if ref.isascii() and ref.isdecimal():
            digits = ref.lstrip("0")
            if digits and len(digits) <= 19 and int(digits) < 2**63:
                return int(digits)
            raise HTTPException(status_code=404, detail={"error": "no such board"})
        try:
            return _find_team(ref)["id"]
        except HTTPException as exc:
            if exc.status_code != 404 and actor == OWNER:
                raise
            raise HTTPException(status_code=404, detail={"error": "no such board"}) from exc

    def _board_call(fn, *args, **kwargs):
        try:
            return fn(conn, *args, **kwargs)
        except boards.BoardError as exc:
            raise HTTPException(status_code=exc.status, detail={"error": exc.error}) from exc

    @app.post("/teams/{team}/board", status_code=201)
    def board_post(team: str, req: BoardPostReq, request: Request):
        actor = _actor(request, req)
        result, created = _board_call(
            boards.post, _board_team_id(team, actor), actor,
            body=req.body, subject=req.subject, reply_to=req.reply_to, client_id=req.client_id,
        )
        return JSONResponse(result, status_code=201 if created else 200)

    @app.get("/teams/{team}/board")
    def board_page(
        team: str, request: Request, caller: ActorFields = Depends(),
        after: int | None = Query(None, ge=0, le=2**63 - 1),
        before: int | None = Query(None, ge=0, le=2**63 - 1),
        unread: bool = False, mark: bool = False,
        thread: int | None = Query(None, gt=0, le=2**63 - 1),
        limit: int = Query(20, ge=1, le=50),
    ):
        """List previews. With mark=1, unread counts what remains after this page."""
        actor = _actor(request, caller)
        if sum((after is not None, before is not None, unread)) > 1:
            raise HTTPException(status_code=422, detail={"error": "use one of after, before, or unread"})
        return _read_json(_board_call(
            boards.page, _board_team_id(team, actor), actor,
            after=after, before=before, unread=unread, thread=thread, limit=limit, mark=mark,
        ))

    @app.get("/teams/{team}/board/{post_id}")
    def board_detail(team: str, post_id: int, request: Request, caller: ActorFields = Depends()):
        actor = _actor(request, caller)
        if not 0 < post_id < 2**63:
            raise HTTPException(status_code=404, detail={"error": "no such board post"})
        return _read_json(_board_call(boards.detail, _board_team_id(team, actor), actor, post_id))

    @app.get("/api/spawn-options")
    def spawn_options(_: None = Depends(_require_owner)):
        return {"harnesses": tmux.spawn_options()}

    @app.post("/agents/spawn")
    def agents_spawn(req: SpawnReq, _: None = Depends(_require_owner)):
        command = tmux.spawn_launch_command(req.flavor, req.model)
        # Only record the model when it is one that actually launched.
        spec = tmux.HARNESS_SPAWN.get(req.flavor)
        model = req.model if (spec and req.model in spec.models) else None
        node = _node_or_422(req.node)
        dirs = node.spawn_dirs
        if req.cwd is not None and req.cwd not in dirs:
            raise HTTPException(
                status_code=422,
                detail={"error": f"{req.cwd} is not a start folder on {node.name}", "spawn_dirs": dirs},
            )
        cwd = req.cwd or (dirs[0] if dirs else None)
        spawned = node.spawn(nodes.new_op_id(), command, cwd)
        if spawned.pane is None:
            # Unknown with no pane: nothing to register, and a retry could
            # leave a second window behind, so the caller decides.
            raise _node_failure("could not create tmux window", spawned)
        pane = spawned.pane
        user_id = names.pick_unused(conn)
        label, server = spawned.label or pane, spawned.tmux_server
        db.register(
            conn,
            user_id,
            pane,
            None,
            model,
            req.flavor,
            None,
            None,
            tmux.submit_key_for_flavor(req.flavor),
            tmux_server=server,
            pane_label=label,
            node=node.name,
        )
        node.tag_pane(nodes.new_op_id(), pane, server, user_id)
        node.rename_window(nodes.new_op_id(), pane, server, user_id)
        _refresh_watch(node.name)
        return {
            "ok": True, "user_id": user_id, "tmux_pane": pane, "pane_label": label,
            "node": node.name,
            # "unknown": the window exists and is registered, but whether the
            # harness launched in it did not report back.
            "launch": "ok" if spawned.ok else spawned.status,
            "launch_error": spawned.error,
            "flavor": req.flavor, "model": model, "command": command, "cwd": cwd,
        }

    @app.post("/agents/{user_id}/restart")
    def agents_restart(user_id: str, req: RestartReq, request: Request):
        row = _own_row_or_403(request, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail={"error": "unknown agent"})
        node = _node_of(row)
        snap = _try_snapshot(node)

        def skipped(reason: str, forceable_activity: str | None = None):
            result = {"ok": True, "status": "skipped", "user_id": user_id, "reason": reason}
            if forceable_activity is not None:
                result.update(forceable=True, activity=forceable_activity)
            return result

        if node is None or snap is None:
            return skipped(f"cannot observe tmux on node {row['node']}")
        if row.get("reserved") or not snap.server or _stale(row, snap.server):
            return skipped("its pane is not verified on the current tmux server")
        pane = row["tmux_pane"]
        observed = snap.table.get(pane)
        layout = [{**observed, "pane_id": pane}] if observed and observed.get("command") else []
        item = restart.plan(
            [{**row, "activity": registry.get(user_id)}], layout, node.name, snap.server,
            handles=[user_id], force=req.force,
        )[0]
        if item.skip:
            return skipped(item.skip, item.forceable_activity)
        if req.dry_run:
            return {"ok": True, "status": "planned", "user_id": user_id,
                    "node": node.name, "pane": pane, "launch": item.launch}

        identity = ("node", "tmux_pane", "tmux_server", "agent_id")

        def same_agent(current):
            return current is not None and all(current[key] == row[key] for key in identity)

        with restart_lock:
            current = db.get_recipient(conn, user_id)
            if user_id in restarting:
                return skipped("a restart is already in progress")
            if not same_agent(current) or current["registered_at"] != row["registered_at"]:
                return skipped("its registration changed while planning; try again")
            restarting.add(user_id)
        try:
            result = node.respawn(nodes.new_op_id(), pane, snap.server, item.cwd, item.command)
            if not result.ok:
                return {"ok": False, "status": result.status, "user_id": user_id, "reason": result.error}
            registry.pop(user_id, None)
            deadline = time.monotonic() + RESTART_WAIT
            while True:
                current = db.get_recipient(conn, user_id)
                if not same_agent(current):
                    return {"ok": False, "status": "unknown", "user_id": user_id,
                            "reason": "the agent's registration changed identity after respawn"}
                if current["registered_at"] > row["registered_at"]:
                    return {"ok": True, "status": "restarted", "user_id": user_id,
                            "node": node.name, "pane": pane}
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.25)
            prompt = _blocking_prompt_error(node, row)
            return {"ok": False, "status": "blocked" if prompt else "unknown", "user_id": user_id,
                    "reason": prompt or f"pane respawned but the session did not re-register within {RESTART_WAIT:g}s"}
        finally:
            with restart_lock:
                restarting.remove(user_id)

    @app.post("/agents/{user_id}/resume")
    def agents_resume(user_id: str, _: None = Depends(_require_owner)):
        """Start a stopped agent's own session again in a new window, in the
        folder it last ran in, on its own machine. It keeps its handle,
        conversation, tasks and history. Its old pane is left alone."""
        recipient = _agent_or_404(user_id)
        if not recipient.get("agent_id") or not recipient.get("flavor"):
            raise HTTPException(status_code=409, detail={"error": f"{user_id} has no saved session to resume"})
        node = _node_of(recipient)
        if node is None:
            raise HTTPException(status_code=409, detail={"error": f"node {recipient['node']} is not connected"})
        snap = _try_snapshot(node)
        if snap is None:
            raise HTTPException(
                status_code=409, detail={"error": f"node {recipient['node']} cannot be observed right now"}
            )
        if _stale(recipient, snap.server) is None and recipient["tmux_pane"] in snap.live:
            raise HTTPException(status_code=409, detail={"error": f"{user_id} is already running"})
        cwd = recipient.get("cwd")
        if not cwd and node is fleet.local:
            place = restore.saved_place(restore.SNAPSHOT_DIR, recipient["agent_id"])
            cwd = place[2]["cwd"] if place else None
        if not cwd:
            raise HTTPException(
                status_code=409, detail={"error": f"the hub does not know which folder {user_id} ran in"}
            )
        command = restore.resume_command(recipient)
        if command is None:
            raise HTTPException(status_code=409, detail={"error": f"no resume command for {recipient['flavor']}"})
        spawned = node.spawn(nodes.new_op_id(), command, cwd, resume=True)
        if spawned.pane is None:
            raise _node_failure("could not create tmux window", spawned)
        pane, label, server = spawned.pane, spawned.label or spawned.pane, spawned.tmux_server
        # Bound to the new pane now, so the harness's own registration from
        # there finds this handle by its session id.
        db.register(conn, user_id, pane, tmux_server=server, pane_label=label, node=node.name)
        node.tag_pane(nodes.new_op_id(), pane, server, user_id)
        node.rename_window(nodes.new_op_id(), pane, server, user_id)
        _refresh_watch(node.name)
        return {
            "ok": True, "user_id": user_id, "tmux_pane": pane, "pane_label": label, "node": node.name,
            "launch": "ok" if spawned.ok else spawned.status, "launch_error": spawned.error,
            "command": command, "cwd": cwd,
        }

    @app.post("/agents/{user_id}/stop")
    def agents_stop(user_id: str, _: None = Depends(_require_owner)):
        recipient = _agent_or_404(user_id)
        return _stop_agent(recipient)

    def _stop_agent(recipient: dict, *, stop_live: bool = True) -> dict:
        user_id = recipient["user_id"]
        pane = recipient["tmux_pane"]
        node = _node_of(recipient)
        if node is None:
            raise HTTPException(
                status_code=409,
                detail={"error": f"node {recipient['node']} is not connected"},
            )
        snap = _try_snapshot(node)
        if snap is None:
            raise HTTPException(
                status_code=409,
                detail={"error": f"node {recipient['node']} cannot be observed right now"},
            )
        # A pane that is gone, or that only holds a bare shell, has no agent
        # to stop; leave the shell (and the registration) alone.
        if _stale(recipient, snap.server) or pane not in snap.live:
            return {
                "ok": True, "user_id": user_id, "tmux_pane": pane,
                "already_stopped": True,
            }
        if not stop_live:
            raise HTTPException(status_code=409, detail={"error": "agent is still running", "live": True})
        killed = node.kill(nodes.new_op_id(), pane, recipient.get("tmux_server"))
        if not killed.ok:
            raise _node_failure("could not stop tmux pane", killed)
        return {
            "ok": True, "user_id": user_id, "tmux_pane": pane,
            "already_stopped": False,
        }

    def _retire(user_id: str, *, stop_live: bool) -> dict:
        with retirement_lock:
            recipient = _agent_or_404(user_id)
            stopped = _stop_agent(recipient, stop_live=stop_live)
            archived = db.retire_recipient(conn, recipient)
            if archived is None:
                raise HTTPException(status_code=409, detail={"error": "registration changed during retirement"})
            registry.pop(user_id, None)
            _refresh_watch(recipient["node"])
            return {**stopped, **archived}

    @app.post("/agents/{user_id}/retire")
    def agents_retire(user_id: str, _: None = Depends(_require_owner)):
        return _retire(user_id, stop_live=True)

    @app.post("/agents/{user_id}/switch")
    def agents_switch(user_id: str, req: SwitchReq, _: None = Depends(_require_owner)):
        """Move an agent to another harness in its own pane, keeping its conversation.

        Reads the source harness's transcript, writes a new resumable session in
        the target's format, respawns the pane and launches the target harness
        on that session. The source transcript is only read. Experimental: the
        hub does this for agents on its own machine, where the pane and the
        transcripts are.
        """
        row = _agent_or_404(user_id)
        node = _node_of(row)
        if node is None:
            raise HTTPException(status_code=409, detail={"error": f"node {row['node']} is not connected"})
        if node is not fleet.local:
            raise HTTPException(status_code=409, detail={
                "error": f"{user_id} runs on {node.name}; switching needs the pane and the harness "
                         f"transcripts, which are on that machine. Run it there."})
        snap = _try_snapshot(node)
        if snap is None:
            raise HTTPException(status_code=409, detail={"error": f"{node.name} cannot be observed right now"})
        if _stale(row, snap.server) or row["tmux_pane"] not in snap.live:
            raise HTTPException(status_code=409, detail={
                "error": f"{user_id} is not running; `buzz resume {user_id}` starts it again"})
        cwd = row.get("cwd")
        if not cwd:
            place = restore.saved_place(restore.SNAPSHOT_DIR, row.get("agent_id") or "")
            cwd = place[2]["cwd"] if place else None
        item = handoff.plan({**row, "cwd": cwd}, req.to, req.model,
                            max_chars=req.max_chars, force=req.force)
        if item.skip:
            raise HTTPException(status_code=409, detail={"error": item.skip, "plan": item.describe()})
        if req.dry_run:
            return {"ok": True, "applied": False, "plan": item.describe()}
        error = handoff.apply(item)
        if error:
            raise HTTPException(status_code=502, detail={"error": error, "plan": item.describe()})
        spec = tmux.HARNESS_SPAWN.get(req.to)
        model = req.model if (spec and req.model in spec.models) else None
        # A seeded session (codex, agy) gets its id from the harness when it
        # starts; its startup registration records it. Until then there is
        # none, and the old harness's id would resume the wrong conversation.
        seeded = item.route == "seed"
        db.register(
            conn, user_id, row["tmux_pane"], None if seeded else item.session_id, model, req.to,
            submit_key=tmux.submit_key_for_flavor(req.to),
            tmux_server=row.get("tmux_server"), pane_label=row.get("pane_label"), node=row.get("node"),
        )
        if seeded:
            db.clear_agent_id(conn, user_id)
        _refresh_watch(node.name)
        return {"ok": True, "applied": True, "plan": item.describe()}

    @app.post("/agents/{user_id}/terminal")
    def agents_terminal(user_id: str, req: TerminalReq, _: None = Depends(_require_owner)):
        """Type straight into an agent's pane, as if at its keyboard.

        `text` is pasted and submitted, like a line typed at the prompt
        (`/fast`, `/model sonnet`). `key` presses one key, for menu navigation
        or interrupting work. Neither is a message: no prefix, no envelope,
        no message row.
        """
        if (req.text is None) == (req.key is None):
            raise HTTPException(status_code=422, detail={"error": "send exactly one of text or key"})
        if req.key is not None and req.key not in tmux.TERMINAL_KEYS:
            raise HTTPException(
                status_code=422,
                detail={"error": f"unknown key {req.key}", "keys": list(tmux.TERMINAL_KEYS)},
            )
        if req.text is not None and not req.text.strip():
            raise HTTPException(status_code=422, detail={"error": "text is empty"})
        recipient = _agent_or_404(user_id)
        node = _node_of(recipient)
        reason = _offline(recipient, node, _try_snapshot(node))
        if reason is not None:
            raise HTTPException(status_code=409, detail={"error": reason})
        pane, server = recipient["tmux_pane"], recipient.get("tmux_server")
        if req.key is not None:
            sent = node.send_key(nodes.new_op_id(), pane, server, req.key)
        else:
            sent = node.deliver(
                nodes.new_op_id(), pane, server, req.text,
                submit_key=recipient.get("submit_key") or tmux.DEFAULT_SUBMIT_KEY,
                flavor=recipient.get("flavor"),
                # A command may open a menu; a retried Enter would pick from it.
                retry_submit=False,
            )
        if sent.status != "ok":
            raise _node_failure("could not type into the pane", sent)
        return {"ok": True, "user_id": user_id}

    @app.get("/teams")
    def teams_list(_: None = Depends(_require_owner)):
        return {"teams": db.list_teams(conn)}

    @app.post("/teams")
    def teams_create(req: TeamCreateReq, _: None = Depends(_require_owner)):
        try:
            team = db.create_team(conn, req.name)
        except db.TeamNameConflict as exc:
            raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"error": str(exc)}) from exc
        return {"ok": True, "team": team}

    @app.post("/teams/reorder")
    def teams_reorder(req: TeamReorderReq, _: None = Depends(_require_owner)):
        """Set the sidebar's team order after a drag."""
        try:
            db.reorder_teams(conn, req.order)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"error": str(exc)}) from exc
        return {"ok": True, "teams": db.list_teams(conn)}

    def _queen_handover(team: dict, old_queen: str):
        content = f"You are no longer queen of team '{team['name']}'. "
        if team["queen"]:
            new_queen = team["queen"]
            content += (
                f"{new_queen} is now queen. Send {new_queen} a handover now with "
                f"`buzz send --to {new_queen} --context queen-handover --message \"...\"`: "
                "branches waiting for review or landing, worktrees to clean up, "
                "decisions pending with the owner, and promises to other teams or agents. "
            )
        content += "Stop coordinating this team."
        try:
            _deliver_as(OWNER, old_queen, content, "queen-handover")
        except HTTPException:
            pass  # Failed delivery is recorded; continue notifying the new team.
        if team["queen"]:
            for member in team["members"]:
                if member not in (old_queen, team["queen"]):
                    try:
                        _deliver_as(
                            OWNER, member,
                            f"The queen of team '{team['name']}' is now {team['queen']}.",
                            "queen-status",
                        )
                    except HTTPException:
                        pass  # An offline member must not block the promotion.

    @app.patch("/teams/{team_id}")
    def teams_update(team_id: int, req: TeamUpdateReq, _: None = Depends(_require_owner)):
        previous = db.get_team(conn, team_id)
        kwargs = {}
        if req.name is not None:
            kwargs["name"] = req.name.strip()
            if not kwargs["name"]:
                raise HTTPException(status_code=422, detail={"error": "Team name cannot be empty."})
        if "queen" in req.model_fields_set:
            kwargs["queen"] = req.queen or None
        try:
            team = db.update_team(conn, team_id, **kwargs)
        except db.TeamNameConflict as exc:
            raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)})
        if team is None:
            raise HTTPException(status_code=404, detail={"error": "unknown team"})
        old_queen = previous["queen"] if previous else None
        changed = old_queen is not None and old_queen != team["queen"]
        if changed:
            _queen_handover(team, old_queen)
        promotion = None
        if kwargs.get("queen"):
            objective = (req.objective or "").strip() or (
                "Coordinate your team to execute the shared task board."
            )
            promotion = _deliver_as(
                OWNER,
                team["queen"], _queen_prompt(team, objective, old_queen if changed else None), "queen-promotion"
            )
        return {"ok": True, "team": team, "promotion": promotion}

    @app.delete("/teams/{team_id}")
    def teams_delete(team_id: int, _: None = Depends(_require_owner)):
        if not db.delete_team(conn, team_id):
            raise HTTPException(status_code=404, detail={"error": "unknown team"})
        return {"ok": True}

    @app.post("/agents/{user_id}/team")
    def agents_set_team(user_id: str, req: AgentTeamReq, _: None = Depends(_require_owner)):
        previous_recipient = db.get_recipient(conn, user_id)
        previous_team = (
            db.get_team(conn, previous_recipient["team_id"])
            if previous_recipient and previous_recipient.get("team_id") is not None else None
        )
        try:
            recipient = db.set_agent_team(conn, user_id, req.team_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail={"error": str(exc)})
        if recipient is None:
            raise HTTPException(status_code=404, detail={"error": "unknown agent"})
        if (previous_team and previous_team["queen"] == user_id
                and previous_team["id"] != req.team_id):
            _queen_handover({**previous_team, "queen": None}, user_id)
        return {"ok": True, "recipient": recipient}

    def _recipients_with_activity(summaries: dict | None = None) -> list[dict]:
        recipients = _annotated_recipients()
        if summaries is None:
            summaries = db.summaries_by_user(conn, db.SUMMARY_HISTORY)
        for r in recipients:
            r["pane_alive"] = r["alive"]
            r["summaries"] = summaries.get(r["user_id"], [])
            r["compact_command"] = tmux.compact_command_for_flavor(r.get("flavor"))
            row = registry.get(r["user_id"])
            r["activity"] = (
                {
                    "status": row["status"],
                    "detail": row["detail"],
                    "error": row.get("error"),
                    "since": row["since"],
                    "context": row.get("context"),
                }
                if row
                else dict(UNKNOWN_ACTIVITY)
            )
        return recipients

    @app.get("/supervisor")
    def supervisor_get():
        return {"supervisor": db.get_supervisor(conn)}

    @app.put("/supervisor")
    def supervisor_set(req: SupervisorReq, _: None = Depends(_require_owner)):
        """Appoint the swarm supervisor and deliver its role prompt.

        Like the queen, this is a prompt the agent is given, stored on the hub
        so the dashboard and `buzz supervisor` can say who holds it.
        The nudge cursor starts at the newest message: the supervisor is told
        about what happens from now on, not the whole backlog.
        """
        objective = (req.objective or "").strip() or (
            "Keep the owner informed about the swarm and act on their requests."
        )
        try:
            row = db.set_supervisor(conn, req.user_id, objective, db.newest_message_id(conn))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail={"error": str(exc)}) from exc
        peers = _annotated_recipients()
        delivery = _deliver_as(
            OWNER, req.user_id, _supervisor_prompt(req.user_id, objective, peers), "supervisor"
        )
        return {"ok": True, "supervisor": row, "delivery": delivery}

    @app.delete("/supervisor")
    def supervisor_clear(_: None = Depends(_require_owner)):
        row = db.clear_supervisor(conn)
        if row is None:
            raise HTTPException(status_code=404, detail={"error": "no supervisor is set"})
        delivery = None
        try:
            delivery = _deliver_as(
                OWNER, row["user_id"],
                "The owner has ended your swarm supervisor role. Stop sending digests "
                "and swarm reports; carry on as a normal agent.", "supervisor",
            )
        except HTTPException:
            pass  # gone or offline: the role is cleared either way
        return {"ok": True, "was": row, "delivery": delivery}

    @app.get("/digest")
    def digest_get(request: Request, caller: ActorFields = Depends(),
                   after_message: int = 0, minutes: float = 60, team: str | None = None):
        """What changed, as text an agent can read in one go.

        `after_message` is an exact cursor (message ids only go up); the last
        line of every digest names the next one. Without it the window is the
        last `minutes`. `team` (name or id) keeps only that team's members,
        its tasks, and messages one of its members sent or received.
        """
        now = time.time()
        since_ts = now - max(minutes, 0) * 60
        if after_message > 0:
            since_ts = db.message_ts(conn, after_message) or since_ts
            msgs = db.fetch_messages_after(conn, after_message)
        else:
            msgs = db.fetch_messages_after(conn, 0, since_ts)
        sup = db.get_supervisor(conn)
        recipients, tasks = _recipients_with_activity(), db.list_tasks(conn)
        if team is not None:
            found = _find_team(team)
            members = set(found["members"])
            recipients = [r for r in recipients if r["user_id"] in members]
            tasks = team_view.team_tasks(found, tasks)
            msgs = [m for m in msgs if m["sender"] in members or m["recipient"] in members]
        rendered = digest.render(
            now, recipients, tasks, msgs,
            after_message, since_ts, sup["user_id"] if sup else None, db.list_teams(conn),
        )
        if team is not None and (stats := _board_summary_for(request, caller, found["id"])) is not None:
            rendered["board"] = stats
            # Keep the existing next-cursor marker as the last line.
            text, sep, cursor = rendered["text"].rpartition("\n")
            rendered["text"] = text + sep + boards.summary_line(stats) + "\n" + cursor
        return rendered

    switching: set[str] = set()
    switching_lock = threading.Lock()

    @app.post("/agents/{user_id}/switch-model")
    def agents_switch_model(user_id: str, req: SwitchModelReq, request: Request):
        """Switch the model an agent runs, for its current session.

        Drives the harness's own /model command in the agent's pane (see
        model_switch) and reads the result back off the screen. An agy agent
        is restarted into the same conversation instead, and only when idle. The owner may
        switch any agent; an agent may switch the members of a team it is
        queen of.
        """
        actor = _actor(request, req)
        recipient = _agent_or_404(user_id)
        if actor == user_id:
            # The switch types into the pane, which would land in the caller's own turn.
            raise HTTPException(
                status_code=403,
                detail={"error": "an agent cannot switch its own model through the hub",
                        "detail": "run /model in your own harness instead"},
            )
        if actor != OWNER:
            team = db.get_team(conn, recipient["team_id"]) if recipient.get("team_id") else None
            if team is None or team.get("queen") != actor:
                raise HTTPException(
                    status_code=403,
                    detail={"error": f"{actor} is not the queen of {user_id}'s team",
                            "detail": "only the owner or the agent's queen can switch its model"},
                )
        flavor = recipient.get("flavor")
        if flavor not in model_switch.SWITCHABLE:
            raise HTTPException(
                status_code=422,
                detail={"error": f"switching models is not supported for {flavor} agents",
                        "supported": list(model_switch.SWITCHABLE)},
            )
        if flavor == "pi" and "/" not in req.model:
            # Pi takes "provider/id"; a bare name ("sonnet", sent to a mixed
            # team) must not reach Pi's own matching.
            raise HTTPException(
                status_code=422,
                detail={"error": f"Pi needs a provider/id model, not {req.model!r}",
                        "models": tmux.pi_models()},
            )
        node = _node_of(recipient)
        reason = _offline(recipient, node, _try_snapshot(node))
        if reason is not None:
            raise HTTPException(status_code=409, detail={"error": reason})
        with switching_lock:
            if user_id in switching:
                raise HTTPException(status_code=409, detail={"error": f"{user_id} is already switching models"})
            switching.add(user_id)
        try:
            pane = model_switch.Pane(
                node, recipient["tmux_pane"], recipient.get("tmux_server"),
                recipient.get("submit_key") or tmux.DEFAULT_SUBMIT_KEY, flavor,
                session=recipient.get("agent_id"),
            )
            try:
                seen = model_switch.switch(pane, req.model.strip())
            except model_switch.SwitchFailed as e:
                tail = "\n".join((e.screen or "").rstrip().splitlines()[-12:])
                raise HTTPException(
                    status_code=502, detail={"error": str(e), "screen": tail or None},
                ) from e
        finally:
            with switching_lock:
                switching.discard(user_id)
        updated = db.set_recipient_model(conn, user_id, seen)
        log.info("%s switched %s to %s", actor, user_id, seen)
        return {"ok": True, "user_id": user_id, "model": seen, "recipient": updated}

    @app.post("/agents/{user_id}/model")
    def agents_set_model(user_id: str, req: AgentModelReq, _: None = Depends(_require_owner)):
        model = (req.model or "").strip() or None
        recipient = db.set_recipient_model(conn, user_id, model)
        if recipient is None:
            raise HTTPException(status_code=404, detail={"error": "unknown agent"})
        return {"ok": True, "recipient": recipient}

    from .routes import tasks as tasks_routes
    from .routes import nodes as nodes_routes
    from .routes import dashboard

    dashboard.register_routes(
        app, conn=conn, db_path=db_path, fleet=fleet,
        _require_owner=_require_owner, _recipients_with_activity=_recipients_with_activity,
        _agent_or_404=_agent_or_404, _node_of=_node_of,
    )

    nodes_routes.register_routes(
        app, _disconnect=_disconnect, _refresh_watch=_refresh_watch, _require_owner=_require_owner,
        _try_snapshot=_try_snapshot, _watch_list=_watch_list, conn=conn, fleet=fleet,
        fleet_lock=fleet_lock, interval=interval,
    )

    tasks_routes.register_routes(
        app, _actor=_actor, _deliver_as=_deliver_as, _require_owner=_require_owner,
        attachments_root=attachments_root, conn=conn, fleet=fleet,
    )

    return app


def _run() -> None:
    """Console-script entry: `buzz-server` starts uvicorn on 127.0.0.1:8765.

    The app is built here, not at import: building it opens the database and
    runs the startup reconciliation, which must happen in the one process
    that serves it, never in a test or a tool that merely imports this module.
    """
    import uvicorn

    port = int(os.environ.get("AGENT_SWARM_PORT", "8765"))
    host = os.environ.get("AGENT_SWARM_HOST", "127.0.0.1")
    # No proxy-header rewriting: request.client must be the real socket peer,
    # since the auth middleware decides trust by it.
    uvicorn.run(create_app(), host=host, port=port, reload=False, proxy_headers=False)
