"""`buzz team`: one team for its queen (agent_swarm/team_view.py and its endpoint)."""

from agent_swarm import client as cli
from agent_swarm import team_view

HOUR = 3600.0
NOW = 1_000_000.0


def _rec(handle, node="linux", alive=True, activity="working", status=None):
    summaries = [{"text": status[0], "source": "agent", "ts": status[1]}] if status else []
    return {"user_id": handle, "node": node, "alive": alive,
            "offline_reason": None if alive else "pane gone",
            "activity": {"status": activity}, "summaries": summaries}


def _task(id, title, assignee=None, status="open", deps=(), team_id=None, updated=NOW - 60):
    return {"id": id, "title": title, "assignee": assignee, "status": status, "team_id": team_id,
            "depends_on": list(deps), "updated_at": updated, "created_at": updated}


TEAM = {"id": 7, "name": "hive", "queen": "galago", "members": ["galago", "gannet", "skink", "vole", "wren"]}


def _view(tasks, recipients=None, last_sent=None, **kw):
    recipients = recipients or [
        _rec("galago", status=("coordinating", NOW - 120)),
        _rec("gannet", status=("working on #2", NOW - 300)),
        _rec("skink", node="mac", activity="idle"),
        _rec("vole", alive=False),
        _rec("wren", activity="idle"),
    ]
    return team_view.build(NOW, TEAM, recipients, tasks, {"gannet": NOW - 600}, last_sent or {}, "linux", **kw)


def test_task_states_follow_deps_and_silence():
    tasks = [
        _task(1, "outside dep, done", "someone", status="done"),
        _task(2, "in progress", "gannet", status="picked_up", deps=[1]),
        _task(3, "waits on 2", "skink", deps=[2]),
        _task(4, "deps done", "vole", deps=[1]),
        _task(5, "quiet", "skink", status="picked_up", updated=NOW - 5 * HOUR),
        _task(6, "finished", "gannet", status="done"),
    ]
    view = _view(tasks)
    by_id = {t["id"]: t for t in view["tasks"]}
    assert sorted(by_id) == [2, 3, 4, 5]  # open team tasks; done and outside ones are left out
    assert by_id[2]["state"] == "in_progress"
    assert by_id[3]["state"] == "blocked" and by_id[3]["blocked_by"] == [2]
    assert by_id[3]["depends_on"] == [{"id": 2, "status": "picked_up", "title": "in progress"}]
    assert by_id[4]["state"] == "ready"
    assert by_id[5]["state"] == "stale"
    # A longer window, or a recent message from the holder, keeps it in progress.
    assert {t["id"]: t["state"] for t in _view(tasks, stale_hours=6)["tasks"]}[5] == "in_progress"
    heard = _view(tasks, last_sent={"skink": NOW - 60})
    assert {t["id"]: t["state"] for t in heard["tasks"]}[5] == "in_progress"


def test_members_show_state_status_tasks_and_last_message_to_queen():
    view = _view([_task(2, "in progress", "gannet", status="picked_up")])
    m = {x["handle"]: x for x in view["members"]}
    assert [x["state"] for x in view["members"]] == ["live", "live", "idle", "offline", "idle"]
    assert m["galago"]["queen"] and not m["gannet"]["queen"]
    assert m["gannet"]["status"] == {"text": "working on #2", "ts": NOW - 300}
    assert m["gannet"]["open_tasks"] == [{"id": 2, "title": "in progress", "status": "picked_up"}]
    assert m["gannet"]["last_to_queen"] == NOW - 600 and m["skink"]["last_to_queen"] is None
    assert m["skink"]["may_sleep"] and not m["gannet"]["may_sleep"]
    text = view["text"]
    assert 'gannet · linux · live · "working on #2" (5m) · last to queen' in text
    assert "skink · mac (may sleep) · idle · (no status line)" in text
    assert "vole · linux · offline: pane gone" in text
    assert "      #2 picked_up · in progress" in text


def test_owner_notes_are_not_status_lines():
    rec = _rec("gannet")
    rec["summaries"] = [{"text": "owner note", "source": "owner", "ts": NOW - 10},
                        {"text": "mine", "source": "agent", "ts": NOW - 20}]
    view = _view([], recipients=[rec])
    assert next(m for m in view["members"] if m["handle"] == "gannet")["status"]["text"] == "mine"


def test_flags_free_members_unassigned_offline_sleepy_and_stale():
    tasks = [
        _task(2, "busy", "gannet", status="picked_up"),
        _task(3, "on the mac", "skink"),
        _task(4, "on a dead pane", "vole"),
        _task(8, "for the team", team_id=7),
        _task(9, "stale on the mac", "skink", status="picked_up", updated=NOW - 9 * HOUR),
    ]
    flags = [(f["kind"], f["member"], f["task"]) for f in _view(tasks)["flags"]]
    assert flags == [
        ("free", "wren", None),  # not the queen, not offline, nothing open
        ("may_sleep", "skink", 3),
        ("offline", "vole", 4),
        ("unassigned", None, 8),
        ("may_sleep", "skink", 9),
        ("stale", "skink", 9),
    ]


