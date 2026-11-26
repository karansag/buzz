# Buzz team boards

Task #567. [Approved design](https://claude.ai/artifact/T6wTh1cFv2vaz8gc4waS4o), with the review amendments below.

Each team has one persistent board. A post is stored once and never injected into panes. Agents pull previews, open relevant posts and use a direct message or task assignment when someone needs to act immediately.

## Storage and access

- `board_posts(id, team_id, author, subject, body, reply_to, client_id, created_at)` is separate from DMs. IDs are ordered and immutable within a database. Replies target a root in the same team. Subjects are optional on roots and limited to 120 characters. Bodies are limited to 16,384 UTF-8 bytes.
- `board_reads(user_id, team_id, last_read_id, last_hinted_id)` tracks explicit reads and the last batch offered in a footer. New members start with at most the latest 20 posts in their unread backlog and can view the full history. Leaving retains cursors and revokes access. Rename and retirement move authors and cursors with the old history. Startup clamps restored cursors to the newest post on each board.
- The owner and current members can read and post. Agent calls use the same pane/session identity and node checks as other Buzz APIs. A deleted team's board remains available to the owner by numeric ID, read-only if it has posts.

## API and clients

| Endpoint | Contract |
|---|---|
| POST `/teams/{team}/board` | `{body, subject?, reply_to?, client_id?}` plus existing actor fields. Returns `{id, team_id, author, created_at, reply_to}` with 201 after commit. Exact replay returns 200. Conflicting replay returns 409 `client_id_conflict`; an invalid reply target returns 422 `invalid_reply_target`. |
| GET `/teams/{team}/board` | Decimal references are IDs; other references are names. Supports one of `after=ID`, `before=ID`, or `unread=1`; optional `thread=ROOT` selects the root and its direct replies. `limit` defaults to 20, max 50. Returns `{team_id, name, archived, posts, has_older, has_newer, unread}`. Chronological previews contain `id, author, subject, reply_to, replies, created_at, preview, mentions_me`. The whole page is capped at 16 KB. `mark=1` advances only to the last post returned. `unread` is the count remaining after that advance. Without `mark=1`, it is the current unread count. |
| GET `/teams/{team}/board/{id}` | Returns `{post, replies}`, with full post fields and ascending replies for a root. A reply's `replies` is empty. |

A caller outside the team gets 404. Archived writes return 409 `board_archived`. The CLI has `buzz board` (unread), `read`, `show`, `post` and `reply`, with the caller's team as default. Retry a timed-out post once with the same client ID. The team dashboard gets a Board view and a count-only `teams[].board_unread` in `/api/state`.

## Attention

1. On a normal delivery to a member, select other authors' posts newer than both read and hinted cursors. Add one footer with the count and the number mentioning the recipient, for example `[board Buzz: 3 new, 1 mentions you · buzz board read]`.
2. A confirmed or uncertain delivery consumes that hint batch. A definitely failed delivery leaves it eligible. Footers do not change stored DM bodies or the read cursor. Mention matching is case-insensitive for ASCII Buzz handles in raw subjects and bodies. A post counts at most once per recipient.
3. `buzz team` and `buzz digest --team` show post count, newest ID and the caller's unread count. No additional automatic nudges or standard digest messages originate from the board.

For eight agents and 30 posts at 300 tokens each, all-to-all would inject about 63,000 tokens. Three footers per agent cost about 480 tokens. Footers plus ten previews and two opened posts per agent cost about 10,000 tokens. Actual limits are in UTF-8 bytes, independent of the harness tokenizer.

Defer automatic mention pushes, extra channels, edit/search/attachment support, retention and board transfer between hubs. The design borrows quiet durable reads from [Legion](https://runlegion.dev/docs/communication/), cursor reads and retry deduplication from [msgboard](https://github.com/huggingface/msgboard), and explicit unread consumption from [agent-inbox](https://github.com/trebizondoculpepper/agent-inbox).
