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


def test_rename_team_preserves_identity_members_queen_and_tasks(client):
    user = _register(client)
    team = _make_team(client)
    client.post(f"/agents/{user}/team", json={"team_id": team["id"]})
    client.patch(f"/teams/{team['id']}", json={"queen": user})
    task = client.post("/tasks", json={"title": "team work", "team_id": team["id"]}).json()["task"]
    calls_before = len(client._calls)
    response = client.patch(f"/teams/{team['id']}", json={"name": "  new name  "})
    assert response.status_code == 200
    renamed = response.json()["team"]
    assert (renamed["id"], renamed["name"], renamed["queen"], renamed["members"]) == (
        team["id"], "new name", user, [user]
    )
    assert len(client._calls) == calls_before  # renaming must not promote the queen again
    state = client.get("/api/state").json()
    assert state["teams"][0]["name"] == "new name"
    assert next(t for t in state["tasks"] if t["id"] == task["id"])["team_id"] == team["id"]
    assert client.patch(f"/teams/{team['id']}", json={"name": "new name"}).status_code == 200


def test_duplicate_team_name_returns_conflict_without_mutation(client):
    first = _make_team(client, "first")
    second = _make_team(client, "second")
    user = _register(client)
    client.post(f"/agents/{user}/team", json={"team_id": second["id"]})
    calls_before = len(client._calls)
    response = client.patch(f"/teams/{second['id']}", json={"name": " first ", "queen": user})
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == 'A team named "first" already exists.'
    teams = client.get("/teams").json()["teams"]
    assert [(t["id"], t["name"], t["queen"]) for t in teams] == [
        (first["id"], "first", None), (second["id"], "second", None)
    ]
    assert len(client._calls) == calls_before
    assert client.post("/teams", json={"name": " first "}).status_code == 409


@pytest.mark.parametrize("name", ["", "   "])
def test_empty_team_name_is_refused(client, name):
    team = _make_team(client)
    assert client.patch(f"/teams/{team['id']}", json={"name": name}).status_code == 422
    assert client.post("/teams", json={"name": name}).status_code == 422
    assert client.get("/teams").json()["teams"][0]["name"] == team["name"]


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


def test_teams_can_be_reordered_atomically(client):
    first = _make_team(client, "first")
    second = _make_team(client, "second")
    third = _make_team(client, "third")
    assert [t["name"] for t in client.get("/teams").json()["teams"]] == ["first", "second", "third"]

    response = client.post("/teams/reorder", json={"order": [third["id"], first["id"], second["id"]]})
    assert response.status_code == 200
    assert [t["id"] for t in response.json()["teams"]] == [third["id"], first["id"], second["id"]]
    state = client.get("/api/state").json()
    assert [t["id"] for t in state["teams"]] == [third["id"], first["id"], second["id"]]

    # A partial, duplicate, unknown or mismatched order changes nothing.
    for order in ([first["id"], second["id"]], [third["id"], first["id"], 9999],
                  [third["id"], first["id"], first["id"]]):
        assert client.post("/teams/reorder", json={"order": order}).status_code == 422
        assert [t["id"] for t in client.get("/teams").json()["teams"]] == [third["id"], first["id"], second["id"]]
    assert client.post("/teams/reorder", json={"order": [third["id"], first["id"], second["id"], third["id"]]}).status_code == 422
    assert client.post("/teams/reorder", json={}).status_code == 422

    # New teams join the end, and the chosen display order survives deletion.
    fourth = _make_team(client, "fourth")
    assert [t["name"] for t in client.get("/teams").json()["teams"]] == ["third", "first", "second", "fourth"]
    client.delete(f"/teams/{first['id']}")
    assert [t["id"] for t in client.get("/teams").json()["teams"]] == [third["id"], second["id"], fourth["id"]]


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
    assert "`buzz team`" in delivered[0]  # the queen learns the team view
    promo = client.get("/messages", params={"user": a}).json()["messages"][0]
    assert promo["context"] == "queen-promotion"
    assert "handover is coming" not in promo["content"]



