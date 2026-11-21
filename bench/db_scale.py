"""Measure the hub's message store at today's size and at projected sizes.

Build mock databases by resampling a read-only copy of the real one, then time
the queries the dashboard runs, on five setups:

  sqlite-asis   db.py's functions as they are in this checkout
  sqlite-idx    the same db.py functions, plus WAL and three indexes: no code change
  sqlite-tuned  WAL, indexes, rewritten conversation queries, a trigram FTS
                prefilter for search, one connection per thread
  pg-asis       Postgres 17 with today's one index and the same queries
  pg-tuned      Postgres 17 with the tuned indexes, queries, and pg_trgm search

Usage:
  python bench/db_scale.py build --source COPY --rows N --out MOCK
  python bench/db_scale.py run --db MOCK --setup sqlite-asis [--pg DSN] --out RESULT.json

Postgres needs psycopg (`uv run --with 'psycopg[binary]' ...`).
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sqlite3
import threading
import time
from pathlib import Path

from agent_swarm import db, search, search_query

OTHER_TABLES = ("recipients", "tasks", "task_deps", "teams", "summaries", "meta", "nodes")
QUERIES = ["the", "tpu", "snowball eval", '"model switch"', "zqxjkv", "from:owner merge", "-done error"]
SEARCH_EXPR = "content || ' ' || COALESCE(context, '')"


# ---- build ----------------------------------------------------------------


def build(source: Path, out: Path, rows: int, seed: int) -> None:
    """Resample `source`'s messages to `rows` rows, spread over the same rate."""
    rng = random.Random(seed)
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    real = src.execute(
        "SELECT sender, recipient, context, content, attachments, status, reply_to IS NOT NULL, notify, ts "
        "FROM messages ORDER BY id"
    ).fetchall()
    first, last = real[0][-1], real[-1][-1]
    per_second = len(real) / (last - first)
    out.unlink(missing_ok=True)
    conn = db.connect(out)
    conn.execute("ATTACH ? AS src", (str(source),))
    for table in OTHER_TABLES:
        cols = [r[1] for r in conn.execute(f"PRAGMA src.table_info({table})")]
        keep = [c for c in cols if c in {r[1] for r in conn.execute(f"PRAGMA main.table_info({table})")}]
        names = ", ".join(keep)
        conn.execute(f"DELETE FROM main.{table}")
        conn.execute(f"INSERT INTO main.{table}({names}) SELECT {names} FROM src.{table}")
    conn.commit()
    conn.execute("DETACH src")
    end = time.time()
    start = end - rows / per_second
    step = (end - start) / rows
    batch = []
    for i in range(1, rows + 1):
        sender, recipient, context, content, attachments, status, replied, notify, _ = rng.choice(real)
        reply_to = rng.randint(max(1, i - 200), i - 1) if replied and i > 1 else None
        batch.append((i, sender, recipient, context, content, start + i * step,
                      1 if status in (None, "delivered") else 0, attachments, status, reply_to, notify))
        if len(batch) == 20000:
            _insert(conn, batch)
            batch = []
    _insert(conn, batch)
    conn.commit()
    conn.execute("VACUUM")
    conn.close()


def _insert(conn: sqlite3.Connection, batch: list) -> None:
    conn.executemany(
        "INSERT INTO messages(id, sender, recipient, context, content, ts, delivered, attachments, "
        "status, reply_to, notify) VALUES(?,?,?,?,?,?,?,?,?,?,?)", batch)


# ---- backends -------------------------------------------------------------


class SqliteAsIs:
    """The hub as checked out: db.py's own functions and connection."""

    concurrent_connections = False

    def __init__(self, path: Path):
        self.conn = db.connect(path)

    def state(self):
        db.fetch_messages(self.conn, None, 300)
        db.list_tasks(self.conn)
        db.list_pins(self.conn)
        db.list_teams(self.conn)

    def page(self, user, before=None):
        return db.agent_messages_page(self.conn, user, 300, before=before)["messages"]

    def chats(self, query=""):
        """The Chats list as /api/chats builds it (only the hub's own code has it)."""
        return db.owner_chats(self.conn, query)

    def around(self, user, mid):
        return db.agent_messages_page(self.conn, user, 300, around=mid)["messages"]

    def search(self, user, query):
        return db.search_agent_messages(self.conn, user, query, 100, 0)["total"]

    def write(self, sender, recipient, content):
        db.record_message(self.conn, sender, recipient, None, content, "delivered")

    def worker(self):
        return self

    def owner_chats(self):
        return json.dumps(db.fetch_messages(self.conn, "owner", 100000))

    def agent_talk(self):
        return json.dumps(db.fetch_messages(self.conn, None, 4000))


