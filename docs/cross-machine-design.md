# Cross-machine agents: hub and node design

Status: implemented on master as of 2026-09-28 (steps 0 to 3 of the
plan below; step 4 is this documentation). Each decision records what
was chosen, the alternatives weighed, and what changed in review by the
hoopoe agent, which also reviewed every commit. Where the code differs
from the text below, the code won: the node's session fence is a local
object rather than the hub's generation number, a spawned pane carries
the server that created it from the creation command itself, a node
token may only touch agents on its own machine, and task notifications
from agents go out in the agent's name. Not built: the owner login for
reverse-proxy dashboards and `import-tasks`; see docs/roadmap.md.

## The problem

agent-swarm is single-machine in every layer, and the assumption is
load-bearing rather than incidental:

- The server binds `127.0.0.1` and identifies an agent by its tmux
  pane id (`%12`) plus the local tmux server id. Both are meaningful
  only on the host that runs that tmux server.
- `/send` resolves the sender from the caller's pane. A CLI on another
  machine has no way to say who it is.
- Delivery, the activity monitor, peek, spawn, stop, and pane titles
  all shell out to the local `tmux` binary (`agent_swarm/tmux.py`).
- Image attachments are delivered as an absolute path on the server's
  disk, which a pane on another machine cannot open.
- The dashboard, task board, and teams read one SQLite file.

The goal is for agents in tmux panes on several machines to register,
message each other, share one task board and team structure, and show
up on one dashboard, with the same commands and the same
`[agent-msg from ...]` contract they use today.

## What master already has

Three recent changes shape this design:

- `de10c12` addresses agents by pane id and tmux server id instead of
  position. That is the right local half of a cross-machine address.
- `577325a` sends a host name with every registration
  (`AGENT_SWARM_NODE` or the short hostname) but only uses it to build
  the handle; it is not stored. That field becomes the `node` column.
- `b27aacb` adds image attachments delivered as hub-local paths, which
  needs a cross-machine answer (decision 6).
- `1666b85` removed the in-session model picker, so there is no
  keystroke choreography left to move across the wire.

## Prerequisite: bare handles

Agreed with hoopoe on 2026-09-23. Auto-assigned handles currently
append harness, model line, and host
(`hoopoe-codex-gpt5-karanslinux`). All three are mutable or better
kept as columns, and the host is stored nowhere else. Hoopoe's own
handle says `gpt5` while it runs GPT-6.

Before the hub work, as one commit:

- Handles come from the pool bare; a numeric suffix only when the
  pool is exhausted. The 48-character requested-name limit stays so
  existing long handles remain legal.
- The reported host is persisted as `node` on the recipient and shown
  next to flavor and model in `recipients`, the protocol brief, and
  the dashboard card. It is never inferred from an old suffix.
- `handle_tag`, `model_line`, `host_tag`, and the tag parameter on
  `pick_unused` are deleted.
- No automatic renaming. Existing handles stay, including suffixed
  ones. Re-registering with `--name` is an explicit rename that
  rewrites message and task references. While suffixed handles exist,
  pool selection treats `foo-anything` as reserving bare `foo`.
- Existing recipient rows get `node = <hub name>` as a one-time
  local-data migration. That is justified by the rows' existing local
  tmux ownership, not by parsing a handle suffix.

## Decision 1: topology

**Chosen: one hub, thin nodes.** One server stays the single source
of truth: handles, messages, tasks, teams, monitor state, dashboard.
Every other machine runs `buzz-node`, a small daemon from the
same package that drives its local tmux and nothing else. The hub
machine's own tmux is served in-process through the same interface.

Run the hub on the machine that stays on. On this tailnet that is
`karans-linux`; the MacBooks show offline for days at a time, and an
agent on a sleeping laptop is offline whether or not the hub is there.

Alternatives:

- **Hub drives remote tmux over SSH.** No daemon on nodes. Review
  corrected an overstatement in the first draft: SSH does not force
  one round trip per tmux call, because the hub can invoke one remote
  helper (`buzz-node deliver ...`) that does the paste, delay,
  submit, and verify locally. That makes SSH a credible prototype if
  avoiding a persistent daemon were the dominant requirement. It is
  not chosen because continuous monitoring, reconnect, spawn, and
  capability reporting all want a long-lived process, and because it
  needs hub-to-node SSH keys next to the Tailscale identity that
  already exists. Because the hub reaches nodes through one `Node`
  interface, an `SshNode` can be added later without touching the
  hub's logic.
