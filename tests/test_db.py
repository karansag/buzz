import sqlite3
from concurrent.futures import ThreadPoolExecutor

from agent_swarm import db


def test_shared_connection_concurrent_reads_and_writes(tmp_path):
    conn = db.connect(tmp_path / "concurrent.sqlite")

    def work(i):
        user = f"worker-{i}"
        db.register(conn, user, f"pane-{i}")
        db.rename_recipient(conn, user, f"renamed-{i}")
        db.record_message(conn, user, "owner", None, str(i), "delivered")
        assert db.list_recipients(conn)
        assert db.fetch_messages(conn, "owner", 100)

    try:
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(work, range(100)))
        assert len(db.list_recipients(conn)) == 100
        assert len(db.fetch_messages(conn, "owner", 200)) == 100
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_register_and_lookup(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    db.register(conn, "alice", "0:0.0")
    assert db.lookup_pane(conn, "alice") == "0:0.0"
    db.register(conn, "alice", "0:1.0")  # update
    assert db.lookup_pane(conn, "alice") == "0:1.0"
    assert db.lookup_pane(conn, "bob") is None


def test_record_and_fetch(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    mid = db.record_message(conn, "alice", "bob", "topic", "hi", "delivered")
    assert mid > 0
    rows = db.fetch_messages(conn, "bob")
    assert len(rows) == 1
    assert rows[0]["sender"] == "alice"
    assert rows[0]["delivered"] == 1


def test_list_recipients(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    db.register(conn, "a", "p1")
    db.register(conn, "b", "p2")
    names = [r["user_id"] for r in db.list_recipients(conn)]
    assert names == ["a", "b"]


def test_register_replaces_existing_entry_for_same_pane(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    db.register(conn, "a", "p1", node="hub")
    db.register(conn, "b", "p1", node="hub")
    assert db.lookup_user_by_pane(conn, "hub", "p1") == "b"
    names = [r["user_id"] for r in db.list_recipients(conn)]
    assert names == ["b"]


def test_lookup_user_by_agent_id(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    db.register(conn, "a", "p1", agent_id="agent-1")
    assert db.lookup_user_by_agent_id(conn, "agent-1") == "a"


def test_task_create_and_list(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    t = db.create_task(conn, "fix the build", description="ci is red", assignee="otter")
    assert t["id"] == 1
    assert t["status"] == "open"
    assert t["assignee"] == "otter"
    assert t["worktree"] is None
    t2 = db.create_task(conn, "write docs")
    assert t2["assignee"] is None
    tasks = db.list_tasks(conn)
    assert [x["id"] for x in tasks] == [2, 1]  # newest first


def test_task_update_status_and_assignee(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    t = db.create_task(conn, "fix the build")
    updated = db.update_task(
        conn, t["id"], status="picked_up", assignee="otter",
        worktree="/tmp/repo-task-1",
    )
    assert updated["status"] == "picked_up"
    assert updated["assignee"] == "otter"
    assert updated["worktree"] == "/tmp/repo-task-1"
    assert updated["updated_at"] >= t["updated_at"]
    # updating only status keeps the assignee
    done = db.update_task(conn, t["id"], status="done", note="Run the task verification.")
    assert done["assignee"] == "otter"
    assert done["worktree"] == "/tmp/repo-task-1"
    # explicit None unassigns
    cleared = db.update_task(conn, t["id"], assignee=None)
    assert cleared["assignee"] is None


def test_task_update_rejects_bad_status_and_unknown_id(tmp_path):
    import pytest

    conn = db.connect(tmp_path / "t.sqlite")
    t = db.create_task(conn, "x")
    with pytest.raises(ValueError):
        db.update_task(conn, t["id"], status="bogus")
    assert db.update_task(conn, 999, status="done") is None


def test_connect_adds_worktree_to_existing_tasks_table(tmp_path):
    path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
        "description TEXT, assignee TEXT, status TEXT NOT NULL, "
        "created_at REAL NOT NULL, updated_at REAL NOT NULL)"
    )
    conn.commit()
    conn.close()

    migrated = db.connect(path)
    cols = {row[1] for row in migrated.execute("PRAGMA table_info(tasks)")}
    assert "worktree" in cols


def test_rename_recipient_moves_handle_and_references(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    db.register(conn, "dormouse", "0:0.0", agent_id="a1")
    db.register(conn, "stoat", "0:1.0", agent_id="a2")
    db.record_message(conn, "dormouse", "stoat", None, "out", "delivered")
    db.record_message(conn, "stoat", "dormouse", None, "in", "delivered")
    task_id = db.create_task(conn, "t", assignee="dormouse")["id"]

    db.rename_recipient(conn, "dormouse", "jax")

    assert db.get_recipient(conn, "dormouse") is None
    assert db.get_recipient(conn, "jax")["agent_id"] == "a1"
    senders = {m["sender"] for m in db.fetch_messages(conn)}
    recipients = {m["recipient"] for m in db.fetch_messages(conn)}
    assert "jax" in senders and "dormouse" not in senders
    assert "jax" in recipients and "dormouse" not in recipients
    assert db.get_task(conn, task_id)["assignee"] == "jax"


def test_name_taken_by_other_distinguishes_self_from_peer(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    db.register(conn, "jax", "0:0.0", agent_id="a1", node="hub", tmux_server="srv-1")
    assert db.name_taken_by_other(conn, "jax", "a1", "hub", "0:0.0", "srv-1") is False
    assert db.name_taken_by_other(conn, "jax", "a2", "hub", "0:1.0", "srv-1") is True
    assert db.name_taken_by_other(conn, "unused", "a2", "hub", "0:1.0", "srv-1") is False
    # Same pane id on another machine, or under an earlier tmux, is a
    # different agent.
    db.register(conn, "pip", "0:5.0", node="hub", tmux_server="srv-1")
    assert db.name_taken_by_other(conn, "pip", None, "hub", "0:5.0", "srv-1") is False
    assert db.name_taken_by_other(conn, "pip", None, "laptop", "0:5.0", "srv-1") is True
    assert db.name_taken_by_other(conn, "pip", None, "hub", "0:5.0", "srv-2") is True


def test_rows_written_by_an_older_server_read_their_status_from_the_flag(tmp_path):
    # An older server, still running during an upgrade, writes rows with no
    # status. They must never look pending, or a restart would mark them
    # unknown even though they were delivered.
    conn = db.connect(tmp_path / "t.sqlite")
    ok = db.record_message(conn, "a", "b", None, "sent", "delivered")
    bad = db.record_message(conn, "a", "b", None, "lost", "failed", "pane gone")
    conn.execute("UPDATE messages SET status=NULL")
    conn.commit()
    conn.close()
    conn = db.connect(tmp_path / "t.sqlite")
    assert db.abandon_pending_messages(conn, "restart") == 0
    by_id = {m["id"]: m["status"] for m in db.fetch_messages(conn)}
    assert by_id == {ok: "delivered", bad: "failed"}
    cols = {r[1]: r[4] for r in conn.execute("PRAGMA table_info(messages)")}
    assert cols["status"] is None  # no default, so older writers leave NULL
    db.set_message_status(conn, bad, "unknown", "result lost")
    m = next(m for m in db.fetch_messages(conn) if m["id"] == bad)
    assert (m["status"], m["delivered"], m["delivery_error"]) == ("unknown", 0, "result lost")


def test_owner_reminder_history_survives_database_reopen(tmp_path):
    path = tmp_path / 'reminders.sqlite'
    conn = db.connect(path)
    db.record_message(conn, 'owner', 'otter', None, 'hello', 'delivered')
    conn.execute('UPDATE messages SET ts=1000')
    conn.commit()
    conn.close()
    conn = db.connect(path)
    assert not db.owner_reply_reminder_due(conn, 'otter', since=900, now=1100, idle_seconds=1500)
    assert db.owner_reply_reminder_due(conn, 'otter', since=900, now=2500, idle_seconds=1500)
    conn.close()


def test_reply_migration_legacy_preview_and_missing_original(tmp_path):
    path = tmp_path / 'replies.sqlite'
    conn = db.connect(path)
    original = db.record_message(conn, 'stoat', 'owner', None, 'Original message', 'delivered')
    legacy_text = f'Old answer\n\n(reply to message {original}; `buzz messages --id {original}` shows it)'
    legacy = db.record_message(conn, 'owner', 'stoat', None, legacy_text, 'delivered')
    conn.execute('ALTER TABLE messages DROP COLUMN reply_to')
    conn.commit()
    conn.close()
    conn = db.connect(path)
    old = db.get_message(conn, legacy)
    assert old['reply_to'] == original
    assert old['reply_preview']['content'] == 'Original message'
    assert old['content'] == 'Old answer'
    assert conn.execute('SELECT reply_to FROM messages WHERE id=?', (legacy,)).fetchone()[0] == original
    untouched = db.record_message(conn, 'owner', 'stoat', None, legacy_text, 'delivered')
    reply = db.record_message(conn, 'owner', 'stoat', None, 'New answer', 'delivered', reply_to=original)
    conn.close()
    conn = db.connect(path)
    assert db.get_message(conn, reply)['reply_to'] == original
    assert db.get_message(conn, untouched)['reply_to'] is None
    assert db.get_message(conn, untouched)['content'] == legacy_text
    conn.execute('DELETE FROM messages WHERE id=?', (original,))
    conn.commit()
    retained = db.get_message(conn, reply)
    assert retained['reply_to'] == original
    assert retained['reply_preview'] is None
    conn.close()


def test_task_patch_rolls_back_fields_when_dependency_write_fails(tmp_path):
    import pytest
    conn = db.connect(tmp_path / 'atomic.sqlite')
    parent = db.create_task(conn,'dependency')
    before = db.create_task(conn,'original')
    conn.execute("CREATE TRIGGER reject_edge BEFORE INSERT ON task_deps BEGIN SELECT RAISE(ABORT, 'edge rejected'); END")
    with pytest.raises(sqlite3.IntegrityError, match='edge rejected'):
        db.update_task(conn,before['id'],title='changed',status='done',note='verify',depends_on=[parent['id']])
    assert db.get_task(conn,before['id']) == before
    assert not conn.in_transaction
    conn.close()
