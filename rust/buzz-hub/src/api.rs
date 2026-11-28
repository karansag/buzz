//! The cloned routes. Each function follows its handler in
//! agent_swarm/server.py and returns the same JSON.

use std::sync::OnceLock;

use regex::Regex;
use serde_json::{json, Value};

use crate::db::{self, squash, text, Conn, Obj, TaskChange, TaskError};
use crate::validate::Body;
use crate::{names, tmux, App};

const OWNER: &str = "owner";
const OWNER_REPLY_IDLE_SECONDS: f64 = 25.0 * 60.0;
const NOTE_GUIDANCE: &str = "Say how to verify it: how to use the feature or reproduce the fix, and where to look - \
    the command, endpoint, screen or files that changed.";

/// An HTTP error: FastAPI's `HTTPException`, sent as {"detail": ...}.
pub struct ApiError {
    pub status: u16,
    pub detail: Value,
}

pub type Api<T> = Result<T, ApiError>;

pub fn fail<T>(status: u16, detail: Value) -> Api<T> {
    Err(ApiError { status, detail })
}

impl From<rusqlite::Error> for ApiError {
    fn from(e: rusqlite::Error) -> Self {
        eprintln!("database error: {e}");
        ApiError { status: 500, detail: Value::Null }
    }
}

/// Who a request comes from: the owner (loopback) or an enrolled node.
#[derive(Clone)]
pub enum Principal {
    Owner,
    Node(String),
}

/// One request's view of the hub.
pub struct Cx<'a> {
    pub app: &'a App,
    pub db: Conn<'a>,
    pub principal: Principal,
}

