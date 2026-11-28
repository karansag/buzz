//! SQLite layer: the same schema and statements as agent_swarm/db.py, for the
//! cloned scope only.

use std::collections::{BTreeSet, HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::{Mutex, MutexGuard};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use rusqlite::types::ValueRef;
use rusqlite::{params, params_from_iter, Connection, OptionalExtension, Row};
use serde_json::{json, Map, Value};

pub type Obj = Map<String, Value>;
pub type Sql<T> = rusqlite::Result<T>;

/// Verbatim from agent_swarm/db.py so a fresh database has the same tables.
const SCHEMA: &str = include_str!("schema.sql");

pub const SUMMARY_HISTORY: i64 = 20;
pub const UNBOUND: &str = "unbound";
const FTS: &str = "messages_fts";

pub fn now() -> f64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs_f64()).unwrap_or(0.0)
}

/// One connection per in-flight request, reused. Python keeps one per thread.
pub struct Pool {
    path: PathBuf,
    idle: Mutex<Vec<Connection>>,
    /// Python's `_write_lock`: one writer at a time across the process.
    write: Mutex<()>,
}

pub struct Conn<'a> {
    pool: &'a Pool,
    conn: Option<Connection>,
}

impl std::ops::Deref for Conn<'_> {
    type Target = Connection;
    fn deref(&self) -> &Connection {
        self.conn.as_ref().expect("connection is held until drop")
    }
}

impl Drop for Conn<'_> {
    fn drop(&mut self) {
        if let (Some(conn), Ok(mut idle)) = (self.conn.take(), self.pool.idle.lock()) {
            // A panic inside a write leaves its transaction open. Such a
            // connection is closed, not reused: closing rolls it back.
            if conn.is_autocommit() && idle.len() < 64 {
                idle.push(conn);
            }
        }
    }
}

fn open(path: &Path) -> Sql<Connection> {
    let conn = Connection::open(path)?;
    conn.busy_timeout(Duration::from_secs(30))?;
    conn.execute_batch("PRAGMA synchronous=NORMAL")?;
    Ok(conn)
}

impl Pool {
    /// Open (or create) the database and bring it to the current schema.
    pub fn connect(path: &Path) -> Sql<Pool> {
        if let Some(parent) = path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let conn = open(path)?;
        conn.query_row("PRAGMA journal_mode=WAL", [], |_| Ok(()))?;
        conn.execute_batch(SCHEMA)?;
        ensure_columns(&conn)?;
        ensure_message_index(&conn)?;
        Ok(Pool { path: path.to_path_buf(), idle: Mutex::new(vec![conn]), write: Mutex::new(()) })
    }

    pub fn get(&self) -> Sql<Conn<'_>> {
        let held = self.idle.lock().ok().and_then(|mut idle| idle.pop());
        let conn = match held {
            Some(conn) => conn,
            None => open(&self.path)?,
        };
        Ok(Conn { pool: self, conn: Some(conn) })
    }

    fn lock(&self) -> MutexGuard<'_, ()> {
        self.write.lock().unwrap_or_else(|e| e.into_inner())
    }
}

impl Conn<'_> {
    /// Run `f` as one write transaction under the process-wide write lock.
    /// `E` lets a caller roll back with its own error (a refused task update).
    fn write<T, E: From<rusqlite::Error>>(&self, f: impl FnOnce(&Connection) -> Result<T, E>) -> Result<T, E> {
        let _guard = self.pool.lock();
        self.execute_batch("BEGIN IMMEDIATE")?;
        match f(self) {
            Ok(value) => {
                self.execute_batch("COMMIT")?;
                Ok(value)
            }
            Err(err) => {
                let _ = self.execute_batch("ROLLBACK");
                Err(err)
            }
        }
    }
}

fn columns(conn: &Connection, table: &str) -> Sql<HashSet<String>> {
    let mut stmt = conn.prepare(&format!("PRAGMA table_info({table})"))?;
    let names = stmt.query_map([], |r| r.get::<_, String>(1))?.collect();
    names
}

