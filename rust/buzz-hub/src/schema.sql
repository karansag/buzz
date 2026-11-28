CREATE TABLE IF NOT EXISTS recipients (
    user_id     TEXT PRIMARY KEY,
    tmux_pane   TEXT NOT NULL,
    agent_id    TEXT,
    model       TEXT,
    flavor      TEXT,
    instructions TEXT,
    message_prefix TEXT,
    submit_key  TEXT,
    registered_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS retired_agents (
    archive_id TEXT PRIMARY KEY,
    original_id TEXT NOT NULL,
    agent_id TEXT,
    retired_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_retired_agent_id ON retired_agents(agent_id);
CREATE INDEX IF NOT EXISTS idx_retired_original_id ON retired_agents(original_id);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sender      TEXT NOT NULL,
    recipient   TEXT NOT NULL,
    context     TEXT,
    content     TEXT NOT NULL,
    ts          REAL NOT NULL,
    delivered   INTEGER NOT NULL DEFAULT 0,
    delivery_error TEXT,
    status      TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_recipient_ts
    ON messages(recipient, ts DESC);
-- The newest messages overall (/api/state), and one conversation's pages
-- walked from each side by id (see _CONVERSATION_PAGE).
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);
CREATE INDEX IF NOT EXISTS idx_messages_sender_id ON messages(sender, id);
CREATE INDEX IF NOT EXISTS idx_messages_recipient_id ON messages(recipient, id);
-- The Chats list (owner_chats): count and newest message per conversation,
-- from each side, without reading rows (ts sits after the long content).
CREATE INDEX IF NOT EXISTS idx_messages_sender_recipient_ts ON messages(sender, recipient, ts);
CREATE INDEX IF NOT EXISTS idx_messages_recipient_sender_ts ON messages(recipient, sender, ts);

CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT,
    assignee    TEXT,
    status      TEXT NOT NULL DEFAULT 'open',
    worktree    TEXT,
    worktree_node TEXT,
    note        TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    queen       TEXT,
    created_at  REAL NOT NULL,
    position    REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS board_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL,
    author TEXT NOT NULL,
    subject TEXT,
    body TEXT NOT NULL,
    reply_to INTEGER REFERENCES board_posts(id),
    client_id TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS board_posts_team_id ON board_posts(team_id, id);
CREATE INDEX IF NOT EXISTS board_posts_thread ON board_posts(team_id, reply_to, id);
CREATE UNIQUE INDEX IF NOT EXISTS board_posts_client
    ON board_posts(author, client_id) WHERE client_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS board_reads (
    user_id TEXT NOT NULL,
    team_id INTEGER NOT NULL,
    last_read_id INTEGER NOT NULL DEFAULT 0,
    last_hinted_id INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, team_id)
);

CREATE TABLE IF NOT EXISTS meta (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    name        TEXT PRIMARY KEY,
    token_hash  TEXT,
    created_at  REAL NOT NULL,
    last_seen   REAL,
    version     TEXT,
    tmux_server TEXT,
    harnesses   TEXT
);

-- Bundles already taken in, so importing the same export twice does not
-- duplicate its tasks and history.
CREATE TABLE IF NOT EXISTS imports (
    source_id   TEXT PRIMARY KEY,
    node        TEXT NOT NULL,
    imported_at REAL NOT NULL,
    report      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_deps (
    task_id     INTEGER NOT NULL,
    depends_on  INTEGER NOT NULL,
    PRIMARY KEY (task_id, depends_on)
);

-- What each agent says it is doing ("source" agent), or what its harness
-- wrote into the tmux pane title ("title"). Newest row is the current one.
CREATE TABLE IF NOT EXISTS summaries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    text        TEXT NOT NULL,
    source      TEXT NOT NULL,
    ts          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_summaries_user_ts ON summaries(user_id, ts);

-- The newest snapshot each node posted, so a machine that lost its disk, or
-- never saved one, can still be restored from the hub (#546).
CREATE TABLE IF NOT EXISTS node_snapshots (
    node        TEXT PRIMARY KEY,
    -- The snapshot's own stamp, ISO 8601 with its offset, as restore writes it.
    taken_at    TEXT NOT NULL,
    snapshot    TEXT NOT NULL
);

-- Messages the owner pinned in the dashboard.
CREATE TABLE IF NOT EXISTS pins (
    message_id  INTEGER PRIMARY KEY,
    pinned_at   REAL NOT NULL
);
