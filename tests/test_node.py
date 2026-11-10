"""The node daemon: executing commands idempotently, and reporting its tmux."""

import asyncio
import hashlib
import json
import time

import pytest

from agent_swarm import config, node, nodes, protocol, tmux


class FakeLocal(nodes.LocalNode):
    """A LocalNode whose tmux is a script: every call is recorded, results are canned."""

    def __init__(self, name="laptop", **results):
        super().__init__(name)
        self.calls = []
        self.results = results
        self.server = "srv-1"

    def server_id(self):
        return self.server

    def snapshot(self):
        table = self.results.get("table", {})
        return nodes.PaneSnapshot(
            self.server, 1.0, frozenset(table),
            frozenset(p for p, r in table.items() if r["command"] not in tmux.SHELL_COMMANDS), table,
        )

    def resolve(self, target):
        self.calls.append(("resolve", target))
        r = self.results.get("resolve")
        return nodes.Resolved(r[0], r[1], self.server) if r else None

    def capture(self, pane, tmux_server, colors=False):
        self.calls.append(("capture", pane, tmux_server, colors))
        return self.results.get("capture", ("screen", None))

    def deliver(self, op_id, pane, tmux_server, text, **kw):
        self.calls.append(("deliver", op_id, pane, tmux_server, text, kw))
        return self.results.get("deliver", nodes.Result("ok"))

    def spawn(self, op_id, command, cwd=None, resume=False):
        self.calls.append(("spawn", op_id, command))
        return self.results.get("spawn", nodes.Spawned("ok", "%7"))

    def kill(self, op_id, pane, tmux_server):
        self.calls.append(("kill", op_id, pane, tmux_server))
        return nodes.Result("ok")

    def send_key(self, op_id, pane, tmux_server, key):
        self.calls.append(("send_key", op_id, pane, tmux_server, key))
        return nodes.Result("ok")

    def tag_pane(self, op_id, pane, tmux_server, handle):
        self.calls.append(("tag_pane", op_id, pane, tmux_server, handle))
        return nodes.Result("ok")

    def rename_window(self, op_id, pane, tmux_server, name):
        self.calls.append(("rename_window", op_id, pane, tmux_server, name))
        return nodes.Result("ok")


@pytest.fixture()
def executor(tmp_path):
    local = FakeLocal()
    store = node.OpStore(tmp_path / "ops.sqlite")
    return node.Executor(local, store, attachment_path=lambda name, budget: tmp_path / "att" / name), local, store


def test_executor_runs_each_kind_and_reports_a_result(executor):
    ex, local, _ = executor
    now = time.monotonic()
    r = ex.run(protocol.command("m1", "deliver", 30, pane="%1", tmux_server="srv-1", text="hi", flavor="codex"), now)
    assert r == protocol.result("m1", "ok")
    assert local.calls[-1][:4] == ("deliver", "m1", "%1", "srv-1")
    assert local.calls[-1][5]["flavor"] == "codex"
    local.results["spawn"] = nodes.Spawned("ok", "%7", label="agents:3.0", tmux_server="srv-1")
    r = ex.run(protocol.command("s1", "spawn", 30, command="claude"), now)
    assert r["status"] == "ok" and r["data"] == {"pane": "%7", "label": "agents:3.0", "tmux_server": "srv-1"}
    local.results["resolve"] = ("%7", "agents:3.0")
    assert ex.run(protocol.command("k1", "kill", 30, pane="%7", tmux_server="srv-1"), now)["status"] == "ok"
    assert ex.run(protocol.command("e1", "send_key", 30, pane="%7", tmux_server="srv-1", key="Up"), now)["status"] == "ok"
    assert local.calls[-1] == ("send_key", "e1", "%7", "srv-1", "Up")
    assert ex.run(protocol.command("t1", "tag_pane", 30, pane="%7", tmux_server="srv-1", handle="otter"), now)["status"] == "ok"
    assert ex.run(protocol.command("w1", "rename_window", 30, pane="%7", tmux_server="srv-1", name="otter"), now)["status"] == "ok"
    r = ex.run(protocol.command("c1", "capture", 30, pane="%7", tmux_server="srv-1"), now)
    assert r["status"] == "ok" and r["data"] == {"text": "screen"}
    assert local.calls[-1] == ("capture", "%7", "srv-1", False)
    ex.run(protocol.command("c2", "capture", 30, pane="%7", tmux_server="srv-1", colors=True), now)
    assert local.calls[-1] == ("capture", "%7", "srv-1", True)  # the dashboard's terminal view
    r = ex.run(protocol.command("r1", "resolve", 30, target="agents:3.0"), now)
    assert r["data"] == {"pane": "%7", "label": "agents:3.0", "tmux_server": "srv-1"}
    local.results["resolve"] = None
    assert ex.run(protocol.command("r2", "resolve", 30, target="nope"), now)["data"] == {"pane": None, "label": None, "tmux_server": None}
    assert ex.run({"op_id": "x", "kind": "reboot", "ttl": 1}, now)["status"] == "failed"