/// Who is calling: (user_id, how, why_not, (pane, label)).
type Caller = (Option<String>, &'static str, Option<String>, (Option<String>, Option<String>));

fn opt(obj: &Obj, key: &str) -> Option<String> {
    text(obj, key).map(String::from)
}

impl Cx<'_> {
    pub fn require_owner(&self) -> Api<()> {
        match self.principal {
            Principal::Owner => Ok(()),
            Principal::Node(_) => fail(403, json!({"error": "owner only", "detail": "a node token cannot do this"})),
        }
    }

    /// The node a request says it is on. Only this machine is known: remote
    /// nodes are not cloned, so any other name is a 422, as on a Python hub
    /// that the node is not connected to.
    fn claimed_node(&self, node: Option<&str>) -> Api<()> {
        let local = self.app.node.as_str();
        let named = node.filter(|n| !n.is_empty()).unwrap_or(local);
        if let Principal::Node(authenticated) = &self.principal {
            if named != authenticated {
                return fail(403, json!({"error": "node mismatch", "claimed": node, "authenticated": authenticated}));
            }
        }
        if named != local {
            return fail(422, json!({"error": "unknown node", "node": node, "known": [local]}));
        }
        Ok(())
    }

    /// The recipient row, after checking a node token may touch it.
    fn own_row_or_403(&self, user_id: &str) -> Api<Option<Obj>> {
        let row = self.db.recipient(user_id)?;
        if let (Some(row), Principal::Node(node)) = (&row, &self.principal) {
            if text(row, "node") != Some(node.as_str()) {
                return fail(
                    403,
                    json!({"error": "agent belongs to another node", "user_id": user_id,
                                        "node": row.get("node"), "authenticated": node}),
                );
            }
        }
        Ok(row)
    }

    /// (pane id, session:window.pane label, tmux server) for a pane target.
    fn pane_ref(&self, target: &str) -> Api<(String, String, Option<String>)> {
        match tmux::resolve(target) {
            Err(e) => fail(503, json!({"error": e, "retry": true})),
            Ok(None) => Ok((target.to_string(), target.to_string(), None)),
            Ok(Some(r)) => Ok((r.pane, r.label, r.server)),
        }
    }

    fn try_snapshot(&self) -> Option<tmux::Snapshot> {
        tmux::snapshot().map_err(|e| eprintln!("node {} could not be observed: {e}", self.app.node)).ok()
    }

    /// Why a recipient cannot take a message right now, or None if it can.
    fn offline(&self, r: &Obj, local: bool, snap: Option<&tmux::Snapshot>) -> Option<String> {
        let node = text(r, "node").unwrap_or("");
        if r.get("reserved").and_then(Value::as_i64).unwrap_or(0) != 0 {
            return Some("recipient offline: imported from another hub; it has not registered here yet".into());
        }
        if !local {
            return Some(format!("recipient offline: node {node} is not connected"));
        }
        let Some(snap) = snap else {
            return Some(format!("recipient offline: node {node} cannot observe its tmux right now"));
        };
        let pane = text(r, "tmux_pane").unwrap_or("");
        if let Some(stale) = stale(r, snap.server.as_deref()) {
            Some(format!("recipient offline: {stale}; the agent must register again"))
        } else if !snap.table.contains_key(pane) {
            Some(format!("recipient offline: pane {pane} no longer exists"))
        } else if !snap.live.contains(pane) {
            Some(format!("recipient offline: pane {pane} is a bare shell (agent not running)"))
        } else {
            None
        }
    }

    /// Every registration, with whether its pane can take a message now.
    fn annotated_recipients(&self) -> Api<Vec<Obj>> {
        let mut rows = self.db.recipients()?;
        let is_local = |r: &Obj| text(r, "node") == Some(self.app.node.as_str());
        let snap = if rows.iter().any(is_local) { self.try_snapshot() } else { None };
        for r in &mut rows {
            let local = is_local(r);
            let reason = self.offline(r, local, snap.as_ref());
            let alive = reason.is_none();
            let pane = text(r, "tmux_pane").unwrap_or("").to_string();
            r.insert("observed".into(), json!(local && snap.is_some()));
            r.insert("offline_reason".into(), json!(reason));
            r.insert("alive".into(), json!(alive));
            // Show where the pane is now; fall back to where it last was.
            let seen = snap.as_ref().filter(|_| alive).and_then(|s| s.table.get(&pane)).map(|p| p.label.clone());
            let label = seen
                .filter(|l| !l.is_empty())
                .or_else(|| opt(r, "pane_label").filter(|l| !l.is_empty()))
                .unwrap_or(pane);
            r.insert("pane_label".into(), json!(label));
        }
        Ok(rows)
    }

    fn is_alive(&self, user_id: &str) -> Api<bool> {
        let rows = self.annotated_recipients()?;
        Ok(rows.iter().any(|r| text(r, "user_id") == Some(user_id) && r["alive"] == json!(true)))
    }

    /// True when `user_id` is registered on another pane that is still live.
    fn live_elsewhere(&self, user_id: &str, pane: &str, server: Option<&str>) -> Api<bool> {
        let row = self.db.recipient(user_id)?.unwrap_or_default();
        let here = text(&row, "node") == Some(self.app.node.as_str())
            && text(&row, "tmux_pane") == Some(pane)
            && text(&row, "tmux_server") == server;
        Ok(!here && self.is_alive(user_id)?)
    }

    /// See `_resolve_caller` in server.py: a known session id wins; a pane
    /// vouches for an unknown id only when the CLI verified it runs there.
    #[allow(clippy::too_many_arguments)]
    fn resolve_caller(
        &self,
        tmux_pane: Option<&str>,
        agent_id: Option<&str>,
        pane_verified: Option<bool>,
        pane_in_tree: Option<bool>,
        harness: Option<&str>,
    ) -> Api<Caller> {
        let node = self.app.node.as_str();
        let agent_id = agent_id.map(str::trim).filter(|s| !s.is_empty());
        let tmux_pane = tmux_pane.filter(|p| !p.is_empty());
        let given = (tmux_pane.map(String::from), None);
        if let Some(id) = agent_id {
            if let Some(by_id) = self.db.user_by_agent_id(id)? {
                let row = self.db.recipient(&by_id)?.unwrap_or_default();
                if text(&row, "node") != Some(node) {
                    return Ok((
                        None,
                        "session",
                        Some(format!("this session belongs to {by_id} on another node")),
                        given,
                    ));
                }
                let Some(target) = tmux_pane.filter(|_| pane_in_tree == Some(true)) else {
                    return Ok((Some(by_id), "session", None, given));
                };
                // The caller runs inside its pane. If the session's agent is
                // live in another pane, this is a copy of that session.
                let (pane, label, server) = self.pane_ref(target)?;
                let at = (Some(pane.clone()), Some(label));
                if !self.live_elsewhere(&by_id, &pane, server.as_deref())? {
                    return Ok((Some(by_id), "session", None, at));
                }
                let pane_user = self.db.user_by_pane(node, &pane, server.as_deref())?;
                let why = pane_user.is_none().then(|| {
                    format!(
                        "this session is {by_id}'s, which is live in another pane; run `buzz register` here to \
                             register this pane as its own agent"
                    )
                });
                return Ok((pane_user, "pane", why, at));
            }
        }
        let how = if agent_id.is_some() { "session" } else { "pane" };
        let Some(target) = tmux_pane else {
            let why = if agent_id.is_some() { "this session is not registered" } else { "no pane and no session id" };
            return Ok((None, how, Some(format!("{why}; run `buzz register` from the agent's pane")), (None, None)));
        };
        if pane_verified == Some(false) {
            let tail =
                if agent_id.is_some() { " and its session is not registered" } else { " and sent no session id" };
            let why = format!("the caller is not running inside pane {target}{tail}; run this from the agent's own pane, or pass --pane");
            return Ok((None, how, Some(why), given));
        }
        let (pane, label, server) = self.pane_ref(target)?;
        let server = server.as_deref();
        let at = (Some(pane.clone()), Some(label));
        let pane_user = self.db.user_by_pane(node, &pane, server)?;
        let Some(id) = agent_id else {
            let why = pane_user.is_none().then(|| "this pane is not registered".to_string());
            return Ok((pane_user, "pane", why, at));
        };
        let Some(pane_user) = pane_user else {
            return Ok((None, "session", Some("this session is not registered; run `buzz register`".into()), at));
        };
        if pane_verified != Some(true) {
            let why = format!(
                "this session is not registered, and the caller is not verified to be in pane {target} \
                               (held by {pane_user}); register from the agent's own pane, or pass --pane"
            );
            return Ok((None, "session", Some(why), at));
        }
        let registration = self.db.recipient(&pane_user)?.unwrap_or_default();
        let held = text(&registration, "agent_id").map(str::trim).filter(|h| !h.is_empty() && *h != id);
        let same_harness = harness
            .filter(|h| !h.is_empty())
            .is_some_and(|h| h.to_lowercase() == text(&registration, "flavor").unwrap_or("").to_lowercase());
        if let Some(held) = held {
            // The same agent after a /clear: its registration moves to the new id.
            if pane_in_tree == Some(true)
                && same_harness
                && self.db.adopt_agent_id(&pane_user, id, node, &pane, server, Some(held))?
            {
                return Ok((Some(pane_user), "session", None, at));
            }
            let why = format!(
                "pane {target} is registered to {pane_user} under a different session id. If this is {pane_user}, run \
                 `buzz register` from this pane (without --name) to move its existing handle to this session; that is \
                 safe when this shell's TMUX_PANE is {target}. Otherwise register from your own pane"
            );
            return Ok((None, "session", Some(why), at));
        }
        if !self.db.adopt_agent_id(&pane_user, id, node, &pane, server, None)? {
            // Lost a race, or the id is already someone else's: check again.
            let current = self.db.recipient(&pane_user)?.unwrap_or_default();
            let moved = self.db.user_by_agent_id(id)?.as_deref() != Some(pane_user.as_str())
                || text(&current, "node") != Some(node)
                || text(&current, "tmux_pane") != Some(pane.as_str())
                || text(&current, "tmux_server") != server;
            if moved {
                let why = format!("could not record this session on {pane_user} (its registration changed); retry, or run `buzz register`");
                return Ok((None, "session", Some(why), at));
            }
        }
        Ok((Some(pane_user), "pane", None, at))
    }

    fn resolve_from(&self, b: &Body) -> Api<Caller> {
        self.resolve_caller(
            b.str("tmux_pane"),
            b.str("agent_id"),
            b.flag("pane_verified"),
            b.flag("pane_in_tree"),
            b.str("harness"),
        )
    }

    fn caller(&self, b: &Body) -> Api<String> {
        self.claimed_node(b.str("node"))?;
        let (user, _, why, _) = self.resolve_from(b)?;
        user.map_or_else(
            || fail(404, json!({"error": "sender not registered", "detail": why, "tmux_pane": b.str("tmux_pane")})),
            Ok,
        )
    }

    /// Whose name a resulting message goes out in: the owner for the
    /// dashboard (no pane, no session), else the acting agent.
    fn actor(&self, b: &Body) -> Api<String> {
        let no_pane = !b.has("tmux_pane") || b.0["tmux_pane"].is_null();
        if no_pane && b.str("agent_id").is_none_or(|a| a.trim().is_empty()) {
            return match self.principal {
                Principal::Owner => Ok(OWNER.into()),
                Principal::Node(_) => fail(
                    403,
                    json!({"error": "a node must say which agent is acting", "hint": "send tmux_pane or agent_id"}),
                ),
            };
        }
        self.claimed_node(b.str("node"))?;
        let (user, _, why, _) = self.resolve_from(b)?;
        user.map_or_else(
            || {
                fail(
                    404,
                    json!({"error": "acting agent is not registered", "detail": why, "tmux_pane": b.str("tmux_pane")}),
                )
            },
            Ok,
        )
    }

    // ---- routes -------------------------------------------------------------

    pub fn register(&self, b: &Body) -> Api<Value> {
        let node = self.app.node.as_str();
        self.claimed_node(b.str("node"))?;
        let target = b.str("tmux_pane").unwrap_or("");
        let (pane, label, server) = self.pane_ref(target)?;
        let Some(server) = server else {
            return fail(
                404,
                json!({"error": format!(
                    "pane {target} does not resolve on node {node}; register from the agent's live pane or supply its --pane explicitly"
                )}),
            );
        };
        let model = b.text("model");
        let flavor_hint = b.text("flavor").or_else(|| model.map(|m| tmux::infer_flavor(Some(m))));
        let mut session = b.text("agent_id");
        let mut existing: Option<String> = None;
        if let Some(id) = session {
            if self.db.is_retired(None, Some(id))? {
                return fail(409, json!({"error": "this agent session has been retired"}));
            }
            existing = self.db.user_by_agent_id(id)?;
            if let Some(user) = &existing {
                self.own_row_or_403(user)?;
                if self.live_elsewhere(user, &pane, Some(&server))? {
                    // A copy of a live agent's session in another pane: this
                    // pane is its own agent and does not take the id.
                    eprintln!("pane {pane} runs a copy of {user}'s live session; not taking its record");
                    existing = None;
                    session = None;
                }
            }
        }
        if existing.is_none() {
            existing = self.db.user_by_pane(node, &pane, Some(&server))?;
        }
        if let (None, false, Some(flavor)) = (&existing, label.is_empty(), flavor_hint) {
            existing = self.db.user_by_restored_label(node, &label, flavor, &server)?;
        }
        if let Some(user) = &existing {
            self.own_row_or_403(user)?;
        }
        let mut requested: Option<String> = None;
        if let Some(raw) = b.str("requested_user") {
            let name = match names::normalize_requested(raw) {
                Ok(name) => name,
                Err(e) => return fail(400, json!({"error": e, "requested_user": raw})),
            };
            if self.db.is_retired(Some(&name), None)? {
                return fail(409, json!({"error": "this handle is a retired archive"}));
            }
            self.own_row_or_403(&name)?;
            // A handle whose agent is offline can be reclaimed.
            if self.db.name_taken_by_other(&name, session, node, &pane, Some(&server))? && self.is_alive(&name)? {
                return fail(409, json!({"error": "name already taken by another agent", "requested_user": name}));
            }
            requested = Some(name);
        }
        // A handle reserved for a named agent is that agent's alone.
        if let Some(handle) = requested.as_ref().or(existing.as_ref()) {
            if let Some(row) = self.db.recipient(handle)? {
                let holder = text(&row, "agent_id").filter(|a| !a.is_empty());
                if let (true, Some(holder)) = (row["reserved"] != json!(0), holder) {
                    if session != Some(holder) {
                        return fail(
                            409,
                            json!({"error": "that handle is reserved for another agent", "requested_user": handle,
                                                "hint": format!("register with --agent-id {holder} to claim it")}),
                        );
                    }
                }
            }
        }
        let mut renamed_from: Option<String> = None;
        let user_id = match (&requested, &existing) {
            (Some(name), Some(held)) if held != name => {
                if self.db.recipient(name)?.is_some() {
                    return fail(
                        409,
                        json!({"error": format!("this pane is registered as {held}; unregister it before claiming {name}"),
                                            "requested_user": name}),
                    );
                }
                self.db.rename_recipient(held, name)?;
                renamed_from = Some(held.clone());
                name.clone()
            }
            (Some(name), _) => name.clone(),
            (None, Some(held)) => held.clone(),
            (None, None) => names::pick(&self.db.used_handles()?),
        };
        // A re-register that omits model and flavor keeps the stored flavor.
        let current = self.db.recipient(&user_id)?;
        let flavor = flavor_hint.map(String::from).unwrap_or_else(|| {
            current
                .as_ref()
                .and_then(|c| opt(c, "flavor"))
                .filter(|f| !f.is_empty())
                .unwrap_or_else(|| "generic".into())
        });
        let submit_key = b.text("submit_key").unwrap_or_else(|| tmux::submit_key_for_flavor(Some(&flavor)));
        self.db.register(
            &user_id,
            &pane,
            session,
            b.str("model"),
            Some(&flavor),
            b.str("instructions"),
            b.str("message_prefix"),
            Some(submit_key),
            Some(&server),
            Some(&label),
            node,
        )?;
        tmux::tag_pane(&pane, Some(&server), &user_id);
        let registered = self.db.recipient(&user_id)?.unwrap_or_default();
        let peers: Vec<Obj> =
            self.annotated_recipients()?.into_iter().filter(|r| text(r, "user_id") != Some(&user_id)).collect();
        let owner_note = text(&registered, "owner_note");
        Ok(json!({
            "ok": true,
            "user_id": user_id,
            "tmux_pane": pane,
            "pane_label": label,
            "node": registered["node"],
            "agent_id": registered["agent_id"],
            "model": registered["model"],
            "flavor": registered["flavor"],
            "instructions": registered["instructions"],
            "message_prefix": registered["message_prefix"],
            "submit_key": text(&registered, "submit_key").filter(|k| !k.is_empty()).unwrap_or(tmux::DEFAULT_SUBMIT_KEY),
            "assigned": requested.is_none(),
            "requested_user": requested,
            "renamed_from": renamed_from,
            "owner_note": owner_note,
            "protocol_brief": protocol_brief(&user_id, &peers, owner_note),
        }))
    }

    pub fn recipients(&self, q: &Body) -> Api<Value> {
        let mut out = json!({"recipients": self.annotated_recipients()?});
        if q.flag("include_retired_sessions") == Some(true) {
            let sessions: Vec<Value> = self
                .db
                .retired_agents()?
                .iter()
                .filter_map(|r| text(r, "agent_id").filter(|a| !a.is_empty()).map(|a| json!(a)))
                .collect();
            out["retired_sessions"] = json!(sessions);
        }
        Ok(out)
    }

    pub fn whoami(&self, q: &Body) -> Api<Value> {
        self.claimed_node(q.str("node"))?;
        let (user, how, why, (pane, label)) = self.resolve_from(q)?;
        let note = match &user {
            Some(user) => self.db.recipient(user)?.and_then(|r| opt(&r, "owner_note")),
            None => None,
        };
        Ok(json!({
            "user_id": user, "node": self.app.node, "tmux_pane": pane, "pane_label": label,
            "identified_by": user.as_ref().map(|_| how), "detail": why, "owner_note": note,
        }))
    }

    /// A team by name (case-insensitive) or id; 404 or 409 otherwise.
    fn find_team(&self, reference: &str) -> Api<Obj> {
        let fold = |s: &str| caseless::default_case_fold_str(s);
        let teams = self.db.teams()?;
        let by_id: Vec<&Obj> = teams
            .iter()
            .filter(|t| t["id"].as_i64().is_some_and(|id| id.to_string() == reference.trim_start_matches('0')))
            .collect();
        let found = if by_id.is_empty() {
            teams.iter().filter(|t| fold(text(t, "name").unwrap_or("")) == fold(reference)).collect()
        } else {
            by_id
        };
        match found.as_slice() {
            [] => fail(
                404,
                json!({"error": "no such team", "team": reference,
                                   "detail": "give a team name or id; `GET /teams` lists them"}),
            ),
            [team] => Ok((*team).clone()),
            many => {
                let ids: Vec<String> =
                    many.iter().map(|t| format!("{} ({})", t["id"], text(t, "name").unwrap_or(""))).collect();
                fail(
                    409,
                    json!({"error": "team name is ambiguous", "team": reference,
                                 "detail": format!("use the team id: {}", ids.join(", "))}),
                )
            }
        }
    }

    /// Record a failed message for an unregistered recipient, then 404.
    fn missing_recipient<T>(
        &self,
        sender: &str,
        recipient: &str,
        context: Option<&str>,
        content: &str,
        reply_to: Option<i64>,
    ) -> Api<T> {
        let mut detail = json!({"error": "recipient not registered", "recipient": recipient});
        // A stale address must not create history on a name that was freed.
        if !self.db.was_retired(recipient)? && !self.db.is_retired(Some(recipient), None)? {
            let mid = self.db.record_message(
                sender,
                recipient,
                context,
                content,
                "failed",
                Some("recipient not registered"),
                &[],
                reply_to,
            )?;
            detail["message_id"] = json!(mid);
        }
        fail(404, detail)
    }

    /// Record a message, then paste it into the recipient's pane. The row
    /// exists before the paste, so a lost result leaves it marked unknown.
    fn dispatch(
        &self,
        sender: &str,
        recipient: &Obj,
        context: Option<&str>,
        content: &str,
        reply: Option<&Obj>,
    ) -> Api<(i64, &'static str, Option<String>)> {
        let user_id = text(recipient, "user_id").unwrap_or("");
        let (pane, server) = (text(recipient, "tmux_pane").unwrap_or(""), text(recipient, "tmux_server"));
        let reply_note = reply.map_or(String::new(), |original| {
            let mut snippet = squash(text(original, "content").unwrap_or(""));
            if snippet.is_empty() {
                snippet = "(files)".into();
            }
            let cut: String = snippet.chars().take(60).collect();
            let more = if snippet.chars().count() > 60 { "…" } else { "" };
            let (id, from) = (&original["id"], text(original, "sender").unwrap_or(""));
            format!(
                "(in reply to message {id} from {from}: \"{cut}{more}\"; buzz messages --id {id} shows all of it)\n\n"
            )
        });
        let reply_to = reply.and_then(|o| o["id"].as_i64());
        let mid = self.db.record_message(sender, user_id, context, content, "pending", None, &[], reply_to)?;
        let since = recipient["registered_at"].as_f64().unwrap_or(0.0);
        let reminder = sender == OWNER && self.db.owner_reply_reminder_due(user_id, since, OWNER_REPLY_IDLE_SECONDS)?;
        // The Enter that submits a message would answer a modal prompt.
        if let Some(err) = tmux::capture(pane, server, false).0.and_then(|screen| blocking_prompt(user_id, &screen)) {
            self.db.set_message_status(mid, "failed", Some(&err))?;
            return Ok((mid, "failed", Some(err)));
        }
        let body = tmux::format_message(sender, context, &format!("{reply_note}{content}"), reminder);
        let submit_key = text(recipient, "submit_key").filter(|k| !k.is_empty()).unwrap_or(tmux::DEFAULT_SUBMIT_KEY);
        let (status, err) = match tmux::deliver(
            pane,
            server,
            &body,
            text(recipient, "message_prefix"),
            submit_key,
            text(recipient, "flavor"),
        ) {
            tmux::Delivery::Ok => ("delivered", None),
            tmux::Delivery::Failed(e) => ("failed", Some(e)),
            tmux::Delivery::Unknown(e) => ("unknown", Some(e)),
        };
        self.db.set_message_status(mid, status, err.as_deref())?;
        Ok((mid, status, err))
    }

    /// Check the recipient can take a message; if not, record why and 409.
    fn reach(&self, sender: &str, recipient: &Obj, context: Option<&str>, content: &str) -> Api<()> {
        let local = text(recipient, "node") == Some(self.app.node.as_str());
        let snap = if local { self.try_snapshot() } else { None };
        let Some(reason) = self.offline(recipient, local, snap.as_ref()) else { return Ok(()) };
        let user_id = text(recipient, "user_id").unwrap_or("");
        let mid = self.db.record_message(sender, user_id, context, content, "failed", Some(&reason), &[], None)?;
        fail(409, json!({"error": reason, "recipient": user_id, "message_id": mid}))
    }

    /// Deliver a message in `sender`'s name (task notices).
    fn deliver_as(&self, sender: &str, recipient_id: &str, content: &str, context: &str) -> Api<()> {
        let Some(recipient) = self.db.recipient(recipient_id)? else {
            return self.missing_recipient(sender, recipient_id, Some(context), content, None);
        };
        self.reach(sender, &recipient, Some(context), content)?;
        self.dispatch(sender, &recipient, Some(context), content, None)?;
        Ok(())
    }

    pub fn send(&self, b: &Body) -> Api<Value> {
        let sender = self.caller(b)?;
        let (context, content) = (b.str("context"), b.str("content").unwrap_or(""));
        let reply_to = b.int("reply_to");
        let original = match reply_to {
            Some(id) => match self.db.message(id)? {
                Some(m) => Some(m),
                None => return fail(422, json!({"error": format!("no message {id}")})),
            },
            None => None,
        };
        // `queen:<team>` goes to the team's current queen.
        let spec = b.str("recipient").unwrap_or("");
        let queen = spec.get(..6).filter(|p| p.eq_ignore_ascii_case("queen:")).map(|_| spec[6..].trim());
        let (target, via_team) = match queen {
            None => (spec.to_string(), None),
            Some(reference) => {
                let team = self.find_team(reference)?;
                let Some(queen) = opt(&team, "queen").filter(|q| !q.is_empty()) else {
                    return fail(
                        409,
                        json!({"error": "team has no queen", "team": team["name"], "team_id": team["id"]}),
                    );
                };
                (queen, Some(json!({"id": team["id"], "name": team["name"]})))
            }
        };
        if target == OWNER {
            // Messages to the human are recorded for the dashboard only.
            let mid = self.db.record_message(&sender, OWNER, context, content, "delivered", None, &[], reply_to)?;
            return Ok(json!({"ok": true, "status": "delivered", "message_id": mid,
                             "delivered_to_pane": null, "delivery_error": null}));
        }
        let Some(recipient) = self.db.recipient(&target)? else {
            return self.missing_recipient(&sender, &target, context, content, reply_to);
        };
        self.reach(&sender, &recipient, context, content)?;
        let (mid, status, err) = self.dispatch(&sender, &recipient, context, content, original.as_ref())?;
        let mut out = json!({"ok": status == "delivered", "status": status, "message_id": mid,
                             "delivered_to_pane": recipient["tmux_pane"], "delivery_error": err});
        if let Some(team) = via_team {
            out["recipient"] = json!(target);
            out["team"] = team;
        }
        Ok(out)
    }

    /// An agent says, in a line, what it is working on.
    pub fn status(&self, b: &Body) -> Api<Value> {
        let user_id = self.caller(b)?;
        let line = squash(b.str("text").unwrap_or(""));
        if line.is_empty() {
            return fail(422, json!({"error": "status is empty"}));
        }
        self.db.record_summary(&user_id, &line, "agent")?;
        Ok(json!({"ok": true, "user_id": user_id, "status": line}))
    }

    pub fn messages(&self, q: &Body) -> Api<Value> {
        if let Some(id) = q.int("id") {
            return match self.db.message(id)? {
                Some(found) => Ok(json!({"messages": [found]})),
                None => fail(404, json!({"error": format!("no message {id}")})),
            };
        }
        Ok(json!({"messages": self.db.messages(q.str("user"), q.int("limit").unwrap_or(50))?}))
    }

    pub fn tasks_list(&self) -> Api<Value> {
        Ok(json!({"tasks": self.db.tasks()?}))
    }

    fn require_registered_assignee(&self, assignee: Option<&str>) -> Api<()> {
        match assignee.filter(|a| !a.is_empty()) {
            Some(a) if self.db.recipient(a)?.is_none() => {
                fail(404, json!({"error": "assignee not registered", "assignee": a}))
            }
            _ => Ok(()),
        }
    }

    fn require_known_team(&self, team_id: Option<i64>) -> Api<()> {
        match team_id {
            Some(id) if self.db.team(id)?.is_none() => fail(404, json!({"error": "unknown team", "team_id": id})),
            _ => Ok(()),
        }
    }

    /// Tell a task's new assignee (an agent) about it. A missing or offline
    /// assignee is not an error for the task itself.
    fn notify_assignment(&self, task: &Obj, actor: &str) -> Api<()> {
        let (id, assignee) = (&task["id"], text(task, "assignee").unwrap_or(""));
        let recipient = self.db.recipient(assignee)?;
        let team = match recipient.as_ref().and_then(|r| r["team_id"].as_i64()) {
            Some(team_id) => self.db.team(team_id)?,
            None => None,
        };
        let team_line = match &team {
            Some(team) if text(team, "queen") != Some(assignee) => {
                let name = text(team, "name").unwrap_or("");
                match text(team, "queen").filter(|q| !q.is_empty()) {
                    Some(queen) => format!(" Team '{name}'; queen {queen}: report progress to them."),
                    None => format!(" Team '{name}' (no queen)."),
                }
            }
            _ => String::new(),
        };
        let mut content = format!("You are assigned task #{id}: {}.", text(task, "title").unwrap_or(""));
        if let Some(description) = text(task, "description").filter(|d| !d.is_empty()) {
            content += &format!(" Details: {description}.");
        }
        content += &format!(
            " Use branch task/{id} in its own git worktree, and record it as you start: buzz task-update {id} \
             --worktree /absolute/path --status picked_up. Keep `buzz status` current as the work moves \
             (\"testing #{id}\", \"waiting on review\") and end with \"done: #{id}\". Close with buzz task-update {id} \
             --status done --note \"...\": the note is required.{team_line}"
        );
        swallow_http(self.deliver_as(actor, assignee, &content, &format!("task #{id}")))
    }

    /// Tell a team's queen (or, with no queen, every member) about a task.
    fn notify_team_assignment(&self, task: &Obj, actor: &str) -> Api<()> {
        let Some(team) = (match task["team_id"].as_i64() {
            Some(team_id) => self.db.team(team_id)?,
            None => None,
        }) else {
            return Ok(());
        };
        let (id, title, name) = (&task["id"], text(task, "title").unwrap_or(""), text(&team, "name").unwrap_or(""));
        let detail =
            text(task, "description").filter(|d| !d.is_empty()).map_or(String::new(), |d| format!(" Details: {d}."));
        let (content, targets) = match text(&team, "queen").filter(|q| !q.is_empty()) {
            Some(queen) => (
                format!(
                    "Task #{id} for your team '{name}': {title}.{detail} As queen, parcel it out with buzz \
                         task-update {id} --assignee <member>, then keep an eye on it."
                ),
                vec![queen.to_string()],
            ),
            None => (
                format!(
                    "Task #{id} for your team '{name}' (no queen yet): {title}.{detail} Whoever takes it: buzz \
                         task-update {id} --assignee <yourself>."
                ),
                team["members"].as_array().into_iter().flatten().filter_map(|m| m.as_str().map(String::from)).collect(),
            ),
        };
        for target in targets {
            swallow_http(self.deliver_as(actor, &target, &content, &format!("task #{id}")))?;
        }
        Ok(())
    }

    pub fn tasks_create(&self, b: &Body) -> Api<Value> {
        let actor = self.actor(b)?;
        self.require_registered_assignee(b.str("assignee"))?;
        self.require_known_team(b.int("team_id"))?;
        let title = b.str("title").unwrap_or("").trim();
        if title.is_empty() {
            return fail(400, json!({"error": "task title is required"}));
        }
        // Attachments are not cloned: no upload exists, so every name is unknown.
        let files = b.strs("attachments");
        if !files.is_empty() {
            return fail(400, json!({"error": "unknown attachment", "attachments": files}));
        }
        let deps = b.ints("depends_on").unwrap_or_default();
        let task = match self.db.create_task(
            title,
            b.str("description"),
            b.str("assignee"),
            b.int("team_id"),
            &files,
            &deps,
        ) {
            Ok(task) => task,
            Err(TaskError::Db(e)) => return Err(e.into()),
            Err(TaskError::Invalid(e)) => return fail(400, json!({"error": e})),
            Err(TaskError::NoteRequired) => {
                return fail(400, json!({"error": "a task needs a note before it can be closed"}))
            }
        };
        if text(&task, "assignee").is_some_and(|a| !a.is_empty()) {
            self.notify_assignment(&task, &actor)?;
        } else if task["team_id"].as_i64().is_some_and(|t| t != 0) {
            self.notify_team_assignment(&task, &actor)?;
        }
        Ok(json!({"ok": true, "task": task}))
    }

    pub fn tasks_update(&self, id: i64, b: &Body) -> Api<Value> {
        let actor = self.actor(b)?;
        let Some(before) = self.db.task(id)? else { return fail(404, json!({"error": "unknown task"})) };
        let cleared = |name: &str| b.str(name).map(str::trim).filter(|s| !s.is_empty()).map(String::from);
        let mut change = TaskChange { status: b.str("status").map(String::from), ..TaskChange::default() };
        if let Some(title) = b.str("title") {
            if title.trim().is_empty() {
                return fail(422, json!({"error": "a task needs a title"}));
            }
            change.title = Some(title.trim().to_string());
        }
        if b.has("description") {
            change.description = Some(cleared("description"));
        }
        if b.has("assignee") {
            self.require_registered_assignee(b.str("assignee"))?;
            change.assignee = Some(b.text("assignee").map(String::from));
        }
        if b.has("team_id") {
            self.require_known_team(b.int("team_id"))?;
            change.team_id = Some(b.int("team_id"));
        }
        if b.has("worktree") {
            change.worktree = Some(b.str("worktree").map(String::from));
            change.worktree_node = Some(Some(b.text("worktree_node").unwrap_or(&self.app.node).to_string()));
        }
        if b.has("note") {
            change.note = Some(cleared("note"));
        }
        if b.has("depends_on") {
            change.depends_on = Some(b.ints("depends_on").unwrap_or_default());
        }
        let task = match self.db.update_task(id, &change) {
            Ok(Some(task)) => task,
            Ok(None) => return fail(404, json!({"error": "unknown task"})),
            Err(TaskError::Db(e)) => return Err(e.into()),
            Err(TaskError::NoteRequired) => {
                return fail(
                    422,
                    json!({"error": "a task needs a note before it can be closed", "note": NOTE_GUIDANCE}),
                )
            }
            Err(TaskError::Invalid(e)) => return fail(400, json!({"error": e})),
        };
        if text(&task, "assignee").is_some_and(|a| !a.is_empty()) && task["assignee"] != before["assignee"] {
            self.notify_assignment(&task, &actor)?;
        } else if task["team_id"].as_i64().is_some_and(|t| t != 0) && task["team_id"] != before["team_id"] {
            self.notify_team_assignment(&task, &actor)?;
        }
        Ok(json!({"ok": true, "task": task}))
    }

    /// Everything the dashboard draws, in one response.
    pub fn state(&self, q: &Body) -> Api<Value> {
        self.require_owner()?;
        let mut summaries = self.db.summaries_by_user(db::SUMMARY_HISTORY)?;
        let mut recipients = self.annotated_recipients()?;
        for r in &mut recipients {
            let lines = summaries.get(text(r, "user_id").unwrap_or("")).cloned().unwrap_or_default();
            let compact = tmux::compact_command_for_flavor(text(r, "flavor"));
            r.insert("pane_alive".into(), r["alive"].clone());
            r.insert("summaries".into(), Value::Array(lines));
            r.insert("compact_command".into(), json!(compact));
            // The activity monitor is not cloned: every agent reads unknown.
            r.insert(
                "activity".into(),
                json!({"status": "unknown", "detail": null, "error": null, "since": null, "context": null}),
            );
        }
        let mut messages = self.db.messages(None, q.int("limit").unwrap_or(300))?;
        messages.reverse();
        let mut nodes =
            vec![json!({"name": self.app.node, "local": true, "connected": true, "spawn_dirs": self.app.spawn_dirs})];
        for mut node in self.db.nodes()? {
            node.insert("connected".into(), json!(false));
            node.insert("spawn_dirs".into(), json!([]));
            nodes.push(Value::Object(node));
        }
        let mut teams = self.db.teams()?;
        for team in &mut teams {
            let unread = self.db.board_unread(team["id"].as_i64().unwrap_or(0), OWNER)?;
            team.insert("board_unread".into(), json!(unread));
        }
        let retired: Vec<Value> = self
            .db
            .retired_agents()?
            .iter()
            .map(|r| {
                let lines = summaries.remove(text(r, "archive_id").unwrap_or("")).unwrap_or_default();
                json!({"archive_id": r["archive_id"], "original_id": r["original_id"], "retired_at": r["retired_at"], "summaries": lines})
            })
            .collect();
        Ok(json!({
            "now": db::now(),
            "recipients": recipients,
            "retired_agents": retired,
            "nodes": nodes,
            "messages": messages,
            "pins": self.db.pins()?,
            "tasks": self.db.tasks()?,
            "teams": teams,
            "supervisor": self.db.supervisor()?,
            "tabs": [],
        }))
    }

    /// The agent's visible screen, with colors, for the dashboard.
    pub fn peek(&self, user_id: &str) -> Api<Value> {
        self.require_owner()?;
        let Some(recipient) = self.db.recipient(user_id)? else { return fail(404, json!({"error": "unknown agent"})) };
        let pane = text(&recipient, "tmux_pane").unwrap_or("");
        let (screen, err) = if text(&recipient, "node") == Some(self.app.node.as_str()) {
            tmux::capture(pane, text(&recipient, "tmux_server"), true)
        } else {
            (None, Some(format!("node {} is not connected", text(&recipient, "node").unwrap_or(""))))
        };
        let label = text(&recipient, "pane_label").filter(|l| !l.is_empty()).unwrap_or(pane);
        Ok(json!({"user_id": user_id, "tmux_pane": pane, "pane_label": label, "text": screen, "error": err}))
    }
}

