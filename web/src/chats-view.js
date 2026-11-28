import { html } from "htm/preact";
import { useEffect, useMemo, useState } from "preact/hooks";

import { agentHash } from "./agent-route.js";
import { agentThreads } from "./chats.js";
import { hl, searchWords, wordsRe } from "./highlight.js";
import { renderMarkdown } from "./markdown.js";
import { shellNewlines } from "./newlines.js";
import { PinnedList } from "./pins.js";
import { Crown } from "./queen.js";
import { ReplyPreview } from "./reply-preview.js";
import { Bee, ErrorMark, STATE, agentStatus, rel, retiredLabel } from "./shared.js";

// "with you": every conversation the owner has had, one row per
// agent, newest first, to find whom you asked about something that never
// became a task. "you and queens" narrows those to the current team leads.
// "between agents": the agents' talk with each other, as
// bursts per pair and broadcasts (see agentThreads), newest first under day
// headings. Each view's history loads once when it opens; new messages come
// from the poll.
export const CHATS_ROUTE = "#/chats";
const chatsParams = () => new URLSearchParams(location.hash.split("?")[1] || "");
const chatsQuery = () => chatsParams().get("q") || "";
// Agent talk beyond this many recent messages stays in each agent's own page.
const AGENT_TALK_LIMIT = 4000;

function snippet(text, words, width = 240) {
  const flat = (text || "").replace(/\s+/g, " ").trim();
  const at = words.length ? flat.toLowerCase().indexOf(words[0]) : -1;
  const start = at > 80 ? at - 60 : 0;
  const cut = flat.slice(start, start + width);
  return `${start ? "…" : ""}${cut}${start + width < flat.length ? "…" : ""}`;
}

export function ChatsView({ state, unreadFor, refresh }) {
  const [view, setView] = useState(() => {
    const selected = chatsParams().get("view");
    return ["agents", "queens"].includes(selected) ? selected : "you";
  });
  const pick = (v) => {
    setView(v);
    history.replaceState(null, "", v === "you" ? CHATS_ROUTE : `${CHATS_ROUTE}?view=${v}`);
  };
  return html`<div class="chats">
    <${PinnedList} pins=${state.pins} now=${state.now} refresh=${refresh} />
    <div class="agents-view-switch chats-switch" role="group" aria-label="Which chats">
      <button type="button" aria-pressed=${view === "you"} onClick=${() => pick("you")}>with you</button>
      <button type="button" aria-pressed=${view === "queens"} onClick=${() => pick("queens")}>you and queens</button>
      <button type="button" aria-pressed=${view === "agents"} onClick=${() => pick("agents")}>between agents</button>
    </div>
    ${view === "agents"
      ? html`<${AgentTalk} state=${state} />`
      : html`<${OwnerChats} key=${view} state=${state} unreadFor=${unreadFor} queensOnly=${view === "queens"} />`}
  </div>`;
}

const clock = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const dayOf = (ts) => new Date(ts * 1000).toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });

function AgentTalk({ state }) {
  const [full, setFull] = useState(null);
  const [query, setQuery] = useState(chatsQuery);
  const [team, setTeam] = useState("");
  useEffect(() => {
    let live = true;
    fetch(`/messages?limit=${AGENT_TALK_LIMIT}`)
      .then(r => r.json())
      .then(d => { if (live) setFull(d.messages || []); })
      .catch(() => { if (live) setFull([]); });
    return () => { live = false; };
  }, []);
  const update = (q) => {
    setQuery(q);
    history.replaceState(null, "", `${CHATS_ROUTE}?view=agents${q ? `&q=${encodeURIComponent(q)}` : ""}`);
  };
  const teams = state.teams || [];
  const members = useMemo(
    () => (team ? new Set(state.recipients.filter(r => String(r.team_id) === team).map(r => r.user_id)) : null),
    [team, state.recipients],
  );
  const { threads, selfNotes } = useMemo(
    () => agentThreads([...state.messages, ...(full || [])], { query, members }),
    [state.messages, full, query, members],
  );
  const words = searchWords(query);
  const oldest = full && full.length >= AGENT_TALK_LIMIT ? full[full.length - 1].ts : null;
  let day = null;
  return html`
    <h2>between agents <span class="count">· ${threads.length} conversation${threads.length === 1 ? "" : "s"}${full === null ? " · loading…" : ""}</span></h2>
    <div class="agent-talk-filters">
      <input type="text" class="h-search chats-search" value=${query} autofocus
        placeholder="search agent talk: a name, a task, a word…"
        aria-label="Search agent talk" onInput=${e => update(e.target.value)}
        onKeyDown=${e => { if (e.key === "Escape" && query) { e.stopPropagation(); update(""); } }} />
      ${teams.length > 0 && html`<select aria-label="Team" value=${team} onChange=${e => setTeam(e.target.value)}>
        <option value="">all teams</option>
        ${teams.map(t => html`<option key=${t.id} value=${String(t.id)}>${t.name}</option>`)}
      </select>`}
    </div>
    <p class="agent-talk-note">Grouped by pair: a quiet gap of 15 min starts a new conversation. The same text sent to several agents shows once.
      ${selfNotes > 0 && ` ${selfNotes} notes agents left themselves are hidden.`}
      ${oldest && ` Showing talk since ${dayOf(oldest)} ${clock(oldest)}.`}</p>
    ${threads.length === 0
      ? html`<div class="empty">${full === null ? "Loading…" : query || team ? "No agent talk matches." : "No agent talk yet."}</div>`
      : html`<div class="agent-talk">${threads.map(t => {
          const d = dayOf(t.end);
          const heading = d !== day ? (day = d, html`<h3 class="agent-talk-day">${d}</h3>`) : null;
          return html`${heading}<${TalkThread} key=${t.key} t=${t} words=${words} />`;
        })}</div>`}`;
}

// One burst of agent talk; its messages render only while it is open.
function TalkThread({ t, words }) {
  const [open, setOpen] = useState(false);
  const last = t.items[t.items.length - 1];
  const title = t.broadcast
    ? html`${t.people[0]} <span class="agent-talk-arrow">→</span> ${t.to.join(", ")}`
    : html`${t.people[0]} <span class="agent-talk-arrow">↔</span> ${t.people[1]}`;
  return html`<details class="agent-talk-thread" onToggle=${e => setOpen(e.currentTarget.open)}>
    <summary>
      <span class="chat-who">${title}<span class="chat-when">${clock(t.start)}${t.end - t.start >= 60 ? `–${clock(t.end)}` : ""} · ${t.count} msg${t.count === 1 ? "" : "s"}</span></span>
      <span class="chat-line"><b>${last.m.sender}:</b> ${hl(snippet(last.m.content, words, 200), wordsRe(words))}</span>
    </summary>
    ${open && html`<div class="agent-talk-msgs">${t.items.map(i => html`<div key=${i.ids[0]} class="agent-talk-msg" data-message-id=${i.m.id} tabindex="-1" onAnimationEnd=${e => e.currentTarget.classList.remove("reply-highlight")}>
      <div class="agent-talk-hdr"><b>${i.m.sender}</b> → ${i.to.join(", ")} · ${clock(i.m.ts)}${i.m.context ? ` · ${i.m.context}` : ""}</div>
      <${ReplyPreview} message=${i.m} messages=${t.items.map(item => item.m)} />
      <div class="md" dangerouslySetInnerHTML=${{ __html: renderMarkdown(shellNewlines(i.m.content)) }} />
    </div>`)}</div>`}
  </details>`;
}

