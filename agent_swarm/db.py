"""SQLite layer. Pure functions over a connection."""

from __future__ import annotations

from functools import wraps
import json
import math
import re
import sqlite3
import threading
import time
from pathlib import Path

from . import names, notifications, search

SCHEMA = """
CREATE TABLE IF NOT EXISTS recipients (
    user_id     TEXT PRIMARY KEY,
    tmux_pane   TEXT NOT NULL,
    agent_id    TEXT,
    model       TEXT,
    flavor      TEXT,
    instructions TEXT,
    message_prefix TEXT,
    submit_key  TEXT,
    registered_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sender      TEXT NOT NULL,
    recipient   TEXT NOT NULL,
    context     TEXT,
    content     TEXT NOT NULL,
    ts          REAL NOT NULL,
    delivered   INTEGER NOT NULL DEFAULT 0,
    delivery_error TEXT,
    status      TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_recipient_ts
    ON messages(recipient, ts DESC);

CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT,
    assignee    TEXT,
    status      TEXT NOT NULL DEFAULT 'open',
    worktree    TEXT,
    worktree_node TEXT,
    note        TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    queen       TEXT,
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    name        TEXT PRIMARY KEY,
    token_hash  TEXT,
    created_at  REAL NOT NULL,
    last_seen   REAL,
    version     TEXT,
    tmux_server TEXT,
    harnesses   TEXT
);

-- Bundles already taken in, so importing the same export twice does not
-- duplicate its tasks and history.
CREATE TABLE IF NOT EXISTS imports (
    source_id   TEXT PRIMARY KEY,
    node        TEXT NOT NULL,
    imported_at REAL NOT NULL,
    report      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_deps (
    task_id     INTEGER NOT NULL,
    depends_on  INTEGER NOT NULL,
    PRIMARY KEY (task_id, depends_on)
);

-- What each agent says it is doing ("source" agent), or what its harness
-- wrote into the tmux pane title ("title"). Newest row is the current one.
CREATE TABLE IF NOT EXISTS summaries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    text        TEXT NOT NULL,
    source      TEXT NOT NULL,
    ts          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_summaries_user_ts ON summaries(user_id, ts);
"""

SUMMARY_SOURCES = ("agent", "title", "owner")
# Older summaries past this many per agent are dropped as new ones arrive.
SUMMARY_HISTORY = 20

TASK_STATUSES = ("open", "picked_up", "done")

_UNSET = object()


# The server shares a connection between FastAPI worker threads and the
# activity monitor. SQLite multi-thread builds require callers to serialize
# access to a connection, including cursor iteration and whole transactions.
# Reentrancy allows database helpers to call one another under the same lock.
_connection_lock = threading.RLock()


def _serialized(func):
    @wraps(func)
    def locked(*args, **kwargs):
        with _connection_lock:
            return func(*args, **kwargs)
    return locked


@_serialized
def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.create_function("casefold", 1, lambda value: (value or "").casefold(), deterministic=True)
    conn.executescript(SCHEMA)
    _ensure_columns(conn)
    return conn


@_serialized
def register(
    conn: sqlite3.Connection,
    user_id: str,
    tmux_pane: str,
    agent_id: str | None = None,
    model: str | None = None,
    flavor: str | None = None,
    instructions: str | None = None,
    message_prefix: str | None = None,
    submit_key: str | None = None,
    tmux_server: str | None = None,
    pane_label: str | None = None,
    node: str | None = None,
) -> None:
    _ensure_columns(conn)
    # One agent per pane. A row holding the same id under an earlier tmux
    # server is a different pane, so it stays (offline) with its history.
    conn.execute(
        "DELETE FROM recipients WHERE node IS ? AND tmux_pane=? AND tmux_server IS ? AND user_id<>?",
        (node, tmux_pane, tmux_server, user_id),
    )
    if agent_id:
        conn.execute(
            "DELETE FROM recipients WHERE agent_id=? AND user_id<>?",
            (agent_id, user_id),
        )
    conn.execute(
        "INSERT INTO recipients("
        "user_id, tmux_pane, agent_id, model, flavor, instructions, message_prefix, submit_key, registered_at, "
        "tmux_server, pane_label, node"
        ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "tmux_pane=excluded.tmux_pane, "
        "tmux_server=excluded.tmux_server, "
        "pane_label=excluded.pane_label, "
        "node=COALESCE(excluded.node, recipients.node), "
        "agent_id=COALESCE(excluded.agent_id, recipients.agent_id), "
        "model=COALESCE(excluded.model, recipients.model), "
        "flavor=COALESCE(excluded.flavor, recipients.flavor), "
        "instructions=COALESCE(excluded.instructions, recipients.instructions), "
        "message_prefix=COALESCE(excluded.message_prefix, recipients.message_prefix), "
        "submit_key=COALESCE(excluded.submit_key, recipients.submit_key), "
        "registered_at=excluded.registered_at",
        (
            user_id,
            tmux_pane,
            agent_id,
            model,
            flavor,
            instructions,
            message_prefix,
            submit_key,
            time.time(),
            tmux_server,
            pane_label,
            node,
        ),
    )
    conn.commit()


@_serialized
def fill_missing_node(conn: sqlite3.Connection, node: str) -> int:
    """Stamp `node` on rows registered before nodes were recorded.

    Every such row was registered against this server's own tmux, so it
    belongs to this machine. Returns the number of rows updated.
    """
    _ensure_columns(conn)
    cur = conn.execute("UPDATE recipients SET node=? WHERE node IS NULL", (node,))
    conn.commit()
    return cur.rowcount


@_serialized
def name_taken_by_other(
    conn: sqlite3.Connection,
    user_id: str,
    agent_id: str | None,
    node: str,
    tmux_pane: str,
    tmux_server: str | None,
) -> bool:
    """True when `user_id` belongs to an agent other than this one.

    Identity is the agent_id when we have one, else the pane on its node
    under the tmux server that issued it, matching how `register` resolves
    an existing handle.
    """
    _ensure_columns(conn)
    row = conn.execute(
        "SELECT agent_id, node, tmux_pane, tmux_server FROM recipients WHERE user_id=?",
        (user_id,),
    ).fetchone()
    if row is None:
        return False
    if agent_id and row["agent_id"]:
        return row["agent_id"] != agent_id
    return (
        row["node"] != node
        or row["tmux_pane"] != tmux_pane
        or row["tmux_server"] != tmux_server
    )


