import { AttachmentList } from "./attachments.js";
import { html } from "htm/preact";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import { Avatar, SUMMARY_SOURCE, focusHash, hue, patchTask, rel } from "./shared.js";
import { agentChips } from "./agent-chips.js";
import { TaskStatusActions } from "./task-status.js";
import { TaskTrash } from "./task-trash.js";

/* The history view: every task as a tile, newest first, with a live text
   search. Its main job is to answer "who was working on X".

   Search runs over a flat list of *records*: tasks, and each agent's status
   lines ("working on X"). Status lines only show while searching or filtering
   by agent, and never under a status chip, so the plain view stays a list of
   tasks. Another source is one more `xxxRecords()` builder returning the same
   shape, plus a tile renderer for its `kind`. A record is:

     { key, kind, id?, status?, ts, agents: [user_id], fields: { name: text }, src }

   - `fields` is what the search matches, and what tiles highlight.
   - `agents` feeds the "who worked on this" line and the agent filter.
   - `id` is matched exactly by a query token like "#42" or "42".
   - `status` is matched by the status chips (records without one always pass).
*/

export const HISTORY_ROUTE = "#/tasks";

const STATUSES = [
  ["", "all"],
  ["open", "open"],
  ["picked_up", "picked up"],
  ["done", "done"],
];

// Search state lives in the hash so a view can be bookmarked or shared:
//   #/tasks?q=hive+canvas&status=done&agent=fennec&sort=oldest
export function historyHash({ q = "", status = "", agent = "", sort = "newest" } = {}) {
  const p = new URLSearchParams();
  if (q) p.set("q", q);
  if (status) p.set("status", status);
  if (agent) p.set("agent", agent);
  if (sort === "oldest") p.set("sort", "oldest");
  const s = p.toString();
  return s ? `${HISTORY_ROUTE}?${s}` : HISTORY_ROUTE;
}

function parseHash(hash) {
  const i = hash.indexOf("?");
  const p = new URLSearchParams(i < 0 ? "" : hash.slice(i + 1));
  return {
    q: p.get("q") || "",
    status: p.get("status") || "",
    agent: p.get("agent") || "",
    sort: p.get("sort") === "oldest" ? "oldest" : "newest",
  };
}

function taskRecords(tasks, teams) {
  const teamName = new Map((teams || []).map(t => [t.id, t.name]));
  return tasks.map(t => ({
    key: `task:${t.id}`,
    kind: "task",
    id: t.id,
    status: t.status,
    ts: t.created_at,
    agents: t.assignee ? [t.assignee] : [],
    fields: {
      title: t.title || "",
      description: t.description || "",
      note: t.note || "",
      assignee: t.assignee || "",
      worktree: t.worktree || "",
      team: teamName.get(t.team_id) || "",
    },
    src: t,
  }));
}

function statusRecords(recipients) {
  return (recipients || []).flatMap(r => (r.summaries || []).map((s, i) => ({
    key: `status:${r.user_id}:${s.ts}:${i}`,
    kind: "status",
    ts: s.ts,
    agents: [r.user_id],
    fields: { status: s.text, agent: r.user_id },
    src: { ...s, user_id: r.user_id, current: i === 0 },
  })));
}

const tokenize = (q) => q.toLowerCase().split(/\s+/).filter(Boolean);

