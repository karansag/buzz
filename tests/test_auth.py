"""Who may do what: loopback is the owner, a token is a node, nothing else gets in."""

import pytest
from fastapi.testclient import TestClient

from agent_swarm import config, nodes, server, tmux


@pytest.fixture()
def hub(tmp_path, monkeypatch):
    monkeypatch.setattr(tmux, "server_id", lambda: "srv-1")
    monkeypatch.setattr(tmux, "resolve_pane", lambda t: (t, t))
    monkeypatch.setattr(
        tmux, "pane_table",
        lambda: {"%1": {"label": "a:0.0", "command": "claude", "title": ""}},
    )
    monkeypatch.setattr(tmux, "deliver", lambda *a, **k: (True, None))
    monkeypatch.setattr(tmux, "tag_pane", lambda *a: (True, None))
    return server.create_app(tmp_path / "db.sqlite", monitor=False)


def owner(app):
    return TestClient(app, client=("127.0.0.1", 40000))


def remote(app, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return TestClient(app, client=("100.64.0.9", 40000), headers=headers)


def enrol(app, name):
    r = owner(app).post(f"/nodes/{name}/token")
    assert r.status_code == 200
    app.state.nodes.add(nodes.LocalNode(name))
    return r.json()["token"]


@pytest.mark.parametrize("key", ["C-c", "C-b"])
def test_control_keys_are_owner_only(hub, key):
    token = enrol(hub, "macbook")
    assert remote(hub, token).post("/agents/otter/terminal", json={"key": key}).status_code == 403


def test_a_request_from_the_tailnet_needs_a_token(hub):
    assert remote(hub).get("/health").status_code == 200
    r = remote(hub).get("/recipients")
    assert r.status_code == 401 and "authentication required" in r.json()["detail"]["error"]
    assert remote(hub, "nope").get("/recipients").status_code == 401
    assert owner(hub).get("/recipients").status_code == 200


def test_a_node_token_speaks_only_for_its_own_machine(hub):
    token = enrol(hub, "macbook")
    node = remote(hub, token)
    assert node.post("/register", json={"tmux_pane": "%1", "node": "macbook"}).status_code == 200
    r = node.post("/register", json={"tmux_pane": "%1", "node": "workstation"})
    assert r.status_code == 403 and r.json()["detail"]["error"] == "node mismatch"
    # Omitting the node means the hub's own machine, which a node is not.
    assert node.post("/register", json={"tmux_pane": "%1"}).status_code == 403
    assert node.get("/whoami", params={"tmux_pane": "%1"}).status_code == 403
    assert node.get("/whoami", params={"tmux_pane": "%1", "node": "macbook"}).json()["user_id"]
    assert node.post("/status", json={"tmux_pane": "%1", "node": "macbook", "text": "busy"}).status_code == 200
    assert node.post("/send", json={"tmux_pane": "%1", "node": "macbook", "recipient": "owner", "content": "hi"}).status_code == 200


def test_a_node_cannot_do_what_the_owner_does(hub):
    token = enrol(hub, "macbook")
    node = remote(hub, token)
    for method, path, body in [
        ("post", "/owner/send", {"recipient": "x", "content": "y"}),
        ("post", "/agents/spawn", {"flavor": "claude"}),
        ("post", "/teams", {"name": "t"}),
        ("get", "/teams", None),
        ("post", "/recipients/prune", {}),
        ("get", "/api/state", None),
        ("get", "/api/peek/x", None),
        ("get", "/tabs/usage/", None),
        ("post", "/recipients/retire", {"user_ids": ["x"]}),
        ("get", "/", None),
        ("get", "/nodes", None),
        ("post", "/nodes/other/token", None),
        ("delete", "/nodes/macbook", None),
    ]:
        r = getattr(node, method)(path, json=body) if body is not None else getattr(node, method)(path)
        assert r.status_code == 403, (method, path, r.status_code)
    # What an agent does is allowed, in its own name.
    assert node.get("/messages").status_code == 200
    assert node.get("/recipients").status_code == 200
    assert node.get("/tasks").status_code == 200
    assert node.post("/register", json={"tmux_pane": "%1", "node": "macbook"}).status_code == 200
    assert node.post("/tasks", json={"title": "from the laptop", "tmux_pane": "%1", "node": "macbook"}).status_code == 200


def test_tokens_are_issued_once_rotated_and_revoked(hub):
    first = enrol(hub, "macbook")
    listed = owner(hub).get("/nodes").json()
    assert [n["name"] for n in listed["nodes"]] == ["macbook"]
    assert listed["nodes"][0]["connected"] is True
    second = owner(hub).post("/nodes/macbook/token").json()["token"]
    assert second != first
    assert remote(hub, first).get("/recipients").status_code == 401
    assert remote(hub, second).get("/recipients").status_code == 200
    assert owner(hub).delete("/nodes/macbook").status_code == 200
    assert remote(hub, second).get("/recipients").status_code == 401
    assert hub.state.nodes.get("macbook") is None
    assert owner(hub).delete("/nodes/macbook").status_code == 404


def test_the_hub_refuses_a_token_for_its_own_name(tmp_path, monkeypatch):
    # A fixed hostname with capitals, as macOS reports them: the hub must know
    # itself however the name is cased, on every machine the tests run on.
    monkeypatch.setattr(config.socket, "gethostname", lambda: "Mixed-Case-Host.local")
    monkeypatch.setattr(tmux, "server_id", lambda: "srv-1")
    app = server.create_app(tmp_path / "db.sqlite", monitor=False)
    assert tmux.local_node() == "mixed-case-host"
    for name in ("mixed-case-host", "Mixed-Case-Host"):
        r = owner(app).post(f"/nodes/{name}/token")
        assert r.status_code == 400, name
        assert "own node" in r.json()["detail"]["error"]
    assert owner(app).post("/nodes/Not%20Valid/token").status_code == 400
    assert owner(app).post("/nodes/other-box/token").status_code == 200


def test_loopback_trust_can_be_switched_off(tmp_path, monkeypatch):
    app = server.create_app(tmp_path / "db.sqlite", monitor=False, trust_loopback=False)
    assert owner(app).get("/recipients").status_code == 401
    assert owner(app).get("/health").status_code == 200
    monkeypatch.setenv("AGENT_SWARM_TRUST_LOOPBACK", "0")
    app = server.create_app(tmp_path / "db2.sqlite", monitor=False)
    assert owner(app).get("/recipients").status_code == 401


def test_a_node_cannot_take_over_or_remove_another_machines_agent(hub, monkeypatch):
    token = enrol(hub, "macbook")
    node = remote(hub, token)
    assert owner(hub).post(
        "/register", json={"tmux_pane": "%1", "agent_id": "known-session", "requested_user": "otter"}
    ).json()["user_id"] == "otter"
    # agent_id is public (recipients, protocol brief); it must not move an agent.
    r = node.post("/register", json={"tmux_pane": "%1", "node": "macbook", "agent_id": "known-session"})
    assert r.status_code == 403 and r.json()["detail"]["error"] == "agent belongs to another node"
    # Nor may a node reclaim the hub agent's handle while it is live...
    assert node.post("/register", json={"tmux_pane": "%1", "node": "macbook", "requested_user": "otter"}).status_code == 403
    # ...or once it is offline (its pane fell back to a shell).
    monkeypatch.setattr(
        tmux, "pane_table", lambda: {"%1": {"label": "a:0.0", "command": "bash", "title": ""}}
    )
    assert owner(hub).get("/recipients").json()["recipients"][0]["alive"] is False
    assert node.post("/register", json={"tmux_pane": "%1", "node": "macbook", "requested_user": "otter"}).status_code == 403
    assert node.delete("/recipients/otter").status_code == 403
    rows = {r["user_id"]: r["node"] for r in owner(hub).get("/recipients").json()["recipients"]}
    assert rows == {"otter": tmux.local_node()}
    # A node may still clear its own registrations, and the owner may move an agent.
    mine = node.post("/register", json={"tmux_pane": "%1", "node": "macbook"}).json()["user_id"]
    assert mine != "otter"
    assert node.delete(f"/recipients/{mine}").status_code == 200
    r = owner(hub).post("/register", json={"tmux_pane": "%1", "node": "macbook", "agent_id": "known-session"})
    assert r.status_code == 200 and r.json()["user_id"] == "otter" and r.json()["node"] == "macbook"


def test_a_task_from_a_node_is_delivered_in_the_agents_name_not_the_owners(hub, monkeypatch):
    delivered = []
    monkeypatch.setattr(tmux, "deliver", lambda pane, text, **k: delivered.append(text) or (True, None))
    token = enrol(hub, "macbook")
    node = remote(hub, token)
    owner(hub).post("/register", json={"tmux_pane": "%1", "requested_user": "otter"})
    puffin = node.post("/register", json={"tmux_pane": "%1", "node": "macbook", "requested_user": "puffin"})
    assert puffin.status_code == 200
    # Without saying which agent is acting, a node may not assign at all.
    r = node.post("/tasks", json={"title": "do this", "assignee": "otter"})
    assert r.status_code == 403
    r = node.post("/tasks", json={"title": "do this", "assignee": "otter", "tmux_pane": "%1", "node": "macbook"})
    assert r.status_code == 200
    assert delivered and delivered[-1].startswith("[agent-msg from puffin · task #")
    msg = owner(hub).get("/messages").json()["messages"][0]
    assert msg["sender"] == "puffin" and msg["recipient"] == "otter"
    # Reassignment by PATCH is signed the same way.
    task_id = r.json()["task"]["id"]
    owner(hub).post("/register", json={"tmux_pane": "%1", "requested_user": "ibis"})
    r = node.patch(f"/tasks/{task_id}", json={"assignee": "ibis", "tmux_pane": "%1", "node": "macbook"})
    assert r.status_code == 200
    assert owner(hub).get("/messages").json()["messages"][0]["sender"] == "puffin"
    # The owner's dashboard still assigns as the owner.
    owner(hub).post("/tasks", json={"title": "from me", "assignee": "ibis"})
    assert owner(hub).get("/messages").json()["messages"][0]["sender"] == "owner"


def test_nodes_me_tells_a_caller_what_it_is(hub):
    token = enrol(hub, "macbook")
    assert remote(hub, token).get("/nodes/me").json() == {"kind": "node", "node": "macbook"}
    assert owner(hub).get("/nodes/me").json() == {"kind": "owner", "node": tmux.local_node()}


def proxied(app, login=None, peer="127.0.0.1"):
    """A request the way Tailscale Serve forwards it: from loopback, with
    forwarding headers and, for a tailnet user, its identity."""
    headers = {"X-Forwarded-For": "100.87.6.39", "X-Forwarded-Proto": "https"}
    if login:
        headers["Tailscale-User-Login"] = login
    return TestClient(app, client=(peer, 40000), headers=headers)


@pytest.fixture()
def named_hub(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SWARM_OWNER_LOGINS", "owner@example.com")
    monkeypatch.setattr(tmux, "server_id", lambda: "srv-1")
    monkeypatch.setattr(tmux, "resolve_pane", lambda t: (t, t))
    monkeypatch.setattr(tmux, "pane_table", lambda: {})
    return server.create_app(tmp_path / "db.sqlite", monitor=False)


def test_a_named_tailnet_user_through_tailscale_serve_is_the_owner(named_hub):
    hub = named_hub
    me = proxied(hub, "owner@example.com")
    assert me.get("/api/state").status_code == 200
    assert me.get("/").status_code == 200
    assert me.get("/nodes/me").json() == {"kind": "owner", "node": tmux.local_node()}
    assert me.post("/nodes/macbook/token").status_code == 200


def test_a_forwarded_request_without_an_identity_is_refused(named_hub):
    hub = named_hub
    r = proxied(hub).get("/api/state")
    assert r.status_code == 401 and "without a Tailscale identity" in r.json()["detail"]["error"]
    # The identity header means nothing from a peer that is not the loopback proxy.
    assert proxied(hub, "owner@example.com", peer="100.64.0.9").get("/api/state").status_code == 401
    # Plain loopback, not forwarded, is still the local owner.
    assert owner(hub).get("/api/state").status_code == 200


def test_any_vouched_login_is_the_owner_until_logins_are_named(hub):
    # No AGENT_SWARM_OWNER_LOGINS: Serve is tailnet-only and vouches for the
    # login, which on a single-user tailnet is the one person.
    assert proxied(hub, "owner@example.com").get("/api/state").status_code == 200
    assert proxied(hub, "owner@example.com").get("/nodes/me").json()["kind"] == "owner"
    assert owner(hub).get("/api/state").status_code == 200


def test_an_identity_header_alone_marks_a_proxied_request(hub, named_hub):
    # Loopback with a login header but no forwarding header never counts as
    # the plain local owner: it takes the proxied path and its rules.
    bare = TestClient(hub, client=("127.0.0.1", 40000), headers={"Tailscale-User-Login": "stranger@example.com"})
    assert bare.get("/nodes/me").json() == {"kind": "owner", "node": tmux.local_node()}  # proxied path, no allowlist
    named = TestClient(named_hub, client=("127.0.0.1", 40000), headers={"Tailscale-User-Login": "owner@example.com"})
    assert named.get("/nodes/me").json()["kind"] == "owner"
    other = TestClient(named_hub, client=("127.0.0.1", 40000), headers={"Tailscale-User-Login": "stranger@example.com"})
    assert other.get("/api/state").status_code == 403


def test_owner_logins_can_be_narrowed(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SWARM_OWNER_LOGINS", "owner@example.com, Other@Example.com")
    app = server.create_app(tmp_path / "db.sqlite", monitor=False)
    assert proxied(app, "owner@example.com").get("/api/state").status_code == 200
    assert proxied(app, "other@example.com").get("/api/state").status_code == 200
    r = proxied(app, "stranger@example.com").get("/api/state")
    assert r.status_code == 403 and "not an owner login" in r.json()["detail"]["error"]


def test_a_node_token_keeps_its_scope_through_the_proxy(named_hub):
    hub = named_hub
    token = enrol(hub, "macbook")
    c = TestClient(
        hub, client=("127.0.0.1", 40000),
        headers={"Authorization": f"Bearer {token}", "X-Forwarded-For": "100.87.6.39",
                 "Tailscale-User-Login": "owner@example.com"},
    )
    assert c.get("/nodes/me").json() == {"kind": "node", "node": "macbook"}
    assert c.get("/api/state").status_code == 403


def test_proxied_identity_still_works_when_loopback_trust_is_off(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SWARM_OWNER_LOGINS", "owner@example.com")
    app = server.create_app(tmp_path / "db.sqlite", monitor=False, trust_loopback=False)
    assert owner(app).get("/api/state").status_code == 401
    assert proxied(app, "owner@example.com").get("/api/state").status_code == 200
