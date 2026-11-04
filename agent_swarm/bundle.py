"""Moving agents, teams, and tasks from one hub's database to another.

A machine that ran its own agent-swarm has agents, teams, and a task board
of its own. `read` turns that database into a bundle: a plain dict, written
as JSON, carried to the hub by hand. `plan` decides what the hub would do
with it, and is pure, so the decisions can be shown before anything is
written (`--dry-run`) and tested without a database. `db.apply_import`
computes a plan and performs it inside one write transaction, so a
registration that lands in between cannot invalidate the names it chose.

Attachments (their bytes are on the other machine) and node tokens do not
travel. Pane addresses are hints verified against the target node. An agent
whose pane cannot be verified arrives as a reservation, an offline row
holding its handle until it registers here through the node daemon. Imported messages are
history: they are written as they were recorded, never delivered again,
and tagged so that task numbers inside their text read as the old board's.
"""

from __future__ import annotations

import random
import sqlite3
import time
import uuid
from pathlib import Path

from . import names, panes, tmux

FORMAT = 1
MAX_MESSAGES = 5000
MAX_ROWS = 20000


class Invalid(ValueError):
    """A bundle this hub will not read."""


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def open_readonly(path: str | Path) -> sqlite3.Connection:
    """Open a database without writing to it: no migrations, no cleanup.

    The source may be a live server's database or an archived copy, and
    neither should change because it was exported.
    """
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise Invalid(f"no database at {resolved}")
    conn = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _pick(row: sqlite3.Row, *fields: str) -> dict:
    return {f: row[f] for f in fields if f in row.keys()}


def read(conn: sqlite3.Connection, with_messages: bool = False, source: str | None = None) -> dict:
    """Read a bundle out of an agent-swarm database.

    Reads by column name against whatever the schema has, since a database
    written by an older agent-swarm has fewer columns than this one, and in
    one deferred transaction so the tables agree with each other even if a
    server is still running against this file.
    """
    tables = _tables(conn)
    if "recipients" not in tables:
        raise Invalid("this does not look like an agent-swarm database")

    conn.execute("BEGIN DEFERRED")
    try:
        # The source's own identity when it has one, so a repeated import of
        # the same export is recognised rather than applied twice.
        source_id = source
        if source_id is None and "meta" in tables:
            row = conn.execute("SELECT value FROM meta WHERE key='hub_id'").fetchone()
            source_id = row["value"] if row else None
        source_id = source_id or uuid.uuid4().hex

        teams_by_id: dict[int, str] = {}
        teams: list[dict] = []
        recipient_cols = _columns(conn, "recipients")
        has_teams = "teams" in tables and "team_id" in recipient_cols
        if has_teams:
            for row in conn.execute("SELECT id, name, queen FROM teams ORDER BY id"):
                teams_by_id[row["id"]] = row["name"]
                teams.append({"name": row["name"], "queen": row["queen"], "members": []})

        agents = []
        wanted = ("user_id", "agent_id", "model", "flavor", "instructions",
                  "message_prefix", "submit_key", "node", "tmux_pane", "tmux_server")
        for row in conn.execute("SELECT * FROM recipients ORDER BY user_id"):
            if "reserved" in recipient_cols and row["reserved"]:
                continue  # a reservation on the source is not an agent
            agent = _pick(row, *wanted)
            team = teams_by_id.get(row["team_id"]) if has_teams else None
            agent["team"] = team
            agents.append(agent)
            if team:
                next(t for t in teams if t["name"] == team)["members"].append(row["user_id"])

        tasks = []
        if "tasks" in tables:
            deps: dict[int, list[int]] = {}
            if "task_deps" in tables:
                for row in conn.execute("SELECT task_id, depends_on FROM task_deps"):
                    deps.setdefault(row["task_id"], []).append(row["depends_on"])
            fields = ("title", "description", "assignee", "status", "worktree",
                      "worktree_node", "note", "created_at", "updated_at")
            for row in conn.execute("SELECT * FROM tasks ORDER BY id LIMIT ?", (MAX_ROWS,)):
                task = _pick(row, *fields)
                task["id"] = row["id"]
                task["team"] = teams_by_id.get(row["team_id"]) if "team_id" in row.keys() else None
                task["depends_on"] = sorted(deps.get(row["id"], []))
                tasks.append(task)

        messages = []
        if with_messages and "messages" in tables:
            rows = conn.execute(
                "SELECT * FROM messages ORDER BY ts DESC LIMIT ?", (MAX_MESSAGES,)
            ).fetchall()
            for row in reversed(rows):
                message = _pick(row, "id", "sender", "recipient", "context", "content",
                                "ts", "delivered", "delivery_error", "status")
                raw = row["attachments"] if "attachments" in row.keys() else None
                message["attachments"] = 0
                if raw:
                    try:
                        import json

                        message["attachments"] = len(json.loads(raw) or [])
                    except ValueError:
                        message["attachments"] = 0
                messages.append(message)
    finally:
        conn.rollback()

    return {
        "agent_swarm_bundle": FORMAT,
        "exported_at": time.time(),
        "source": {"id": source_id, "hub": source_id},
        "agents": agents,
        "teams": teams,
        "tasks": tasks,
        "messages": messages,
    }