// Every token must match somewhere in the record (AND). "#42" matches only
// task 42; a bare "42" matches task 42 or the text "42" anywhere.
function matches(rec, tokens) {
  return tokens.every(tok => {
    const idTok = /^#(\d+)$/.exec(tok);
    if (idTok) return rec.id === Number(idTok[1]);
    if (/^\d+$/.test(tok) && rec.id === Number(tok)) return true;
    return Object.values(rec.fields).some(v => v.toLowerCase().includes(tok));
  });
}

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function markRe(tokens) {
  const words = tokens.filter(t => !/^#\d+$/.test(t));
  return words.length ? new RegExp(`(${words.map(escapeRe).join("|")})`, "gi") : null;
}

// Wrap each match in <mark>. `re` has one capture group, so split() puts the
// matches at the odd indexes.
function hl(text, re) {
  if (!re || !text) return text;
  return text.split(re).map((part, i) => (i % 2 ? html`<mark>${part}</mark>` : part));
}

// Long text shows a window around the first match, so a hit deep inside a
// long note is still visible without expanding it.
const CLIP = 220;
function excerpt(text, re) {
  if (text.length <= CLIP) return text;
  let start = 0;
  if (re) {
    re.lastIndex = 0;
    const m = re.exec(text);
    re.lastIndex = 0;
    if (m && m.index > CLIP - 60) start = Math.max(0, m.index - 70);
  }
  const end = Math.min(text.length, start + CLIP);
  return `${start > 0 ? "…" : ""}${text.slice(start, end).trimEnd()}${end < text.length ? "…" : ""}`;
}

const fmtDate = (ts) => new Date(ts * 1000).toLocaleString([], {
  month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
});

function Clipped({ label, text, re }) {
  const [open, setOpen] = useState(false);
  if (!text) return null;
  const long = text.length > CLIP;
  return html`<div class="h-field">
    ${label && html`<span class="h-label">${label}</span>`}
    <span class="h-text">${hl(open || !long ? text : excerpt(text, re), re)}</span>
    ${long && html` <button type="button" class="h-more" onClick=${() => setOpen(!open)}>${open ? "less" : "more"}</button>`}
  </div>`;
}

function TaskEdit({ task, refresh, done }) {
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async (e) => {
    e.preventDefault();
    setBusy(true); setError("");
    const result = await patchTask(task.id, { title, description });
    setBusy(false);
    if (!result.ok) { setError(result.error); return; }
    done();
    await refresh();
  };
  return html`<form class="h-edit" onSubmit=${save}>
    <label>Title <input value=${title} required autofocus onInput=${e => setTitle(e.target.value)} /></label>
    <label>Description <textarea rows="5" value=${description}
      onInput=${e => setDescription(e.target.value)}></textarea></label>
    <div class="h-edit-actions">
      <button type="submit" class="mini" disabled=${busy || !title.trim()}>${busy ? "Saving…" : "Save"}</button>
      <button type="button" class="mini" disabled=${busy} onClick=${done}>Cancel</button>
      ${error && html`<span class="task-action-error" role="alert">${error}</span>`}
    </div>
  </form>`;
}

function TaskTile({ rec, re, now, filterAgent, refresh }) {
  const t = rec.src;
  const f = rec.fields;
  const [editing, setEditing] = useState(false);
  if (editing) {
    return html`<article class=${`htile ${t.status}`}>
      <div class="h-title"><span class="h-id">#${t.id}</span> editing</div>
      <${TaskEdit} task=${t} refresh=${refresh} done=${() => setEditing(false)} />
    </article>`;
  }
  return html`<article class=${`htile ${t.status}`}>
    <div class="h-who">
      ${t.assignee
        ? html`<${Avatar} name=${t.assignee} size="tiny" />
          <a class="agent-link h-agent" href=${focusHash(t.assignee)}
            title=${`Open ${t.assignee} and message it`}>${hl(t.assignee, re)}</a>
          <button type="button" class="h-only" onClick=${() => filterAgent(t.assignee)}
            title=${`Show only ${t.assignee}'s tasks`} aria-label=${`Show only ${t.assignee}'s tasks`}>⌕</button>`
        : html`<span class="h-noagent">unassigned</span>`}
      <span class=${`pill ${t.status}`}>${t.status.replace("_", " ")}</span>
    </div>
    <div class="h-title"><span class="h-id">#${t.id}</span> ${hl(f.title, re)}</div>
    <${Clipped} text=${f.description} re=${re} />
    <${AttachmentList} files=${t.attachments} />
    <${Clipped} label="how to verify" text=${f.note} re=${re} />
    <div class="h-meta">
      <span title=${fmtDate(t.created_at)}>created ${fmtDate(t.created_at)}</span>
      ${t.status === "done"
        ? html`<span title=${`last updated ${fmtDate(t.updated_at)}`}>closed ${fmtDate(t.updated_at)} · ${rel(t.updated_at, now)}</span>`
        : html`<span>updated ${rel(t.updated_at, now)}</span>`}
      ${f.team && html`<span>team ${hl(f.team, re)}</span>`}
      ${f.worktree && html`<span class="h-wt" title=${f.worktree}>${hl(f.worktree, re)}</span>`}
    </div>
    <div class="h-actions">
      <button type="button" class="mini" onClick=${() => setEditing(true)}
        aria-label=${`Edit task #${t.id}`}>Edit</button>
      <${TaskStatusActions} task=${t} refresh=${refresh} />
      <${TaskTrash} task=${t} refresh=${refresh} />
    </div>
  </article>`;
}

function StatusTile({ rec, re, now, filterAgent }) {
  const s = rec.src;
  return html`<article class="htile status-line">
    <div class="h-who">
      <${Avatar} name=${s.user_id} size="tiny" />
      <a class="agent-link h-agent" href=${focusHash(s.user_id)}
        title=${`Open ${s.user_id} and message it`}>${hl(s.user_id, re)}</a>
      <button type="button" class="h-only" onClick=${() => filterAgent(s.user_id)}
        title=${`Show only ${s.user_id}`} aria-label=${`Show only ${s.user_id}`}>⌕</button>
      <span class="pill statusline">${s.current ? "status now" : "status"}</span>
    </div>
    <div class="h-title">${hl(s.text, re)}</div>
    <div class="h-meta">
      <span title=${fmtDate(s.ts)}>${fmtDate(s.ts)} · ${rel(s.ts, now)}</span>
      <span>${SUMMARY_SOURCE[s.source] || s.source}</span>
    </div>
  </article>`;
}

const TILE = { task: TaskTile, status: StatusTile };

export function HistoryView({ state, refresh }) {
  const [s, setS] = useState(() => parseHash(location.hash));
  const inputRef = useRef(null);

  // Follow real navigation (links, back button, a pasted URL).
  useEffect(() => {
    const onHash = () => { if (location.hash.startsWith(HISTORY_ROUTE)) setS(parseHash(location.hash)); };
    const onKey = (e) => {
      if (e.key === "/" && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    addEventListener("hashchange", onHash);
    addEventListener("keydown", onKey);
    return () => { removeEventListener("hashchange", onHash); removeEventListener("keydown", onKey); };
  }, []);

  // Typing rewrites the hash in place: no history entry per keystroke, and
  // no hashchange event, so the input keeps focus.
  const update = (patch) => {
    const next = { ...s, ...patch };
    setS(next);
    history.replaceState(null, "", historyHash(next));
  };
  const filterAgent = (a) => update({ agent: s.agent === a ? "" : a });

  const tasks = useMemo(
    () => taskRecords(state.tasks, state.teams),
    [state.tasks, state.teams],
  );
  const lines = useMemo(() => statusRecords(state.recipients), [state.recipients]);
  const tokens = tokenize(s.q);
  const re = markRe(tokens);
  const withLines = (tokens.length || s.agent) && !s.status;
  const records = withLines ? tasks.concat(lines) : tasks;
  const textHits = tokens.length ? records.filter(r => matches(r, tokens)) : records;
  const inStatus = (r) => !s.status || r.status === s.status;
  const hasAgent = (r) => !s.agent || r.agents.includes(s.agent);

  // Each count ignores its own filter, so every chip shows what clicking it gives.
  const statusCount = {};
  for (const r of textHits) {
    if (!hasAgent(r)) continue;
    statusCount[""] = (statusCount[""] || 0) + 1;
    if (r.status) statusCount[r.status] = (statusCount[r.status] || 0) + 1;
  }
  const agentCount = new Map();
  for (const r of textHits) {
    if (!inStatus(r)) continue;
    for (const a of r.agents) agentCount.set(a, (agentCount.get(a) || 0) + 1);
  }
  const agents = agentChips(agentCount, state.recipients, s.agent);

  const shown = textHits
    .filter(r => inStatus(r) && hasAgent(r))
    .sort((a, b) => (s.sort === "oldest" ? a.ts - b.ts : b.ts - a.ts));

  return html`<div class="history">
    <h2>task history <span class="count">· ${shown.length} of ${tasks.length} tasks${withLines ? ` + ${lines.length} status lines` : ""}</span></h2>
    <div class="h-controls">
      <input ref=${inputRef} type="text" class="h-search" value=${s.q} autofocus
        placeholder="search tasks, notes, status lines, agent, worktree, #id…  ( / to focus )"
        aria-label="Search all tasks"
        onInput=${e => update({ q: e.target.value })}
        onKeyDown=${e => { if (e.key === "Escape" && s.q) { e.stopPropagation(); update({ q: "" }); } }} />
      <div class="h-chips" role="group" aria-label="Filter by status">
        ${STATUSES.map(([v, label]) => html`<button type="button" key=${v}
          class=${`h-chip ${s.status === v ? "on" : ""}`} aria-pressed=${s.status === v}
          onClick=${() => update({ status: v })}>${label} <span class="n">${statusCount[v] || 0}</span></button>`)}
      </div>
      <button type="button" class="mini h-sort" onClick=${() => update({ sort: s.sort === "oldest" ? "newest" : "oldest" })}
        title="Flip the order (by creation time)">${s.sort === "oldest" ? "oldest first ↑" : "newest first ↓"}</button>
    </div>
    <div class="h-agents">
      <span class="h-label">${tokens.length ? "who worked on this" : "by agent"}</span>
      ${agents.length === 0
        ? html`<span class="h-noagent">nobody</span>`
        : agents.map(([a, n]) => html`<button type="button" key=${a}
            class=${`h-agentchip ${s.agent === a ? "on" : ""}`} aria-pressed=${s.agent === a}
            style=${`--hue: hsl(${hue(a)} 42% 58%)`}
            title=${s.agent === a ? "Clear the agent filter" : `Show only ${a}'s tasks`}
            onClick=${() => filterAgent(a)}>${a} <span class="n">${n}</span></button>`)}
      ${(s.q || s.status || s.agent) && html`<button type="button" class="mini" onClick=${() => update({ q: "", status: "", agent: "" })}>clear filters</button>`}
    </div>
    ${shown.length === 0
      ? html`<div class="empty">No tasks match${s.q ? html` "<b>${s.q}</b>"` : ""}.</div>`
      : html`<div class="h-grid">
          ${shown.map(r => {
            const Tile = TILE[r.kind];
            return html`<${Tile} key=${r.key} rec=${r} re=${re} now=${state.now} filterAgent=${filterAgent} refresh=${refresh} />`;
          })}
        </div>`}
  </div>`;
}
