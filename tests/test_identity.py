"""Callers are identified by their harness session id when they send one.

Claude Code and Codex can run a session's tools in a background host whose
TMUX_PANE is missing or names another agent's pane, so the pane alone can't
say who is calling. These tests pin how /send, /status and /whoami resolve a
caller, and that an unknown or foreign session id never falls back to the
agent that happens to hold the named pane."""

from tests.test_auth import enrol, hub, owner, remote  # noqa: F401  (fixtures/helpers)
from tests.test_server import client  # noqa: F401  (reuse the app fixture)


def register(client, pane, name, agent_id=None):
    body = {"tmux_pane": pane, "requested_user": name}
    if agent_id:
        body["agent_id"] = agent_id
    r = client.post("/register", json=body)
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


def whoami(client, **params):
    return client.get("/whoami", params=params).json()


def send(client, **body):
    return client.post("/send", json={"recipient": "owner", "content": "hi", **body})


def test_a_known_session_is_the_caller_whatever_pane_it_names(client):
    # explainer's case: its commands ran in a background host and guessed
    # tmux's active pane, which was numbat's.
    register(client, "0:0.0", "numbat", agent_id="sess-numbat")
    register(client, "0:1.0", "explainer", agent_id="sess-explainer")
    answer = whoami(client, tmux_pane="0:0.0", agent_id="sess-explainer", pane_verified="false")
    assert answer["user_id"] == "explainer" and answer["identified_by"] == "session"
    r = send(client, tmux_pane="0:0.0", agent_id="sess-explainer", pane_verified=False)
    assert r.status_code == 200
    last = client.get("/api/state").json()["messages"][-1]
    assert last["sender"] == "explainer"


def test_a_session_can_send_with_no_pane_at_all(client):
    register(client, "0:1.0", "explainer", agent_id="sess-explainer")
    assert send(client, agent_id="sess-explainer").status_code == 200
    r = client.post("/status", json={"agent_id": "sess-explainer", "text": "working on it"})
    assert r.status_code == 200 and r.json()["user_id"] == "explainer"


def test_an_unknown_session_never_borrows_an_unverified_pane(client):
    # A daemon-hosted Codex session naming mongoose's pane must not become mongoose.
    register(client, "0:0.0", "mongoose")  # registered before session ids existed
    r = send(client, tmux_pane="0:0.0", agent_id="sess-stranger", pane_verified=False)
    assert r.status_code == 404
    assert "not running inside pane" in r.json()["detail"]["detail"]
    assert whoami(client, tmux_pane="0:0.0", agent_id="sess-stranger")["user_id"] is None


def test_a_verified_pane_adopts_the_session_onto_a_registration_without_one(client):
    # Agents registered before the CLI sent session ids get theirs on first contact.
    register(client, "0:0.0", "mongoose")
    r = send(client, tmux_pane="0:0.0", agent_id="sess-mongoose", pane_verified=True)
    assert r.status_code == 200
    # From now on the session alone identifies it, even from a background host.
    assert whoami(client, agent_id="sess-mongoose")["user_id"] == "mongoose"


def test_a_pane_held_by_a_different_session_is_refused(client):
    register(client, "0:0.0", "mongoose", agent_id="sess-mongoose")
    r = send(client, tmux_pane="0:0.0", agent_id="sess-other", pane_verified=True)
    assert r.status_code == 404
    assert "different session" in r.json()["detail"]["detail"]


def test_a_new_session_inside_the_registered_pane_takes_over_the_registration(client):
    # shoveler's case: /clear in its pane gave Claude Code a new session id.
    # Messages still arrived by pane, but every reply was refused.
    client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "shoveler",
                                   "agent_id": "sess-old", "flavor": "claude"})
    r = send(client, tmux_pane="0:0.0", agent_id="sess-new", pane_verified=True,
             pane_in_tree=True, harness="claude")
    assert r.status_code == 200, r.text
    assert client.get("/api/state").json()["messages"][-1]["sender"] == "shoveler"
    assert whoami(client, agent_id="sess-new")["user_id"] == "shoveler"
    assert whoami(client, agent_id="sess-old")["user_id"] is None