def test_a_resent_mutating_command_returns_the_earlier_result_without_acting(executor):
    ex, local, store = executor
    now = time.monotonic()
    cmd = protocol.command("m1", "deliver", 30, pane="%1", tmux_server="srv-1", text="hi")
    first = ex.run(cmd, now, hub_id="hub-a")
    assert ex.run(cmd, now, hub_id="hub-a") == first
    assert [c for c in local.calls if c[0] == "deliver"] == [local.calls[0]]
    # The store survives a daemon restart.
    assert node.OpStore(store.path).get("hub-a:m1") == first
    # The same op id from another hub, or with other arguments, is not the same command.
    ex.run(cmd, now, hub_id="hub-b")
    assert len([c for c in local.calls if c[0] == "deliver"]) == 2
    other = protocol.command("m1", "deliver", 30, pane="%1", tmux_server="srv-1", text="different")
    r = ex.run(other, now, hub_id="hub-a")
    assert r["status"] == "failed" and "reused" in r["error"]
    # Read-only commands are never deduplicated.
    ex.run(protocol.command("c1", "capture", 30, pane="%1"), now)
    ex.run(protocol.command("c1", "capture", 30, pane="%1"), now)
    assert len([c for c in local.calls if c[0] == "capture"]) == 2


def test_two_copies_of_one_command_at_once_run_it_once(executor):
    import threading

    ex, local, _ = executor
    started, release = threading.Event(), threading.Event()
    results = []

    def slow_deliver(op_id, pane, tmux_server, text, **kw):
        started.set()
        release.wait(5)
        local.calls.append(("deliver", op_id))
        return nodes.Result("ok")

    local.deliver = slow_deliver
    cmd = protocol.command("m1", "deliver", 30, pane="%1", tmux_server="srv-1", text="hi")
    t = threading.Thread(target=lambda: results.append(ex.run(cmd, time.monotonic())))
    t.start()
    assert started.wait(5)
    # The second copy is claimed away while the first is inside tmux.
    dup = ex.run(cmd, time.monotonic())
    assert dup["status"] == "unknown" and "in flight" in dup["error"]
    release.set()
    t.join(5)
    assert results[0]["status"] == "ok"
    assert [c for c in local.calls if c[0] == "deliver"] == [("deliver", "m1")]
    # Once settled, a further copy gets the real result.
    assert ex.run(cmd, time.monotonic()) == results[0]


