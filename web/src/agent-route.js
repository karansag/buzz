// No imports, so `node --test web/test` can exercise it without a browser.

// The agent page's route: #/agent/<handle>, optionally with ?m=<message id> to
// open the conversation at one message. One parser and one builder, so links
// from the chats search, other search UIs and the router agree.
export const AGENT_ROUTE = "#/agent/";

export function agentHash(user, messageId = null) {
  const base = `${AGENT_ROUTE}${encodeURIComponent(user)}`;
  return messageId ? `${base}?m=${messageId}` : base;
}

// The message id in a query string, or null when it is missing or unusable.
// A bad ?m= is ignored rather than failing the whole route: the page still
// opens at the end of the conversation.
export function messageParam(query) {
  const value = new URLSearchParams(query).get("m");
  return value && /^\d+$/.test(value) && Number(value) > 0 ? Number(value) : null;
}

// { user, messageId } for an agent route, or null for any other hash.
export function parseAgentRoute(hash = "") {
  if (!hash.startsWith(AGENT_ROUTE)) return null;
  const rest = hash.slice(AGENT_ROUTE.length);
  const cut = rest.indexOf("?");
  const raw = cut < 0 ? rest : rest.slice(0, cut);
  let user = raw;
  try { user = decodeURIComponent(raw); } catch { /* keep the raw handle */ }
  if (!user) return null;
  return { user, messageId: cut < 0 ? null : messageParam(rest.slice(cut + 1)) };
}
