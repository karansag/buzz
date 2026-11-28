"""Messaging, chat history, and attachment routes."""

from __future__ import annotations

import asyncio

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from .. import attachments, db, notifications
from ..server import ActorFields, OWNER, _read_json


class PinReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pinned: bool


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


class NotifyReq(ActorFields):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=notifications.MAX_TEXT_LENGTH)
    context: str | None = None


def register_routes(
    app: FastAPI, *, _caller, _claimed_node, _deliver_as, _dispatch, _find_team,
    _missing_recipient, _reach, _replayed, _require_owner, attachments_root, conn,
) -> None:
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