def test_a_claim_left_in_flight_by_a_crash_is_unknown_and_never_run(tmp_path):
    store = node.OpStore(tmp_path / "ops.sqlite")
    args = {"pane": "%1", "text": "hi"}
    assert store.claim("hub:m1", node.fingerprint("deliver", args)) == ("new", None)
    # ...the daemon dies between the paste and settling the result...
    reopened = node.OpStore(tmp_path / "ops.sqlite")
    assert reopened.abandon_in_flight("node restarted") == 1
    local = FakeLocal()
    ex = node.Executor(local, reopened)
    r = ex.run(protocol.command("m1", "deliver", 30, pane="%1", text="hi"), time.monotonic(), hub_id="hub")
    assert r["status"] == "unknown" and "node restarted" in r["error"]
    assert local.calls == []


def test_a_command_that_waited_past_its_ttl_expires_instead_of_running(executor):
    ex, local, store = executor
    received = time.monotonic() - 10
    cmd = protocol.command("m1", "deliver", 5, pane="%1", text="late")
    r = ex.run(cmd, received)
    assert r["status"] == "failed" and "expired" in r["error"]
    assert not any(c[0] == "deliver" for c in local.calls)
    # Nothing touched tmux, so the claim is released: a fresh resend may run.
    assert store.get("hub:m1") is None
    assert ex.run(cmd, time.monotonic())["status"] == "ok"


def test_expiry_is_judged_after_attachments_are_fetched(executor, tmp_path, monkeypatch):
    ex, local, _ = executor
    clock = {"now": 100.0}
    monkeypatch.setattr(node.time, "monotonic", lambda: clock["now"])

    def slow_fetch(name, budget):
        assert budget == pytest.approx(5.0)
        clock["now"] = 120.0  # the fetch took longer than the command had
        return tmp_path / name

    ex.attachment_path = slow_fetch
    r = ex.run(protocol.command("m1", "deliver", 5, pane="%1", text="see", attachments=["a.png"]), 100.0)
    assert r["status"] == "failed" and "expired" in r["error"]
    assert not any(c[0] == "deliver" for c in local.calls)


def test_a_command_from_an_ended_session_does_not_run(executor):
    ex, local, _ = executor
    r = ex.run(protocol.command("m1", "deliver", 30, pane="%1", text="hi"), time.monotonic(), still_valid=lambda: False)
    assert r["status"] == "failed" and "session ended" in r["error"]
    assert local.calls == []


def test_an_exception_during_a_command_is_unknown(executor):
    ex, local, _ = executor

    def boom(*a, **k):
        raise RuntimeError("tmux went away")

    local.deliver = boom
    r = ex.run(protocol.command("m1", "deliver", 30, pane="%1", text="hi"), time.monotonic())
    assert r["status"] == "unknown" and "RuntimeError" in r["error"]


def test_attachments_are_fetched_before_the_paste_and_a_missing_one_fails_cleanly(executor, tmp_path):
    ex, local, _ = executor
    (tmp_path / "att").mkdir()
    (tmp_path / "att" / "a.png").write_bytes(b"x")

    def path_for(name):
        p = tmp_path / "att" / name
        if not p.exists():
            raise ValueError(f"{name}: hub answered 404")
        return p

    now = time.monotonic()
    ex.attachment_path = lambda name, budget: path_for(name)
    r = ex.run(protocol.command("m1", "deliver", 30, pane="%1", text="see", attachments=["a.png"]), now)
    assert r["status"] == "ok"
    assert local.calls[-1][4] == f"see\n\n[attached image: {tmp_path / 'att' / 'a.png'}]"
    r = ex.run(protocol.command("m2", "deliver", 30, pane="%1", text="see", attachments=["b.png"]), now)
    assert r["status"] == "failed" and "attachment unavailable" in r["error"]
    assert local.calls[-1][1] == "m1"  # nothing was pasted for m2


