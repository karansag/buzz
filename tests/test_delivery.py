"""The hub against a DeliveryBackend that is not tmux.

FakeBackend addresses agents by session id and can only deliver and report
liveness, so these tests show what the hub does through the interface alone
and what it refuses when a capability is missing.
"""

import pytest
from fastapi.testclient import TestClient

from agent_swarm import delivery, server
from agent_swarm.delivery import tmux_backend

EPOCH = "fake-epoch"


class FakeNode:
    name = "hub"
    spawn_dirs: list[str] = []

    def __init__(self):
        self.live: set[str] = set()
        self.known: set[str] = set()
        self.sent: list[tuple[str, str, str]] = []
        self.outcome = delivery.Result("ok")
        self.calls: list[str] = []

    def snapshot(self):
        table = {s: {"label": f"label-{s}", "command": "claude", "title": "", "cwd": ""}
                 for s in self.known | self.live}
        return delivery.PaneSnapshot(EPOCH, None, frozenset(table), frozenset(self.live), table)

    def server_id(self):
        return EPOCH

    def resolve(self, target):
        if target in self.known | self.live:
            return delivery.Resolved(target, f"label-{target}", EPOCH)
        return None

    def deliver(self, op_id, pane, tmux_server, text, **kwargs):
        self.sent.append((op_id, pane, text))
        return self.outcome

    def screen(self, pane, tmux_server):
        return None

    def tag_pane(self, op_id, pane, tmux_server, handle):
        return delivery.Result("ok")

    def __getattr__(self, name):
        # capture, send_key, spawn, respawn, kill, rename_window: the hub must not get this far.
        def refuse(*args, **kwargs):
            self.calls.append(name)
            raise AssertionError(f"the hub called {name} on a backend without that capability")
        return refuse


class FakeBackend(delivery.NodeRegistry):
    name = "fake"
    address_kind = "session"
    capabilities = delivery.Capabilities(deliver=True, liveness=True, inbound=True)

    def __init__(self):
        super().__init__(FakeNode())
        self.handler = None
        self.closed = False

    def offline_reason(self, address, snapshot, stale):
        if stale:
            return "recipient offline: registered under another backend"
        if address not in snapshot.live:
            return f"recipient offline: fake session {address} is not live"
        return None

    def arrival_note(self):
        return "Messages arrive by carrier pigeon."

    def on_inbound(self, handler):
        self.handler = handler

    def close(self):
        self.closed = True


@pytest.fixture()
def hub(tmp_path):
    backend = FakeBackend()
    app = server.create_app(tmp_path / "db.sqlite", monitor=False, backend=backend)
    client = TestClient(app, client=("127.0.0.1", 50000))
    client.backend, client.node = backend, backend.local
    return client


def register(hub, session, name):
    hub.node.live.add(session)
    r = hub.post("/register", json={"agent_id": session, "requested_user": name, "flavor": "claude"})
    assert r.status_code == 200, r.text
    return r.json()


def test_state_reports_the_backend_and_its_capabilities(hub):
    info = hub.get("/api/state").json()["delivery"]
    assert info["backend"] == "fake" and info["address"] == "session"
    assert info["capabilities"]["deliver"] is True
    assert info["capabilities"]["peek"] is False and info["capabilities"]["keys"] is False
    assert hub.get("/health").json()["delivery"] == {"backend": "fake", "address": "session"}


def test_the_tmux_backend_is_the_default_and_can_do_everything(tmp_path, monkeypatch):
    monkeypatch.delenv("BUZZ_DELIVERY", raising=False)
    app = server.create_app(tmp_path / "db.sqlite", monitor=False)
    assert isinstance(app.state.delivery, tmux_backend.TmuxBackend)
    info = TestClient(app, client=("127.0.0.1", 50000)).get("/api/state").json()["delivery"]
    assert info["backend"] == "tmux" and info["address"] == "pane"
    assert info["capabilities"] == {**info["capabilities"], "peek": True, "keys": True, "spawn": True,
                                    "restart": True, "stop": True, "remote_nodes": True,
                                    "activity": True, "liveness": True, "inbound": False}