def _queen_messages(client, user):
    return [m for m in client.get("/messages", params={"user": user}).json()["messages"]
            if m["context"] in ("queen-promotion", "queen-handover", "queen-status")]


@pytest.mark.parametrize("offline", ["old", "member"])
def test_offline_handover_recipient_does_not_block_promotion(client, offline):
    old = _register(client, "0:0.0")
    new = _register(client, "0:1.0")
    shell = _register(client, "0:2.0")
    team = _make_team(client)
    for user in (old, new, shell):
        client.post(f"/agents/{user}/team", json={"team_id": team["id"]})
    # A shell queen cannot receive its promotion, but the crown is still set.
    previous = shell if offline == "old" else old
    client.patch(f"/teams/{team['id']}", json={"queen": previous})
    response = client.patch(f"/teams/{team['id']}", json={"queen": new})
    assert response.status_code == 200
    assert response.json()["promotion"]["ok"] is True
    assert _queen_messages(client, new)[0]["context"] == "queen-promotion"
    failed = _queen_messages(client, shell)[0]
    assert failed["status"] == "failed"
    assert failed["context"] == ("queen-handover" if offline == "old" else "queen-status")


def test_rejected_or_unchanged_queen_membership_does_not_notify(client):
    old = _register(client)
    team = _make_team(client)
    client.post(f"/agents/{old}/team", json={"team_id": team["id"]})
    client.patch(f"/teams/{team['id']}", json={"queen": old})
    before = len(client._calls)
    assert client.patch(f"/teams/{team['id']}", json={"queen": "nobody"}).status_code == 400
    assert client.post(f"/agents/{old}/team", json={"team_id": 999}).status_code == 404
    assert client.post(f"/agents/{old}/team", json={"team_id": team["id"]}).status_code == 200
    assert len(client._calls) == before
    assert client.get("/teams").json()["teams"][0]["queen"] == old


def test_queen_replacement_notifies_old_new_and_other_members(client, monkeypatch):
    from agent_swarm import tmux

    # Add a third live agent so the member notice is a real delivery.
    table = tmux.pane_table()
    table["0:3.0"] = {"label": "0:3.0", "command": "claude", "title": ""}
    monkeypatch.setattr(tmux, "pane_table", lambda: table)
    monkeypatch.setattr(tmux, "list_panes", lambda: set(table))
    monkeypatch.setattr(tmux, "live_agent_panes", lambda: {"0:0.0", "0:1.0", "0:3.0"})
    old, new, member = [_register(client, pane) for pane in ("0:0.0", "0:1.0", "0:3.0")]
    team = _make_team(client, "skunkworks")
    for user in (old, new, member):
        client.post(f"/agents/{user}/team", json={"team_id": team["id"]})
    client.patch(f"/teams/{team['id']}", json={"queen": old})
    before = len(client._calls)
    response = client.patch(f"/teams/{team['id']}", json={"queen": new, "objective": "Ship"})
    assert response.status_code == 200
    assert response.json()["promotion"]["ok"] is True
    assert len(client._calls) - before == 3
    handover = _queen_messages(client, old)[0]
    assert handover["context"] == "queen-handover"
    assert handover["sender"] == "owner"
    assert handover["content"] == (
        "You are no longer queen of team 'skunkworks'. "
        f"{new} is now queen. Send {new} a handover now with "
        f'`buzz send --to {new} --context queen-handover --message "..."`: '
        "branches waiting for review or landing, worktrees to clean up, "
        "decisions pending with the owner, and promises to other teams or agents. "
        "Stop coordinating this team."
    )
    promotion = _queen_messages(client, new)
    assert len(promotion) == 1
    assert promotion[0]["context"] == "queen-promotion"
    assert f"The previous queen was {old}; a handover is coming. Start with `buzz team`." in promotion[0]["content"]
    notices = _queen_messages(client, member)
    assert len(notices) == 1
    assert notices[0]["context"] == "queen-status"
    assert notices[0]["content"] == f"The queen of team 'skunkworks' is now {new}."

    # Re-applying the queen may refresh the objective, but is not a handover.
    before = len(client._calls)
    response = client.patch(f"/teams/{team['id']}", json={"queen": new, "objective": "New goal"})
    assert response.status_code == 200
    assert len(client._calls) - before == 1
    assert "handover is coming" not in _queen_messages(client, new)[0]["content"]
    assert len(_queen_messages(client, old)) == 2  # first promotion + handover
    assert len(_queen_messages(client, member)) == 1