/// Python's `except HTTPException: pass`: a notice that cannot be delivered
/// does not fail the task write. Database errors still do.
fn swallow_http(result: Api<()>) -> Api<()> {
    match result {
        Err(e) if e.status != 500 => Ok(()),
        other => other,
    }
}

/// Why a row's pane id no longer identifies its pane, or None.
fn stale(r: &Obj, server: Option<&str>) -> Option<&'static str> {
    let server = server?;
    match text(r, "tmux_server") {
        Some(db::UNBOUND) => Some("its pane could not be verified when pane ids were introduced"),
        Some(bound) if bound != server => Some("its pane is from an earlier tmux session"),
        None if text(r, "tmux_pane").is_some_and(|p| p.starts_with('%')) => {
            Some("its pane id was never tied to a tmux session")
        }
        _ => None,
    }
}

/// (harness, title line, answer that must be on screen at or after it).
const TRUST_PROMPTS: [(&str, &str, &str); 4] = [
    ("Antigravity", r"^\W*Do you trust the contents of this project\?", "Yes, I trust this folder"),
    ("Claude", r"^\W*Accessing workspace:\s*$", "Yes, I trust this folder"),
    ("Codex", r"^\W*Trust this folder\?", "Trust and continue"),
    ("Codex", r"^\W*Do you trust the contents of this directory\?", r"\bYes, continue\b"),
];

