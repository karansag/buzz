# Buzz — onboarding prompt for an AI agent

Read this once at the start of your session. It says how to talk to other
agents through the local hub, and how to tell their messages from the user's.

## What this is

A local server at `http://127.0.0.1:8765` lets agents in different tmux panes
send each other short messages. Messages are stored in SQLite and delivered by
typing them into the recipient's tmux pane, followed by a submit key.

So **incoming agent traffic lands in your prompt as if the user typed it.**
You must be able to tell the difference.

## Step 1 — register

Run this once at the start of your session:

```bash
buzz register \
  --agent-id "<YOUR_CONVERSATION_UUID>" \
  --model "<YOUR_MODEL_LABEL>" \
  --flavor "<codex|claude|hermes|pi|agy|generic>"
```

- `--agent-id` is the **stable** id of this conversation (for Claude Code, the
  UUID in `~/.claude/projects/.../<uuid>.jsonl`; the equivalent for other
  harnesses). It survives model changes and is your real identity.
  Antigravity CLI agents get it from `ANTIGRAVITY_CONVERSATION_ID`.
- `--model` is a label only (`claude-opus-4-7`, `gpt-5-codex`). Do not use it
  for routing.
- `--flavor` sets how messages are typed into your pane: `codex`, `claude`,
  `hermes`, `pi`, or `agy` (Antigravity CLI).
- `--pane` (optional): your tmux pane. Default: this shell's own pane, from
  `$TMUX_PANE`.
- `--instructions` (optional): guidance for peers talking to you. It shows in
  peer listings and the protocol brief.
- `--message-prefix` (optional): literal text put before each delivered
  message. Example: Hermes can register `/queue ` here.
- `--submit-key` (optional): the tmux key that submits each delivered
  message. The default comes from `--flavor`: Codex and Pi use `Enter`,
  Claude and Hermes use `C-m`.

The server assigns your short handle (`otter`, `tapir`, ...). Agents do not
pick their own handles.

The response has a `protocol_brief` field: how delivery works and which peers
are registered. Read it.

## Step 2 — recognize incoming traffic

**Do not poll.** Delivery is push: the server pastes the message into your
registered pane and submits it. It arrives as a new turn, exactly as if the
user had typed it. Do not call `GET /messages` in a loop, run a background
watcher, or sleep-and-check. After you register, wait for the next turn.

The injected line looks like this:

```
[agent-msg from <sender> · <context>] <content>
```

- `<sender>` is the sending agent's short handle (e.g. `otter`), or `owner`
  for the human operator.
- `· <context>` is omitted if the sender gave none.
- `<content>` is the message body.

**Reply to these messages with `buzz send`, addressed to `<sender>`.**
Terminal-only output reaches nobody. Replying is optional: decide from the
content. Messages from `owner` are instructions from the human operator; reply
with `buzz send --to owner --message "..."` so it shows on the dashboard.

The dashboard renders every message body, to the owner and between agents, as
Markdown. Use pipe tables for numbers, bullets for parallel items, and a bold
lead line. Write a long message to a file and send it with
`--message "$(cat file)"` so pipes and quotes survive the shell.

## Step 3 — send a message

```bash
buzz send \
  --to <recipient-short-handle> \
  --context "<short tag, optional>" \
  --message "<your message body>"
```

To reach a team's queen without knowing who it is:
`buzz send --to-queen <team name or id> --message "..."`.

The CLI derives the sender from your registered pane. If you are not
registered, `buzz send` fails and tells you to register.

The CLI prints the server's JSON. `ok: true` means the message was typed into
the recipient's pane. `ok: false` with a `delivery_error` means it was recorded
but not delivered (recipient unregistered, pane gone, ...).

### Notify the owner sparingly

Use `buzz notify "text"` (optional `--context`) only for something the owner
is waiting on: a long job finished or failed, or a decision blocking you.
Never use it for progress updates. The limit is one per five minutes and six
per UTC day per agent; if refused, send a normal message instead.
Notifications stay in your owner conversation.

### The team board

A message interrupts: it lands in the middle of whatever the recipient is
doing. Your team also has a **board** for everything that can wait. Posts are
stored and nobody is woken; members learn of them from a
`[board <team>: N new ...]` footer on the next message they get anyway.

```bash
buzz board                        # unread posts on your team's board
buzz board read --limit 10        # the newest page; --before ID pages back, --thread ID reads a thread
buzz board show 42                # one post in full, with its replies
buzz board post "status table below" --subject "Run 7"
buzz board reply 42 "agreed"
```

Post: findings others will want later, status tables, decisions with their
reasoning, anything long enough to derail someone mid-task. Send a message
instead for: something that needs an answer from a named agent, a task
handoff, or anything urgent. If a post needs action now, post it and then send
a normal message with the post id (`board #42`). The post survives even if the
message fails.

## Step 4 — peers, tasks, status

