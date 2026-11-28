"""Task management routes and assignment notifications."""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import ConfigDict, Field

from .. import attachments, db
from ..server import ActorFields, NOTE_GUIDANCE, _read_json


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


def register_routes(
    app: FastAPI, *, _actor, _deliver_as, _require_owner, attachments_root, conn, fleet,
) -> None:
    def _notify_assignment(task: dict, actor: str):
        def team_line(user_id: str) -> str:
            """Which team to report progress to, unless the assignee is its queen.

            The queen counts even when she is offline: she is who to report to.
            The other members are left to `buzz team`.
            """
            recipient = db.get_recipient(conn, user_id)
            team = recipient and recipient.get("team_id") and db.get_team(conn, recipient["team_id"])
            if not team or team.get("queen") == user_id:
                return ""
            if team.get("queen"):
                return f" Team '{team['name']}'; queen {team['queen']}: report progress to them."
            return f" Team '{team['name']}' (no queen)."

        tid = task["id"]
        hint = (
            f"Work on branch task/{tid} in its own git worktree. Start: buzz "
            f"task-update {tid} --worktree /absolute/path --status picked_up. "
            f"Keep `buzz status` current (\"testing #{tid}\", \"waiting on "
            f"review\"); end with \"done: #{tid}\". Close: buzz task-update {tid} "
            f"--status done --note \"...\" (the note is required)."
        )
        content = f"You are assigned task #{task['id']}: {task['title']}."
        if task.get("description"):
            content += f" Details: {task['description']}."
        content += f" {hint}{team_line(task['assignee'])}"
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
                f"Task #{task['id']} for your team '{team['name']}': "
                f"{task['title']}.{detail} As queen, parcel it out with buzz "
                f"task-update {task['id']} --assignee <member>, then keep an eye on it."
            )
            targets = [team["queen"]]
        else:
            content = (
                f"Task #{task['id']} for your team '{team['name']}' (no queen yet): "
                f"{task['title']}.{detail} Whoever takes it: buzz task-update "
                f"{task['id']} --assignee <yourself>."
            )
            targets = team["members"]
        for target in targets:
            try:
                _deliver_as(actor, target, content, context, task.get("attachments") or [])
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
        return _read_json({"tasks": db.list_tasks(conn)})

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
            kwargs["depends_on"] = req.depends_on or []
        try:
            task = db.update_task(conn, task_id, **kwargs)
        except db.TaskNoteRequired as exc:
            raise HTTPException(status_code=422, detail={"error": str(exc), "note": NOTE_GUIDANCE}) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
        if task is None:
            raise HTTPException(status_code=404, detail={"error": "unknown task"})
        if task["assignee"] and task["assignee"] != before["assignee"]:
            _notify_assignment(task, actor)
        elif task["team_id"] and task["team_id"] != before["team_id"]:
            _notify_team_assignment(task, actor)
        return {"ok": True, "task": task}
