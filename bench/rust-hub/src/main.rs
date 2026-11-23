use axum::{
    extract::{Path, Query, State},
    http::{header, StatusCode},
    response::{IntoResponse, Response},
    routing::get,
    Router,
};
use rusqlite::{
    functions::FunctionFlags,
    params_from_iter,
    types::{Value as Bind, ValueRef},
    Connection, OpenFlags,
};
use serde::Deserialize;
use serde_json::{json, Map, Value};
use std::{
    cell::{Cell, RefCell},
    collections::{BTreeMap, HashMap, HashSet},
    env, fs,
    sync::Arc,
    time::{Duration, Instant},
};

type Rows = Vec<Value>;
type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

#[derive(Deserialize)]
struct Fixture {
    state: Map<String, Value>,
    plans: HashMap<String, SearchPlan>,
    fold: HashMap<char, String>,
}

#[derive(Deserialize)]
struct SearchPlan {
    exact: String,
    args: Vec<String>,
    terms: Vec<String>,
    groups: Vec<Vec<Vec<String>>>,
    fts: String,
}

struct App {
    db: String,
    fixture: Arc<Fixture>,
}

thread_local! {
    static SQL_NS: Cell<u128> = const { Cell::new(0) };
    static CONN: RefCell<Option<Connection>> = const { RefCell::new(None) };
}

fn sql<T>(f: impl FnOnce() -> T) -> T {
    let start = Instant::now();
    let result = f();
    SQL_NS.set(SQL_NS.get() + start.elapsed().as_nanos());
    result
}

fn fold(text: &str, overrides: &HashMap<char, String>) -> String {
    let mut result = String::with_capacity(text.len());
    for ch in text.chars() {
        if ch.is_ascii() {
            result.push(ch.to_ascii_lowercase());
        } else if let Some(value) = overrides.get(&ch) {
            result.push_str(value);
        } else {
            result.push(ch);
        }
    }
    result
}

fn open(app: &App) -> rusqlite::Result<Connection> {
    let conn = Connection::open_with_flags(&app.db, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    conn.busy_timeout(Duration::from_secs(30))?;
    let fixture = app.fixture.clone();
    conn.create_scalar_function(
        "casefold",
        1,
        FunctionFlags::SQLITE_DETERMINISTIC,
        move |ctx| {
            let text: Option<String> = ctx.get(0)?;
            Ok(fold(text.as_deref().unwrap_or(""), &fixture.fold))
        },
    )?;
    Ok(conn)
}

fn query(conn: &Connection, statement: &str, values: Vec<Bind>) -> Result<Rows> {
    let mut st = sql(|| conn.prepare(statement))?;
    let names: Vec<_> = st.column_names().into_iter().map(str::to_owned).collect();
    let mut rows = sql(|| st.query(params_from_iter(values)))?;
    let mut result = Vec::new();
    // Measure SQLite API time separately from JSON row construction. Like
    // sqlite3.execute/fetch in Python, this includes the language's bindings.
    while let Some(row) = sql(|| rows.next())? {
        let mut fields = Map::new();
        for (i, name) in names.iter().enumerate() {
            let value = match row.get_ref(i)? {
                ValueRef::Null => Value::Null,
                ValueRef::Integer(n) => json!(n),
                ValueRef::Real(n) => json!(n),
                ValueRef::Text(s) => json!(std::str::from_utf8(s)?),
                ValueRef::Blob(_) => return Err("unexpected blob".into()),
            };
            fields.insert(name.clone(), value);
        }
        result.push(Value::Object(fields));
    }
    Ok(result)
}

fn squash(text: &str) -> String {
    text.split(|ch: char| ch.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&ch))
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
}

