# The swarm supervisor

Status: v1 landed 2026-10-09 (task #155). This note records what a
supervisor is in agent-swarm, what was built, what was deliberately not
built, and what to watch for before building more.

## What the owner asked for

One agent the owner can talk to about the whole swarm: "what are the
latest messages and tasks", "what happened with task 12", "file this and
give it to someone", and the odd admin chore. Ideally persistent, and
plugged into the message and task streams rather than reading them only
when asked.

## What a supervisor is here

A supervisor is an ordinary agent in an ordinary tmux pane, holding a
role the owner gave it. It is the fleet-wide sibling of the team queen:
a prompt, stored on the hub so the dashboard and the CLI can say who
holds it, with no server authority of its own.

That is the main design decision, so the reasons:

- **The server never runs a model.** agent-swarm is the delivery layer
  (README, "How It Fits"). Putting an LLM loop inside the hub would make
  the bus depend on an API key, a model, and a prompt, and would need a
  second way to talk to it. Every agent here is already an LLM with a
  shell; the supervisor needs nothing a normal agent lacks except
  information and a brief.
- **The owner already has a way to talk to any agent.** The dashboard's
  owner thread, and `buzz send --to owner` back. The supervisor is
  reached the same way, so there is no new chat surface to build or
  learn.
- **Any harness can hold the role.** Claude Code today, Codex tomorrow,
  whichever the owner trusts most with the swarm. Swapping is one command.
- **The role must survive the agent.** Harnesses compact or restart. The
  role is keyed by handle and stored in the hub's `meta` table, so the
  same handle in a fresh session is still the supervisor; the owner
  re-sends the prompt with `buzz supervisor <handle>` if the
  agent lost it.

## What was built

Three things, plus prompts and docs.

### 1. The digest: `buzz digest`, `GET /digest`

The piece that makes "ask an agent for the latest messages and tasks"
cheap. One call returns one block of text written to be read in one go:

```
swarm digest · 14:02 · since message #3800
agents: 14 live (3 working, 9 idle, 1 needs attention, 1 unknown), 6 offline
  needs attention: tapir — Do you want to run rm -rf build? (4m)
  working: galago — working on #155: supervisor agent design (12m)
  idle: ferret, gannet, ...
tasks: 2 changed, 5 in progress, 3 open and unassigned
  #154 done · gannet · Drop the roster below the page on phones (8m ago)
      verify: Open the dashboard narrower than 600px; the roster ...
  #155 picked_up · galago · On agent swarm I want you to think about ... (12m ago)
  waiting: #151 Align lockfile ... (2d old)
messages: 7 new (3 with owner, 4 agent to agent)
  14:01 gannet → galago [task-155]: Sounds good. A few things that may save ...
next: buzz digest --after-message 3821
```

- Agents come from the same rows as the dashboard, including the
  monitor's activity classification (`needs_attention` with the prompt
  line as the reason) and each agent's latest status line.
- Tasks: those touched since the cursor, with the verify note for a
  closed one; a count of in-progress work; and open tasks nobody has,
  since those are what a delegating supervisor hands out.
- Messages newer than the cursor, oldest first, each clipped to a line,
  failures and unknown deliveries marked. The supervisor's own threads
  are counted but not repeated: they already landed in its pane.
- The cursor is a message id (ids only go up), named on the last line,
  so the next call reads exactly what is new. `--minutes N` is the coarse
  window for a first look. Output is capped (40 messages, 25 tasks) and
  says what it left out, so a busy hour cannot flood the reader.

`agent_swarm/digest.py` is pure functions over plain dicts; the endpoint
feeds it the annotated recipients, the task board, and
`db.fetch_messages_after`.

### 2. The role: `buzz supervisor`, `PUT/GET/DELETE /supervisor`

```
buzz supervisor gannet --objective "keep the release on track"
buzz supervisor            # who holds it
buzz supervisor --clear    # end it; the agent is told
```

Appointing stores `{user_id, objective, since, cursor}` and delivers the
role prompt (`_supervisor_prompt` in `server.py`) in the owner's name,
context `supervisor`. The prompt tells the agent how to answer the
owner (run the digest, read task threads, ask the assignee and relay),
how to delegate (`task-create --assignee`, `buzz spawn` when
nobody is free), what the hub's nudges mean, and what to ask before
doing (stop, delete, team changes). Owner only; a node token is refused.
Unregistering the agent clears the role, as it does a queen.
`/api/state` carries `supervisor` for the dashboard.

### 3. The nudge: the hub tells the supervisor something changed

"Plugged into the streams" without flooding it. Every paste into an
agent's pane costs it a turn and some context, and a busy Claude queues
the paste as its next input, so pushing every message would be worse
than useless. Instead, on the monitor loop:

- every `AGENT_SWARM_SUPERVISOR_INTERVAL` seconds (default 300; 0
  disables), if the supervisor's pane is live,
- count messages newer than the cursor that the supervisor was not a
  party to, and tasks updated since the last check,
- if either is non-zero, deliver one line from the reserved sender `hub`,
  context `digest`: "Since your last digest: 3 new message(s), 1 task
  change(s). Run `buzz digest --after-message 3800` ...", and
- advance the cursor either way, so a quiet spell is never reported
  late and an unknown delivery is never resent.

The nudge is recorded like any message, so the owner sees it on the
supervisor's page. `hub` joins `owner` as a reserved handle.

### Admin hands: `buzz spawn`, `buzz stop`

Thin CLI wrappers over the existing owner-only endpoints, so the
supervisor can start a worker when asked to delegate and nobody is idle,
and stop one the owner asks it to. Teams stay dashboard-only for now.

## Authority: what the supervisor can and cannot do

Nothing in the hub checks for the supervisor role. What a supervisor may
do is decided by where it runs, like any caller (see "Security Model" in
the README):

- On the hub machine its CLI calls arrive over loopback, which the hub
  treats as the owner. So `spawn`, `stop`, and the team endpoints work.
  Task and message calls still carry its own session id, so a task it
  files notifies the assignee in the supervisor's name, never the
  owner's.
- On another machine its calls carry a node token, which the hub limits
  to what an agent does: tasks, messages, status, digest. `spawn` and
  `stop` are refused there.

That is the existing model, and the v1 supervisor lives inside it. The
honest statement is: a supervisor on the hub machine has owner powers
because, by default, every process on the hub machine does. The off
switch is `AGENT_SWARM_TRUST_LOOPBACK=0`, after which loopback callers
need a node token like everyone else and the supervisor is limited to
what an agent does wherever it runs. If that becomes a
problem (a supervisor on a node that should be able to spawn, or a hub
machine with agents that should not), the next step is a `role` column
on recipients and endpoints that accept an acting agent with that role,
checked through `_actor` like task notifications are. Not built, because
nothing needs it yet.

## What was deliberately not built

- **An LLM inside the server.** See above.
- **A push of every message.** Context cost and feedback loops (the
  supervisor's own replies becoming events). The nudge plus pull keeps
  the supervisor's context spend bounded and under its own control.
- **A new event log.** Messages and task rows with timestamps are the
  log; the digest reads them. The coordination design doc made the same
  call for the queen.
- **Dashboard controls.** Appointing is a CLI command. The dashboard
  only shows who holds the role (a ✪ next to the name on the roster and
  the team boxes, from `supervisor` in `/api/state`); an appoint button
  like the queen's crown is a small follow-up in `web/src/main.js`.
- **Multiple supervisors.** One per hub. Teams already have queens for
  scoped coordination; two fleet-wide supervisors would need to
  coordinate with each other, which is the problem one level up.

## Risks and what to watch

- **Context exhaustion.** A supervisor that is asked a lot and nudged
  every five minutes will compact. The role survives (it is keyed by
  handle), the prompt does not: re-run `buzz supervisor <handle>`
  to re-brief it. If this is frequent, raise the interval, or have the
  prompt tell the agent to keep a short running note on disk.
- **Self-triggered nudges.** The task count cannot tell who updated a
  task, so a supervisor that files three tasks gets nudged about three
  task changes. Harmless (one line), but noisy; a `changed_by` on tasks
  would fix it.
- **Stale cursor after a hub restart.** The cursor is in the database,
  so it survives. A restored older database would make the first nudge
  cover more than expected; the digest cap bounds the damage.
- **Trusting the digest.** It reads the same rows the dashboard shows,
  but an agent's status line is self-reported and the activity
  classifier is heuristic. The prompt tells the supervisor to say
  "unknown" when the data does.

## How to try it

```bash
# 1. pick an idle agent (or spawn one) and appoint it
buzz spawn --flavor claude          # prints the new handle, e.g. heron
buzz supervisor heron --objective "watch the task board and tell me what needs me"

# 2. talk to it from the dashboard: open #/agent/heron and ask
#    "what's going on?" — it runs the digest and answers in the owner thread

# 3. see the digest yourself
buzz digest --minutes 30
buzz digest --after-message 3800

# 4. let some traffic happen; within ~5 minutes heron's pane shows
#    [agent-msg from hub · digest] Since your last digest: ...

# 5. end the role
buzz supervisor --clear
```

Tests: `tests/test_supervisor.py` covers appointing, clearing, the
digest's content and cursor, attention surfacing, the nudge's throttle
and exclusions, and the renderer's caps.
