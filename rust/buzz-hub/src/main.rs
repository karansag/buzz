//! buzz-hub: a Rust clone of the core of the Buzz hub (agent_swarm/server.py).
//!
//! Cloned: register, recipients, whoami, send with real tmux delivery,
//! messages, tasks, status, the dashboard state and its static files.
//! Not cloned: see rust/REPORT.md.

mod api;
mod db;
mod names;
mod tmux;
mod validate;

use std::net::SocketAddr;
use std::path::PathBuf;
use std::sync::Arc;

use axum::body::Bytes;
use axum::extract::{ConnectInfo, Path, RawQuery, Request, State};
use axum::http::{header, HeaderMap, HeaderValue, StatusCode};
use axum::middleware::{self, Next};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, patch, post};
use axum::{Extension, Router};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use api::{Api, ApiError, Cx, Principal};
use validate::{opt, req, validate, Body, Field, Kind, INT, STR};

/// Optional (`--features mimalloc`): responses are megabytes of small
/// strings built on many threads, and glibc's allocator contends there.
/// It is off by default because it holds more memory; rust/REPORT.md has
/// both measurements.
#[cfg(feature = "mimalloc")]
#[global_allocator]
static ALLOCATOR: mimalloc::MiMalloc = mimalloc::MiMalloc;

pub struct App {
    pool: db::Pool,
    db_path: String,
    /// This machine's node name, as stored on its agents' rows.
    node: String,
    spawn_dirs: Vec<String>,
    trust_loopback: bool,
    owner_logins: Vec<String>,
    assets: Vec<Asset>,
    portal: String,
}

struct Asset {
    name: String,
    mime: &'static str,
    etag: String,
    bytes: Vec<u8>,
}

/// The dashboard, built into the binary; `--assets` reads a folder instead.
const EMBEDDED: [(&str, &[u8]); 7] = [
    ("portal.js", include_bytes!("../../../agent_swarm/static/portal.js")),
    ("portal.css", include_bytes!("../../../agent_swarm/static/portal.css")),
    ("icon.svg", include_bytes!("../../../agent_swarm/static/icon.svg")),
    ("icon-192.png", include_bytes!("../../../agent_swarm/static/icon-192.png")),
    ("icon-512.png", include_bytes!("../../../agent_swarm/static/icon-512.png")),
    ("apple-touch-icon.png", include_bytes!("../../../agent_swarm/static/apple-touch-icon.png")),
    ("manifest.webmanifest", include_bytes!("../../../agent_swarm/static/manifest.webmanifest")),
];
const PORTAL: &str = include_str!("../../../agent_swarm/portal.html");

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes).iter().map(|b| format!("{b:02x}")).collect()
}

fn mime(name: &str) -> &'static str {
    match name.rsplit('.').next().unwrap_or("") {
        "js" => "text/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "webmanifest" => "application/manifest+json",
        "html" => "text/html; charset=utf-8",
        _ => "application/octet-stream",
    }
}

/// Load the dashboard files and version the bundle URLs by content, so a
/// normal refresh cannot reuse an older bundle.
fn load_assets(dir: Option<&PathBuf>) -> std::io::Result<(Vec<Asset>, String)> {
    let mut files: Vec<(String, Vec<u8>)> = Vec::new();
    let mut portal = PORTAL.to_string();
    match dir {
        None => files.extend(EMBEDDED.iter().map(|(name, bytes)| (name.to_string(), bytes.to_vec()))),
        Some(dir) => {
            portal = std::fs::read_to_string(dir.join("portal.html"))?;
            for entry in std::fs::read_dir(dir.join("static"))? {
                let entry = entry?;
                if entry.file_type()?.is_file() {
                    files.push((entry.file_name().to_string_lossy().into_owned(), std::fs::read(entry.path())?));
                }
            }
        }
    }
    let assets: Vec<Asset> = files
        .into_iter()
        .map(|(name, bytes)| Asset {
            mime: mime(&name),
            etag: format!("\"{}\"", &sha256_hex(&bytes)[..32]),
            name,
            bytes,
        })
        .collect();
    for asset in assets.iter().filter(|a| a.name == "portal.js" || a.name == "portal.css") {
        let plain = format!("\"/static/{}\"", asset.name);
        portal = portal.replace(&plain, &format!("\"/static/{}?v={}\"", asset.name, &sha256_hex(&asset.bytes)[..16]));
    }
    Ok((assets, portal))
}

