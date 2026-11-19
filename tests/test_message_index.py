"""The trigram prefilter must never change what a search returns."""
import sqlite3

import pytest

from agent_swarm import db, message_index

TEXTS = [
    ("owner", "otter", None, "Please deploy the Straße fix"),
    ("otter", "owner", "deploy", "STRASSE deployed, tests green"),
    ("owner", "otter", None, "gpu or tpu for the weights job?"),
    ("otter", "owner", None, "tpu please; do not use the GPU"),
    ("owner", "otter", "flaky", "a flaky test again"),
    ("otter", "owner", None, "ok"),
    ("owner", "tapir", None, "deploy to tapir"),
    ("otter", "tapir", None, "peer deploy chatter"),
    ("owner", "otter", None, 'say "not available" when empty'),
]
QUERIES = ["deploy", "STRASSE", "straße", "Straße", "deploy -tests", "gpu OR tpu", "tpu -gpu",
           '"not available"', '"do not use"', "from:otter deploy", "from:me deploy",
           "ok", "an", "de", "flaky deploy", "the", "-the", "zzzz", "dep loy", "50%_"]


def _db(tmp_path, n_filler=0):
    conn = db.connect(tmp_path / "idx.db")
    for sender, recipient, context, content in TEXTS:
        db.record_message(conn, sender, recipient, context, content, "delivered")
    for i in range(n_filler):
        db.record_message(conn, "owner", "otter", None, f"filler {i} {'x' * (i % 7)}", "delivered")
    return conn


def _scan(conn, user, query, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(message_index, "prefilter", lambda c, q: ("", []))
        return db.search_agent_messages(conn, user, query, 100, 0)


@pytest.mark.parametrize("query", QUERIES)
def test_indexed_search_matches_the_scan(tmp_path, monkeypatch, query):
    conn = _db(tmp_path, n_filler=400)
    for user in ("otter", "tapir"):
        assert db.search_agent_messages(conn, user, query, 100, 0) == _scan(conn, user, query, monkeypatch)


def test_rare_terms_use_the_index_and_common_ones_scan(tmp_path):
    conn = _db(tmp_path, n_filler=400)
    assert message_index.prefilter(conn, "straße")[0]
    assert not message_index.prefilter(conn, "filler")[0]       # in nearly every message
    assert not message_index.prefilter(conn, "an")[0]
    assert not message_index.prefilter(conn, "-straße")[0]       # exclusions cannot narrow


def test_casefold_expansion_is_found(tmp_path):
    conn = _db(tmp_path, n_filler=400)
    hits = db.search_agent_messages(conn, "otter", "strasse")["matches"]
    assert len(hits) == 2          # "Straße" and "STRASSE" both casefold to "strasse"


def test_unindexed_message_falls_back_to_scan(tmp_path):
    conn = _db(tmp_path, n_filler=400)
    # A message written by something that does not know the index.
    conn.execute("INSERT INTO messages(sender, recipient, content, ts, delivered, status) "
                 "VALUES('owner','otter','sneaky rareword',1,1,'delivered')")
    conn.commit()
    assert not message_index.prefilter(conn, "rareword")[0]
    assert db.search_agent_messages(conn, "otter", "rareword")["total"] == 1


def test_pruned_messages_leave_the_index(tmp_path):
    conn = _db(tmp_path, n_filler=10)
    pinned = db.record_message(conn, "owner", "otter", None, "pinned needle", "delivered")
    db.set_pinned(conn, pinned, True)
    db.record_message(conn, "owner", "otter", None, "doomed needle", "delivered")
    import time
    assert db.delete_messages_before(conn, time.time() + 60) > 0
    assert [m["id"] for m in db.search_agent_messages(conn, "otter", "needle")["matches"]] == [pinned]
    assert conn.execute(f"SELECT COUNT(*) FROM {message_index.TABLE}").fetchone()[0] == 1


def test_notifications_are_indexed(tmp_path):
    conn = _db(tmp_path, n_filler=300)
    db.record_notification(conn, "otter", "build finished quietly", "ctx")
    assert message_index.prefilter(conn, "quietly")[0]
    assert db.search_agent_messages(conn, "otter", "quietly")["total"] == 1


def test_existing_database_is_backed_up_then_indexed(tmp_path):
    path = tmp_path / "old.db"
    conn = db.connect(path)
    for i in range(30):
        db.record_message(conn, "owner", "otter", None, f"message {i} marker", "delivered")
    conn.execute(f"DROP TABLE {message_index.VOCAB}")
    conn.execute(f"DROP TABLE {message_index.TABLE}")
    conn.commit()
    conn.close()
    (tmp_path / "old.db.pre-fts").unlink(missing_ok=True)
    conn = db.connect(path)
    backup = sqlite3.connect(tmp_path / "old.db.pre-fts")
    assert backup.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 30
    assert backup.execute("SELECT 1 FROM sqlite_master WHERE name=?", (message_index.TABLE,)).fetchone() is None
    assert conn.execute(f"SELECT COUNT(*) FROM {message_index.TABLE}").fetchone()[0] == 30
    assert db.search_agent_messages(conn, "otter", "message 7")["total"] == 3
