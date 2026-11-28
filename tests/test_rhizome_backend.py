"""The Rhizome backend against a fake `rhizome mcp` (tests/fixtures/fake_rhizome.py).

The fake is a real child process speaking MCP over stdio, so the client,
its reader thread and the restart path all run. Nothing here starts the
real Rhizome or touches its network.
"""

import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_swarm import delivery, server
from agent_swarm.delivery import Unavailable, rhizome_backend
from agent_swarm.delivery.tmux_backend import TmuxBackend
from agent_swarm.delivery.rhizome_backend import EPOCH, RhizomeBackend, RhizomeNode, split_parts

FAKE = Path(__file__).parent / "fixtures" / "fake_rhizome.py"
HUB_SESSION = "buzz-hub-test"


def session(sid, status="live", capable=True, name=None, project="/work/repo", agent="claude"):
    return {"identity": {"session_id": sid, "session_name": name or f"{sid} name",
                         "project": project, "agent_type": agent},
            "status": status, "delivery_capable": capable}


class Fake:
    def __init__(self, root: Path):
        self.root = root

    def sessions(self, *rows):
        (self.root / "sessions.json").write_text(json.dumps(list(rows)))

    def sent(self):
        path = self.root / "sent.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def starts(self):
        return len((self.root / "starts").read_text().splitlines())


@pytest.fixture()
def fake(tmp_path, monkeypatch):
    root = tmp_path / "fake-rhizome"
    root.mkdir()
    monkeypatch.setenv("FAKE_RHIZOME_DIR", str(root))
    # Every test sees a fresh list, not one cached by the test before.
    monkeypatch.setattr(rhizome_backend, "SESSIONS_TTL", 0.0)
    return Fake(root)


@pytest.fixture()
def node(fake, tmp_path):
    made = RhizomeNode("hub", [sys.executable, str(FAKE)], HUB_SESSION, tmp_path / "state", tmp_path / "att")
    yield made
    made.close()


def deliver(node, sid, text, **kwargs):
    return node.deliver("1", sid, EPOCH, text, **kwargs)


def test_deliver_binds_the_hub_session_then_sends(node, fake, tmp_path):
    fake.sessions(session("s1"))
    result = deliver(node, "s1", "[agent-msg from owner] hello")
    assert result.status == "ok" and result.error is None
    assert fake.sent() == [{"session_id": "s1", "text": "[agent-msg from owner] hello"}]
    # The hub bound itself with an empty transcript of its own.
    assert (tmp_path / "state" / "hub-transcript.jsonl").read_text() == ""
    deliver(node, "s1", "again")
    assert fake.starts() == 1


def test_a_send_rhizome_refuses_is_failed(node, fake):
    fake.sessions(session("s1"), session("s2", status="recent", capable=False))
    gone = deliver(node, "nobody", "hello")
    assert gone.status == "failed" and 'session "nobody" is not currently available' in gone.error
    assert deliver(node, "s2", "hello").status == "failed"
    limited = deliver(node, "s1", "RATE")
    assert limited.status == "failed" and "rate limit" in limited.error
    assert fake.sent() == []


def test_no_answer_is_unknown(node, fake, monkeypatch):
    fake.sessions(session("s1"))
    deliver(node, "s1", "warm up")
    monkeypatch.setattr(rhizome_backend, "CALL_TIMEOUT", 0.3)
    result = deliver(node, "s1", "HANG")
    assert result.status == "unknown" and "no answer" in result.error


def test_a_child_that_dies_mid_send_is_unknown_and_is_restarted(node, fake):
    fake.sessions(session("s1"))
    result = deliver(node, "s1", "DIE")
    assert result.status == "unknown" and "exited" in result.error
    assert deliver(node, "s1", "after the restart").status == "ok"
    assert fake.starts() == 2
    assert [m["text"] for m in fake.sent()] == ["after the restart"]


def test_a_missing_binary_fails_without_sending(tmp_path, fake):
    node = RhizomeNode("hub", [str(tmp_path / "no-such-rhizome")], HUB_SESSION, tmp_path / "state")
    result = deliver(node, "s1", "hello")
    assert result.status == "failed" and "could not start" in result.error
    with pytest.raises(Unavailable, match="could not list sessions"):
        node.snapshot()


def test_a_refused_binding_fails_without_sending(node, fake, monkeypatch):
    monkeypatch.setenv("FAKE_RHIZOME_NO_BIND", "1")
    fake.sessions(session("s1"))
    result = deliver(node, "s1", "hello")
    assert result.status == "failed" and "did not bind the hub session" in result.error
    assert fake.sent() == []


