"""FastAPI server. Endpoints: /register, /send, /messages, /recipients, /health,
plus the live web portal at / (backed by /api/state and /api/peek)."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import secrets
import threading
from dataclasses import dataclass

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import activity, attachments, bundle, db, digest, names, nodes, panes, protocol, tmux

log = logging.getLogger("agent_swarm.monitor")

# Default activity shown when the monitor is off or hasn't observed an agent
# yet. The dashboard must tolerate this shape.
UNKNOWN_ACTIVITY = {"status": "unknown", "detail": None, "since": None}

DB_PATH = Path(
    os.environ.get(
        "AGENT_SWARM_DB",
        os.environ.get("AGENT_MSG_DB", "~/.agent-swarm/db.sqlite"),
    )
).expanduser()
PORTAL_PATH = Path(__file__).parent / "portal.html"
PORTAL_STATIC_PATH = Path(__file__).parent / "static"

# Reserved handle for the human operator. Never assigned to an agent
# (the name pool contains only animals). Messages sent to it are recorded
# for the dashboard instead of being injected into a tmux pane.
OWNER = "owner"
# The server itself, when it signs a message (the supervisor's digest nudges).
HUB = "hub"

# Said the same way wherever a worker meets it: in the assignment message, in
# the protocol brief, and in the error it gets if it tries to close without one.
NOTE_GUIDANCE = (
    "Say how to verify the work: for a feature, how to use it; for a fix, how "
    "to reproduce the problem it solves; and where to look - the command to "
    "run, the endpoint or screen to open, or the files that changed. Write it "
    "for someone coming back to this later with no memory of the work."
)

# The dashboard shows each agent's latest status line, so the owner can see
# what everyone is doing (and did last) without a task to go by.
STATUS_GUIDANCE = (
    "Whenever you start on something new, run `agent-swarm status \"working on "
    "<what, in a few words>\"` so the owner's dashboard shows what you are "
    "doing; say when you finish, e.g. `agent-swarm status \"done: <what>\"`."
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


class ImportReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node: str = Field(min_length=1, description="the machine these agents run on")
    bundle: dict = Field(description="what `agent-swarm export` wrote on that machine")
    dry_run: bool = Field(default=False, description="decide and report, write nothing")
    again: bool = Field(
        default=False,
        description="take in a bundle that was imported before, duplicating what it carries",
    )
    merge_teams: bool = Field(
        default=False,
        description="add to a team of the same name here instead of importing it under a new one",
    )


class RetireReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_ids: list[str] = Field(min_length=1)


class PruneReq(BaseModel):
    include_shells: bool = Field(
        default=False,
        description="Also drop registrations whose pane exists but only runs a bare shell.",
    )


class StatusReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tmux_pane: str | None = Field(
        default=None,
        description="The caller's pane, when it has one. A session in a "
        "background host has none and is identified by agent_id alone.",
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

    node: str | None = Field(
        default=None,
        description="Machine the caller's pane lives on; the CLI sends "
        "$AGENT_SWARM_NODE or its short hostname. Omitted means the server's own.",
    )
    text: str = Field(min_length=1, max_length=200)


class SendReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tmux_pane: str | None = Field(
        default=None,
        description="The caller's pane, when it has one. A session in a "
        "background host has none and is identified by agent_id alone.",
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

    node: str | None = Field(
        default=None,
        description="Machine the caller's pane lives on; the CLI sends "
        "$AGENT_SWARM_NODE or its short hostname. Omitted means the server's own.",
    )
    recipient: str = Field(min_length=1)
    content: str = Field(min_length=1)
    context: str | None = None


class OwnerSendReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient: str = Field(min_length=1)
    content: str = ""
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


class ActorFields(BaseModel):
    """Who is acting, for requests whose effects are delivered as messages.

    The owner's dashboard sends neither field. An agent's CLI sends its pane
    and node, and the notification goes out in that agent's name rather than
    the owner's: a node token must never be able to speak as the human.
    """

    tmux_pane: str | None = None
    node: str | None = None
    agent_id: str | None = Field(
        default=None,
        description="The acting agent's harness session id; see SendReq.agent_id.",
    )
    pane_verified: bool | None = None
    pane_in_tree: bool | None = Field(default=None, description="See SendReq.pane_in_tree.")
    harness: str | None = Field(default=None, description="See SendReq.harness.")


class TaskCreateReq(ActorFields):
    attachments: list[str] = Field(default_factory=list, max_length=attachments.MAX_PER_MESSAGE)
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    description: str | None = None
    assignee: str | None = None
    team_id: int | None = None
    depends_on: list[int] | None = None


class TaskUpdateReq(ActorFields):
    model_config = ConfigDict(extra="forbid")

    status: Literal["open", "picked_up", "done"] | None = None
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    assignee: str | None = None
    worktree: str | None = Field(default=None, min_length=1)
    worktree_node: str | None = Field(
        default=None,
        description="Machine the worktree path is on. The CLI sends its own node; "
        "omitted means the server's own.",
    )
    team_id: int | None = None
    depends_on: list[int] | None = None
    note: str | None = Field(
        default=None,
        description="How to verify the finished work: how to use it if it is a "
        "feature, how to reproduce if it is a fix, and where to look. Required "
        "to close a task, and kept on the task so it can be read later.",
    )


class SpawnReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flavor: Literal["claude", "codex", "pi", "hermes"] = "claude"
    model: str | None = Field(
        default=None,
        description="Optional harness model. Only honored when it is one of "
        "the harness's known models; otherwise the harness default is used.",
    )
    node: str | None = Field(
        default=None,
        description="Machine to spawn on. Omitted means the server's own.",
    )


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


class AgentModelReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = Field(
        default=None,
        max_length=120,
        description="Model label shown on the dashboard, e.g. claude-opus-4-7. "
        "Display only: the running agent is not switched. Blank clears it.",
    )


def _queen_prompt(team: dict, objective: str) -> str:
    teammates = [m for m in team["members"] if m != team["queen"]]
    roster = ", ".join(teammates) if teammates else "(no teammates yet)"
    return (
        f"The owner has made you Queen of team '{team['name']}'. "
        f"Your teammates: {roster}.\n\n"
        f"Objective: {objective}\n\n"
        "Act as the owner's coordination point for this team until the owner ends "
        "or changes this role. Immediately notify each teammate, using context "
        "queen-status, that you coordinate this team for this objective and that "
        "their task coordination should route through you.\n\n"
        "Decompose the objective into concrete tasks; create and assign them to "
        "teammates with agent-swarm task-create and agent-swarm task-update, and "
        "record ordering with --depends-on <ids> so the board shows the "
        "dependency graph. Tasks "
        "the owner assigns to the team are delivered to you: parcel them out by "
        "reassigning or splitting them among teammates as appropriate, and "
        "monitor your workers' progress. Normally coordinate rather than "
        "implement. Require repository workers to use "
        "branch task/<id> in a dedicated worktree and record it on the task. "
        "Track progress, dependencies, stopped agents, commits, tests, and "
        "integration; integrate one branch at a time. Keep the owner informed of "
        "material progress and decisions, and ask before changing scope or the "
        "definition of done. Coordinate only your own team.\n\n"
        "This is a prompt-driven role, not special server authority. The owner "
        "retains every right and can replace or demote you at any time."
    )


def _supervisor_prompt(user_id: str, objective: str, peers: list[dict]) -> str:
    live = [p["user_id"] for p in peers if p.get("alive") and p["user_id"] != user_id]
    roster = ", ".join(live) if live else "(no other live agents right now)"
    return (
        f"The owner has made you the swarm supervisor: the one agent the owner "
        f"asks about the whole swarm. Live agents right now: {roster}.\n\n"
        f"Objective: {objective}\n\n"
        "What you do:\n"
        "- Answer the owner. When asked what is going on, run `agent-swarm digest` "
        "(`--minutes N` for a window, or `--after-message ID` from the end of your "
        "last digest) and reply in a few lines: what changed, who needs attention, "
        "what is done, what is stalled. For one task, read `agent-swarm tasks` and "
        "the messages tagged `task-N` (`agent-swarm messages --user <handle>`); "
        "if the board does not say, ask the assignee with `agent-swarm send` and "
        "relay the answer.\n"
        "- Delegate when asked. File work with `agent-swarm task-create \"title\" "
        "--description ... --assignee <handle>`; the assignee is notified in your "
        "name. Prefer an idle agent of a suitable harness; when none is free, "
        "`agent-swarm spawn --flavor claude|codex|pi|hermes` starts one, then assign "
        "to the handle it prints. Record ordering with --depends-on.\n"
        "- Watch the swarm. The hub sends you a message from `hub` tagged `digest` "
        "when there is new traffic or task changes you were not party to; read the "
        "digest it names and tell the owner only what matters. Agents whose pane "
        "shows an approval prompt appear as `needs attention`; you cannot answer "
        "the prompt, but you can tell the owner which agent and why.\n"
        "- Admin. `agent-swarm stop <handle>` kills an agent's pane: ask the owner "
        "first unless they already told you to. Never delete tasks or change team "
        "membership on your own.\n\n"
        "Report facts, not guesses: a delivery marked unknown may or may not have "
        "arrived, so say so and never resend on your own. Keep replies to the owner "
        "short; they land on the dashboard via `agent-swarm send --to owner`. "
        "Set `agent-swarm status \"supervising: ...\"` so the dashboard shows the "
        "role.\n\n"
        "This is a prompt-driven role, not special server authority. The owner "
        "retains every right and can end the role at any time."
    )


def _protocol_brief(user_id: str, peers: list[dict]) -> str:
    """A one-shot primer the agent sees in its register response.

    Tells the agent what inbound messages look like so a line appearing in
    its prompt doesn't get mistaken for user input.
    """

    def _peer_line(p: dict) -> str:
        tags = []
        if p.get("flavor"):
            tags.append(f"flavor={p['flavor']}")
        if p.get("model"):
            tags.append(p["model"])
        if p.get("node"):
            tags.append(f"node={p['node']}")
        if p.get("agent_id"):
            tags.append(f"agent={p['agent_id']}")
        if p.get("submit_key"):
            tags.append(f"submit={p['submit_key']}")
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
    return (
        f"You are registered as '{user_id}'.\n"
        f"\n"
        f"Incoming messages from the owner and other agents are delivered by injecting a "
        f"line into your tmux pane (as if typed) followed by the configured "
        f"submit key (default `C-m`). The "
        f"format is:\n"
        f"\n"
        f"    [agent-msg from <sender> · <context>] <content>\n"
        f"\n"
        f"The `· <context>` segment is omitted when the sender didn't "
        f"supply a context tag. Reply to the sender through the agent-swarm API "
        f"so the response reaches their inbox.\n"
        f"\n"
        f"To reply or initiate, POST to /send (or use the `agent-swarm send` "
        f"CLI). Currently registered peers:\n"
        f"{peer_lines}\n"
        f"\n"
        f"{offline_note}"
        f"List peers anytime: GET /recipients.\n"
        f"\n"
        f"The reserved handle 'owner' is the human operator in charge of "
        f"all agents. Messages from 'owner' are instructions from the "
        f"human, not from a peer agent. To message the human, send to "
        f"recipient 'owner'; replies land on the owner's dashboard. "
        f"Terminal-only output does not reach the owner. The dashboard "
        f"renders every message body, to the owner and between agents, as "
        f"Markdown: use pipe tables for numbers, bullets for parallel items, "
        f"and a bold lead line. Write a long message to a file and send it "
        f"with `--message \"$(cat file)\"` so pipes and quotes survive the "
        f"shell.\n"
        f"\n"
        f"The owner can assign you tasks. They arrive as messages tagged "
        f"'task #N'. When you start one, run "
        f"`agent-swarm task-update N --status picked_up`; when you finish, "
        f"run `agent-swarm task-update N --status done --note \"...\"`. "
        f"The note is required: closing without one is refused. {NOTE_GUIDANCE} "
        f"It stays on the task, so the owner can open it later and see how to "
        f"check the work. "
        f"List tasks anytime: `agent-swarm tasks`. You can file work for the "
        f"shared board with `agent-swarm task-create \"title\"` (optionally "
        f"add `--description`, `--assignee`, or `--depends-on 3,5` to record "
        f"ordering; dependencies show as a graph on the dashboard).\n"
        f"\n"
        f"{STATUS_GUIDANCE}\n"
        f"\n"
        f"The owner may group agents into teams, each with a queen who "
        f"coordinates that team's work. Tasks can be assigned to a team; "
        f"they reach the queen, who parcels them out. The owner may also "
        f"appoint one agent as swarm supervisor, the agent they ask about the "
        f"whole swarm; `agent-swarm supervisor` says who, if anyone, holds it."
    )


def create_app(
    db_path: Path = DB_PATH, monitor: bool = True, trust_loopback: bool | None = None
) -> FastAPI:
    conn = db.connect(db_path)
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
    interval = float(
        os.environ.get(
            "AGENT_SWARM_MONITOR_INTERVAL",
            os.environ.get("AGENT_MSG_MONITOR_INTERVAL", "5.0"),
        )
    )
    grace = float(
        os.environ.get(
            "AGENT_SWARM_ATTENTION_GRACE",
            os.environ.get("AGENT_MSG_ATTENTION_GRACE", "60.0"),
        )
    )

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
        _migrate_legacy_panes()
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
            capture = None
            if alive:
                # Claude Code and Codex title their pane with the current topic.
                topic = tmux.title_summary(snap.title(pane) or "")
                if topic:
                    db.record_summary(conn, r["user_id"], topic, "title")
                # Subprocess capture must not block the event loop, and one
                # pane's failure must not end the tick for the others.
                try:
                    text, err = await asyncio.to_thread(node.capture, pane, r.get("tmux_server"))
                except Exception:
                    log.exception("capture of %s on %s failed", pane, node.name)
                    text, err = None, "capture failed"
                capture = text if err is None else None
            observations.append(
                activity.Observation(r["user_id"], r.get("flavor"), alive, capture)
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
                    {"detail": {"error": "unknown token; enrol the machine with `agent-swarm node-token`"}},
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
                {"detail": {"error": "authentication required", "hint": "set AGENT_SWARM_TOKEN or run `agent-swarm join`"}},
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
        registration moves to the new id, as `agent-swarm register` would.
        A background host is never inside the pane's process tree. Without an
        id, a pane the CLI says it is not in is refused; an older CLI, which
        says nothing (None), is identified by its pane as before.
        """
        agent_id = (agent_id or "").strip() or None
        if agent_id:
            by_id = db.lookup_user_by_agent_id(conn, agent_id)
            if by_id:
                # Session ids are public (recipients, the protocol brief), so
                # an id held on another machine is a refusal, never this caller.
                if (db.get_recipient(conn, by_id) or {}).get("node") != node.name:
                    return None, "session", f"this session belongs to {by_id} on another node", (tmux_pane, None)
                return by_id, "session", None, (tmux_pane, None)
        if not tmux_pane:
            why = "this session is not registered" if agent_id else "no pane and no session id"
            return None, "session" if agent_id else "pane", f"{why}; run `agent-swarm register` from the agent's pane", (None, None)
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
            return None, "session", "this session is not registered; run `agent-swarm register`", where
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
                f"is {pane_user}, run `agent-swarm register` from this pane (without --name) to move "
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
                    "retry, or run `agent-swarm register`"
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

    @app.get("/health")
    def health():
        return {"ok": True, "db": str(db_path)}

    @app.post("/register")
    def register(req: RegisterReq, request: Request):
        _migrate_legacy_panes()
        node = _claimed_node(request, req.node)
        pane, label, server = _pane_ref(req.tmux_pane, node)
        if server is None:
            raise HTTPException(status_code=404, detail={
                "error": f"pane {req.tmux_pane} does not resolve on node {node.name}; "
                         "register from the agent's live pane or supply its --pane explicitly"
            })
        flavor_hint = req.flavor or (tmux.infer_flavor(req.model) if req.model else None)
        existing_id = None
        if req.agent_id:
            existing_id = db.lookup_user_by_agent_id(conn, req.agent_id)
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
                if (req.agent_id or None) != row["agent_id"]:
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
            _own_row_or_403(request, requested)
            if (
                db.name_taken_by_other(
                    conn, requested, req.agent_id, node.name, pane, server
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
        flavor = req.flavor or (tmux.infer_flavor(req.model) if req.model else None)
        if flavor is None:
            flavor = (current["flavor"] if current else None) or tmux.infer_flavor(None)
        submit_key = req.submit_key or tmux.submit_key_for_flavor(flavor)
        db.register(
            conn,
            user_id,
            pane,
            req.agent_id,
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
            "agent_id": registered["agent_id"] if registered else req.agent_id,
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
            "protocol_brief": _protocol_brief(user_id, peers),
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

    def _snapshot_named(name: str | None) -> nodes.PaneSnapshot | None:
        return _try_snapshot(fleet.get(name))

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
        _migrate_legacy_panes()
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

    def _migrate_legacy_panes() -> None:
        """Rebind rows stored before pane ids; see agent_swarm/panes.py."""
        # Only this machine's rows can predate pane ids: no other node could
        # have registered before nodes existed. A row with no node at all is
        # from that era too, so it is stamped local first.
        db.fill_missing_node(conn, fleet.local.name)
        rows = [r for r in db.legacy_pane_rows(conn) if r["node"] == fleet.local.name]
        if not rows:
            return
        snap = _try_snapshot(fleet.local)
        if snap is None or snap.server is None:
            return  # no tmux right now; try again on a later call
        for d in panes.plan(rows, snap.table, snap.server_start):
            row = next(r for r in rows if r["user_id"] == d.user_id)
            if d.pane_id is not None:
                db.bind_pane(conn, d.user_id, d.pane_id, snap.server, d.label)
            elif d.gone:
                # Keeping the old address under this server reads as "pane no
                # longer exists" (addresses never match ids), so prune clears it.
                db.bind_pane(conn, d.user_id, row["tmux_pane"], snap.server, row["tmux_pane"])
            else:
                db.bind_pane(conn, d.user_id, row["tmux_pane"], db.UNBOUND, row["tmux_pane"])
            log.info("pane migration: %s -> %s (%s)", d.user_id, d.pane_id or "offline", d.reason)

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
    def recipients():
        return {"recipients": _annotated_recipients()}

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
        """Forget agents that are not running: their registration, team
        membership, and status lines go; messages and tasks stay. A live
        agent is never retired, so a stale page cannot remove one."""
        by_id = {r["user_id"]: r for r in _annotated_recipients()}
        retired, live, unknown = [], [], []
        for user_id in dict.fromkeys(req.user_ids):
            row = by_id.get(user_id)
            if row is None:
                unknown.append(user_id)
            elif row["alive"]:
                live.append(user_id)
            elif db.delete_recipient(conn, user_id):
                retired.append(user_id)
                _refresh_watch(row["node"])
        return {"ok": True, "retired": retired, "kept_live": live, "unknown": unknown}

    @app.delete("/recipients/{user_id}")
    def unregister(user_id: str, request: Request):
        row = _own_row_or_403(request, user_id)
        if not db.delete_recipient(conn, user_id):
            raise HTTPException(status_code=404, detail="recipient not registered")
        if row:
            _refresh_watch(row["node"])
        return {"ok": True, "user_id": user_id}

    def _deliver_as(
        sender: str,
        recipient_id: str,
        content: str,
        context: str | None,
        files: list[str] | None = None,
        client_id: str | None = None,
    ):
        """Deliver a message in `sender`'s name to an agent's pane.

        The owner's dashboard sends as `owner`; a task assigned by an agent
        arrives from that agent, so a node token can never sign as the human.
        """
        files = files or []
        recipient = db.get_recipient(conn, recipient_id)
        if recipient is None:
            mid = db.record_message(
                conn,
                sender,
                recipient_id,
                context,
                content,
                status="failed",
                delivery_error="recipient not registered",
                attachments=files,
            )
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "recipient not registered",
                    "recipient": recipient_id,
                    "message_id": mid,
                },
            )
        node = _reach(sender, recipient, context, content, files)
        mid, status, err = _dispatch(node, sender, recipient, context, content, files, client_id)
        return {
            "ok": status == "delivered", "status": status,
            "message_id": mid, "delivery_error": err,
        }

    # Node result -> message status.
    MESSAGE_STATUS = {"ok": "delivered", "failed": "failed", "unknown": "unknown"}

    def _replayed(m: dict) -> tuple[int, str, str | None]:
        """An earlier attempt's (id, status, error), for a repeated client id."""
        if m["status"] == "pending":
            return m["id"], "unknown", "an earlier attempt of this message is still being delivered"
        return m["id"], m["status"], m.get("delivery_error")
    OWNER_REPLY_IDLE_SECONDS = 25 * 60

    def _dispatch(
        node: nodes.Node,
        sender: str,
        recipient: dict,
        context: str | None,
        content: str,
        files: list[str] | None = None,
        client_id: str | None = None,
    ) -> tuple[int, str, str | None]:
        """Record a message, then paste it into the recipient's pane.

        The row exists before the paste, with the message id as the
        operation id, so a result that never comes back leaves a message
        marked unknown rather than a paste with no record. Unknown is never
        retried here: the agent may already have it. Nor is a client id seen
        before: that request's outcome is returned without a second paste.
        """
        files = files or []
        try:
            mid = db.record_message(
                conn, sender, recipient["user_id"], context, content,
                status="pending", attachments=files, client_id=client_id,
            )
        except db.DuplicateMessage as dup:
            return _replayed(dup.existing)
        # Attachment names travel as names; the node renders them as paths on
        # the machine the pane is on, fetching them from the hub if remote.
        reminder = sender == OWNER and db.owner_reply_reminder_due(
            conn, recipient["user_id"], since=recipient["registered_at"],
            now=time.time(), idle_seconds=OWNER_REPLY_IDLE_SECONDS,
        )
        body = tmux.format_message(sender, context, content, owner_reply_reminder=reminder)
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
        return mid, status, result.error

    @app.post("/send")
    def send(req: SendReq, request: Request):
        node = _claimed_node(request, req.node)
        sender = _caller(node, req.tmux_pane, req.agent_id, req.pane_verified, req.pane_in_tree, req.harness)
        if req.recipient == OWNER:
            # Messages to the human are recorded for the dashboard, not
            # injected into a pane.
            mid = db.record_message(
                conn, sender, OWNER, req.context, req.content, status="delivered"
            )
            return {"ok": True, "status": "delivered", "message_id": mid,
                    "delivered_to_pane": None, "delivery_error": None}
        recipient = db.get_recipient(conn, req.recipient)
        if recipient is None:
            mid = db.record_message(
                conn,
                sender,
                req.recipient,
                req.context,
                req.content,
                status="failed",
                delivery_error="recipient not registered",
            )
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "recipient not registered",
                    "recipient": req.recipient,
                    "message_id": mid,
                },
            )
        node = _reach(sender, recipient, req.context, req.content)
        mid, status, err = _dispatch(node, sender, recipient, req.context, req.content)
        return {
            "ok": status == "delivered",
            "status": status,
            "message_id": mid,
            "delivered_to_pane": recipient["tmux_pane"],
            "delivery_error": err,
        }

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
    def messages(user: str | None = None, limit: int = 50):
        return {"messages": db.fetch_messages(conn, user, limit)}

    @app.get("/api/agents/{user_id}/messages")
    def agent_messages(user_id: str, limit: int = Query(300, ge=1, le=500),
                       before: int | None = Query(None, ge=1),
                       after: int | None = Query(None, ge=0),
                       _: None = Depends(_require_owner)):
        if before is not None and after is not None:
            raise HTTPException(status_code=422, detail="Use either before or after")
        return db.agent_messages_page(conn, user_id, limit, before, after)

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
        return _deliver_as(OWNER, req.recipient, content, req.context, req.attachments, req.client_id)

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

    def _team_line(user_id: str) -> str:
        """One sentence telling an agent who its teammates are right now:
        only the ones running, since an offline one cannot answer."""
        recipient = db.get_recipient(conn, user_id)
        if recipient is None or not recipient.get("team_id"):
            return ""
        team = db.get_team(conn, recipient["team_id"])
        if team is None:
            return ""
        live = {r["user_id"] for r in _annotated_recipients() if r["alive"]}
        others = [m for m in team["members"] if m != user_id and m in live]
        mates = ", ".join(others) if others else "no one else running"
        line = f" You are on team '{team['name']}' with {mates}"
        if team["queen"] in live:
            line += f" (queen: {team['queen']})"
        return line + "."

    def _notify_assignment(task: dict, actor: str):
        hint = (
            f"Before editing, use branch task/{task['id']} in a dedicated git worktree. "
            f"Record it when you start: agent-swarm task-update {task['id']} "
            f"--worktree /absolute/path --status picked_up. "
            f"When finished: agent-swarm task-update {task['id']} --status done "
            f"--note \"...\". The note is required and the close is refused "
            f"without one. {NOTE_GUIDANCE} "
            f"When you start, also run agent-swarm status \"working on "
            f"#{task['id']}: <a few words>\" so the dashboard shows it."
        )
        content = f"You are assigned task #{task['id']}: {task['title']}."
        if task.get("description"):
            content += f" Details: {task['description']}."
        content += f" {hint}{_team_line(task['assignee'])}"
        try:
            _deliver_as(actor, task["assignee"], content, f"task #{task['id']}", task.get("attachments") or [])
        except HTTPException:
            pass  # assignee validated by callers; pane may still be gone

    def _notify_team_assignment(task: dict, actor: str):
        team = db.get_team(conn, task["team_id"])
        if team is None:
            return
        context = f"task #{task['id']}"
        detail = f" Details: {task['description']}." if task.get("description") else ""
        if team["queen"]:
            content = (
                f"Task #{task['id']} is assigned to your team '{team['name']}': "
                f"{task['title']}.{detail} As queen, parcel it out: split it into "
                f"subtasks or hand it to a teammate with agent-swarm task-update "
                f"{task['id']} --assignee <member>, then monitor progress."
            )
            targets = [team["queen"]]
        else:
            content = (
                f"Task #{task['id']} is assigned to your team '{team['name']}' "
                f"(no queen yet): {task['title']}.{detail} Coordinate with your "
                f"teammates; whoever takes it should run agent-swarm task-update "
                f"{task['id']} --assignee <yourself>."
            )
            targets = team["members"]
        for target in targets:
            try:
                _deliver_as(actor, target, content + _team_line(target), context, task.get("attachments") or [])
            except HTTPException:
                pass  # membership validated; a pane may still be gone

    def _require_registered_assignee(assignee: str | None):
        if assignee and db.get_recipient(conn, assignee) is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "assignee not registered", "assignee": assignee},
            )

    def _require_known_team(team_id: int | None):
        if team_id is not None and db.get_team(conn, team_id) is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "unknown team", "team_id": team_id},
            )

    @app.get("/tasks")
    def tasks_list():
        return {"tasks": db.list_tasks(conn)}

    def _set_deps(task_id: int, depends_on: list[int]):
        try:
            db.set_task_deps(conn, task_id, depends_on)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)})

    @app.post("/tasks")
    def tasks_create(req: TaskCreateReq, request: Request):
        actor = _actor(request, req)
        _require_registered_assignee(req.assignee)
        _require_known_team(req.team_id)
        if not req.title.strip():
            raise HTTPException(status_code=400, detail={"error": "task title is required"})
        unknown = [name for name in req.attachments if attachments.resolve(attachments_root, name) is None]
        if unknown:
            raise HTTPException(status_code=400, detail={"error": "unknown attachment", "attachments": unknown})
        try:
            task = db.create_task(
                conn, req.title.strip(), req.description, req.assignee, req.team_id,
                attachments=req.attachments, depends_on=req.depends_on,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        if task["assignee"]:
            _notify_assignment(task, actor)
        elif task["team_id"]:
            _notify_team_assignment(task, actor)
        return {"ok": True, "task": task}

    @app.delete("/tasks/{task_id}")
    def tasks_delete(task_id: int, _: None = Depends(_require_owner)):
        try:
            removed = db.delete_task(conn, task_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc
        if not removed:
            raise HTTPException(status_code=404, detail={"error": "unknown task"})
        return {"ok": True}

    @app.patch("/tasks/{task_id}")
    def tasks_update(task_id: int, req: TaskUpdateReq, request: Request):
        actor = _actor(request, req)
        before = db.get_task(conn, task_id)
        if before is None:
            raise HTTPException(status_code=404, detail={"error": "unknown task"})
        kwargs = {}
        if req.status is not None:
            kwargs["status"] = req.status
        if req.title is not None:
            if not req.title.strip():
                raise HTTPException(status_code=422, detail={"error": "a task needs a title"})
            kwargs["title"] = req.title.strip()
        if "description" in req.model_fields_set:
            kwargs["description"] = (req.description or "").strip() or None
        if "assignee" in req.model_fields_set:
            _require_registered_assignee(req.assignee)
            kwargs["assignee"] = req.assignee or None
        if "team_id" in req.model_fields_set:
            _require_known_team(req.team_id)
            kwargs["team_id"] = req.team_id
        if "worktree" in req.model_fields_set:
            kwargs["worktree"] = req.worktree
            kwargs["worktree_node"] = req.worktree_node or fleet.local.name
        if "note" in req.model_fields_set:
            kwargs["note"] = (req.note or "").strip() or None
        if "depends_on" in req.model_fields_set:
            _set_deps(task_id, req.depends_on or [])
        # Closing is the one moment the worker still has the context needed to
        # say how the work is checked, so it is the moment we insist on it.
        if req.status == "done" and not (kwargs.get("note") or before["note"]):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "a task needs a note before it can be closed",
                    "note": NOTE_GUIDANCE,
                },
            )
        task = db.update_task(conn, task_id, **kwargs)
        if task["assignee"] and task["assignee"] != before["assignee"]:
            _notify_assignment(task, actor)
        elif task["team_id"] and task["team_id"] != before["team_id"]:
            _notify_team_assignment(task, actor)
        return {"ok": True, "task": task}

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
        spawned = node.spawn(nodes.new_op_id(), command)
        if spawned.pane is None:
            # Unknown with no pane: nothing to register, and a retry could
            # leave a second window behind, so the caller decides.
            raise HTTPException(
                status_code=502 if spawned.status == "unknown" else 500,
                detail={
                    "error": "could not create tmux window",
                    "status": spawned.status,
                    "detail": spawned.error,
                },
            )
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
            "flavor": req.flavor, "model": model, "command": command,
        }

    @app.post("/agents/{user_id}/stop")
    def agents_stop(user_id: str, _: None = Depends(_require_owner)):
        recipient = db.get_recipient(conn, user_id)
        if recipient is None:
            raise HTTPException(status_code=404, detail={"error": "unknown agent"})
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
        killed = node.kill(nodes.new_op_id(), pane, recipient.get("tmux_server"))
        if not killed.ok:
            raise HTTPException(
                status_code=502 if killed.status == "unknown" else 500,
                detail={
                    "error": "could not stop tmux pane",
                    "status": killed.status,
                    "detail": killed.error,
                },
            )
        return {
            "ok": True, "user_id": user_id, "tmux_pane": pane,
            "already_stopped": False,
        }

    @app.post("/agents/{user_id}/terminal")
    def agents_terminal(user_id: str, req: TerminalReq, _: None = Depends(_require_owner)):
        """Type straight into an agent's pane, as if at its keyboard.

        `text` is pasted and submitted, like a line typed at the prompt
        (`/fast`, `/model sonnet`). `key` presses one key, for menus a command
        opens. Neither is a message: no prefix, no envelope, no message row.
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
        recipient = db.get_recipient(conn, user_id)
        if recipient is None:
            raise HTTPException(status_code=404, detail={"error": "unknown agent"})
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
            raise HTTPException(
                status_code=502 if sent.status == "unknown" else 500,
                detail={"error": "could not type into the pane",
                        "status": sent.status, "detail": sent.error},
            )
        return {"ok": True, "user_id": user_id}

    @app.get("/teams")
    def teams_list(_: None = Depends(_require_owner)):
        return {"teams": db.list_teams(conn)}

    @app.post("/teams")
    def teams_create(req: TeamCreateReq, _: None = Depends(_require_owner)):
        return {"ok": True, "team": db.create_team(conn, req.name.strip())}

    @app.patch("/teams/{team_id}")
    def teams_update(team_id: int, req: TeamUpdateReq, _: None = Depends(_require_owner)):
        kwargs = {}
        if req.name is not None:
            kwargs["name"] = req.name.strip()
        if "queen" in req.model_fields_set:
            kwargs["queen"] = req.queen or None
        try:
            team = db.update_team(conn, team_id, **kwargs)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)})
        if team is None:
            raise HTTPException(status_code=404, detail={"error": "unknown team"})
        promotion = None
        if kwargs.get("queen"):
            objective = (req.objective or "").strip() or (
                "Coordinate your team to execute the shared task board."
            )
            promotion = _deliver_as(
                OWNER,
                team["queen"], _queen_prompt(team, objective), "queen-promotion"
            )
        return {"ok": True, "team": team, "promotion": promotion}

    @app.delete("/teams/{team_id}")
    def teams_delete(team_id: int, _: None = Depends(_require_owner)):
        if not db.delete_team(conn, team_id):
            raise HTTPException(status_code=404, detail={"error": "unknown team"})
        return {"ok": True}

    @app.post("/agents/{user_id}/team")
    def agents_set_team(user_id: str, req: AgentTeamReq, _: None = Depends(_require_owner)):
        try:
            recipient = db.set_agent_team(conn, user_id, req.team_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail={"error": str(exc)})
        if recipient is None:
            raise HTTPException(status_code=404, detail={"error": "unknown agent"})
        return {"ok": True, "recipient": recipient}

    def _recipients_with_activity() -> list[dict]:
        recipients = _annotated_recipients()
        summaries = db.summaries_by_user(conn, db.SUMMARY_HISTORY)
        for r in recipients:
            r["pane_alive"] = r["alive"]
            r["summaries"] = summaries.get(r["user_id"], [])
            r["compact_command"] = tmux.compact_command_for_flavor(r.get("flavor"))
            row = registry.get(r["user_id"])
            r["activity"] = (
                {"status": row["status"], "detail": row["detail"], "since": row["since"]}
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
        so the dashboard and `agent-swarm supervisor` can say who holds it.
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
    def digest_get(after_message: int = 0, minutes: float = 60):
        """What changed, as text an agent can read in one go.

        `after_message` is an exact cursor (message ids only go up); the last
        line of every digest names the next one. Without it the window is the
        last `minutes`.
        """
        now = time.time()
        since_ts = now - max(minutes, 0) * 60
        if after_message > 0:
            since_ts = db.message_ts(conn, after_message) or since_ts
            msgs = db.fetch_messages_after(conn, after_message)
        else:
            msgs = db.fetch_messages_after(conn, 0, since_ts)
        sup = db.get_supervisor(conn)
        return digest.render(
            now, _recipients_with_activity(), db.list_tasks(conn), msgs,
            after_message, since_ts, sup["user_id"] if sup else None, db.list_teams(conn),
        )

    @app.post("/agents/{user_id}/model")
    def agents_set_model(user_id: str, req: AgentModelReq, _: None = Depends(_require_owner)):
        model = (req.model or "").strip() or None
        recipient = db.set_recipient_model(conn, user_id, model)
        if recipient is None:
            raise HTTPException(status_code=404, detail={"error": "unknown agent"})
        return {"ok": True, "recipient": recipient}

    generations = iter(range(1, 1 << 62))

    @app.websocket("/nodes/ws")
    async def nodes_ws(ws: WebSocket):
        """A node's connection. HTTP middleware does not see websockets, so
        the token is checked here, on the handshake, before accepting."""
        auth = ws.headers.get("authorization", "")
        name = db.node_for_token(conn, auth[7:].strip()) if auth.lower().startswith("bearer ") else None
        if name is None:
            await ws.close(code=1008, reason="unknown or missing token")
            return
        await ws.accept()
        try:
            hello = await asyncio.wait_for(ws.receive_json(), timeout=15)
        except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
            await ws.close(code=1002, reason="expected hello")
            return
        if hello.get("type") != "hello" or hello.get("node") != name:
            await ws.close(code=1008, reason="hello does not match the token's node")
            return
        if hello.get("protocol") != protocol.PROTOCOL:
            await ws.close(code=1002, reason=f"protocol {hello.get('protocol')} not supported")
            return
        loop = asyncio.get_running_loop()
        node = nodes.RemoteNode(
            name, next(generations), loop, ws.send_json, ws.close, interval
        )
        node.hello(hello)
        # The token was checked before the hello, which took time: a rotation
        # or revocation since then must not let this connection in. The
        # re-check and the publication are one step under the registry lock,
        # so a rotation cannot slip between them.
        # Nothing awaits inside the lock: a threading lock held across an
        # await could block the loop that has to release it.
        with fleet_lock:
            admitted = db.node_for_token(conn, auth[7:].strip()) == name
            if admitted:
                # A newer connection replaces an older one from the same
                # node; the older is fenced so nothing in flight on it can
                # be believed.
                previous = fleet.get(name)
                if isinstance(previous, nodes.RemoteNode):
                    previous.fence("replaced by a newer connection")
                fleet.add(node)
        if not admitted:
            await ws.close(code=1008, reason="token no longer valid")
            return
        db.touch_node(conn, name, node.version, node.tmux_server, node.harnesses)
        log.info("node %s connected (generation %d)", name, node.generation)
        try:
            await ws.send_json(
                protocol.welcome(interval, _watch_list(name), node.generation, db.hub_id(conn))
            )
            observed = 0
            while True:
                frame = await ws.receive_json()
                kind = frame.get("type")
                if kind == "observe":
                    node.observed(frame)
                    observed += 1
                    if observed % 12 == 1:  # about once a minute at the default interval
                        db.touch_node(conn, name, tmux_server=node.tmux_server)
                elif kind == "result":
                    node.resolved(frame)
        except WebSocketDisconnect:
            pass
        except Exception:  # noqa: BLE001 - a bad frame ends the connection, not the hub
            log.exception("node %s connection failed", name)
        finally:
            node.fence("node disconnected")
            with fleet_lock:
                if fleet.get(name) is node:
                    fleet.remove(name)
            log.info("node %s disconnected (generation %d)", name, node.generation)

    @app.post("/import")
    def import_bundle(req: ImportReq, _: None = Depends(_require_owner)):
        """Take in the agents, teams, and tasks of another hub.

        The node must be one this hub knows, so a typo cannot strand an
        import on a machine that will never connect. A dry run decides and
        reports without writing; the task ids it shows are the bundle's own,
        since the real ones are assigned when it is applied.
        """
        known = {n["name"] for n in db.list_nodes(conn)} | {fleet.local.name}
        if req.node not in known:
            raise HTTPException(
                status_code=422,
                detail={"error": "unknown node", "node": req.node, "known": sorted(known),
                        "hint": "enrol it first with `agent-swarm node-token`"},
            )
        try:
            source = bundle.source_id(req.bundle)
        except bundle.Invalid as e:
            raise HTTPException(status_code=400, detail={"error": str(e)}) from e

        import_node = fleet.get(req.node)
        snapshot = _try_snapshot(import_node) if import_node is not None else None

        def make_plan(hub: dict) -> dict:
            hub["merge_teams"] = req.merge_teams
            return bundle.plan(req.bundle, req.node, hub, snapshot=snapshot)

        earlier = db.imported_report(conn, source)
        try:
            if req.dry_run:
                plan = make_plan(db.hub_state(conn))
                report = bundle.summary(plan)
            else:
                plan = None

                def planning(hub: dict) -> dict:
                    nonlocal plan
                    plan = make_plan(hub)
                    return plan

                report = db.apply_import(
                    conn, source, req.node, planning, bundle.summary, again=req.again
                )
                _refresh_watch(req.node)
        except bundle.Invalid as e:
            raise HTTPException(status_code=400, detail={"error": str(e)}) from e
        except db.AlreadyImported as e:
            raise HTTPException(
                status_code=409,
                detail={"error": "this bundle was imported already", "report": e.report,
                        "hint": "pass again=true to take it in a second time"},
            ) from e
        return {
            "ok": True,
            "dry_run": req.dry_run,
            "imported_before": earlier,
            "report": report,
            "register": bundle.register_commands(plan),
        }

    @app.get("/nodes/me")
    def nodes_me(request: Request):
        """What the hub takes the caller for; `agent-swarm join` checks this."""
        p = request.state.principal
        return {"kind": p.kind, "node": p.node if p.kind == "node" else fleet.local.name}

    @app.get("/nodes")
    def nodes_list(_: None = Depends(_require_owner)):
        rows = db.list_nodes(conn)
        for row in rows:
            row["connected"] = row["name"] in fleet.names()
        return {"nodes": rows, "local": fleet.local.name}

    @app.post("/nodes/{name}/token")
    def nodes_token(name: str, _: None = Depends(_require_owner)):
        """Enrol a machine, or rotate its token. The token is shown once."""
        try:
            name = names.normalize_requested(name)
        except names.InvalidName as e:
            raise HTTPException(status_code=400, detail={"error": str(e)}) from e
        if name == fleet.local.name:
            raise HTTPException(
                status_code=400, detail={"error": f"{name} is this hub's own node; it needs no token"}
            )
        token = secrets.token_urlsafe(32)
        db.set_node_token(conn, name, token)
        # A connection made with the old token does not outlive it.
        _disconnect(name, "token rotated")
        return {"ok": True, "name": name, "token": token}

    @app.delete("/nodes/{name}")
    def nodes_delete(name: str, _: None = Depends(_require_owner)):
        """Revoke a machine: its token stops working and it is disconnected."""
        if not db.delete_node(conn, name):
            raise HTTPException(status_code=404, detail={"error": "unknown node"})
        _disconnect(name, "node revoked")
        return {"ok": True, "name": name}

    @app.get("/", response_class=HTMLResponse)
    def portal(_: None = Depends(_require_owner)):
        # Asset filenames are stable across builds. Version their URLs by
        # content so a normal refresh cannot reuse an older JS/CSS bundle.
        page = PORTAL_PATH.read_text()
        for name in ("portal.js", "portal.css"):
            digest = hashlib.sha256((PORTAL_STATIC_PATH / name).read_bytes()).hexdigest()[:16]
            page = page.replace(f'"/static/{name}"', f'"/static/{name}?v={digest}"')
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})

    @app.get("/api/state")
    def state(limit: int = 300, _: None = Depends(_require_owner)):
        # All summaries that are kept, so the history search finds older lines too.
        recipients = _recipients_with_activity()
        msgs = db.fetch_messages(conn, None, limit)
        msgs.reverse()  # oldest first for thread rendering
        enrolled = db.list_nodes(conn)
        for n in enrolled:
            n["connected"] = n["name"] in fleet.names()
        return {
            "now": time.time(),
            "recipients": recipients,
            "nodes": [{"name": fleet.local.name, "local": True, "connected": True}, *enrolled],
            "messages": msgs,
            "tasks": db.list_tasks(conn),
            "teams": db.list_teams(conn),
            "supervisor": db.get_supervisor(conn),
            "tabs": [t["name"] for t in extra_tabs()],
        }

    # Response headers worth passing back from a tab's page. The body arrives
    # decoded, so length and encoding are the hub's to set.
    tab_headers = ("content-type", "cache-control", "etag", "last-modified", "location")

    @app.get("/tabs/{name}")
    def tab_root(name: str, _: None = Depends(_require_owner)):
        # The page's relative links need the trailing slash.
        return RedirectResponse(f"/tabs/{name}/", status_code=307)

    @app.api_route("/tabs/{name}/{path:path}", methods=["GET", "HEAD"])
    async def tab_page(name: str, path: str, request: Request, _: None = Depends(_require_owner)):
        tab = next((t for t in extra_tabs() if t["name"] == name), None)
        if tab is None:
            raise HTTPException(status_code=404, detail={"error": "no such tab"})
        base = tab["url"].rstrip("/") + "/"
        url = base + path + (f"?{request.url.query}" if request.url.query else "")
        # Only content negotiation goes along: never the caller's identity.
        sent = {k: v for k, v in request.headers.items() if k in ("accept", "accept-language")}
        try:
            async with httpx.AsyncClient(timeout=30) as http:
                r = await http.request(request.method, url, headers=sent)
        except httpx.HTTPError as e:
            return Response(f"{name} is unreachable at {base}: {e}", status_code=502, media_type="text/plain")
        headers = {k: v for k, v in r.headers.items() if k in tab_headers}
        if "location" in headers and headers["location"].startswith(base):
            headers["location"] = f"/tabs/{name}/" + headers["location"][len(base):]
        return Response(r.content, status_code=r.status_code, headers=headers)

    @app.get("/api/peek/{user_id}")
    def peek(user_id: str, _: None = Depends(_require_owner)):
        recipient = db.get_recipient(conn, user_id)
        if recipient is None:
            raise HTTPException(status_code=404, detail={"error": "unknown agent"})
        node = _node_of(recipient)
        if node is None:
            text, err, label = None, f"node {recipient['node']} is not connected", None
        else:
            text, err = node.capture(recipient["tmux_pane"], recipient.get("tmux_server"))
            snap = _try_snapshot(node)
            label = snap.label(recipient["tmux_pane"]) if snap else None
        return {
            "user_id": user_id,
            "tmux_pane": recipient["tmux_pane"],
            "pane_label": label or recipient.get("pane_label") or recipient["tmux_pane"],
            "text": text,
            "error": err,
        }

    return app


def _run() -> None:
    """Console-script entry: `agent-swarm-server` starts uvicorn on 127.0.0.1:8765.

    The app is built here, not at import: building it opens the database and
    runs the startup reconciliation, which must happen in the one process
    that serves it, never in a test or a tool that merely imports this module.
    """
    import uvicorn

    port = int(
        os.environ.get("AGENT_SWARM_PORT", os.environ.get("AGENT_MSG_PORT", "8765"))
    )
    host = os.environ.get(
        "AGENT_SWARM_HOST", os.environ.get("AGENT_MSG_HOST", "127.0.0.1")
    )
    # No proxy-header rewriting: request.client must be the real socket peer,
    # since the auth middleware decides trust by it.
    uvicorn.run(create_app(), host=host, port=port, reload=False, proxy_headers=False)
