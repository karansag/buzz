"""One row per owner conversation, with search, built by the database."""
import sqlite3

from agent_swarm import db


def _fill(conn):
    rec = lambda s, r, c, ts: conn.execute(
        "INSERT INTO messages(sender, recipient, content, ts, delivered) VALUES(?,?,?,?,1)",
        (s, r, c, ts))
    rec("owner", "otter", "can you check the zephyr reducers?", 10)
    rec("otter", "owner", "yes, skew is small", 20)
    rec("owner", "tapir", "deploy the dashboard", 30)
    rec("tapir", "stoat", "peer chatter", 40)      # not the owner's
    rec("owner", "owner", "note to self", 50)        # not a conversation
    rec("owner", "otter", "zephyr again", 60)
    conn.commit()


def test_one_row_per_agent_newest_first(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    _fill(conn)
    chats = db.owner_chats(conn)
    assert [(c["agent"], c["count"], c["last"]["content"]) for c in chats] == [
        ("otter", 3, "zephyr again"), ("tapir", 1, "deploy the dashboard")]
    assert all(c["match"] is None and c["matches"] == 0 for c in chats)


def test_search_keeps_conversations_with_a_match_and_sorts_by_it(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    _fill(conn)
    chats = db.owner_chats(conn, "Zephyr")
    assert [(c["agent"], c["matches"], c["match"]["content"], c["count"]) for c in chats] == [
        ("otter", 2, "zephyr again", 3)]
    assert db.owner_chats(conn, "zephyr dashboard") == []
    assert db.owner_chats(conn, "nonesuch") == []


def test_agents_filter(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    _fill(conn)
    assert [c["agent"] for c in db.owner_chats(conn, "", ["tapir", "ghost"])] == ["tapir"]
    assert db.owner_chats(conn, "", []) == []
