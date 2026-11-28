"""Run the same black-box scenarios against the Python hub and the Rust hub
and compare what they answer.

Each hub gets its own empty database and its own isolated tmux server
(`tmux -L rustclone-...`) with the same windows, each running `cat`, so a
delivered message can be read back with capture-pane.

    python rust/compat/run_compat.py [--out DIR] [--real-db COPY.sqlite]

Exit status 1 when any step differs. Prints a Markdown table.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hubs import SCRATCH, Hub, Tmux, copy_db  # noqa: E402

TIMES = {"ts", "registered_at", "created_at", "updated_at", "now", "pinned_at", "since", "retired_at", "last_seen"}
TRUST_SCREEN = "Accessing workspace:\\n\\n/tmp/compat-folder\\n\\n1. Yes, I trust this folder\\n2. No, exit\\n"


def normal(value, names: dict[str, str]):
    """Replace what legitimately differs between two runs: times, the tmux
    server id, the randomly picked handle, and scratch paths."""
    if isinstance(value, dict):
        return {k: ("<time>" if k in TIMES and isinstance(v, (int, float)) else normal(v, names)) for k, v in value.items()}
    if isinstance(value, list):
        return [normal(v, names) for v in value]
    if isinstance(value, str):
        for real, alias in names.items():
            value = value.replace(real, alias)
        return re.sub(r"\b\d{3,}:\d{9,}\b", "<tmux-server>", value)
    return value


class Run:
    """One hub's pass through the scenarios: an ordered list of named steps."""

    def __init__(self, hub: Hub, tmux: Tmux):
        self.hub, self.tmux = hub, tmux
        self.steps: list[tuple[str, str, object]] = []
        self.names = {str(hub.db.parent): "<work>", hub.db.name: "<db>"}

    def step(self, group: str, name: str, value) -> None:
        self.steps.append((group, name, value))

    def normalized(self) -> list[tuple[str, str, object]]:
        """Steps with run-specific values replaced, once every name is known."""
        return [(group, name, normal(value, self.names)) for group, name, value in self.steps]

    def http(self, group: str, name: str, method: str, path: str, body=None, headers=None):
        status, payload, _ = self.hub.call(method, path, body, headers)
        self.step(group, name, {"status": status, "body": payload})
        return status, payload

    def screen(self, group: str, name: str, pane: str) -> str:
        time.sleep(0.3)  # let `cat` echo the submitted line
        text = self.tmux.capture(pane)
        self.step(group, name, text)
        return text