/// (label, title line, answer that must be on screen after it).
const DOWNGRADE_PROMPTS: [(&str, &str, &str); 2] = [
    ("Codex's low-quota model switch prompt", r"^\W*Switch to .+ for lower credit usage\?", r"\bKeep current model\b"),
    (
        "Codex's Luna Reserve recovery prompt",
        r"^\W*Your included usage is exhausted\.",
        r"\bContinue with Luna Reserve\b",
    ),
];

type Prompts = Vec<(&'static str, Regex, Regex)>;

fn compile(table: &[(&'static str, &str, &str)]) -> Prompts {
    table
        .iter()
        .map(|(name, title, answer)| (*name, Regex::new(title).expect("static"), Regex::new(answer).expect("static")))
        .collect()
}

/// The error for a pane showing a modal prompt that a pasted message (and
/// its Enter) would answer, or None.
fn blocking_prompt(user_id: &str, screen: &str) -> Option<String> {
    static TRUST: OnceLock<Prompts> = OnceLock::new();
    static DOWNGRADE: OnceLock<Prompts> = OnceLock::new();
    let lines: Vec<&str> = screen.lines().collect();
    for (harness, title, answer) in TRUST.get_or_init(|| compile(&TRUST_PROMPTS)) {
        let Some(at) = lines.iter().position(|l| title.is_match(l)) else { continue };
        if !lines[at..].iter().any(|l| answer.is_match(l)) {
            continue;
        }
        let folder = lines[at + 1..].iter().map(|l| l.trim()).find(|l| !l.is_empty()).unwrap_or("");
        let what = if *harness == "Claude" && folder.starts_with('/') {
            format!("{harness}'s workspace trust prompt for {folder}")
        } else {
            format!("{harness}'s workspace trust prompt")
        };
        return Some(format!(
            "not delivered: {user_id} is waiting at {what}. Answer it in its pane first; a pasted \
                             message would answer it, and Claude's default there is No, exit."
        ));
    }
    for (label, title, answer) in DOWNGRADE.get_or_init(|| compile(&DOWNGRADE_PROMPTS)) {
        let Some(at) = lines.iter().position(|l| title.is_match(l)) else { continue };
        if lines[at + 1..].iter().any(|l| answer.is_match(l)) {
            return Some(format!(
                "not delivered: {user_id} is waiting at {label}. Answer it in its pane first; a pasted \
                                 message would accept the model downgrade."
            ));
        }
    }
    None
}

/// The one-shot primer an agent reads in its register response.
fn protocol_brief(user_id: &str, peers: &[Obj], owner_note: Option<&str>) -> String {
    let line = |p: &Obj| {
        let mut tags: Vec<String> = Vec::new();
        let set = |key: &str| text(p, key).filter(|v| !v.is_empty());
        tags.extend(set("flavor").map(|v| format!("flavor={v}")));
        tags.extend(set("model").map(String::from));
        tags.extend(set("node").map(|v| format!("node={v}")));
        tags.extend(set("agent_id").map(|v| format!("agent={v}")));
        tags.extend(set("submit_key").map(|v| format!("submit={v}")));
        if p["alive"] == json!(false) {
            tags.push("OFFLINE".into());
        }
        let suffix = if tags.is_empty() { String::new() } else { format!(" ({})", tags.join(", ")) };
        let instructions = set("instructions").map_or(String::new(), |i| format!(" -- {i}"));
        format!("  - {}{suffix}{instructions}", text(p, "user_id").unwrap_or(""))
    };
    let peer_lines = if peers.is_empty() {
        "  (none yet)".to_string()
    } else {
        peers.iter().map(line).collect::<Vec<_>>().join("\n")
    };
    let offline_note = if peers.iter().any(|p| p["alive"] == json!(false)) {
        "Peers tagged OFFLINE are registered but not running (pane gone or a bare shell); sending to them is refused \
         until they restart.\n\n"
    } else {
        ""
    };
    let note =
        owner_note.filter(|n| !n.is_empty()).map_or(String::new(), |n| format!("Owner note about your work: {n}\n"));
    include_str!("brief.txt")
        .replace("{offline_note}", offline_note)
        .replace("{owner_note}", &note)
        .replace("{user}", user_id)
        .replace("{peers}", &peer_lines)
}
