//! tmux access, the same commands agent_swarm/tmux.py runs, with timeouts.

use std::collections::{HashMap, HashSet};
use std::process::Stdio;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};

use tokio::io::AsyncWriteExt;
use tokio::process::Command;

pub const DEFAULT_SUBMIT_KEY: &str = "C-m";
const SHELLS: [&str; 8] = ["bash", "zsh", "sh", "dash", "fish", "ksh", "tcsh", "csh"];

/// Why a tmux command gave no output.
pub enum Failure {
    /// tmux ran and said no (non-zero exit): nothing happened.
    Refused(String),
    /// No answer: a timeout, or tmux could not be started.
    NoAnswer(String),
}

impl Failure {
    pub fn text(&self) -> &str {
        match self {
            Failure::Refused(s) | Failure::NoAnswer(s) => s,
        }
    }
}

/// Run `tmux <args>`, feeding `input` on stdin, killing it after `timeout`.
/// Called from blocking threads, so it parks on the async runtime.
fn run(args: &[&str], input: Option<&str>, timeout: f64) -> Result<String, Failure> {
    let shown = || format!("['tmux', {}]", args.iter().map(|a| format!("'{a}'")).collect::<Vec<_>>().join(", "));
    tokio::runtime::Handle::current().block_on(async {
        let mut child = Command::new("tmux")
            .args(args)
            .stdin(if input.is_some() { Stdio::piped() } else { Stdio::null() })
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true)
            .spawn()
            .map_err(|e| Failure::NoAnswer(e.to_string()))?;
        let work = async {
            if let (Some(text), Some(mut stdin)) = (input, child.stdin.take()) {
                let _ = stdin.write_all(text.as_bytes()).await;
            }
            child.wait_with_output().await
        };
        match tokio::time::timeout(Duration::from_secs_f64(timeout), work).await {
            Err(_) => Err(Failure::NoAnswer(format!("Command '{}' timed out after {timeout} seconds", shown()))),
            Ok(Err(e)) => Err(Failure::NoAnswer(e.to_string())),
            Ok(Ok(out)) if out.status.success() => Ok(String::from_utf8_lossy(&out.stdout).into_owned()),
            Ok(Ok(out)) => {
                let stderr = String::from_utf8_lossy(&out.stderr).trim().to_string();
                Err(Failure::Refused(if stderr.is_empty() {
                    format!("Command '{}' returned non-zero exit status {}.", shown(), out.status.code().unwrap_or(-1))
                } else {
                    stderr
                }))
            }
        }
    })
}

fn out(args: &[&str]) -> Option<String> {
    run(args, None, 2.0).ok()
}

/// "pid:start_time" of the running tmux server, or None without tmux.
pub fn server_id() -> Option<String> {
    let id = out(&["display-message", "-p", "#{pid}:#{start_time}"])?.trim().to_string();
    (!id.is_empty()).then_some(id)
}

pub struct Pane {
    pub label: String,
    pub command: String,
}

/// One look at tmux: which panes exist and which hold an agent.
pub struct Snapshot {
    pub server: Option<String>,
    pub table: HashMap<String, Pane>,
    pub live: HashSet<String>,
}

fn pane_table() -> HashMap<String, Pane> {
    let listed = out(&["list-panes", "-a", "-F", "#{pane_id}\t#S:#I.#P\t#{pane_current_command}"]).unwrap_or_default();
    let mut table = HashMap::new();
    for line in listed.lines() {
        let mut cols = line.split('\t');
        let id = cols.next().unwrap_or("");
        if !id.is_empty() {
            let label = cols.next().unwrap_or("").to_string();
            table.insert(id.to_string(), Pane { label, command: cols.next().unwrap_or("").trim().to_string() });
        }
    }
    table
}

/// The pane table bracketed by the server id, so a tmux restart in between
/// cannot pair one server's panes with another's identity. Err when tmux
/// restarted on both attempts.
pub fn snapshot() -> Result<Snapshot, String> {
    for _ in 0..2 {
        let before = server_id();
        let table = pane_table();
        let server = server_id();
        if server == before {
            let live =
                table.iter().filter(|(_, p)| !SHELLS.contains(&p.command.as_str())).map(|(id, _)| id.clone()).collect();
            return Ok(Snapshot { server, table, live });
        }
    }
    Err("tmux restarted during every attempt to read its panes".into())
}

pub struct Resolved {
    pub pane: String,
    pub label: String,
    pub server: Option<String>,
}

/// Resolve any tmux target to its pane id, label and server. Ok(None) when
/// the target names no pane.
pub fn resolve(target: &str) -> Result<Option<Resolved>, String> {
    let before = server_id();
    let found = out(&["display-message", "-p", "-t", target, "#{pane_id}\t#S:#I.#P"]).unwrap_or_default();
    let after = server_id();
    let (pane, label) = found.trim().split_once('\t').unwrap_or((found.trim(), ""));
    if !pane.starts_with('%') {
        return Ok(None);
    }
    if before != after {
        return Err("tmux restarted while resolving the pane".into());
    }
    Ok(Some(Resolved { pane: pane.to_string(), label: label.to_string(), server: after }))
}

/// Why a pane id from `expected` cannot be used now, or None if it can.
fn stale_server(expected: Option<&str>) -> Option<String> {
    let expected = expected?;
    (server_id().as_deref() != Some(expected))
        .then(|| format!("tmux server changed ({expected} is gone); the pane id is from an earlier session"))
}