fn message_objects(conn: &Connection, mut rows: Rows) -> Result<Rows> {
    let ids: HashSet<_> = rows.iter().filter_map(|r| r["reply_to"].as_i64()).collect();
    let mut parents = HashMap::new();
    if !ids.is_empty() {
        let marks = std::iter::repeat_n("?", ids.len())
            .collect::<Vec<_>>()
            .join(",");
        for row in query(
            conn,
            &format!("SELECT id, sender, content FROM messages WHERE id IN ({marks})"),
            ids.into_iter().map(Bind::Integer).collect(),
        )? {
            let content = squash(row["content"].as_str().unwrap());
            parents.insert(
                row["id"].as_i64().unwrap(),
                json!({
                    "id": row["id"], "sender": row["sender"],
                    "content": content.chars().take(100).collect::<String>(),
                }),
            );
        }
    }
    for row in &mut rows {
        let fields = row.as_object_mut().unwrap();
        let attachments = match fields["attachments"].as_str() {
            Some(value) if !value.is_empty() => serde_json::from_str(value)?,
            _ => json!([]),
        };
        fields.insert("attachments".into(), attachments);
        if fields["status"].is_null() {
            let status = if fields["delivered"].as_i64() == Some(0) {
                "failed"
            } else {
                "delivered"
            };
            fields.insert("status".into(), json!(status));
        }
        let parent = fields["reply_to"]
            .as_i64()
            .and_then(|id| parents.get(&id))
            .cloned();
        fields.insert("reply_preview".into(), parent.unwrap_or(Value::Null));
    }
    Ok(rows)
}

fn state(conn: &Connection, fixture: &Fixture, limit: i64) -> Result<Value> {
    let rows = query(
        conn,
        "SELECT * FROM messages ORDER BY ts DESC LIMIT ?",
        vec![limit.into()],
    )?;
    let mut messages = message_objects(conn, rows)?;
    messages.reverse();
    let mut result = fixture.state.clone();
    result.insert("messages".into(), json!(messages));
    Ok(Value::Object(result))
}

fn page(conn: &Connection, user: &str, op: &str, bound: i64, limit: i64) -> Result<Rows> {
    let order = if op.starts_with('<') { "DESC" } else { "ASC" };
    let statement = format!("SELECT * FROM (
      SELECT * FROM (SELECT * FROM messages WHERE sender=?1 AND id {op} ?2 ORDER BY id {order} LIMIT ?3)
      UNION
      SELECT * FROM (SELECT * FROM messages WHERE recipient=?1 AND id {op} ?2 ORDER BY id {order} LIMIT ?3)
    ) ORDER BY id {order} LIMIT ?3");
    query(
        conn,
        &statement,
        vec![user.to_owned().into(), bound.into(), limit.into()],
    )
}

#[derive(Default, Deserialize)]
struct Page {
    limit: Option<i64>,
    before: Option<i64>,
    after: Option<i64>,
    around: Option<i64>,
}

fn conversation(conn: &Connection, user: &str, args: Page) -> Result<Value> {
    let limit = args.limit.unwrap_or(300);
    let (rows, more) = if let Some(around) = args.around {
        let half = (limit / 2).max(1);
        let mut older = page(conn, user, "<=", around, half + 1)?;
        let more = older.len() as i64 > half;
        older.truncate(half as usize);
        older.reverse();
        older.extend(page(conn, user, ">", around, half)?);
        (older, more)
    } else {
        let (op, bound) = args
            .after
            .map_or(("<", args.before.unwrap_or(i64::MAX)), |x| (">", x));
        let mut rows = page(conn, user, op, bound, limit + 1)?;
        let more = rows.len() as i64 > limit;
        rows.truncate(limit as usize);
        (rows, more)
    };
    Ok(json!({"messages": message_objects(conn, rows)?, "has_more": more}))
}

#[derive(Clone, Copy)]
struct Latest {
    ts: f64,
    id: i64,
    n: i64,
}

fn latest(conn: &Connection) -> Result<BTreeMap<String, Latest>> {
    let mut best: BTreeMap<String, Latest> = BTreeMap::new();
    for (agent, owner, index) in [
        ("recipient", "sender", "idx_messages_sender_recipient_ts"),
        ("sender", "recipient", "idx_messages_recipient_sender_ts"),
    ] {
        let where_ = format!("{owner}='owner' AND {agent}<>'owner'");
        let statement = format!(
            "SELECT a, n, ts, (SELECT id FROM messages WHERE {where_} AND {agent}=g.a
             AND ts=g.ts ORDER BY id DESC LIMIT 1) AS id FROM (
             SELECT {agent} AS a, COUNT(*) AS n, MAX(ts) AS ts FROM messages INDEXED BY {index}
             WHERE {where_} GROUP BY {agent}) AS g"
        );
        for row in query(conn, &statement, vec![])? {
            let found = Latest {
                ts: row["ts"].as_f64().unwrap(),
                id: row["id"].as_i64().unwrap(),
                n: row["n"].as_i64().unwrap(),
            };
            let current = best
                .entry(row["a"].as_str().unwrap().into())
                .or_insert(Latest { n: 0, ..found });
            current.n += found.n;
            if (found.ts, found.id) > (current.ts, current.id) {
                current.ts = found.ts;
                current.id = found.id;
            }
        }
    }
    Ok(best)
}

