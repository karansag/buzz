"""Persistent team conversations, independent of direct-message delivery."""

import re
import time

import orjson

from . import db

PAGE_BYTES = 16_384
INITIAL_POSTS = 20
MENTION = re.compile(r"(?<![A-Za-z0-9_@.-])@([A-Za-z0-9][A-Za-z0-9-]{0,47})(?![A-Za-z0-9_-])")
POST_FIELDS = "id, team_id, author, subject, body, reply_to, created_at"


class BoardError(Exception):
    def __init__(self, status, error):
        super().__init__(error)
        self.status = status
        self.error = error


def _access(conn, team_id, actor):
    row = conn.execute("SELECT name FROM teams WHERE id=?", (team_id,)).fetchone()
    if row is None:
        if actor == "owner" and conn.execute(
            "SELECT 1 FROM board_posts WHERE team_id=? LIMIT 1", (team_id,)
        ).fetchone():
            return f"Team #{team_id}", True
        raise BoardError(404, "no such board")
    if actor != "owner" and not conn.execute(
        "SELECT 1 FROM recipients WHERE user_id=? AND team_id=?", (actor, team_id)
    ).fetchone():
        raise BoardError(404, "no such board")
    return row["name"], False


def _mentions(row, actor):
    return any(m.group(1).lower() == actor for field in ("subject", "body")
               for m in MENTION.finditer(row[field] or ""))


def _newest(conn, team_id):
    return conn.execute(
        "SELECT COALESCE(MAX(id), 0) FROM board_posts WHERE team_id=?", (team_id,)
    ).fetchone()[0]


def _cursors(conn, team_id, actor, newest):
    row = conn.execute(
        "SELECT last_read_id, last_hinted_id FROM board_reads WHERE user_id=? AND team_id=?",
        (actor, team_id),
    ).fetchone()
    if row is not None:
        return min(row[0], newest), min(row[1], newest)
    row = conn.execute(
        "SELECT id FROM board_posts WHERE team_id=? ORDER BY id DESC LIMIT 1 OFFSET ?",
        (team_id, INITIAL_POSTS),
    ).fetchone()
    baseline = row[0] if row else 0
    return baseline, baseline


def _unread(conn, team_id, actor, read_id):
    return conn.execute(
        "SELECT COUNT(*) FROM board_posts WHERE team_id=? AND id>? AND author<>?",
        (team_id, read_id, actor),
    ).fetchone()[0]


def _root(conn, team_id, reply_to):
    if not conn.execute(
        "SELECT 1 FROM board_posts WHERE team_id=? AND id=? AND reply_to IS NULL",
        (team_id, reply_to),
    ).fetchone():
        raise BoardError(422, "invalid_reply_target")


@db._writes
def post(conn, team_id, actor, *, body, subject, reply_to, client_id):
    _, archived = _access(conn, team_id, actor)
    if archived:
        raise BoardError(409, "board_archived")
    if not body.strip() or len(body.encode("utf-8")) > 16384 or "\0" in body:
        raise BoardError(422, "body must be nonblank and at most 16384 UTF-8 bytes")
    if subject is not None and (reply_to is not None or "\0" in subject):
        raise BoardError(422, "subject is allowed only on roots")
    if client_id is not None:
        row = conn.execute(
            f"SELECT {POST_FIELDS} FROM board_posts WHERE author=? AND client_id=?",
            (actor, client_id),
        ).fetchone()
        if row is not None:
            if (row["team_id"], row["body"], row["subject"], row["reply_to"]) != (
                team_id, body, subject, reply_to
            ):
                raise BoardError(409, "client_id_conflict")
            return _post_ack(row), False
    if reply_to is not None:
        _root(conn, team_id, reply_to)
    created = time.time()
    cursor = conn.execute(
        "INSERT INTO board_posts(team_id,author,subject,body,reply_to,client_id,created_at)"
        " VALUES(?,?,?,?,?,?,?)", (team_id, actor, subject, body, reply_to, client_id, created),
    )
    return {"id": cursor.lastrowid, "team_id": team_id, "author": actor,
            "created_at": created, "reply_to": reply_to}, True