- **Federated servers, one per machine.** Tasks, teams, queens, and
  dependency graphs live in one file today, and the value of the tool
  is that the owner sees one board. Federation either replicates that
  state or elects one server as authoritative, which is the hub design
  with more parts and a dashboard split per machine. Hoopoe agreed
  there is no case for it at this scope.

## Decision 2: connection direction

**Chosen: one outbound WebSocket from node to hub.** The node opens a
socket to `AGENT_SWARM_HUB` and keeps it open. Commands go down the
socket with an operation id and a deadline; results come back tagged
with the id; observations (decision 3) stream up on the same socket.
The socket is the heartbeat. Nodes never listen and never publish a
callback URL, auth is enforced only on the hub, and a node behind a
network that blocks inbound connections still works.

The first draft chose the reverse (node runs an HTTP listener, hub
calls it, node announces a callback URL with a heartbeat). Review
preferred the socket because it removes the second listener, the
second auth surface, and the callback-address bookkeeping, and gives
one channel for commands, results, and observations. Cost accepted:
the hub keeps per-node connection state and needs the protocol below.

Socket protocol, all of which the implementation must specify:

- Every command carries `op_id`, `kind`, `deadline` (hub clock,
  absolute), and the arguments. The node drops a command whose
  deadline has passed when it is dequeued, so a laptop waking from
  sleep never executes an old queued paste.
- Every result carries the `op_id` and one of `ok`, `failed` (with
  reason), or `unknown` (the node cannot say whether the side effect
  happened, for example a crash between paste and result).
- Bounded queues in both directions; a full queue fails the oldest
  command with `unknown` rather than blocking.
- Hello on connect: node name, protocol version, package version,
  tmux server id, harness binaries available, capabilities.
- Heartbeat with a timeout in both directions; reconnect with backoff
  on the node side.
- Connection generation: each connection gets a number; a new
  connection fences the old one, and results arriving on a fenced
  connection are discarded. On reconnect the hub re-snapshots the
  node's panes before marking its agents available.
- A connected socket does not mean tmux is healthy. The hello and
  every observation batch carry the tmux server id; a node whose tmux
  is gone reports that and its agents read offline.
- Mutating operations on one pane are serialized on the node, so a
  paste and a kill cannot interleave.

## Decision 3: monitoring placement

**Chosen: node captures and streams; hub classifies.** The node
captures its registered panes on the hub's interval and sends
observation batches up the socket: pane id, exists, foreground
command, title, capture hash and capture text when changed, a
sequence number, and the tmux server id. A batch is sent every tick
even when nothing changed, which is the liveness signal. The hub runs
`activity.step` exactly as today. On reconnect the hub discards old
observations and resets stale activity timers.

Alternative: run the classifier on the node and push only status
changes. Rejected for v1. `activity.step` changed this week
(`e0377a5`); keeping it in one process avoids version and reset
semantics across two, and the traffic saved is unmeasured. Revisit
with measurements.

## Decision 4: addressing

An agent's address is `(node, pane id, tmux server id)`. The node
name is `AGENT_SWARM_NODE` or the short hostname, sent by the CLI on
register and send, stored as `recipients.node`. The hub's own node
name is its hostname.

Review added a rule the first draft lacked: **every pane operation
carries the expected tmux server id, and the node checks it at
execution time.** Checking only at the hub allows a tmux restart
between observation and delivery to target a reused `%N`. Under
direction B this is one field on every command.

Node-side resolution: `register` may send a positional target
(`agents:1.0`) as it does today. Resolution to a pane id happens on
the node named in the request, never against the hub's tmux. The
pane migration in `agent_swarm/panes.py` runs per node against that
node's own snapshot. In practice every legacy row belongs to the hub
node, because no remote row can exist before this lands; remote
legacy migration is therefore not needed, and the
`server_start_time` versus `registered_at` heuristic never has to
compare clocks across machines. If that ever changes, a remote
ambiguous row requires fresh registration rather than a guess.