@_serialized
def rename_recipient(conn: sqlite3.Connection, old_id: str, new_id: str) -> None:
    """Move a handle, carrying its message history, tasks and team role along.

    The handle is a bare string in four tables rather than a foreign key, so
    every reference is rewritten in one transaction.
    """
    _ensure_columns(conn)
    with conn:
        conn.execute(
            "UPDATE recipients SET user_id=? WHERE user_id=?", (new_id, old_id)
        )
        conn.execute("UPDATE messages SET sender=? WHERE sender=?", (new_id, old_id))
        conn.execute(
            "UPDATE messages SET recipient=? WHERE recipient=?", (new_id, old_id)
        )
        conn.execute("UPDATE tasks SET assignee=? WHERE assignee=?", (new_id, old_id))
        conn.execute("UPDATE teams SET queen=? WHERE queen=?", (new_id, old_id))


@_serialized
def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Add new optional columns to pre-existing DBs."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(recipients)")}
    for col in (
        "agent_id",
        "model",
        "flavor",
        "instructions",
        "message_prefix",
        "submit_key",
        "owner_note",
        # The folder the agent's harness last ran in: where resuming its
        # session starts it again, long after its pane is gone.
        "cwd",
    ):
        if col not in cols:
            conn.execute(f"ALTER TABLE recipients ADD COLUMN {col} TEXT")
    if "team_id" not in cols:
        conn.execute("ALTER TABLE recipients ADD COLUMN team_id INTEGER")
    # tmux_pane holds the pane id (%N); tmux_server is the tmux server that
    # issued it (NULL for rows from before pane ids, which migrate_panes
    # rebinds); pane_label is the last-known session:window.pane, display only.
    for col in ("tmux_server", "pane_label"):
        if col not in cols:
            conn.execute(f"ALTER TABLE recipients ADD COLUMN {col} TEXT")
    # node is the machine the agent's pane lives on. Metadata for now; the
    # server fills it for rows that predate the column (fill_missing_node).
    if "node" not in cols:
        conn.execute("ALTER TABLE recipients ADD COLUMN node TEXT")
    # A reservation: a handle imported from another hub, holding its history
    # until the agent registers here. It has no pane yet, so it is offline,
    # it is never swept by the pane migration, and prune leaves it alone.
    if "reserved" not in cols:
        conn.execute("ALTER TABLE recipients ADD COLUMN reserved INTEGER NOT NULL DEFAULT 0")
    task_cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
    if "worktree" not in task_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN worktree TEXT")
    if "team_id" not in task_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN team_id INTEGER")
    if "note" not in task_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN note TEXT")
    if "worktree_node" not in task_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN worktree_node TEXT")
    if "attachments" not in task_cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN attachments TEXT")
    msg_cols = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
    if "reply_to" not in msg_cols:
        # Convert the old composer suffix once, atomically with the column.
        with conn:
            conn.execute("SAVEPOINT reply_backfill")
            conn.execute("ALTER TABLE messages ADD COLUMN reply_to INTEGER")
            suffix = re.compile(r'(?:^|\n\n)\(reply to message ([1-9]\d*); `(?:buzz|agent-swarm) messages --id \1` shows it\)$')
            for row in conn.execute("SELECT id, content FROM messages").fetchall():
                if match := suffix.search(row["content"]):
                    conn.execute("UPDATE messages SET reply_to=?, content=? WHERE id=?",
                                 (int(match[1]), row["content"][:match.start()], row["id"]))
            conn.execute("RELEASE SAVEPOINT reply_backfill")
    if "notify" not in msg_cols:
        conn.execute("ALTER TABLE messages ADD COLUMN notify INTEGER NOT NULL DEFAULT 0")
    if "attachments" not in msg_cols:
        conn.execute("ALTER TABLE messages ADD COLUMN attachments TEXT")
    if "status" not in msg_cols:
        # No default on purpose: a row an older server writes during an
        # upgrade has NULL here, and _message reads its flag instead. A
        # default of 'pending' would make such rows look in flight.
        conn.execute("ALTER TABLE messages ADD COLUMN status TEXT")
    if "client_id" not in msg_cols:
        conn.execute("ALTER TABLE messages ADD COLUMN client_id TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_client "
        "ON messages(sender, client_id) WHERE client_id IS NOT NULL"
    )
    conn.commit()


@_serialized
def lookup_pane(conn: sqlite3.Connection, user_id: str) -> str | None:
    row = conn.execute(
        "SELECT tmux_pane FROM recipients WHERE user_id=?", (user_id,)
    ).fetchone()
    return row["tmux_pane"] if row else None


@_serialized
def lookup_user_by_pane(
    conn: sqlite3.Connection, node: str, tmux_pane: str, tmux_server: str | None = None
) -> str | None:
    """The agent bound to this pane id under this tmux server on this node."""
    _ensure_columns(conn)
    row = conn.execute(
        "SELECT user_id FROM recipients WHERE node=? AND tmux_pane=? AND tmux_server IS ?",
        (node, tmux_pane, tmux_server),
    ).fetchone()
    return row["user_id"] if row else None


@_serialized
def lookup_user_by_restored_label(
    conn: sqlite3.Connection,
    node: str,
    pane_label: str,
    flavor: str | None,
    tmux_server: str,
) -> str | None:
    """An agent from an earlier tmux server that sat at this same position.

    After a tmux restart that restores the layout (e.g. tmux-resurrect), pane
    ids start over but positions come back, so a harness re-registering from
    its old position gets its identity back. Only rows from another server
    qualify, never ones bound in the running server.
    """
    row = conn.execute(
        "SELECT user_id FROM recipients WHERE node=? AND pane_label=? AND flavor IS ? "
        "AND tmux_server IS NOT NULL AND tmux_server<>? AND tmux_server<>? "
        "ORDER BY registered_at DESC LIMIT 1",
        (node, pane_label, flavor, tmux_server, UNBOUND),
    ).fetchone()
    return row["user_id"] if row else None


# tmux_server value for a row that could not be tied to any pane (see
# migrate_panes): offline until the agent registers again.
UNBOUND = "unbound"


