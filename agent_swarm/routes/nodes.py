"""Node connections, enrollment, snapshots, and import routes."""

from __future__ import annotations

import asyncio
import secrets

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from .. import bundle, db, names, nodes, protocol
from ..server import log


class ImportReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node: str = Field(min_length=1, description="the machine these agents run on")
    bundle: dict = Field(description="what `buzz export` wrote on that machine")
    dry_run: bool = Field(default=False, description="decide and report, write nothing")
    again: bool = Field(
        default=False,
        description="take in a bundle that was imported before, duplicating what it carries",
    )
    merge_teams: bool = Field(
        default=False,
        description="add to a team of the same name here instead of importing it under a new one",
    )


class NodeSnapshotReq(BaseModel):
    snapshot: dict


def register_routes(
    app: FastAPI, *, _disconnect, _refresh_watch, _require_owner, _try_snapshot, _watch_list, conn,
    fleet, fleet_lock, interval,
) -> None:
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
                        "hint": "enrol it first with `buzz node-token`"},
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
        """What the hub takes the caller for; `buzz join` checks this."""
        p = request.state.principal
        return {"kind": p.kind, "node": p.node if p.kind == "node" else fleet.local.name}

    @app.post("/nodes/snapshot")
    def node_snapshot_post(req: NodeSnapshotReq, request: Request):
        """Keep the newest snapshot a machine posts, so the hub can hand it back.

        A node may only post its own; the owner (the hub's own timer, or a
        machine's `buzz snapshot`) may post for the node the snapshot names.
        """
        principal = request.state.principal
        snapshot = req.snapshot
        name = snapshot.get("node")
        if not isinstance(name, str) or not name:
            raise HTTPException(status_code=422, detail={"error": "a snapshot must name its node"})
        if principal.kind == "node":
            if name != principal.node:
                raise HTTPException(
                    status_code=403,
                    detail={"error": f"node {principal.node} may not post a snapshot for {name}"},
                )
        elif name != fleet.local.name and not any(n["name"] == name for n in db.list_nodes(conn)):
            # The owner posts the hub's own snapshot, or one from an enrolled node.
            raise HTTPException(status_code=404, detail={"error": f"unknown node {name}"})
        if not isinstance(snapshot.get("sessions"), list):
            raise HTTPException(status_code=422, detail={"error": "a snapshot needs its sessions"})
        db.save_node_snapshot(conn, name, snapshot)
        return {"ok": True, "node": name, "taken_at": snapshot.get("taken_at")}

    @app.get("/nodes/snapshot")
    def node_snapshot_get(request: Request, node: str | None = None):
        """The newest snapshot for a machine: a node asks for its own, the owner for any."""
        principal = request.state.principal
        if principal.kind == "node":
            if node and node != principal.node:
                raise HTTPException(
                    status_code=403,
                    detail={"error": f"node {principal.node} may not read the snapshot for {node}"},
                )
            wanted = principal.node
        else:
            wanted = node or fleet.local.name
        snapshot = db.node_snapshot(conn, wanted)
        if snapshot is None:
            raise HTTPException(
                status_code=404,
                detail={"error": f"the hub has no snapshot for {wanted}",
                        "hint": "a machine's buzz-node posts one every five minutes, and `buzz snapshot` posts one too"},
            )
        return snapshot

    @app.get("/nodes/snapshots")
    def node_snapshots_list(_: None = Depends(_require_owner)):
        """Which machines the hub holds a snapshot for, and when each was taken."""
        return {"snapshots": db.node_snapshot_names(conn), "local": fleet.local.name}

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