@pytest.mark.parametrize("change", ["clear", "leave", "move"])
def test_queen_clearing_or_leaving_notifies_only_the_old_queen(client, change):
    old = _register(client, "0:0.0")
    member = _register(client, "0:1.0")
    team = _make_team(client, "skunkworks")
    for user in (old, member):
        client.post(f"/agents/{user}/team", json={"team_id": team["id"]})
    client.patch(f"/teams/{team['id']}", json={"queen": old})
    before = len(client._calls)
    if change == "clear":
        response = client.patch(f"/teams/{team['id']}", json={"queen": None})
        assert response.json()["promotion"] is None
    else:
        target = _make_team(client, "other")["id"] if change == "move" else None
        response = client.post(f"/agents/{old}/team", json={"team_id": target})
    assert response.status_code == 200
    assert client.get("/teams").json()["teams"][0]["queen"] is None
    assert len(client._calls) - before == 1
    message = _queen_messages(client, old)[0]
    assert message["context"] == "queen-handover"
    assert message["content"] == "You are no longer queen of team 'skunkworks'. Stop coordinating this team."
    assert not _queen_messages(client, member)



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
    assert "for your team 'buildcrew'" in delivered[0]
    assert "parcel it out" in delivered[0]
    # The message names the work, not the roster: `buzz team` and the
    # registration brief cover who is around.
    assert "You are on team" not in delivered[0]
    assert len(delivered[0]) < 400

    # queen hands it to a member: assignee set, team cleared, and the member
    # gets the same short assignment hint as any other assignment
    calls_before = len(client._calls)
    r = client.patch(f"/tasks/{task['id']}", json={"assignee": a})
    task = r.json()["task"]
    assert task["assignee"] == a and task["team_id"] is None
    delivered = [text for _, text, *_ in client._calls[calls_before:]]
    assert len(delivered) == 1
    assert f"You are assigned task #{task['id']}" in delivered[0]
    assert "You are on team" not in delivered[0]

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
    assert all("--assignee <yourself>" in text for text in delivered)
    # No roster: each member looks up the team with `buzz team`.
    assert all("You are on team" not in text for text in delivered)


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


def test_assignment_message_stays_short(client):
    # The owner's ask (#537): a task message is the work plus three sentences
    # of instructions, with no roster and no second copy of the note guidance.
    a, b, c, team = _crew_with_one_offline(client)
    calls_before = len(client._calls)
    client.post("/tasks", json={"title": "solo", "assignee": a})
    delivered = [text for _, text, *_ in client._calls[calls_before:]]
    assert len(delivered) == 1
    message = delivered[0]
    assert len(message) < 600, message
    assert "worktree" in message and "--status picked_up" in message
    assert "--status done --note" in message and "the note is required" in message
    # Status is asked for as the work moves, not once at the start.
    assert 'buzz status' in message and '"done: #' in message
    # The roster and the long note guidance stay out of every task message.
    assert "You are on team" not in message
    assert "how to use it" not in message
    assert b not in message and c not in message


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


def _queen_team(client, name="hivemind"):
    sender = _register(client, pane="0:0.0")
    queen = _register(client, pane="0:1.0")
    team = _make_team(client, name)
    client.post(f"/agents/{queen}/team", json={"team_id": team["id"]})
    client.patch(f"/teams/{team['id']}", json={"queen": queen})
    return sender, queen, team