def test_a_new_session_takes_over_only_from_inside_the_pane_with_the_same_harness(client):
    client.post("/register", json={"tmux_pane": "0:0.0", "requested_user": "shoveler",
                                   "agent_id": "sess-old", "flavor": "claude"})
    # An explicit --pane is "verified" but proves nothing about the process tree.
    assert send(client, tmux_pane="0:0.0", agent_id="sess-x", pane_verified=True,
                harness="claude").status_code == 404
    # A Codex session inside a pane registered for Claude is someone else.
    assert send(client, tmux_pane="0:0.0", agent_id="sess-y", pane_verified=True,
                pane_in_tree=True, harness="codex").status_code == 404
    assert whoami(client, agent_id="sess-old")["user_id"] == "shoveler"


def test_without_a_session_id_the_pane_is_the_identity_as_before(client):
    # Older CLIs send no agent_id.
    register(client, "0:0.0", "otter")
    assert whoami(client, tmux_pane="0:0.0")["user_id"] == "otter"
    assert send(client, tmux_pane="0:0.0").status_code == 200


def test_a_node_cannot_speak_as_another_nodes_session(hub):
    # Session ids are public; knowing one must not let a node act as that agent.
    register(owner(hub), "%1", "otter", agent_id="hub-session")
    token = enrol(hub, "macbook")
    node = remote(hub, token)
    r = node.post("/send", json={"node": "macbook", "agent_id": "hub-session",
                                 "recipient": "owner", "content": "x"})
    assert r.status_code == 404
    assert "another node" in r.json()["detail"]["detail"]
    answer = node.get("/whoami", params={"node": "macbook", "agent_id": "hub-session"}).json()
    assert answer["user_id"] is None


def test_a_node_resolves_its_own_sessions(hub):
    token = enrol(hub, "macbook")
    node = remote(hub, token)
    r = node.post("/register", json={"tmux_pane": "%1", "node": "macbook",
                                      "agent_id": "mac-session", "requested_user": "puffin"})
    assert r.status_code == 200, r.text
    answer = node.get("/whoami", params={"node": "macbook", "agent_id": "mac-session"}).json()
    assert answer["user_id"] == "puffin" and answer["identified_by"] == "session"


# --- review fixes -------------------------------------------------------------

def test_without_a_session_an_unverified_pane_is_refused(client):
    # A new CLI says it isn't in the pane and has no session id: never that agent.
    register(client, "0:0.0", "otter")
    r = send(client, tmux_pane="0:0.0", pane_verified=False)
    assert r.status_code == 404 and "not running inside pane" in r.json()["detail"]["detail"]
    assert whoami(client, tmux_pane="0:0.0", pane_verified="false")["user_id"] is None


def test_a_known_session_is_resolved_before_the_pane_is_looked_at(client, monkeypatch):
    # A stale or unresolvable pane must not reject a valid session.
    from agent_swarm import tmux
    register(client, "0:1.0", "explainer", agent_id="sess-explainer")

    def resolve(target):
        raise AssertionError("the pane should not be resolved for a known session")

    monkeypatch.setattr(tmux, "resolve_pane", resolve)
    r = send(client, tmux_pane="9:9.9", agent_id="sess-explainer", pane_verified=False)
    assert r.status_code == 200


def test_an_empty_stored_id_is_adopted_too(client, tmp_path):
    import sqlite3
    register(client, "0:0.0", "mongoose")
    # The client fixture's database (pytest shares tmp_path within a test).
    conn = sqlite3.connect(tmp_path / "db.sqlite")
    assert conn.execute("UPDATE recipients SET agent_id='' WHERE user_id='mongoose'").rowcount == 1
    conn.commit()
    conn.close()
    assert send(client, tmux_pane="0:0.0", agent_id="sess-mongoose", pane_verified=True).status_code == 200
    assert whoami(client, agent_id="sess-mongoose")["user_id"] == "mongoose"


def test_a_lost_adoption_race_is_not_reported_as_success(client, monkeypatch):
    from agent_swarm import db
    register(client, "0:0.0", "mongoose")
    monkeypatch.setattr(db, "adopt_agent_id", lambda conn, user_id, agent_id, **kwargs: False)
    r = send(client, tmux_pane="0:0.0", agent_id="sess-mongoose", pane_verified=True)
    assert r.status_code == 404 and "could not record this session" in r.json()["detail"]["detail"]


