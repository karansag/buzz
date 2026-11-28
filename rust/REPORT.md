# Rust clone of the hub core: report

Date: 2026-11-27. Branch `rust-hub`. This is an experiment. It is not meant to be merged.

## Summary

- The Rust hub answers the cloned routes the same as the Python hub: 123 of 124 compared steps are equal. The one difference is expected (no activity monitor).
- The real `buzz` CLI and the existing dashboard work against it without changes.
- Rust is much faster when many clients ask at once (20 to 35 times more requests per second on the large read routes). With one client it is 1.2 to 2.2 times faster.
- Sending a message takes the same time in both. tmux sets that time, not the hub.
- Rust uses less memory when idle (10 MB against 62 MB) and more after heavy load (204 to 301 MB against about 102 MB).
- The cloned part is about 20% of the Python code. It needed about 19% more lines in Rust.
- Recommendation: keep Python. Details and the uncertainty are at the end.

## What was cloned

| Area | State |
|---|---|
| SQLite schema | Same `CREATE` text. Same column upgrades for older files. Opens a copy of the live database and makes new files. |
| `GET /health` | Cloned. |
| `POST /register` | Cloned: pool pick, requested handle, reclaim of an offline handle, rename, pane tag, protocol brief. |
| `GET /recipients`, `GET /whoami` | Cloned. |
| `POST /send` | Cloned: caller from `tmux_pane` or session id, owner target, `queen:` target, reply link, offline checks, real tmux delivery, `delivered` / `failed` rows. |
| `GET /messages` | Cloned: `user`, `limit`, `id` filters. |
| `POST /status` | Cloned. |
| `GET /tasks`, `POST /tasks`, `PATCH /tasks/{id}` | Cloned, with the assignment notices and the close-note rule. |
| `GET /api/state` | Cloned. `activity` is always `unknown` and `tabs` is always empty. |
| Dashboard files | Served from inside the binary, with the same versioned URLs and ETag answers. |
| Auth layer | Cloned: loopback is the owner, a bearer token is a node, an unknown token gets 401. |
| Request checks | FastAPI's 422 bodies are written by hand in `validate.rs`. |
| tmux delivery | Same commands as `tmux.py`: buffer load, bracketed paste, submit key, check of the composer. |
| Extra: `GET /api/peek/{user}` | Added after the core passed. Cost: 13 lines in `api.rs`, about 10 in `main.rs`. It reuses the pane capture that delivery needs. |

## What was not cloned

Remote nodes (the node routes and the relay), teams, queens and boards as routes (the tables exist; `queen:` targets do work), handoff, model switch, restart, retire, snapshots and restore, the activity monitor, attachments, notifications, digest, search, chats view routes, spawn.

`GET /api/spawn-options` answers with an empty list. The dashboard asks for it on load, and a 404 put an error in the browser console.

Other gaps inside the cloned routes:

- No board hint footer on delivered messages and no `client_id` on send.
- Requests with attachments are refused.
- Python's `str.casefold()` is replaced by the `caseless` crate. Not compared on non-ASCII text.
- No `.pre-fts` backup before the search index is first built.
- No read or write of `node.toml`. The node name comes from `AGENT_SWARM_NODE` or the host name.
- No legacy pane migration.

## Compatibility

Method: `rust/compat/run_compat.py` starts each hub on its own new database and its own isolated tmux server (`tmux -L rustclone-...`). It sends the same requests to both. It replaces values that must differ (ports, times, pane ids, the picked handle) and compares the rest, including key order. It also compares the final database: schema text and every row. With `--real-db` it then compares read routes on two copies of the live database.

| Scenario group | Steps | Same | Different |
|---|---:|---:|---:|
| health | 1 | 1 | 0 |
| register | 13 | 13 | 0 |
| validation (422 bodies) | 13 | 13 | 0 |
| recipients | 8 | 8 | 0 |
| send and delivery | 12 | 12 | 0 |
| recipient offline | 11 | 11 | 0 |
| messages | 4 | 4 | 0 |
| status | 3 | 3 | 0 |
| tasks | 24 | 24 | 0 |
| dashboard state | 5 | 5 | 0 |
| static and errors | 17 | 17 | 0 |
| database after the run | 7 | 7 | 0 |
| known difference | 1 | 0 | 1 |
| real database copy (61,648 messages, 64 agents, 578 tasks) | 5 | 5 | 0 |
| **total** | 124 | 123 | 1 |

The known difference: after two monitor ticks Python reports `activity: working` for a live agent. Rust has no monitor and reports `unknown`.

Other checks:

