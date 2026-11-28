"""Agents are addressed by tmux pane id, so positions that tmux reuses or
renumbers can't send a message to the wrong agent. A small fake tmux keeps
panes by id with a positional label, the way the real one does."""


import pytest
from fastapi.testclient import TestClient

from agent_swarm import db, server, tmux


class FakeTmux:
    def __init__(self):
        self.server = "srv-1"
        self.next_id = 0
        self.panes = {}  # id -> {"label", "command", "title"}
        self.delivered = []

    def add(self, label, command="claude"):
        pane_id = f"%{self.next_id}"
        self.next_id += 1
        self.panes[pane_id] = {"label": label, "command": command, "title": ""}
        return pane_id

    def kill(self, pane_id):
        label = self.panes.pop(pane_id)["label"]
        # tmux renumbers the panes left in a window: s:0.1 becomes s:0.0.
        window, _, index = label.rpartition(".")
        for p in self.panes.values():
            w, _, i = p["label"].rpartition(".")
            if w == window and int(i) > int(index):
                p["label"] = f"{w}.{int(i) - 1}"

    def restart(self):
        """New tmux server: ids start over, positions restored."""
        self.server = "srv-2"
        labels = [(p["label"], p["command"]) for p in self.panes.values()]
        self.panes, self.next_id = {}, 0
        for label, command in labels:
            self.add(label, command)

    def resolve(self, target):
        if target in self.panes:
            return target, self.panes[target]["label"]
        for pane_id, p in self.panes.items():
            if p["label"] == target:
                return pane_id, p["label"]
        return None


@pytest.fixture()
def fake(tmp_path, monkeypatch):
    t = FakeTmux()
    monkeypatch.setattr(tmux, "server_id", lambda: t.server)
    monkeypatch.setattr(tmux, "server_start_time", lambda: 0.0)
    monkeypatch.setattr(tmux, "resolve_pane", t.resolve)
    monkeypatch.setattr(tmux, "pane_table", lambda: {k: dict(v) for k, v in t.panes.items()})
    monkeypatch.setattr(tmux, "list_panes", lambda: set(t.panes))
    monkeypatch.setattr(
        tmux, "live_agent_panes",
        lambda: {k for k, v in t.panes.items() if v["command"] not in tmux.SHELL_COMMANDS},
    )

    def deliver(pane, text, **_):
        t.delivered.append((pane, text))
        return True, None

    def spawn_window(session=tmux.AGENTS_SESSION, command=None, cwd=None):
        used = {int(p["label"].split(":")[1].split(".")[0]) for p in t.panes.values()
                if p["label"].startswith(f"{session}:")}
        index = next(i for i in range(100) if i not in used)  # tmux reuses the lowest free
        label = f"{session}:{index}.0"
        return tmux.Created(t.add(label), label, t.server), None

    def kill_pane(pane):
        t.kill(pane)
        return True, None

    monkeypatch.setattr(tmux, "deliver", deliver)
    monkeypatch.setattr(tmux, "spawn_window", spawn_window)
    monkeypatch.setattr(tmux, "kill_pane", kill_pane)
    monkeypatch.setattr(tmux, "rename_window", lambda *a: (True, None))
    monkeypatch.setattr(tmux, "tag_pane", lambda *a: (True, None))
    t.client = TestClient(server.create_app(tmp_path / "db.sqlite", monitor=False), client=("127.0.0.1", 50000))
    t.db_path = tmp_path / "db.sqlite"
    return t


def register(fake, target, **extra):
    r = fake.client.post("/register", json={"tmux_pane": target, "flavor": "claude", **extra})
    assert r.status_code == 200, r.text
    return r.json()


def recipients(fake):
    return {r["user_id"]: r for r in fake.client.get("/recipients").json()["recipients"]}


def owner_send(fake, user, text="hi"):
    return fake.client.post("/owner/send", json={"recipient": user, "content": text})


def test_registration_stores_the_pane_id_and_shows_its_position(fake):
    pane = fake.add("work:0.0")
    body = register(fake, "work:0.0")
    assert body["tmux_pane"] == pane and body["pane_label"] == "work:0.0"
    row = recipients(fake)[body["user_id"]]
    assert row["tmux_pane"] == pane and row["pane_label"] == "work:0.0" and row["alive"]


def test_split_pane_renumbering_does_not_misroute(fake):
    first, second = fake.add("work:0.0"), fake.add("work:0.1")
    a = register(fake, "work:0.0")["user_id"]
    b = register(fake, "work:0.1")["user_id"]

    fake.kill(first)  # b is now work:0.0

    assert owner_send(fake, b).status_code == 200
    assert fake.delivered[-1][0] == second
    assert owner_send(fake, a).status_code == 409  # a's pane is gone
    assert recipients(fake)[b]["pane_label"] == "work:0.0"
    # b's CLI still finds b from its new position.
    sender = fake.client.post("/send", json={"tmux_pane": "work:0.0", "recipient": "owner", "content": "me"})
    assert sender.status_code == 200
    assert fake.client.get("/messages", params={"limit": 1}).json()["messages"][0]["sender"] == b


def test_stop_then_spawn_at_the_same_position_keeps_agents_apart(fake):
    old = fake.client.post("/agents/spawn", json={"flavor": "claude"}).json()
    assert fake.client.post(f"/agents/{old['user_id']}/stop").status_code == 200
    new = fake.client.post("/agents/spawn", json={"flavor": "claude"}).json()

    assert new["pane_label"] == old["pane_label"]  # tmux reused the position
    assert new["tmux_pane"] != old["tmux_pane"]
    rows = recipients(fake)
    assert not rows[old["user_id"]]["alive"]  # still listed, offline, history kept
    assert rows[new["user_id"]]["alive"]
    assert owner_send(fake, old["user_id"]).status_code == 409
    assert owner_send(fake, new["user_id"]).status_code == 200
    assert fake.delivered[-1][0] == new["tmux_pane"]


def test_a_new_agent_at_a_reused_position_does_not_inherit_the_old_identity(fake):
    first = fake.add("work:1.0")
    old = register(fake, "work:1.0")["user_id"]
    fake.kill(first)
    fake.add("work:1.0")
    assert register(fake, "work:1.0")["user_id"] != old


def test_tmux_restart_takes_ids_offline_until_the_agent_returns(fake):
    fake.add("other:0.0", "codex")
    fake.add("work:0.0")
    a = register(fake, "work:0.0")["user_id"]  # %1 under srv-1

    fake.restart()  # now other:0.0 is %0 and work:0.0 is %1 again, under srv-2
    row = recipients(fake)[a]
    assert not row["alive"] and "earlier tmux session" in row["offline_reason"]
    assert owner_send(fake, a).status_code == 409
    assert fake.delivered == []

    # The restored harness re-registers from its old position and is itself again.
    assert register(fake, "work:0.0")["user_id"] == a
    assert recipients(fake)[a]["alive"]


def test_an_offline_handle_can_be_reclaimed_by_name(fake):
    first = fake.add("work:0.0")
    a = register(fake, "work:0.0")["user_id"]
    fake.kill(first)
    fake.add("work:5.0")
    body = register(fake, "work:5.0", requested_user=a)
    assert body["user_id"] == a and recipients(fake)[a]["alive"]


def test_a_live_handle_still_cannot_be_taken(fake):
    fake.add("work:0.0")
    fake.add("work:1.0")
    a = register(fake, "work:0.0")["user_id"]
    r = fake.client.post("/register", json={"tmux_pane": "work:1.0", "requested_user": a})
    assert r.status_code == 409