One tmux socket per node in v1: the default socket for the user the
daemon runs as. A server id (`pid:start_time`) identifies a server
but does not tell tmux how to connect to it, so a socket selector is
a later addition, if ever.

Handles stay global and server-assigned from the one pool, so
`puffin` means the same agent from every machine. A requested handle
is a hub-wide claim: first registration wins regardless of node, and
a later request for a taken, live handle gets a 409 naming the owning
node.

Schema: `recipients` gains `node TEXT NOT NULL`; uniqueness becomes
`(node, tmux_pane, tmux_server)`. `tasks` gains `worktree_node`
(decision 7). `messages.delivered` becomes a three-way status
(decision 8). A `nodes` table records `name, token_hash, last_seen,
version, tmux_server, harnesses, generation`.

## Decision 5: auth

Today there is no auth and the server binds loopback. Once the hub
listens on the tailnet, anyone who reaches it can type into every
registered pane on every machine, so the tailnet-auth item in the
roadmap stops being deferrable.

**Chosen: per-node bearer tokens bound to node identity.**
`buzz node-token <name>` on the hub creates or rotates a
token, prints it once, and stores only a hash. The node daemon and
the CLI on that machine send it as `Authorization: Bearer`. The hub
derives the node from the token and **rejects a register or send
whose claimed `node` differs from the authenticated one**, so one
node cannot impersonate another. Revoking a laptop is deleting its
row.

This also resolves a contradiction review found in the first draft,
which had announce overwrite an address while a second machine with
the same name got a 409. Identity is the token, not the name: the
same token reconnecting fences the previous connection and carries
on; a different token claiming an enrolled name is refused.

Owner operations (dashboard sends, task and team changes, spawn,
stop, relabel) are authorized separately from node tokens. A node
token can register, send, read recipients and messages, and update
its own tasks; it cannot act as the owner.

Listeners and the browser, stated explicitly because review showed
the first draft was wrong here:

- The hub listens on loopback and on its Tailscale IP. Binding only
  the Tailscale address would drop the loopback listener the local
  dashboard uses; binding `0.0.0.0` is acceptable only because every
  non-loopback request requires a token.
- Loopback requests without a token are trusted by default
  (`AGENT_SWARM_TRUST_LOOPBACK=1`) so the local dashboard keeps
  working. When `tailscale serve` or any reverse proxy fronts the hub,
  remote requests arrive on loopback, so the operator sets
  `AGENT_SWARM_TRUST_LOOPBACK=0` and the dashboard authenticates.
- Dashboard authentication is a login page that POSTs an owner token
  and sets an HttpOnly, SameSite=Strict cookie. No token in a query
  string. Mutating dashboard requests check `Origin`.

Alternatives:

- **One shared token.** Less to manage, but every laptop holds the
  hub's entire authority and a lost one means rotating every machine.
- **Tailscale identity headers** via `tailscale serve`, or **tsnet**
  embedding. Not needed for v1 on a single-user tailnet; revisit if
  the tool ever serves more than one person.

## Decision 6: attachments

Attachments are stored under the hub's database directory and pasted
into panes as `[attached image: /abs/path]`. On a remote node that
path does not exist.

**Chosen: structured attachment ids, rendered on the recipient
node.** A deliver command carries the message text and a list of
attachment ids; the hub does not format paths into the text. The node
fetches each id it does not already have from the hub's
authenticated `GET /attachments/{name}`, validates the type, size,
and content hash, writes atomically under its own
`~/.agent-swarm/attachments`, and only then renders the
`[attached image: <local path>]` lines and pastes. A failed fetch
means delivery has not started; the result is `failed`, never a
half-delivered message. The node's cache keeps a file for at least
the hub's retention window after last delivery, so an agent that
opens a path minutes later still finds it.

Alternative: a shared filesystem or `rsync` between machines.
Rejected because it adds a setup step outside agent-swarm and breaks
silently when it is missing. Sending bytes down the socket is
possible but HTTP fetch is simpler and reuses the endpoint.

## Decision 7: spawn and repositories

Spawn takes a node and a structured request: harness, model, autonomy,
and a working directory. The node validates the harness binary and
the directory exist before launching and returns a useful error
otherwise. Available harnesses come from the node's hello, so the
dashboard's spawn control only offers what that node has.

