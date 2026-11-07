"""The Node interface: LocalNode delegates to tmux; the registry finds nodes."""

from agent_swarm import nodes, tmux


def test_local_node_snapshot_derives_everything_from_one_pane_read(monkeypatch):
    node = nodes.LocalNode("here")
    monkeypatch.setattr(tmux, "server_id", lambda: "1234:42")
    monkeypatch.setattr(
        tmux, "pane_table",
        lambda: {
            "%1": {"label": "a:0.0", "command": "claude", "title": "✳ topic"},
            "%2": {"label": "a:0.1", "command": "bash", "title": ""},
        },
    )
    snap = node.snapshot()
    assert snap.server == "1234:42"
    assert snap.server_start == 42.0
    assert snap.existing == {"%1", "%2"}
    assert snap.live == {"%1"}
    assert snap.label("%1") == "a:0.0"
    assert snap.title("%1") == "✳ topic"
    assert snap.label("%3") is None
    assert node.server_id() == "1234:42"


def test_local_node_snapshot_rereads_when_tmux_restarts_mid_read(monkeypatch):
    # Server id before and after the pane read must agree; otherwise the
    # panes belong to one server and the identity to another.
    ids = iter(["1:1", "2:2", "2:2", "2:2"])
    tables = iter([{"%0": {"label": "old", "command": "claude", "title": ""}},
                   {"%0": {"label": "new", "command": "bash", "title": ""}}])
    monkeypatch.setattr(tmux, "server_id", lambda: next(ids))
    monkeypatch.setattr(tmux, "pane_table", lambda: next(tables))
    snap = nodes.LocalNode("here").snapshot()
    assert snap.server == "2:2"
    assert snap.label("%0") == "new"
    assert snap.live == frozenset()


def test_local_node_refuses_a_pane_from_an_earlier_tmux(monkeypatch):
    monkeypatch.setattr(tmux, "server_id", lambda: "srv-2")
    calls = []
    monkeypatch.setattr(tmux, "deliver", lambda *a, **k: calls.append(a) or (True, None))
    monkeypatch.setattr(tmux, "capture_pane", lambda pane, colors=False: calls.append(pane) or ("x", None))
    monkeypatch.setattr(tmux, "kill_pane", lambda pane: calls.append(pane) or (True, None))
    monkeypatch.setattr(tmux, "tag_pane", lambda pane, h: calls.append(pane) or (True, None))
    monkeypatch.setattr(tmux, "rename_window", lambda pane, n: calls.append(pane) or (True, None))
    node = nodes.LocalNode("here")
    result = node.deliver("op", "%1", "srv-1", "hello")
    assert result.status == "failed" and "srv-1 is gone" in result.error
    assert node.capture("%1", "srv-1")[0] is None
    assert node.kill("op", "%1", "srv-1").status == "failed"
    assert node.tag_pane("op", "%1", "srv-1", "otter").status == "failed"
    assert node.rename_window("op", "%1", "srv-1", "otter").status == "failed"
    assert calls == []
    # The current server, or no expectation at all, goes through.
    assert node.deliver("op", "%1", "srv-2", "hello").ok
    assert node.deliver("op", "%1", None, "hello").ok
    assert len(calls) == 2


def test_local_node_snapshot_gives_up_after_two_restarts(monkeypatch):
    import pytest

    ids = iter(["1:1", "2:2", "2:2", "3:3"])
    monkeypatch.setattr(tmux, "server_id", lambda: next(ids))
    monkeypatch.setattr(tmux, "pane_table", lambda: {"%0": {"label": "x", "command": "claude", "title": ""}})
    with pytest.raises(nodes.Unavailable):
        nodes.LocalNode("here").snapshot()


def test_local_node_reports_an_uncertain_paste_as_unknown(monkeypatch):
    monkeypatch.setattr(tmux, "server_id", lambda: "srv-1")

    def deliver(*a, **k):
        raise tmux.Uncertain("pasted, but the submit key failed: timed out")

    monkeypatch.setattr(tmux, "deliver", deliver)
    result = nodes.LocalNode("here").deliver("op", "%1", "srv-1", "hi")
    assert result.status == "unknown" and "submit key" in result.error


def test_local_node_spawn_and_kill_return_results(monkeypatch):
    monkeypatch.setattr(tmux, "server_id", lambda: "srv-1")
    monkeypatch.setattr(
        tmux, "spawn_window",
        lambda session=None, command=None: (tmux.Created("%9", "agents:2.0", "srv-1"), None),
    )
    monkeypatch.setattr(tmux, "kill_pane", lambda pane: (False, "no such pane"))
    node = nodes.LocalNode("here")
    spawned = node.spawn("op", "claude")
    assert spawned.ok and spawned.pane == "%9"
    assert spawned.label == "agents:2.0" and spawned.tmux_server == "srv-1"
    monkeypatch.setattr(tmux, "spawn_window", lambda session=None, command=None: (None, "boom"))
    assert node.spawn("op", "claude") == nodes.Spawned("failed", None, "boom")
    assert node.kill("op", "%9", "srv-1") == nodes.Result("failed", "no such pane")