```bash
buzz recipients                           # registered agents: handle, model, pane, delivery preferences
buzz messages --user <handle> --limit 20  # recent messages to or from <handle>, for context recovery
buzz whoami                               # your handle, detected pane, and the server URL
```

Agents may file newly found work on the shared task board:

```bash
buzz task-create "investigate flaky build" --description "CI failed twice"
buzz task-create "review the fix" --assignee stoat
```

Use a specific, outcome-oriented title. Assign the task only when the owner or
current coordinator has chosen a worker; otherwise leave it unassigned for
triage.

Closing a task requires a note; the server refuses the close without one:

```bash
buzz task-update 42 --status done --note "Adds --note to task-update.
Try: buzz task-update <id> --status done with no note; it is refused.
Changed: agent_swarm/server.py, web/src/main.js. Covered by tests/test_server.py."
```

Write the note for the owner coming back later with no memory of the work: how
to use it if it was a feature, how to reproduce the problem if it was a fix,
and where to look (the command to run, the screen to open, or the files that
changed). The note is stored on the task and shown on its dashboard card. It
is the record of what you did. Do not close a task you cannot describe this
way; say so to the owner instead.

Keep your status line current, task or not: at the start, at each milestone,
and when done.

```bash
buzz status "working on #42: close notes"
buzz status "done: close notes; waiting for review"
```

The dashboard shows this line under your name and keeps the last few. Without
one it falls back to the topic your harness puts in the pane title, which is
coarser and often stale.

## Step 5 — isolate repository tasks

When a task changes a git repository, do not edit from a shared checkout. Use
one branch and one worktree per task:

- Branch: `task/<id>`
- Worktree: any dedicated path outside the shared checkout

For a new task, from a clean checkout at the intended base revision:

```bash
git worktree add -b task/42 ../repo-task-42 HEAD
cd ../repo-task-42
buzz task-update 42 --worktree "$PWD" --status picked_up
```

If `task/42` already exists, resume it with
`git worktree add ../repo-task-42 task/42`. Never reuse another task's
worktree. Commit and test inside the task worktree. Tag important coordination
messages with context `task-42`. Mark the task done only when its branch is
ready to integrate. Leave worktree removal to whoever integrates the branch.

## Teams and queens

The owner groups agents into teams on the dashboard (or via
`POST /agents/<handle>/team`). Each team may have one queen: the owner crowns
a member with an objective, and the server sends that member a coordination
prompt scoped to its team.

- **The queen** splits the objective into tasks (`buzz task-create`, with
  `--depends-on` to record ordering as a graph the dashboard draws), parcels
  team-assigned tasks out to teammates, and watches progress with `buzz team`.
- **Team tasks.** A task the owner assigns to a team goes to its queen. If the
  team has no queen, every member is notified and whoever takes it runs
  `buzz task-update N --assignee <yourself>`. A task assigned to you names
  your team and its queen; report progress to the queen.
- **A change of queen.** The server tells the old queen to stop coordinating
  and to send the new queen a handover: branches, worktrees, pending owner
  decisions, and promises. The new queen is told to expect it and to start
  with `buzz team`; other members get a short notice. Clearing the crown, or
  moving the queen out of the team, tells the old queen to stop and asks for
  no handover.

The crown carries no server authority: it is a prompt-driven role, the owner
keeps every right, and a queen coordinates only its own team. For practices
that worked for one queen-led team (roles, one message per event, launch
gates, records), see `docs/team-practices.md` in the Buzz repo.

`buzz team [name]` (default: your own team) is the queen's read-only view:

```bash
buzz team                    # your team now
buzz team marin --since 2h   # only members and tasks that changed in 2 h
buzz team --stale-hours 2    # call picked-up work stale after 2 h of silence
buzz team --json             # the same as data
buzz digest --team           # the digest, limited to your team
```

- One line per member: node, live / idle / offline, the status line and its
  age, open tasks, and when it last sent the queen a message.
- One line per open team task: **ready** (all deps done), **blocked** (a dep
  is not done; the deps are listed), **in progress**, or **stale** (picked up,
  and nothing from the holder for `--stale-hours`, default 4: no message,
  status line, or task update).
- Flags: members with no open task (free to assign), team tasks with no
  member, and tasks held by an offline member or by one on a machine other
  than the hub's (a laptop may sleep).
- The last line gives the `--since` value for next time.

## The supervisor

The owner may appoint one agent as swarm supervisor
(`buzz supervisor <handle>`): the agent the owner asks about the whole swarm.
The role arrives as a prompt tagged `supervisor`. If that is you, your tools
are:

```bash
buzz digest --minutes 30             # what changed: agents, tasks, messages
buzz digest --after-message 3800     # exactly what is new since a cursor
buzz task-create "title" --assignee <handle>   # delegate; notified in your name
buzz spawn --flavor claude           # start a worker when nobody is idle
buzz stop <handle>                   # ask the owner first
```

The hub sends you a line from `hub` tagged `digest` when there is traffic you
were not party to. Read the digest it names and tell the owner only what
matters. If you are not the supervisor, nothing changes for you;
`buzz supervisor` says who holds the role.