@_serialized
def legacy_pane_rows(conn: sqlite3.Connection) -> list[dict]:
    """Rows still addressed the old way (no tmux server recorded)."""
    _ensure_columns(conn)
    return [dict(r) for r in conn.execute(
        "SELECT user_id, tmux_pane, flavor, node, registered_at FROM recipients "
        "WHERE tmux_server IS NULL AND reserved=0"
    )]


@_serialized
def bind_pane(
    conn: sqlite3.Connection,
    user_id: str,
    tmux_pane: str,
    tmux_server: str,
    pane_label: str | None,
) -> None:
    """Point a registration at a pane id (or mark it UNBOUND)."""
    conn.execute(
        "UPDATE recipients SET tmux_pane=?, tmux_server=?, pane_label=? WHERE user_id=?",
        (tmux_pane, tmux_server, pane_label, user_id),
    )
    conn.commit()


@_serialized
def lookup_user_by_agent_id(
    conn: sqlite3.Connection, agent_id: str, node: str | None = None
) -> str | None:
    """The agent with this harness session id, on `node` when one is given.

    A session id is only meaningful on the machine whose harness issued it,
    so callers pass the node they are speaking for (a node token may only
    speak for its own); an id held on another node is not this agent.
    """
    _ensure_columns(conn)
    if node is None:
        row = conn.execute(
            "SELECT user_id FROM recipients WHERE agent_id=?", (agent_id,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT user_id FROM recipients WHERE agent_id=? AND node=?", (agent_id, node)
        ).fetchone()
    return row["user_id"] if row else None


@_serialized
def adopt_agent_id(
    conn: sqlite3.Connection, user_id: str, agent_id: str, *,
    node: str, tmux_pane: str, tmux_server: str | None, replacing: str | None = None,
) -> bool:
    """Record a session id on a registration that has none, or, with
    `replacing`, swap that id for this one (see server._resolve_caller).
    One statement, so it can't half-happen: it only applies while the row
    still holds the expected id (empty, or `replacing`) and no row holds
    this id. True when this call recorded it."""
    held = "agent_id=?" if replacing else "(agent_id IS NULL OR agent_id='')"
    cur = conn.execute(
        "UPDATE recipients SET agent_id=? WHERE user_id=? "
        "AND node=? AND tmux_pane=? AND tmux_server IS ? AND reserved=0 "
        f"AND {held} "
        "AND NOT EXISTS (SELECT 1 FROM recipients WHERE agent_id=?)",
        (agent_id, user_id, node, tmux_pane, tmux_server, *([replacing] if replacing else []), agent_id),
    )
    conn.commit()
    return cur.rowcount == 1


@_serialized
def get_recipient(conn: sqlite3.Connection, user_id: str) -> dict | None:
    _ensure_columns(conn)
    row = conn.execute(
        "SELECT user_id, tmux_pane, tmux_server, pane_label, node, reserved, agent_id, model, flavor, instructions, message_prefix, submit_key, team_id, owner_note, cwd, registered_at "
        "FROM recipients WHERE user_id=?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


@_serialized
def list_recipients(conn: sqlite3.Connection) -> list[dict]:
    _ensure_columns(conn)
    rows = conn.execute(
        "SELECT user_id, tmux_pane, tmux_server, pane_label, node, reserved, agent_id, model, flavor, instructions, message_prefix, submit_key, team_id, owner_note, cwd, registered_at "
        "FROM recipients ORDER BY user_id"
    ).fetchall()
    return [dict(r) for r in rows]


@_serialized
def delete_recipient(conn: sqlite3.Connection, user_id: str) -> bool:
    with conn:
        cur = conn.execute("DELETE FROM recipients WHERE user_id=?", (user_id,))
        conn.execute("UPDATE teams SET queen=NULL WHERE queen=?", (user_id,))
        conn.execute("DELETE FROM summaries WHERE user_id=?", (user_id,))
        if _supervisor_row(conn).get("user_id") == user_id:
            conn.execute("DELETE FROM meta WHERE key='supervisor'")
    return cur.rowcount > 0


# ---- supervisor: the one agent the owner talks to about the whole swarm ----

SUPERVISOR_KEY = "supervisor"


def _supervisor_row(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (SUPERVISOR_KEY,)).fetchone()
    return json.loads(row["value"]) if row else {}


@_serialized
def get_supervisor(conn: sqlite3.Connection) -> dict | None:
    """{user_id, objective, since, cursor} or None. `cursor` is the last
    message id the hub has nudged the supervisor about."""
    row = _supervisor_row(conn)
    return row or None


@_serialized
def set_supervisor(
    conn: sqlite3.Connection, user_id: str, objective: str, cursor: int
) -> dict:
    """Appoint `user_id`; the nudge cursor starts at the newest message so the
    first nudge covers only what happens from now on."""
    if conn.execute("SELECT 1 FROM recipients WHERE user_id=?", (user_id,)).fetchone() is None:
        raise ValueError(f"{user_id} is not registered")
    row = {"user_id": user_id, "objective": objective, "since": time.time(),
           "cursor": cursor, "nudged_at": None}
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
            (SUPERVISOR_KEY, json.dumps(row)),
        )
    return row


@_serialized
def set_supervisor_cursor(conn: sqlite3.Connection, cursor: int, nudged_at: float) -> None:
    row = _supervisor_row(conn)
    if not row:
        return
    row["cursor"], row["nudged_at"] = cursor, nudged_at
    with conn:
        conn.execute("UPDATE meta SET value=? WHERE key=?", (json.dumps(row), SUPERVISOR_KEY))


@_serialized
def clear_supervisor(conn: sqlite3.Connection) -> dict | None:
    row = _supervisor_row(conn)
    with conn:
        conn.execute("DELETE FROM meta WHERE key=?", (SUPERVISOR_KEY,))
    return row or None


@_serialized
def record_summary(
    conn: sqlite3.Connection, user_id: str, text: str, source: str, ts: float | None = None
) -> bool:
    """Store what an agent is doing; False when nothing new was said.

    A pane title counts as new only when it changed since the last title seen;
    it keeps showing the same text while an agent reports its own summaries.
    An agent's own summary is new unless it is already the current summary.
    """
    only = "AND source=? " if source in ("title", "owner") else "AND source!='owner' "
    latest = conn.execute(
        f"SELECT text, source FROM summaries WHERE user_id=? {only}"
        "ORDER BY ts DESC, id DESC LIMIT 1",
        ((user_id, source) if source in ("title", "owner") else (user_id,)),
    ).fetchone()
    if latest is not None and (latest["text"], latest["source"]) == (text, source):
        return False
    with conn:
        conn.execute(
            "INSERT INTO summaries(user_id, text, source, ts) VALUES(?,?,?,?)",
            (user_id, text, source, time.time() if ts is None else ts),
        )
        conn.execute(
            "DELETE FROM summaries WHERE user_id=? AND id NOT IN ("
            "SELECT id FROM summaries WHERE user_id=? ORDER BY ts DESC, id DESC LIMIT ?)",
            (user_id, user_id, SUMMARY_HISTORY),
        )
    return True


@_serialized
def set_cwd(conn: sqlite3.Connection, user_id: str, cwd: str) -> None:
    with conn:
        conn.execute("UPDATE recipients SET cwd=? WHERE user_id=?", (cwd, user_id))


@_serialized
def set_owner_note(conn: sqlite3.Connection, user_id: str, text: str) -> dict | None:
    recipient = get_recipient(conn, user_id)
    if recipient is None:
        return None
    if (recipient["owner_note"] or "") != text:
        with conn:
            conn.execute("UPDATE recipients SET owner_note=? WHERE user_id=?", (text or None, user_id))
            record_summary(conn, user_id, text, "owner")
    return get_recipient(conn, user_id)


@_serialized
def summaries_by_user(conn: sqlite3.Connection, per_user: int = 5) -> dict[str, list[dict]]:
    """Each agent's latest summaries, newest first."""
    rows = conn.execute(
        "SELECT user_id, text, source, ts FROM ("
        "SELECT *, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY ts DESC, id DESC) AS n "
        "FROM summaries) WHERE n <= ? ORDER BY user_id, ts DESC, id DESC",
        (per_user,),
    ).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["user_id"], []).append(
            {"text": r["text"], "source": r["source"], "ts": r["ts"]}
        )
    return out