| Check | Result |
|---|---|
| Real tmux delivery, both hubs | The text arrives in a pane that runs `cat`, on an isolated tmux server. Captured pane text is equal for both hubs. Part of "send and delivery" above. |
| Real `buzz` CLI in tmux panes (`cli_check.py`) | 16 of 16 steps equal: exit codes, output, and the text that reached the other pane. |
| Dashboard in headless Chrome (`dashboard_smoke.py`), copy of the live database | Both hubs: every request 200, no page or console errors, same views. Python drew 2,110 elements and Rust 2,101 (text length 65,542 and 65,491). The cause of that gap was not checked. The monitor fields are the likely cause. |
| Repeat runs | The synthetic scenarios gave the same result in 5 of 5 runs after the harness fixes. A later independent rerun gave 123 of 124 again. |

Limits of this evidence:

- The scenarios were written by the same author as the clone. They cover the paths that author thought of.
- Node-token paths past the 401 check are not tested.
- No test of races between concurrent writers.
- The Python hub in the tests ran FastAPI 0.141.1 and uvicorn 0.52.4 from the lock file. The live hub runs FastAPI 0.165.0 and uvicorn 0.54.0. Both use SQLite 3.47.1. Rust bundles SQLite 3.46.

## Measurements

Machine: Intel i7-8700K (6 cores, 12 threads), 62 GB RAM, Linux 6.8, tmux 3.4, rustc 1.94.1, Python 3.13.5. The machine was busy with other work the whole time: load average 6 to 12 during these runs. Treat small gaps as noise.

Method: `rust/compat/bench.py` on copies of the live database (224 MB). One hub at a time. The load client is Python threads, one keep-alive connection each, closed loop, 10 seconds per case. Each cell is the mean of two runs, one with Python first and one with Rust first. The mimalloc column is one run. The largest gap between two runs of the same hub in any cell was 55%. Failed requests in all runs: 0. `/send` delivers to 16 real panes that run `cat`.

Response sizes: `/api/state` 1.72 MB, `/tasks` 1.20 MB, `/messages` 52 KB, `/messages?user=...&limit=300` 330 KB.

| Measure | Python | Rust | Rust + mimalloc |
|---|---:|---:|---:|
| Cold start to first `/health` (ms), median of 5 | 417.9 | 32.6 | 34.4 |
| Memory (RSS) 3 s after start (MB) | 62.3 | 10.2 | 17.7 |
| Memory (RSS) after all load runs (MB) | 103.2 | 260.8 | 410.6 |
| Peak memory (RSS) (MB) | 180.4 | 261.0 | 544.7 |
| `GET /api/state`, 1 client: p50 / p95 (ms) | 28.0 / 40.3 | 20.8 / 30.4 | 18.2 / 24.8 |
| `GET /api/state`, 1 client: requests/s | 33.6 | 45.1 | 51.7 |
| `GET /api/state`, 1 client: hub CPU per request (ms) | 19.94 | 12.41 | 9.81 |
| `GET /api/state`, 16 clients: p50 / p95 (ms) | 1,311.7 / 2,180.7 | 67.5 / 95.9 | 68.1 / 110.0 |
| `GET /api/state`, 16 clients: requests/s | 9.9 | 224.3 | 216.6 |
| `GET /api/state`, 16 clients: hub CPU per request (ms) | 264.22 | 22.82 | 19.08 |
| `GET /messages`, 1 client: p50 / p95 (ms) | 1.2 / 1.7 | 0.5 / 0.8 | 0.5 / 0.8 |
| `GET /messages`, 1 client: requests/s | 787.7 | 1,709.8 | 1,853.6 |
| `GET /messages`, 1 client: hub CPU per request (ms) | 1.16 | 0.42 | 0.36 |
| `GET /messages`, 16 clients: p50 / p95 (ms) | 62.5 / 78.4 | 2.4 / 5.8 | 2.3 / 4.7 |
| `GET /messages`, 16 clients: requests/s | 254.4 | 5,656.2 | 6,196.8 |
| `GET /messages`, 16 clients: hub CPU per request (ms) | 9.88 | 0.56 | 0.45 |
| `GET /messages?user=<busiest>&limit=300`, 1 client: p50 / p95 (ms) | 121.1 / 147.3 | 72.6 / 98.1 | 70.1 / 95.1 |
| `GET /messages?user=<busiest>&limit=300`, 1 client: requests/s | 7.9 | 13.0 | 13.3 |
| `GET /messages?user=<busiest>&limit=300`, 1 client: hub CPU per request (ms) | 126.20 | 76.31 | 74.56 |
| `GET /messages?user=<busiest>&limit=300`, 16 clients: p50 / p95 (ms) | 1,112.3 / 1,300.3 | 1,463.7 / 1,609.4 | 1,337.7 / 1,424.2 |
| `GET /messages?user=<busiest>&limit=300`, 16 clients: requests/s | 12.5 | 9.2 | 10.4 |
| `GET /messages?user=<busiest>&limit=300`, 16 clients: hub CPU per request (ms) | 655.36 | 848.20 | 769.73 |
| `GET /tasks`, 1 client: p50 / p95 (ms) | 6.2 / 10.4 | 5.3 / 8.6 | 3.6 / 5.6 |
| `GET /tasks`, 1 client: requests/s | 146.7 | 174.5 | 255.3 |
| `GET /tasks`, 1 client: hub CPU per request (ms) | 6.73 | 5.54 | 3.72 |
| `GET /tasks`, 16 clients: p50 / p95 (ms) | 609.8 / 724.6 | 17.4 / 31.1 | 16.7 / 26.3 |
| `GET /tasks`, 16 clients: requests/s | 25.3 | 850.6 | 910.9 |
| `GET /tasks`, 16 clients: hub CPU per request (ms) | 104.75 | 8.76 | 8.31 |
| `POST /send`, 1 client: p50 / p95 (ms) | 206.7 / 261.8 | 223.3 / 313.4 | 198.6 / 226.4 |
| `POST /send`, 1 client: requests/s | 4.6 | 4.2 | 4.8 |
| `POST /send`, 1 client: hub CPU per request (ms) | 9.61 | 5.52 | 3.80 |
| `POST /send`, 16 clients: p50 / p95 (ms) | 314.2 / 560.2 | 286.7 / 548.0 | 281.5 / 565.3 |
| `POST /send`, 16 clients: requests/s | 43.2 | 47.0 | 46.5 |
| `POST /send`, 16 clients: hub CPU per request (ms) | 12.92 | 4.21 | 4.05 |

