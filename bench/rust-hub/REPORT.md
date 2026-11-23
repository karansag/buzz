# Would a Rust hub be worth it?

**TL;DR. Keep the Python hub for now.** Rust made the biggest response, dashboard state, much faster in a like-for-like read prototype: **64.5 → 7.5 ms** median today and **50.0 → 8.3 ms** at 200k messages. The full Python state handler went from **58.7 → 14.5 ms** with a direct JSON response and `orjson`, with no database or protocol changes. Start there. Under sustained four-reader load optimized Python reached 86–93 reads/sec while Rust reached 151–244, so revisit a small Rust read service if several dashboards or automation clients routinely saturate the hub after the Python change. The monitor and message delivery spend most of their wall time in tmux and would get little from a language change alone.

## What this would feel like

- **Dashboard load and refresh.** The live hub served a 1.61 MB state response in 81 ms median during one extra dashboard-equivalent poll at the real two-second cadence. A faster encoder lowers the latency and CPU for every poll. Reducing the payload helps network and browser time too, which the loopback prototype does not measure.
- **Switching between agent pages.** The default 300-message page went from 23.5 → 7.3 ms today and 19.4 → 7.8 ms at 200k on loopback. The change is most visible when several readers are busy. Actual harness switching, pane creation, and model startup are outside the prototype.
- **Chats and search.** The plain Chats list is already fast. At 200k it went from 13.2 → 8.5 ms. At that size the conversation search for `tpu` went from 74.7 → 65.5 ms, and the common word `the` from 51.5 → 34.3 ms. Both still spend most of the request inside the SQLite API. The browser’s search debounce and network cost are additional.

## Live samples and where the work goes

On karans-linux (i7-8700K, 6 cores / 12 threads), I observed three adjacent 60-second windows on the same live hub PID. The middle window added one read-only GET of `/api/state` every two seconds. Other normal hub traffic continued throughout, so the first and last windows approximate background use rather than true idle. CPU is a percentage of **one** core. RSS excludes tmux children.

| Live window | Hub CPU | Median hub RSS | Added state requests |
|---|---:|---:|---|
| Background, before | 5.6% | 93.9 MiB | 0 |
| Background + one state poller | 5.4% | 93.9 MiB | 30; 81.3 ms p50 / 115.8 ms p95 |
| Background, after | 1.0% | 93.9 MiB | 0 |

Live background activity varied too much to use subtraction as the per-dashboard CPU cost. On the isolated full Python state route, 60 sequential requests consumed 3.71 CPU seconds, or about **3.1% of one core** at one request per two seconds. Direct JSON with `orjson` used 0.87 CPU seconds for the same number of requests, or **0.7% of one core** at that cadence. This estimate excludes actual tmux observations, monitor traffic, and browser work.

Linux denied `py-spy` attachment to the live process (Yama `ptrace_scope=1`, no passwordless `sudo`). I left those settings alone. The following per-operation split comes from instrumentation of the actual Python code in isolation; it is not a live CPU attribution:

| Component | What the isolated measurement showed |
|---|---|
| Full Python state, 1.57 MB in this run | 58.7 ms HTTP median. Handler 10.1 ms, including 6.4 ms in SQLite calls. JSON encoding 17.5 ms; framework work between handler and response, principally FastAPI’s traversal of the nested result, 26.8 ms. The isolated node has no live tmux snapshot. |
| Monitor | 509 ms median tick with 60 local synthetic panes, 12 ticks. Capture calls were 5,958 of 6,340 ms total wall time (94%); pane snapshots another 166 ms (3%). Title/model/color parsing and activity evaluation totalled 65 ms across the run. The hub process used 802 ms CPU in the 12 ticks (67 ms/tick; ~1.3% of a core at a five-second interval). This excludes tmux children and uses steady synthetic output. |
| Local delivery | 199 ms median through the Python API into a synthetic pane (15 sends). tmux paste, delay, submit and verification together took 171 ms median. Snapshot and prompt capture took 14.5 and 7.6 ms median respectively. The DB insert and status update were about 0.17 and 0.07 ms median. |
| Node websocket ingress | 120 synthetic observation frames (24 KB each, 10 screens) processed in ~28.5 ms in-process, about 0.24 ms/frame including the test harness. JSON decode alone took ~0.058 ms median and the observation assignment ~0.002 ms. This omits network latency, peer captures, and real contention. |