def test_a_long_message_goes_in_numbered_parts(node, fake):
    fake.sessions(session("s1"))
    text = "\n".join(f"line {i} " + "x" * 90 for i in range(150))  # about 15 KB
    assert deliver(node, "s1", text).status == "ok"
    parts = [m["text"] for m in fake.sent()]
    assert len(parts) == 3 and parts[0].startswith("(part 1/3) line 0 ")
    assert all(len(p.encode()) < 6100 for p in parts)
    assert "".join(p.split(") ", 1)[1] for p in parts) == text


def test_a_message_too_long_for_the_part_limit_is_not_sent(node, fake):
    fake.sessions(session("s1"))
    result = deliver(node, "s1", "y" * 40_000)
    assert result.status == "failed" and "at most 4 parts" in result.error
    assert fake.sent() == []


def test_a_later_part_that_fails_leaves_the_message_unknown(node, fake):
    fake.sessions(session("s1"))
    result = deliver(node, "s1", "a" * 5990 + " " + "RATE" + "b" * 3000)
    assert result.status == "unknown" and "part 2/2 was not sent" in result.error
    assert len(fake.sent()) == 1


def test_split_parts_keeps_every_character():
    text = "é" * 5000 + " " + "word " * 2000
    parts = split_parts(text, 6000)
    assert "".join(parts) == text and all(len(p.encode()) <= 6000 for p in parts)
    assert split_parts("short") == ["short"]


def test_attachments_arrive_as_paths_on_the_hub(node, fake, tmp_path):
    fake.sessions(session("s1"))
    deliver(node, "s1", "see this", attachments=["abc.png"])
    assert fake.sent()[0]["text"] == f"see this\n\n[attached image: {tmp_path / 'att' / 'abc.png'}]"


def test_a_row_from_another_backend_is_not_sent_to(node, fake):
    fake.sessions(session("%4"))
    result = node.deliver("1", "%4", "tmux-socket:1700000000", "hello")
    assert result.status == "failed" and "another delivery backend" in result.error
    assert fake.sent() == []


def test_snapshot_lists_sessions_and_which_can_take_a_message(node, fake):
    fake.sessions(
        session("s1", name="fix the parser"),
        session("s2", status="recent", capable=False),
        session("s3", status="live", capable=False),
        session("s4", status="live (direct)", agent="codex"),
    )
    snap = node.snapshot()
    assert snap.server == EPOCH
    assert snap.existing == {"s1", "s2", "s3", "s4"}  # the hub's own session is left out
    assert snap.live == {"s1", "s4"}
    assert snap.label("s1") == "fix the parser" and snap.cwd("s1") == "/work/repo"
    assert snap.title("s1") == ""
    resolved = node.resolve("s1")
    assert (resolved.pane, resolved.label, resolved.tmux_server) == ("s1", "fix the parser", EPOCH)
    assert node.resolve("nobody") is None and node.resolve(HUB_SESSION) is None

    backend = RhizomeBackend(node)
    assert backend.offline_reason("s1", snap, None) is None
    assert "Rhizome does not list session nobody" in backend.offline_reason("nobody", snap, None)
    assert "is recent (no bound process reports it)" in backend.offline_reason("s2", snap, None)
    assert "live but not delivery capable" in backend.offline_reason("s3", snap, None)
    assert "another delivery backend" in backend.offline_reason("s1", snap, "stale")


def test_what_rhizome_cannot_do_says_so(node):
    suffix = "is not supported by the rhizome delivery backend"
    assert node.capture("s1", EPOCH)[1].endswith(suffix)
    assert node.screen("s1", EPOCH) is None
    for result in (node.send_key("1", "s1", EPOCH, "Escape"), node.kill("1", "s1", EPOCH),
                   node.respawn("1", "s1", EPOCH, "/tmp", "claude"), node.spawn("1", "claude")):
        assert result.status == "failed" and result.error.endswith(suffix)
    caps = RhizomeBackend.capabilities
    assert (caps.deliver, caps.liveness, caps.inbound) == (True, True, True)
    assert not any((caps.peek, caps.activity, caps.keys, caps.spawn, caps.restart, caps.stop, caps.remote_nodes))