def scenarios(r: Run) -> None:
    panes = r.tmux.start(4)
    a_pane, b_pane, c_pane, d_pane = panes

    g = "health"
    r.http(g, "GET /health", "GET", "/health")

    g = "register"
    _, a = r.http(g, "register A: pool handle, session id, claude model", "POST", "/register",
                  {"tmux_pane": a_pane, "agent_id": "sess-a", "model": "claude-opus-4-7"})
    A = a["user_id"]
    r.names[A] = "<A>"
    r.step(g, "assigned handle is a pool name", {"assigned": a["assigned"], "in_pool": bool(re.fullmatch(r"[a-z-]+", A))})
    r.http(g, "register B: requested handle, codex model, positional target", "POST", "/register",
           {"tmux_pane": "w:1.0", "requested_user": "Tapir", "model": "gpt-5-codex", "instructions": "be brief"})
    r.http(g, "register B again: same pane, no fields (keeps flavor)", "POST", "/register", {"tmux_pane": b_pane})
    r.http(g, "register: invalid handle", "POST", "/register", {"tmux_pane": c_pane, "requested_user": "Bad Name!"})
    r.http(g, "register: reserved handle owner", "POST", "/register", {"tmux_pane": c_pane, "requested_user": "owner"})
    r.http(g, "register: handle held by a live agent", "POST", "/register", {"tmux_pane": c_pane, "requested_user": "tapir"})
    r.http(g, "register: pane does not resolve", "POST", "/register", {"tmux_pane": "%99"})
    r.http(g, "register: unknown node", "POST", "/register", {"tmux_pane": c_pane, "node": "elsewhere"})
    r.http(g, "register C: prefix and submit key", "POST", "/register",
           {"tmux_pane": c_pane, "requested_user": "civet", "flavor": "generic", "message_prefix": ">> ", "submit_key": "Enter"})
    r.http(g, "register: rename C to a free handle", "POST", "/register", {"tmux_pane": c_pane, "requested_user": "gecko"})
    r.http(g, "register: pane already holds another handle", "POST", "/register", {"tmux_pane": c_pane, "requested_user": "tapir"})

    g = "validation (422 bodies)"
    r.http(g, "register: missing tmux_pane", "POST", "/register", {"model": "x"})
    r.http(g, "register: extra field", "POST", "/register", {"tmux_pane": a_pane, "bogus": 1})
    r.http(g, "register: empty tmux_pane", "POST", "/register", {"tmux_pane": ""})
    r.http(g, "register: wrong type", "POST", "/register", {"tmux_pane": 7})
    r.http(g, "register: body is a list", "POST", "/register", [1])
    r.http(g, "send: empty content, reply_to 0", "POST", "/send", {"tmux_pane": a_pane, "recipient": "tapir", "content": "", "reply_to": 0})
    r.http(g, "send: reply_to as numeric string, bad bool", "POST", "/send",
           {"tmux_pane": a_pane, "recipient": "owner", "content": "x", "reply_to": "abc", "pane_verified": "maybe"})
    r.http(g, "status: text too long", "POST", "/status", {"tmux_pane": a_pane, "text": "x" * 201})
    r.http(g, "tasks: missing title, bad list", "POST", "/tasks", {"depends_on": "3", "attachments": None})
    r.http(g, "tasks: bad status literal", "PATCH", "/tasks/1", {"status": "closed"})
    r.http(g, "tasks: non-numeric id", "PATCH", "/tasks/abc", {"status": "open"})
    r.http(g, "messages: non-numeric limit", "GET", "/messages?limit=abc")
    status, _, _ = r.hub.call("POST", "/register", b"{not json")
    r.step(g, "register: invalid JSON (status only)", {"status": status})

    g = "recipients"
    r.http(g, "GET /recipients", "GET", "/recipients")
    r.http(g, "GET /recipients?include_retired_sessions=true", "GET", "/recipients?include_retired_sessions=true")
    r.http(g, "whoami by pane", "GET", f"/whoami?tmux_pane={a_pane.replace('%', '%25')}")
    r.http(g, "whoami by session id", "GET", "/whoami?agent_id=sess-a")
    r.http(g, "whoami: unregistered pane", "GET", f"/whoami?tmux_pane={d_pane.replace('%', '%25')}")
    r.http(g, "whoami: pane the CLI says it is not in", "GET", f"/whoami?tmux_pane={b_pane.replace('%', '%25')}&pane_verified=false")
    r.http(g, "whoami: unknown session, verified pane adopts it", "GET",
           f"/whoami?tmux_pane={b_pane.replace('%', '%25')}&agent_id=sess-b&pane_verified=true")
    r.http(g, "whoami: second unknown session on that pane is refused", "GET",
           f"/whoami?tmux_pane={b_pane.replace('%', '%25')}&agent_id=sess-b2&pane_verified=true")

    g = "send and delivery"
    r.http(g, "send A to B with context", "POST", "/send",
           {"tmux_pane": a_pane, "recipient": "tapir", "content": "hello from the compat run", "context": "compat"})
    r.screen(g, "pane B shows the pasted message", b_pane)
    r.http(g, "send B to A by session id, reply_to 1, multi-line", "POST", "/send",
           {"agent_id": "sess-b", "recipient": A, "content": "line one\nline two: ünïcödé ✓", "reply_to": 1})
    r.screen(g, "pane A shows the reply note and both lines", a_pane)
    r.http(g, "send to C: prefix and Enter submit key", "POST", "/send", {"tmux_pane": a_pane, "recipient": "gecko", "content": "prefixed"})
    r.screen(g, "pane C shows the prefix", c_pane)
    r.http(g, "send to owner (recorded, no pane)", "POST", "/send", {"tmux_pane": a_pane, "recipient": "owner", "content": "for the human"})
    r.http(g, "send to an unregistered recipient", "POST", "/send", {"tmux_pane": a_pane, "recipient": "nobody", "content": "x"})
    r.http(g, "send from an unregistered pane", "POST", "/send", {"tmux_pane": d_pane, "recipient": "tapir", "content": "x"})
    r.http(g, "send with no pane and no session", "POST", "/send", {"recipient": "tapir", "content": "x"})
    r.http(g, "send replying to a missing message", "POST", "/send", {"tmux_pane": a_pane, "recipient": "tapir", "content": "x", "reply_to": 999})
    r.http(g, "send to queen: of an unknown team", "POST", "/send", {"tmux_pane": a_pane, "recipient": "queen:nope", "content": "x"})

    g = "recipient offline"
    shell = r.tmux.window("env PS1='$ ' bash --norc --noprofile")
    r.http(g, "register D in a pane running a bare shell", "POST", "/register", {"tmux_pane": shell, "requested_user": "newt"})
    r.http(g, "send to a bare shell is refused", "POST", "/send", {"tmux_pane": a_pane, "recipient": "newt", "content": "do not type this"})
    r.screen(g, "nothing was typed into the shell", shell)
    r.tmux.run("kill-pane", "-t", b_pane)
    r.http(g, "send to a pane that is gone", "POST", "/send", {"tmux_pane": a_pane, "recipient": "tapir", "content": "anyone there"})
    r.http(g, "GET /recipients shows why each is offline", "GET", "/recipients")
    r.http(g, "requesting an offline handle from a new pane reclaims it", "POST", "/register",
           {"tmux_pane": d_pane, "requested_user": "tapir", "agent_id": "sess-b"})
    r.http(g, "send to the reclaimed handle is delivered", "POST", "/send", {"tmux_pane": a_pane, "recipient": "tapir", "content": "welcome back"})
    r.screen(g, "the new pane shows it", d_pane)
    prompt = r.tmux.window(f"sh -c 'printf \"{TRUST_SCREEN}\"; exec cat'")
    r.http(g, "register E in a pane showing a trust prompt", "POST", "/register", {"tmux_pane": prompt, "requested_user": "ibis"})
    r.http(g, "send to a pane at a trust prompt is not pasted", "POST", "/send", {"tmux_pane": a_pane, "recipient": "ibis", "content": "would answer the prompt"})
    r.screen(g, "the prompt pane is unchanged", prompt)

    g = "messages"
    r.http(g, "GET /messages", "GET", "/messages")
    r.http(g, "GET /messages?user=tapir&limit=2", "GET", "/messages?user=tapir&limit=2")
    r.http(g, "GET /messages?id=2 (has reply preview)", "GET", "/messages?id=2")
    r.http(g, "GET /messages?id=999", "GET", "/messages?id=999")

    g = "status"
    r.http(g, "POST /status", "POST", "/status", {"tmux_pane": a_pane, "text": "  testing   #12 "})
    r.http(g, "POST /status: only spaces", "POST", "/status", {"tmux_pane": a_pane, "text": "   "})
    r.http(g, "POST /status from an unregistered pane", "POST", "/status", {"tmux_pane": "%77", "text": "x"})

    g = "tasks"
    r.http(g, "create: owner, no assignee", "POST", "/tasks", {"title": "  first task ", "description": "do it"})
    r.http(g, "create: assigned to A by B (notice is delivered)", "POST", "/tasks",
           {"tmux_pane": d_pane, "title": "second", "assignee": A, "depends_on": [1, 1]})
    r.screen(g, "pane A shows the task notice", a_pane)
    r.http(g, "create: owner assigns an offline agent (task still made)", "POST", "/tasks", {"title": "third", "assignee": "newt"})
    r.http(g, "create: unknown dependency", "POST", "/tasks", {"title": "x", "depends_on": [42]})
    r.http(g, "create: unregistered assignee", "POST", "/tasks", {"title": "x", "assignee": "nobody"})
    r.http(g, "create: unknown team", "POST", "/tasks", {"title": "x", "team_id": 5})
    r.http(g, "create: blank title", "POST", "/tasks", {"title": "   "})
    r.http(g, "create: unknown attachment", "POST", "/tasks", {"title": "x", "attachments": ["nope.png"]})
    r.http(g, "create: acting agent not registered", "POST", "/tasks", {"title": "x", "tmux_pane": "%77"})
    r.http(g, "GET /tasks", "GET", "/tasks")
    r.http(g, "update: pick up with a worktree", "PATCH", "/tasks/1",
           {"tmux_pane": a_pane, "status": "picked_up", "worktree": "/tmp/wt"})
    r.http(g, "update: done without a note is refused", "PATCH", "/tasks/1", {"status": "done"})
    r.http(g, "update: done with a note", "PATCH", "/tasks/1", {"status": "done", "note": " ran the tests "})
    r.http(g, "update: reassign (notice goes to the new assignee)", "PATCH", "/tasks/1", {"assignee": "tapir", "title": " renamed "})
    r.screen(g, "pane of the new assignee shows the notice", d_pane)
    r.http(g, "update: clear description, worktree and assignee", "PATCH", "/tasks/1", {"description": "  ", "worktree": None, "assignee": None})
    r.http(g, "update: depend on itself", "PATCH", "/tasks/2", {"depends_on": [2]})
    r.http(g, "update: dependency cycle", "PATCH", "/tasks/1", {"depends_on": [2]})
    r.http(g, "update: set dependencies", "PATCH", "/tasks/3", {"depends_on": [2, 1]})
    r.http(g, "update: unknown task", "PATCH", "/tasks/99", {"status": "open"})
    r.http(g, "update: unregistered assignee", "PATCH", "/tasks/2", {"assignee": "nobody"})
    r.http(g, "update: blank title", "PATCH", "/tasks/2", {"title": "  "})
    r.http(g, "GET /tasks after updates", "GET", "/tasks")

    g = "dashboard state"
    _, state = r.http(g, "GET /api/state (whole body)", "GET", "/api/state")
    r.step(g, "/api/state key sets", {
        "top": sorted(state), "recipient": sorted(state["recipients"][0]), "message": sorted(state["messages"][0]),
        "task": sorted(state["tasks"][0]), "node": sorted(state["nodes"][0]),
    })
    r.http(g, "GET /api/state?limit=2", "GET", "/api/state?limit=2")
    r.http(g, f"GET /api/peek/{'{'}C{'}'} (extra feature)", "GET", "/api/peek/gecko")
    r.http(g, "GET /api/peek of an unknown agent", "GET", "/api/peek/nobody")

    g = "static and errors"
    status, page, headers = r.hub.call("GET", "/", raw=True)
    r.step(g, "GET / (page bytes, cache header)", {"status": status, "sha": hashlib.sha256(page).hexdigest(),
                                                   "versioned": len(re.findall(rb"/static/portal\.(?:js|css)\?v=[0-9a-f]{16}", page)),
                                                   "cache": headers.get("cache-control"), "type": headers.get("content-type")})
    for name in ("portal.js", "portal.css", "icon.svg", "icon-192.png", "manifest.webmanifest"):
        status, data, headers = r.hub.call("GET", f"/static/{name}", raw=True)
        r.step(g, f"GET /static/{name} (bytes)", {"status": status, "sha": hashlib.sha256(data).hexdigest()})
        r.step(g, f"GET /static/{name} (content-type)", headers.get("content-type"))
    r.http(g, "GET /static/missing.js", "GET", "/static/missing.js")
    r.http(g, "GET /nope", "GET", "/nope")
    r.http(g, "DELETE /send (wrong method)", "DELETE", "/send")
    r.http(g, "forwarded request without identity", "GET", "/recipients", headers={"X-Forwarded-For": "10.0.0.1"})
    r.http(g, "unknown bearer token", "GET", "/recipients", headers={"Authorization": "Bearer nope"})
    r.http(g, "/health needs no identity", "GET", "/health", headers={"X-Forwarded-For": "10.0.0.1"})

    g = "database after the run"
    r.hub.stop()
    with sqlite3.connect(f"file:{r.hub.db}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        for table, order in (("messages", "id"), ("recipients", "user_id"), ("tasks", "id"), ("task_deps", "task_id, depends_on"),
                             ("summaries", "id")):
            rows = [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY {order}")]
            r.step(g, f"rows of {table}", rows)
        schema = sorted((row["type"], row["name"], re.sub(r"\s+", " ", row["sql"] or "")) for row in conn.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'messages_fts_%' AND name NOT LIKE 'sqlite_%'"))
        r.step(g, "schema (sqlite_master)", schema)
        indexed = conn.execute("SELECT COUNT(*) FROM messages_fts_docsize").fetchone()[0]
        r.step(g, "search index has a row per message", indexed == conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0])
    conn.close()


def real_db(py: Hub, rs: Hub) -> list[tuple[str, str, object, object]]:
    """Read-only routes on two copies of a real database. Counts only."""
    out = []
    for name, path in (("GET /recipients", "/recipients"), ("GET /messages?limit=500", "/messages?limit=500"),
                       ("GET /tasks", "/tasks"), ("GET /api/state", "/api/state")):
        sides = []
        for hub in (py, rs):
            status, body, _ = hub.call("GET", path)
            names = {str(hub.db.parent): "<work>", hub.db.name: "<db>"}
            sides.append(normal({"status": status, "body": body}, names))
        out.append(("real database copy", name, *sides))
        if path == "/api/state":
            # The activity monitor is not cloned; compare the rest without it.
            for side in sides:
                for rec in side["body"]["recipients"]:
                    rec.pop("activity", None)
            out.append(("real database copy", "GET /api/state without `activity`", *json.loads(json.dumps(sides))))
    return out


def differences(a, b, path="") -> list[str]:
    """Paths where two JSON values differ."""
    if type(a) is not type(b):
        return [f"{path or '.'}: {type(a).__name__} vs {type(b).__name__}"]
    if isinstance(a, dict):
        found = [f"{path}.{k}: only in {'python' if k in a else 'rust'}" for k in sorted(set(a) ^ set(b))]
        return found + [d for k in sorted(set(a) & set(b)) for d in differences(a[k], b[k], f"{path}.{k}")]
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{path}: {len(a)} vs {len(b)} items"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path or '.'}: {str(a)[:70]!r} vs {str(b)[:70]!r}"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=SCRATCH / "compat")
    parser.add_argument("--real-db", type=Path, help="a COPY of a real database; never the live one")
    parser.add_argument("--node", default="karans-linux", help="node name the real database's agents are on")
    args = parser.parse_args()
    work = args.out / f"run-{os.getpid()}"
    work.mkdir(parents=True)
    runs, tmuxes = {}, []
    try:
        for kind in ("python", "rust"):
            tmux = Tmux(f"rustclone-{kind[:2]}-{os.getpid()}", work)
            tmuxes.append(tmux)
            (work / kind).mkdir()
            run = Run(Hub(kind, work / kind / "db.sqlite", tmux), tmux)
            try:
                scenarios(run)
            finally:
                run.hub.stop()
            runs[kind] = run
        rows = [(g, n, p, r) for (g, n, p), (_, _, r) in zip(runs["python"].normalized(), runs["rust"].normalized(), strict=True)]
        if args.real_db:
            assert ".agent-swarm" not in str(args.real_db.resolve()), "give a copy, never the live database"
            hubs = []
            try:
                for kind, tmux in zip(("python", "rust"), tmuxes):
                    copy_db(args.real_db, work / kind / "real.sqlite")
                    hubs.append(Hub(kind, work / kind / "real.sqlite", tmux, node=args.node))
                time.sleep(2)  # the Python monitor's one tick at start
                rows += real_db(*hubs)
            finally:
                for hub in hubs:
                    hub.stop()
                    # The copies hold real message text: do not leave them behind.
                    for leftover in hub.db.parent.glob("real.sqlite*"):
                        leftover.unlink()
    finally:
        for tmux in tmuxes:
            tmux.kill()
    groups: dict[str, list[int]] = {}
    failed = []
    for group, name, py, rs in rows:
        diff = differences(py, rs)
        groups.setdefault(group, [0, 0])[0 if not diff else 1] += 1
        if diff:
            failed.append((group, name, diff))
    print("| Scenario group | Steps | Same | Different |\n|---|---:|---:|---:|")
    for group, (same, different) in groups.items():
        print(f"| {group} | {same + different} | {same} | {different} |")
    total = sum(s + d for s, d in groups.values())
    print(f"| **total** | {total} | {total - len(failed)} | {len(failed)} |")
    for group, name, diff in failed:
        print(f"\nDIFFERENT: {group} / {name}")
        for line in diff[:8]:
            print(f"  {line}")
        if len(diff) > 8:
            print(f"  ... and {len(diff) - 8} more paths")
    # The real-database rows hold message text: keep only the synthetic ones.
    synthetic = [{"group": g, "step": n, "python": p, "rust": r} for g, n, p, r in rows if g != "real database copy"]
    (work / "steps.json").write_text(json.dumps(synthetic, indent=1, ensure_ascii=False))
    print(f"\nsteps: {work / 'steps.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