The phase timers measure **SQLite API wall time**, including prepare/execute/step/fetch, binding overhead, and the exact-match `casefold` callback. Python's SQLite calls also include SQLite row materialization and any time waiting to resume the interpreter; Rust's row-to-JSON conversion is timed outside the SQLite phase. Neither timer is a pure native-engine CPU counter. The library, query plans, and golden responses are controlled, but the phase difference cannot be assigned entirely to native SQLite or entirely to the GIL.

## HTTP comparison

These are release Rust/axum/rusqlite and Python 3.12/FastAPI/Uvicorn compared on the **same system SQLite 3.45.1**. The live hub uses Python’s bundled SQLite 3.47.1 and is shown separately. The backup has **58,706 messages**, 65 recipients and 546 tasks. The larger copy is a deterministic 200,000-message resample using `bench/db_scale.py` with the trigram index brought up to date. Test copies ran on NVMe in WAL mode, on private loopback listeners. One persistent HTTP client was warmed up first; each endpoint/query had 40 timed requests. Payloads were uncompressed. Times are p50 / p95 in milliseconds.

| Endpoint | 58.7k Python | 58.7k Rust | 200k Python | 200k Rust |
|---|---:|---:|---:|---:|
| State | 64.5 / 111.5 | 7.5 / 11.9 | 50.0 / 85.4 | 8.3 / 13.4 |
| Chats, plain | 13.1 / 16.5 | 4.2 / 6.9 | 13.2 / 22.3 | 8.5 / 15.7 |
| Conversation, 300 messages | 23.5 / 37.0 | 7.3 / 12.8 | 19.4 / 31.2 | 7.8 / 13.2 |
| Search, common `the` | 23.3 / 75.4 | 10.1 / 39.2 | 51.5 / 178.7 | 34.3 / 126.7 |
| Search, `tpu` | 37.4 / 45.9 | 22.9 / 33.3 | 74.7 / 110.1 | 65.5 / 93.3 |
| Search, `snowball eval` | 34.6 / 55.0 | 21.8 / 34.8 | 88.4 / 129.9 | 74.6 / 100.6 |
| Search, `"model switch"` | 18.4 / 23.2 | 11.7 / 18.4 | 38.0 / 56.6 | 37.0 / 59.8 |
| Search, no-match `zqxjkv` | 3.6 / 5.5 | 1.6 / 2.7 | 3.5 / 5.0 | 2.6 / 3.2 |
| Search, `from:owner merge` | 12.1 / 19.6 | 7.0 / 12.0 | 25.9 / 46.4 | 23.7 / 39.3 |
| Search, `-done error` | 31.0 / 54.2 | 18.7 / 31.8 | 74.6 / 110.8 | 65.0 / 99.0 |

Single-client phase medians below are calculated separately, so they cannot be added to recover the HTTP median. “Build outside DB” includes response row shaping and snippets; “encode” is the final JSON writer. The remaining Python cost includes the framework’s validation/traversal and response overhead. User space HTTP setup and body transfer are also present in the end-to-end measurements.

| Endpoint | 58.7k SQLite API Python → Rust | 200k SQLite API Python → Rust | 58.7k build outside DB Python → Rust | 58.7k encode Python → Rust |
|---|---:|---:|---:|---:|
| State | 1.59 → 0.34 | 1.11 → 0.39 | 1.18 → 2.61 | 20.31 → 1.49 |
| Chats | 4.85 → 2.28 | 7.19 → 6.46 | 0.75 → 0.78 | 1.18 → 0.11 |
| Conversation | 6.12 → 3.84 | 5.97 → 4.84 | 1.39 → 1.37 | 3.69 → 0.33 |
| Search, `the` | 16.64 → 8.62 | 46.21 → 32.63 | 2.15 → 0.78 | 0.44 → 0.03 |
| Search, `tpu` | 30.41 → 20.89 | 68.84 → 63.02 | 2.94 → 0.98 | 0.31 → 0.03 |

For state, the Rust and Python runs freeze the same non-message fields, including clock, roster/activity observations, teams, tasks, and pins. They fetch, shape and encode the real message rows and reply previews on each request. This makes the comparison reproducible and **does not** measure a Rust implementation of live metadata. The separate full Python test builds that metadata each request. Rust uses the conversation cursor SQL, covering-index Chats SQL, and the same FTS candidate estimates and exact search SQL. It uses a fixture of the seven query plans compiled by the hub instead of porting the text query parser. Rust does not implement Chats search or the queen filter, only the plain list.

