"""Snapshots on every node (#546): the node daemon's own schedule, and the
copy the hub keeps so a machine that lost its disk can still be restored."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agent_swarm import client as cli, config, node, nodes, restore, server, tmux

SNAPSHOT = {
    "node": "macbook",
    "tmux_server": "mac-srv:1",
    "taken_at": "2026-11-22T18:55:07-05:00",
    "sessions": [{
        "name": "agents",
        "windows": [{
            "index": 0, "name": "swarm", "layout": "abcd,80x24,0,0", "panes": [{
                "index": 0, "cwd": "/Users/me", "command": "claude",
                "agent": {"handle": "otter", "flavor": "claude", "agent_id": "session-1"},
            }],
        }],
    }],
}


@pytest.fixture()
def hub(tmp_path, monkeypatch):
    """A hub, its owner client, and a token for a machine called macbook."""
    monkeypatch.setattr(tmux, "server_id", lambda: "hub-srv")
    monkeypatch.setattr(tmux, "pane_table", lambda: {})
    monkeypatch.setattr(tmux, "resolve_pane", lambda target: (target, target))
    app = server.create_app(tmp_path / "db.sqlite", monitor=False)
    owner = TestClient(app, client=("127.0.0.1", 41000))
    token = owner.post("/nodes/macbook/token").json()["token"]
    return owner, token


def _as_node(owner: TestClient, token: str) -> TestClient:
    return TestClient(owner.app, client=("100.64.0.9", 50000),
                      headers={"Authorization": f"Bearer {token}"})


# --- the hub's copy -------------------------------------------------------


def test_the_hub_keeps_the_newest_snapshot_a_machine_posts(hub):
    owner, token = hub
    assert owner.get("/nodes/snapshot?node=macbook").status_code == 404

    mac = _as_node(owner, token)
    r = mac.post("/nodes/snapshot", json={"snapshot": SNAPSHOT})
    assert r.status_code == 200 and r.json()["node"] == "macbook"

    got = mac.get("/nodes/snapshot")
    assert got.status_code == 200 and got.json() == SNAPSHOT
    assert owner.get("/nodes/snapshot?node=macbook").json() == SNAPSHOT

    newer = {**SNAPSHOT, "taken_at": "2026-11-22T19:00:07-05:00"}
    assert mac.post("/nodes/snapshot", json={"snapshot": newer}).status_code == 200
    assert owner.get("/nodes/snapshot?node=macbook").json()["taken_at"] == newer["taken_at"]
    # One row per machine: which machines the hub has, and how fresh each is.
    assert owner.get("/nodes/snapshots").json()["snapshots"] == [
        {"node": "macbook", "taken_at": newer["taken_at"]},
    ]


def test_a_node_can_only_post_and_read_its_own_snapshot(hub):
    owner, token = hub
    mac = _as_node(owner, token)
    elsewhere = {**SNAPSHOT, "node": "linuxbox"}
    r = mac.post("/nodes/snapshot", json={"snapshot": elsewhere})
    assert r.status_code == 403 and "may not post" in r.json()["detail"]["error"]
    assert mac.get("/nodes/snapshot?node=linuxbox").status_code == 403
    assert mac.get("/nodes/snapshot").status_code == 404


def test_snapshot_bodies_are_checked(hub):
    owner, token = hub
    mac = _as_node(owner, token)
    assert mac.post("/nodes/snapshot", json={"snapshot": {"sessions": []}}).status_code == 422
    assert mac.post("/nodes/snapshot", json={"snapshot": {**SNAPSHOT, "sessions": "x"}}).status_code == 422
    # The owner may post the hub's own snapshot, but not one for an unknown machine.
    local = {**SNAPSHOT, "node": "hubnode"}
    r = owner.post("/nodes/snapshot", json={"snapshot": local})
    assert r.status_code == 404 and "unknown node" in r.json()["detail"]["error"]


def test_the_owner_posts_and_reads_the_hubs_own_snapshot(hub):
    owner, _ = hub
    local = {**SNAPSHOT, "node": "karans-linux"}
    assert owner.post("/nodes/snapshot", json={"snapshot": local}).status_code == 200
    # Without a node, the owner gets the hub machine's copy.
    assert owner.get("/nodes/snapshot").json() == local


# --- the node daemon's own schedule --------------------------------------


def _node_daemon(tmp_path, monkeypatch, *, every=0.01, post=None, server_id="mac-srv"):
    """A Node with tmux, the snapshot code and the hub's HTTP all faked."""
    saved = []

    monkeypatch.setattr(tmux, "server_id", lambda: server_id)
    monkeypatch.setattr(restore, "read_layout", lambda: [
        {"session": "agents", "window": 0, "window_name": "swarm", "layout": "l",
         "pane": 0, "pane_id": "%1", "cwd": "/Users/me", "command": "claude"},
    ])
    monkeypatch.setattr(restore, "save", lambda snap: saved.append(snap) or tmp_path / "x.json")
    monkeypatch.setattr(node.httpx, "get", lambda url, **kw: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"recipients": [
            {"user_id": "otter", "node": "macbook", "tmux_server": "mac-srv",
             "tmux_pane": "%1", "agent_id": "session-1", "flavor": "claude"},
        ]},
    ))
    posted = []

    def fake_post(url, json=None, **kw):
        posted.append(json["snapshot"])
        if post is not None:
            return post()
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr(node.httpx, "post", fake_post)
    settings = config.Settings(hub="http://hub.test:8765", token="tok", node="macbook")
    daemon = node.Daemon(
        settings, node.Executor(nodes.LocalNode("macbook"), node.OpStore(tmp_path / "ops.sqlite")),
        snapshot_every=every,
    )
    return daemon, saved, posted