def _post_ack(row):
    return {key: row[key] for key in ("id", "team_id", "author", "created_at", "reply_to")}


def _set_cursors(conn, team_id, actor, read_id, hint_id):
    conn.execute(
        "INSERT INTO board_reads VALUES(?,?,?,?) ON CONFLICT(user_id,team_id) DO UPDATE SET "
        "last_read_id=excluded.last_read_id,last_hinted_id=excluded.last_hinted_id",
        (actor, team_id, read_id, hint_id),
    )


@db._writes
def page(conn, team_id, actor, *, after, before, unread, thread, limit, mark):
    name, archived = _access(conn, team_id, actor)
    newest = _newest(conn, team_id)
    read_id, hint_id = _cursors(conn, team_id, actor, newest)
    terms, args = ["p.team_id=?"], [team_id]
    if thread is not None:
        _root(conn, team_id, thread)
        terms.append("(p.id=? OR p.reply_to=?)")
        args.extend((thread, thread))
    membership = " AND ".join(terms)
    if unread:
        terms.append("p.author<>?")
        args.append(actor)
        after = read_id
    if after is not None:
        terms.append("p.id>?")
        args.append(min(after, newest))
    if before is not None:
        terms.append("p.id<?")
        args.append(before)
    order = "ASC" if after is not None else "DESC"
    rows = conn.execute(
        "SELECT p.*, (SELECT COUNT(*) FROM board_posts r WHERE r.team_id=p.team_id "
        "AND r.reply_to=p.id) AS replies FROM board_posts p WHERE "
        + " AND ".join(terms) + f" ORDER BY p.id {order} LIMIT ?", (*args, limit),
    ).fetchall()

    def exists(op, bound):
        scoped_args = [team_id, thread, thread] if thread is not None else [team_id]
        return conn.execute(
            f"SELECT 1 FROM board_posts p WHERE {membership} AND p.id{op}? LIMIT 1",
            (*scoped_args, bound),
        ).fetchone() is not None

    entries = []
    # Items are encoded once for byte accounting. Reserve enough space for
    # the envelope, including count changes and boolean flags after selection.
    envelope = {"team_id": team_id, "name": name, "archived": archived, "posts": [],
                "has_older": False, "has_newer": False,
                "unread": _unread(conn, team_id, actor, read_id)}
    size = len(orjson.dumps(envelope))
    for row in rows:
        item = {k: row[k] for k in ("id", "author", "subject", "reply_to", "created_at", "replies")}
        item["preview"] = row["subject"] or row["body"][:200]
        item["mentions_me"] = not archived and actor != "owner" and _mentions(row, actor)
        size += len(orjson.dumps(item)) + bool(entries)
        if size > PAGE_BYTES:
            break
        entries.append(item)
    if order == "DESC":
        entries.reverse()
    envelope["posts"] = entries
    if entries:
        first_id, last_id = entries[0]["id"], entries[-1]["id"]
        envelope["has_older"] = exists("<", first_id)
        envelope["has_newer"] = exists(">", last_id)
        if mark:
            read_id = max(read_id, last_id)
            envelope["unread"] = _unread(conn, team_id, actor, read_id)
    elif after is not None:
        envelope["has_older"] = exists("<=", min(after, newest))
    elif before is not None:
        envelope["has_newer"] = exists(">=", before)
    if mark:
        _set_cursors(conn, team_id, actor, read_id, hint_id)
    return envelope


def detail(conn, team_id, actor, post_id):
    _access(conn, team_id, actor)
    row = conn.execute(
        f"SELECT {POST_FIELDS} FROM board_posts WHERE team_id=? AND id=?", (team_id, post_id)
    ).fetchone()
    if row is None:
        raise BoardError(404, "no such board post")
    replies = [] if row["reply_to"] is not None else [dict(reply) for reply in conn.execute(
        f"SELECT {POST_FIELDS} FROM board_posts WHERE team_id=? AND reply_to=? ORDER BY id",
        (team_id, post_id),
    )]
    return {"post": dict(row), "replies": replies}