/// Add the optional columns the Python hub adds to a database made by SCHEMA.
fn ensure_columns(conn: &Connection) -> Sql<()> {
    let add = |table: &str, have: &HashSet<String>, col: &str, kind: &str| -> Sql<()> {
        if !have.contains(col) {
            conn.execute_batch(&format!("ALTER TABLE {table} ADD COLUMN {col} {kind}"))?;
        }
        Ok(())
    };
    let cols = columns(conn, "recipients")?;
    for col in ["agent_id", "model", "flavor", "instructions", "message_prefix", "submit_key", "owner_note", "cwd"] {
        add("recipients", &cols, col, "TEXT")?;
    }
    add("recipients", &cols, "team_id", "INTEGER")?;
    for col in ["tmux_server", "pane_label", "node"] {
        add("recipients", &cols, col, "TEXT")?;
    }
    add("recipients", &cols, "reserved", "INTEGER NOT NULL DEFAULT 0")?;
    let cols = columns(conn, "tasks")?;
    add("tasks", &cols, "worktree", "TEXT")?;
    add("tasks", &cols, "team_id", "INTEGER")?;
    add("tasks", &cols, "note", "TEXT")?;
    add("tasks", &cols, "worktree_node", "TEXT")?;
    add("tasks", &cols, "attachments", "TEXT")?;
    let cols = columns(conn, "messages")?;
    if !cols.contains("reply_to") {
        conn.execute_batch("BEGIN; ALTER TABLE messages ADD COLUMN reply_to INTEGER")?;
        backfill_replies(conn)?;
        conn.execute_batch("COMMIT")?;
    }
    add("messages", &cols, "notify", "INTEGER NOT NULL DEFAULT 0")?;
    add("messages", &cols, "attachments", "TEXT")?;
    add("messages", &cols, "status", "TEXT")?;
    add("messages", &cols, "client_id", "TEXT")?;
    if !columns(conn, "teams")?.contains("position") {
        conn.execute_batch(
            "ALTER TABLE teams ADD COLUMN position REAL; \
             UPDATE teams SET position=(SELECT COUNT(*) FROM teams t WHERE t.id<=teams.id)",
        )?;
    }
    conn.execute_batch(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_client \
         ON messages(sender, client_id) WHERE client_id IS NOT NULL",
    )
}

/// Move the old composer's "(reply to message N; ...)" suffix into reply_to.
fn backfill_replies(conn: &Connection) -> Sql<()> {
    let suffix = regex::Regex::new(
        r"(?:^|\n\n)\(reply to message ([1-9]\d*); `(?:buzz|agent-swarm) messages --id ([1-9]\d*)` shows it\)$",
    )
    .expect("static pattern");
    let rows: Vec<(i64, String)> = conn
        .prepare("SELECT id, content FROM messages")?
        .query_map([], |r| Ok((r.get(0)?, r.get(1)?)))?
        .collect::<Sql<_>>()?;
    for (id, content) in rows {
        // The Python pattern uses a backreference; compare the two ids here.
        if let Some(m) = suffix.captures(&content).filter(|m| m[1] == m[2]) {
            let start = m.get(0).map_or(0, |all| all.start());
            conn.execute(
                "UPDATE messages SET reply_to=?, content=? WHERE id=?",
                params![m[1].parse::<i64>().unwrap_or(0), &content[..start], id],
            )?;
        }
    }
    Ok(())
}

fn index_text(content: &str, context: Option<&str>) -> String {
    caseless::default_case_fold_str(&format!("{content} {}", context.unwrap_or("")))
}

fn have_index(conn: &Connection) -> Sql<bool> {
    conn.query_row("SELECT 1 FROM sqlite_master WHERE name=?", [FTS], |_| Ok(())).optional().map(|r| r.is_some())
}

/// Create the trigram search index if missing and index what it lacks.
fn ensure_message_index(conn: &Connection) -> Sql<()> {
    if !have_index(conn)? {
        let made = conn.execute_batch(&format!(
            "CREATE VIRTUAL TABLE {FTS} USING fts5(body, content='', contentless_delete=1, \
             tokenize='trigram case_sensitive 0'); \
             CREATE VIRTUAL TABLE {FTS}_vocab USING fts5vocab({FTS}, 'row')"
        ));
        if made.is_err() {
            return Ok(());
        }
    }
    let mut last: i64 = conn.query_row(&format!("SELECT COALESCE(MAX(rowid), 0) FROM {FTS}"), [], |r| r.get(0))?;
    loop {
        let rows: Vec<(i64, String, Option<String>)> = conn
            .prepare("SELECT id, content, context FROM messages WHERE id > ? ORDER BY id LIMIT 2000")?
            .query_map([last], |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)))?
            .collect::<Sql<_>>()?;
        let Some(newest) = rows.last().map(|r| r.0) else { break };
        for (id, content, context) in &rows {
            conn.execute(
                &format!("INSERT INTO {FTS}(rowid, body) VALUES(?, ?)"),
                params![id, index_text(content, context.as_deref())],
            )?;
        }
        last = newest;
    }
    Ok(())
}

fn value(v: ValueRef<'_>) -> Value {
    match v {
        ValueRef::Null | ValueRef::Blob(_) => Value::Null,
        ValueRef::Integer(i) => json!(i),
        ValueRef::Real(f) => json!(f),
        ValueRef::Text(t) => Value::String(String::from_utf8_lossy(t).into_owned()),
    }
}

/// Python's `dict(row)`: every column, in the order the query returns them.
fn row_obj(row: &Row<'_>) -> Sql<Obj> {
    let stmt = row.as_ref();
    let mut out = Obj::new();
    for i in 0..stmt.column_count() {
        out.insert(stmt.column_name(i)?.to_string(), value(row.get_ref(i)?));
    }
    Ok(out)
}

fn rows(conn: &Connection, sql: &str, args: impl rusqlite::Params) -> Sql<Vec<Obj>> {
    let mut stmt = conn.prepare_cached(sql)?;
    let out = stmt.query_map(args, row_obj)?.collect();
    out
}

fn one(conn: &Connection, sql: &str, args: impl rusqlite::Params) -> Sql<Option<Obj>> {
    conn.prepare_cached(sql)?.query_row(args, row_obj).optional()
}