def test_send_to_queen_by_team_name_or_id_reaches_the_current_queen(client):
    sender, queen, team = _queen_team(client)
    for ref in ("hivemind", "HiveMind", str(team["id"])):
        r = client.post("/send", json={"tmux_pane": "0:0.0", "recipient": f"queen:{ref}", "content": f"hi {ref}"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["recipient"] == queen and body["team"] == {"id": team["id"], "name": "hivemind"}
    stored = client.get("/messages", params={"user": queen}).json()["messages"]
    assert sorted(m["content"] for m in stored if m["sender"] == sender) == sorted(["hi hivemind", "hi HiveMind", f"hi {team['id']}"])
    # A queen change is followed at send time.
    new = _register(client, pane="0:2.0")
    client.post(f"/agents/{new}/team", json={"team_id": team["id"]})
    client.patch(f"/teams/{team['id']}", json={"queen": new})
    client.post("/send", json={"tmux_pane": "0:0.0", "recipient": "queen:hivemind", "content": "again"})
    last = client.get("/messages", params={"limit": 1}).json()["messages"][0]
    assert last["content"] == "again" and last["recipient"] == new


def test_send_to_queen_reports_unknown_team_and_missing_queen_without_storing(client):
    _register(client, pane="0:0.0")
    team = _make_team(client, "leaderless")
    before = client.get("/messages", params={"limit": 100}).json()["messages"]
    r = client.post("/send", json={"tmux_pane": "0:0.0", "recipient": "queen:nope", "content": "x"})
    assert r.status_code == 404 and r.json()["detail"]["error"] == "no such team"
    r = client.post("/send", json={"tmux_pane": "0:0.0", "recipient": f"queen:{team['id']}", "content": "x"})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "team has no queen"
    assert client.get("/messages", params={"limit": 100}).json()["messages"] == before


def test_send_to_queen_who_cannot_receive_is_recorded_as_undelivered(client):
    _register(client, pane="0:0.0")
    shell = _register(client, pane="0:2.0")  # a bare shell: not a live agent
    team = _make_team(client)
    client.post(f"/agents/{shell}/team", json={"team_id": team["id"]})
    client.patch(f"/teams/{team['id']}", json={"queen": shell})
    r = client.post("/send", json={"tmux_pane": "0:0.0", "recipient": "queen:hivemind", "content": "hello?"})
    assert r.status_code == 409
    msg = client.get("/messages", params={"limit": 1}).json()["messages"][0]
    assert msg["recipient"] == shell and msg["content"] == "hello?" and not msg["delivered"]


def test_send_to_queen_after_the_queen_leaves_says_the_team_has_none(client):
    sender, queen, team = _queen_team(client)
    client.delete(f"/recipients/{queen}")
    r = client.post("/send", json={"tmux_pane": "0:0.0", "recipient": "queen:hivemind", "content": "hello?"})
    assert r.status_code == 409 and r.json()["detail"]["error"] == "team has no queen"


def test_team_tasks_lists_members_and_team_work_by_name_or_id(client):
    outsider, queen, team = _queen_team(client)
    member = _register(client, pane="0:2.0")
    client.post(f"/agents/{member}/team", json={"team_id": team["id"]})
    ids = {}
    for title, body in [("queen's", {"assignee": queen}), ("member's", {"assignee": member}),
                        ("team's", {"team_id": team["id"]}), ("outside", {"assignee": outsider}),
                        ("unassigned", {})]:
        ids[title] = client.post("/tasks", json={"title": title, **body}).json()["task"]["id"]
    for ref in ("hivemind", "HIVEMIND", str(team["id"])):
        r = client.get(f"/teams/{ref}/tasks")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["team"] == {"id": team["id"], "name": "hivemind", "queen": queen}
        assert sorted(t["id"] for t in body["tasks"]) == sorted(ids[k] for k in ("queen's", "member's", "team's"))
    assert client.get("/teams/nope/tasks").status_code == 404
