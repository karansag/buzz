"""Dashboard, health, and proxied tab routes."""

from __future__ import annotations

import hashlib
import time

import anyio
import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from .. import boards, db, server
from ..server import OWNER, _read_json, extra_tabs


def register_routes(
    app: FastAPI, *, conn, db_path, fleet,
    _require_owner, _recipients_with_activity, _agent_or_404, _node_of,
) -> None:
    @app.get("/health")
    def health():
        return {"ok": True, "db": str(db_path)}

    @app.get("/", response_class=HTMLResponse)
    def portal(_: None = Depends(_require_owner)):
        # Asset filenames are stable across builds. Version their URLs by
        # content so a normal refresh cannot reuse an older JS/CSS bundle.
        page = server.PORTAL_PATH.read_text()
        for name in ("portal.js", "portal.css"):
            digest = hashlib.sha256((server.PORTAL_STATIC_PATH / name).read_bytes()).hexdigest()[:16]
            page = page.replace(f'"/static/{name}"', f'"/static/{name}?v={digest}"')
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})

    @app.get("/api/state")
    def state(limit: int = 300, _: None = Depends(_require_owner)):
        # All summaries that are kept, so the history search finds older lines too.
        summaries = db.summaries_by_user(conn, db.SUMMARY_HISTORY)
        recipients = _recipients_with_activity(summaries)
        msgs = db.fetch_messages(conn, None, limit)
        msgs.reverse()  # oldest first for thread rendering
        enrolled = db.list_nodes(conn)
        for n in enrolled:
            live = fleet.get(n["name"])
            n["connected"] = live is not None
            n["spawn_dirs"] = live.spawn_dirs if live is not None else []
        local = {"name": fleet.local.name, "local": True, "connected": True,
                 "spawn_dirs": fleet.local.spawn_dirs}
        teams = db.list_teams(conn)
        for team in teams:
            team["board_unread"] = boards.unread_count(conn, team["id"], OWNER)
        return _read_json({
            "now": time.time(),
            "recipients": recipients,
            "retired_agents": [
                {"archive_id": r["archive_id"], "original_id": r["original_id"],
                 "retired_at": r["retired_at"], "summaries": summaries.get(r["archive_id"], [])}
                for r in db.retired_agents(conn)
            ],
            "nodes": [local, *enrolled],
            "messages": msgs,
            "pins": db.list_pins(conn),
            "tasks": db.list_tasks(conn),
            "teams": teams,
            "supervisor": db.get_supervisor(conn),
            "tabs": [t["name"] for t in extra_tabs()],
        })

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

    # Peeking should still work when slow sends or switches occupy the
    # default worker pool. Bound captures separately so repeated polls
    # cannot create an unbounded number of workers.
    peek_workers = anyio.CapacityLimiter(8)

    def _capture_peek(user_id: str) -> dict:
        recipient = _agent_or_404(user_id)
        node = _node_of(recipient)
        pane = recipient["tmux_pane"]
        if node is None:
            text, err = None, f"node {recipient['node']} is not connected"
        else:
            text, err = node.capture(pane, recipient.get("tmux_server"), colors=True)
        return {
            "user_id": user_id,
            "tmux_pane": pane,
            "pane_label": recipient.get("pane_label") or pane,
            "text": text,
            "error": err,
        }

    @app.get("/api/peek/{user_id}")
    async def peek(user_id: str, request: Request):
        # The owner check is in-memory. A sync dependency would still queue
        # behind the same default workers before reaching the capture pool.
        _require_owner(request)
        return await anyio.to_thread.run_sync(_capture_peek, user_id, limiter=peek_workers)