fn exists(conn: &Connection, sql: &str, args: impl rusqlite::Params) -> Sql<bool> {
    Ok(conn.prepare_cached(sql)?.query_row(args, |_| Ok(())).optional()?.is_some())
}

fn strings(conn: &Connection, sql: &str, args: impl rusqlite::Params) -> Sql<Vec<String>> {
    let mut stmt = conn.prepare_cached(sql)?;
    let out = stmt.query_map(args, |r| r.get(0))?.collect();
    out
}

pub fn text<'a>(obj: &'a Obj, key: &str) -> Option<&'a str> {
    obj.get(key).and_then(Value::as_str)
}

// ---- startup reconciliation -------------------------------------------------

impl Conn<'_> {
    pub fn startup(&self, node: &str) -> Sql<usize> {
        self.write(|c| {
            c.execute_batch(
                "WITH newest AS (SELECT team_id,MAX(id) AS id FROM board_posts GROUP BY team_id) \
                 UPDATE board_reads SET last_read_id=MIN(last_read_id,COALESCE(newest.id,0)), \
                 last_hinted_id=MIN(last_hinted_id,COALESCE(newest.id,0)) \
                 FROM (SELECT r.user_id,r.team_id,n.id FROM board_reads r \
                 LEFT JOIN newest n ON n.team_id=r.team_id) newest \
                 WHERE newest.user_id=board_reads.user_id AND newest.team_id=board_reads.team_id \
                 AND MAX(last_read_id,last_hinted_id)>COALESCE(newest.id,0)",
            )?;
            c.execute("UPDATE recipients SET node=? WHERE node IS NULL", [node])?;
            c.execute("UPDATE tasks SET worktree_node=? WHERE worktree IS NOT NULL AND worktree_node IS NULL", [node])?;
            c.execute(
                "UPDATE messages SET status='unknown', delivered=0, delivery_error=? WHERE status='pending'",
                ["the server stopped before the delivery result was recorded"],
            )
        })
    }

    // ---- recipients ---------------------------------------------------------

    #[allow(clippy::too_many_arguments)]
    pub fn register(
        &self,
        user_id: &str,
        pane: &str,
        agent_id: Option<&str>,
        model: Option<&str>,
        flavor: Option<&str>,
        instructions: Option<&str>,
        message_prefix: Option<&str>,
        submit_key: Option<&str>,
        tmux_server: Option<&str>,
        pane_label: Option<&str>,
        node: &str,
    ) -> Sql<()> {
        self.write(|c| {
            c.execute(
                "DELETE FROM recipients WHERE node IS ? AND tmux_pane=? AND tmux_server IS ? AND user_id<>?",
                params![node, pane, tmux_server, user_id],
            )?;
            if let Some(id) = agent_id.filter(|id| !id.is_empty()) {
                c.execute("DELETE FROM recipients WHERE agent_id=? AND user_id<>?", params![id, user_id])?;
            }
            c.execute(
                "INSERT INTO recipients(\
                 user_id, tmux_pane, agent_id, model, flavor, instructions, message_prefix, submit_key, registered_at, \
                 tmux_server, pane_label, node\
                 ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) \
                 ON CONFLICT(user_id) DO UPDATE SET \
                 tmux_pane=excluded.tmux_pane, \
                 tmux_server=excluded.tmux_server, \
                 pane_label=excluded.pane_label, \
                 node=COALESCE(excluded.node, recipients.node), \
                 agent_id=COALESCE(excluded.agent_id, recipients.agent_id), \
                 model=COALESCE(excluded.model, recipients.model), \
                 flavor=COALESCE(excluded.flavor, recipients.flavor), \
                 instructions=COALESCE(excluded.instructions, recipients.instructions), \
                 message_prefix=COALESCE(excluded.message_prefix, recipients.message_prefix), \
                 submit_key=COALESCE(excluded.submit_key, recipients.submit_key), \
                 registered_at=excluded.registered_at",
                params![
                    user_id,
                    pane,
                    agent_id,
                    model,
                    flavor,
                    instructions,
                    message_prefix,
                    submit_key,
                    now(),
                    tmux_server,
                    pane_label,
                    node
                ],
            )?;
            c.execute("UPDATE recipients SET reserved=0 WHERE user_id=?", [user_id])?;
            Ok(())
        })
    }

    /// True when `user_id` belongs to an agent other than this one.
    pub fn name_taken_by_other(
        &self,
        user_id: &str,
        agent_id: Option<&str>,
        node: &str,
        pane: &str,
        server: Option<&str>,
    ) -> Sql<bool> {
        let Some(row) =
            one(self, "SELECT agent_id, node, tmux_pane, tmux_server FROM recipients WHERE user_id=?", [user_id])?
        else {
            return Ok(false);
        };
        if let (Some(mine), Some(theirs)) =
            (agent_id.filter(|s| !s.is_empty()), text(&row, "agent_id").filter(|s| !s.is_empty()))
        {
            return Ok(mine != theirs);
        }
        Ok(text(&row, "node") != Some(node)
            || text(&row, "tmux_pane") != Some(pane)
            || text(&row, "tmux_server") != server)
    }

    /// Move a handle, with its history, tasks, team role and board state.
    pub fn rename_recipient(&self, old: &str, new: &str) -> Sql<()> {
        if old == new {
            return Ok(());
        }
        self.write(|c| {
            for sql in [
                "UPDATE recipients SET user_id=?1 WHERE user_id=?2",
                "UPDATE messages SET sender=?1 WHERE sender=?2",
                "UPDATE messages SET recipient=?1 WHERE recipient=?2",
                "UPDATE tasks SET assignee=?1 WHERE assignee=?2",
                "UPDATE teams SET queen=?1 WHERE queen=?2",
                "UPDATE summaries SET user_id=?1 WHERE user_id=?2",
                "UPDATE board_posts SET client_id=NULL WHERE author=?2 AND client_id IN \
                 (SELECT client_id FROM board_posts WHERE author=?1)",
                "UPDATE board_posts SET author=?1 WHERE author=?2",
                "INSERT INTO board_reads SELECT ?1,team_id,last_read_id,last_hinted_id FROM board_reads \
                 WHERE user_id=?2 ON CONFLICT(user_id,team_id) DO UPDATE SET \
                 last_read_id=MAX(board_reads.last_read_id,excluded.last_read_id), \
                 last_hinted_id=MAX(board_reads.last_hinted_id,excluded.last_hinted_id)",
            ] {
                c.execute(sql, params![new, old])?;
            }
            c.execute("DELETE FROM board_reads WHERE user_id=?", [old])?;
            Ok(())
        })
    }

    pub fn user_by_pane(&self, node: &str, pane: &str, server: Option<&str>) -> Sql<Option<String>> {
        self.prepare_cached("SELECT user_id FROM recipients WHERE node=? AND tmux_pane=? AND tmux_server IS ?")?
            .query_row(params![node, pane, server], |r| r.get(0))
            .optional()
    }

    /// An agent from an earlier tmux server that sat at this same position.
    pub fn user_by_restored_label(&self, node: &str, label: &str, flavor: &str, server: &str) -> Sql<Option<String>> {
        self.prepare_cached(
            "SELECT user_id FROM recipients WHERE node=? AND pane_label=? AND flavor IS ? \
             AND tmux_server IS NOT NULL AND tmux_server<>? AND tmux_server<>? \
             ORDER BY registered_at DESC LIMIT 1",
        )?
        .query_row(params![node, label, flavor, server, UNBOUND], |r| r.get(0))
        .optional()
    }

    pub fn user_by_agent_id(&self, agent_id: &str) -> Sql<Option<String>> {
        self.prepare_cached("SELECT user_id FROM recipients WHERE agent_id=?")?
            .query_row([agent_id], |r| r.get(0))
            .optional()
    }

    /// Record a session id on a registration that has none, or swap
    /// `replacing` for it. One statement. True when this call recorded it.
    pub fn adopt_agent_id(
        &self,
        user_id: &str,
        agent_id: &str,
        node: &str,
        pane: &str,
        server: Option<&str>,
        replacing: Option<&str>,
    ) -> Sql<bool> {
        let held = if replacing.is_some() { "agent_id=?6" } else { "(agent_id IS NULL OR agent_id='') AND ?6 IS NULL" };
        let sql = format!(
            "UPDATE recipients SET agent_id=?1 WHERE user_id=?2 \
             AND node=?3 AND tmux_pane=?4 AND tmux_server IS ?5 AND reserved=0 AND {held} \
             AND NOT EXISTS (SELECT 1 FROM recipients WHERE agent_id=?1)"
        );
        self.write(|c| Ok(c.execute(&sql, params![agent_id, user_id, node, pane, server, replacing])? == 1))
    }

    const RECIPIENT: &'static str =
        "SELECT user_id, tmux_pane, tmux_server, pane_label, node, reserved, agent_id, model, \
        flavor, instructions, message_prefix, submit_key, team_id, owner_note, cwd, registered_at FROM recipients";

    pub fn recipient(&self, user_id: &str) -> Sql<Option<Obj>> {
        one(self, &format!("{} WHERE user_id=?", Self::RECIPIENT), [user_id])
    }

    pub fn recipients(&self) -> Sql<Vec<Obj>> {
        rows(self, &format!("{} ORDER BY user_id", Self::RECIPIENT), [])
    }

    pub fn retired_agents(&self) -> Sql<Vec<Obj>> {
        rows(self, "SELECT * FROM retired_agents ORDER BY archive_id", [])
    }

    pub fn is_retired(&self, archive_id: Option<&str>, agent_id: Option<&str>) -> Sql<bool> {
        exists(
            self,
            "SELECT 1 FROM retired_agents WHERE archive_id=? OR agent_id=? LIMIT 1",
            params![archive_id, agent_id],
        )
    }

    pub fn was_retired(&self, original_id: &str) -> Sql<bool> {
        exists(self, "SELECT 1 FROM retired_agents WHERE original_id=? LIMIT 1", [original_id])
    }

    /// Every handle this hub has used, by agents present or retired.
    pub fn used_handles(&self) -> Sql<HashSet<String>> {
        Ok(strings(
            self,
            "SELECT user_id FROM recipients \
             UNION SELECT sender FROM messages \
             UNION SELECT recipient FROM messages \
             UNION SELECT assignee FROM tasks WHERE assignee IS NOT NULL \
             UNION SELECT user_id FROM summaries \
             UNION SELECT archive_id FROM retired_agents \
             UNION SELECT author FROM board_posts \
             UNION SELECT user_id FROM board_reads",
            [],
        )?
        .into_iter()
        .collect())
    }

    pub fn node_for_token(&self, token_hash: &str) -> Sql<Option<String>> {
        self.prepare_cached("SELECT name FROM nodes WHERE token_hash=?")?
            .query_row([token_hash], |r| r.get(0))
            .optional()
    }

    pub fn nodes(&self) -> Sql<Vec<Obj>> {
        let mut out = rows(
            self,
            "SELECT name, created_at, last_seen, version, tmux_server, harnesses FROM nodes ORDER BY name",
            [],
        )?;
        for node in &mut out {
            let harnesses =
                text(node, "harnesses").and_then(|h| serde_json::from_str(h).ok()).unwrap_or_else(|| json!([]));
            node.insert("harnesses".into(), harnesses);
        }
        Ok(out)
    }

    pub fn supervisor(&self) -> Sql<Value> {
        let raw: Option<String> = self
            .prepare_cached("SELECT value FROM meta WHERE key='supervisor'")?
            .query_row([], |r| r.get(0))
            .optional()?;
        let row = raw.and_then(|v| serde_json::from_str::<Value>(&v).ok()).unwrap_or(Value::Null);
        Ok(if row.as_object().is_some_and(|o| !o.is_empty()) { row } else { Value::Null })
    }

    // ---- summaries ----------------------------------------------------------

    /// Store what an agent is doing; false when nothing new was said.
    pub fn record_summary(&self, user_id: &str, line: &str, source: &str) -> Sql<bool> {
        self.write(|c| {
            let scoped = matches!(source, "title" | "owner");
            let only = if scoped { "AND source=?2 " } else { "AND source!='owner' AND ?2 IS NOT NULL " };
            let latest: Option<(String, String)> = c
                .prepare_cached(&format!(
                    "SELECT text, source FROM summaries WHERE user_id=?1 {only}ORDER BY ts DESC, id DESC LIMIT 1"
                ))?
                .query_row(params![user_id, source], |r| Ok((r.get(0)?, r.get(1)?)))
                .optional()?;
            if latest.is_some_and(|(t, s)| t == line && s == source) {
                return Ok(false);
            }
            c.execute(
                "INSERT INTO summaries(user_id, text, source, ts) VALUES(?,?,?,?)",
                params![user_id, line, source, now()],
            )?;
            c.execute(
                "DELETE FROM summaries WHERE user_id=?1 AND id NOT IN (\
                 SELECT id FROM summaries WHERE user_id=?1 ORDER BY ts DESC, id DESC LIMIT ?2)",
                params![user_id, SUMMARY_HISTORY],
            )?;
            Ok(true)
        })
    }

    /// Each agent's latest summaries, newest first.
    pub fn summaries_by_user(&self, per_user: i64) -> Sql<HashMap<String, Vec<Value>>> {
        let mut out: HashMap<String, Vec<Value>> = HashMap::new();
        let mut stmt = self.prepare_cached(
            "SELECT user_id, text, source, ts FROM (\
             SELECT *, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY ts DESC, id DESC) AS n \
             FROM summaries) WHERE n <= ? ORDER BY user_id, ts DESC, id DESC",
        )?;
        let mut found = stmt.query([per_user])?;
        while let Some(r) = found.next()? {
            let (user, line, source, ts): (String, String, String, f64) = (r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?);
            out.entry(user).or_default().push(json!({"text": line, "source": source, "ts": ts}));
        }
        Ok(out)
    }

    // ---- tasks --------------------------------------------------------------

    pub fn create_task(
        &self,
        title: &str,
        description: Option<&str>,
        assignee: Option<&str>,
        team_id: Option<i64>,
        attachments: &[String],
        depends_on: &[i64],
    ) -> Result<Obj, TaskError> {
        let id = self.write(|c| {
            let deps: BTreeSet<i64> = depends_on.iter().copied().collect();
            for dep in &deps {
                if !exists(c, "SELECT 1 FROM tasks WHERE id=?", [dep])? {
                    return Err(TaskError::Invalid(format!("unknown dependency: #{dep}")));
                }
            }
            let at = now();
            c.execute(
                "INSERT INTO tasks(title, description, assignee, team_id, status, created_at, updated_at, attachments) \
                 VALUES(?,?,?,?,?,?,?,?)",
                params![title, description, assignee.filter(|_| team_id.is_none()), team_id, "open", at, at,
                        python_json(&json!(attachments))],
            )?;
            let id = c.last_insert_rowid();
            for dep in deps {
                c.execute("INSERT INTO task_deps(task_id, depends_on) VALUES(?,?)", params![id, dep])?;
            }
            Ok(id)
        })?;
        Ok(self.task(id)?.unwrap_or_default())
    }

    pub fn task(&self, id: i64) -> Sql<Option<Obj>> {
        task(self, id)
    }

    pub fn tasks(&self) -> Sql<Vec<Obj>> {
        let mut deps: HashMap<i64, Vec<Value>> = HashMap::new();
        let mut stmt = self.prepare_cached("SELECT task_id, depends_on FROM task_deps ORDER BY depends_on")?;
        let mut found = stmt.query([])?;
        while let Some(r) = found.next()? {
            deps.entry(r.get(0)?).or_default().push(json!(r.get::<_, i64>(1)?));
        }
        let mut out = rows(self, "SELECT * FROM tasks ORDER BY id DESC", [])?;
        for t in &mut out {
            decode_attachments(t);
            let id = t.get("id").and_then(Value::as_i64).unwrap_or(0);
            t.insert("depends_on".into(), Value::Array(deps.remove(&id).unwrap_or_default()));
        }
        Ok(out)
    }

    /// Validate and commit the whole task against one database snapshot.
    pub fn update_task(&self, id: i64, change: &TaskChange) -> Result<Option<Obj>, TaskError> {
        self.write(|c| {
            let Some(mut t) = task(c, id)? else { return Ok(None) };
            let is_null = |t: &Obj, key: &str| t.get(key).is_none_or(Value::is_null);
            if let Some(status) = &change.status {
                t.insert("status".into(), json!(status));
            }
            if let Some(title) = &change.title {
                t.insert("title".into(), json!(title));
            }
            if let Some(description) = &change.description {
                t.insert("description".into(), json!(description));
            }
            // A task is owned by one agent or one team, never both.
            if let Some(assignee) = &change.assignee {
                t.insert("assignee".into(), json!(assignee));
                if assignee.is_some() {
                    t.insert("team_id".into(), Value::Null);
                }
            }
            if let Some(team_id) = &change.team_id {
                t.insert("team_id".into(), json!(team_id));
                if team_id.is_some() {
                    t.insert("assignee".into(), Value::Null);
                }
            }
            if let Some(worktree) = &change.worktree {
                t.insert("worktree".into(), json!(worktree));
            }
            if let Some(node) = &change.worktree_node {
                t.insert("worktree_node".into(), json!(node));
            }
            if is_null(&t, "worktree") {
                t.insert("worktree_node".into(), Value::Null);
            }
            if let Some(note) = &change.note {
                t.insert("note".into(), json!(note));
            }
            if text(&t, "status") == Some("done") && text(&t, "note").is_none_or(|n| n.trim().is_empty()) {
                return Err(TaskError::NoteRequired);
            }
            let deps = match &change.depends_on {
                Some(deps) => Some(validate_deps(c, id, deps)?),
                None => None,
            };
            c.execute(
                "UPDATE tasks SET status=?, title=?, description=?, assignee=?, team_id=?, worktree=?, \
                 worktree_node=?, note=?, updated_at=? WHERE id=?",
                params![
                    text(&t, "status"),
                    text(&t, "title"),
                    text(&t, "description"),
                    text(&t, "assignee"),
                    t.get("team_id").and_then(Value::as_i64),
                    text(&t, "worktree"),
                    text(&t, "worktree_node"),
                    text(&t, "note"),
                    now(),
                    id
                ],
            )?;
            if let Some(deps) = deps {
                c.execute("DELETE FROM task_deps WHERE task_id=?", [id])?;
                for dep in deps {
                    c.execute("INSERT INTO task_deps(task_id, depends_on) VALUES(?,?)", params![id, dep])?;
                }
            }
            Ok(task(c, id)?)
        })
    }

    // ---- teams (read only: /api/state and the queen: address) ----------------

    pub fn team(&self, id: i64) -> Sql<Option<Obj>> {
        let Some(mut team) = one(self, "SELECT * FROM teams WHERE id=?", [id])? else { return Ok(None) };
        let members = strings(self, "SELECT user_id FROM recipients WHERE team_id=? ORDER BY user_id", [id])?;
        team.insert("members".into(), json!(members));
        Ok(Some(team))
    }

    pub fn teams(&self) -> Sql<Vec<Obj>> {
        let ids: Vec<i64> = {
            let mut stmt = self.prepare_cached("SELECT id FROM teams ORDER BY position, id")?;
            let ids = stmt.query_map([], |r| r.get(0))?.collect::<Sql<_>>()?;
            ids
        };
        let mut out = Vec::new();
        for id in ids {
            out.extend(self.team(id)?);
        }
        Ok(out)
    }

    /// Board posts by others that `actor` has not read. Read only.
    pub fn board_unread(&self, team_id: i64, actor: &str) -> Sql<i64> {
        let newest: i64 =
            self.query_row("SELECT COALESCE(MAX(id), 0) FROM board_posts WHERE team_id=?", [team_id], |r| r.get(0))?;
        let cursor: Option<i64> = self
            .prepare_cached("SELECT last_read_id FROM board_reads WHERE user_id=? AND team_id=?")?
            .query_row(params![actor, team_id], |r| r.get(0))
            .optional()?;
        let read_id = match cursor {
            Some(read) => read.min(newest),
            // No cursor yet: all but the newest 20 posts count as read.
            None => self
                .prepare_cached("SELECT id FROM board_posts WHERE team_id=? ORDER BY id DESC LIMIT 1 OFFSET 20")?
                .query_row([team_id], |r| r.get(0))
                .optional()?
                .unwrap_or(0),
        };
        self.query_row(
            "SELECT COUNT(*) FROM board_posts WHERE team_id=? AND id>? AND author<>?",
            params![team_id, read_id, actor],
            |r| r.get(0),
        )
    }

    // ---- messages -----------------------------------------------------------

    /// Store a message and index it for search. Returns its id.
    #[allow(clippy::too_many_arguments)]
    pub fn record_message(
        &self,
        sender: &str,
        recipient: &str,
        context: Option<&str>,
        content: &str,
        status: &str,
        delivery_error: Option<&str>,
        attachments: &[String],
        reply_to: Option<i64>,
    ) -> Sql<i64> {
        self.write(|c| {
            let files = (!attachments.is_empty()).then(|| python_json(&json!(attachments)));
            c.execute(
                "INSERT INTO messages(sender, recipient, context, content, ts, delivered, delivery_error, \
                 attachments, status, client_id, reply_to) VALUES(?,?,?,?,?,?,?,?,?,NULL,?)",
                params![
                    sender,
                    recipient,
                    context,
                    content,
                    now(),
                    (status == "delivered") as i64,
                    delivery_error,
                    files,
                    status,
                    reply_to
                ],
            )?;
            let id = c.last_insert_rowid();
            if have_index(c)? {
                c.execute(
                    &format!("INSERT OR REPLACE INTO {FTS}(rowid, body) VALUES(?, ?)"),
                    params![id, index_text(content, context)],
                )?;
            }
            Ok(id)
        })
    }

    pub fn set_message_status(&self, id: i64, status: &str, error: Option<&str>) -> Sql<()> {
        self.write(|c| {
            c.execute(
                "UPDATE messages SET status=?1, delivered=?2, delivery_error=?3, \
                 client_id=CASE WHEN ?1='failed' THEN NULL ELSE client_id END WHERE id=?4",
                params![status, (status == "delivered") as i64, error, id],
            )?;
            Ok(())
        })
    }

    pub fn message(&self, id: i64) -> Sql<Option<Obj>> {
        Ok(self.with_previews(rows(self, "SELECT * FROM messages WHERE id=?", [id])?)?.pop())
    }

    pub fn messages(&self, user: Option<&str>, limit: i64) -> Sql<Vec<Obj>> {
        let found = match user.filter(|u| !u.is_empty()) {
            Some(user) => rows(
                self,
                "SELECT * FROM messages WHERE recipient=? OR sender=? ORDER BY ts DESC LIMIT ?",
                params![user, user, limit],
            )?,
            None => rows(self, "SELECT * FROM messages ORDER BY ts DESC LIMIT ?", [limit])?,
        };
        self.with_previews(found)
    }

    pub fn pins(&self) -> Sql<Vec<Obj>> {
        let found = rows(
            self,
            "SELECT m.*, p.pinned_at FROM pins p CROSS JOIN messages m ON m.id = p.message_id ORDER BY p.pinned_at DESC",
            [],
        )?;
        self.with_previews(found)
    }

    /// Decode stored fields and attach reply previews, one query per page.
    fn with_previews(&self, mut messages: Vec<Obj>) -> Sql<Vec<Obj>> {
        let mut ids: Vec<i64> = Vec::new();
        for m in &mut messages {
            decode_attachments(m);
            if m.get("status").is_none_or(Value::is_null) {
                // From before statuses: the delivered flag is the whole story.
                let delivered = m.get("delivered").and_then(Value::as_i64).unwrap_or(0) != 0;
                m.insert("status".into(), json!(if delivered { "delivered" } else { "failed" }));
            }
            ids.extend(m.get("reply_to").and_then(Value::as_i64));
        }
        ids.sort_unstable();
        ids.dedup();
        let mut originals: HashMap<i64, Value> = HashMap::new();
        if !ids.is_empty() {
            let marks = vec!["?"; ids.len()].join(",");
            let mut stmt = self.prepare(&format!("SELECT id, sender, content FROM messages WHERE id IN ({marks})"))?;
            let mut found = stmt.query(params_from_iter(ids.iter()))?;
            while let Some(r) = found.next()? {
                let (id, sender, content): (i64, String, String) = (r.get(0)?, r.get(1)?, r.get(2)?);
                let preview: String = squash(&content).chars().take(100).collect();
                originals.insert(id, json!({"id": id, "sender": sender, "content": preview}));
            }
        }
        for m in &mut messages {
            let parent = m.get("reply_to").and_then(Value::as_i64).and_then(|id| originals.get(&id)).cloned();
            m.insert("reply_preview".into(), parent.unwrap_or(Value::Null));
        }
        Ok(messages)
    }

    /// Remind once per active owner conversation, after a quiet interval.
    pub fn owner_reply_reminder_due(&self, recipient: &str, since: f64, idle_seconds: f64) -> Sql<bool> {
        let (owner_last, last): (Option<f64>, Option<f64>) = self.query_row(
            "SELECT MAX(CASE WHEN sender='owner' THEN ts END), MAX(ts) FROM messages \
             WHERE delivered=1 AND ts>=? AND \
             ((sender='owner' AND recipient=?) OR (sender=? AND recipient='owner'))",
            params![since, recipient, recipient],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )?;
        Ok(owner_last.is_none() || now() - last.unwrap_or(0.0) >= idle_seconds)
    }
}