The benchmark checked **76 responses per corpus** (152 total), including before/after/around pages and seven search syntaxes on six conversations. All were byte-equal after parsing and canonicalizing JSON object key order and number formatting, including message IDs, ordering, attachments, reply previews, status and snippets. Raw bytes differ because Rust’s JSON map serializer sorts object keys while Python emits insertion order, and the two serializers can spell floating-point exponents differently. The prototype binds localhost only and is a benchmark program, with no production writes, owner auth, or node control.

## Four readers and a writer

The sustained test uses the same traffic mix as `bench/db_scale.py`: four closed-loop HTTP readers choosing state (50%), conversation (35%), or one of the first four search queries (15% total). Another connection records 20 messages/s using the actual Python write and FTS path on both copies. There were 300 attempted writes over each 15-second run and zero errors. The writer is excluded from server CPU. This is a saturation test, not a prediction of typical dashboard traffic. Search p95 in the Python runs has only 13–24 samples per query, so treat those tails as indicative.

| Endpoint | 58.7k Python | 58.7k Rust | 200k Python | 200k Rust |
|---|---:|---:|---:|---:|
| State | 165 / 322 | 13 / 21 | 106 / 207 | 13 / 19 |
| Conversation | 126 / 266 | 13 / 28 | 76 / 188 | 15 / 24 |
| Search, `the` | 305 / 851 | 20 / 59 | 849 / 2,237 | 57 / 182 |
| Search, `tpu` | 150 / 311 | 35 / 51 | 446 / 1,061 | 98 / 121 |
| Search, `snowball eval` | 160 / 374 | 36 / 55 | 300 / 512 | 128 / 161 |
| Search, `"model switch"` | 119 / 242 | 18 / 28 | 141 / 310 | 62 / 80 |
| Writer, same Python path | 0.34 / 5.26 | 0.54 / 5.74 | 0.33 / 12.05 | 4.42 / 10.16 |

| Resource | 58.7k Python | 58.7k Rust | 200k Python | 200k Rust |
|---|---:|---:|---:|---:|
| Single client, CPU seconds for 400 requests | 10.54 | 4.66 | 19.30 | 14.06 |
| Single client, end RSS | 81.8 MiB | 17.4 MiB | 81.1 MiB | 18.6 MiB |
| Mixed reads/sec | 23.8 | 243.8 | 24.0 | 151.4 |
| Mixed server CPU, percent of one core | 126% | 308% | 147% | 345% |
| Mixed server CPU per read | 53 ms | 13 ms | 61 ms | 23 ms |
| Mixed server peak RSS | 101.0 MiB | 55.5 MiB | 97.2 MiB | 56.0 MiB |

Chats is absent from the original traffic mix. With a separate 2 Hz Chats probe alongside the same four readers and writer, the plain-list latency was **121 / 249 → 6.6 / 10.9 ms** at 58.7k and **113 / 184 → 14.0 / 27.4 ms** at 200k (24 probes per engine and corpus, supplementary run).

The faster service used more cores because it served **6–10×** as many reads, and used less process CPU per completed read. Under load the Python SQLite API phase for state rose to 84 / 39 ms median (58.7k / 200k), from 1–2 ms single-client. Rust stayed below 0.6 ms median. Other reads show similar inflation in Python. That is consistent with interpreter contention during SQLite row conversion and search callbacks, as well as service and OS scheduling. It is not evidence that SQLite alone becomes 40× slower. The writer tails also show that a much faster reader is not uniformly better for the write path. The Rust service implements only four reads, so the RSS comparison is for these processes, not a prediction for an entire port.

## Cheaper Python paths

I measured the actual Python state handler with no frozen metadata, on the 58.7k copy. A direct response means returning a `JSONResponse` from the endpoint instead of returning a dict to FastAPI. Its input already consists of JSON-native values. Changing just the serializer leaves the framework traversal in place.

