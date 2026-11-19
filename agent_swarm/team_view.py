"""One team at a glance, for its queen: who is doing what, and what can move.

`buzz team` and GET /teams/{ref}/view render this. Pure functions over the
rows the hub already has, so tests never need the server.
"""

from __future__ import annotations

import shlex
import time

from .digest import _ago, _clip

OWNER = "owner"
# A picked-up task whose holder has sent no message, set no status line, and
# not touched the task for this long is called stale.
STALE_HOURS = 4.0


def _status_line(summaries: list[dict]) -> dict | None:
    """The agent's own newest status line; owner notes are not status lines."""
    return next((s for s in summaries if s.get("source") != OWNER), None)


def _state(recipient: dict) -> str:
    if not recipient.get("alive"):
        return "offline"
    return "idle" if (recipient.get("activity") or {}).get("status") == "idle" else "live"


def team_tasks(team: dict, tasks: list[dict]) -> list[dict]:
    """The team's work: tasks held by any member, and tasks assigned to the team."""
    members = set(team["members"])
    return [t for t in tasks if t["assignee"] in members or t["team_id"] == team["id"]]


def build(
    now: float,
    team: dict,
    recipients: list[dict],
    tasks: list[dict],
    last_to_queen: dict[str, float],
    last_sent: dict[str, float],
    hub_node: str,
    stale_hours: float = STALE_HOURS,
    since: float | None = None,
) -> dict:
    """The view as data plus text.

    `recipients` carry `alive`, `activity` and `summaries`, as the dashboard
    gets them. `tasks` is the whole board, so dependencies outside the team
    can be looked up. `last_to_queen` and `last_sent` map a member to the
    time of the newest message it sent to the queen, and to anyone.
    With `since`, members and tasks that did not change after it are left out;
    flags always show, because they are about now.
    """
    queen = team.get("queen")
    by_id = {t["id"]: t for t in tasks}
    by_user = {r["user_id"]: r for r in recipients}
    mine = [t for t in team_tasks(team, tasks) if t["status"] != "done"]
    mine.sort(key=lambda t: t["id"])

    members = []
    for handle in team["members"]:
        r = by_user.get(handle, {})
        line = _status_line(r.get("summaries") or [])
        members.append({
            "handle": handle,
            "queen": handle == queen,
            "node": r.get("node"),
            "may_sleep": bool(r.get("node")) and r.get("node") != hub_node,
            "state": _state(r),
            "activity": (r.get("activity") or {}).get("status"),
            "offline_reason": (r.get("offline_reason") or "").removeprefix("recipient offline: ") or None,
            "status": {"text": line["text"], "ts": line["ts"]} if line else None,
            "open_tasks": [
                {"id": t["id"], "title": t["title"], "status": t["status"]}
                for t in mine if t["assignee"] == handle
            ],
            "last_to_queen": last_to_queen.get(handle),
        })
    member_of = {m["handle"]: m for m in members}

    views = []
    for t in mine:
        deps = [by_id[d] for d in t["depends_on"] if d in by_id]
        waiting = [d for d in deps if d["status"] != "done"]
        holder = by_user.get(t["assignee"] or "", {})
        line = _status_line(holder.get("summaries") or [])
        heard = max([t["updated_at"], last_sent.get(t["assignee"] or "", 0), line["ts"] if line else 0])
        if t["status"] == "picked_up":
            state = "stale" if now - heard > stale_hours * 3600 else "in_progress"
        else:
            state = "blocked" if waiting else "ready"
        views.append({
            "id": t["id"],
            "title": t["title"],
            "status": t["status"],
            "assignee": t["assignee"],
            "state": state,
            "depends_on": [{"id": d["id"], "status": d["status"], "title": d["title"]} for d in deps],
            "blocked_by": [d["id"] for d in waiting],
            "last_heard": heard,
            "updated_at": t["updated_at"],
        })

    flags = []
    for m in members:
        if not m["queen"] and m["state"] != "offline" and not m["open_tasks"]:
            flags.append({"kind": "free", "member": m["handle"], "task": None,
                          "text": f"{m['handle']} has no open task: free to assign"})
    for v in views:
        holder = member_of.get(v["assignee"] or "")
        if v["assignee"] is None:
            flags.append({"kind": "unassigned", "member": None, "task": v["id"],
                          "text": f"#{v['id']} is assigned to the team but to no member"})
        elif holder is None:
            continue  # a team task held outside the team; its holder is not ours to judge
        elif holder["state"] == "offline":
            flags.append({"kind": "offline", "member": holder["handle"], "task": v["id"],
                          "text": f"#{v['id']} is held by {holder['handle']}, who is offline"})
        elif holder["may_sleep"]:
            flags.append({"kind": "may_sleep", "member": holder["handle"], "task": v["id"],
                          "text": f"#{v['id']} is held by {holder['handle']} on {holder['node']}, "
                                  "which may sleep"})
        if v["state"] == "stale":
            flags.append({"kind": "stale", "member": v["assignee"], "task": v["id"],
                          "text": f"#{v['id']} is stale: nothing from {v['assignee'] or 'anyone'} "
                                  f"for {_ago(now - v['last_heard'])}"})

    if since is not None:
        changed = {v["assignee"] for v in views if v["updated_at"] > since}
        members = [
            m for m in members
            if m["handle"] in changed
            or (m["status"] and m["status"]["ts"] > since)
            or (m["last_to_queen"] or 0) > since
        ]
        views = [v for v in views if v["updated_at"] > since]

    view = {
        "team": {"id": team["id"], "name": team["name"], "queen": queen},
        "now": now,
        "since": since,
        "hub_node": hub_node,
        "stale_hours": stale_hours,
        "members": members,
        "tasks": views,
        "flags": flags,
    }
    view["text"] = render(view)
    return view