/// What a task update sets. `None` leaves a field as it is; the inner
/// `Option` is the new value, where a field can be cleared.
#[derive(Default)]
pub struct TaskChange {
    pub status: Option<String>,
    pub title: Option<String>,
    pub description: Option<Option<String>>,
    pub assignee: Option<Option<String>>,
    pub team_id: Option<Option<i64>>,
    pub worktree: Option<Option<String>>,
    pub worktree_node: Option<Option<String>>,
    pub note: Option<Option<String>>,
    pub depends_on: Option<Vec<i64>>,
}

pub enum TaskError {
    /// The next state would be done without its verification note.
    NoteRequired,
    Invalid(String),
    Db(rusqlite::Error),
}

impl From<rusqlite::Error> for TaskError {
    fn from(e: rusqlite::Error) -> Self {
        TaskError::Db(e)
    }
}

fn task(conn: &Connection, id: i64) -> Sql<Option<Obj>> {
    let Some(mut t) = one(conn, "SELECT * FROM tasks WHERE id=?", [id])? else { return Ok(None) };
    decode_attachments(&mut t);
    let deps: Vec<i64> = {
        let mut stmt = conn.prepare_cached("SELECT depends_on FROM task_deps WHERE task_id=? ORDER BY depends_on")?;
        let deps = stmt.query_map([id], |r| r.get(0))?.collect::<Sql<_>>()?;
        deps
    };
    t.insert("depends_on".into(), json!(deps));
    Ok(Some(t))
}

