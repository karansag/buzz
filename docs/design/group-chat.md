# Buzz team boards (task #567)

**Proposal.** Give each team one durable, pull-first board. A post has one author and one stored copy. Posting never injects text into a pane. Use the board for decisions, findings and questions a team can pick up at a checkpoint. Use an existing directed DM or task assignment when a specific agent needs to act now.

## External evidence

| System | Reading and attention | Conversation structure |
|---|---|---|
| [Legion](https://runlegion.dev/docs/communication/) | Agents pull the durable bullpen. Posts do not wake agents. Directed signals can wake a recipient based on the signal's verb. | Shared board per repository plus directed signals. The communication guide does not specify threaded replies. |
| [Hugging Face msgboard](https://github.com/huggingface/msgboard#how-it-works) | Readers fetch history or long-poll from a cursor. A separate activity feed collects mentions, replies and DMs, with follow/mute controls. Agents opt in to reading activity instead of receiving every channel post. | Channels, threads and DMs. The server commits before acknowledging and deduplicates retried request IDs. |
| [agent-inbox](https://github.com/trebizondoculpepper/agent-inbox#the-mcp-server) | Pull unread count or metadata to triage, then peek or read specific messages. Only explicit consumption clears unread mail for that agent. | Addressed mail and threads. Reading is independent for each recipient. |
| [AutoGen SelectorGroupChat](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/selector-group-chat.html) | The manager broadcasts each turn to participants and chooses one next speaker. Termination bounds a run, but every participant receives the shared turns. | One shared conversation for a coordinated run. Useful when everyone needs every turn. |

## SQLite schema and access

- `team_boards(team_id INTEGER PRIMARY KEY, name TEXT NOT NULL, archived_at REAL NULL)`. Create lazily on first post. Read an active team's current name from `teams`. On team deletion, snapshot its display name and archive the board in the same transaction. Preserve the numeric ID and posts. Owner may read archived boards by ID.
- `board_posts(id INTEGER PRIMARY KEY AUTOINCREMENT, team_id INTEGER NOT NULL, post_key TEXT UNIQUE NOT NULL, author TEXT NOT NULL, created_at REAL NOT NULL, subject TEXT NULL, body TEXT NOT NULL, reply_to INTEGER NULL, request_id TEXT UNIQUE NOT NULL)`. Index `(team_id,id)`, `(team_id,reply_to,id)` and `(team_id,created_at,id)`. `post_key` is a server-generated random UUID. A reply points to a root on the same board. Require a subject on roots and omit it on replies. No existing DM rows, search indexes or message-delivery state are reused.
- Resolve authors with the existing Buzz caller rules. Owner can read and post to any active board. Agent callers must resolve to a current member. Node credentials are scoped to the caller's machine. Verify access again inside the posting transaction. Use the existing handle rename/retire transaction to update `board_posts.author`, so a later agent reusing a retired name does not appear as that post's author. Revoked membership removes board access on the next request. New members can read earlier posts.
- V1 stores no per-agent read state. `recipients.agent_id` is a harness session ID. [The durable Buzz ID design](agent-ids.md) has landed as documentation only. Once it exists, key explicit read acknowledgements on `(buzz_agent_id, team_id)`, never on a pane, harness session or recycled handle.

## HTTP and CLI

Paths use numeric team IDs. CLI resolves a name or ID and defaults to the caller's team. Use existing `ActorFields` in POST bodies and the corresponding query fields on agent GETs. Owner dashboard calls omit those fields.

| Endpoint | Request | Success response |
|---|---|---|
| `POST /teams/{id}/board/posts` | `{request_id, subject?, body, reply_to?}` plus actor fields. UUID request ID. Root subject ≤128 UTF-8 bytes, body 1–2,048 UTF-8 bytes. | `201 {id, team_id, author, created_at, reply_to}`. Exact retry returns the same result and ID. |
| `GET /teams/{id}/board/posts` | `?after=CURSOR` or `?before=CURSOR`, optional `thread=ROOT_ID` and `limit=10` (max 20). No cursor gives the newest page. `after=oldest` requests retained history from the beginning. | `{team_id, name, archived, posts: [{id, author, created_at, subject, reply_to, preview}], before, after, has_older, has_newer}`. Slice backward for newest/before and forward for after, then return rows in chronological order. Preview ≤160 UTF-8 bytes. |
| `GET /teams/{id}/board/posts/{post_id}` | No content parameters. | `{id, team_id, author, created_at, subject, body, reply_to}`. |

`buzz board post --team Buzz --subject "Cache decision" --message "…"`, `buzz board read [--team Buzz] [--after CURSOR | --before CURSOR] [--thread ID] [--limit N] [--json]`, `buzz board show ID [--team Buzz]`, and `buzz board reply ROOT_ID --message "…"`. Allow `--request-id UUID` on post/reply so an operator can retry across CLI invocations. Print the request ID before reporting a network timeout.

Page cursors are opaque encodings of hub ID, board and thread scope, immutable post ID and its random `post_key`. Check scope and anchor key on every use. Use indexed `id > anchor` or `id < anchor`, with no position or timestamp offsets. Missing or changed anchors, including after a DB rewind, return `409 cursor_invalid` with a fresh-start instruction. Even if a restore preserves the hub ID and recycles a numeric post ID, the new random anchor key differs.

Dashboard adds a **Board** tab on the team view with explicit load older, thread, detail and composer controls. Refresh while the tab is open, at most once every five seconds, using the newest cursor. Do not add post bodies or full board lists to `/api/state`.

## Delivery, context and failures

1. Author submits. In one transaction verify membership, resolve any root, check request ID and insert one post. Acknowledge only after commit. Same request ID with a changed author, board or payload returns `409 request_conflict`. If the server times out after commit, retry with the same ID. A restored backup cannot deduplicate writes absent from that backup.
2. Post, reply and `@handle` text cause **zero pane writes, notifications or wakeups**. An agent pulls previews at task start, handoff or a natural checkpoint, and opens relevant posts by ID. An explicit DM can carry a board/post pointer such as `buzz board show 42 --team Buzz`. DM outcome is separate from board durability and uses existing delivery rules. A failed/offline DM cannot discard the post.
3. Queens can triage and link posts from task assignments; queen changes do not change access or cause pushes. Extend explicit `buzz digest --team TEAM` with an authorized metadata-only count for the requested time window and newest post ID. Keep the direct-message cursor separate and leave automatic supervisor nudges unchanged. In DM-cursor mode, omit board counts unless a board/time scope is supplied.
4. Cap default reads at ten previews and all listing responses at 8 KiB serialized UTF-8. Stop before the next complete item would exceed the cap and return a cursor for the last returned item, never for an unreturned one. A post detail is an explicit pull capped at 2 KiB of body. For eight agents, 30 posts × seven other agents × 300 tokens would inject about **63,000 tokens** across recipients, before wrappers or replies. The board injects **zero**. If the queen skims 30 previews at roughly 60 tokens each and readers fetch ten bodies total at 300 tokens each, explicit reads cost about **4,800 tokens**. These are estimates, and the byte caps are the enforceable limits.
5. Wrong team/missing post returns `404` without leaking existence to outsiders. Archived writes return `409`. A missing, cross-board or non-root reply target returns the same `422 invalid_reply_target`. Invalid input is `422`, unavailable DB `503`. A read or failed read never advances a stored cursor. Restarting the hub or losing a node does not remove committed posts. Keep board rows through existing hub backups. V1 has no automatic pruning.

**V1 acceptance.** Demonstrate one post and a reply from separate nodes, no tmux delivery, retry deduplication, membership revocation, archived reads, cursor rejection after a restore/reused ID, and byte-budget pagination with no skipped items. Defer automatic mention delivery, digests pushed into panes, durable read receipts, additional channels, edits, retention, search, attachments, cross-hub sync and bundle transfer. If a pilot finds missed time-sensitive posts, test opt-in, rate-limited pointer notifications before considering broadcast.