fn chats(conn: &Connection) -> Result<Value> {
    let latest = latest(conn)?;
    let mut order: Vec<_> = latest.into_iter().collect();
    order.sort_unstable_by(|a, b| b.1.ts.total_cmp(&a.1.ts).then_with(|| b.1.id.cmp(&a.1.id)));
    if order.is_empty() {
        return Ok(json!({"chats": []}));
    }
    let marks = std::iter::repeat_n("?", order.len())
        .collect::<Vec<_>>()
        .join(",");
    let mut messages: HashMap<_, _> = message_objects(
        conn,
        query(
            conn,
            &format!("SELECT * FROM messages WHERE id IN ({marks})"),
            order.iter().map(|(_, r)| Bind::Integer(r.id)).collect(),
        )?,
    )?
    .into_iter()
    .map(|m| (m["id"].as_i64().unwrap(), m))
    .collect();
    let chats: Vec<_> = order
        .into_iter()
        .map(|(agent, r)| {
            json!({"agent": agent, "count": r.n, "last": messages.remove(&r.id).unwrap(),
               "match": null, "matches": 0})
        })
        .collect();
    Ok(json!({"chats": chats}))
}

fn int(conn: &Connection, statement: &str, args: Vec<Bind>) -> Result<i64> {
    Ok(sql(|| {
        conn.query_row(statement, params_from_iter(args), |r| r.get(0))
    })?)
}

fn prefilter(conn: &Connection, plan: &SearchPlan) -> Result<bool> {
    if plan.groups.is_empty()
        || int(
            conn,
            "SELECT COUNT(*) FROM sqlite_master WHERE name='messages_fts'",
            vec![],
        )? == 0
    {
        return Ok(false);
    }
    let newest = int(conn, "SELECT COALESCE(MAX(id),0) FROM messages", vec![])?;
    if newest
        != int(
            conn,
            "SELECT COALESCE(MAX(rowid),0) FROM messages_fts",
            vec![],
        )?
    {
        return Ok(false);
    }
    let total = int(conn, "SELECT COUNT(*) FROM messages", vec![])?;
    let mut estimate = i64::MAX;
    for group in &plan.groups {
        let mut group_docs = 0;
        for term in group {
            let mut min_docs = i64::MAX;
            for gram in term {
                min_docs = min_docs.min(int(
                    conn,
                    "SELECT COALESCE((SELECT doc FROM messages_fts_vocab WHERE term=?),0)",
                    vec![gram.clone().into()],
                )?);
            }
            group_docs += min_docs;
        }
        estimate = estimate.min(group_docs);
    }
    Ok(estimate as f64 <= total as f64 * 0.30)
}

#[derive(Deserialize)]
struct Search {
    q: String,
    limit: Option<i64>,
    offset: Option<i64>,
}