Review corrected the first draft's claim that a worktree's node can be
read off the assignee: reassignment or an agent moving nodes changes
that inference while the files stay put. Tasks therefore persist the
worktree as `(worktree_node, worktree)`, set from the updating agent's
node. The existing convention (branch `task/<id>`, one worktree per
task, queen integrates one branch at a time) works across machines
when workers push. The queen prompt gains one sentence: a worker must
push its branch and report the remote ref and commit when marking a
task done, and the integrating agent fetches it. A local path alone
is not a handoff.

## Decision 8: delivery semantics

Review's top finding. Today the hub records a message after
`tmux.deliver` returns, in one process, so the window in which a
message is delivered but unrecorded is microseconds. Across a network
that window becomes ordinary: a node can paste and submit
successfully and the result can be lost. That outcome is *unknown*,
not failed, and replaying it would submit the message twice.

Rules:

- The hub records the message with status `pending` **before**
  dispatch, and the message id is the command's `op_id`.
- The node keeps a bounded, durable record of recently executed
  mutating op ids (deliver, spawn, kill, title). A command whose id
  it has already executed returns the recorded result instead of
  running again.
- Message status is `delivered`, `failed`, or `unknown`. Unknown is
  shown on the dashboard as such, with a resend control for the owner.
  The hub never replays an unknown mutation on its own. Read-only
  operations (observe, capture, panes) retry freely.
- Exactly-once is not promised. A crash on the node between the tmux
  side effect and recording its result is still ambiguous, and the
  design says so rather than papering over it.
- Deadlines on every command (decision 2) so a stale paste is never
  executed on wake.
- `unreachable` and `confirmed absent` are distinct: the node reports
  that a pane is gone; the hub infers nothing from a dropped
  connection. Prune therefore cannot delete a registration because of
  a network failure; it only removes panes a node has confirmed gone.
- Dispatch handles failure immediately. The three-missed-heartbeats
  rule sets the dashboard's node status; a send to an agent on a node
  with no live socket fails at once with `node unreachable`.

## The node daemon

`agent_swarm/node.py`, console script `buzz-node`. On start it
connects to `AGENT_SWARM_HUB` with its token, sends hello, then loops:
execute commands from the socket, stream observations on the
interval. Command kinds and what they do:

| Kind             | Arguments                                                      | Notes |
|------------------|----------------------------------------------------------------|-------|
| `panes`          | none                                                           | pane id, label, command, title for every pane; plus tmux server id |
| `resolve`        | `target`                                                       | positional or id target to pane id on this node |
| `capture`        | `pane, tmux_server`                                            | dashboard peek |
| `deliver`        | `pane, tmux_server, text, attachments, message_prefix, submit_key, flavor` | paste, delay, submit, verify-retry, all local; dedup by op id |
| `spawn`          | `harness, model, autonomy, cwd`                                | validates binary and cwd; returns pane id and label |
| `kill`           | `pane, tmux_server`                                            | |
| `title`          | `pane, tmux_server, title`                                     | |
| `rename_window`  | `pane, tmux_server, name`                                      | |

Observation batches go up unrequested on the interval the hub set in
its hello reply.

## Hub changes

`agent_swarm/nodes.py` defines the interface both sides use:

```python
class Node(Protocol):
    name: str
    def panes(self) -> PaneSnapshot: ...
    def resolve(self, target) -> tuple[str, str] | None: ...
    def capture(self, pane, tmux_server): ...
    def deliver(self, op_id, pane, tmux_server, text, *, attachments, message_prefix, submit_key, flavor, deadline) -> Result: ...
    def spawn(self, op_id, harness, model, autonomy, cwd, deadline) -> Result: ...
    def kill(self, op_id, pane, tmux_server, deadline) -> Result: ...
    def set_title(self, pane, tmux_server, title): ...
    def rename_window(self, pane, tmux_server, name): ...
```

`LocalNode` calls `tmux.py` directly and always returns `ok` or
`failed`. `RemoteNode` wraps one socket connection and can return
`unknown`. A `NodeRegistry` on `app.state` maps name to `Node`,
seeded with the local node and updated as sockets connect and fence.

