# Rust clone of the hub core

An experiment: the core of the Buzz hub (`agent_swarm/server.py`) written again in Rust, to see what is better and what is worse. The findings are in [REPORT.md](REPORT.md).

- `buzz-hub/` is the Rust hub (axum, tokio, rusqlite with SQLite built in).
- `compat/` holds the Python scripts that start both hubs and compare them.

The Rust hub reads and writes the same SQLite file format as the Python hub. Run it on a copy of a database, or on a new file. Do not point it at a database a Python hub is using.

## Build

```bash
export CARGO_TARGET_DIR=/mnt/storage/karan-scratchpad/rust-hub/target   # keep build output off the root disk
cargo build --release --manifest-path rust/buzz-hub/Cargo.toml
```

The binary is `$CARGO_TARGET_DIR/release/buzz-hub`. It holds the dashboard files, so it needs nothing else at run time except `tmux`.

`--features mimalloc` builds with a faster allocator that uses more memory. The report has numbers for both.

## Run

```bash
$CARGO_TARGET_DIR/release/buzz-hub --db /path/to/copy.sqlite --port 8799
```

| Option | Meaning |
|---|---|
| `--db PATH` | SQLite file. Created if missing. Also `AGENT_SWARM_DB`. |
| `--port N` | Default 8766. Also `AGENT_SWARM_PORT`. The live hub uses 8765: pick another. |
| `--host H` | Default `127.0.0.1`. |
| `--assets DIR` | Read `portal.html` and `static/` from this folder (for example `agent_swarm`) instead of the built-in copy. |

It reads `AGENT_SWARM_NODE` (default: the short host name), `AGENT_SWARM_TRUST_LOOPBACK`, `AGENT_SWARM_OWNER_LOGINS`, `AGENT_SWARM_SPAWN_DIRS` and `AGENT_SWARM_SUBMIT_VERIFY_DELAY` as the Python hub does. It never reads or writes `~/.agent-swarm/`.

The existing `buzz` CLI works against it: set `AGENT_SWARM_URL=http://127.0.0.1:8799`.

## Compare the two hubs

The scripts need a Python environment with the repo's dependencies. This makes one outside the repo:

```bash
export UV_PROJECT_ENVIRONMENT=/mnt/storage/karan-scratchpad/rust-hub/venv
uv sync --frozen --python 3.13
PY=$UV_PROJECT_ENVIRONMENT/bin/python
```

Make a private copy of a real database. The source is opened read-only:

```bash
$PY -c "import sys; sys.path.insert(0, 'rust/compat'); from hubs import copy_db; from pathlib import Path; \
copy_db(Path.home() / '.agent-swarm/db.sqlite', Path('/mnt/storage/karan-scratchpad/rust-hub/db-copy.sqlite'))"
```

Then, from the repository root:

```bash
COPY=/mnt/storage/karan-scratchpad/rust-hub/db-copy.sqlite
$PY rust/compat/run_compat.py --real-db $COPY     # same scenarios on both hubs; prints the table
$PY rust/compat/cli_check.py                      # the real buzz CLI, run inside tmux panes, against both
$PY rust/compat/dashboard_smoke.py --db $COPY     # the dashboard in headless Chrome, from both
$PY rust/compat/bench.py --db $COPY --seconds 10  # latency, throughput, memory, cold start
$PY rust/compat/loc.py                            # lines of code for the cloned scope
```

`bench.py` prints where it wrote `results.json`. To get one table from several runs (for example one with `--order python,rust` and one with `--order rust,python`):

```bash
$PY rust/compat/bench_table.py RUN1/results.json RUN2/results.json
```

`BUZZ_HUB_BIN=/path/to/buzz-hub` picks another Rust binary. `RUST_HUB_SCRATCH` moves the working folder (default `/mnt/storage/karan-scratchpad/rust-hub`).

### What the scripts do to stay safe

- Each hub listens on a free port chosen at run time, never 8765. Before any request, the script checks that the listener's PID is the process it started. Hubs are stopped by PID.
- Each hub talks to its own tmux server, `tmux -L rustclone-...`, through a `tmux` wrapper placed first on its `PATH`, with `TMUX` unset. The default tmux server is never used. The server is killed at the end.
- The Python hub gets its own `AGENT_SWARM_DB` and `AGENT_SWARM_CONFIG`, so it does not touch `~/.agent-swarm/`.
- Copies of a real database are deleted after each run. Saved step files hold only the made-up scenario data.

## Layout of the crate

| File | What it holds |
|---|---|
| `src/main.rs` | Arguments, routes, the auth layer, static files, request models. |
| `src/api.rs` | The route logic: register, caller resolution, send and delivery, tasks, state. |
| `src/db.rs` | Schema, migrations of older files, and every SQL statement. |
| `src/tmux.rs` | The tmux commands: snapshot, resolve, capture, paste and submit. |
| `src/validate.rs` | Request checks that answer in FastAPI's 422 format. |
| `src/names.rs` | The handle pool and handle checks. |
| `src/schema.sql`, `pool.txt`, `brief.txt` | Text copied from `db.py`, `names.py` and `server.py`. If the Python side changes, copy again; `run_compat.py` fails when they drift. |
