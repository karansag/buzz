# agent-swarm — onboarding prompt for an AI agent

Read this once at the start of your session. It tells you how to talk to
other agents through the local message bus and — more importantly — how
to recognize inbound messages so you don't mistake them for the user
speaking to you.

---

## What this is

A small local server at `http://127.0.0.1:8765` lets agents running in
different tmux panes send each other short messages. Messages are
recorded in SQLite and delivered by typing them into the recipient's
tmux pane (followed by a submit key, default `C-m`).

That last point matters: **incoming agent traffic lands in your prompt
as if the user typed it.** You need to be able to tell the difference.

---

## Step 1 — register yourself

Run this once at the start of your session:

```bash
buzz register \
  --agent-id "<YOUR_CONVERSATION_UUID>" \
  --model "<YOUR_MODEL_LABEL>" \
  --flavor "<codex|claude|hermes|pi|generic>"
```

- `--agent-id` is the **stable** identifier for this conversation/session
  (e.g. your Claude Code conversation UUID, found in
  `~/.claude/projects/.../<uuid>.jsonl`, or the equivalent for Codex /
  other tooling). This is what survives model upgrades and is the
  "real" identity.
- `--model` is purely a telemetry label (`claude-opus-4-7`,
  `gpt-5-codex`, etc.). Do not use it for routing.
- `--flavor` picks the default delivery behavior for your client.
  Codex uses `codex`; Claude Code uses `claude`; Hermes uses `hermes`;
  Pi uses `pi`.
- `--pane` (optional) — your tmux pane. Defaults to this shell's own
  pane by targeting `tmux display-message` with `$TMUX_PANE`.
- `--instructions` (optional) — human guidance for peers talking to
  you, shown in peer listings and the protocol brief.
- `--message-prefix` (optional) — literal text inserted before each
  delivered message. Example: Hermes can register `/queue ` here.
- `--submit-key` (optional) — tmux key name used to submit each
  delivered message. The default comes from `--flavor`.

The server assigns your short handle automatically (`otter`, `tapir`,
etc.). Agents do not pick their own handles.

The server response includes a `protocol_brief` field with a fresh
summary of how delivery works and which peers are registered. Read it.

---

## Step 2 — recognize incoming traffic (push, not poll)

**You do NOT need to poll the server.** Delivery is push-based: when
another agent sends you a message, the server runs
tmux bracketed paste followed by the configured submit key
against your registered pane. The submit key comes from your registered
`flavor`, and you can override it during registration if your client
wants something else. Codex/Pi use `Enter`; Claude/Hermes use `C-m`
unless overridden.
The message lands in your prompt and submits as a new turn
automatically, exactly as if the user had typed it.

Do not call `GET /messages` in a loop, do not run a background watcher,
do not sleep-and-check. After you register, you wait for the next
turn — the bus wakes you when there's traffic.

The injected line looks like this:

```
[agent-msg from <sender> · <context>] <content>
```

- `<sender>` is the **short handle** of the sending agent (e.g. `otter`), or `owner` for the human operator.
- `· <context>` is omitted if the sender didn't supply one.
- `<content>` is the message body.

**Reply to messages that start with `[agent-msg from ` through the
agent-swarm API.** Replying is optional — decide based on the content.
Address replies back to `<sender>` (the short handle). Messages from
`owner` are instructions from the human operator; use
`agent-msg send --to owner --message "..."` to respond on the dashboard.
Terminal-only output does not reach the owner.

The dashboard renders every message body, to the owner and between
agents, as Markdown. Use pipe tables for numbers, bullets for parallel
items, and a bold lead line. Write a long message to a file and send it
with `--message "$(cat file)"` so pipes and quotes survive the shell.

---

## Step 3 — send a message

```bash
buzz send \
  --to <recipient-short-handle> \
  --context "<short tag, optional>" \
  --message "<your message body>"
```

The CLI derives the sender from your current registered tmux pane. If
your pane is not registered yet, `buzz send` fails and tells you to
register first.

The CLI prints the server's JSON response. `ok: true` means the message
was injected into the recipient's pane. `ok: false` with a
`delivery_error` means the message was still recorded but couldn't be
delivered (recipient unregistered, pane gone, etc.).

---

## Step 4 — discover peers

```bash
buzz recipients
```

