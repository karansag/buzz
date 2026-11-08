"""A compact, text-first summary of what changed in the swarm.

Written for an LLM to read in one go: the supervisor agent runs
`buzz digest` when the owner asks what is going on, and the hub
nudges it when there is something new. Pure functions over the same rows
the dashboard shows, so tests never need the server.
"""

from __future__ import annotations

import time

OWNER = "owner"
HUB = "hub"

# How much of a message or title is shown per line.
LINE_CHARS = 160
# Past this many new messages the digest lists the newest and says how many
# it left out, so a busy hour cannot flood the reader's context.
MAX_MESSAGES = 40
MAX_TASKS = 25
ACTIVITY_ORDER = ("needs_attention", "working", "idle", "unknown")


def _clip(text: str, n: int = LINE_CHARS) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _ago(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    return f"{seconds // 86400}d"


def _clock(ts: float) -> str:
    return time.strftime("%H:%M", time.localtime(ts))


def changed(
    messages: list[dict], tasks: list[dict], since_ts: float, supervisor: str | None
) -> dict:
    """What the nudge counts: traffic the supervisor was not party to, and
    tasks touched since the cursor. Its own threads land in its pane anyway."""
    others = [m for m in messages if supervisor not in (m["sender"], m["recipient"])]
    return {
        "messages": len(others),
        "failed": sum(1 for m in others if m["status"] in ("failed", "unknown")),
        "tasks": sum(1 for t in tasks if t["updated_at"] > since_ts),
    }


def nudge_text(counts: dict, after_id: int) -> str:
    parts = []
    if counts["messages"]:
        parts.append(f"{counts['messages']} new message(s)")
        if counts["failed"]:
            parts[-1] += f" ({counts['failed']} failed/unknown)"
    if counts["tasks"]:
        parts.append(f"{counts['tasks']} task change(s)")
    return (
        f"Since your last digest: {', '.join(parts)}. "
        f"Run `buzz digest --after-message {after_id}` to read them, then tell "
        f"the owner only what matters (attention, done, failed, stalled). "
        f"Reply via `buzz send --to owner`."
    )


def render(
    now: float,
    recipients: list[dict],
    tasks: list[dict],
    messages: list[dict],
    after_id: int,
    since_ts: float,
    supervisor: str | None = None,
    teams: list[dict] | None = None,
) -> dict:
    """The digest as text plus the cursor to pass next time.

    `messages` are the rows newer than the cursor, oldest first. `tasks` is
    the whole board (the digest picks out what changed and what is waiting).
    """
    team_name = {t["id"]: t["name"] for t in (teams or [])}
    lines = []
    cursor = max([after_id, *(m["id"] for m in messages)])
    window = f"since message #{after_id}" if after_id else f"since {_clock(since_ts)}"
    lines.append(f"swarm digest · {_clock(now)} · {window}")

    # -- agents ---------------------------------------------------------
    live = [r for r in recipients if r.get("alive")]
    offline = [r for r in recipients if not r.get("alive")]
    by_status: dict[str, list[dict]] = {k: [] for k in ACTIVITY_ORDER}
    for r in live:
        status = (r.get("activity") or {}).get("status") or "unknown"
        by_status.setdefault(status, []).append(r)
    tally = ", ".join(f"{len(v)} {k.replace('_', ' ')}" for k, v in by_status.items() if v)
    lines.append(f"agents: {len(live)} live ({tally or 'none'}), {len(offline)} offline")
    for status in ("needs_attention", "working"):
        for r in by_status.get(status, []):
            act = r.get("activity") or {}
            since = act.get("since")
            age = f" ({_ago(now - since)})" if since else ""
            tag = f" [team {team_name[r['team_id']]}]" if r.get("team_id") in team_name else ""
            if status == "needs_attention":
                lines.append(f"  needs attention: {r['user_id']}{tag} — {_clip(act.get('detail') or '')}{age}")
            else:
                summary = next((s for s in r.get("summaries", []) if s.get("source") != "owner"), {}).get("text") or "(no status line)"
                lines.append(f"  working: {r['user_id']}{tag} — {_clip(summary)}{age}")
    idle = [r["user_id"] for r in by_status.get("idle", [])]
    if idle:
        lines.append(f"  idle: {', '.join(idle)}")
    if supervisor:
        lines.append(f"  you are the supervisor: {supervisor}")

    # -- tasks ----------------------------------------------------------
    touched = sorted((t for t in tasks if t["updated_at"] > since_ts), key=lambda t: -t["updated_at"])
    waiting = [t for t in tasks if t["status"] == "open" and not t.get("assignee") and not t.get("team_id")]
    in_flight = [t for t in tasks if t["status"] == "picked_up"]
    lines.append(
        f"tasks: {len(touched)} changed, {len(in_flight)} in progress, "
        f"{len(waiting)} open and unassigned"
    )
    for t in touched[:MAX_TASKS]:
        who = t.get("assignee") or (f"team {team_name.get(t['team_id'], t['team_id'])}" if t.get("team_id") else "unassigned")
        line = f"  #{t['id']} {t['status']} · {who} · {_clip(t['title'], 90)} ({_ago(now - t['updated_at'])} ago)"
        if t["status"] == "done" and t.get("note"):
            line += f"\n      verify: {_clip(t['note'], 140)}"
        lines.append(line)
    if len(touched) > MAX_TASKS:
        lines.append(f"  … {len(touched) - MAX_TASKS} more changed; see buzz tasks")
    for t in waiting[:MAX_TASKS]:
        if t["updated_at"] <= since_ts:
            lines.append(f"  waiting: #{t['id']} {_clip(t['title'], 90)} ({_ago(now - t['created_at'])} old)")

    # -- messages -------------------------------------------------------
    own_ids = {m["id"] for m in messages if supervisor and supervisor in (m["sender"], m["recipient"])}
    own = [m for m in messages if m["id"] in own_ids]
    shown = [m for m in messages if m["id"] not in own_ids]
    owner_side = sum(1 for m in shown if OWNER in (m["sender"], m["recipient"]))
    failed = [m for m in shown if m["status"] in ("failed", "unknown")]
    head = f"messages: {len(shown)} new"
    if shown:
        head += f" ({owner_side} with owner, {len(shown) - owner_side} agent to agent"
        head += f", {len(failed)} failed/unknown)" if failed else ")"
    if own:
        head += f"; {len(own)} in your own threads not repeated here"
    lines.append(head)
    hidden = max(0, len(shown) - MAX_MESSAGES)
    if hidden:
        lines.append(f"  … {hidden} older new message(s) left out; newest {MAX_MESSAGES} follow")
    for m in shown[-MAX_MESSAGES:]:
        ctx = f" [{m['context']}]" if m.get("context") else ""
        mark = "" if m["status"] == "delivered" else f" ({m['status']}: {_clip(m.get('delivery_error') or '', 60)})"
        lines.append(f"  {_clock(m['ts'])} {m['sender']} → {m['recipient']}{ctx}{mark}: {_clip(m['content'])}")

    lines.append(f"next: buzz digest --after-message {cursor}")
    counts = changed(messages, tasks, since_ts, supervisor)
    return {
        "text": "\n".join(lines),
        "cursor": {"message_id": cursor, "ts": now},
        "counts": counts,
    }