@_serialized
def create_task(
    conn: sqlite3.Connection,
    title: str,
    description: str | None = None,
    assignee: str | None = None,
    team_id: int | None = None,
    attachments: list[str] | None = None,
    depends_on: list[int] | None = None,
) -> dict:
    now = time.time()
    if team_id is not None:
        assignee = None
    with conn:
        deps = sorted(set(depends_on or []))
        for dep in deps:
            if conn.execute("SELECT 1 FROM tasks WHERE id=?", (dep,)).fetchone() is None:
                raise ValueError(f"unknown dependency: #{dep}")
        cur = conn.execute(
            "INSERT INTO tasks(title, description, assignee, team_id, status, created_at, updated_at, attachments) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (title, description, assignee, team_id, "open", now, now, json.dumps(attachments or [])),
        )
        task_id = int(cur.lastrowid)
        conn.executemany("INSERT INTO task_deps(task_id, depends_on) VALUES(?,?)", [(task_id, d) for d in deps])
    return get_task(conn, int(cur.lastrowid))


@_serialized
def delete_task(conn: sqlite3.Connection, task_id: int) -> bool:
    """Remove a task without silently satisfying another task's dependency."""
    with conn:
        dependents = [r[0] for r in conn.execute(
            "SELECT task_id FROM task_deps WHERE depends_on=?", (task_id,)
        )]
        if dependents:
            raise ValueError("remove this dependency from tasks " +
                             ", ".join(f"#{i}" for i in dependents) + " first")
        conn.execute("DELETE FROM task_deps WHERE task_id=?", (task_id,))
        return conn.execute("DELETE FROM tasks WHERE id=?", (task_id,)).rowcount > 0


