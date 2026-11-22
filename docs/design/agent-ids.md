# Stable agent IDs and reusable handles

Task #547. Proposed design for review.

Buzz currently uses `recipients.user_id` as both identity and address.
Taking over an offline handle can consequently inherit its messages and
tasks. Give each agent a permanent ID and treat the handle as an address
that can be freed. Retirement removes an agent from active use while
preserving its record. Erasing stored history would be a separate operation.

## Data model

- `agents(id INTEGER PRIMARY KEY AUTOINCREMENT, handle, created_at, retired_at)`
  is the identity table. A partial unique index on normalized `handle`
  where `retired_at IS NULL` covers active, offline and reserved agents.
  Keep the last handle on retired rows, reserve system names, and never
  recycle IDs within a hub. Offline and retired are separate states.
- `agent_sessions(agent_id, harness, session_id, state)` maps a harness
  session to one Buzz ID. Use a unique key on (harness, session_id),
  keeping superseded and retired sessions as tombstones so stale clients
  cannot register them as new. Allow at most one current session per
  agent. If a harness has a narrower session namespace, include its
  stable scope in the key and document how it travels across nodes.
  Today's `recipients.agent_id` is a harness session string. Call that
  field `session_id` in the new protocol.
- Rekey `recipients` as an optional registration/binding row keyed by
  `agent_id` with a foreign key to `agents`. Keep node, tmux identity,
  reservation, model, instructions and team membership here. A binding
  is replaceable. A retired identity has no live binding or membership.
- Messages store ID references for agent senders and recipients, with a
  checked discriminator for system actors such as owner and hub. Audit
  legacy values before deciding which are system actors. Rebuild
  conversation, search and deduplication indexes around the new keys.
  Preserve message IDs, timestamps, delivery results, reply links and
  attachments. Pins already key on message ID and need no DB rewrite.
- Tasks store `assignee_agent_id`, teams store `queen_agent_id`, and
  summaries store `agent_id`. The supervisor setting stores an agent ID
  with its existing message cursor. Team IDs, task IDs and dependencies
  stay stable. Audit other handle-keyed state, including activity maps,
  digests, message search indexes and browser read/unread cursors.
- Browser cursors, tabs, chat drafts and selection state key on hub and
  agent ID. Translate old keys once through the immutable migration map
  before enabling reuse. Drop state that cannot be mapped unambiguously.
  A reclaimed handle starts with no chat, drafts, unread cursor, tasks
  or roles inherited from its previous holder.

## Lifecycle

**Register and resume.** Resolve a known current harness session to its
Buzz ID, validate the caller's node and pane ownership, then update its
binding. An exact, verified existing pane may support same-pane
re-registration for a sessionless harness. A new pane without a known
session needs an owner-authorized restore or a new identity. Pane labels,
handle strings and model names are insufficient proofs. Reject a copied
session that is already bound to another live pane and reject stale
sessions. A session ID is a lookup key and does not grant permission.

**Retire.** Owner selects an ID. Atomically mark it retired, revoke its
binding, pending handoff and session eligibility, clear team membership,
queen and supervisor roles, and release the handle. Preserve historical
assignments and status lines. Flag unfinished tasks with a retired
assignee for reassignment and keep their worktree metadata. Exclude those
tasks from active agent load. Preempt or close the pane through the
existing node operation if the owner requests it. The hub commits
retirement even if the node cannot confirm shutdown, so a reconnect
cannot restore the old registration. Reports should show that shutdown
outcome separately. Unregister, offline pruning and retirement need
distinct semantics. Disconnection leaves the identity and handle intact.

**Reclaim.** Register a new session with the freed handle and allocate
a new ID in the same transaction. A non-retired handle, including an
offline one, conflicts if it belongs to another ID. Allow explicit
reclaim first. Keep automatic allocation conservative until the owner
opts into auto-reuse. Two competing requests must produce one winner.

**Rename.** Update the display handle on the same ID after checking
active uniqueness. History, memberships, role assignments and links
follow the ID. Handles are displayed using the agent's current name
or the last name at retirement. Old handle URLs need the compatibility
rule below.

**Switch harness.** The owner or another actor already authorized by
the existing switch policy starts an ID-bound handoff. For a launch that
creates the destination session asynchronously, issue a single-use,
expiring claim tied to the expected harness, node and launch, consumed
when registration binds the new session. Atomically switch the current
session and supersede the old one. Failed or canceled launches must not
give a second session control of the identity. Use a binding generation
or compare-and-swap to reject delayed launch replies after retirement
or a newer switch. Store both sessions for diagnosis and stale rejection.

## API, CLI and dashboard

Continue accepting `buzz send --to stoat` and other handle selectors
for interactive targeting of the current non-retired agent. If that
agent is offline, report normal delivery failure and record it against
its ID. Resolve `--to-queen` through the team's ID reference. For scripts
and durable targets expose an explicit ID selector such as `--to-id`.
Expose `agent_id` as the integer and `session_id` as the harness string
in versioned payloads. Keep the handle as display metadata. Use IDs for
actor authorization, dashboard writes, task assignment, mentions that
are structured references, and retry jobs. Resolve once at the boundary
and store the selected ID. A queued send or retry can fail if that ID
retires, but must never follow the handle to the next holder.