def test_adoption_is_atomic_in_the_database(tmp_path):
    from agent_swarm import db
    conn = db.connect(tmp_path / "db.sqlite")
    for user, pane in (("a", "%1"), ("b", "%2")):
        db.register(conn, user, pane, node="local", tmux_server="srv-1")
    assert db.adopt_agent_id(conn, "a", "sess-1", node="local", tmux_pane="%1", tmux_server="srv-1") is True
    assert db.adopt_agent_id(conn, "a", "sess-2", node="local", tmux_pane="%1", tmux_server="srv-1") is False  # a already has one
    assert db.adopt_agent_id(conn, "b", "sess-1", node="local", tmux_pane="%2", tmux_server="srv-1") is False  # sess-1 is a's
    assert db.lookup_user_by_agent_id(conn, "sess-1") == "a"


def test_a_mismatched_id_says_how_to_reregister(client):
    register(client, "0:0.0", "heron", agent_id="old-imported-id")
    r = send(client, tmux_pane="0:0.0", agent_id="actual-session", pane_verified=True)
    detail = r.json()["detail"]["detail"]
    assert r.status_code == 404 and "buzz register` from this pane (without --name)" in detail
    # Nothing was overwritten.
    assert whoami(client, agent_id="old-imported-id")["user_id"] == "heron"
    repaired = client.post("/register", json={"tmux_pane": "0:0.0", "agent_id": "actual-session"})
    assert repaired.status_code == 200 and repaired.json()["user_id"] == "heron"
    assert send(client, agent_id="actual-session").status_code == 200


def test_task_notifications_go_out_as_the_session_not_the_guessed_pane(client):
    register(client, "0:0.0", "numbat", agent_id="sess-numbat")
    register(client, "0:1.0", "explainer", agent_id="sess-explainer")
    r = client.post("/tasks", json={
        "title": "check the dashboard", "assignee": "numbat",
        "tmux_pane": "0:0.0", "agent_id": "sess-explainer", "pane_verified": False,
    })
    assert r.status_code == 200, r.text
    note = [m for m in client.get("/api/state").json()["messages"] if m["recipient"] == "numbat"][-1]
    assert note["sender"] == "explainer"
    task_id = r.json()["task"]["id"]
    r = client.patch(f"/tasks/{task_id}", json={"assignee": "numbat", "status": "open",
                                                "agent_id": "sess-stranger", "tmux_pane": "0:0.0",
                                                "pane_verified": False})
    assert r.status_code == 404  # an unknown session can't act as numbat either


def test_session_adoption_requires_the_same_pane_binding(tmp_path):
    from agent_swarm import db
    conn = db.connect(tmp_path / 'cas.sqlite')
    db.register(conn, 'a', '%2', node='other-node', tmux_server='srv-2')
    assert not db.adopt_agent_id(conn, 'a', 'sess-x', node='local', tmux_pane='%1', tmux_server='srv-1')
    assert db.lookup_user_by_agent_id(conn, 'sess-x') is None


def test_session_swap_requires_the_expected_old_id(tmp_path):
    from agent_swarm import db
    conn = db.connect(tmp_path / 'swap.sqlite')
    db.register(conn, 'a', '%1', node='local', tmux_server='srv-1', agent_id='sess-old')
    # Someone else moved it first: the swap must not apply over their id.
    assert not db.adopt_agent_id(conn, 'a', 'sess-new', node='local', tmux_pane='%1',
                                 tmux_server='srv-1', replacing='sess-stale')
    assert db.adopt_agent_id(conn, 'a', 'sess-new', node='local', tmux_pane='%1',
                             tmux_server='srv-1', replacing='sess-old')
    assert db.lookup_user_by_agent_id(conn, 'sess-new') == 'a'


def test_unverified_task_caller_is_not_treated_as_owner(client):
    register(client, '0:0.0', 'otter')
    r = client.post('/tasks', json={'title': 'not owner', 'tmux_pane': '0:0.0', 'pane_verified': False})
    assert r.status_code == 404
