"""Teams: membership, queen promotion, team tasks, and dependency graph."""

import pytest

from tests.test_server import client  # noqa: F401  (reuse the app fixture)


def _register(client, pane="0:0.0", model="m"):
    r = client.post("/register", json={"tmux_pane": pane, "model": model})
    assert r.status_code == 200
    return r.json()["user_id"]


def _make_team(client, name="hivemind"):
    r = client.post("/teams", json={"name": name})
    assert r.status_code == 200
    return r.json()["team"]


def test_team_crud_and_membership(client):
    a = _register(client, "0:0.0")
    b = _register(client, "0:1.0")
    team = _make_team(client)
    assert team["queen"] is None and team["members"] == []

    for user in (a, b):
        r = client.post(f"/agents/{user}/team", json={"team_id": team["id"]})
        assert r.status_code == 200
        assert r.json()["recipient"]["team_id"] == team["id"]
    listed = client.get("/teams").json()["teams"][0]
    assert sorted(listed["members"]) == sorted([a, b])

    # membership is exposed on state
    state = client.get("/api/state").json()
    assert state["teams"][0]["id"] == team["id"]
    assert all(r["team_id"] == team["id"] for r in state["recipients"])

    # leaving a team
    r = client.post(f"/agents/{a}/team", json={"team_id": None})
    assert r.status_code == 200
    assert r.json()["recipient"]["team_id"] is None
    assert client.get("/teams").json()["teams"][0]["members"] == [b]

    # unknown team rejected
    r = client.post(f"/agents/{b}/team", json={"team_id": 999})
    assert r.status_code == 404

    # disband clears membership
    assert client.delete(f"/teams/{team['id']}").status_code == 200
    assert client.get("/teams").json()["teams"] == []
    state = client.get("/api/state").json()
    assert all(r["team_id"] is None for r in state["recipients"])


def test_unregister_queen_clears_role_without_removing_teammates(client):
    queen = _register(client, "0:0.0")
    teammate = _register(client, "0:1.0")
    team = _make_team(client)
    for user in (queen, teammate):
        client.post(f"/agents/{user}/team", json={"team_id": team["id"]})
    assert client.patch(f"/teams/{team['id']}", json={"queen": queen}).status_code == 200
    assert client.delete(f"/recipients/{queen}").status_code == 200
    remaining = client.get("/teams").json()["teams"][0]
    assert remaining["queen"] is None
    assert remaining["members"] == [teammate]


def test_queen_promotion_delivers_scoped_prompt(client):
    a = _register(client, "0:0.0")
    b = _register(client, "0:1.0")
    team = _make_team(client, "skunkworks")
    for user in (a, b):
        client.post(f"/agents/{user}/team", json={"team_id": team["id"]})

    # a non-member cannot be queen
    r = client.patch(f"/teams/{team['id']}", json={"queen": "nobody"})
    assert r.status_code == 400

    calls_before = len(client._calls)
    r = client.patch(
        f"/teams/{team['id']}",
        json={"queen": a, "objective": "Ship the widget"},
    )
    assert r.status_code == 200
    assert r.json()["team"]["queen"] == a
    assert r.json()["promotion"]["ok"] is True
    delivered = [text for _, text, *_ in client._calls[calls_before:]]
    assert len(delivered) == 1
    assert "Queen of team 'skunkworks'" in delivered[0]
    assert b in delivered[0]  # teammates are listed
    assert "Ship the widget" in delivered[0]
    assert "parcel them out" in delivered[0]
    promo = client.get("/messages", params={"user": a}).json()["messages"][0]
    assert promo["context"] == "queen-promotion"

    # clearing the queen sends nothing
    calls_before = len(client._calls)
    r = client.patch(f"/teams/{team['id']}", json={"queen": None})
    assert r.status_code == 200
    assert r.json()["team"]["queen"] is None
    assert len(client._calls) == calls_before

    # a queen who leaves the team loses the crown
    client.patch(f"/teams/{team['id']}", json={"queen": a, "objective": "x"})
    client.post(f"/agents/{a}/team", json={"team_id": None})
    assert client.get("/teams").json()["teams"][0]["queen"] is None


