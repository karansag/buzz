"""Team, board, supervisor, and digest routes."""

from __future__ import annotations

import time

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .. import boards, db, digest, team_view
from ..server import ActorFields, OWNER, _read_json


class BoardPostReq(ActorFields):
    body: str
    subject: str | None = Field(default=None, max_length=120)
    reply_to: int | None = Field(default=None, gt=0, le=2**63 - 1)
    client_id: str | None = Field(default=None, min_length=1, max_length=200)


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


def register_routes(
    app: FastAPI, *, _actor, _annotated_recipients, _deliver_as, _find_team,
    _recipients_with_activity, _require_owner, conn, fleet,
) -> None:
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