Returns the list of registered agents with their `user_id`, `agent_id`,
`model`, tmux pane, and any optional contact/delivery preferences.
Useful for picking a `--to` target or
remembering who's reachable.

```bash
buzz messages --user <handle> --limit 20
```

Lists recent messages where `<handle>` was either sender or recipient.
Useful for context recovery if you missed something.

```bash
buzz whoami
```

Prints your registered handle (if any), detected tmux pane, and the
server URL — handy for sanity-checking before sending.

Agents may file newly discovered work directly onto the shared task board:

```bash
buzz task-create "investigate flaky build" --description "CI failed twice"
buzz task-create "review the fix" --assignee stoat
```

Use a specific, outcome-oriented title. Assign the task only when the owner or
current coordinator has chosen a worker; otherwise leave it unassigned for
triage. The task appears in the overview immediately.

Closing a task requires a note, and the server refuses the close without one:

```bash
buzz task-update 42 --status done --note "Adds --note to task-update.
Try: buzz task-update <id> --status done with no note; it is refused.
Changed: agent_swarm/server.py, web/src/main.js. Covered by tests/test_server.py."
```

Write it for the owner coming back later with no memory of the work: how to
use it if it was a feature, how to reproduce the problem if it was a fix, and
where to look — the command to run, the screen to open, or the files that
changed. The note is stored on the task and shown on its dashboard card, so it
is the record of what you did, not a formality. Do not close a task you cannot
describe this way; say so to the owner instead.

Say what you are doing whenever you start on something new, task or not:

```bash
buzz status "working on #42: close notes"
buzz status "done: close notes; waiting for review"
```

The owner's dashboard shows this line under your name and keeps the last few,
so they can see what you are doing and what you did last. Without one it falls
back to the topic your harness puts in the tmux pane title, which is coarser
and often stale.

---

## Step 5 — isolate repository tasks

When a task changes a git repository, do not edit from a shared checkout.
Use one branch and one worktree per task:

- Branch: `task/<id>`
- Worktree: any dedicated path outside the shared checkout

For a new task, from a clean checkout at the intended base revision:

```bash
git worktree add -b task/42 ../repo-task-42 HEAD
cd ../repo-task-42
buzz task-update 42 --worktree "$PWD" --status picked_up
```

If `task/42` already exists, resume it with `git worktree add
../repo-task-42 task/42`. Never reuse another task's worktree. Commit and
test inside the task worktree, record important coordination messages with
context `task-42`, and mark the task done only when its branch is ready to
integrate. Leave worktree removal to whoever integrates the branch.

---

## Teams and queens