/// Check the next dependency graph without writing it.
fn validate_deps(conn: &Connection, id: i64, depends_on: &[i64]) -> Result<Vec<i64>, TaskError> {
    let unique: BTreeSet<i64> = depends_on.iter().copied().collect();
    for dep in &unique {
        if *dep == id {
            return Err(TaskError::Invalid("a task cannot depend on itself".into()));
        }
        if !exists(conn, "SELECT 1 FROM tasks WHERE id=?", [dep])? {
            return Err(TaskError::Invalid(format!("unknown dependency: #{dep}")));
        }
    }
    let mut edges: HashMap<i64, Vec<i64>> = HashMap::new();
    {
        let mut stmt = conn.prepare_cached("SELECT task_id, depends_on FROM task_deps")?;
        let mut found = stmt.query([])?;
        while let Some(r) = found.next()? {
            edges.entry(r.get(0)?).or_default().push(r.get(1)?);
        }
    }
    let unique: Vec<i64> = unique.into_iter().collect();
    edges.insert(id, unique.clone());
    let (mut seen, mut stack) = (HashSet::new(), vec![id]);
    while let Some(node) = stack.pop() {
        for dep in edges.get(&node).into_iter().flatten() {
            if *dep == id {
                return Err(TaskError::Invalid("dependency cycle".into()));
            }
            if seen.insert(*dep) {
                stack.push(*dep);
            }
        }
    }
    Ok(unique)
}

