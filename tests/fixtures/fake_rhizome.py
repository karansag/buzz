"""A stand-in for `rhizome mcp`: MCP over stdio, shaped like Rhizome 0.14.0.

Answers copy what the real binary returned in an isolated cluster. State
comes from the folder in FAKE_RHIZOME_DIR: `sessions.json` is the rows
list_sessions returns, `sent.jsonl` gets one line per accepted send, and
`starts` gets one line per process start. Text in a send picks a failure:
RATE (rate limit), HANG (no answer), DIE (exit without answering), PING
(accept, then deliver a direct message back from that session).
"""

import json
import os
import sys
from pathlib import Path

root = Path(os.environ["FAKE_RHIZOME_DIR"])
bound = None


def out(frame):
    sys.stdout.write(json.dumps(frame) + "\n")
    sys.stdout.flush()


def answer(rid, text, error=False):
    result = {"content": [{"type": "text", "text": text}]}
    if error:
        result["isError"] = True
    out({"jsonrpc": "2.0", "id": rid, "result": result})


def sessions():
    path = root / "sessions.json"
    return json.loads(path.read_text()) if path.exists() else []


with (root / "starts").open("a") as f:
    f.write("start\n")

for line in sys.stdin:
    frame = json.loads(line)
    rid, method, params = frame.get("id"), frame.get("method"), frame.get("params") or {}
    if method == "initialize":
        out({"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2025-11-25", "capabilities": {"tools": {}},
            "serverInfo": {"name": "rhizome", "version": "fake"}}})
    elif method == "tools/call":
        name, args = params["name"], params.get("arguments") or {}
        if name == "observe_session":
            if os.environ.get("FAKE_RHIZOME_NO_BIND"):
                answer(rid, "binding refused", error=True)
                continue
            bound = args["session_id"]
            answer(rid, "{}")
        elif name == "list_sessions":
            if bound is None:
                answer(rid, json.dumps({"binding": "UNBOUND: waiting for session hook"}))
            else:
                own = {"identity": {"session_id": bound, "agent_type": "claude"},
                       "status": "live", "delivery_capable": True}
                answer(rid, json.dumps({"binding": "BOUND", "identity": own["identity"],
                                        "sessions": [own, *sessions()]}))
        elif name == "send":
            sid, text = args["session_id"], args["text"]
            row = next((s for s in sessions() if s["identity"]["session_id"] == sid), None)
            if bound is None:
                answer(rid, "UNBOUND: waiting for session hook", error=True)
            elif row is None or row["status"] != "live" or not row["delivery_capable"]:
                answer(rid, f'session "{sid}" is not currently available', error=True)
            elif "RATE" in text:
                answer(rid, "rate limit: at most ten publish/send calls per minute", error=True)
            elif "HANG" in text:
                pass
            elif "DIE" in text:
                sys.exit(1)
            else:
                with (root / "sent.jsonl").open("a") as f:
                    f.write(json.dumps({"session_id": sid, "text": text}) + "\n")
                mid = f"m{sum(1 for _ in (root / 'sent.jsonl').open())}"
                answer(rid, json.dumps({"accepted": True, "message_id": mid}))
                if "PING" in text:
                    out({"jsonrpc": "2.0", "method": "notifications/claude/channel", "params": {
                        "content": "[direct] " + text.split("PING", 1)[1].strip(),
                        "meta": {"kind": "direct", "session_id": sid, "message_id": "in-" + mid}}})
        else:
            answer(rid, f"unknown tool {name}", error=True)
