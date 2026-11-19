"""Per-thread connections, the write lock, and the indexed conversation queries."""

import gc
import os
import random
import sqlite3
import threading
from pathlib import Path

import pytest

from agent_swarm import db


def test_each_thread_reads_through_its_own_wal_connection(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    seen = []
    t = threading.Thread(target=lambda: seen.append(conn._conn()))
    t.start()
    t.join()
    assert seen[0] is not conn._conn()
    conn.close()


def test_a_read_does_not_wait_for_a_write_in_progress(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    db.record_message(conn, "a", "b", None, "hello", "delivered")
    holding, release = threading.Event(), threading.Event()

    @db._writes
    def slow_write(c):
        c.execute("INSERT INTO messages(sender, recipient, content, ts) VALUES('a', 'b', 'later', 0)")
        holding.set()
        release.wait(10)

    writer = threading.Thread(target=slow_write, args=(conn,))
    writer.start()
    assert holding.wait(10)
    try:
        # The write lock is held and its transaction is open; a reader on
        # another thread still answers, from the last committed state.
        done = []
        reader = threading.Thread(target=lambda: done.append(db.fetch_messages(conn, None, 10)))
        reader.start()
        reader.join(5)
        assert not reader.is_alive()
        assert [m["content"] for m in done[0]] == ["hello"]
    finally:
        release.set()
        writer.join()
    # The outermost write commits what its function left open.
    assert {m["content"] for m in db.fetch_messages(conn, None, 10)} == {"hello", "later"}
    conn.close()


def test_a_failed_write_rolls_back_and_frees_the_database(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")

    @db._writes
    def broken(c):
        c.execute("INSERT INTO messages(sender, recipient, content, ts) VALUES('a', 'b', 'half', 0)")
        raise RuntimeError("midway")

    with pytest.raises(RuntimeError):
        broken(conn)
    assert not conn.in_transaction
    # Another thread can write at once: nothing is left holding SQLite's lock.
    other = db.connect(tmp_path / "t.sqlite")
    errors = []

    def write():
        try:
            db.record_message(other, "c", "d", None, "next", "delivered")
        except sqlite3.Error as e:
            errors.append(e)

    t = threading.Thread(target=write)
    t.start()
    t.join(10)
    assert errors == []
    assert [m["content"] for m in db.fetch_messages(conn, None, 10)] == ["next"]
    conn.close()
    other.close()


def _reference_page(rows, user, limit, before=None, after=None, around=None):
    """The old `sender=? OR recipient=?` queries, in Python."""
    mine = [r for r in rows if user in (r["sender"], r["recipient"])]
    if around is not None:
        half = max(1, limit // 2)
        older = sorted((r for r in mine if r["id"] <= around), key=lambda r: -r["id"])[:half + 1]
        newer = sorted((r for r in mine if r["id"] > around), key=lambda r: r["id"])[:half]
        return [r["id"] for r in [*reversed(older[:half]), *newer]], len(older) > half
    if after is not None:
        picked = sorted((r for r in mine if r["id"] > after), key=lambda r: r["id"])[:limit + 1]
    else:
        picked = sorted((r for r in mine if before is None or r["id"] < before), key=lambda r: -r["id"])[:limit + 1]
    return [r["id"] for r in picked[:limit]], len(picked) > limit


def test_conversation_pages_match_the_or_query(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    rng = random.Random(497)
    users = ["owner", "ann", "bob", "cat"]
    for i in range(400):
        sender = rng.choice(users)
        # Some messages to oneself: both index walks find them, UNION keeps one.
        recipient = sender if i % 37 == 0 else rng.choice([u for u in users if u != sender])
        db.record_message(conn, sender, recipient, None, f"m{i}", "delivered")
    rows = [dict(r) for r in conn.execute("SELECT id, sender, recipient FROM messages")]
    for user in ["ann", "owner", "nobody"]:
        for kwargs in [{}, {"before": 200}, {"before": 3}, {"after": 0}, {"after": 350},
                       {"around": 1}, {"around": 200}, {"around": 400}]:
            for limit in (1, 7, 300):
                page = db.agent_messages_page(conn, user, limit, **kwargs)
                assert ([m["id"] for m in page["messages"]], page["has_more"]) == \
                    _reference_page(rows, user, limit, **kwargs), (user, kwargs, limit)
        for after, before in [(0, 401), (50, 60), (100, 101)]:
            expected = sum(1 for r in rows if user in (r["sender"], r["recipient"]) and after < r["id"] < before)
            assert db.count_agent_messages_between(conn, user, after, before) == expected
    conn.close()


def test_hot_queries_use_their_indexes_even_after_analyze(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    # Many agents, as in a real hub, so one agent's index side is selective.
    for i in range(2000):
        db.record_message(conn, f"agent-{i % 40}", f"agent-{(i * 7 + 1) % 40}", None, str(i), "delivered")
    # ANALYZE leaves the empty pins table without statistics; the planner
    # then scanned every message to join it.
    conn.execute("ANALYZE")

    def plan(sql, params=()):
        return " | ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params))

    assert "idx_messages_ts" in plan("SELECT * FROM messages ORDER BY ts DESC LIMIT 300")
    page = plan(db._CONVERSATION_PAGE.format(op="<", order="DESC"), {"u": "agent-3", "bound": 1500, "n": 5})
    assert "idx_messages_sender_id" in page and "idx_messages_recipient_id" in page
    pins = plan("SELECT m.*, p.pinned_at FROM pins p CROSS JOIN messages m ON m.id = p.message_id")
    assert pins.startswith("SCAN p")
    conn.close()


def test_a_finished_thread_closes_its_connection(tmp_path):
    # The server's worker threads retire when idle; each one's connection
    # must close with it, or the hub runs out of file descriptors.
    path = tmp_path / "t.sqlite"
    conn = db.connect(path)

    def db_fds():
        fd_dir = Path("/proc/self/fd")
        return sum(1 for fd in fd_dir.iterdir() if os.path.realpath(fd).startswith(str(path)))

    def run_threads(n):
        for _ in range(n):
            t = threading.Thread(target=lambda: db.fetch_messages(conn, None, 1))
            t.start()
            t.join()
        gc.collect()

    run_threads(1)
    # SQLite may keep one closed connection's descriptor for reuse while
    # another connection holds locks on the file, so measure growth, not zero.
    after_one = db_fds()
    run_threads(40)
    assert len(conn._opened) == 1  # only the main thread's
    assert db_fds() == after_one
    conn.close()
    assert len(conn._opened) == 0