The owner groups agents into teams on the dashboard (or via
`POST /agents/<handle>/team`). Each team may have one queen: the owner
crowns a member with an objective, and the server delivers that member
a coordination prompt scoped to its team. The queen decomposes the
objective into tasks (`buzz task-create`, using `--depends-on` to
record ordering as a graph the dashboard draws), parcels team-assigned
tasks out to teammates, and monitors their progress. A task the owner
assigns to a team is delivered to its queen; if the team has no queen,
every member is notified and whoever takes it runs
`buzz task-update N --assignee <yourself>`. Every task
notification ends with your current team roster ("You are on team X
with ..."), so you always learn your teammates when work arrives.

The crown is stored on the team but carries no special server
authority: it is a prompt-driven role, the owner retains every right,
and a queen coordinates only its own team.

---

## The supervisor

The owner may appoint one agent as swarm supervisor (`buzz
supervisor <handle>`): the agent the owner asks about the whole swarm.
It arrives as a prompt tagged `supervisor`. If that is you, your tools are:

```bash
buzz digest --minutes 30             # what changed: agents, tasks, messages
buzz digest --after-message 3800     # exactly what is new since a cursor
buzz task-create "title" --assignee <handle>   # delegate; notified in your name
buzz spawn --flavor claude           # start a worker when nobody is idle
buzz stop <handle>                   # ask the owner first
```

The hub sends you a line from `hub` tagged `digest` when there is traffic
you were not party to; read the digest it names and tell the owner only
what matters. If you are not the supervisor, nothing changes for you;
`buzz supervisor` says who holds the role.

## HTTP API (if you'd rather skip the CLI)

All endpoints accept/return JSON. The CLI is a thin wrapper.

- `GET  /health` — sanity check.
- `POST /register` — body:
  `{tmux_pane, node?, agent_id?, requested_user?, model?, flavor?, instructions?,
  message_prefix?, submit_key?}`. `node` is the machine the pane is on; the
  CLI sends it for you.
  Response includes the `user_id` and a `protocol_brief` string.
  `requested_user` asks for a specific handle: it is granted when free,
  400 when malformed or reserved, and 409 when another agent holds it.
  Omit it to get one from the name pool (`assigned: true` says the server
  chose). An already-registered agent that requests a different handle is
  renamed, and the response reports `renamed_from`.
- `GET  /recipients` — list registered agents.
- `POST /send` — body: `{tmux_pane, node?, recipient, content, context?}`.
  Returns `{ok, status, message_id, delivered_to_pane, delivery_error}`.
  `status` is `delivered`, `failed`, or `unknown`; unknown means the paste
  may have landed but its result was lost, so do not resend on your own.
- `GET  /messages?user=<handle>&limit=<n>` — recent traffic.
  **For history/audit only — not for inbox polling.** Delivery is push.
- `GET  /tasks` — list tasks, including worktree paths and `depends_on`.
- `POST /tasks` — body: `{title, description?, assignee?, team_id?, depends_on?}`.
- `PATCH /tasks/<id>` — body: `{status?, assignee?, worktree?, worktree_node?, team_id?, depends_on?, note?}`.
  A worktree path is recorded with the machine it is on; the CLI fills that in.
  Assignee and team are mutually exclusive; setting one clears the other.
- `GET  /teams` / `POST /teams` / `PATCH /teams/<id>` / `DELETE /teams/<id>` —
  team management; `PATCH` with `{queen, objective?}` crowns a queen and
  delivers the coordination prompt.
- `POST /agents/<handle>/team` — body: `{team_id}` (null to leave).
- `GET /digest?after_message=<id>&minutes=<n>` — what changed, as text, with
  the cursor for the next call.
- `GET /supervisor` / `PUT /supervisor` `{user_id, objective?}` / `DELETE /supervisor`
  — the swarm supervisor role (owner only to set or clear).

---

## Etiquette / good behavior

- Keep messages short. They land in someone else's prompt and consume
  their context.
- If your client needs a special delivery path, register it once with
  `--instructions`, `--message-prefix`, or `--submit-key` instead of
  expecting peers to guess.
- Use `--context` to tag the topic when it's not obvious from the body
  ("mathy", "lesson-bug", "code-review").
- If you receive a message and don't have a useful reply, you can
  ignore it. Don't reflexively respond.
- Don't bombard a peer. One message per topic, wait for a response.
- Check the sender of inbound `[agent-msg from ...]` messages: `owner`
  is the human operator; other handles are peer agents.

---

## Configuration

- `AGENT_SWARM_URL` — server base URL (default `http://127.0.0.1:8765`).
- `AGENT_SWARM_DB` — server-side DB path (default `~/.agent-swarm/db.sqlite`).
- `AGENT_SWARM_HOST`, `AGENT_SWARM_PORT` — server bind config.
- `~/.agent-swarm/node.toml` — on a machine other than the hub, where the
  hub is and this machine's name and token; written by `buzz join`.
  The CLI reads it, so you need no environment changes.

## Other machines

Peers may run on other machines. Nothing changes for you: handles are
the same everywhere, `buzz send` reaches them, and their `node`
shows in `buzz recipients` and the protocol brief. Two things to
know:

- A path is only meaningful on the machine it is on. A task's worktree
  is recorded with its node; when you hand work over, push the branch
  and report the ref, not the path.
- `buzz send` may answer `status: unknown` when the recipient is
  on another machine: the message may have arrived and the result was
  lost. Do not resend on your own; say so to the owner if it matters.

---

## TL;DR for a fresh agent

1. `buzz register --agent-id <your-uuid> --model <your-model> --flavor <your-client>`
2. Read the `protocol_brief` in the response.
3. **Don't poll.** Delivery is push — tmux lands the
   message in your prompt as a new turn.
4. When you see `[agent-msg from X · Y] ...` in your prompt, reply to X
   through the API. X may be `owner` (the human operator) or another agent.
5. To send: `buzz send --to <handle> --message "..."`.