// ---- responses ---------------------------------------------------------------

fn json_response(status: u16, value: &Value) -> Response {
    let body = serde_json::to_vec(value).unwrap_or_default();
    let status = StatusCode::from_u16(status).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR);
    (status, [(header::CONTENT_TYPE, "application/json")], body).into_response()
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        if self.status == 500 {
            return (StatusCode::INTERNAL_SERVER_ERROR, "Internal Server Error").into_response();
        }
        json_response(self.status, &json!({"detail": self.detail}))
    }
}

fn unprocessable(detail: Value) -> ApiError {
    ApiError { status: 422, detail }
}

/// Run a route's blocking work (SQLite, tmux) off the async workers, as
/// Starlette runs a sync endpoint in its thread pool.
async fn run<F>(app: Arc<App>, principal: Principal, work: F) -> Response
where
    F: FnOnce(&Cx<'_>) -> Api<Value> + Send + 'static,
{
    let done = tokio::task::spawn_blocking(move || {
        let cx = Cx { app: &app, db: app.pool.get()?, principal };
        work(&cx).map(|value| json_response(200, &value))
    })
    .await;
    match done {
        Ok(Ok(response)) => response,
        Ok(Err(e)) => e.into_response(),
        Err(_) => ApiError { status: 500, detail: Value::Null }.into_response(),
    }
}

// ---- request models ----------------------------------------------------------

const NAME: Kind = Kind::Str { min: Some(1), max: None };

const CALLER: [Field; 6] = [
    opt("tmux_pane", STR),
    opt("agent_id", STR),
    opt("pane_verified", Kind::Bool),
    opt("pane_in_tree", Kind::Bool),
    opt("harness", STR),
    opt("node", STR),
];

fn register_fields() -> Vec<Field> {
    vec![
        req("tmux_pane", NAME),
        opt("agent_id", STR),
        opt("requested_user", STR),
        opt("model", STR),
        opt("flavor", STR),
        opt("node", STR),
        opt("instructions", STR),
        opt("message_prefix", STR),
        opt("submit_key", STR),
    ]
}

fn with_caller(own: Vec<Field>) -> Vec<Field> {
    CALLER.into_iter().chain(own).collect()
}

fn send_fields() -> Vec<Field> {
    with_caller(vec![
        req("recipient", NAME),
        req("content", NAME),
        opt("reply_to", Kind::Int { gt: Some(0) }),
        opt("context", STR),
    ])
}

fn status_fields() -> Vec<Field> {
    with_caller(vec![req("text", Kind::Str { min: Some(1), max: Some(200) })])
}

/// `ActorFields` in server.py: the same six, in the model's own order.
fn actor_fields(own: Vec<Field>) -> Vec<Field> {
    let order = ["tmux_pane", "node", "agent_id", "pane_verified", "pane_in_tree", "harness"];
    let mut fields: Vec<Field> = CALLER.into_iter().collect();
    fields.sort_by_key(|f| order.iter().position(|name| *name == f.name));
    fields.into_iter().chain(own).collect()
}

fn task_create_fields() -> Vec<Field> {
    actor_fields(vec![
        Field { name: "attachments", kind: Kind::StrList { max: 8 }, required: false, nullable: false },
        req("title", NAME),
        opt("description", STR),
        opt("assignee", STR),
        opt("team_id", INT),
        opt("depends_on", Kind::IntList),
    ])
}

fn task_update_fields() -> Vec<Field> {
    actor_fields(vec![
        opt("status", Kind::Literal(&["open", "picked_up", "done"])),
        opt("title", NAME),
        opt("description", STR),
        opt("assignee", STR),
        opt("worktree", NAME),
        opt("worktree_node", STR),
        opt("team_id", INT),
        opt("depends_on", Kind::IntList),
        opt("note", STR),
    ])
}

fn parse_body(bytes: &Bytes, fields: &[Field]) -> Result<Body, ApiError> {
    let value: Value = serde_json::from_slice(bytes).map_err(|e| {
        unprocessable(json!([{"type": "json_invalid", "loc": ["body", e.column()], "msg": "JSON decode error",
                              "input": {}, "ctx": {"error": e.to_string()}}]))
    })?;
    validate(&value, fields, "body", true).map_err(unprocessable)
}

fn percent_decode(raw: &str) -> String {
    let bytes = raw.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        let hex =
            (bytes[i] == b'%').then(|| raw.get(i + 1..i + 3).and_then(|h| u8::from_str_radix(h, 16).ok())).flatten();
        match (hex, bytes[i]) {
            (Some(byte), _) => {
                out.push(byte);
                i += 2;
            }
            (None, b'+') => out.push(b' '),
            (None, byte) => out.push(byte),
        }
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn parse_query(raw: Option<String>, fields: &[Field]) -> Result<Body, ApiError> {
    let mut given = serde_json::Map::new();
    for pair in raw.as_deref().unwrap_or("").split('&').filter(|p| !p.is_empty()) {
        let (key, value) = pair.split_once('=').unwrap_or((pair, ""));
        given.insert(percent_decode(key), Value::String(percent_decode(value)));
    }
    validate(&Value::Object(given), fields, "query", false).map_err(unprocessable)
}

// ---- routes ------------------------------------------------------------------

type Ctx = (State<Arc<App>>, Extension<Principal>);

macro_rules! body_route {
    ($name:ident, $fields:expr, $method:ident) => {
        async fn $name((State(app), Extension(who)): Ctx, bytes: Bytes) -> Response {
            match parse_body(&bytes, &$fields) {
                Ok(body) => run(app, who, move |cx| cx.$method(&body)).await,
                Err(e) => e.into_response(),
            }
        }
    };
}

macro_rules! query_route {
    ($name:ident, $fields:expr, $method:ident) => {
        async fn $name((State(app), Extension(who)): Ctx, RawQuery(raw): RawQuery) -> Response {
            match parse_query(raw, &$fields) {
                Ok(query) => run(app, who, move |cx| cx.$method(&query)).await,
                Err(e) => e.into_response(),
            }
        }
    };
}

body_route!(register, register_fields(), register);
body_route!(send, send_fields(), send);
body_route!(set_status, status_fields(), status);
body_route!(tasks_create, task_create_fields(), tasks_create);
query_route!(recipients, [opt("include_retired_sessions", Kind::Bool)], recipients);
query_route!(whoami, CALLER, whoami);
query_route!(messages, [opt("user", STR), opt("limit", INT), opt("id", INT)], messages);
query_route!(state, [opt("limit", INT)], state);

async fn health(State(app): State<Arc<App>>) -> Response {
    json_response(200, &json!({"ok": true, "db": app.db_path}))
}

async fn tasks_list((State(app), Extension(who)): Ctx) -> Response {
    run(app, who, |cx| cx.tasks_list()).await
}

async fn tasks_update((State(app), Extension(who)): Ctx, Path(raw): Path<String>, bytes: Bytes) -> Response {
    let Ok(id) = raw.parse::<i64>() else {
        let msg = "Input should be a valid integer, unable to parse string as an integer";
        return unprocessable(json!([{"type": "int_parsing", "loc": ["path", "task_id"], "msg": msg, "input": raw}]))
            .into_response();
    };
    match parse_body(&bytes, &task_update_fields()) {
        Ok(body) => run(app, who, move |cx| cx.tasks_update(id, &body)).await,
        Err(e) => e.into_response(),
    }
}

/// Spawning agents is not cloned, so this hub offers no harness to start.
/// The dashboard asks on load; an empty list is the true answer here.
async fn spawn_options(Extension(who): Extension<Principal>) -> Response {
    match who {
        Principal::Owner => json_response(200, &json!({"harnesses": []})),
        Principal::Node(_) => {
            json_response(403, &json!({"detail": {"error": "owner only", "detail": "a node token cannot do this"}}))
        }
    }
}

async fn peek((State(app), Extension(who)): Ctx, Path(user): Path<String>) -> Response {
    run(app, who, move |cx| cx.peek(&user)).await
}

async fn portal((State(app), Extension(who)): Ctx) -> Response {
    if let Principal::Node(_) = who {
        return json_response(
            403,
            &json!({"detail": {"error": "owner only", "detail": "a node token cannot do this"}}),
        );
    }
    let headers = [(header::CONTENT_TYPE, "text/html; charset=utf-8"), (header::CACHE_CONTROL, "no-store")];
    (headers, app.portal.clone()).into_response()
}

async fn static_file(State(app): State<Arc<App>>, Path(name): Path<String>, headers: HeaderMap) -> Response {
    let Some(asset) = app.assets.iter().find(|a| a.name == name) else { return not_found().await };
    if headers.get(header::IF_NONE_MATCH).and_then(|v| v.to_str().ok()) == Some(asset.etag.as_str()) {
        return (StatusCode::NOT_MODIFIED, [(header::ETAG, asset.etag.clone())]).into_response();
    }
    let etag = HeaderValue::from_str(&asset.etag).unwrap_or(HeaderValue::from_static(""));
    ([(header::CONTENT_TYPE, HeaderValue::from_static(asset.mime)), (header::ETAG, etag)], asset.bytes.clone())
        .into_response()
}

async fn not_found() -> Response {
    json_response(404, &json!({"detail": "Not Found"}))
}

async fn method_not_allowed() -> Response {
    json_response(405, &json!({"detail": "Method Not Allowed"}))
}

/// Attach a Principal, or refuse. A bearer token names a node. Otherwise
/// the socket peer decides: plain loopback is the owner; loopback forwarded
/// by Tailscale Serve needs its identity header. Health stays open.
async fn authenticate(
    State(app): State<Arc<App>>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    mut request: Request,
    next: Next,
) -> Response {
    if request.uri().path() == "/health" {
        return next.run(request).await;
    }
    // Owned copies: nothing may borrow the request across an await.
    let (auth, login, forwarded) = {
        let headers = request.headers();
        let text =
            |name: &str| headers.get(name).and_then(|v| v.to_str().ok()).map(str::trim).unwrap_or("").to_string();
        let forwarded = headers.contains_key("x-forwarded-for") || headers.contains_key("forwarded");
        (text("authorization"), text("tailscale-user-login").to_lowercase(), forwarded)
    };
    fn refuse(status: u16, error: String, hint: &str) -> Response {
        json_response(status, &json!({"detail": {"error": error, "hint": hint}}))
    }
    let principal = if auth.to_lowercase().starts_with("bearer ") {
        let token_hash = sha256_hex(auth[7..].trim().as_bytes());
        let pool = app.clone();
        let node =
            tokio::task::spawn_blocking(move || pool.pool.get().and_then(|db| db.node_for_token(&token_hash))).await;
        match node {
            Ok(Ok(Some(node))) => Principal::Node(node),
            Ok(Ok(None)) => {
                let error = "unknown token; enrol the machine with `buzz node-token`";
                return json_response(401, &json!({"detail": {"error": error}}));
            }
            _ => return ApiError { status: 500, detail: Value::Null }.into_response(),
        }
    } else {
        let proxied = !login.is_empty() || forwarded;
        if peer.ip().is_loopback() && proxied {
            if login.is_empty() {
                let hint = "the hub accepts proxied requests only from Tailscale Serve";
                return refuse(401, "forwarded request without a Tailscale identity".into(), hint);
            }
            if !app.owner_logins.is_empty() && !app.owner_logins.contains(&login) {
                return refuse(403, format!("{login} is not an owner login"), "AGENT_SWARM_OWNER_LOGINS");
            }
            Principal::Owner
        } else if peer.ip().is_loopback() && app.trust_loopback {
            Principal::Owner
        } else {
            return refuse(401, "authentication required".into(), "set AGENT_SWARM_TOKEN or run `buzz join`");
        }
    };
    request.extensions_mut().insert(principal);
    next.run(request).await
}

// ---- startup -----------------------------------------------------------------

struct Args {
    db: PathBuf,
    host: String,
    port: u16,
    assets: Option<PathBuf>,
}

fn args() -> Result<Args, String> {
    let env = |name: &str| std::env::var(name).ok().filter(|v| !v.is_empty());
    let mut out = Args {
        db: PathBuf::from(env("AGENT_SWARM_DB").unwrap_or_default()),
        host: env("AGENT_SWARM_HOST").unwrap_or_else(|| "127.0.0.1".into()),
        port: env("AGENT_SWARM_PORT").and_then(|p| p.parse().ok()).unwrap_or(8766),
        assets: None,
    };
    let mut given = std::env::args().skip(1);
    while let Some(flag) = given.next() {
        let mut value = || given.next().ok_or(format!("{flag} needs a value"));
        match flag.as_str() {
            "--db" => out.db = PathBuf::from(value()?),
            "--host" => out.host = value()?,
            "--port" => out.port = value()?.parse().map_err(|_| "--port needs a number".to_string())?,
            "--assets" => out.assets = Some(PathBuf::from(value()?)),
            _ => return Err(format!("unknown argument {flag}")),
        }
    }
    if out.db.as_os_str().is_empty() {
        return Err("usage: buzz-hub --db PATH [--port N] [--host H] [--assets AGENT_SWARM_DIR]".into());
    }
    Ok(out)
}

/// AGENT_SWARM_NODE, else the short hostname, lowercase. Unlike the Python
/// hub this never reads or writes ~/.agent-swarm/node.toml.
fn node_name() -> String {
    let named = std::env::var("AGENT_SWARM_NODE").ok().filter(|n| !n.trim().is_empty());
    let host = || std::fs::read_to_string("/proc/sys/kernel/hostname").unwrap_or_else(|_| "localhost".into());
    named.unwrap_or_else(|| host().split('.').next().unwrap_or("").to_string()).trim().to_lowercase()
}

fn list_env(name: &str) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    for item in std::env::var(name).unwrap_or_default().split(',').map(str::trim).filter(|d| !d.is_empty()) {
        if !out.iter().any(|seen| seen == item) {
            out.push(item.to_string());
        }
    }
    out
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = args()?;
    let node = node_name();
    let pool = db::Pool::connect(&args.db)?;
    let abandoned = pool.get()?.startup(&node)?;
    if abandoned > 0 {
        eprintln!("{abandoned} message(s) left pending by the previous run are now unknown");
    }
    let (assets, page) = load_assets(args.assets.as_ref())?;
    let app = Arc::new(App {
        pool,
        db_path: args.db.to_string_lossy().into_owned(),
        node,
        spawn_dirs: list_env("AGENT_SWARM_SPAWN_DIRS"),
        trust_loopback: std::env::var("AGENT_SWARM_TRUST_LOOPBACK").map_or(true, |v| v != "0"),
        owner_logins: list_env("AGENT_SWARM_OWNER_LOGINS").iter().map(|l| l.to_lowercase()).collect(),
        assets,
        portal: page,
    });
    let router = Router::new()
        .route("/health", get(health))
        .route("/register", post(register))
        .route("/recipients", get(recipients))
        .route("/whoami", get(whoami))
        .route("/send", post(send))
        .route("/status", post(set_status))
        .route("/messages", get(messages))
        .route("/tasks", get(tasks_list).post(tasks_create))
        .route("/tasks/{task_id}", patch(tasks_update))
        .route("/api/state", get(state))
        .route("/api/peek/{user_id}", get(peek))
        .route("/api/spawn-options", get(spawn_options))
        .route("/", get(portal))
        .route("/static/{name}", get(static_file))
        .fallback(not_found)
        .method_not_allowed_fallback(method_not_allowed)
        .layer(middleware::from_fn_with_state(app.clone(), authenticate))
        .with_state(app);
    let listener = tokio::net::TcpListener::bind((args.host.as_str(), args.port)).await?;
    eprintln!("buzz-hub listening on http://{}", listener.local_addr()?);
    let stop = async {
        let mut term = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()).ok();
        tokio::select! {
            _ = tokio::signal::ctrl_c() => {}
            _ = async { match term.as_mut() { Some(t) => { t.recv().await; } None => std::future::pending().await } } => {}
        }
    };
    axum::serve(listener, router.into_make_service_with_connect_info::<SocketAddr>())
        .with_graceful_shutdown(stop)
        .await?;
    Ok(())
}
