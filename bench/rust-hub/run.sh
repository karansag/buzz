#!/usr/bin/env bash
# Call from repo root. Use private scratch, never the live database.
set -euo pipefail
umask 077
: "${PYTHON:=python3}" "${PY_PORT:=8811}" "${RS_PORT:=8812}" "${REPS:=40}" "${SECONDS_PER_RUN:=15}"
export PYTHONPATH=".${PYTHONPATH:+:$PYTHONPATH}"
bench=bench/rust-hub
src=${1:?path to prepared DB copy}
fixture=${2:?path to matching fixture}
out=${3:?private output directory}
bin=${4:?path to release rust-hub-bench}
mkdir -p "$out"
for port in "$PY_PORT" "$RS_PORT"; do
    if [[ -n $(ss -H -ltn "sport = :$port") ]]; then
        echo "port $port is in use" >&2
        exit 1
    fi
done
extra=()
if [[ ${CHATS_PROBE:-0} == 1 ]]; then extra+=(--chats-probe); fi
py_pid=
rs_pid=
cleanup() {
    for pid in "$py_pid" "$rs_pid"; do
        if [[ -n $pid ]]; then
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
        fi
    done
}
trap cleanup EXIT
wait_for() {
    local port=$1 pid=$2
    for ((n=0;n<80;n++)); do
        kill -0 "$pid"
        if curl -fs "http://127.0.0.1:$port/health" >/dev/null; then return; fi
        sleep .1
    done
    return 1
}

"$PYTHON" - "$src" "$out" <<'PY'
import sqlite3
import sys
from pathlib import Path

src, out = map(Path, sys.argv[1:])
for name in ("python", "rust"):
    target = out / f"{name}.sqlite"
    if target.exists():
        raise FileExistsError(target)
    with sqlite3.connect(src.resolve().as_uri() + "?mode=ro", uri=True) as a, sqlite3.connect(target) as b:
        a.backup(b)
PY
"$PYTHON" "$bench/python_hub.py" serve "$out/python.sqlite" "$fixture" --port "$PY_PORT" >"$out/python-server.log" 2>&1 &
py_pid=$!
"$bin" "$out/rust.sqlite" "$fixture" "127.0.0.1:$RS_PORT" >"$out/rust-server.log" 2>&1 &
rs_pid=$!
wait_for "$PY_PORT" "$py_pid"
wait_for "$RS_PORT" "$rs_pid"
ss -H -ltnp "sport = :$PY_PORT or sport = :$RS_PORT"
"$PYTHON" "$bench/compare.py" --db "$out/python.sqlite" --base "http://127.0.0.1:$PY_PORT" \
    --other "http://127.0.0.1:$RS_PORT" --pid "$py_pid" --reps "$REPS" --seconds "$SECONDS_PER_RUN" --out "$out/python.json" "${extra[@]}"
"$PYTHON" "$bench/compare.py" --db "$out/rust.sqlite" --base "http://127.0.0.1:$RS_PORT" \
    --pid "$rs_pid" --reps "$REPS" --seconds "$SECONDS_PER_RUN" --out "$out/rust.json" "${extra[@]}"
