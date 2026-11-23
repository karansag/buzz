"""The real Python hub's read routes, with optional frozen state metadata."""
from __future__ import annotations

import argparse
import contextvars
import json
import time
from pathlib import Path

import uvicorn
from starlette.responses import JSONResponse

from agent_swarm import db, message_index, search_query, server, tmux
from bench.db_scale import QUERIES

clock = time.perf_counter_ns
phases = contextvars.ContextVar("bench_phases", default=None)


def timed(f, *args):
    timing = phases.get()
    if timing is None:
        return f(*args)
    start = clock()
    try:
        return f(*args)
    finally:
        timing["db"] += clock() - start


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def __iter__(self):
        return self

    def __next__(self):
        return timed(next, self.cursor)

    def fetchone(self):
        return timed(self.cursor.fetchone)

    def fetchall(self):
        return timed(self.cursor.fetchall)

    def __getattr__(self, name):
        return getattr(self.cursor, name)


def instrument(app, direct_json=False):
    native_execute = db.Connections.execute
    native_render = JSONResponse.render

    def execute(conn, statement, params=()):
        cursor = timed(native_execute, conn, statement, params)
        return Cursor(cursor) if phases.get() is not None else cursor

    def render(self, content):
        start = clock()
        body = native_render(self, content)
        if (timing := phases.get()) is not None:
            timing["encode"] += clock() - start
        return body

    db.Connections.execute = execute
    JSONResponse.render = render

    @app.middleware("http")
    async def timing_header(request, call_next):
        timing = {"db": 0, "build": 0, "encode": 0}
        token = phases.set(timing)
        start = clock()
        try:
            response = await call_next(request)
            timing["total"] = clock() - start
            response.headers["Server-Timing"] = ", ".join(
                f"{key};dur={value / 1e6:.4f}" for key, value in timing.items()
            )
            return response
        finally:
            phases.reset(token)

    for route in app.routes:
        if not getattr(route, "path", "").startswith("/api/") or not hasattr(route, "dependant"):
            continue
        call = route.dependant.call

        def wrap(*args, _call=call, **kwargs):
            start = clock()
            value = _call(*args, **kwargs)
            timing = phases.get()
            timing["build"] += clock() - start
            # These benchmark handlers already return JSON primitives.
            return JSONResponse(value) if direct_json else value

        # FastAPI records the callable in its dependant at route construction,
        # retaining the original signature used to resolve request arguments.
        route.dependant.call = wrap


def snapshot(app):
    run_state = next(r.endpoint for r in app.routes if getattr(r, "path", "") == "/api/state")
    value = run_state(limit=300)
    value.pop("messages")
    return value


def prepare(path, fixture, method):
    conn = db.connect(path)
    if method == "prep":
        message_index.ensure(conn, path)
    else:
        app = server.create_app(path, monitor=False)
        state = snapshot(app)
        plans = {}
        for text in QUERIES:
            q = search_query.parse(text)
            exact, args = search_query.to_sql(q)
            groups = [c for c in q.clauses if all(len(t.text) >= 3 for t in c)]
            plans[text] = {
                "exact": exact, "args": args, "terms": q.highlight(),
                "groups": [[message_index._trigrams(t.text) for t in c] for c in groups],
                "fts": " AND ".join(
                    "(" + " OR ".join(message_index._quote(t.text) for t in c) + ")"
                    for c in groups
                ),
            }
        fold = {chr(i): chr(i).casefold() for i in range(128, 0x110000)
                if chr(i).casefold() != chr(i)}
        with fixture.open("w", encoding="utf-8") as out:
            json.dump({"state": state, "plans": plans, "fold": fold}, out, ensure_ascii=False)
    print(conn.execute("SELECT sqlite_version(), (SELECT COUNT(*) FROM messages)").fetchone()[:])
    conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prep", "fixture", "serve", "full"))
    parser.add_argument("db", type=Path)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--port", type=int, default=8811)
    parser.add_argument("--sample-monitor", action="store_true")
    parser.add_argument("--orjson", action="store_true")
    parser.add_argument("--direct-json", action="store_true")
    args = parser.parse_args()

    # Without the explicit synthetic tmux setup the benchmark must not
    # inspect, migrate or touch the live machine's panes.
    if not args.sample_monitor:
        tmux.pane_table = lambda: {}
        tmux.server_id = lambda: None
        tmux.server_start_time = lambda: None

    if args.mode in {"prep", "fixture"}:
        prepare(args.db, args.fixture, args.mode)
        return

    app = server.create_app(args.db, monitor=args.sample_monitor, trust_loopback=True)
    if args.mode == "serve":
        fixture = json.loads(args.fixture.read_text())["state"]
        conn = db.connect(args.db)
        route = next(r for r in app.routes if getattr(r, "path", "") == "/api/state")

        def frozen_state(limit=300, _=None):
            messages = db.fetch_messages(conn, None, limit)
            return {**fixture, "messages": messages[::-1]}

        route.dependant.call = frozen_state

    if args.orjson:
        import orjson

        # Timing covers the response encoder only. FastAPI's jsonable_encoder
        # still traverses the response first, as with its default JSONResponse.
        JSONResponse.render = lambda self, content: orjson.dumps(content)

    instrument(app, direct_json=args.direct_json)
    uvicorn.run(app, host="127.0.0.1", port=args.port, proxy_headers=False, access_log=False)


if __name__ == "__main__":
    main()