def test_the_node_saves_its_snapshot_and_hands_the_hub_a_copy(tmp_path, monkeypatch):
    daemon, saved, posted = _node_daemon(tmp_path, monkeypatch)
    snap = daemon.snapshot_once()
    assert snap["node"] == "macbook" and snap["tmux_server"] == "mac-srv"
    assert [p["agent"]["handle"] for p in snap["sessions"][0]["windows"][0]["panes"]] == ["otter"]
    # Saved locally first, so restore works even if the hub copy failed.
    assert saved == [snap] and posted == [snap]


def test_no_tmux_server_means_no_snapshot(tmp_path, monkeypatch):
    daemon, saved, posted = _node_daemon(tmp_path, monkeypatch, server_id=None)
    assert daemon.snapshot_once() is None
    assert saved == [] and posted == []


def test_a_hub_that_refuses_the_copy_still_leaves_the_local_snapshot(tmp_path, monkeypatch):
    def refuse():
        raise node.httpx.ConnectError("refused")

    daemon, saved, _ = _node_daemon(tmp_path, monkeypatch, post=refuse)
    assert daemon.snapshot_once() is not None
    assert len(saved) == 1


def test_the_node_snapshots_itself_every_interval(tmp_path, monkeypatch):
    daemon, _, _ = _node_daemon(tmp_path, monkeypatch, every=0.01)
    calls = []
    monkeypatch.setattr(daemon, "snapshot_once", lambda: calls.append(time.monotonic()))

    async def run():
        task = asyncio.create_task(daemon._snapshots())
        await asyncio.sleep(0.12)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert len(calls) >= 3  # roughly one every 10 ms, not once at startup
    assert calls[-1] - calls[0] > 0


def test_no_interval_takes_no_snapshots(tmp_path, monkeypatch):
    daemon, _, _ = _node_daemon(tmp_path, monkeypatch, every=0)
    calls = []
    monkeypatch.setattr(daemon, "snapshot_once", lambda: calls.append(1))
    asyncio.run(asyncio.wait_for(daemon._snapshots(), timeout=1))
    assert calls == []


# --- the CLI --------------------------------------------------------------


def test_buzz_snapshot_hands_the_hub_a_copy(tmp_path, monkeypatch):
    posted = []
    monkeypatch.setattr(cli, "tmux", SimpleNamespace(server_id=lambda: "srv:1"))
    monkeypatch.setattr(cli.httpx, "get", lambda url, **kw: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"recipients": []}))
    monkeypatch.setattr(cli.httpx, "post", lambda url, json=None, **kw: posted.append(json["snapshot"])
                        or SimpleNamespace(raise_for_status=lambda: None))
    monkeypatch.setattr(cli.restore, "read_layout", lambda: [])
    monkeypatch.setattr(cli.restore, "save", lambda snap, directory: tmp_path / "s.json")
    monkeypatch.setattr(cli, "local_node", lambda: "macbook")
    args = SimpleNamespace(dir=str(tmp_path))
    assert cli.cmd_snapshot(args) == 0
    assert len(posted) == 1 and posted[0]["node"] == "macbook"


def test_restore_from_hub_uses_the_hubs_copy(tmp_path, monkeypatch):
    snap = {**SNAPSHOT, "node": "macbook"}
    monkeypatch.setattr(cli.httpx, "get", lambda url, **kw: SimpleNamespace(
        status_code=200, raise_for_status=lambda: None, json=lambda: snap))
    monkeypatch.setattr(cli, "local_node", lambda: "macbook")
    monkeypatch.setattr(cli.restore, "read_layout", lambda: [])
    monkeypatch.setattr(cli.restore, "running_sessions", lambda recipients, agents: set())
    seen = {}

    def fake_run(steps, args, recipients):
        seen["steps"] = steps
        return 0

    monkeypatch.setattr(cli, "_run_restore", fake_run)
    args = SimpleNamespace(from_hub=True, from_file=None, dir=str(tmp_path), apply=False, stagger=0.0)
    assert cli._restore_from_hub(args, tmp_path, []) == 0
    # The copy is kept locally, so a second restore needs no hub.
    assert list(tmp_path.glob("*.json"))
    assert seen["steps"] == restore.plan(snap, [], set())


def test_restore_from_hub_says_so_when_the_hub_has_none(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli.httpx, "get", lambda url, **kw: SimpleNamespace(status_code=404))
    args = SimpleNamespace(from_hub=True, from_file=None)
    assert cli._restore_from_hub(args, tmp_path, []) == 1
    assert "no snapshot for this machine" in capsys.readouterr().err