def test_since_keeps_only_changed_members_and_tasks_but_all_flags():
    tasks = [
        _task(2, "touched", "gannet", status="picked_up", updated=NOW - 60),
        _task(3, "old", "skink", updated=NOW - 5 * HOUR),
    ]
    view = _view(tasks, since=NOW - HOUR)
    # galago changed its status line, gannet's task moved; skink did neither.
    assert [m["handle"] for m in view["members"]] == ["galago", "gannet"]
    assert [t["id"] for t in view["tasks"]] == [2]
    assert ("may_sleep", 3) in [(f["kind"], f["task"]) for f in view["flags"]]
    assert view["text"].endswith(f"next: buzz team hive --since {int(NOW)}")


def test_parse_since_takes_durations_or_epoch_seconds():
    assert cli._parse_since("30m", NOW) == NOW - 1800
    assert cli._parse_since("2h", NOW) == NOW - 2 * HOUR
    assert cli._parse_since("1d", NOW) == NOW - 24 * HOUR
    assert cli._parse_since("1795126015", NOW) == 1795126015.0


# ---- endpoint ------------------------------------------------------------------


def _member(client, team_id, pane, name):
    user = client.post("/register", json={"tmux_pane": pane, "requested_user": name}).json()["user_id"]
    client.post(f"/agents/{user}/team", json={"team_id": team_id})
    return user


def test_view_endpoint_by_name_or_id(client):
    team = client.post("/teams", json={"name": "hive"}).json()["team"]
    queen = _member(client, team["id"], "0:0.0", "galago")
    worker = _member(client, team["id"], "0:1.0", "gannet")
    shell = _member(client, team["id"], "0:2.0", "vole")  # a bare shell: offline
    client.patch(f"/teams/{team['id']}", json={"queen": queen})
    client.post("/status", json={"tmux_pane": "0:1.0", "text": "working on the base"})
    client.post("/send", json={"tmux_pane": "0:1.0", "recipient": queen, "content": "branch ready"})
    base = client.post("/tasks", json={"title": "base", "assignee": worker}).json()["task"]
    client.patch(f"/tasks/{base['id']}", json={"status": "picked_up"})
    top = client.post("/tasks", json={"title": "top", "assignee": shell, "depends_on": [base["id"]]}).json()["task"]
    loose = client.post("/tasks", json={"title": "loose", "team_id": team["id"]}).json()["task"]

    for ref in ("hive", str(team["id"])):
        r = client.get(f"/teams/{ref}/view")
        assert r.status_code == 200, r.text
    body = r.json()
    assert body["team"] == {"id": team["id"], "name": "hive", "queen": queen}
    members = {m["handle"]: m for m in body["members"]}
    assert members[worker]["state"] != "offline" and members[shell]["state"] == "offline"
    assert members[worker]["status"]["text"] == "working on the base"
    assert members[worker]["last_to_queen"] is not None
    states = {t["id"]: (t["state"], t["blocked_by"]) for t in body["tasks"]}
    assert states == {base["id"]: ("in_progress", []), top["id"]: ("blocked", [base["id"]]),
                      loose["id"]: ("ready", [])}
    kinds = {(f["kind"], f["task"]) for f in body["flags"]}
    assert ("offline", top["id"]) in kinds and ("unassigned", loose["id"]) in kinds
    assert "team hive · queen galago" in body["text"]

    later = client.get("/teams/hive/view", params={"since": body["now"] + 1}).json()
    assert later["tasks"] == [] and later["members"] == []
    assert client.get("/teams/nope/view").status_code == 404


def test_digest_team_keeps_only_that_teams_agents_tasks_and_messages(client):
    team = client.post("/teams", json={"name": "hive"}).json()["team"]
    member = _member(client, team["id"], "0:0.0", "gannet")
    outsider = client.post("/register", json={"tmux_pane": "0:1.0", "requested_user": "otter"}).json()["user_id"]
    client.post("/tasks", json={"title": "ours", "assignee": member})
    client.post("/tasks", json={"title": "theirs", "assignee": outsider})
    client.post("/send", json={"tmux_pane": "0:0.0", "recipient": "owner", "content": "from the team"})
    client.post("/send", json={"tmux_pane": "0:1.0", "recipient": "owner", "content": "from outside"})
    whole = client.get("/digest").json()["text"]
    assert "theirs" in whole and "from outside" in whole
    text = client.get("/digest", params={"team": "hive"}).json()["text"]
    assert "ours" in text and "from the team" in text
    assert "theirs" not in text and "from outside" not in text
    assert client.get("/digest", params={"team": "nope"}).status_code == 404