fn search(conn: &Connection, fixture: &Fixture, user: &str, args: Search) -> Result<Value> {
    let plan = fixture
        .plans
        .get(&args.q)
        .ok_or("query missing from benchmark fixture")?;
    let narrowed = prefilter(conn, plan)?;
    let (pre, plus, mut binds) = if narrowed {
        (
            "id IN (SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?) AND ",
            "+",
            vec![plan.fts.clone().into()],
        )
    } else {
        ("", "", Vec::new())
    };
    let exact = &plan.exact;
    let where_ = format!(
        "{pre}(({plus}sender='owner' AND {plus}recipient=?) OR
                           ({plus}sender=? AND {plus}recipient='owner')) AND ({exact})"
    );
    binds.extend([Bind::Text(user.into()), Bind::Text(user.into())]);
    binds.extend(plan.args.iter().cloned().map(Bind::Text));
    let total = int(
        conn,
        &format!("SELECT COUNT(*) FROM messages WHERE {where_}"),
        binds.clone(),
    )?;
    binds.extend([
        args.limit.unwrap_or(100).into(),
        args.offset.unwrap_or(0).into(),
    ]);
    let hits = query(
        conn,
        &format!(
            "SELECT id, ts, sender, content FROM messages WHERE {where_}
                     ORDER BY id DESC LIMIT ? OFFSET ?"
        ),
        binds,
    )?;
    let matches: Vec<_> = hits
        .into_iter()
        .map(|hit| {
            let text = squash(hit["content"].as_str().unwrap());
            let lowered = fold(&text, &fixture.fold);
            let start = plan
                .terms
                .iter()
                .filter_map(|term| lowered.find(term))
                .map(|bytes| lowered[..bytes].chars().count())
                .min()
                .unwrap_or(0)
                .saturating_sub(40);
            let snippet = text.chars().skip(start).take(160).collect::<String>();
            json!({"id": hit["id"], "ts": hit["ts"], "sender": hit["sender"],
               "snippet": format!("{}{}{}", if start > 0 {"…"} else {""}, snippet,
                                  if text.chars().count() > start + 160 {"…"} else {""})})
        })
        .collect();
    Ok(json!({"matches": matches, "total": total, "terms": plan.terms}))
}

async fn respond(
    app: Arc<App>,
    build: impl FnOnce(&Connection, &Fixture) -> Result<Value> + Send + 'static,
) -> Response {
    let result = tokio::task::spawn_blocking(move || -> Result<(Vec<u8>, String)> {
        CONN.with_borrow_mut(|conn| {
            if conn.is_none() {
                *conn = Some(open(&app)?);
            }
            SQL_NS.set(0);
            let start = Instant::now();
            let value = build(conn.as_ref().unwrap(), &app.fixture)?;
            let built = start.elapsed().as_secs_f64() * 1000.0;
            let encode = Instant::now();
            let body = serde_json::to_vec(&value)?;
            let elapsed = encode.elapsed().as_secs_f64() * 1000.0;
            let sql = SQL_NS.get() as f64 / 1e6;
            Ok((
                body,
                format!("db;dur={sql:.4}, build;dur={built:.4}, encode;dur={elapsed:.4}"),
            ))
        })
    })
    .await;
    match result {
        Ok(Ok((body, timing))) => (
            [
                (header::CONTENT_TYPE.as_str(), "application/json"),
                ("server-timing", timing.as_str()),
            ],
            body,
        )
            .into_response(),
        Ok(Err(err)) => (StatusCode::BAD_REQUEST, err.to_string()).into_response(),
        Err(err) => (StatusCode::INTERNAL_SERVER_ERROR, err.to_string()).into_response(),
    }
}

#[tokio::main(worker_threads = 2)]
async fn main() -> Result<()> {
    let args: Vec<_> = env::args().collect();
    if args.len() != 4 {
        return Err("usage: rust-hub-bench COPY.sqlite FIXTURE.json ADDRESS".into());
    }
    let fixture = Arc::new(serde_json::from_slice(&fs::read(&args[2])?)?);
    let app = Arc::new(App {
        db: args[1].clone(),
        fixture,
    });
    let router = Router::new()
        .route("/health", get(|| async { "ok" }))
        .route("/api/state", get(|State(app): State<Arc<App>>, Query(q): Query<Page>| async move {
            respond(app, move |c, f| state(c, f, q.limit.unwrap_or(300))).await
        }))
        .route("/api/chats", get(|State(app): State<Arc<App>>| async move {
            respond(app, |c, _| chats(c)).await
        }))
        .route("/api/agents/{user}/messages", get(|State(app): State<Arc<App>>, Path(u): Path<String>, Query(q): Query<Page>| async move {
            respond(app, move |c, _| conversation(c, &u, q)).await
        }))
        .route("/api/agents/{user}/messages/search", get(|State(app): State<Arc<App>>, Path(u): Path<String>, Query(q): Query<Search>| async move {
            respond(app, move |c, f| search(c, f, &u, q)).await
        }))
        .with_state(app);
    let address: std::net::SocketAddr = args[3].parse()?;
    if !address.ip().is_loopback() {
        return Err("benchmark listener must be loopback".into());
    }
    let socket = tokio::net::TcpListener::bind(address).await?;
    axum::serve(socket, router).await?;
    Ok(())
}
