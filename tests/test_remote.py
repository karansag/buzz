"""The hub end of a node's socket: auth on the handshake, commands as futures,
observations as snapshots, fencing when a connection is replaced or dropped."""

import threading
import time
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agent_swarm import nodes, protocol, server, tmux


@pytest.fixture()
def hub(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SWARM_MONITOR_INTERVAL", "0.2")
    monkeypatch.setattr(tmux, "server_id", lambda: "hub-srv")
    monkeypatch.setattr(tmux, "resolve_pane", lambda t: (t, t))
    monkeypatch.setattr(tmux, "pane_table", lambda: {})
    monkeypatch.setattr(nodes, "DELIVER_TTL", 1.0)
    monkeypatch.setattr(nodes, "COMMAND_TTL", 1.0)
    app = server.create_app(tmp_path / "db.sqlite", monitor=False)
    owner = TestClient(app, client=("127.0.0.1", 40000))
    token = owner.post("/nodes/macbook/token").json()["token"]
    return app, owner, token


TABLE = {"%1": {"label": "a:0.0", "command": "claude", "title": "✳ working"}}


@contextmanager
def connect(owner, token, name="macbook", hello=None):
    """An accepted node socket that has said hello; the welcome is left to read."""
    with owner.websocket_connect("/nodes/ws", headers={"Authorization": f"Bearer {token}"}) as ws:
        ws.send_json(hello or protocol.hello(name, "0.1.0", "mac-srv", ["claude"]))
        yield ws


def in_thread(fn):
    """Run an HTTP call that will block on the socket in another thread."""
    out = {}

    def run():
        try:
            out["value"] = fn()
        except Exception as e:  # noqa: BLE001 - surfaced by the test
            out["error"] = e

    t = threading.Thread(target=run)
    t.start()
    return t, out


def answer(ws, kind, **result):
    """Wait for the next command of `kind` on the socket and reply."""
    for _ in range(50):
        frame = ws.receive_json()
        if frame.get("type") == "command" and frame["kind"] == kind:
            ws.send_json(protocol.result(frame["op_id"], **result))
            return frame
    raise AssertionError(f"no {kind} command arrived")


def test_the_handshake_needs_the_nodes_token_and_a_matching_hello(hub):
    app, owner, token = hub
    with pytest.raises(WebSocketDisconnect):
        with owner.websocket_connect("/nodes/ws"):
            pass
    with pytest.raises(WebSocketDisconnect):
        with owner.websocket_connect("/nodes/ws", headers={"Authorization": "Bearer nope"}):
            pass
    with pytest.raises(WebSocketDisconnect):
        with connect(owner, token, hello=protocol.hello("laptop", "0.1.0", None, [])) as ws:
            ws.receive_json()
    assert app.state.nodes.get("macbook") is None


def test_a_connected_node_is_welcomed_observed_and_listed(hub):
    app, owner, token = hub
    with connect(owner, token) as ws:
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome" and welcome["watch"] == []
        assert welcome["interval"] == pytest.approx(0.2)
        node = app.state.nodes.get("macbook")
        assert isinstance(node, nodes.RemoteNode) and node.harnesses == ["claude"]
        listed = owner.get("/nodes").json()["nodes"][0]
        assert listed["connected"] is True and listed["version"] == "0.1.0"
        assert [n["name"] for n in owner.get("/api/state").json()["nodes"]] == [tmux.local_node(), "macbook"]
        with pytest.raises(nodes.Unavailable, match="not reported"):
            node.snapshot()
        ws.send_json(protocol.observe(1, "mac-srv", TABLE, {"%1": "the screen"}))
        for _ in range(50):
            time.sleep(0.01)
            if node._last:
                break
        snap = node.snapshot()
        assert snap.server == "mac-srv" and snap.live == {"%1"} and snap.title("%1") == "✳ working"
        assert node.capture("%1", "mac-srv") == ("the screen", None)
    for _ in range(50):
        time.sleep(0.01)
        if app.state.nodes.get("macbook") is None:
            break
    assert app.state.nodes.get("macbook") is None
    assert owner.get("/nodes").json()["nodes"][0]["connected"] is False


def test_registering_and_messaging_an_agent_on_a_node_goes_over_the_socket(hub):
    app, owner, token = hub
    remote = TestClient(app, client=("100.64.0.9", 1), headers={"Authorization": f"Bearer {token}"})
    with connect(owner, token) as ws:
        ws.receive_json()  # welcome
        ws.send_json(protocol.observe(1, "mac-srv", TABLE, {}))
        # Registering resolves the pane on the node, then tags it there.
        t, out = in_thread(lambda: remote.post(
            "/register", json={"tmux_pane": "a:0.0", "node": "macbook", "requested_user": "puffin"}
        ).json())
        resolve = answer(ws, "resolve", status="ok", pane="%1", label="a:0.0", tmux_server="mac-srv")
        assert resolve["args"] == {"target": "a:0.0"}
        tag = answer(ws, "tag_pane", status="ok")
        assert tag["args"]["pane"] == "%1" and tag["args"]["tmux_server"] == "mac-srv"
        t.join(5)
        assert out["value"]["user_id"] == "puffin" and out["value"]["tmux_pane"] == "%1"
        # The node is told to watch its new agent's pane.
        watch = ws.receive_json()
        assert watch == protocol.watch([{"pane": "%1", "tmux_server": "mac-srv"}])
        row = next(r for r in owner.get("/recipients").json()["recipients"] if r["user_id"] == "puffin")
        assert row["alive"] is True and row["node"] == "macbook"

        # A message from the owner becomes a deliver command carrying the message id.
        t, out = in_thread(lambda: owner.post("/owner/send", json={"recipient": "puffin", "content": "hello there"}).json())
        cmd = answer(ws, "deliver", status="ok")
        assert cmd["args"]["pane"] == "%1" and cmd["args"]["tmux_server"] == "mac-srv"
        assert cmd["args"]["text"].startswith("[agent-msg from owner] ")
        assert "hello there" in cmd["args"]["text"]
        assert cmd["ttl"] == 1.0
        t.join(5)
        assert out["value"]["status"] == "delivered"
        assert str(out["value"]["message_id"]) == cmd["op_id"]

        # The node's own uncertainty is kept as such.
        t, out = in_thread(lambda: owner.post("/owner/send", json={"recipient": "puffin", "content": "again"}).json())
        answer(ws, "deliver", status="unknown", error="submit key timed out")
        t.join(5)
        assert out["value"]["status"] == "unknown" and "submit key" in out["value"]["delivery_error"]

        # No answer within the ttl is unknown too, and nothing is resent.
        t, out = in_thread(lambda: owner.post("/owner/send", json={"recipient": "puffin", "content": "silence"}).json())
        cmd = ws.receive_json()
        assert cmd["kind"] == "deliver"
        t.join(10)
        assert out["value"]["status"] == "unknown" and "within" in out["value"]["delivery_error"]
        msgs = owner.get("/messages").json()["messages"]
        assert [m["status"] for m in msgs[:3]] == ["unknown", "unknown", "delivered"]


def test_a_dropped_connection_leaves_in_flight_deliveries_unknown_and_agents_offline(hub):
    app, owner, token = hub
    with connect(owner, token) as ws:
        ws.receive_json()
        ws.send_json(protocol.observe(1, "mac-srv", TABLE, {}))
        t, out = in_thread(lambda: owner.post("/register", json={"tmux_pane": "%1", "node": "macbook", "requested_user": "puffin"}).json())
        answer(ws, "resolve", status="ok", pane="%1", label="a:0.0", tmux_server="mac-srv")
        answer(ws, "tag_pane", status="ok")
        t.join(5)
        ws.receive_json()  # watch
        t, out = in_thread(lambda: owner.post("/owner/send", json={"recipient": "puffin", "content": "x"}).json())
        assert ws.receive_json()["kind"] == "deliver"
        # The socket closes before the node answers.
    t.join(5)
    assert out["value"]["status"] == "unknown" and "disconnected" in out["value"]["delivery_error"]
    for _ in range(50):
        time.sleep(0.01)
        if app.state.nodes.get("macbook") is None:
            break
    row = next(r for r in owner.get("/recipients").json()["recipients"] if r["user_id"] == "puffin")
    assert row["alive"] is False and "not connected" in row["offline_reason"]
    assert owner.post("/owner/send", json={"recipient": "puffin", "content": "y"}).status_code == 409


def test_a_silent_node_reads_as_unobservable(hub):
    app, owner, token = hub
    with connect(owner, token) as ws:
        ws.receive_json()
        ws.send_json(protocol.observe(1, "mac-srv", TABLE, {}))
        t, out = in_thread(lambda: owner.post("/register", json={"tmux_pane": "%1", "node": "macbook", "requested_user": "puffin"}).json())
        answer(ws, "resolve", status="ok", pane="%1", label="a:0.0", tmux_server="mac-srv")
        answer(ws, "tag_pane", status="ok")
        t.join(5)
        assert next(r for r in owner.get("/recipients").json()["recipients"] if r["user_id"] == "puffin")["alive"]
        time.sleep(0.2 * protocol.STALE_AFTER + 0.3)
        row = next(r for r in owner.get("/recipients").json()["recipients"] if r["user_id"] == "puffin")
        assert row["alive"] is False and "cannot observe" in row["offline_reason"]
        ws.send_json(protocol.observe(2, "mac-srv", None, {}, unavailable="tmux restarting"))
        time.sleep(0.05)
        assert not next(r for r in owner.get("/recipients").json()["recipients"] if r["user_id"] == "puffin")["alive"]


def test_a_newer_connection_replaces_and_fences_the_older(hub):
    app, owner, token = hub
    with connect(owner, token) as first:
        first.receive_json()
        older = app.state.nodes.get("macbook")
        with connect(owner, token) as second:
            second.receive_json()
            newer = app.state.nodes.get("macbook")
            assert newer is not older and newer.generation > older.generation
            assert older.fenced == "replaced by a newer connection"
            assert older.deliver("m", "%1", "mac-srv", "x").status == "unknown"
            # The hub closed the older socket.
            with pytest.raises(WebSocketDisconnect):
                first.receive_json()


def test_rotating_or_revoking_a_token_closes_its_connection(hub):
    app, owner, token = hub
    with connect(owner, token) as ws:
        ws.receive_json()
        node = app.state.nodes.get("macbook")
        owner.post("/nodes/macbook/token")
        assert node.fenced == "token rotated"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
        assert app.state.nodes.get("macbook") is None
    with pytest.raises(WebSocketDisconnect):
        with connect(owner, token) as ws:
            ws.receive_json()


def test_fencing_from_another_thread_settles_futures_on_the_loop_and_stops_late_sends():
    import asyncio

    sent = []
    hold = asyncio.Event()

    async def run():
        loop = asyncio.get_running_loop()

        async def send(frame):
            await hold.wait()  # the first send blocks, the rest queue behind the lock
            sent.append(frame)

        async def close():
            sent.append("closed")

        node = nodes.RemoteNode("macbook", 1, loop, send, close, interval=1.0)
        first = loop.create_task(node._submit(protocol.command("a", "capture", 1, pane="%1")))
        second = loop.create_task(node._submit(protocol.command("b", "capture", 1, pane="%1")))
        await asyncio.sleep(0.01)
        assert set(node._pending) == {"a", "b"}
        # Fence from a worker thread, as a token rotation does.
        await asyncio.to_thread(node.fence, "token rotated")
        assert node.fenced == "token rotated"
        await asyncio.sleep(0.01)  # the loop-side part runs
        assert node._pending == {}
        hold.set()
        results = await asyncio.gather(first, second)
        # "a" was mid-send; "b" never went out.
        assert [r["status"] for r in results] == ["unknown", "unknown"]
        assert [f for f in sent if f != "closed"] == [protocol.command("a", "capture", 1, pane="%1")]
        assert "closed" in sent
        # A watch push after the fence is dropped too.
        await node.push_watch([{"pane": "%1"}])
        assert not any(isinstance(f, dict) and f.get("type") == "watch" for f in sent)

    asyncio.run(run())


def test_a_call_that_gave_up_waiting_is_not_sent_late():
    import asyncio

    sent = []

    async def run():
        loop = asyncio.get_running_loop()
        hold = asyncio.Event()

        async def send(frame):
            await hold.wait()
            sent.append(frame)

        node = nodes.RemoteNode("macbook", 1, loop, send, lambda: asyncio.sleep(0), interval=1.0)
        blocker = loop.create_task(node._submit(protocol.command("x", "capture", 1, pane="%1")))
        await asyncio.sleep(0.01)
        # A caller times out and abandons "y" while "y" still waits for the lock.
        waiting = loop.create_task(node._submit(protocol.command("y", "capture", 1, pane="%1")))
        await asyncio.sleep(0.01)
        node._pending.pop("y")  # what _call does on timeout
        hold.set()
        node.resolved(protocol.result("x", "ok"))
        assert (await blocker)["status"] == "ok"
        assert (await waiting)["error"] == "abandoned before it was sent"
        assert [f["op_id"] for f in sent] == ["x"]

    asyncio.run(run())


def test_a_token_revoked_or_rotated_during_the_hello_window_is_refused(hub):
    app, owner, token = hub
    with owner.websocket_connect("/nodes/ws", headers={"Authorization": f"Bearer {token}"}) as ws:
        # Accepted on the old token; the hello has not been sent yet.
        assert owner.delete("/nodes/macbook").status_code == 200
        ws.send_json(protocol.hello("macbook", "0.1.0", "mac-srv", []))
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert app.state.nodes.get("macbook") is None
    token = owner.post("/nodes/macbook/token").json()["token"]
    with owner.websocket_connect("/nodes/ws", headers={"Authorization": f"Bearer {token}"}) as ws:
        owner.post("/nodes/macbook/token")  # rotated while the hello is pending
        ws.send_json(protocol.hello("macbook", "0.1.0", "mac-srv", []))
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert app.state.nodes.get("macbook") is None


def test_a_pane_is_paired_with_the_server_that_resolved_it_not_a_cached_one(hub):
    app, owner, token = hub
    remote = TestClient(app, client=("100.64.0.9", 1), headers={"Authorization": f"Bearer {token}"})
    with connect(owner, token) as ws:
        ws.receive_json()
        ws.send_json(protocol.observe(1, "mac-srv", TABLE, {}))
        t, out = in_thread(lambda: remote.post("/register", json={"tmux_pane": "%1", "node": "macbook", "requested_user": "puffin"}).json())
        answer(ws, "resolve", status="ok", pane="%1", label="a:0.0", tmux_server="mac-srv")
        answer(ws, "tag_pane", status="ok")
        t.join(5)
        ws.receive_json()  # watch
        # tmux restarts on the node. The next resolve reports the new server
        # while the hub's last observation still names the old one.
        t, out = in_thread(lambda: remote.get("/whoami", params={"tmux_pane": "%1", "node": "macbook"}).json())
        answer(ws, "resolve", status="ok", pane="%1", label="a:0.0", tmux_server="mac-srv-2")
        t.join(5)
        assert out["value"]["user_id"] is None  # the new %1 is not puffin
        t, out = in_thread(lambda: remote.post("/send", json={"tmux_pane": "%1", "node": "macbook", "recipient": "owner", "content": "x"}))
        answer(ws, "resolve", status="ok", pane="%1", label="a:0.0", tmux_server="mac-srv-2")
        t.join(5)
        assert out["value"].status_code == 404  # not registered under the new server
        # A resolve the node could not do coherently is a retryable 503.
        t, out = in_thread(lambda: remote.get("/whoami", params={"tmux_pane": "%1", "node": "macbook"}))
        answer(ws, "resolve", status="failed", error="tmux restarted while resolving the pane")
        t.join(5)
        assert out["value"].status_code == 503


def test_timed_out_calls_do_not_leak_and_late_results_are_dropped():
    import asyncio

    async def run():
        loop = asyncio.get_running_loop()
        sent = []

        async def send(frame):
            sent.append(frame)

        node = nodes.RemoteNode("macbook", 1, loop, send, lambda: asyncio.sleep(0), interval=1.0)
        before = len(asyncio.all_tasks())
        for i in range(5):
            r = await asyncio.to_thread(node._call, "capture", 0.05, None, pane="%1")
            assert r["status"] == "unknown" and "within" in r["error"]
        await asyncio.sleep(0.05)
        assert node._pending == {}
        assert len(asyncio.all_tasks()) == before
        # A result arriving after the caller gave up finds nothing waiting.
        node.resolved(protocol.result(sent[-1]["op_id"], "ok"))
        assert node._pending == {}
        node.fence("done")
        await asyncio.sleep(0.01)

    asyncio.run(run())


def test_a_node_reports_its_start_folders_and_a_spawn_names_one(hub):
    app, owner, token = hub
    hello = protocol.hello("macbook", "0.1.0", "mac-srv", ["claude"], ["~/agents", "~/marin"])
    with connect(owner, token, hello=hello) as ws:
        ws.receive_json()
        listed = next(n for n in owner.get("/api/state").json()["nodes"] if n["name"] == "macbook")
        assert listed["spawn_dirs"] == ["~/agents", "~/marin"]
        r = owner.post("/agents/spawn", json={"flavor": "claude", "node": "macbook", "cwd": "~/oa/marin"})
        assert r.status_code == 422  # the hub's own folders are not the Mac's
        t, out = in_thread(lambda: owner.post(
            "/agents/spawn", json={"flavor": "claude", "node": "macbook", "cwd": "~/marin"}))
        frame = answer(ws, "spawn", status="ok", pane="%4", label="agents:1.0", tmux_server="mac-srv")
        assert frame["args"]["cwd"] == "~/marin"
        t.join(5)
        # The window is tagged and renamed afterwards; answer those too if asked.
        assert out.get("error") is None