Use a distinct ID route such as `#/agents/id/123` and an ID-based API
route. Cut over generated links and rewrite old handle routes through
the frozen migration map where known. If no historical mapping exists,
send the visitor to agent search. A deliberate handle lookup can still
find the current holder. Label ambiguous display names with a retirement
date, for example `stoat (retired 11-22)`, with the ID available if two
retirements share a date. Keep retired profiles and chat visible in
history, search and pinned-message navigation. Hide retired agents
from active rosters, send targets and assignment controls. Profile and
conversation controls become read-only on retirement. Preserve
message jumps by message ID. Scope tabs, DOM keys, filtering and unread
counts by ID so two instances of the same handle never collapse.

## Remote nodes, snapshots and imports

The hub allocates IDs and owns lifecycle decisions. Nodes execute
operations on verified (node, tmux server, pane) bindings. A raw
`PaneSnapshot` stays an observation of tmux state. It cannot prove
identity. Saved restore manifests carry schema version, hub UUID, Buzz
ID, session key, node and layout metadata. Verify an active identity,
current session and binding generation before restoring. Never schedule
a retired or superseded session, and coalesce duplicate restores by
Buzz ID. A moved agent requires explicit authorization to transfer its
binding. Legacy manifests may resolve through a unique current session
within the original hub and authorized node. Unmatched or ambiguous
entries require manual reconciliation. A matching handle or pane
label cannot restore identity.

Distinguish layout restore from full database restore. A full restore
keeps the same hub UUID and IDs, but restoring an older backup also
rolls back retirements and can rewind the ID sequence. Before reopening
a restored hub, reconcile lost retirements and fence IDs allocated
after the backup (recover the high-water mark, or rotate the hub
identity and invalidate old references if it cannot be recovered).
Reject stale restore claims before reconnecting nodes. Version bundle
exports separately. Foreign IDs are scoped to their source hub and
translated through a persistent import mapping. Remap message, task,
team and role references in a transaction. A handle collision results
in an allocation conflict or a distinct imported handle, never a
merge. For legacy exports without stable IDs, scope synthetic identities
to the source export and map all local references consistently. Keep
duplicate-import checks.

## Migration and rollback

Rehearse against a SQLite backup of production size (roughly 56k
messages), with writes disabled on the copy. Measure time, temp/WAL
space and the duration of the production pause. Inventory all handle
references, including metadata and browser keys. Create one ID per
current handle and one retired placeholder per historical-only handle
from the union of references, excluding system actors. Mark imported
retirement dates as unknown rather than inferring a date from last
activity. Already conflated histories cannot be separated reliably.
Report duplicate session keys, orphan references and normalized handle
collisions and resolve them before cutover.

During cutover, pause the hub and other writers, drain outstanding
deliveries, and take a verified SQLite backup using the backup API
or `.backup` so committed WAL data is included. Save the old binary
and configuration. Build and backfill tables in a versioned,
transactional migration, preserving row IDs and sequence high-water
marks. Save a frozen handle-to-ID map for legacy links and browser
migration. Rebuild derived indexes and caches. Verify integrity and
foreign keys, per-table counts, per-agent history totals, message
thread order, pins, replies, tasks, roles and representative restore
fixtures. Restart with a schema-compatible build and smoke-test local
and remote delivery and resume. Keep reclaim disabled during validation.

On failure before reopening writes, roll back the transaction or
restore the verified backup and old build together. After reopening,
reverting to a pre-cutover backup discards newer writes. Preserve the
current DB first and prefer a forward fix. After any handle reuse, a
general downgrade to handle keys is lossy. Recovery to the old build
then requires an explicit outage and reconciliation of all post-backup
writes under distinct handles, or owner acceptance of data loss. Never
run an old binary against a schema it does not understand.

## Landing sequence and cost

1. Inventory references and fixtures. Add migration and verification
   tooling with reclaim disabled. Rehearse backup, migration and rollback
   on a copy. Land the migration tooling before selecting a cutover.
2. Convert `db.py` persistence and indexes and move `server.py`
   boundaries and authorization to ID resolution. This is the main
   sweep: audit roughly 150 SQL statements in `db.py`, including
   dynamic filters, projections and import SQL. Update `names.py`,
   `message_index.py`, summaries, digests, activity and `team_view.py`.
   Keep handle projections at compatibility boundaries during rollout.
3. Convert `client.py`, `protocol.py`, `nodes.py`, `node.py`,
   `restore.py`, `handoff.py`, `restart.py` and `bundle.py`. Verify
   mixed versions or require coordinated upgrade where old clients
   cannot safely address by ID. Cut over dashboard routes, chats,
   history, task/agent selectors and persisted state in `web/src`.
   Rebuild packaged static assets at implementation time.
4. Enable retirement and reclaim after proving the full path. Test
   retire/reclaim with the same handle across messages, pins, unread,
   tasks, role routing, old URLs, delayed sends, offline nodes, and
   both legacy and new restore/import. Remove temporary compatibility
   projections once callers move.

Biggest risk is a missed handle lookup that exposes or mutates the
previous holder's state. Treat cross-identity writes, stale node
observations, session collisions, and imports that merge by handle as
release blockers. Test two distinct IDs with the same display handle
wherever history and live state meet.