/// The pane's visible screen: (text, error).
pub fn capture(pane: &str, server: Option<&str>, colors: bool) -> (Option<String>, Option<String>) {
    if let Some(stale) = stale_server(server) {
        return (None, Some(stale));
    }
    let mut args = vec!["capture-pane", "-p", "-J"];
    if colors {
        args.push("-e");
    }
    args.extend(["-t", pane]);
    match run(&args, None, 3.0) {
        Ok(text) => (Some(text), None),
        Err(e) => (None, Some(e.text().to_string())),
    }
}

/// Record the agent's handle as the pane option @agent_swarm.
pub fn tag_pane(pane: &str, server: Option<&str>, handle: &str) {
    if stale_server(server).is_none() {
        let _ = run(&["set-option", "-p", "-t", pane, "@agent_swarm", handle], None, 2.0);
    }
}

pub fn infer_flavor(model: Option<&str>) -> &'static str {
    let Some(label) = model.filter(|m| !m.is_empty()).map(str::to_lowercase) else { return "generic" };
    let has_token = |token: &str| {
        label.match_indices(token).any(|(at, _)| {
            let edge = |c: Option<char>| c.is_none_or(|c| !(c.is_ascii_lowercase() || c.is_ascii_digit()));
            edge(label[..at].chars().next_back()) && edge(label[at + token.len()..].chars().next())
        })
    };
    if label.contains("codex") {
        "codex"
    } else if label.contains("claude") {
        "claude"
    } else if label.contains("hermes") {
        "hermes"
    } else if has_token("pi") {
        "pi"
    } else if label.starts_with("gemini") || label.contains("antigravity") {
        "agy"
    } else {
        "generic"
    }
}

pub fn submit_key_for_flavor(flavor: Option<&str>) -> &'static str {
    match flavor.map(str::to_lowercase).as_deref() {
        Some("codex" | "pi" | "agy") => "Enter",
        _ => DEFAULT_SUBMIT_KEY,
    }
}

pub fn compact_command_for_flavor(flavor: Option<&str>) -> Option<&'static str> {
    match flavor.unwrap_or("generic").to_lowercase().as_str() {
        "claude" | "codex" | "pi" | "agy" => Some("/compact"),
        "hermes" => Some("/compress"),
        _ => None,
    }
}

/// The message body that lands in the recipient's pane.
pub fn format_message(sender: &str, context: Option<&str>, content: &str, owner_reply_reminder: bool) -> String {
    let mut head = format!("[agent-msg from {sender}");
    if let Some(context) = context.filter(|c| !c.is_empty()) {
        head += &format!(" · {context}");
    }
    head += "] ";
    if sender == "owner" && owner_reply_reminder {
        head += "Reply via `buzz send --to owner --message \"...\"` so it appears on the dashboard.\n\n";
    }
    head + content
}

/// True when the row under the cursor is more than a bare prompt: the
/// submit key was swallowed and the text is still in the composer.
fn composer_holds_text(pane: &str) -> bool {
    let Ok(pos) = run(&["display-message", "-p", "-t", pane, "#{cursor_y}"], None, 2.0) else { return false };
    let Ok(y) = pos.trim().parse::<usize>() else { return false };
    let Ok(screen) = run(&["capture-pane", "-p", "-t", pane], None, 3.0) else { return false };
    let Some(row) = screen.lines().nth(y) else { return false };
    !row.trim().trim_start_matches(['>', '›', '❯', '$', '%', '#']).trim().is_empty()
}

fn await_submit(pane: &str, timeout: f64) -> bool {
    let deadline = Instant::now() + Duration::from_secs_f64(timeout);
    loop {
        std::thread::sleep(Duration::from_millis(100));
        if !composer_holds_text(pane) {
            return true;
        }
        if Instant::now() >= deadline {
            return false;
        }
    }
}

pub enum Delivery {
    Ok,
    /// Certain: nothing reached the pane.
    Failed(String),
    /// The paste may have happened. Never retried.
    Unknown(String),
}

static BUFFER: AtomicU64 = AtomicU64::new(0);

/// Paste `text` into a pane as one bracketed paste, then press the submit key.
pub fn deliver(
    pane: &str,
    server: Option<&str>,
    text: &str,
    prefix: Option<&str>,
    submit_key: &str,
    flavor: Option<&str>,
) -> Delivery {
    if let Some(stale) = stale_server(server) {
        return Delivery::Failed(stale);
    }
    let injected = format!("{}{text}", prefix.unwrap_or(""));
    let buffer = format!("agent-swarm-{}-{}", std::process::id(), BUFFER.fetch_add(1, Ordering::Relaxed));
    if let Err(e) = run(&["load-buffer", "-b", &buffer, "-"], Some(&injected), 5.0) {
        return Delivery::Failed(e.text().to_string());
    }
    match run(&["paste-buffer", "-p", "-d", "-b", &buffer, "-t", pane], None, 5.0) {
        Ok(_) => {}
        Err(Failure::Refused(e)) => return Delivery::Failed(e),
        Err(Failure::NoAnswer(e)) => return Delivery::Unknown(format!("paste did not report back: {e}")),
    }
    let delay = if flavor.is_some_and(|f| f.eq_ignore_ascii_case("codex")) { 0.2 } else { 0.05 };
    std::thread::sleep(Duration::from_secs_f64(delay));
    let verify = std::env::var("AGENT_SWARM_SUBMIT_VERIFY_DELAY").ok().and_then(|v| v.parse().ok()).unwrap_or(1.5);
    let submit = || run(&["send-keys", "-t", pane, submit_key], None, 5.0).map(drop);
    // Retry only the submit key, once: pasting again would duplicate text.
    let pressed = submit().and_then(|()| if await_submit(pane, verify) { Ok(()) } else { submit() });
    match pressed {
        Ok(()) => Delivery::Ok,
        Err(e) => Delivery::Unknown(format!("pasted, but the submit key failed: {}", e.text())),
    }
}
