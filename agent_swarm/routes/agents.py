"""Agent registration, lifecycle, metadata, and terminal routes."""

from __future__ import annotations

import threading
import time
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .. import db, handoff, model_switch, names, nodes, restart, restore, tmux
from ..server import ActorFields, OWNER, _protocol_brief, log

RESTART_WAIT = 30.0


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


class OwnerNoteReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=1000)


class StatusReq(ActorFields):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=200)


class RestartReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = False
    dry_run: bool = True


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


def register_routes(
    app: FastAPI, *, _actor, _agent_or_404, _annotated_recipients, _blocking_prompt_error, _caller,
    _claimed_node, _is_alive, _live_elsewhere, _node_of, _node_or_422, _offline, _pane_ref,
    _refresh_watch, _require_owner, _resolve_caller, _stale, _try_snapshot, conn, fleet, registry,
) -> None:
    retirement_lock = threading.Lock()
    restart_lock = threading.Lock()
    restarting: set[str] = set()

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

    def _node_failure(error: str, result) -> HTTPException:
        """502 when the node's outcome is unknown, 500 when it reported failure."""
        return HTTPException(
            status_code=502 if result.status == "unknown" else 500,
            detail={"error": error, "status": result.status, "detail": result.error},
        )

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