def source_id(bundle: dict) -> str:
    """What identifies this export, so importing it twice can be refused."""
    source = bundle.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("id"), str) or not source["id"]:
        raise Invalid("the bundle does not say where it came from")
    return source["id"]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Invalid(message)


def _text(value, what: str, required: bool = False) -> str | None:
    """A string, or nothing. Anything else is a bundle this hub will not read."""
    if value is None or value == "":
        _require(not required, f"{what} is required")
        return None
    _require(isinstance(value, str), f"{what} must be text, not {type(value).__name__}")
    return value


def _number(value, what: str):
    if value is None:
        return None
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"{what} must be a number",
    )
    return value


def validate(bundle: dict) -> None:
    """Check the shape of a bundle before anything is decided about it.

    Everything after this may assume the types it names, so a malformed
    bundle is one clear refusal rather than an error from somewhere deep in
    the planning.
    """
    _require(isinstance(bundle, dict), "a bundle is a JSON object")
    version = bundle.get("agent_swarm_bundle")
    _require(version == FORMAT, f"bundle format {version!r}, expected {FORMAT}")
    for key in ("agents", "teams", "tasks", "messages"):
        value = bundle.get(key, [])
        _require(isinstance(value, list), f"{key} must be a list")
        _require(len(value) <= MAX_ROWS, f"too many {key} in one bundle")
        _require(all(isinstance(x, dict) for x in value), f"each of {key} is an object")

    handles, ids = set(), set()
    for raw in bundle.get("agents", []):
        handle = _text(raw.get("user_id"), "an agent's user_id", required=True)
        _require(handle not in handles, f"the bundle lists {handle!r} twice")
        handles.add(handle)
        agent_id = _text(raw.get("agent_id"), f"{handle}'s agent_id")
        if agent_id:
            _require(agent_id not in ids, f"two agents share the id {agent_id!r}")
            ids.add(agent_id)
        for field in ("model", "flavor", "instructions", "message_prefix", "submit_key", "team", "tmux_pane", "tmux_server"):
            _text(raw.get(field), f"{handle}'s {field}")

    names_seen, members_seen = set(), {}
    for raw in bundle.get("teams", []):
        name = (_text(raw.get("name"), "a team's name", required=True) or "").strip()
        _require(bool(name), "a team's name is required")
        _require(name not in names_seen, f"the bundle lists team {name!r} twice")
        names_seen.add(name)
        _text(raw.get("queen"), f"team {name!r} queen")
        members = raw.get("members", [])
        _require(isinstance(members, list), f"team {name!r} members must be a list")
        for member in members:
            _text(member, f"a member of team {name!r}", required=True)
            _require(
                member not in members_seen,
                f"{member!r} is on two teams, {members_seen.get(member)!r} and {name!r}",
            )
            members_seen[member] = name

    task_ids = set()
    for raw in bundle.get("tasks", []):
        title = _text(raw.get("title"), "a task's title", required=True)
        task_id = raw.get("id")
        if task_id is not None:
            _require(
                isinstance(task_id, int) and not isinstance(task_id, bool),
                "a task id is a whole number",
            )
            _require(task_id not in task_ids, f"the bundle lists task id {task_id} twice")
            task_ids.add(task_id)
        for field in ("description", "assignee", "status", "worktree", "worktree_node", "note", "team"):
            _text(raw.get(field), f"task {title!r} {field}")
        for field in ("created_at", "updated_at"):
            _number(raw.get(field), f"task {title!r} {field}")
        deps = raw.get("depends_on", []) or []
        _require(isinstance(deps, list), f"task {title!r} depends_on must be a list")
        for dep in deps:
            _require(
                isinstance(dep, int) and not isinstance(dep, bool),
                f"task {title!r} depends on something that is not a task id",
            )

    for raw in bundle.get("messages", []):
        _text(raw.get("sender"), "a message sender", required=True)
        _text(raw.get("recipient"), "a message recipient", required=True)
        _text(raw.get("content"), "a message's text")
        _text(raw.get("context"), "a message's context")
        _number(raw.get("ts"), "a message's time")
        count = raw.get("attachments", 0) or 0
        _require(
            isinstance(count, int) and not isinstance(count, bool),
            "an attachment count is a whole number",
        )