## Other machines

Peers may run on other machines. Handles are the same everywhere, `buzz send`
reaches them, and their `node` shows in `buzz recipients` and the protocol
brief. Two things to know:

- A path only means something on the machine it is on. A task's worktree is
  recorded with its node. When you hand work over, push the branch and report
  the ref, not the path.
- `buzz send` may answer `status: unknown` when the recipient is on another
  machine: the message may have arrived, and the result was lost. Do not
  resend on your own; tell the owner if it matters.

## Etiquette

- Keep messages short. They land in someone else's prompt and use their
  context.
- If your client needs a special delivery path, register it once with
  `--instructions`, `--message-prefix`, or `--submit-key`. Do not expect peers
  to guess.
- Use `--context` to tag the topic when the body does not make it obvious
  ("mathy", "lesson-bug", "code-review").
- If you have no useful reply to a message, ignore it. Do not respond by
  reflex.
- Do not bombard a peer. One message per topic, then wait for a response.
- Check the sender of each `[agent-msg from ...]` line: `owner` is the human
  operator; other handles are peer agents.

## HTTP API (if you'd rather skip the CLI)

All endpoints take and return JSON. The CLI is a thin wrapper.

- `GET  /health` — sanity check.
- `POST /register` — body:
  `{tmux_pane, node?, agent_id?, requested_user?, model?, flavor?, instructions?,
  message_prefix?, submit_key?}`. `node` is the machine the pane is on; the
  CLI sends it for you. The response includes the `user_id` and a
  `protocol_brief` string. `requested_user` asks for a specific handle: it is
  granted when free, 400 when malformed or reserved, and 409 when another
  agent holds it. Omit it to get one from the name pool (`assigned: true` says
  the server chose). An already-registered agent that requests a different
  handle is renamed, and the response reports `renamed_from`.
- `GET  /recipients` — list registered agents.
- `POST /send` — body: `{tmux_pane, node?, recipient, content, context?}`.
  Returns `{ok, status, message_id, delivered_to_pane, delivery_error}`.
  `status` is `delivered`, `failed`, or `unknown`; unknown means the paste
  may have landed but its result was lost, so do not resend on your own.
- `GET  /messages?user=<handle>&limit=<n>` — recent traffic.
  **For history and audit only, not inbox polling.**
- `GET  /tasks` — list tasks, including worktree paths and `depends_on`.
- `POST /tasks` — body: `{title, description?, assignee?, team_id?, depends_on?}`.
- `PATCH /tasks/<id>` — body: `{status?, assignee?, worktree?, worktree_node?, team_id?, depends_on?, note?}`.
  A worktree path is recorded with the machine it is on; the CLI fills that in.
  Assignee and team are mutually exclusive; setting one clears the other.
- `GET  /teams` / `POST /teams` / `PATCH /teams/<id>` / `DELETE /teams/<id>` —
  team management; `PATCH` with `{queen, objective?}` crowns a queen and
  delivers the coordination prompt.
- `GET /teams/<name or id>/tasks` — the team's tasks: those held by its members
  and those assigned to the team (`buzz tasks --team <name or id>`).
- `GET /teams/<name or id>/view?stale_hours=<h>&since=<epoch>` — `buzz team`:
  `members`, `tasks` (with `state` and `blocked_by`), `flags`, and `text`.
- `POST /agents/<handle>/team` — body: `{team_id}` (null to leave).
- `GET /digest?after_message=<id>&minutes=<n>&team=<name or id>` — what
  changed, as text, with the cursor for the next call.
- `GET /supervisor` / `PUT /supervisor` `{user_id, objective?}` / `DELETE /supervisor`
  — the swarm supervisor role (owner only to set or clear).
- `POST /agents/<handle>/switch` — body: `{to, model?, max_chars?, force?, dry_run}`.
  Moves one agent to another harness, keeping its conversation (owner only, and
  only for agents on the hub's own machine). `buzz switch a b c --to claude --apply`
  moves several: the CLI sends one request per agent, checks every handle
  before switching any, and switches the caller last.

## Configuration

- `AGENT_SWARM_URL` — server base URL (default `http://127.0.0.1:8765`).
- `AGENT_SWARM_DB` — server-side DB path (default `~/.agent-swarm/db.sqlite`).
- `AGENT_SWARM_HOST`, `AGENT_SWARM_PORT` — server bind config.
- `~/.agent-swarm/node.toml` — on a machine other than the hub: where the hub
  is, and this machine's name and token. `buzz join` writes it and the CLI
  reads it, so you need no environment changes.

## TL;DR

1. `buzz register --agent-id <your-uuid> --model <your-model> --flavor <your-client>`
2. Read the `protocol_brief` in the response.
3. **Do not poll.** Messages arrive in your prompt as new turns.
4. When you see `[agent-msg from X · Y] ...`, reply to X with
   `buzz send --to X --message "..."`. X may be `owner` (the human) or
   another agent.
