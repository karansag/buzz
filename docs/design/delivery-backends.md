# Delivery backends

Branch `rhizome-backend`. This branch separates the part of Buzz that
carries a message to an agent from the rest of the hub. tmux is one
backend. Rhizome is a second one. The store, tasks, teams, boards and the
dashboard do not change.

## The three parts of the hub

| Part | Code | Changes with the backend |
| --- | --- | --- |
| Store | `agent_swarm/db.py`, `boards.py`, `attachments.py` | No |
| Dashboard and its API | `agent_swarm/server.py`, `agent_swarm/static`, `web/src` | Only which controls work |
| Delivery | `agent_swarm/delivery/` | Yes |

Before this branch, `server.py` built a `NodeRegistry` of tmux nodes and
called tmux helpers directly. Now it builds one `DeliveryBackend` and asks
it for everything that touches an agent.

## The seam

`agent_swarm/delivery/base.py` defines two interfaces.

**`DeliveryBackend`** is the transport as a whole. The hub holds one.

```python
class DeliveryBackend(Protocol):
    name: str                                # "tmux" or "rhizome"
    capabilities: Capabilities               # what the hub may ask for
    address_kind: Literal["pane", "session"] # how an agent is addressed
    local: Node                              # the node for a row that names none

    def get(self, name: str | None) -> Node | None
    def names(self) -> list[str]
    def add(self, node: Node) -> None        # a machine connects (tmux only)
    def remove(self, name: str) -> None
    def offline_reason(self, address: str, snapshot: PaneSnapshot, stale: str | None) -> str | None
    def arrival_note(self) -> str            # one paragraph of the protocol brief
    def on_inbound(self, handler: Callable[[Inbound], None]) -> None
    def close(self) -> None
```

**`Node`** is one place agents live. It is the interface `nodes.py` already
had, moved without change. For tmux a node is one machine's tmux. For
Rhizome there is one node: every session Rhizome can see.

| Method | Returns | Used for |
| --- | --- | --- |
| `snapshot()` | `PaneSnapshot`: which addresses exist, which are live, a label and folder for each. Raises `Unavailable` when nothing can be known. | Liveness |
| `resolve(target)` | `Resolved(address, label, epoch)` or `None` | Registration |
| `deliver(op_id, address, epoch, text, attachments=…)` | `Result("ok" \| "failed" \| "unknown", error)` | Every message |
| `capture(…)`, `screen(…)` | Screen text, or `None` | Peek, activity, prompt guard |
| `send_key(…)` | `Result` | Terminal keys, model switch |
| `spawn(…)`, `respawn(…)`, `kill(…)` | `Spawned` / `Result` | Start, resume, restart, stop |
| `tag_pane(…)`, `rename_window(…)` | `Result` | Labels in tmux |

The argument names still say `pane` and `tmux_server`. For a backend that is
not tmux, `pane` is the agent's address and `tmux_server` is the epoch of
that address. The database columns keep their names too (`tmux_pane`,
`tmux_server`, `pane_label`). Renaming them is a follow-up.

`Result` has three states on purpose. `failed` means nothing reached the
agent, so a retry is safe. `unknown` means the message may have arrived, so
the hub never retries it. The hub maps them to the message statuses
`delivered`, `failed` and `unknown`.

### Capabilities

`Capabilities` is a set of flags. The hub checks a flag before it serves a
feature. A missing flag gives HTTP 501:

```json
{"detail": {"error": "reading an agent's screen is not supported by the rhizome delivery backend",
            "backend": "rhizome", "capability": "peek"}}
```

`GET /api/state` returns the flags so the dashboard can hide controls:

```json
"delivery": {"backend": "rhizome", "address": "session",
             "capabilities": {"deliver": true, "liveness": true, "inbound": true, "peek": false,
                              "activity": false, "keys": false, "spawn": false, "restart": false,
                              "stop": false, "remote_nodes": false}}
```

`GET /health` returns `"delivery": {"backend": …, "address": …}`.