def _unique_team_name(name: str, node: str, taken: set[str]) -> str:
    """A name for a team whose name is already used here, saying where it
    came from rather than merging two unrelated teams."""
    candidate = f"{name} ({node})"
    n = 2
    while candidate in taken:
        candidate = f"{name} ({node} {n})"
        n += 1
    return candidate


def plan(bundle: dict, node: str, hub: dict, rng=None, snapshot=None) -> dict:
    """Decide what importing `bundle` onto `node` would do.

    `hub` describes this hub as it is right now:
        handles      every handle in use
        agents_by_id stable agent id -> {"user_id", "node"} of the row holding it
        team_names   team name -> id
        nodes        node names this hub knows
        merge_teams  reuse a team of the same name instead of renaming

    Nothing here touches a database. `db.apply_import` calls it inside the
    transaction that writes the result, so these decisions cannot go stale.
    """
    validate(bundle)
    # Names come from a generator seeded by the export itself, so a dry run
    # and the import that follows it agree on every rename.
    rng = rng or random.Random(f"agent-swarm-import:{source_id(bundle)}:{node}")

    taken = set(hub.get("handles") or ())
    agents_by_id = hub.get("agents_by_id") or {}
    team_names = dict(hub.get("team_names") or {})
    known_nodes = set(hub.get("nodes") or ()) | {node}
    merge_teams = bool(hub.get("merge_teams"))

    warnings: list[str] = []
    handle_of: dict[str, str] = {}
    renamed: dict[str, str] = {}
    merged: list[dict] = []
    agents: list[dict] = []
    seen: set[str] = set()

    for raw in bundle.get("agents", []):
        old = raw["user_id"]
        seen.add(old)
        agent_id = raw.get("agent_id") or None
        # An empty id matches nothing: two agents that never reported one are
        # not the same agent.
        if agent_id and agent_id in agents_by_id:
            here = agents_by_id[agent_id]
            handle_of[old] = here["user_id"]
            merged.append({"from": old, "to": here["user_id"], "node": here.get("node")})
            if here.get("node") and here["node"] != node:
                warnings.append(
                    f"{old} is already here as {here['user_id']} on {here['node']}; "
                    "it keeps that handle and machine, and nothing about it is changed"
                )
            continue
        # The canonical form decides the clash: "OTTER" and "otter" are one
        # handle here, and so are two spellings of it within one bundle.
        try:
            canonical = names.normalize_requested(old)
        except names.InvalidName:
            canonical = None
            warnings.append(f"{old!r} is not a usable handle here")
        if canonical is None or canonical in taken:
            handle_of[old] = names.pick(taken, rng)
            renamed[old] = handle_of[old]
        else:
            handle_of[old] = canonical
            if canonical != old:
                renamed[old] = canonical
        taken.add(handle_of[old])
        agents.append({
            "user_id": handle_of[old],
            "agent_id": agent_id,
            "model": raw.get("model"),
            "flavor": raw.get("flavor"),
            "instructions": raw.get("instructions"),
            "message_prefix": raw.get("message_prefix"),
            "submit_key": raw.get("submit_key"),
            "team": raw.get("team"),
            "node": node,
            "source_handle": old,
            "source_pane": raw.get("tmux_pane"),
            "source_server": raw.get("tmux_server"),
        })

    # A pane id alone can point to an unrelated agent after tmux restarts.
    # Require both server provenance and the pane's own agent identity tag.
    occupied = {(p["node"], p["tmux_server"], p["tmux_pane"])
                for p in hub.get("panes", [])}
    claims = {}
    for agent in agents:
        key = (agent["source_server"], agent["source_pane"])
        claims[key] = claims.get(key, 0) + 1
    for agent in agents:
        pane, server = agent["source_pane"], agent["source_server"]
        row = snapshot.table.get(pane) if snapshot and pane else None
        agent["binding"] = None
        if not pane or not pane.startswith("%") or not server:
            reason = "export has no stable pane/server identity"
        elif snapshot is None:
            reason = "node is disconnected or cannot observe tmux"
        elif server != snapshot.server:
            reason = "tmux server changed"
        elif not row:
            reason = "pane no longer exists"
        elif claims[(server, pane)] != 1:
            reason = "multiple imported agents claim this pane"
        elif (node, server, pane) in occupied:
            reason = "pane already belongs to an agent on this hub"
        elif not panes.harness_matches(agent["flavor"], row.get("command", "")):
            reason = "pane is not running the expected harness"
        elif (row.get("agent_swarm") != agent["source_handle"]
              and row.get("title") != tmux.status_title(agent["source_handle"], agent["flavor"])):
            reason = "pane does not identify the imported agent"
        else:
            agent["binding"] = {"pane": pane, "server": server, "label": row["label"]}
            reason = None
            occupied.add((node, server, pane))
        agent["reservation_reason"] = reason

    def resolve(handle, what: str):
        """A bundle handle as it will read here.

        Only handles the bundle itself brought over, plus the owner. A name
        that merely matches an agent already on this hub is a different
        agent and is refused, rather than quietly pointing at a stranger.
        """
        if handle is None:
            return None
        if handle == "owner":
            return "owner"
        if handle in handle_of:
            return handle_of[handle]
        warnings.append(
            f"{what} names {handle!r}, which the bundle does not carry"
            + (f"; this hub has an unrelated {handle!r}, which is not used" if handle in taken else "")
        )
        return None

    teams = []
    team_of: dict[str, str] = {}
    for raw in bundle.get("teams", []):
        name = raw["name"].strip()
        here_id = team_names.get(name)
        if here_id is not None and not merge_teams:
            # Two teams that share a name are not one team.
            fresh = _unique_team_name(name, node, set(team_names) | {t["name"] for t in teams})
            warnings.append(f"a team called {name!r} is already here; imported as {fresh!r}")
            new_name, existing_id = fresh, None
        else:
            new_name, existing_id = name, here_id
        team_of[name] = new_name
        arriving = {a["user_id"] for a in agents}
        members, elsewhere = [], []
        for handle in raw.get("members", []):
            here = resolve(handle, f"team {name!r}")
            if here is None:
                continue
            # An agent this hub already had keeps the team it is already on:
            # an import never moves a row that was here first.
            (members if here in arriving else elsewhere).append(here)
        if elsewhere:
            warnings.append(
                f"team {name!r} lists {', '.join(sorted(elsewhere))}, already here and left "
                "on whatever team they are on; add them by hand if you want them on this one"
            )
        queen = resolve(raw.get("queen"), f"team {name!r} queen")
        if queen and queen not in members:
            warnings.append(f"team {name!r} queen {queen} is not one of its members; imported without a queen")
            queen = None
        teams.append({"name": new_name, "was": name, "members": members,
                      "queen": queen, "existing_id": existing_id})

    for agent in agents:
        if agent["team"]:
            agent["team"] = team_of.get(agent["team"])

    tasks = []
    ids = {raw["id"] for raw in bundle.get("tasks", []) if raw.get("id") is not None}
    for raw in bundle.get("tasks", []):
        title = raw["title"].strip()
        _require(bool(title), "each task needs a title")
        team = team_of.get(raw.get("team")) if raw.get("team") else None
        if raw.get("team") and team is None:
            warnings.append(f"task {title!r} names team {raw['team']!r}, which is not in the bundle")
        assignee = None if team else resolve(raw.get("assignee"), f"task {title!r}")
        status = raw.get("status") if raw.get("status") in ("open", "picked_up", "done") else "open"
        kept, dropped = [], []
        for dep in raw.get("depends_on", []) or []:
            (kept if dep in ids else dropped).append(dep)
        if dropped:
            warnings.append(
                f"task {title!r} depends on {', '.join(f'#{d}' for d in dropped)}, "
                "which the bundle does not carry; those dependencies are dropped"
            )
        # A path belongs to the machine that holds it, which the source may
        # already have recorded; otherwise it is the machine being imported.
        where = raw.get("worktree_node") or (node if raw.get("worktree") else None)
        if where and where not in known_nodes:
            warnings.append(f"task {title!r} has a worktree on {where!r}, which this hub does not know")
        tasks.append({
            "old_id": raw.get("id"),
            "title": title,
            "description": raw.get("description"),
            "assignee": assignee,
            "team": team,
            "status": status,
            "worktree": raw.get("worktree"),
            "worktree_node": where,
            "note": raw.get("note"),
            "created_at": raw.get("created_at") or time.time(),
            "updated_at": raw.get("updated_at") or time.time(),
            "depends_on": kept,
        })
    _check_cycles(tasks)

    source = bundle.get("source") or {}
    tag = f"imported from {source.get('id', 'elsewhere')[:8]}"
    messages = []
    for raw in bundle.get("messages", [])[:MAX_MESSAGES]:
        sender = resolve(raw.get("sender"), "a message")
        recipient = resolve(raw.get("recipient"), "a message")
        if sender is None or recipient is None:
            continue  # an end of the conversation did not come across
        content = raw.get("content") or ""
        if raw.get("attachments"):
            content += f"\n\n[{raw['attachments']} attachment(s) not migrated]"
        status = raw.get("status") or ("delivered" if raw.get("delivered") else "failed")
        messages.append({
            "sender": sender, "recipient": recipient,
            # Marked as history: task numbers in the text are the old board's.
            "context": f"{raw['context']} · imported" if raw.get("context") else tag,
            "content": content,
            "ts": raw.get("ts") or time.time(),
            # Nothing imported is in flight, so nothing reads as pending.
            "status": status if status in ("delivered", "failed", "unknown") else "unknown",
            "delivery_error": raw.get("delivery_error"),
        })

    return {
        "node": node,
        "source_id": source_id(bundle),
        "agents": agents,
        "teams": teams,
        "tasks": tasks,
        "messages": messages,
        "renamed": renamed,
        "merged": merged,
        "warnings": sorted(set(warnings)),
    }