def test_attachment_cache_verifies_what_it_fetches(tmp_path, monkeypatch):
    png = b"\x89PNG\r\n\x1a\n" + b"rest"
    name = hashlib.sha256(png).hexdigest() + ".png"
    served = {name: png}

    from contextlib import contextmanager

    class R:
        def __init__(self, content, ok=True):
            self.content, self.is_success, self.status_code = content, ok, 200 if ok else 404

        def iter_bytes(self):
            yield from (self.content[i:i + 4] for i in range(0, len(self.content), 4))

    seen = []

    @contextmanager
    def stream(method, url, headers, timeout):
        seen.append((url, headers))
        n = url.rsplit("/", 1)[1]
        yield R(served[n]) if n in served else R(b"", False)

    monkeypatch.setattr(node.httpx, "stream", stream)
    cache = node.AttachmentCache(tmp_path / "cache", "http://hub:8765/", "tok")
    path = cache.path_for(name)
    assert path.read_bytes() == png
    assert seen == [(f"http://hub:8765/attachments/{name}", {"Authorization": "Bearer tok"})]
    cache.path_for(name)
    assert len(seen) == 1  # cached
    with pytest.raises(ValueError, match="404"):
        cache.path_for("0" * 64 + ".png")
    served["0" * 64 + ".png"] = png
    with pytest.raises(ValueError, match="does not match"):
        cache.path_for("0" * 64 + ".png")
    with pytest.raises(ValueError, match="malformed"):
        cache.path_for("../etc/passwd")
    served["1" * 64 + ".png"] = b"\x89PNG\r\n\x1a\n" + b"x" * (node.attachments.MAX_BYTES + 1)
    with pytest.raises(ValueError, match="larger"):
        cache.path_for("1" * 64 + ".png")


class FakeSocket:
    """Enough of a websocket for Daemon.session: frames in, frames out."""

    def __init__(self, incoming):
        self.sent = []
        self.incoming = asyncio.Queue()
        for frame in incoming:
            self.incoming.put_nowait(json.dumps(frame))
        self.closed = asyncio.Event()

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        return await self.incoming.get()

    def __aiter__(self):
        return self

    async def __anext__(self):
        raw = await self.incoming.get()
        if raw is None:
            raise StopAsyncIteration
        return raw

    def end(self):
        self.incoming.put_nowait(None)


def test_daemon_session_says_hello_observes_and_answers_commands(tmp_path, monkeypatch):
    local = FakeLocal(table={"%1": {"label": "a:0.0", "command": "claude", "title": ""},
                             "%2": {"label": "a:0.1", "command": "bash", "title": ""}})
    ex = node.Executor(local, node.OpStore(tmp_path / "ops.sqlite"))
    monkeypatch.setattr(node, "harnesses_here", lambda: ["claude"])
    monkeypatch.setattr(node, "package_version", lambda: "0.1.0-test")
    monkeypatch.setenv("AGENT_SWARM_SPAWN_DIRS", "~/agents, ~/marin")
    settings = config.Settings("http://hub:8765", "tok", "laptop")
    daemon = node.Daemon(settings, ex, interval=100)
    assert daemon.ws_url == "ws://hub:8765/nodes/ws"
    ws = FakeSocket([
        protocol.welcome(100, [{"pane": "%1", "tmux_server": "srv-1"}, {"pane": "%2", "tmux_server": "srv-1"}], 7, "hub-x"),
        protocol.command("m1", "deliver", 30, pane="%1", tmux_server="srv-1", text="hi"),
    ])

    async def run():
        task = asyncio.create_task(daemon.session(ws))
        for _ in range(100):
            await asyncio.sleep(0.01)
            if any(f["type"] == "result" for f in ws.sent) and any(f["type"] == "observe" for f in ws.sent):
                break
        # A later watch frame changes what the next observation captures.
        ws.incoming.put_nowait(json.dumps(protocol.watch([])))
        for _ in range(100):
            await asyncio.sleep(0.01)
            if daemon.watched == {}:
                break
        ws.end()
        await task  # the socket closing ends the session cleanly; run_forever redials

    asyncio.run(run())
    types = [f["type"] for f in ws.sent]
    assert types[0] == "hello"
    assert ws.sent[0]["node"] == "laptop" and ws.sent[0]["harnesses"] == ["claude"]
    assert ws.sent[0]["spawn_dirs"] == ["~/agents", "~/marin"]
    assert ws.sent[0]["tmux_server"] == "srv-1" and ws.sent[0]["protocol"] == protocol.PROTOCOL
    observe = next(f for f in ws.sent if f["type"] == "observe")
    assert observe["tmux_server"] == "srv-1" and set(observe["table"]) == {"%1", "%2"}
    assert observe["captures"] == {"%1": "screen"}  # only live watched panes are captured
    result = next(f for f in ws.sent if f["type"] == "result")
    assert result["op_id"] == "m1" and result["status"] == "ok"
    assert daemon.watched == {}  # the watch frame was applied
    assert daemon.hub_id == "hub-x" and daemon.generation == 7
    assert daemon.current_session.ended  # for good
    assert ex.store.get("hub-x:m1") == result