Notes on the table:

- Rust memory after load was 204, 216, 221 and 301 MB in four runs. Python was 100 to 105 MB in four runs.
- The Python client limits the fastest cases. The 5,656 requests/s figure for Rust is a lower bound.
- The Python hub gets slower with 16 clients than with 1 on the large routes (`/api/state`: 33.6 to 9.9 requests/s). The cause was not checked. The interpreter lock is the likely cause.
- The Python hub also runs its monitor loop during the test. The Rust hub has none. The size of that cost was not measured.

Build and size:

| Measure | Python | Rust |
|---|---:|---:|
| Install or build from nothing | `uv sync`, warm download cache: 0.32 s | Clean debug build 15.6 s. Clean release build 57.6 s (163 s of CPU). One earlier clean release build took 150 s under heavier load. Crate downloads not counted. |
| After a one-line edit | Restart the hub: 0.42 s | `cargo check` 0.2 s. Debug build 0.6 s. Release build 8.7 to 11.3 s. |
| Size on disk | venv 42 MB plus the Python runtime 122 MB | One file, 6,570,520 bytes (6.3 MB). Dashboard files inside. Links only to libc, libm, libgcc. |
| Build output folder | none | 783 MB |
| Packages | 29 installed distributions | 99 crates in `Cargo.lock`, 9 direct |

Lines of code, from `rust/compat/loc.py`. Python: only the functions and classes the clone has an equal for, found by name with `ast`. Rust: every line under `src/`. "Code lines" leaves out blank lines and comments. Schema text and the name pool are counted apart as data.

| | All lines | Code lines |
|---|---:|---:|
| Python, cloned scope | 2,830 | 2,298 |
| Rust | 3,139 | 2,742 |
| Ratio | 1.11 | 1.19 |

The cloned scope is 20% of `agent_swarm/*.py` (13,982 lines). The Rust hub has 14 routes. `server.py` has 63 route decorators. `validate.rs` (239 lines) has no Python equal: pydantic does that work there.

## Better in Rust

| Claim | Evidence |
|---|---|
| Many clients at once | Measurements: 16 clients, `/api/state` 224 against 9.9 requests/s, `/tasks` 851 against 25, `/messages` 5,656 against 254. |
| One client, read routes | p50 lower by 15% to 58%: `/api/state` 20.8 against 28.0 ms, `/messages` 0.5 against 1.2 ms, `/tasks` 5.3 against 6.2 ms. The `/tasks` gap is inside the noise. |
| CPU per request | Lower on every case but one: for example `/send` 4.2 to 5.5 ms against 9.6 to 12.9 ms. |
| Cold start | 33 ms against 418 ms. |
| Idle memory | 10 MB against 62 MB. |
| Deploy | One 6.3 MB file with the dashboard inside. Python needs a 42 MB venv and a 122 MB runtime. |
| Whole classes of mistakes stop the build | A missing `None` check or a wrong type is a compile error. Example from this work: a future that held a borrowed request across an `await` did not compile. The message was long and named a trait bound, not the line at fault. |
| `cargo check` after an edit | 0.2 s. It gives type errors for the whole crate without a run. |

