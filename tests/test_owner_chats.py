"""One row per owner conversation, with search, built by the database."""
import random

from agent_swarm import db, search


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


def _reference(conn, query="", agents=None):
    """The window query owner_chats used before it grouped each side on its own."""
    agent = "CASE WHEN sender='owner' THEN recipient ELSE sender END"
    scope = "(sender='owner' OR recipient='owner') AND NOT (sender='owner' AND recipient='owner')"
    args = []
    if agents is not None:
        scope += f" AND {agent} IN ({','.join('?' for _ in agents)})"
        args = list(agents)
    clause, params = search.matches(query) if query.strip() else ("", [])

    def latest(extra, extra_args):
        rows = conn.execute(
            f"SELECT a, id, n FROM (SELECT {agent} AS a, id, ROW_NUMBER() OVER ("
            f"PARTITION BY {agent} ORDER BY ts DESC, id DESC) AS r, COUNT(*) OVER (PARTITION BY {agent}) AS n "
            f"FROM messages WHERE {scope}{extra}) WHERE r=1", (*args, *extra_args)).fetchall()
        return {r["a"]: (r["id"], r["n"]) for r in rows}

    last = latest("", [])
    match = latest(f" AND ({clause})", list(params)) if clause else {}
    return sorted(
        (a, n, i, *(match.get(a) or (None, 0)))
        for a, (i, n) in last.items() if not clause or a in match)


def _summary(chats):
    return sorted((c["agent"], c["count"], c["last"]["id"],
                   c["match"]["id"] if c["match"] else None, c["matches"]) for c in chats)


def test_matches_the_window_query_with_ties_filters_and_search(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    rng = random.Random(541)
    agents = [f"agent-{i}" for i in range(12)]
    words = ["zephyr", "tpu", "merge", "the", "eval", "dashboard"]
    for i in range(3000):
        a = rng.choice(agents)
        sender, recipient = rng.choice([("owner", a), (a, "owner"), (a, rng.choice(agents)), ("owner", "owner")])
        # Coarse timestamps, so many messages in a conversation share one.
        conn.execute(
            "INSERT INTO messages(sender, recipient, content, ts, delivered) VALUES(?,?,?,?,1)",
            (sender, recipient, " ".join(rng.sample(words, 2)), float(rng.randint(0, 400))))
    conn.commit()
    for analyzed in (False, True):
        if analyzed:
            conn.execute("ANALYZE")
        for query in ("", "zephyr", "tpu merge", "-the", "nonesuch"):
            for only in (None, ["agent-1", "agent-5", "ghost"]):
                got = db.owner_chats(conn, query, only)
                assert _summary(got) == _reference(conn, query, only), (query, only, analyzed)
                shown = "match" if query else "last"
                keys = [(c[shown]["ts"], c[shown]["id"]) for c in got]
                assert keys == sorted(keys, reverse=True)


def test_chats_list_reads_only_the_covering_indexes(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    _fill(conn)
    plans = []
    real = conn.execute

    def traced(sql, *a):
        if "GROUP BY" in sql:
            plans.append(" | ".join(r[3] for r in real("EXPLAIN QUERY PLAN " + sql, *a)))
        return real(sql, *a)

    conn.execute = traced
    db.owner_chats(conn)
    assert len(plans) == 2
    assert "COVERING INDEX idx_messages_sender_recipient_ts" in plans[0]
    assert "COVERING INDEX idx_messages_recipient_sender_ts" in plans[1]