function OwnerChats({ state, unreadFor, queensOnly = false }) {
  const [chats, setChats] = useState(null);
  const [query, setQuery] = useState(chatsQuery);
  // The server builds the rows (one per conversation, search included). The
  // list is fetched again when the search or the newest message changes.
  const newest = state.messages.reduce((n, m) => Math.max(n, m.id), 0);
  const queens = (state.teams || []).map(t => t.queen || "").join(",");
  const archives = new Map((state.retired_agents || []).map(r => [r.archive_id, retiredLabel(r)]));
  const archiveVersion = [...archives.keys()].join(",");
  useEffect(() => {
    let live = true;
    const params = new URLSearchParams({ q: query });
    if (queensOnly) params.set("queens", "true");
    const timer = setTimeout(() => {
      fetch(`/api/chats?${params}`)
        .then(r => r.json())
        .then(d => { if (live) setChats(d.chats || []); })
        .catch(() => { if (live) setChats(c => c || []); });
    }, query ? 150 : 0);
    return () => { live = false; clearTimeout(timer); };
  }, [query, queensOnly, newest, queens, archiveVersion]);
  const update = (q) => {
    setQuery(q);
    const params = new URLSearchParams();
    if (queensOnly) params.set("view", "queens");
    if (q) params.set("q", q);
    history.replaceState(null, "", params.size ? `${CHATS_ROUTE}?${params}` : CHATS_ROUTE);
  };
  const words = searchWords(query);
  if (chats === null) return html`<h2>${queensOnly ? "you and queens" : "with you"} <span class="count">· loading…</span></h2>`;
  const byId = new Map(state.recipients.map(r => [r.user_id, r]));
  return html`
    <h2>${queensOnly ? "you and queens" : "with you"} <span class="count">· ${chats.length}</span></h2>
    <input type="text" class="h-search chats-search" value=${query} autofocus
      placeholder=${queensOnly ? "search your conversations with queens…" : "search your conversations: who did I ask about…"}
      aria-label=${queensOnly ? "Search your conversations with queens" : "Search your conversations"} onInput=${e => update(e.target.value)}
      onKeyDown=${e => { if (e.key === "Escape" && query) { e.stopPropagation(); update(""); } }} />
    ${chats.length === 0
      ? html`<div class="empty">${query ? html`No conversation mentions "<b>${query}</b>".` : queensOnly ? "No conversations with current team queens yet." : "No conversations yet."}</div>`
      : html`<div class="chat-list">${chats.map(c => {
          const r = byId.get(c.agent);
          const st = STATE[r ? agentStatus(r) : "unknown"] || STATE.unknown;
          const m = c.match || c.last;
          // A search match opens the conversation at that message; without a
          // search the row opens the end of the conversation, as before.
          const matchId = c.match?.id ?? null;
          return html`<a key=${c.agent} class="chat-row" href=${agentHash(c.agent, matchId)}>
            ${r ? html`<${Bee} node=${r.node} flavor=${r.flavor} error=${r.activity?.error} size="small" working=${st.cls === "working"} />`
              : html`<span class="chat-gone" aria-hidden="true">◌</span>`}
            <span class="chat-main">
              <span class="chat-who">${archives.get(c.agent) || c.agent}<${ErrorMark} error=${r?.activity?.error} /><${Crown} teams=${state.teams} user=${c.agent} word=${!queensOnly} /><span class=${`status ${st.cls}`} title=${r ? st.word : "no longer registered"}></span>
                ${unreadFor(c.agent) && html`<span class="team-mate-unread" title="new reply">●</span>`}
                <span class="chat-when">${rel(m.ts, state.now)}${c.match ? ` · ${c.matches} match${c.matches === 1 ? "" : "es"}` : ` · ${c.count} msg${c.count === 1 ? "" : "s"}`}</span></span>
              <span class="chat-line">${!!m.notify && html`<span class="notification-mark" role="img" aria-label="notification" title="Agent notification">🔔</span> `}<b>${m.sender === "owner" ? "you" : m.sender}:</b> ${hl(snippet(m.content, words), wordsRe(words))}</span>
            </span>
          </a>`;
        })}</div>`}`;
}