| Full state response | HTTP p50 / p95 | Final encode p50 | CPU seconds / 60 |
|---|---:|---:|---:|
| Current path | 58.7 / 89.9 | 17.5 ms | 3.71 |
| Faster encoder only | 41.7 / 57.9 | 1.0 ms | 2.50 |
| Direct response, standard JSON | 30.1 / 47.2 | 17.1 ms | 1.88 |
| Direct response + `orjson` | **14.5 / 31.5** | 1.0 ms | **0.87** |

I also applied direct responses and `orjson` to **all four** benchmark endpoints on the frozen-state setup. With a single reader the frozen Python state path reached 6.2 ms today and 4.9 ms at 200k, compared with Rust’s 7.5 ms and 8.3 ms in the baseline run. That comparison is sensitive to run order and represents these implementations, not a limit for Rust. With four readers the gain remained substantial, but Rust still handled 1.8–2.6× the optimized Python throughput.

| Four readers, optimized Python | 58.7k | 200k |
|---|---:|---:|
| Reads/sec | 92.8 | 85.7 |
| State p50 / p95 | 34.6 / 57.4 ms | 23.8 / 52.4 ms |
| History p50 / p95 | 38.1 / 66.2 ms | 26.9 / 55.7 ms |
| `tpu` search p50 / p95 | 69.8 / 136.7 ms | 136.8 / 175.4 ms |
| Server CPU per read | 20 ms | 29 ms |
| Peak RSS | 99.3 MiB | 94.2 MiB |

Ship a direct state response first, with response-contract tests for the chosen encoder. Then measure real requests again. If state polls still dominate, split out or cache stable roster/task metadata and return message deltas by ID, or briefly reuse encoded state across concurrent dashboard polls. That also saves network transfer if the UI no longer downloads the whole state. Caching needs an explicit freshness rule for node presence and status, and neither caching nor a delta protocol was measured here. For monitor CPU and responsiveness, batch or stagger tmux captures and avoid polling panes that have gone quiet. For search, use the measured query phases to choose between SQL/index work and moving Unicode folding out of the scan.

A full port would replace about 2,900 lines of `server.py` plus 1,900 lines of `db.py` with 166 SQL execution sites, and would need to preserve roughly 2,300 lines’ worth of tmux, node, and protocol behavior. The expensive part is matching delivery semantics, timeout/retry behavior, hub/node compatibility, migrations and dashboard contracts. The four-read prototype sidesteps all of that. If optimizing Python leaves a real capacity problem, keep writes, monitoring and node transport in Python and prototype a read-only sidecar against the existing database and contracts. Treat the throughput result as reasons to measure demand first, not demand on its own.

## Reproduce

Run from the repo root using a **copy**, not the live database. Keep copies and fixtures private because they contain message text. The `run.sh` driver checks ports, makes two copies with SQLite’s backup API, starts both servers, verifies parity before the write workload and cleans up its processes. Give it a new output directory on the same volume for both engines. For comparable SQLite versions use Python linked to the same system library as `rusqlite`. Optional `--direct-json --orjson` requires `orjson` installed in that Python environment.

```bash
export PYTHON=python3
export PYTHONPATH=.
cargo build --release --locked --manifest-path bench/rust-hub/Cargo.toml
bench=bench/rust-hub
# Set DB to a private SQLite backup, and RUN to a new private scratch directory.
umask 077
mkdir -p "$RUN"
"$PYTHON" "$bench/python_hub.py" fixture "$DB" "$RUN/now.json"
"$PYTHON" bench/db_scale.py build --source "$DB" --rows 200000 --out "$RUN/200k.sqlite"
"$PYTHON" "$bench/python_hub.py" prep "$RUN/200k.sqlite" "$RUN/unused"
"$PYTHON" "$bench/python_hub.py" fixture "$RUN/200k.sqlite" "$RUN/200k.json"
"$bench/run.sh" "$DB" "$RUN/now.json" "$RUN/now-run" "$bench/target/release/rust-hub-bench"
"$bench/run.sh" "$RUN/200k.sqlite" "$RUN/200k.json" "$RUN/200k-run" "$bench/target/release/rust-hub-bench"
"$PYTHON" "$bench/profile_monitor.py" --work "$RUN/monitor" --out "$RUN/monitor-metrics.json"
```

On this host, the pristine backup, phase measurements, parity counts, and resource samples are under `/mnt/storage/karan-scratchpad/task-551/`. No database or transcript was added to the repo.
