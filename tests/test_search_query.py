import sqlite3
import time

import pytest

from agent_swarm import search_query as sq

DAY = 86400
T0 = time.mktime(time.strptime("2026-11-05", "%Y-%m-%d"))

MESSAGES = [
    {"id": 1, "sender": "owner", "content": "Please fix the GPU deploy", "ts": T0},
    {"id": 2, "sender": "skink", "content": "Deploy fix landed; the test is flaky", "ts": T0 + DAY},
    {"id": 3, "sender": "skink", "content": "TPU run finished", "ts": T0 + 2 * DAY},
    {"id": 4, "sender": "grebe", "content": "fix deploy order", "ts": T0 + 3 * DAY},
    {"id": 5, "sender": "owner", "content": "100% done_now, see a\\b", "ts": T0 + 4 * DAY},
]


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE messages(id INTEGER, sender TEXT, content TEXT, ts REAL)")
    c.executemany("INSERT INTO messages VALUES(:id,:sender,:content,:ts)", MESSAGES)
    return c


def ids(conn, text):
    where, params = sq.to_sql(sq.parse(text))
    got = [r["id"] for r in conn.execute(f"SELECT id FROM messages WHERE {where} ORDER BY id", params)]
    # The in-memory matcher must agree with SQL.
    q = sq.parse(text)
    assert got == [m["id"] for m in MESSAGES if sq.matches(q, m)], text
    return got


@pytest.mark.parametrize("text,expected", [
    ("", [1, 2, 3, 4, 5]),
    ("deploy fix", [1, 2, 4]),
    ("DEPLOY", [1, 2, 4]),
    ('"fix deploy"', [4]),
    ('"deploy fix"', [2]),
    ("deploy -flaky", [1, 4]),
    ('deploy -"fix deploy"', [1, 2]),
    ("gpu OR tpu", [1, 3]),
    ("finished OR flaky fix", [2]),
    ("fix gpu OR tpu", [1]),
    ("from:skink", [2, 3]),
    ("from:me deploy", [1]),
    ("from:owner", [1, 5]),
    ("from:skink from:grebe fix", [2, 4]),
    ("after:2026-11-07", [3, 4, 5]),
    ("before:2026-11-07", [1, 2]),
    ("after:2026-11-06 before:2026-11-08 ", [2, 3]),
    ("100%", [5]),
    ("done_now", [5]),
    ("a\\b", [5]),
    ("_", [5]),
    ('"unclosed deploy', []),
    ('"unclosed', []),
    ("after:notadate", []),
    ("OR deploy", [1, 2, 4]),
    ("deploy OR", [1, 2, 4]),
    ("-", []),  # a lone dash is literal text
])
def test_queries(conn, text, expected):
    assert ids(conn, text) == expected


def test_unknown_operator_is_plain_text(conn):
    conn.execute("INSERT INTO messages VALUES(6,'owner','see http://x',?)", (T0,))
    q = sq.parse("http://x")
    assert q.clauses == [[sq.Term("http://x")]]
    assert [r["id"] for r in conn.execute(
        "SELECT id FROM messages WHERE " + sq.to_sql(q)[0], sq.to_sql(q)[1])] == [6]


def test_highlight_lists_positive_terms_only():
    q = sq.parse('fix "gpu deploy" OR tpu -flaky from:skink')
    assert q.highlight() == ["fix", "gpu deploy", "tpu"]


def test_lowercase_or_is_a_word(conn):
    assert sq.parse("gpu or tpu").clauses == [[sq.Term("gpu")], [sq.Term("or")], [sq.Term("tpu")]]