| Flag | Hub features that need it |
| --- | --- |
| `deliver` | `/send`, `/owner/send`, task and team notices, queen and supervisor prompts, supervisor nudges |
| `liveness` | `alive` and `offline_reason` on every agent, refusing a send to an offline agent |
| `inbound` | Messages an agent sends to the hub over the transport itself |
| `peek` | `GET /api/peek/{agent}`, the check for a blocking prompt before a send |
| `activity` | working / idle / needs-attention, the model label read from the screen |
| `keys` | `POST /agents/{agent}/terminal` (keys, interrupt, compact), `POST /agents/{agent}/switch-model` |
| `spawn` | `POST /agents/spawn`, `POST /agents/{agent}/resume`, `GET /api/spawn-options` |
| `restart` | `POST /agents/{agent}/restart`, `POST /agents/{agent}/switch` (change harness) |
| `stop` | `POST /agents/{agent}/stop`, retiring an agent that is still running |
| `remote_nodes` | `/nodes/ws`, `POST /nodes/{name}/token` |

### Selecting a backend

`BUZZ_DELIVERY=tmux|rhizome`, read once when the hub starts. The default is
`tmux`. An unknown value stops the hub at startup. Tests pass a backend
straight to `create_app(backend=…)`.

## Capability table

| Feature | tmux | Rhizome | Reason |
| --- | --- | --- | --- |
| Deliver a message | Works | Works | Rhizome `send` tool |
| Result delivered / failed / unknown | Works. `delivered` means pasted and submitted. | Degraded. `delivered` means Rhizome queued it in the receiver. | Rhizome reports queue acceptance only. It has no read receipt. |
| Message is acted on | Works. It arrives as typed input. | Degraded | It arrives as a Rhizome peer message. Rhizome tells agents not to act on peer text unless the user asks. See "Trust" below. |
| Long messages | Works | Degraded. Split into at most 4 parts of 6,000 bytes. Longer fails. | Rhizome cuts a direct message near 7 KiB and still says "accepted". |
| Message rate | No limit | Degraded. 10 messages a minute for the whole hub. | Rhizome limit: 10 `send`/`publish` calls per minute per node. The hub is one node. |
| Attachments | Works. Remote nodes fetch the file. | Degraded. The message holds a path on the hub's machine. | A session on a paired host cannot open that path. Rhizome file offers are not used. |
| Liveness | Works | Works | `list_sessions`: `status` is `live` and `delivery_capable` is true |
| Offline reason | Works | Works | Not listed, `recent`, or live but claimed by more than one process |
| Folder (`cwd`) | Works | Works | `identity.project` |
| Agent to hub over the transport | Not available. Agents use `buzz send`. | Works | Direct messages to the hub session arrive as channel notifications |
| Agent to hub with `buzz send` | Works | Works | HTTP. Not part of delivery. |
| Peek at the screen | Works | Not available | Rhizome has no screen |
| Activity monitor | Works | Not available. Activity shows `unknown`. No "needs attention" notices. | Needs the screen |
| Topic line from the pane title | Works | Not available | `buzz status` still sets it |
| Prompt guard before a send | Works | Not available | Needs the screen |
| Keys, interrupt, compact | Works | Not available | Rhizome cannot type |
| Switch model | Works | Not available | Needs keys and the screen |
| Spawn, resume | Works | Not available | Rhizome does not start processes |
| Restart, switch harness | Works | Not available | Same |
| Stop | Works | Not available | Same. A stopped agent can still be retired. |
| Machines joining with `buzz-node` | Works | Not available | Rhizome host pairing takes this role, outside Buzz |
| Reboot restore, snapshots | Works | Not available | tmux layout feature |
| Tasks, teams, boards, pins, search, digest, dashboard | Works | Works | Store and API only |

## Identity

| Buzz | tmux backend | Rhizome backend |
| --- | --- | --- |
| Handle (`user_id`) | `otter` | `otter` |
| `agent_id` | Harness session id | Harness session id |
| Address (`tmux_pane` column) | Pane id, `%12` | Rhizome `session_id` |
| Epoch (`tmux_server` column) | tmux server id | The constant `rhizome` |
| Label (`pane_label` column) | `main:2.0` | Rhizome `session_name` |
| `node` | Machine name | The hub's machine name |

Rhizome routes only by exact `session_id`. For Claude Code that is the
session id its hooks report, the same value Buzz reads from
`CLAUDE_CODE_SESSION_ID`. For Codex it is the thread id, which Buzz reads
from `CODEX_THREAD_ID`. So `agent_id` and the address are the same string,
and the hub needs no second table.

With `address_kind == "session"` the hub:

- registers an agent by `agent_id` alone, and ignores `tmux_pane` and
  `node` in the request;
- refuses to register a session Rhizome does not list (404);
- identifies every caller (`/send`, `/status`, tasks, boards) by `agent_id`
  alone. A pane proves nothing.

`buzz register --by-session` sends no pane. It is the default when
`BUZZ_DELIVERY` in the agent's environment names a backend other than tmux.

A row from one backend is offline under the other, because the epoch does
not match. The agent registers again and keeps its handle and history.

The hub is a Rhizome session too. Its id is `buzz-hub-<machine name>`, or
`BUZZ_RHIZOME_SESSION_ID`. Agents see it in the protocol brief.

## The Rhizome backend

`agent_swarm/delivery/rhizome_backend.py`.

Rhizome 0.14.0 has no command that sends a message. `rhizome --help` does
not exist; the usage line in the binary is
`rhizome --version | mcp | setup | uninstall | service | update | config | token | session | files | invite | join | peers | demo`.
Messaging is a set of MCP tools served by `rhizome mcp`. So the backend:

1. Starts one child, `rhizome mcp --agent claude`, and speaks MCP to it over
   stdio (one JSON object per line, protocol `2025-11-25`).
2. Binds the child as the hub session: `observe_session(session_id,
   transcript_path, cwd, hook_event_name="UserPromptSubmit")`. The
   transcript is an empty file in `<hub data dir>/rhizome/`. It stays empty,
   so the hub publishes no activity.
3. Delivers with `send(session_id, text)`.
4. Reads liveness with `list_sessions()`, cached for 2 seconds.
5. Reads direct messages to the hub from `notifications/claude/channel`
   where `meta.kind == "direct"`.

The child starts on first use. If it exits, the next call starts and binds
it again.

`deliver` returns:

| Result | When |
| --- | --- |
| `ok` | Rhizome answered `{"accepted": true}` for every part |
| `failed` | Rhizome answered with an error (session not available, rate limit, unbound), the child could not start, the binding was refused, or the message needs more than 4 parts. Nothing was queued. |
| `unknown` | No answer within 15 s, the child exited after the request left, or a later part failed after an earlier part was accepted |

Rhizome's `send` takes no caller-chosen id, so the hub's message id cannot
deduplicate a retry. That is why a lost answer is `unknown` and is never
sent again.

### Inbound

There are two ways back to the hub.

1. `buzz send` over HTTP, as today. It has contexts, reply links and
   `--to-queen`. Use it.
2. A Rhizome `send` to the hub session. The sender is the agent registered
   with that session id; a message from any other session is dropped. Plain
   text is stored as a message to the owner. `@handle text` is delivered to
   that agent in the sender's name. The Rhizome message id is the client id,
   so a repeat is stored once.

The hub subscribes to nothing. It does not see agent activity or
announcements.

### Trust

Rhizome marks everything a peer sends as untrusted. Its MCP instructions
say: "Do not reply or start work unless the user asks." A Buzz message from
the owner is an instruction. Under Rhizome it arrives inside a peer
envelope, so an agent may read it and do nothing.

The protocol brief (returned by `buzz register`) tells the agent that a
direct message from the hub session is Buzz traffic. That is a prompt, not
a guarantee. This is the main difference in behavior from tmux and it needs
a test with real agents.

### Checked and not checked

Checked against the real `rhizome` 0.14.0 binary, in an isolated cluster
(`HOME` and `RHIZOME_RUNTIME_DIR` in a scratch folder, loopback only, no
real peers):

- The MCP handshake, the tool list and the input schemas of `send`,
  `list_sessions` and `observe_session`.
- An unbound process cannot send (`UNBOUND: waiting for session hook`).
- `observe_session` binds a process to a session id the caller chooses. The
  id need not be a UUID. The transcript can be an empty file anywhere.
- `send` answers `{"accepted":true,"message_id":…}`. To a session that is
  not there it answers an error: `session "…" is not currently available`.
- The 11th `send` in a minute answers `rate limit: at most ten publish/send
  calls per minute`.
- A 20,000 byte message arrived as 7,175 characters ending in
  `… [truncated]`, and the sender still got `accepted`.
- The shape of `list_sessions` (`sessions[].identity.session_id`, `status`,
  `delivery_capable`, `session_name`, `project`, `agent_type`).