def test_daemon_reports_an_unavailable_tmux_as_nothing_known(tmp_path):
    local = FakeLocal()

    def snapshot():
        raise nodes.Unavailable("restarting")

    local.snapshot = snapshot
    daemon = node.Daemon(config.Settings("http://hub", None, "laptop"), node.Executor(local, node.OpStore(tmp_path / "o.sqlite")))
    frame = daemon.observation()
    assert frame["table"] is None and frame["unavailable"] == "restarting"


def test_a_command_queued_behind_a_busy_pane_does_not_run_after_its_session_ends(tmp_path):
    import threading

    local = FakeLocal(table={"%1": {"label": "a:0.0", "command": "claude", "title": ""}})
    started, release = threading.Event(), threading.Event()
    delivered = []

    def slow_deliver(op_id, pane, tmux_server, text, **kw):
        delivered.append(op_id)
        started.set()
        release.wait(5)
        return nodes.Result("ok")

    local.deliver = slow_deliver
    ex = node.Executor(local, node.OpStore(tmp_path / "ops.sqlite"))
    daemon = node.Daemon(config.Settings("http://hub", None, "laptop"), ex, interval=100)
    first = FakeSocket([
        protocol.welcome(100, [], 1, "hub"),
        protocol.command("m1", "deliver", 30, pane="%1", text="one"),
        protocol.command("m2", "deliver", 30, pane="%1", text="two"),  # queued behind m1
    ])

    async def run():
        session = asyncio.create_task(daemon.session(first))
        await asyncio.to_thread(started.wait, 5)
        await asyncio.sleep(0.05)
        first.end()  # the socket drops while m1 is inside tmux and m2 waits
        await session
        # A new session begins before m1 finishes.
        second = FakeSocket([protocol.welcome(100, [], 2, "hub")])
        session2 = asyncio.create_task(daemon.session(second))
        await asyncio.sleep(0.05)
        release.set()
        await asyncio.sleep(0.2)
        second.end()
        await session2

    asyncio.run(run())
    assert delivered == ["m1"]  # m2 never touched tmux
    assert ex.store.get("hub:m1")["status"] == "ok"  # m1's result is kept for a resend
    assert ex.store.get("hub:m2") is None  # m2's claim was released


def test_admission_is_bounded(tmp_path):
    import threading

    local = FakeLocal(table={})
    gate = threading.Event()
    local.deliver = lambda *a, **k: (gate.wait(5), nodes.Result("ok"))[1]
    ex = node.Executor(local, node.OpStore(tmp_path / "ops.sqlite"))
    daemon = node.Daemon(config.Settings("http://hub", None, "laptop"), ex, interval=100, max_queued=2)
    ws = FakeSocket([
        protocol.welcome(100, [], 1, "hub"),
        protocol.command("m1", "deliver", 30, pane="%1", text="a"),
        protocol.command("m2", "deliver", 30, pane="%1", text="b"),
        protocol.command("m3", "deliver", 30, pane="%1", text="c"),
    ])

    async def run():
        task = asyncio.create_task(daemon.session(ws))
        for _ in range(100):
            await asyncio.sleep(0.01)
            if any(f["type"] == "result" and f["op_id"] == "m3" for f in ws.sent):
                break
        gate.set()
        await asyncio.sleep(0.1)
        ws.end()
        await task

    asyncio.run(run())
    refused = next(f for f in ws.sent if f["type"] == "result" and f["op_id"] == "m3")
    assert refused["status"] == "failed" and "busy" in refused["error"]