## Worse in Rust

| Claim | Evidence |
|---|---|
| Memory after heavy load | 204 to 301 MB against 100 to 105 MB. With mimalloc 411 to 439 MB. The process does not give the memory back. |
| One heavy read with 16 clients | `/messages?user=<busiest>&limit=300`: 9.2 against 12.5 requests/s. The cause was not found. This query is bound by a SQLite scan. |
| Amount of code | 19% more code lines for the same scope. |
| Request checks | 239 lines by hand in `validate.rs` to match FastAPI's 422 bodies. Each new request model needs more. Serde's own errors do not match that format. |
| JSON handling needs care | The first version copied each row through the `json!` macro. `/tasks` was then no faster than Python. Fixed by moving rows (commit `a49a8f6`). Python has no such trap. |
| Allocator choice matters | `MALLOC_ARENA_MAX=2` cut 16-client throughput by half in a trial. mimalloc is faster for one client (`/tasks` p50 3.6 against 5.3 ms) and doubles memory. |
| SQLite access | `rusqlite` is blocking. Each handler runs in `spawn_blocking` with a small connection pool written for this crate, plus a write lock. Rows are read into JSON maps by column, so the compiler does not check column names. Python's `sqlite3` with dict rows is shorter. |
| tmux subprocess code | 286 lines against 289: the same size. Timeouts need `tokio::process`, `kill_on_drop` and a bridge from blocking code back to the runtime. In Python it is `subprocess.run(..., timeout=...)`. |
| Release build wait | 9 to 11 s after each edit, 58 s clean. Python restarts in 0.4 s. Debug builds are 0.6 s, so this cost is for release tests only. |
| Text shared with Python | `schema.sql`, `pool.txt` and `brief.txt` are copies. Two hubs in two languages would need this kept in step by hand. |
| Tests | The crate has no unit tests. All checks are black-box and need the Python hub. 41 of the 42 Python test files import the Python code direct, so the 702 tests do not carry over. |

## Same

| Claim | Evidence |
|---|---|
| Send latency and throughput | `/send` p50 207 against 223 ms with one client, 43 against 47 requests/s with 16. tmux commands and the submit check set the time. |
| Wire format and database content | Compatibility table: 123 of 124 steps, and the final databases are equal row for row. |
| tmux command sequence | Same commands in the same order. Pane text equal in the delivery and CLI checks. |
| Dashboard and CLI | Both work unchanged against either hub. |
| Size of the tmux module | 286 against 289 lines. |

## How hard is the other 80%

This section is an estimate. Nothing in it was built.

- By line count the rest is about four times the cloned part. At the measured ratio that is about 11,000 to 13,000 more lines of Rust.
- Mostly mechanical: teams and boards routes, notifications, digest, search routes, attachments, snapshots. These are SQL plus JSON, like the tasks routes.
- Harder: the activity monitor, handoff, model switch and restart. They read pane text with many regular expressions (`activity.py` 15 uses, `model_switch.py` 21) and drive tmux in timed steps. `boards.py` and `context_usage.py` use look-behind, which the `regex` crate does not have.
- Harder: remote nodes. That is a second HTTP client and server role with tokens and a relay. None of it was tried.
- The 702 Python tests would have to be written again or turned into black-box tests.
- The hub changes often. Each change would cost a release build and hand-written request checks.

## Recommendation

Keep the hub in Python. Do not port it.

Reasons:

1. The speed gain is real, but it is in a case the hub does not seem to have. Rust wins most with 16 clients that each pull megabyte answers. The one path every agent waits on is `/send`, and it is the same speed.
2. If `/api/state` at 28 ms or the 16-client slowdown is a real problem, a smaller answer or a cache in Python is a cheaper fix to try first. This was not tried here.
3. The port would cost an estimated 11,000 or more lines, a new test suite, and slower edits on code that changes often.
4. Memory is better only when idle.

Uncertainty:

- Confidence in "the clone is compatible on the tested paths": high. It is measured.
- Confidence in the speed ratios: medium. The machine was busy and runs differed by up to 55% in one cell. The large ratios (20 times and more) are far outside that noise. The small ones are not.
- Confidence in "keep Python": medium. It rests on a belief that was not measured: that the live hub rarely serves many heavy requests at once. If the live hub does show slow dashboard loads under many agents, that changes the answer. A check of live request counts and latencies would settle it.
- The cost of the other 80% is an estimate from line counts.

A middle path, if the single binary matters: this crate could serve as a read-only dashboard server on a database copy. That was not tested as a product, only as part of this comparison.