def _when(now: float, ts: float | None) -> str:
    if not ts:
        return "never"
    return f"{time.strftime('%H:%M', time.localtime(ts))} ({_ago(now - ts)} ago)"


def render(view: dict) -> str:
    now = view["now"]
    team = view["team"]
    members = view["members"]
    counts = {s: sum(1 for m in members if m["state"] == s) for s in ("live", "idle", "offline")}
    window = f" · changes since {time.strftime('%H:%M', time.localtime(view['since']))}" if view["since"] else ""
    lines = [
        (f"team {team['name']} · queen {team['queen'] or '(none)'} · "
         f"{time.strftime('%H:%M', time.localtime(now))}{window}"),
        (f"members: {len(members)} shown ({counts['live']} live, {counts['idle']} idle, "
         f"{counts['offline']} offline)"),
    ]
    for m in members:
        node = f"{m['node'] or '?'}{' (may sleep)' if m['may_sleep'] else ''}"
        state = m["state"] + (f": {m['offline_reason']}" if m["offline_reason"] else "")
        status = (f"\"{_clip(m['status']['text'], 100)}\" ({_ago(now - m['status']['ts'])})"
                  if m["status"] else "(no status line)")
        head = f"  {m['handle']}{' (queen)' if m['queen'] else ''} · {node} · {state} · {status}"
        if not m["queen"]:
            head += f" · last to queen {_when(now, m['last_to_queen'])}"
        lines.append(head)
        for t in m["open_tasks"]:
            lines.append(f"      #{t['id']} {t['status']} · {_clip(t['title'], 90)}")

    tasks = view["tasks"]
    tally = {s: sum(1 for t in tasks if t["state"] == s) for s in ("ready", "blocked", "in_progress", "stale")}
    lines.append(
        f"tasks: {len(tasks)} open shown ({tally['ready']} ready, {tally['blocked']} blocked, "
        f"{tally['in_progress']} in progress, {tally['stale']} stale after {view['stale_hours']:g}h)"
    )
    for t in tasks:
        line = f"  #{t['id']} {t['state'].replace('_', ' ')} · {t['assignee'] or 'unassigned'} · {_clip(t['title'], 90)}"
        if t["depends_on"]:
            deps = ", ".join(f"#{d['id']} {d['status']}" for d in t["depends_on"])
            line += f" · deps: {deps}"
        lines.append(line)

    lines.append(f"flags: {len(view['flags'])}" if view["flags"] else "flags: none")
    for f in view["flags"]:
        lines.append(f"  {f['text']}")
    lines.append(f"next: buzz team {shlex.quote(team['name'])} --since {int(now)}")
    return "\n".join(lines)