def test_a_reused_hub_generation_cannot_revive_a_command_from_an_ended_session(tmp_path):
    import threading

    local = FakeLocal(table={"%1": {"label": "a:0.0", "command": "claude", "title": ""}})
    delivered = []
    local.deliver = lambda op_id, *a, **k: (delivered.append(op_id), nodes.Result("ok"))[1]
    fetching, release = threading.Event(), threading.Event()

    def slow_fetch(name, budget):
        fetching.set()
        release.wait(5)
        return tmp_path / name

    ex = node.Executor(local, node.OpStore(tmp_path / "ops.sqlite"), attachment_path=slow_fetch)
    daemon = node.Daemon(config.Settings("http://hub", None, "laptop"), ex, interval=100)
    first = FakeSocket([
        protocol.welcome(100, [], 1, "hub"),
        protocol.command("m1", "deliver", 60, pane="%1", text="one", attachments=["a.png"]),
    ])

    async def run():
        session = asyncio.create_task(daemon.session(first))
        await asyncio.to_thread(fetching.wait, 5)
        first.end()  # the socket drops while m1 is still fetching its attachment
        await session
        # The hub restarted: its generation counter starts over at 1.
        second = FakeSocket([protocol.welcome(100, [], 1, "hub")])
        session2 = asyncio.create_task(daemon.session(second))
        await asyncio.sleep(0.05)
        release.set()
        await asyncio.sleep(0.2)
        second.end()
        await session2

    asyncio.run(run())
    assert delivered == []
    assert ex.store.get("hub:m1") is None  # never touched tmux, so the claim was released


def test_attachment_fetch_gives_up_when_its_budget_runs_out(tmp_path, monkeypatch):
    from contextlib import contextmanager

    clock = {"now": 0.0}
    monkeypatch.setattr(node.time, "monotonic", lambda: clock["now"])

    class Trickle:
        is_success, status_code = True, 200

        def iter_bytes(self):
            while True:
                clock["now"] += 1.0
                yield b"x"

    @contextmanager
    def stream(method, url, headers, timeout):
        yield Trickle()

    monkeypatch.setattr(node.httpx, "stream", stream)
    cache = node.AttachmentCache(tmp_path / "cache", "http://hub", None)
    with pytest.raises(ValueError, match="budget"):
        cache.path_for("0" * 64 + ".png", budget=3.0)
    assert clock["now"] <= 5.0


def test_a_spawn_command_starts_in_the_folder_it_names(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SWARM_SPAWN_DIRS", "~/agents")
    seen = []
    monkeypatch.setattr(
        tmux, "spawn_window",
        lambda session=None, command=None, cwd=None: (seen.append(cwd), (tmux.Created("%5", "a:1.0", "srv-1"), None))[1],
    )
    ex = node.Executor(nodes.LocalNode("laptop"), node.OpStore(tmp_path / "ops.sqlite"))
    ok = ex.run(protocol.command("s1", "spawn", 30, command="claude", cwd="~/agents"), time.monotonic())
    assert ok["status"] == "ok" and seen == ["~/agents"]
    # A folder this machine did not list is refused here too, whatever the hub sent.
    no = ex.run(protocol.command("s2", "spawn", 30, command="claude", cwd="/etc"), time.monotonic())
    assert no["status"] == "failed" and "not a start folder" in no["error"] and seen == ["~/agents"]