def test_local_node_delivers_through_tmux(monkeypatch):
    calls = []
    monkeypatch.setattr(
        tmux, "deliver",
        lambda pane, text, message_prefix=None, submit_key="C-m", flavor=None, retry_submit=True: (
            calls.append((pane, text, message_prefix, submit_key, flavor, retry_submit)) or (True, None)
        ),
    )
    monkeypatch.setattr(tmux, "server_id", lambda: "srv-1")
    result = nodes.LocalNode("here").deliver(
        "7", "%3", "srv-1", "hello", message_prefix="/queue ", submit_key="Enter", flavor="codex"
    )
    assert result == nodes.Result("ok", None) and result.ok
    assert calls == [("%3", "hello", "/queue ", "Enter", "codex", True)]


def test_registry_always_keeps_the_local_node():
    local = nodes.LocalNode("hub")
    fleet = nodes.NodeRegistry(local)
    assert fleet.get(None) is local
    assert fleet.get("hub") is local
    assert fleet.get("laptop") is None
    other = nodes.LocalNode("laptop")
    fleet.add(other)
    assert fleet.get("laptop") is other
    assert fleet.names() == ["hub", "laptop"]
    fleet.remove("laptop")
    fleet.remove("hub")
    assert fleet.names() == ["hub"]


def test_registry_refuses_a_node_claiming_the_local_name():
    import pytest

    fleet = nodes.NodeRegistry(nodes.LocalNode("hub"))
    with pytest.raises(ValueError):
        fleet.add(nodes.LocalNode("hub"))


def test_local_node_send_key(monkeypatch):
    monkeypatch.setattr(tmux, "server_id", lambda: "srv-1")
    monkeypatch.setattr(tmux, "send_key", lambda pane, key: (True, None))
    node = nodes.LocalNode("here")
    assert node.send_key("op", "%1", "srv-1", "Up").status == "ok"
    assert node.send_key("op", "%1", "srv-0", "Up").status == "failed"

    def uncertain(pane, key):
        raise tmux.Uncertain("key did not report back")

    monkeypatch.setattr(tmux, "send_key", uncertain)
    assert node.send_key("op", "%1", "srv-1", "Up").status == "unknown"


def test_local_node_carries_uncertain_spawn_and_kill(monkeypatch):
    monkeypatch.setattr(tmux, "server_id", lambda: "srv-1")

    def spawn_window(session=None, command=None):
        raise tmux.Uncertain("launch command did not report back", tmux.Created("%4", "agents:4.0", "srv-1"))

    monkeypatch.setattr(tmux, "spawn_window", spawn_window)
    assert nodes.LocalNode("here").spawn("op", "claude") == nodes.Spawned(
        "unknown", "%4", "launch command did not report back", label="agents:4.0", tmux_server="srv-1"
    )

    def kill_pane(pane):
        raise tmux.Uncertain("kill did not report back")

    monkeypatch.setattr(tmux, "kill_pane", kill_pane)
    assert nodes.LocalNode("here").kill("op", "%4", "srv-1").status == "unknown"


def test_local_node_resolve_pairs_the_pane_with_the_server_that_issued_it(monkeypatch):
    import pytest

    monkeypatch.setattr(tmux, "server_id", lambda: "srv-1")
    monkeypatch.setattr(tmux, "resolve_pane", lambda t: ("%3", "a:0.1"))
    assert nodes.LocalNode("here").resolve("a:0.1") == nodes.Resolved("%3", "a:0.1", "srv-1")
    monkeypatch.setattr(tmux, "resolve_pane", lambda t: None)
    assert nodes.LocalNode("here").resolve("nope") is None
    # A restart during the look is not a pane on either server.
    ids = iter(["srv-1", "srv-2"])
    monkeypatch.setattr(tmux, "server_id", lambda: next(ids))
    monkeypatch.setattr(tmux, "resolve_pane", lambda t: ("%0", "a:0.0"))
    with pytest.raises(nodes.Unavailable):
        nodes.LocalNode("here").resolve("a:0.0")


def test_a_spawned_pane_keeps_the_server_that_created_it_across_a_restart(monkeypatch):
    # The window was made on srv-1; tmux restarts right after, and %1 on the
    # new server is an unrelated pane. Nothing must look it up again.
    monkeypatch.setattr(
        tmux, "spawn_window",
        lambda session=None, command=None: (tmux.Created("%1", "agents:1.0", "srv-1"), None),
    )
    monkeypatch.setattr(tmux, "server_id", lambda: "srv-2")
    looked = []
    monkeypatch.setattr(tmux, "resolve_pane", lambda t: looked.append(t) or ("%1", "unrelated:0.0"))
    spawned = nodes.LocalNode("here").spawn("op", "claude")
    assert spawned == nodes.Spawned("ok", "%1", None, label="agents:1.0", tmux_server="srv-1")
    assert looked == []
    # And any later operation on it is refused by the server check.
    assert nodes.LocalNode("here").kill("op", "%1", "srv-1").status == "failed"
