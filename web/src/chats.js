// No imports, so `node --test web/test` can exercise it without a browser.

// The owner's conversations, one per agent, newest first. `messages` may hold
// the same message twice (full history plus the live poll); ids decide. With
// a query, only conversations with a message containing every word are kept,
// and each carries its newest matching message.
export function ownerChats(messages, query = "") {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const seen = new Set();
  const byAgent = new Map();
  for (const m of messages) {
    if (seen.has(m.id) || (m.sender !== "owner" && m.recipient !== "owner")) continue;
    if (m.sender === "owner" && m.recipient === "owner") continue;
    seen.add(m.id);
    const agent = m.sender === "owner" ? m.recipient : m.sender;
    const chat = byAgent.get(agent) || { agent, last: null, count: 0, match: null, matches: 0 };
    chat.count += 1;
    if (!chat.last || m.ts > chat.last.ts) chat.last = m;
    if (words.length) {
      const text = `${m.context || ""} ${m.content || ""}`.toLowerCase();
      if (words.every(w => text.includes(w))) {
        chat.matches += 1;
        if (!chat.match || m.ts > chat.match.ts) chat.match = m;
      }
    }
    byAgent.set(agent, chat);
  }
  return [...byAgent.values()]
    .filter(c => !words.length || c.matches > 0)
    .sort((a, b) => (words.length ? b.match.ts - a.match.ts : b.last.ts - a.last.ts));
}

// Agent-to-agent traffic, organized so that N agents don't mean N² lists:
// - a "thread" is one burst of talk between one pair of agents, closed by a
//   quiet gap (`gap` seconds); the same pair talking again later is a new one;
// - the same text from one sender to several agents within `fanout` seconds
//   is one broadcast, and a sender's broadcasts form their own threads;
// - messages to or from the owner (the other chats view) and an agent's
//   notes to itself (reminders it sets) are left out; `selfNotes` counts them.
// Threads come newest-activity first. With a query, a thread is kept when
// every word appears in its messages or in its agents' names. With `members`
// (a Set of handles), only threads involving one of them are kept.
export function agentThreads(messages, { query = "", members = null, gap = 900, fanout = 120 } = {}) {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const seen = new Set();
  const own = [];
  let selfNotes = 0;
  for (const m of messages) {
    if (seen.has(m.id)) continue;
    seen.add(m.id);
    if (m.sender === "owner" || m.recipient === "owner") continue;
    if (m.sender === m.recipient) { selfNotes += 1; continue; }
    own.push(m);
  }
  own.sort((a, b) => a.ts - b.ts || a.id - b.id);

  // One item per message, or per broadcast (one text, several recipients).
  const items = [];
  const lastCopy = new Map();
  for (const m of own) {
    const key = `${m.sender}\u0000${m.content}`;
    const prev = lastCopy.get(key);
    if (prev && m.ts - prev.m.ts <= fanout && !prev.to.includes(m.recipient)) {
      prev.to.push(m.recipient);
      prev.ids.push(m.id);
      continue;
    }
    const item = { m, to: [m.recipient], ids: [m.id] };
    lastCopy.set(key, item);
    items.push(item);
  }

  const open = new Map();
  const threads = [];
  for (const item of items) {
    const { m } = item;
    const broadcast = item.to.length > 1;
    const key = broadcast ? `${m.sender}\u0000*` : [m.sender, m.recipient].sort().join("\u0000");
    let t = open.get(key);
    if (!t || m.ts - t.end > gap) {
      t = { key: `${key}\u0000${m.id}`, broadcast, people: broadcast ? [m.sender] : [m.sender, m.recipient].sort(),
            to: new Set(), start: m.ts, end: m.ts, items: [], count: 0 };
      open.set(key, t);
      threads.push(t);
    }
    item.to.forEach(r => t.to.add(r));
    t.items.push(item);
    t.end = m.ts;
    t.count += item.ids.length;
  }

  const kept = threads.filter(t => {
    const names = [...t.people, ...t.to];
    if (members && !names.some(n => members.has(n))) return false;
    if (!words.length) return true;
    const text = `${names.join(" ")} ${t.items.map(i => `${i.m.context || ""} ${i.m.content || ""}`).join(" ")}`.toLowerCase();
    return words.every(w => text.includes(w));
  });
  kept.sort((a, b) => b.end - a.end);
  kept.forEach(t => { t.to = [...t.to].sort(); });
  return { threads: kept, selfNotes };
}