SQLITE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS bench_messages_sender_id ON messages(sender, id)",
    "CREATE INDEX IF NOT EXISTS bench_messages_recipient_id ON messages(recipient, id)",
    "CREATE INDEX IF NOT EXISTS bench_messages_ts ON messages(ts)",
]


def _prepare_sqlite_idx(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    for sql in SQLITE_INDEXES:
        conn.execute(sql)
    conn.execute("ANALYZE")
    conn.commit()
    conn.close()


class SqliteIdx(SqliteAsIs):
    """db.py's functions unchanged; the file has WAL and the extra indexes."""

    def __init__(self, path: Path):
        _prepare_sqlite_idx(path)
        super().__init__(path)
        self.conn.execute("PRAGMA synchronous=NORMAL")


def _prepare_sqlite_tuned(path: Path) -> None:
    _prepare_sqlite_idx(path)
    conn = sqlite3.connect(path)
    conn.executescript(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            body, content='', contentless_delete=1, tokenize='trigram case_sensitive 0');
        INSERT INTO messages_fts(rowid, body) SELECT id, {SEARCH_EXPR} FROM messages;
        CREATE TRIGGER IF NOT EXISTS messages_fts_ai AFTER INSERT ON messages BEGIN
            INSERT INTO messages_fts(rowid, body) VALUES (new.id, new.content || ' ' || COALESCE(new.context, ''));
        END;
    """)
    conn.commit()
    conn.close()


def _sqlite_conn(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.create_function("casefold", 1, lambda v: (v or "").casefold(), deterministic=True)
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


# Newest page of one conversation: each side walks its own (column, id) index,
# so the cost is the page, not the conversation.
PAGE_SQL = """
SELECT * FROM (
  SELECT * FROM (SELECT * FROM messages WHERE sender=:u AND id < :before ORDER BY id DESC LIMIT :n)
  UNION
  SELECT * FROM (SELECT * FROM messages WHERE recipient=:u AND id < :before ORDER BY id DESC LIMIT :n)
) ORDER BY id DESC LIMIT :n
"""
NEWER_SQL = """
SELECT * FROM (
  SELECT * FROM (SELECT * FROM messages WHERE sender=:u AND id > :after ORDER BY id ASC LIMIT :n)
  UNION
  SELECT * FROM (SELECT * FROM messages WHERE recipient=:u AND id > :after ORDER BY id ASC LIMIT :n)
) ORDER BY id ASC LIMIT :n
"""


class SqliteTuned:
    """Proposed hub: WAL, indexes, rewritten queries, FTS search, a connection per thread."""

    concurrent_connections = True

    def __init__(self, path: Path, prepare: bool = True):
        if prepare:
            _prepare_sqlite_tuned(path)
        self.path = path
        self.conn = _sqlite_conn(path)

    def worker(self):
        return SqliteTuned(self.path, prepare=False)

    def owner_chats(self):
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE sender='owner' UNION SELECT * FROM messages WHERE recipient='owner' "
            "ORDER BY id DESC LIMIT 100000").fetchall()
        return json.dumps(db._messages(self.conn, rows))

    def agent_talk(self):
        rows = self.conn.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 4000").fetchall()
        return json.dumps(db._messages(self.conn, rows))

    def state(self):
        rows = self.conn.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 300").fetchall()
        db._messages(self.conn, rows)
        db.list_tasks(self.conn)
        db.list_pins(self.conn)
        db.list_teams(self.conn)

    def page(self, user, before=None):
        rows = self.conn.execute(PAGE_SQL, {"u": user, "before": before or 2**62, "n": 301}).fetchall()
        return db._messages(self.conn, rows[:300])

    def around(self, user, mid):
        older = self.conn.execute(PAGE_SQL, {"u": user, "before": mid + 1, "n": 151}).fetchall()
        newer = self.conn.execute(NEWER_SQL, {"u": user, "after": mid, "n": 150}).fetchall()
        return db._messages(self.conn, [*reversed(older[:150]), *newer])

    def search(self, user, query):
        clause, params = search.matches(query)
        scope = "((sender='owner' AND recipient=?) OR (sender=? AND recipient='owner'))"
        # A superset of the matches: each all-long OR-group as an FTS group.
        # The exact clause still runs on what the index returns.
        groups = [clause for clause in search_query.parse(query).clauses
                  if all(len(t.text) >= 3 for t in clause)]
        prefilter, fts_args = "", []
        if groups:
            match = " AND ".join(
                "(" + " OR ".join('"' + t.text.replace('"', '""') + '"' for t in clause) + ")"
                for clause in groups)
            prefilter = "id IN (SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?) AND "
            fts_args = [match]
        where = f"{prefilter}{scope} AND ({clause})"
        args = [*fts_args, user, user, *params]
        total = self.conn.execute(f"SELECT COUNT(*) FROM messages WHERE {where}", args).fetchone()[0]
        self.conn.execute(
            f"SELECT id, ts, sender, content FROM messages WHERE {where} ORDER BY id DESC LIMIT 100",
            args).fetchall()
        return total

    def write(self, sender, recipient, content):
        with self.conn:
            self.conn.execute(
                "INSERT INTO messages(sender, recipient, context, content, ts, delivered, status) "
                "VALUES(?,?,?,?,?,1,'delivered')", (sender, recipient, None, content, time.time()))


# ---- Postgres --------------------------------------------------------------


PG_SCHEMA = """
DROP TABLE IF EXISTS messages, pins, tasks, task_deps, teams, team_members CASCADE;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE TABLE messages (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  sender TEXT NOT NULL, recipient TEXT NOT NULL, context TEXT, content TEXT NOT NULL,
  ts DOUBLE PRECISION NOT NULL, delivered INTEGER NOT NULL DEFAULT 0, delivery_error TEXT,
  attachments TEXT, status TEXT, client_id TEXT, reply_to BIGINT, notify INTEGER NOT NULL DEFAULT 0);
CREATE INDEX messages_recipient_ts ON messages(recipient, ts DESC);
CREATE TABLE pins (message_id BIGINT PRIMARY KEY, pinned_at DOUBLE PRECISION NOT NULL);
CREATE TABLE tasks (id BIGINT PRIMARY KEY, doc JSONB NOT NULL);
CREATE TABLE task_deps (task_id BIGINT, depends_on BIGINT);
CREATE TABLE teams (id BIGINT PRIMARY KEY, doc JSONB NOT NULL, position INTEGER);
"""
PG_TUNED = f"""
CREATE INDEX IF NOT EXISTS messages_sender_id ON messages(sender, id);
CREATE INDEX IF NOT EXISTS messages_recipient_id ON messages(recipient, id);
CREATE INDEX IF NOT EXISTS messages_ts ON messages(ts);
CREATE INDEX IF NOT EXISTS messages_search ON messages USING gin (lower({SEARCH_EXPR}) gin_trgm_ops);
"""
COLS = ["id", "sender", "recipient", "context", "content", "ts", "delivered", "delivery_error",
        "attachments", "status", "client_id", "reply_to", "notify"]


def load_pg(dsn: str, mock: Path, tuned: bool) -> None:
    import psycopg

    src = sqlite3.connect(f"file:{mock}?mode=ro", uri=True)
    with psycopg.connect(dsn, autocommit=True) as pg:
        pg.execute(PG_SCHEMA)
        with pg.cursor().copy(f"COPY messages ({', '.join(COLS)}) FROM STDIN") as copy:
            for row in src.execute(f"SELECT {', '.join(COLS)} FROM messages"):
                copy.write_row(row)
        pg.execute("SELECT setval(pg_get_serial_sequence('messages','id'), (SELECT max(id) FROM messages))")
        src.row_factory = sqlite3.Row
        for row in src.execute("SELECT * FROM tasks"):
            pg.execute("INSERT INTO tasks VALUES (%s, %s)", (row["id"], json.dumps(dict(row))))
        for row in src.execute("SELECT task_id, depends_on FROM task_deps"):
            pg.execute("INSERT INTO task_deps VALUES (%s, %s)", tuple(row))
        for row in src.execute("SELECT * FROM teams"):
            pg.execute("INSERT INTO teams VALUES (%s, %s, %s)",
                       (row["id"], json.dumps(dict(row)), dict(row).get("position")))
        if tuned:
            pg.execute(PG_TUNED)
        pg.execute("VACUUM ANALYZE")


def _pg_messages(pg, rows: list[dict]) -> list[dict]:
    """The same post-processing as db._messages: attachments and reply previews."""
    for row in rows:
        row["attachments"] = json.loads(row["attachments"]) if row["attachments"] else []
    ids = list({r["reply_to"] for r in rows if r["reply_to"] is not None})
    originals = {}
    if ids:
        originals = {r["id"]: r for r in pg.execute(
            "SELECT id, sender, content FROM messages WHERE id = ANY(%s)", (ids,)).fetchall()}
    for row in rows:
        parent = originals.get(row["reply_to"])
        row["reply_preview"] = ({"id": parent["id"], "sender": parent["sender"],
                                 "content": " ".join(parent["content"].split())[:100]} if parent else None)
    return rows


def _like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class Pg:
    """Postgres with the as-is queries (tuned=False) or the tuned ones."""

    concurrent_connections = True

    def __init__(self, dsn: str, tuned: bool):
        import psycopg
        from psycopg.rows import dict_row

        self.dsn, self.tuned = dsn, tuned
        self.conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)

    def worker(self):
        return Pg(self.dsn, self.tuned)

    def owner_chats(self):
        if self.tuned:
            sql = ("SELECT * FROM messages WHERE sender='owner' UNION SELECT * FROM messages "
                   "WHERE recipient='owner' ORDER BY id DESC LIMIT 100000")
        else:
            sql = "SELECT * FROM messages WHERE recipient='owner' OR sender='owner' ORDER BY ts DESC LIMIT 100000"
        return json.dumps(_pg_messages(self.conn, self.conn.execute(sql).fetchall()))

    def agent_talk(self):
        order = "id" if self.tuned else "ts"
        rows = self.conn.execute(f"SELECT * FROM messages ORDER BY {order} DESC LIMIT 4000").fetchall()
        return json.dumps(_pg_messages(self.conn, rows))

    def state(self):
        order = "id" if self.tuned else "ts"
        rows = self.conn.execute(f"SELECT * FROM messages ORDER BY {order} DESC LIMIT 300").fetchall()
        _pg_messages(self.conn, rows)
        self.conn.execute("SELECT task_id, depends_on FROM task_deps ORDER BY depends_on").fetchall()
        self.conn.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
        _pg_messages(self.conn, self.conn.execute(
            "SELECT m.*, p.pinned_at FROM pins p JOIN messages m ON m.id = p.message_id "
            "ORDER BY p.pinned_at DESC").fetchall())
        self.conn.execute("SELECT * FROM teams ORDER BY position, id").fetchall()

    def page(self, user, before=None):
        if self.tuned:
            sql = PAGE_SQL.replace(":u", "%(u)s").replace(":before", "%(before)s").replace(":n", "%(n)s")
            rows = self.conn.execute(sql, {"u": user, "before": before or 2**62, "n": 301}).fetchall()
        else:
            extra = "AND id < %(before)s" if before else ""
            rows = self.conn.execute(
                f"SELECT * FROM messages WHERE (sender=%(u)s OR recipient=%(u)s) {extra} "
                "ORDER BY id DESC LIMIT 301", {"u": user, "before": before}).fetchall()
        return _pg_messages(self.conn, rows[:300])

    def around(self, user, mid):
        if self.tuned:
            q = lambda s: s.replace(":u", "%(u)s").replace(":before", "%(before)s").replace(
                ":after", "%(after)s").replace(":n", "%(n)s")
            older = self.conn.execute(q(PAGE_SQL), {"u": user, "before": mid + 1, "n": 151}).fetchall()
            newer = self.conn.execute(q(NEWER_SQL), {"u": user, "after": mid, "n": 150}).fetchall()
        else:
            older = self.conn.execute(
                "SELECT * FROM messages WHERE (sender=%(u)s OR recipient=%(u)s) AND id <= %(m)s "
                "ORDER BY id DESC LIMIT 151", {"u": user, "m": mid}).fetchall()
            newer = self.conn.execute(
                "SELECT * FROM messages WHERE (sender=%(u)s OR recipient=%(u)s) AND id > %(m)s "
                "ORDER BY id ASC LIMIT 150", {"u": user, "m": mid}).fetchall()
        return _pg_messages(self.conn, [*reversed(older[:150]), *newer])

    def search(self, user, query):
        parsed = search_query.parse(query)
        conds, args = ["((sender='owner' AND recipient=%s) OR (sender=%s AND recipient='owner'))"], [user, user]
        body = f"lower({SEARCH_EXPR})"
        for clause in parsed.clauses:
            conds.append("(" + " OR ".join(f"{body} LIKE %s" for _ in clause) + ")")
            args += [_like(t.text.lower()) for t in clause]
        for term in parsed.excluded:
            conds.append(f"{body} NOT LIKE %s")
            args.append(_like(term.text.lower()))
        if parsed.senders:
            conds.append("sender = ANY(%s)")
            args.append(parsed.senders)
        where = " AND ".join(conds)
        total = self.conn.execute(f"SELECT COUNT(*) AS n FROM messages WHERE {where}", args).fetchone()["n"]
        self.conn.execute(f"SELECT id, ts, sender, content FROM messages WHERE {where} "
                          "ORDER BY id DESC LIMIT 100", args).fetchall()
        return total

    def write(self, sender, recipient, content):
        self.conn.execute(
            "INSERT INTO messages(sender, recipient, content, ts, delivered, status) "
            "VALUES(%s,%s,%s,%s,1,'delivered')", (sender, recipient, content, time.time()))


# ---- workloads -------------------------------------------------------------


def _ms(fn, *args) -> float:
    t = time.perf_counter()
    fn(*args)
    return (time.perf_counter() - t) * 1000


def _summary(samples: list[float]) -> dict:
    s = sorted(samples)
    pick = lambda q: s[min(len(s) - 1, int(q * len(s)))]
    return {"n": len(s), "p50": round(pick(0.5), 2), "p95": round(pick(0.95), 2), "max": round(s[-1], 2)}


def pick_users(mock: Path) -> dict:
    conn = sqlite3.connect(f"file:{mock}?mode=ro", uri=True)
    counts = conn.execute(
        "SELECT u, COUNT(*) n FROM (SELECT sender u FROM messages UNION ALL SELECT recipient FROM messages) "
        "WHERE u <> 'owner' GROUP BY u ORDER BY n DESC").fetchall()
    owner = conn.execute(
        "SELECT CASE WHEN sender='owner' THEN recipient ELSE sender END u, COUNT(*) n FROM messages "
        "WHERE (sender='owner') <> (recipient='owner') GROUP BY u ORDER BY n DESC LIMIT 6").fetchall()
    big = [u for u, _ in counts[:4]]
    mid = [u for u, _ in counts[len(counts) // 3: len(counts) // 3 + 4]]
    users = big + mid
    old = {}
    for u in users:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM messages WHERE sender=? OR recipient=? ORDER BY id", (u, u))]
        old[u] = ids[len(ids) // 10] if ids else 1
    return {"users": users, "sizes": dict(counts[:4] + counts[len(counts) // 3: len(counts) // 3 + 4]),
            "owner_users": [u for u, _ in owner], "owner_sizes": dict(owner), "old_id": old}


def run(backend, plan: dict, reps: int) -> dict:
    users, out = plan["users"], {}
    for _ in range(3):
        backend.state()
    out["state"] = _summary([_ms(backend.state) for _ in range(reps)])
    out["owner_chats_all"] = _summary([_ms(backend.owner_chats) for _ in range(max(3, reps // 8))])
    if hasattr(backend, "chats"):
        out["chats_list"] = _summary([_ms(backend.chats) for _ in range(reps)])
        out["chats_search tpu"] = _summary([_ms(backend.chats, "tpu") for _ in range(max(3, reps // 4))])
    out["agent_talk_4000"] = _summary([_ms(backend.agent_talk) for _ in range(max(3, reps // 8))])
    out["history_open"] = _summary([_ms(backend.page, u) for _ in range(max(1, reps // 4)) for u in users])

    def scroll(u):
        before = None
        for _ in range(5):
            page = backend.page(u, before)
            if len(page) < 300:
                return
            before = min(m["id"] for m in page)

    out["history_scroll_5_pages"] = _summary([_ms(scroll, u) for _ in range(max(1, reps // 8)) for u in users])
    out["jump_to_old"] = _summary(
        [_ms(backend.around, u, plan["old_id"][u]) for _ in range(max(1, reps // 4)) for u in users])
    for q in QUERIES:
        out[f"search {q}"] = _summary(
            [_ms(backend.search, u, q) for _ in range(max(1, reps // 8)) for u in plan["owner_users"]])
    body = "benchmark write " * 40
    out["write"] = _summary([_ms(backend.write, "bench-a", "bench-b", body) for _ in range(reps)])
    out["mixed"] = mixed(backend, plan)
    return out


def answers(backend, plan: dict) -> dict:
    """What each setup returns, so the setups can be checked against each other."""
    got = {}
    for u in plan["users"]:
        got[f"page {u}"] = [m["id"] for m in backend.page(u)]
        got[f"around {u}"] = [m["id"] for m in backend.around(u, plan["old_id"][u])]
    for u in plan["owner_users"]:
        for q in QUERIES:
            got[f"search {u} {q}"] = backend.search(u, q)
    got["owner_chats"] = len(json.loads(backend.owner_chats()))
    if hasattr(backend, "chats"):
        for q in ("", *QUERIES):
            got[f"chats {q}"] = json.loads(json.dumps(backend.chats(q), default=str))
    return got


def mixed(backend, plan: dict, seconds: float = 15.0, readers: int = 4, writes_per_s: float = 20.0) -> dict:
    """Readers poll state, open conversations and search while one writer sends."""
    stop = time.monotonic() + seconds
    reads, writes, errors = [], [], []
    lock = threading.Lock()

    def reader(i):
        me = backend.worker() if backend.concurrent_connections else backend
        rng = random.Random(i)
        while time.monotonic() < stop:
            kind = rng.random()
            try:
                if kind < 0.5:
                    t = _ms(me.state)
                elif kind < 0.85:
                    t = _ms(me.page, rng.choice(plan["users"]))
                else:
                    t = _ms(me.search, rng.choice(plan["owner_users"]), rng.choice(QUERIES[:4]))
            except Exception as e:  # noqa: BLE001 - recorded, the run goes on
                errors.append(repr(e))
                continue
            with lock:
                reads.append(t)

    def writer():
        me = backend.worker() if backend.concurrent_connections else backend
        nxt = time.monotonic()
        while time.monotonic() < stop:
            try:
                writes.append(_ms(me.write, "bench-a", "bench-b", "mixed load write " * 40))
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))
            nxt += 1 / writes_per_s
            time.sleep(max(0, nxt - time.monotonic()))

    threads = [threading.Thread(target=reader, args=(i,)) for i in range(readers)]
    threads.append(threading.Thread(target=writer))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return {"reads": _summary(reads), "writes": _summary(writes), "errors": errors[:5],
            "error_count": len(errors), "reads_per_s": round(len(reads) / seconds, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--source", type=Path, required=True)
    b.add_argument("--rows", type=int, required=True)
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--seed", type=int, default=483)
    r = sub.add_parser("run")
    r.add_argument("--db", type=Path, required=True)
    r.add_argument("--setup", required=True,
                   choices=["sqlite-asis", "sqlite-idx", "sqlite-tuned", "pg-asis", "pg-tuned"])
    r.add_argument("--pg")
    r.add_argument("--reps", type=int, default=40)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--work-dir", type=Path, help="where the timed SQLite copy lives (put it on the live DB's disk)")
    args = ap.parse_args()
    if args.cmd == "build":
        build(args.source, args.out, args.rows, args.seed)
        return
    plan = pick_users(args.db)
    work = (args.work_dir or args.out.parent) / (args.out.stem + ".sqlite")
    started = time.perf_counter()
    if args.setup.startswith("sqlite"):
        shutil.copyfile(args.db, work)
        backend = {"sqlite-asis": SqliteAsIs, "sqlite-idx": SqliteIdx, "sqlite-tuned": SqliteTuned}[args.setup](work)
    else:
        load_pg(args.pg, args.db, tuned=args.setup == "pg-tuned")
        backend = Pg(args.pg, tuned=args.setup == "pg-tuned")
    prepared = time.perf_counter() - started
    result = {"setup": args.setup, "db": str(args.db), "plan": plan, "prepare_s": round(prepared, 1),
              "answers": answers(backend, plan), "results": run(backend, plan, args.reps)}
    args.out.write_text(json.dumps(result, indent=1))
    work.unlink(missing_ok=True)
    for suffix in ("-wal", "-shm"):
        Path(str(work) + suffix).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