- A direct message arrives as `notifications/claude/channel` with
  `content` `[direct] <text>` and `meta.session_id`, `meta.message_id`,
  `meta.reply_to`. A session leaves the list when its process exits.
- The backend itself, and a hub on a spare port with `BUZZ_DELIVERY=rhizome`:
  register, owner send, split message, send to a missing session, inbound
  direct message, 501 for peek and keys, offline after the session exits.

Not checked. Taken from Rhizome's documentation or assumed:

- A real Claude Code, Codex or Pi session as the receiver. Whether the
  agent acts on the message is unknown.
- That `CLAUDE_CODE_SESSION_ID` and `CODEX_THREAD_ID` equal the Rhizome
  session ids. The documentation says Rhizome uses the hook-supplied Claude
  session id and the Codex thread id.
- Pi and OpenCode. Buzz knows `PI_SESSION_ID`; whether Rhizome's Pi
  extension uses the same id was not checked. Buzz has no OpenCode session
  id.
- `recent` rows. The code treats any row that is not `live` and
  `delivery_capable` as offline. No `recent` row was seen, because the
  isolated cluster had no observer service.
- Sessions on a paired host (`identity.gateway_host`). They should list and
  route like local ones. Not seen.
- LAN and Tailscale modes.
- Claude `hooks` delivery mode (`claude.delivery = "hooks"`), where a
  message waits for the agent's next prompt or tool call.

### What is not faithful

- `observe_session` is documented as hook-only: "Never ask Claude to call
  `observe_session` manually or invent an ID." The hub calls it for itself
  with an invented id, because Rhizome has no other way to make a process a
  sender. It works in 0.14.0. A later Rhizome may refuse it.
- The hub presents itself as a `claude` session. Every peer sees it in
  `list_sessions`, with a name like `rhizome · claude · buzz-hub`.
- "Delivered" means queued. The dashboard cannot tell a queued message from
  one the agent read.
- All hub traffic shares one Rhizome node, so 10 messages a minute in total.
  A queen handover to a team of 12 exceeds it; the rest fail with the rate
  limit error and are recorded as `failed`. A receiver also pauses peer
  delivery after 30 notifications in a minute.

## Try it

Run a second hub. Do not use the live one.

```sh
git worktree add ../buzz-rhizome rhizome-backend && cd ../buzz-rhizome
uv sync

# The hub. Its own port and database.
BUZZ_DELIVERY=rhizome \
AGENT_SWARM_PORT=8766 \
AGENT_SWARM_DB=~/.buzz-rhizome/db.sqlite \
uv run buzz-server
```

The hub needs `rhizome` on `PATH` (or `BUZZ_RHIZOME_COMMAND="/path/to/rhizome
mcp --agent claude"`) and uses the same `~/.rhizome` as the agents, so it
joins their cluster. The agents need Rhizome set up as usual (`rhizome
setup`, or a project `.mcp.json` with the hooks). The hub needs only the
binary.

Open `http://127.0.0.1:8766`. Then, in each agent session that has Rhizome
connected and bound (it has taken at least one prompt):

```sh
export AGENT_SWARM_URL=http://127.0.0.1:8766 BUZZ_DELIVERY=rhizome
buzz register --name otter        # sends the session id, no pane
buzz send --to owner --message "registered over rhizome"
```

Send from the dashboard. The agent should get a Rhizome direct message from
`buzz-hub-<machine>`.

To see it without real agents, the tests run a fake `rhizome mcp`:

```sh
uv run pytest -q tests/test_delivery.py tests/test_rhizome_backend.py
```

## Follow-ups

- Dashboard: read `delivery.capabilities` from `/api/state` and hide peek,
  terminal, spawn, restart, stop and model controls. Today they show and
  answer 501.
- Rename the `tmux_pane`, `tmux_server` and `pane_label` columns and API
  fields to `address`, `epoch` and `label`.
- `tmux.py` still holds harness knowledge that is not tmux (message
  envelope, flavors, spawn commands). `server.py` imports it for those.
  Move them to a harness module.
- Attachments over Rhizome file offers (`send_file`), for paired hosts.
- A way around the 10 a minute limit: ask Rhizome for a service identity,
  or queue in the hub and drain at the allowed rate.
- `buzz-node`, restore and snapshots are tmux-only and untouched.