def test_from_env_reads_the_command_and_session_id(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SWARM_NODE", "workstation")
    backend = RhizomeBackend.from_env(attachments_root=tmp_path / "a", data_dir=tmp_path)
    assert backend.local.name == "workstation" and backend.local.session_id == "buzz-hub-workstation"
    assert backend.local._client.command == ["rhizome", "mcp", "--agent", "claude"]
    assert backend.local.state_dir == tmp_path / "rhizome"
    monkeypatch.setenv("BUZZ_RHIZOME_COMMAND", "/opt/rhizome mcp --agent claude --debug")
    monkeypatch.setenv("BUZZ_RHIZOME_SESSION_ID", "team-hub")
    backend = RhizomeBackend.from_env(attachments_root=tmp_path / "a", data_dir=tmp_path)
    assert backend.local._client.command == ["/opt/rhizome", "mcp", "--agent", "claude", "--debug"]
    assert backend.local.session_id == "team-hub"
    assert "`team-hub`" in backend.arrival_note()


def test_backend_is_chosen_by_environment(tmp_path, monkeypatch):
    kwargs = {"attachments_root": tmp_path / "a", "data_dir": tmp_path}
    monkeypatch.setenv("BUZZ_DELIVERY", "rhizome")
    assert isinstance(delivery.create(**kwargs), rhizome_backend.RhizomeBackend)
    monkeypatch.setenv("BUZZ_DELIVERY", "tmux")
    assert isinstance(delivery.create(**kwargs), TmuxBackend)
    monkeypatch.setenv("BUZZ_DELIVERY", "carrier-pigeon")
    with pytest.raises(ValueError, match="BUZZ_DELIVERY must be one of tmux, rhizome"):
        delivery.create(**kwargs)


# ---- through the hub -----------------------------------------------------------


@pytest.fixture()
def hub(node, fake, tmp_path):
    app = server.create_app(tmp_path / "db.sqlite", monitor=False, backend=RhizomeBackend(node))
    client = TestClient(app, client=("127.0.0.1", 50000))
    client.fake = fake
    return client


def wait_for(check, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if found := check():
            return found
        time.sleep(0.05)
    raise AssertionError("timed out")


def test_register_and_send_through_the_hub(hub):
    hub.fake.sessions(session("s1", name="parser work"), session("s2"))
    r = hub.post("/register", json={"agent_id": "s1", "requested_user": "otter", "flavor": "claude"})
    assert r.status_code == 200, r.text
    assert (r.json()["tmux_pane"], r.json()["pane_label"]) == ("s1", "parser work")
    assert f"direct message from the hub's session `{HUB_SESSION}`" in r.json()["protocol_brief"]
    hub.post("/register", json={"agent_id": "s2", "requested_user": "tapir"})

    sent = hub.post("/send", json={"agent_id": "s1", "recipient": "tapir", "content": "hello"}).json()
    assert sent["status"] == "delivered"
    assert hub.fake.sent() == [{"session_id": "s2", "text": "[agent-msg from otter] hello"}]

    state = hub.get("/api/state").json()
    assert state["delivery"]["backend"] == "rhizome"
    assert state["delivery"]["capabilities"]["peek"] is False
    assert {r["user_id"]: r["alive"] for r in state["recipients"]} == {"otter": True, "tapir": True}
    assert hub.get("/api/peek/otter").status_code == 501


def test_a_session_that_went_away_is_offline(hub):
    hub.fake.sessions(session("s1"))
    hub.post("/register", json={"agent_id": "s1", "requested_user": "otter"})
    hub.fake.sessions(session("s1", status="recent", capable=False))
    r = hub.post("/owner/send", json={"recipient": "otter", "content": "hello"})
    assert r.status_code == 409 and "is recent (no bound process reports it)" in r.json()["detail"]["error"]
    hub.fake.sessions()
    row = hub.get("/recipients").json()["recipients"][0]
    assert row["alive"] is False and "does not list session s1" in row["offline_reason"]


def test_a_direct_message_to_the_hub_lands_in_the_store(hub):
    hub.fake.sessions(session("s1"))
    hub.post("/register", json={"agent_id": "s1", "requested_user": "otter"})
    # The fake answers a PING by sending a direct message back from that session.
    hub.post("/owner/send", json={"recipient": "otter", "content": "PING done with task 3"})

    def stored():
        return [m for m in hub.get("/messages", params={"user": "owner"}).json()["messages"]
                if m["sender"] == "otter"]

    message = wait_for(stored)[0]
    assert (message["recipient"], message["content"], message["status"]) == ("owner", "done with task 3", "delivered")