fn decode_attachments(obj: &mut Obj) {
    let files = text(obj, "attachments").and_then(|a| serde_json::from_str(a).ok()).unwrap_or_else(|| json!([]));
    obj.insert("attachments".into(), files);
}

/// Python's `" ".join(s.split())`.
pub fn squash(s: &str) -> String {
    s.split_whitespace().collect::<Vec<_>>().join(" ")
}

/// A list of strings as Python's json.dumps writes it (", " between items),
/// so stored rows are byte-equal whichever hub wrote them.
fn python_json(list: &Value) -> String {
    let items: Vec<String> =
        list.as_array().into_iter().flatten().map(|v| python_json_string(v.as_str().unwrap_or(""))).collect();
    format!("[{}]", items.join(", "))
}

/// json.dumps default: non-ASCII is escaped as \uXXXX.
fn python_json_string(s: &str) -> String {
    let mut out = String::from("\"");
    for unit in s.encode_utf16() {
        match unit {
            0x22 => out.push_str("\\\""),
            0x5c => out.push_str("\\\\"),
            0x0a => out.push_str("\\n"),
            0x0d => out.push_str("\\r"),
            0x09 => out.push_str("\\t"),
            0x08 => out.push_str("\\b"),
            0x0c => out.push_str("\\f"),
            0x20..=0x7e => out.push(unit as u8 as char),
            _ => out.push_str(&format!("\\u{unit:04x}")),
        }
    }
    out.push('"');
    out
}