def test_team_task_reaches_queen_and_clears_assignee(client):
    a = _register(client, "0:0.0")
    b = _register(client, "0:1.0")
    team = _make_team(client, "buildcrew")
    for user in (a, b):
        client.post(f"/agents/{user}/team", json={"team_id": team["id"]})
    client.patch(f"/teams/{team['id']}", json={"queen": b, "objective": "x"})

    calls_before = len(client._calls)
    r = client.post("/tasks", json={"title": "big feature", "team_id": team["id"]})
    assert r.status_code == 200
    task = r.json()["task"]
    assert task["team_id"] == team["id"] and task["assignee"] is None
    delivered = [text for _, text, *_ in client._calls[calls_before:]]
    assert len(delivered) == 1  # only the queen is notified
    assert "assigned to your team 'buildcrew'" in delivered[0]
    assert "parcel it out" in delivered[0]
    # the notification names the teammates
    assert f"You are on team 'buildcrew' with {a}" in delivered[0]

    # queen hands it to a member: assignee set, team cleared, and the
    # member still learns its team roster with the assignment
    calls_before = len(client._calls)
    r = client.patch(f"/tasks/{task['id']}", json={"assignee": a})
    task = r.json()["task"]
    assert task["assignee"] == a and task["team_id"] is None
    delivered = [text for _, text, *_ in client._calls[calls_before:]]
    assert len(delivered) == 1
    assert f"You are on team 'buildcrew' with {b} (queen: {b})" in delivered[0]

    # and back to the team: assignee cleared again
    r = client.patch(f"/tasks/{task['id']}", json={"team_id": team["id"]})
    task = r.json()["task"]
    assert task["team_id"] == team["id"] and task["assignee"] is None

    # unknown team rejected
    r = client.post("/tasks", json={"title": "nope", "team_id": 999})
    assert r.status_code == 404


def test_team_task_without_queen_notifies_members(client):
    a = _register(client, "0:0.0")
    b = _register(client, "0:1.0")
    team = _make_team(client, "leaderless")
    for user in (a, b):
        client.post(f"/agents/{user}/team", json={"team_id": team["id"]})
    calls_before = len(client._calls)
    client.post("/tasks", json={"title": "shared job", "team_id": team["id"]})
    delivered = [text for _, text, *_ in client._calls[calls_before:]]
    assert len(delivered) == 2
    assert all("no queen yet" in text for text in delivered)
    # each member is told who the rest of the team is
    rosters = sorted(d.split("You are on team 'leaderless' with ")[1] for d in delivered)
    assert rosters == sorted([f"{a}.", f"{b}."])


def test_task_dependency_graph(client):
    r1 = client.post("/tasks", json={"title": "design"}).json()["task"]
    r2 = client.post(
        "/tasks", json={"title": "build", "depends_on": [r1["id"]]}
    ).json()["task"]
    assert r2["depends_on"] == [r1["id"]]

    r3 = client.post(
        "/tasks", json={"title": "ship", "depends_on": [r1["id"], r2["id"]]}
    ).json()["task"]
    assert r3["depends_on"] == [r1["id"], r2["id"]]

    # deps are listed on state and the tasks endpoint
    listed = {t["id"]: t for t in client.get("/tasks").json()["tasks"]}
    assert listed[r3["id"]]["depends_on"] == [r1["id"], r2["id"]]
    state_tasks = {t["id"]: t for t in client.get("/api/state").json()["tasks"]}
    assert state_tasks[r2["id"]]["depends_on"] == [r1["id"]]

    # replace and clear
    r = client.patch(f"/tasks/{r3['id']}", json={"depends_on": [r2["id"]]})
    assert r.json()["task"]["depends_on"] == [r2["id"]]
    r = client.patch(f"/tasks/{r3['id']}", json={"depends_on": []})
    assert r.json()["task"]["depends_on"] == []

    # self-dependency and cycles rejected
    r = client.patch(f"/tasks/{r1['id']}", json={"depends_on": [r1["id"]]})
    assert r.status_code == 400
    r = client.patch(f"/tasks/{r1['id']}", json={"depends_on": [r2["id"]]})
    assert r.status_code == 400
    # unknown dependency rejected
    r = client.patch(f"/tasks/{r1['id']}", json={"depends_on": [999]})
    assert r.status_code == 400