def _check_cycles(tasks: list[dict]) -> None:
    """Refuse a board whose tasks wait on each other.

    Walked with an explicit stack: a bundle may carry thousands of tasks in
    one chain, which recursion could not follow.
    """
    edges = {t["old_id"]: list(t["depends_on"]) for t in tasks if t["old_id"] is not None}
    state: dict = {}
    for start in edges:
        if start in state:
            continue
        state[start] = "open"
        stack = [(start, iter(edges.get(start, ())))]
        while stack:
            node_id, following = stack[-1]
            nxt = next(following, None)
            if nxt is None:
                state[node_id] = "done"
                stack.pop()
                continue
            if state.get(nxt) == "open":
                raise Invalid(f"the bundle's tasks depend on each other in a cycle (#{nxt})")
            if nxt not in state:
                state[nxt] = "open"
                stack.append((nxt, iter(edges.get(nxt, ()))))


def summary(plan_result: dict) -> dict:
    """The short form kept with the import and shown to the owner."""
    return {
        "node": plan_result["node"],
        "source_id": plan_result["source_id"],
        "agents": len(plan_result["agents"]),
        "teams": len(plan_result["teams"]),
        "tasks": len(plan_result["tasks"]),
        "messages": len(plan_result["messages"]),
        "renamed": plan_result["renamed"],
        "merged": plan_result["merged"],
        "warnings": plan_result["warnings"],
        "reconnected": [a["user_id"] for a in plan_result["agents"] if a.get("binding")],
        "reservations": [{"user_id": a["user_id"], "reason": a.get("reservation_reason")}
                         for a in plan_result["agents"] if not a.get("binding")],
    }


def register_commands(plan_result: dict) -> list[str]:
    """What to tell each agent on the other machine to run.

    An agent that reports its stable id reclaims its handle by itself; the
    rest ask for it by name.
    """
    lines = []
    for agent in plan_result["agents"]:
        if agent.get("binding"):
            continue
        flavor = f" --flavor {agent['flavor']}" if agent.get("flavor") else ""
        # A handle held for a named conversation is given only to that
        # conversation, so the line has to carry its id.
        agent_id = f" --agent-id {agent['agent_id']}" if agent.get("agent_id") else ""
        lines.append(f"buzz register --name {agent['user_id']}{flavor}{agent_id}")
    return lines