Every place `server.py` calls `tmux.*` changes to go through the
recipient's node. Review was right that calling these edits
mechanical is optimistic: the call sites change shape because results
gain the `unknown` state, messages are recorded before dispatch
rather than after, and every operation carries a server id. Expect a
behavior-level pass over `/send`, `/owner/send`, task notification,
spawn, stop, prune, and the monitor tick, with tests for the unknown
path on each.

## CLI and per-machine setup

`register`, `send`, and `whoami` already send the host; it is renamed
`node` and persisted. The CLI and the node daemon read one per-machine
config file, `~/.agent-swarm/node.toml`, written once by
`buzz join`:

```bash
buzz join http://karans-linux:8765 --token <from: buzz node-token karans-macbook-pro>
# writes ~/.agent-swarm/node.toml: hub url, token, node name (short hostname unless --node)
```

Environment variables (`AGENT_SWARM_URL`, `AGENT_SWARM_TOKEN`,
`AGENT_SWARM_NODE`) override the file when set, and the loopback
default applies when neither exists, so a single-machine install
needs no file at all.

A file rather than shell-profile exports because an agent already
running in a tmux pane inherited its environment at launch and cannot
pick up new exports; its harness runs `buzz register` as a
subprocess, which reads the file. That is what makes migration below
a re-register rather than a restart. The bundled register skills work
unchanged.

## Dashboard

- Each roster chip and bee carries the node name; the roster groups
  agents under node headers once more than one node exists.
- A node strip near the spawn control: name, connected dot, last
  seen, agent count, harnesses available. A disconnected node's agents
  collapse into the stopped group with the reason.
- The spawn control gains a node select limited to that node's
  harnesses, and a working-directory field.
- Messages with status `unknown` show a marker and a resend control.
- Peek, the composer, and model relabeling work unchanged because the
  hub proxies.

## Migrating existing machines

Two kinds of machine exist today, and the hub cannot tell which from
outside because a local server binds loopback.

**A machine with agents in tmux but no server of its own.** Nothing to
migrate. Install the package, run `buzz join`, start
`buzz-node`, and have each agent register with the hub; the
register skill does it on request. Each gets a handle from the hub
pool.

**A machine running its own agent-swarm server.** It has its own
handles, messages, tasks, teams, and attachments. Its agents were
registered by `agent_id` (a Claude conversation UUID or the Codex
equivalent) which the hub has never seen, so re-registration creates
a fresh hub row with no clash, and registering twice returns the same
hub handle. The old database is archived, not merged:

1. On the hub, after steps 0 to 2 of the implementation plan are
   deployed: `buzz node-token karans-macbook-pro`.
2. On the machine: pull, reinstall, stop its server (`fuser -k
   8765/tcp` or `launchctl bootout`), rename its database to
   `db.sqlite.pre-hub`, run `buzz join` with the token, start
   `buzz-node` as a launchd or systemd user service.
3. Ask each live agent to register. It keeps running in its pane; the
   CLI reads the new config file. An agent that wants its old handle
   asks for it with `--name`; the hub grants it when free and refuses
   it when a live hub agent already holds it, in which case the agent
   takes the assigned one. The register response's protocol brief
   lists its peers under their hub handles.
4. `buzz export` on that machine writes its agents, teams, and
   tasks (and, with `--with-messages`, its history) to a JSON bundle,
   reading its database without writing to it. `buzz import
   BUNDLE --node <machine>` on the hub takes them in as one
   transaction: agents arrive as reservations holding their handles
   until they register, clashing handles and team names are imported
   under fresh ones with every reference remapped, tasks keep their
   status, notes, and dependencies under new ids, and worktree paths
   keep the machine they are on. A dry run reports all of it first, and
   importing the same export twice is refused.
5. Message history is optional and arrives as history: never delivered
   again, tagged `imported`, with attachments left behind and noted.
   Task numbers inside old message text refer to the old board.

Rollback on that machine is stopping the node daemon, restoring the
archived database, and starting its old server; nothing in the
archive was modified. The hub's own rows are migrated once with
`node = <hub name>`, as the prerequisite section says.

Why not merge the databases: handle, task id, and team id collisions
would each need rewriting across messages and task references, and
the text of old messages cannot be rewritten reliably. The live board
is what matters, and open tasks carry it.