def get_task(conn: sqlite3.Connection, task_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        return None
    task = dict(row)
    task["attachments"] = json.loads(task.get("attachments") or "[]")
    task["depends_on"] = [
        r["depends_on"]
        for r in conn.execute(
            "SELECT depends_on FROM task_deps WHERE task_id=? ORDER BY depends_on",
            (task_id,),
        )
    ]
    return task


@_serialized
def list_tasks(conn: sqlite3.Connection) -> list[dict]:
    deps: dict[int, list[int]] = {}
    for r in conn.execute("SELECT task_id, depends_on FROM task_deps ORDER BY depends_on"):
        deps.setdefault(r["task_id"], []).append(r["depends_on"])
    rows = conn.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
    tasks = []
    for row in rows:
        task = dict(row)
        task["attachments"] = json.loads(task.get("attachments") or "[]")
        task["depends_on"] = deps.get(task["id"], [])
        tasks.append(task)
    return tasks


def _validate_task_deps(
    conn: sqlite3.Connection, task_id: int, depends_on: list[int]
) -> list[int]:
    """Validate the next dependency graph without writing it."""
    unique = sorted(set(depends_on))
    for dep in unique:
        if dep == task_id:
            raise ValueError("a task cannot depend on itself")
        if conn.execute("SELECT 1 FROM tasks WHERE id=?", (dep,)).fetchone() is None:
            raise ValueError(f"unknown dependency: #{dep}")
    edges: dict[int, list[int]] = {}
    for r in conn.execute("SELECT task_id, depends_on FROM task_deps"):
        edges.setdefault(r["task_id"], []).append(r["depends_on"])
    edges[task_id] = unique
    seen, stack = set(), [task_id]
    while stack:
        node = stack.pop()
        for dep in edges.get(node, []):
            if dep == task_id:
                raise ValueError("dependency cycle")
            if dep not in seen:
                seen.add(dep)
                stack.append(dep)
    return unique


class TaskNoteRequired(ValueError):
    """The next task state would be done without its verification note."""


@_serialized
def update_task(
    conn: sqlite3.Connection,
    task_id: int,
    status: str | None = None,
    title: str | None = None,
    description: str | None | object = _UNSET,
    assignee: str | None | object = _UNSET,
    worktree: str | None | object = _UNSET,
    team_id: int | None | object = _UNSET,
    note: str | None | object = _UNSET,
    worktree_node: str | None | object = _UNSET,
    depends_on: list[int] | object = _UNSET,
) -> dict | None:
    """Validate and commit the full task aggregate against one database snapshot."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        task = get_task(conn, task_id)
        if task is None:
            return None
        if status is not None:
            if status not in TASK_STATUSES:
                raise ValueError(f"invalid status: {status}")
            task["status"] = status
        if title is not None:
            task["title"] = title
        if description is not _UNSET:
            task["description"] = description
        # A task is owned by an individual or a team, never both; setting one
        # side clears the other.
        if assignee is not _UNSET:
            task["assignee"] = assignee
            if assignee is not None:
                task["team_id"] = None
        if team_id is not _UNSET:
            task["team_id"] = team_id
            if team_id is not None:
                task["assignee"] = None
        if worktree is not _UNSET:
            task["worktree"] = worktree
        # A path only means something on the machine it is on; the two are set
        # and cleared together.
        if worktree_node is not _UNSET:
            task["worktree_node"] = worktree_node
        if task["worktree"] is None:
            task["worktree_node"] = None
        if note is not _UNSET:
            task["note"] = note
        if task["status"] == "done" and not (task["note"] or "").strip():
            raise TaskNoteRequired("a task needs a note before it can be closed")
        deps = _validate_task_deps(conn, task_id, depends_on) if depends_on is not _UNSET else None
        conn.execute(
            "UPDATE tasks SET status=?, title=?, description=?, assignee=?, team_id=?, worktree=?, "
            "worktree_node=?, note=?, updated_at=? WHERE id=?",
            (
                task["status"],
                task["title"],
                task["description"],
                task["assignee"],
                task["team_id"],
                task["worktree"],
                task["worktree_node"],
                task["note"],
                time.time(),
                task_id,
            ),
        )
        if deps is not None:
            conn.execute("DELETE FROM task_deps WHERE task_id=?", (task_id,))
            conn.executemany("INSERT INTO task_deps(task_id, depends_on) VALUES(?,?)",
                             [(task_id, dep) for dep in deps])
        return get_task(conn, task_id)


class TeamNameConflict(ValueError):
    """A different team already uses this name."""


def _team_name(conn: sqlite3.Connection, name: str, team_id: int = -1) -> str:
    name = name.strip()
    if not name:
        raise ValueError("Team name cannot be empty.")
    if conn.execute("SELECT 1 FROM teams WHERE name=? AND id!=?", (name, team_id)).fetchone():
        raise TeamNameConflict(f'A team named "{name}" already exists.')
    return name


@_serialized
def create_team(conn: sqlite3.Connection, name: str) -> dict:
    name = _team_name(conn, name)
    cur = conn.execute(
        "INSERT INTO teams(name, queen, created_at) VALUES(?,?,?)",
        (name, None, time.time()),
    )
    conn.commit()
    return get_team(conn, int(cur.lastrowid))


@_serialized
def get_team(conn: sqlite3.Connection, team_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
    if row is None:
        return None
    team = dict(row)
    team["members"] = [
        r["user_id"]
        for r in conn.execute(
            "SELECT user_id FROM recipients WHERE team_id=? ORDER BY user_id",
            (team_id,),
        )
    ]
    return team


@_serialized
def list_teams(conn: sqlite3.Connection) -> list[dict]:
    ids = [row["id"] for row in conn.execute("SELECT id FROM teams ORDER BY id")]
    return [get_team(conn, team_id) for team_id in ids]


@_serialized
def update_team(
    conn: sqlite3.Connection,
    team_id: int,
    name: str | None = None,
    queen: str | None | object = _UNSET,
) -> dict | None:
    team = get_team(conn, team_id)
    if team is None:
        return None
    if name is not None:
        team["name"] = _team_name(conn, name, team_id)
    if queen is not _UNSET:
        if queen is not None and queen not in team["members"]:
            raise ValueError(f"{queen} is not a member of team {team['name']}")
        team["queen"] = queen
    conn.execute(
        "UPDATE teams SET name=?, queen=? WHERE id=?",
        (team["name"], team["queen"], team_id),
    )
    conn.commit()
    return get_team(conn, team_id)


@_serialized
def delete_team(conn: sqlite3.Connection, team_id: int) -> bool:
    if get_team(conn, team_id) is None:
        return False
    conn.execute("UPDATE recipients SET team_id=NULL WHERE team_id=?", (team_id,))
    conn.execute("UPDATE tasks SET team_id=NULL WHERE team_id=?", (team_id,))
    conn.execute("DELETE FROM teams WHERE id=?", (team_id,))
    conn.commit()
    return True


@_serialized
def set_recipient_model(
    conn: sqlite3.Connection, user_id: str, model: str | None
) -> dict | None:
    """Relabel an agent's model on the dashboard. Never touches the agent itself."""
    cur = conn.execute("UPDATE recipients SET model=? WHERE user_id=?", (model, user_id))
    conn.commit()
    return get_recipient(conn, user_id) if cur.rowcount else None


@_serialized
def set_agent_team(
    conn: sqlite3.Connection, user_id: str, team_id: int | None
) -> dict | None:
    """Move an agent between teams (or out of any). Clears a vacated queen seat."""
    _ensure_columns(conn)
    recipient = get_recipient(conn, user_id)
    if recipient is None:
        return None
    if team_id is not None and get_team(conn, team_id) is None:
        raise ValueError(f"no such team: {team_id}")
    previous = recipient.get("team_id")
    if previous is not None and previous != team_id:
        conn.execute(
            "UPDATE teams SET queen=NULL WHERE id=? AND queen=?", (previous, user_id)
        )
    conn.execute(
        "UPDATE recipients SET team_id=? WHERE user_id=?", (team_id, user_id)
    )
    conn.commit()
    return get_recipient(conn, user_id)


MESSAGE_STATUSES = ("pending", "delivered", "failed", "unknown")


class DuplicateMessage(Exception):
    """A message with this sender and client id is already recorded."""

    def __init__(self, existing: dict):
        super().__init__(f"message {existing['id']} already has this client id")
        self.existing = existing


@_serialized
def record_message(
    conn: sqlite3.Connection,
    sender: str,
    recipient: str,
    context: str | None,
    content: str,
    status: str,
    delivery_error: str | None = None,
    attachments: list[str] | None = None,
    client_id: str | None = None,
    reply_to: int | None = None,
) -> int:
    """Store a message. `status` is one of MESSAGE_STATUSES.

    A message bound for a pane is recorded as pending before dispatch and
    settled with set_message_status afterwards, so the row exists even when
    the outcome is lost. `delivered` is kept as the flag form of the status.

    `client_id` is the sender's own id for the message, so a retry after a
    lost answer is recognised: if a row with it exists, DuplicateMessage is
    raised instead of recording a second message. A failed message does not
    keep its client id, so a definite failure can be retried.
    """
    if status not in MESSAGE_STATUSES:
        raise ValueError(f"invalid message status: {status}")
    if status == "failed":
        client_id = None
    if client_id:
        row = conn.execute(
            "SELECT * FROM messages WHERE sender=? AND client_id=?", (sender, client_id)
        ).fetchone()
        if row:
            raise DuplicateMessage(_message(row))
    cur = conn.execute(
        "INSERT INTO messages(sender, recipient, context, content, ts, delivered, delivery_error, "
        "attachments, status, client_id, reply_to) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            sender,
            recipient,
            context,
            content,
            time.time(),
            1 if status == "delivered" else 0,
            delivery_error,
            json.dumps(attachments) if attachments else None,
            status,
            client_id,
            reply_to,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


@_serialized
def record_notification(conn: sqlite3.Connection, sender: str, content: str,
                        context: str | None = None) -> int:
    """Check limits and store together, including across hub connections."""
    now = time.time()
    day = now // 86400 * 86400
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT MAX(ts) AS latest, COUNT(CASE WHEN ts >= ? THEN 1 END) AS today "
            "FROM messages WHERE sender=? AND recipient='owner' AND notify=1",
            (day, sender),
        ).fetchone()
        waits = []
        if row["latest"] is not None and now - row["latest"] < notifications.COOLDOWN_SECONDS:
            waits.append(row["latest"] + notifications.COOLDOWN_SECONDS - now)
        if row["today"] >= notifications.DAILY_LIMIT:
            waits.append(day + 86400 - now)
        if waits:
            raise notifications.NotificationLimit(max(1, math.ceil(max(waits))))
        cur = conn.execute(
            "INSERT INTO messages(sender,recipient,context,content,ts,delivered,status,notify) "
            "VALUES(?,'owner',?,?,?,1,'delivered',1)", (sender, context, content, now),
        )
        return int(cur.lastrowid)


@_serialized
def get_message(conn: sqlite3.Connection, message_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
    return _messages(conn, [row])[0] if row else None


def message_by_client_id(conn: sqlite3.Connection, sender: str, client_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM messages WHERE sender=? AND client_id=?", (sender, client_id)
    ).fetchone()
    return _messages(conn, [row])[0] if row else None


@_serialized
def owner_reply_reminder_due(
    conn: sqlite3.Connection, recipient: str, *, since: float, now: float,
    idle_seconds: float,
) -> bool:
    """Remind once per active owner conversation, after a quiet interval.

    Failed, pending, and unknown deliveries do not prove the agent saw the
    reminder. Replies to the owner keep an established conversation active.
    Registration starts a fresh interval; history keeps this restart-safe.
    """
    row = conn.execute(
        "SELECT MAX(CASE WHEN sender='owner' THEN ts END), MAX(ts) FROM messages "
        "WHERE delivered=1 AND ts>=? AND "
        "((sender='owner' AND recipient=?) OR (sender=? AND recipient='owner'))",
        (since, recipient, recipient),
    ).fetchone()
    return row[0] is None or now - row[1] >= idle_seconds


@_serialized
def abandon_pending_messages(conn: sqlite3.Connection, reason: str) -> int:
    """Mark every pending message unknown.

    Called once at startup, when no delivery can be in flight: a row still
    pending was dispatched by a server that stopped before recording the
    result. The paste may or may not have happened, so it is unknown and is
    never replayed. Returns the number of rows changed.
    """
    cur = conn.execute(
        "UPDATE messages SET status='unknown', delivered=0, delivery_error=? WHERE status='pending'",
        (reason,),
    )
    conn.commit()
    return cur.rowcount


@_serialized
def fill_missing_worktree_node(conn: sqlite3.Connection, node: str) -> int:
    """Stamp `node` on worktree paths recorded before nodes were. Every such
    path was recorded by an agent on this server's own machine."""
    cur = conn.execute(
        "UPDATE tasks SET worktree_node=? WHERE worktree IS NOT NULL AND worktree_node IS NULL",
        (node,),
    )
    conn.commit()
    return cur.rowcount


@_serialized
def set_message_status(
    conn: sqlite3.Connection, message_id: int, status: str, delivery_error: str | None = None
) -> None:
    if status not in MESSAGE_STATUSES:
        raise ValueError(f"invalid message status: {status}")
    # A failed message gives up its client id: sending it again is a retry.
    conn.execute(
        "UPDATE messages SET status=?, delivered=?, delivery_error=?, "
        "client_id=CASE WHEN ?='failed' THEN NULL ELSE client_id END WHERE id=?",
        (status, 1 if status == "delivered" else 0, delivery_error, status, message_id),
    )
    conn.commit()


@_serialized
def fetch_messages(
    conn: sqlite3.Connection,
    user_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    if user_id:
        rows = conn.execute(
            "SELECT * FROM messages WHERE recipient=? OR sender=? ORDER BY ts DESC LIMIT ?",
            (user_id, user_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM messages ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
    return _messages(conn, rows)


@_serialized
def search_agent_messages(conn: sqlite3.Connection, user: str, query: str,
                          limit: int = 100, offset: int = 0) -> dict:
    """Search the whole owner conversation, independently of history pages."""
    clause, params = search.matches(query)
    scope = "((sender='owner' AND recipient=?) OR (sender=? AND recipient='owner'))"
    where = f"{scope} AND ({clause})"
    args = [user, user, *params]
    total = conn.execute(f"SELECT COUNT(*) FROM messages WHERE {where}", args).fetchone()[0]
    rows = conn.execute(
        f"SELECT id, ts, sender, content FROM messages WHERE {where} "
        "ORDER BY id DESC LIMIT ? OFFSET ?", (*args, limit, offset),
    ).fetchall()
    def snippet(content):
        text = " ".join(content.split())
        # Center the short preview near the first literal search word when possible.
        positions = [text.casefold().find(word) for word in query.casefold().split()]
        start = max(0, min((p for p in positions if p >= 0), default=0) - 40)
        return ("…" if start else "") + text[start:start + 160] + ("…" if len(text) > start + 160 else "")
    return {"matches": [{"id": row["id"], "ts": row["ts"], "sender": row["sender"],
                         "snippet": snippet(row["content"])} for row in rows], "total": total}


@_serialized
def agent_messages_page(conn: sqlite3.Connection, user: str, limit: int = 300,
                        before: int | None = None, after: int | None = None) -> dict:
    """Page by immutable IDs so imports/timestamp ties cannot skip messages."""
    clauses = ["(sender=? OR recipient=?)"]
    args = [user, user]
    if before is not None:
        clauses.append("id < ?")
        args.append(before)
    if after is not None:
        clauses.append("id > ?")
        args.append(after)
    order = "ASC" if after is not None else "DESC"
    rows = conn.execute(
        f"SELECT * FROM messages WHERE {' AND '.join(clauses)} ORDER BY id {order} LIMIT ?",
        (*args, limit + 1),
    ).fetchall()
    return {"messages": _messages(conn, rows[:limit]), "has_more": len(rows) > limit}


@_serialized
def fetch_messages_after(
    conn: sqlite3.Connection, after_id: int = 0, since_ts: float = 0.0, limit: int = 500
) -> list[dict]:
    """Messages newer than a cursor, oldest first. Ids only go up, so a message
    id is an exact cursor; `since_ts` is the coarse alternative for a first look."""
    rows = conn.execute(
        "SELECT * FROM messages WHERE id > ? AND ts >= ? ORDER BY id ASC LIMIT ?",
        (after_id, since_ts, limit),
    ).fetchall()
    return _messages(conn, rows)


@_serialized
def message_ts(conn: sqlite3.Connection, message_id: int) -> float | None:
    row = conn.execute("SELECT ts FROM messages WHERE id=?", (message_id,)).fetchone()
    return float(row["ts"]) if row else None


@_serialized
def newest_message_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(id) AS m FROM messages").fetchone()
    return int(row["m"] or 0)


@_serialized
def delete_messages_before(conn: sqlite3.Connection, cutoff: float) -> int:
    """Delete messages sent before `cutoff`; return how many were removed."""
    cur = conn.execute("DELETE FROM messages WHERE ts < ?", (cutoff,))
    conn.commit()
    return cur.rowcount


@_serialized
def attachment_last_used(conn: sqlite3.Connection) -> dict[str, float]:
    """Message last use, plus current use for attachments retained by tasks."""
    rows = conn.execute(
        "SELECT j.value AS name, MAX(m.ts) AS ts "
        "FROM messages m, json_each(m.attachments) j "
        "WHERE m.attachments IS NOT NULL GROUP BY j.value"
    ).fetchall()
    used = {r["name"]: r["ts"] for r in rows}
    # Task references remain available for the lifetime of the task, including
    # unassigned work that has never generated a message.
    for row in conn.execute("SELECT DISTINCT j.value FROM tasks t, json_each(t.attachments) j"):
        used[row[0]] = time.time()
    return used


def _messages(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[dict]:
    """Attach reply previews in one query per page, including off-page parents."""
    messages = [_message(row) for row in rows]
    ids = {m["reply_to"] for m in messages if m.get("reply_to") is not None}
    originals = {}
    if ids:
        marks = ",".join("?" for _ in ids)
        originals = {r["id"]: r for r in conn.execute(
            f"SELECT id, sender, content FROM messages WHERE id IN ({marks})", tuple(ids)
        )}
    for message in messages:
        parent = originals.get(message.get("reply_to"))
        message["reply_preview"] = ({"id": parent["id"], "sender": parent["sender"],
                                     "content": " ".join(parent["content"].split())[:100]}
                                    if parent else None)
    return messages


def _message(row: sqlite3.Row) -> dict:
    msg = dict(row)
    msg["attachments"] = json.loads(msg["attachments"]) if msg.get("attachments") else []
    if msg.get("status") is None:
        # Written by a server from before statuses, which recorded a message
        # only after delivery: the flag is the whole story.
        msg["status"] = "delivered" if msg["delivered"] else "failed"
    return msg


# ---- nodes: the other machines enrolled with this hub ----------------------


@_serialized
def hub_id(conn: sqlite3.Connection) -> str:
    """A random id minted once per database. Nodes scope their record of
    executed commands by it, since message ids restart with a new database."""
    import uuid

    row = conn.execute("SELECT value FROM meta WHERE key='hub_id'").fetchone()
    if row:
        return row["value"]
    value = uuid.uuid4().hex
    conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('hub_id', ?)", (value,))
    conn.commit()
    return conn.execute("SELECT value FROM meta WHERE key='hub_id'").fetchone()["value"]


def hash_token(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@_serialized
def set_node_token(conn: sqlite3.Connection, name: str, token: str) -> None:
    """Enrol a node, or rotate its token. Only the hash is kept."""
    now = time.time()
    conn.execute(
        "INSERT INTO nodes(name, token_hash, created_at) VALUES(?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET token_hash=excluded.token_hash",
        (name, hash_token(token), now),
    )
    conn.commit()


@_serialized
def node_for_token(conn: sqlite3.Connection, token: str) -> str | None:
    """The node a bearer token belongs to, or None."""
    row = conn.execute(
        "SELECT name FROM nodes WHERE token_hash=?", (hash_token(token),)
    ).fetchone()
    return row["name"] if row else None


@_serialized
def touch_node(
    conn: sqlite3.Connection,
    name: str,
    version: str | None = None,
    tmux_server: str | None = None,
    harnesses: list[str] | None = None,
) -> None:
    """Record what a node last told us about itself, and when."""
    conn.execute(
        "UPDATE nodes SET last_seen=?, version=COALESCE(?, version), "
        "tmux_server=COALESCE(?, tmux_server), harnesses=COALESCE(?, harnesses) WHERE name=?",
        (
            time.time(),
            version,
            tmux_server,
            json.dumps(harnesses) if harnesses is not None else None,
            name,
        ),
    )
    conn.commit()


@_serialized
def list_nodes(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT name, created_at, last_seen, version, tmux_server, harnesses FROM nodes ORDER BY name"
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["harnesses"] = json.loads(d["harnesses"]) if d.get("harnesses") else []
        result.append(d)
    return result


@_serialized
def delete_node(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute("DELETE FROM nodes WHERE name=?", (name,))
    conn.commit()
    return cur.rowcount > 0


# ---- importing a bundle from another hub ----------------------------------


def _hub_state(conn: sqlite3.Connection) -> dict:
    """This hub as an import plan needs to see it: which handles, stable ids,
    team names, and node names are already in use."""
    return {
        # Retired agents' handles too, so an imported agent never takes over
        # a stranger's history.
        "handles": names.used(conn),
        "panes": [dict(r) for r in conn.execute(
            "SELECT node, tmux_server, tmux_pane FROM recipients WHERE reserved=0"
        )],
        "agents_by_id": {
            r["agent_id"]: {"user_id": r["user_id"], "node": r["node"]}
            for r in conn.execute(
                "SELECT user_id, agent_id, node FROM recipients "
                "WHERE agent_id IS NOT NULL AND agent_id<>''"
            )
        },
        "team_names": {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM teams")},
        "nodes": {r[0] for r in conn.execute("SELECT name FROM nodes")},
    }


@_serialized
def hub_state(conn: sqlite3.Connection) -> dict:
    """The same snapshot, for a dry run, which writes nothing."""
    _ensure_columns(conn)
    return _hub_state(conn)


class AlreadyImported(Exception):
    """This export has been taken in before. Carries the earlier report."""

    def __init__(self, report: dict):
        super().__init__("this bundle was imported already")
        self.report = report


@_serialized
def clear_reservation(conn: sqlite3.Connection, user_id: str) -> None:
    """The agent registered: its row is a real registration now."""
    conn.execute("UPDATE recipients SET reserved=0 WHERE user_id=?", (user_id,))
    conn.commit()


@_serialized
def imported_report(conn: sqlite3.Connection, source_id: str) -> dict | None:
    row = conn.execute(
        "SELECT report FROM imports WHERE source_id=?", (source_id,)
    ).fetchone()
    return json.loads(row["report"]) if row else None


@_serialized
def apply_import(
    conn: sqlite3.Connection,
    source_id: str,
    node: str,
    make_plan,
    summarize,
    again: bool = False,
) -> dict:
    """Take a bundle in, as one transaction.

    `make_plan` is handed this hub as it is inside the transaction and
    returns the plan; deciding and writing in the same transaction means a
    registration landing in between cannot take a handle the plan chose.
    Nothing is written when any part of it fails.
    """
    _ensure_columns(conn)
    # IMMEDIATE, so the state the plan is made from and the writes it turns
    # into are one transaction against one snapshot.
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT report FROM imports WHERE source_id=?", (source_id,)
        ).fetchone()
        if row is not None and not again:
            raise AlreadyImported(json.loads(row["report"]))

        plan = make_plan(_hub_state(conn))
        now = time.time()

        team_ids: dict[str, int] = {}
        for team in plan["teams"]:
            if team["existing_id"] is not None:
                team_ids[team["name"]] = team["existing_id"]
            else:
                cur = conn.execute(
                    "INSERT INTO teams(name, queen, created_at) VALUES(?,?,?)",
                    (team["name"], None, now),
                )
                team_ids[team["name"]] = int(cur.lastrowid)

        for agent in plan["agents"]:
            binding = agent.get("binding")
            conn.execute(
                "INSERT INTO recipients(user_id, tmux_pane, agent_id, model, flavor, instructions, "
                "message_prefix, submit_key, registered_at, tmux_server, pane_label, node, team_id, reserved) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    agent["user_id"],
                    # Unique per handle, and never a pane id, so no two
                    # reservations collide and none matches a real pane.
                    binding["pane"] if binding else f"reserved:{agent['user_id']}",
                    agent["agent_id"], agent["model"], agent["flavor"], agent["instructions"],
                    agent["message_prefix"], agent["submit_key"], now,
                    binding["server"] if binding else None,
                    binding["label"] if binding else None, agent["node"],
                    team_ids.get(agent["team"]) if agent["team"] else None,
                    0 if binding else 1,
                ),
            )

        for team in plan["teams"]:
            for member in team["members"]:
                conn.execute(
                    "UPDATE recipients SET team_id=? WHERE user_id=?",
                    (team_ids[team["name"]], member),
                )
            if team["queen"]:
                conn.execute(
                    "UPDATE teams SET queen=? WHERE id=?", (team["queen"], team_ids[team["name"]])
                )

        task_ids: dict = {}
        for task in plan["tasks"]:
            cur = conn.execute(
                "INSERT INTO tasks(title, description, assignee, team_id, status, worktree, "
                "worktree_node, note, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    task["title"], task["description"], task["assignee"],
                    team_ids.get(task["team"]) if task["team"] else None,
                    task["status"], task["worktree"], task["worktree_node"], task["note"],
                    task["created_at"], task["updated_at"],
                ),
            )
            if task["old_id"] is not None:
                task_ids[task["old_id"]] = int(cur.lastrowid)
        for task in plan["tasks"]:
            here = task_ids.get(task["old_id"])
            for dep in task["depends_on"]:
                if here is not None and dep in task_ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO task_deps(task_id, depends_on) VALUES(?,?)",
                        (here, task_ids[dep]),
                    )

        for message in plan["messages"]:
            conn.execute(
                "INSERT INTO messages(sender, recipient, context, content, ts, delivered, "
                "delivery_error, attachments, status) VALUES(?,?,?,?,?,?,?,NULL,?)",
                (
                    message["sender"], message["recipient"], message["context"],
                    message["content"], message["ts"],
                    1 if message["status"] == "delivered" else 0,
                    message["delivery_error"], message["status"],
                ),
            )

        report = summarize(plan)
        report["task_ids"] = {str(k): v for k, v in task_ids.items()}
        report["imported_at"] = now
        conn.execute(
            "INSERT OR REPLACE INTO imports(source_id, node, imported_at, report) VALUES(?,?,?,?)",
            (source_id, node, now, json.dumps(report)),
        )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return report
