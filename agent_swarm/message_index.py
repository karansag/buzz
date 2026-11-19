"""A trigram index over message text, used to narrow a search before the scan.

Search matches casefolded substrings (search_query). A trigram index holds
every 3-character run of each message, so a term of 3+ characters can only
match messages the index returns for it. The index is a prefilter: the exact
search clause still runs on what it returns, so results are the scan's results.

Text goes in casefolded, as the search compares it. Ids are the messages' ids.
Messages added or removed outside add()/remove_before() make the index stale;
usable() notices when the newest message is not indexed and the search then
scans as before.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import search_query

TABLE = "messages_fts"
VOCAB = "messages_fts_vocab"

# The prefilter is skipped when the rarest trigram of a search term is in more
# than this share of the messages: reading that many candidates through the
# index costs about what scanning does (measured on 48k messages: "the", in 70%,
# was even; "task", in 33%, was 2x faster; "agent", in 20%, 3x).
MAX_SHARE = 0.3
BATCH = 2000


def _text(content: str | None, context: str | None) -> str:
    return f"{content or ''} {context or ''}".casefold()


def ensure(conn, path: Path | None = None) -> None:
    """Create the index if missing and index messages it does not have yet.

    Before the first build the database is copied to `<name>.pre-fts` next to
    it, so a bad migration can be undone. Without FTS5 trigram support
    (SQLite 3.43 or newer) there is no index and every search scans.
    """
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (TABLE,)).fetchone()
    if not exists:
        if path is not None and conn.execute("SELECT 1 FROM messages LIMIT 1").fetchone():
            _backup(conn, path)
        try:
            conn.execute(
                f"CREATE VIRTUAL TABLE {TABLE} USING fts5(body, content='', "
                "contentless_delete=1, tokenize='trigram case_sensitive 0')")
            conn.execute(f"CREATE VIRTUAL TABLE {VOCAB} USING fts5vocab({TABLE}, 'row')")
        except sqlite3.OperationalError:
            return
    last = conn.execute(f"SELECT COALESCE(MAX(rowid), 0) FROM {TABLE}").fetchone()[0]
    while True:
        rows = conn.execute(
            "SELECT id, content, context FROM messages WHERE id > ? ORDER BY id LIMIT ?",
            (last, BATCH)).fetchall()
        if not rows:
            break
        conn.executemany(
            f"INSERT INTO {TABLE}(rowid, body) VALUES(?, ?)",
            [(r["id"], _text(r["content"], r["context"])) for r in rows])
        last = rows[-1]["id"]
    conn.commit()


def _backup(conn, path: Path) -> None:
    target = Path(f"{path}.pre-fts")
    if target.exists():
        return
    dest = sqlite3.connect(str(target))
    try:
        conn.backup(dest)
    finally:
        dest.close()


def _have(conn) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (TABLE,)).fetchone() is not None


def add(conn, message_id: int, content: str, context: str | None) -> None:
    if _have(conn):
        conn.execute(f"INSERT OR REPLACE INTO {TABLE}(rowid, body) VALUES(?, ?)",
                     (message_id, _text(content, context)))


def remove_before(conn, cutoff: float) -> None:
    """Drop index rows of the messages delete_messages_before is about to delete."""
    if _have(conn):
        conn.execute(
            f"DELETE FROM {TABLE} WHERE rowid IN (SELECT id FROM messages "
            "WHERE ts < ? AND id NOT IN (SELECT message_id FROM pins))", (cutoff,))


def _usable(conn) -> bool:
    if not _have(conn):
        return False
    newest = conn.execute("SELECT MAX(id) FROM messages").fetchone()[0]
    indexed = conn.execute(f"SELECT MAX(rowid) FROM {TABLE}").fetchone()[0]
    return newest is None or newest == indexed


def _quote(text: str) -> str:
    return '"' + text.replace('"', '""') + '"'


def _trigrams(text: str, limit: int = 16) -> list[str]:
    grams = [text[i:i + 3] for i in range(len(text) - 2)]
    if len(grams) > limit:
        step = len(grams) / limit
        grams = [grams[int(i * step)] for i in range(limit)]
    return grams


def _docs(conn, trigram: str) -> int:
    row = conn.execute(f"SELECT doc FROM {VOCAB} WHERE term=?", (trigram,)).fetchone()
    return row[0] if row else 0


def prefilter(conn, query: str) -> tuple[str, list]:
    """A WHERE fragment ending in AND, with its parameters; ("", []) to scan.

    Every AND-clause whose terms are all 3+ characters must match, so the index
    is asked for them (an OR-group becomes an FTS OR). Excluded terms, short
    terms, senders and dates are left to the exact clause.
    """
    q = search_query.parse(query)
    groups = [c for c in q.clauses if all(len(t.text) >= 3 for t in c)]
    if not groups or not _usable(conn):
        return "", []
    total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    # Candidates a group can have: at most the rarest trigram's document count
    # per term, summed over its OR-ed terms. The smallest group bounds the result.
    estimate = min(
        sum(min(_docs(conn, g) for g in _trigrams(t.text)) for t in clause)
        for clause in groups)
    if estimate > total * MAX_SHARE:
        return "", []
    match = " AND ".join(
        "(" + " OR ".join(_quote(t.text) for t in clause) + ")" for clause in groups)
    return f"id IN (SELECT rowid FROM {TABLE} WHERE {TABLE} MATCH ?) AND ", [match]