## Failure behaviour

| Situation | Behaviour |
|-----------|-----------|
| Node daemon down or laptop asleep | Socket drops; the node reads disconnected at once for dispatch and after the heartbeat timeout for the dashboard. Its agents show offline with the reason; sends fail immediately with `node unreachable` and are recorded. On reconnect the hub re-snapshots panes, then agents return with the same handles. |
| Hub down | Nothing works anywhere, including hub-local agents. Same as today; run the hub on the always-on machine. |
| Hub restarts | Nodes reconnect with backoff; nothing on the node side needs restarting. In-flight commands at the moment of restart are `unknown`. |
| tmux restarts on a node | The node reports a new server id in its next batch; rows bound to the old one read offline until the agent re-registers, exactly as `de10c12` handles it locally. Commands carrying the old server id are refused by the node. |
| Node crashes between paste and result | Result `unknown`; message shown as unknown with a resend control; never replayed automatically. |
| Command dequeued after its deadline | Dropped on the node, result `failed: expired`. |
| Pane gone on a live node | Node confirms absence; same as today: pane no longer exists; prune removes it. Prune never acts on a disconnected node's rows. |
| Attachment fetch fails on the node | Delivery does not start; result `failed` with the reason. |
| Wrong, missing, or revoked token | 401 naming the variable; a revoked node's socket is closed. |
| Different token claims an enrolled node name | Refused; the operator rotates the token or renames the node. |

## Implementation plan

Each step leaves the single-machine path working and the tests green.

0. **Bare handles and the node column** (prerequisite, one commit).
   Delete the handle tag code, persist `node`, migrate existing rows
   to the hub node, show it in recipients, protocol brief, and
   dashboard card.
1. **Node interface and delivery semantics, local only.** Add
   `nodes.py` with `Node`, `LocalNode`, `NodeRegistry`, the `nodes`
   table, `worktree_node`, three-way message status, and
   record-before-dispatch. Route every `tmux.*` call in `server.py`
   through the registry. No network change yet; tests monkeypatch
   `LocalNode` and cover the unknown path.
2. **Node daemon and socket transport.** Add `node.py`, the
   `buzz-node` script, the socket protocol (op ids, deadlines,
   fencing, hello, heartbeat, observation batches), `RemoteNode`,
   per-node tokens with node-claim validation, and attachment fetch
   with dedup. Test `RemoteNode` against the daemon in-process with
   tmux monkeypatched, including deadline expiry, duplicate op ids,
   and reconnect fencing.
3. **Dashboard.** Node names, node strip, spawn node select and cwd,
   unknown-message marker and resend, login page and loopback trust
   switch. Rebuild the committed portal assets.
4. **Docs.** README section "Multiple machines", `AGENT_PROMPT.md`
   note that peers may be on other machines and paths are per node,
   `docs/upgrading.md` entry, roadmap item closed.

Rough size: `node.py` and `nodes.py` about 600 lines together,
`server.py` diff about 250, `db.py` and `client.py` about 100, web
about 150. Four focused sessions; the socket protocol and its tests
are the bulk.

## Verification

- Scratch hub on this machine (`AGENT_SWARM_PORT=8799`,
  `AGENT_SWARM_DB=/tmp/hub.sqlite`), scratch node on the MacBook
  pointed at it over the tailnet, one Claude pane on each. Register
  both, send in both directions, confirm the bracketed paste lands
  and submits on the remote pane, confirm the dashboard shows both
  with node names and live peek.
- Paste an image into the remote agent's chat; confirm the pasted
  path is on the MacBook and the agent can open it.
- Kill the node daemon mid-delivery (a paste with a long verify
  delay); confirm the message shows unknown, is not replayed on
  reconnect, and the resend control works once.
- Put the MacBook to sleep with a send queued: within the heartbeat
  timeout the dashboard shows the node disconnected and the send has
  failed with the node reason. Wake it: the queued command is
  expired, not executed; the agent returns with the same handle.
- Restart tmux on the MacBook; confirm its agents read offline with
  the stale-server reason and a delivery carrying the old server id
  is refused by the node.
- Spawn a Codex agent on the remote node from the dashboard into a
  chosen directory and stop it.
