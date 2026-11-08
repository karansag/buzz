// Pure decisions the dashboard makes about server answers and spawn targets.
// No imports, so `node --test web/test` can exercise them without a browser.

// What a /owner/send answer means. The HTTP status alone says nothing: a
// node's failed or unknown result comes back as HTTP 200 with a status.
// Only a recognised, structured answer proves anything. A body that could
// not be read (truncated, a proxy's HTML error page) or that carries no
// status proves neither delivery nor failure, so it is "uncertain".
function structured(body) {
  return body !== null && typeof body === "object" && !Array.isArray(body);
}

export function deliveryOutcome(httpOk, body) {
  if (!structured(body)) return { status: "uncertain", reason: "the server's answer could not be read" };
  const b = body;
  // An explicit status is the server's word, whatever the HTTP code.
  if (b.status === "delivered") return { status: "delivered", reason: null };
  if (b.status === "unknown") return { status: "unknown", reason: b.delivery_error || "result lost" };
  if (b.status === "failed") return { status: "failed", reason: b.delivery_error || "delivery failed" };
  const detail = structured(b.detail) ? b.detail : {};
  if (detail.status === "unknown") return { status: "unknown", reason: detail.error || detail.detail || "result lost" };
  if (!httpOk && (detail.error || b.error)) {
    // A refusal the server recorded: offline recipient, unknown handle.
    return { status: "failed", reason: detail.error || b.error };
  }
  return { status: "uncertain", reason: "the server's answer was not recognised" };
}

// The server never answered. The request may or may not have arrived, so
// this is not a definite failure and must not be reported as one.
export function unansweredOutcome(err) {
  return { status: "uncertain", reason: (err && err.message) || "no answer from the server" };
}

// The id a draft is sent under. A draft that comes back after an unconfirmed
// send keeps that attempt's id, so sending it again lets the server say the
// first copy already arrived instead of pasting a second one. Edited text is
// a new message and gets a new id.
export function draftClientId(draft, retryOf, makeId) {
  const same = retryOf && retryOf.text === draft.text && retryOf.context === draft.context
    && (retryOf.reply_to ?? null) === (draft.reply_to ?? null)
    && JSON.stringify(retryOf.images || []) === JSON.stringify(draft.images || []);
  return same ? retryOf.clientId : makeId();
}

// Where a spawn would go, given the machines the hub knows right now and
// what the user picked. A pick that has since gone away, or is no longer
// connected, is kept and shown as unusable rather than quietly replaced by
// the hub; an empty pick means the hub itself. `dirs` are the folders that
// machine lets a new agent start in (AGENT_SWARM_SPAWN_DIRS), first = default.
export function spawnTarget(nodes, selected, harnesses) {
  const all = Array.isArray(nodes) ? nodes : [];
  const dirsOf = n => (n && Array.isArray(n.spawn_dirs) ? n.spawn_dirs : []);
  const local = all.find(n => n.local) || null;
  const here = { ok: true, remote: false, node: null, harnesses, dirs: dirsOf(local), reason: null };
  if (!selected) return here;
  const n = all.find(x => x.name === selected);
  const blocked = reason => ({ ok: false, remote: true, node: selected, harnesses: [], dirs: [], reason });
  if (!n) return blocked(`${selected} is no longer enrolled`);
  if (n.local) return here;
  if (!n.connected) return blocked(`${selected} is not connected`);
  const offered = (harnesses || []).filter(h => (n.harnesses || []).includes(h.flavor));
  if (offered.length === 0) return blocked(`${selected} reports no spawnable harness`);
  return { ok: true, remote: true, node: selected, harnesses: offered, dirs: dirsOf(n), reason: null };
}

// What a /agents/spawn answer means. The window may exist without the
// harness having started in it (launch unknown), and a 502 says the node
// could not tell whether a window was made at all.
export function spawnOutcome(httpOk, body) {
  if (!structured(body)) return { status: "uncertain", reason: "the server's answer could not be read" };
  const b = body;
  if (b.launch === "ok" && b.user_id) return { status: "ok", reason: null, user: b.user_id };
  if (b.launch === "unknown") {
    return { status: "unknown", reason: b.launch_error || "the launch command did not report back", user: b.user_id };
  }
  const detail = structured(b.detail) ? b.detail : {};
  if (detail.status === "unknown") return { status: "unknown", reason: detail.detail || detail.error || "no report" };
  if (!httpOk && (detail.status === "failed" || detail.error || detail.detail || b.error)) {
    return { status: "failed", reason: detail.detail || detail.error || b.error || "spawn failed" };
  }
  return { status: "uncertain", reason: "the server's answer was not recognised" };
}