def test_register_uses_the_session_id_as_the_address(hub):
    # A pane the CLI happened to detect is ignored, and so is the machine it names.
    hub.node.live.add("sess-1")
    r = hub.post("/register", json={"agent_id": "sess-1", "tmux_pane": "%7", "node": "some-laptop",
                                    "requested_user": "otter"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["user_id"], body["tmux_pane"], body["pane_label"], body["node"]) == (
        "otter", "sess-1", "label-sess-1", "hub")
    assert "carrier pigeon" in body["protocol_brief"] and "tmux pane" not in body["protocol_brief"]
    row = next(r for r in hub.get("/recipients").json()["recipients"] if r["user_id"] == "otter")
    assert row["alive"] is True and row["tmux_server"] == EPOCH


def test_register_needs_a_session_the_backend_can_see(hub):
    r = hub.post("/register", json={"tmux_pane": "%7"})
    assert r.status_code == 422 and "session id" in r.json()["detail"]["error"]
    r = hub.post("/register", json={"agent_id": "nobody"})
    assert r.status_code == 404 and "not visible to the fake backend" in r.json()["detail"]["error"]


def test_the_tmux_backend_still_needs_a_pane(tmp_path):
    app = server.create_app(tmp_path / "db.sqlite", monitor=False)
    r = TestClient(app, client=("127.0.0.1", 50000)).post("/register", json={"agent_id": "sess-1"})
    assert r.status_code == 422 and r.json()["detail"]["error"] == "tmux_pane is required"


def test_send_goes_through_the_backend_and_maps_its_result(hub):
    register(hub, "sess-1", "otter")
    register(hub, "sess-2", "tapir")
    # The caller is known by its session id; a stale pane claim changes nothing.
    r = hub.post("/send", json={"agent_id": "sess-1", "tmux_pane": "%9", "pane_in_tree": True,
                                "pane_verified": True, "recipient": "tapir", "content": "hello"})
    assert r.status_code == 200 and r.json()["status"] == "delivered"
    op_id, address, text = hub.node.sent[-1]
    assert address == "sess-2" and text == "[agent-msg from otter] hello"
    assert op_id == str(r.json()["message_id"])

    for outcome, status in (("failed", "failed"), ("unknown", "unknown")):
        hub.node.outcome = delivery.Result(outcome, f"{outcome} for a reason")
        r = hub.post("/owner/send", json={"recipient": "tapir", "content": "again"}).json()
        assert (r["status"], r["ok"], r["delivery_error"]) == (status, False, f"{outcome} for a reason")


def test_a_caller_without_a_registered_session_is_refused(hub):
    register(hub, "sess-1", "otter")
    r = hub.post("/send", json={"tmux_pane": "sess-1", "recipient": "otter", "content": "x"})
    assert r.status_code == 404 and "no session id" in r.json()["detail"]["detail"]
    r = hub.post("/send", json={"agent_id": "stranger", "recipient": "otter", "content": "x"})
    assert r.status_code == 404 and "not registered" in r.json()["detail"]["detail"]


def test_offline_reason_comes_from_the_backend(hub):
    register(hub, "sess-1", "otter")
    hub.node.live.discard("sess-1")
    r = hub.post("/owner/send", json={"recipient": "otter", "content": "anyone there"})
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "recipient offline: fake session sess-1 is not live"
    assert hub.node.sent == []


@pytest.mark.parametrize("method,path,body,capability", [
    ("get", "/api/peek/otter", None, "peek"),
    ("post", "/agents/otter/terminal", {"key": "Escape"}, "keys"),
    ("post", "/agents/otter/terminal", {"text": "/compact"}, "keys"),
    ("post", "/agents/otter/switch-model", {"model": "sonnet"}, "keys"),
    ("post", "/agents/otter/restart", {}, "restart"),
    ("post", "/agents/otter/switch", {"to": "codex"}, "restart"),
    ("post", "/agents/otter/resume", None, "spawn"),
    ("post", "/agents/spawn", {"flavor": "claude"}, "spawn"),
    ("post", "/agents/otter/stop", None, "stop"),
    ("post", "/agents/otter/retire", None, "stop"),
    ("post", "/nodes/laptop/token", None, "remote_nodes"),
])
def test_features_the_backend_lacks_answer_501(hub, method, path, body, capability):
    register(hub, "sess-1", "otter")
    r = getattr(hub, method)(path, json=body) if body is not None else getattr(hub, method)(path)
    assert r.status_code == 501, r.text
    detail = r.json()["detail"]
    assert detail["backend"] == "fake" and detail["capability"] == capability
    assert detail["error"].endswith("is not supported by the fake delivery backend")
    assert hub.node.calls == []


def test_controls_that_need_a_missing_capability_are_not_offered(hub):
    register(hub, "sess-1", "otter")
    assert hub.get("/api/spawn-options").json() == {"harnesses": []}
    row = hub.get("/api/state").json()["recipients"][0]
    assert row["compact_command"] is None


def test_a_stopped_agent_can_still_be_retired(hub):
    register(hub, "sess-1", "otter")
    hub.node.live.discard("sess-1")
    r = hub.post("/agents/otter/retire")
    assert r.status_code == 200 and r.json()["already_stopped"] is True


def test_the_monitor_tick_never_reads_a_screen(hub):
    import asyncio

    register(hub, "sess-1", "otter")
    asyncio.run(hub.app.state.monitor_tick())
    assert hub.node.calls == []
    row = hub.get("/api/state").json()["recipients"][0]
    assert row["alive"] is True and row["activity"]["status"] == "unknown"


def test_inbound_messages_are_stored_for_the_owner_once(hub):
    register(hub, "sess-1", "otter")
    assert hub.backend.handler is not None
    message = delivery.Inbound("sess-1", "tests pass on the branch", transport_id="t-1")
    hub.backend.handler(message)
    hub.backend.handler(message)  # the transport delivered it twice
    stored = [m for m in hub.get("/messages", params={"user": "owner"}).json()["messages"]
              if m["sender"] == "otter"]
    assert [(m["recipient"], m["content"], m["status"]) for m in stored] == [
        ("owner", "tests pass on the branch", "delivered")]


def test_inbound_messages_can_name_another_agent(hub):
    register(hub, "sess-1", "otter")
    register(hub, "sess-2", "tapir")
    hub.backend.handler(delivery.Inbound("sess-1", "@tapir can you review task 4?", transport_id="t-2"))
    assert hub.node.sent[-1][1:] == ("sess-2", "[agent-msg from otter] can you review task 4?")


def test_inbound_from_an_unregistered_address_is_dropped(hub):
    register(hub, "sess-1", "otter")
    hub.backend.handler(delivery.Inbound("stranger", "@otter run this"))
    assert hub.node.sent == []
    assert hub.get("/messages").json()["messages"] == []


def test_the_backend_is_closed_with_the_app(hub):
    with hub:
        assert hub.backend.closed is False
    assert hub.backend.closed is True