def _crew_with_one_offline(client):
    a = _register(client, "0:0.0")
    b = _register(client, "0:1.0")
    c = _register(client, "0:2.0")  # a bare shell: registered but not running
    team = _make_team(client, "crew")
    for user in (a, b, c):
        client.post(f"/agents/{user}/team", json={"team_id": team["id"]})
    alive = {r["user_id"]: r["pane_alive"] for r in client.get("/api/state").json()["recipients"]}
    assert alive == {a: True, b: True, c: False}
    return a, b, c, team


def test_team_line_names_only_running_teammates(client):
    a, b, c, team = _crew_with_one_offline(client)
    client.patch(f"/teams/{team['id']}", json={"queen": c, "objective": "x"})
    calls_before = len(client._calls)
    client.post("/tasks", json={"title": "solo", "assignee": a})
    delivered = [text for _, text, *_ in client._calls[calls_before:]]
    assert f"You are on team 'crew' with {b}." in delivered[0]
    assert c not in delivered[0]


def test_retire_forgets_offline_agents_and_refuses_live_ones(client):
    a, b, c, team = _crew_with_one_offline(client)
    client.post("/send", json={"tmux_pane": "0:0.0", "recipient": c, "content": "old note"})
    r = client.post("/recipients/retire", json={"user_ids": [c, a, "nobody", c]})
    assert r.json() == {"ok": True, "retired": [c], "kept_live": [a], "unknown": ["nobody"]}
    state = client.get("/api/state").json()
    assert sorted(r["user_id"] for r in state["recipients"]) == sorted([a, b])
    assert sorted(client.get("/teams").json()["teams"][0]["members"]) == sorted([a, b])
    # Its messages stay in the history.
    assert any(m["recipient"] == c for m in state["messages"])
    assert client.post("/recipients/retire", json={"user_ids": []}).status_code == 422


def test_a_spawned_agent_never_gets_a_retired_agents_name(client, monkeypatch):
    # Task #288: a retired agent's name, reissued, showed its old messages
    # and tasks as the new agent's history.
    from agent_swarm import names

    a, b, c, team = _crew_with_one_offline(client)
    client.post("/send", json={"tmux_pane": "0:0.0", "recipient": c, "content": "old note"})
    client.post("/recipients/retire", json={"user_ids": [c]})
    # The retired name is the only one in the pool, so the new agent gets a
    # numbered variant of it rather than the name itself.
    monkeypatch.setattr(names, "POOL", [c])
    r = client.post("/agents/spawn", json={"flavor": "claude"})
    assert r.status_code == 200
    assert r.json()["user_id"] == f"{c}-2"
    assert not client.get(f"/api/agents/{c}-2/messages?limit=50").json().get("messages")


def test_task_title_and_description_can_be_edited(client):
    task = client.post("/tasks", json={"title": "draft", "description": "old"}).json()["task"]
    r = client.patch(f"/tasks/{task['id']}", json={"title": "  final title ", "description": "new words"})
    assert r.status_code == 200
    assert (r.json()["task"]["title"], r.json()["task"]["description"]) == ("final title", "new words")
    # An empty description clears it; a blank title is refused.
    r = client.patch(f"/tasks/{task['id']}", json={"description": "  "})
    assert r.json()["task"]["description"] is None
    assert client.patch(f"/tasks/{task['id']}", json={"title": "   "}).status_code == 422
    assert client.get("/tasks").json()["tasks"][0]["title"] == "final title"
