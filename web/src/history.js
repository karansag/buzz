import { AttachmentList } from "./attachments.js";
import { html } from "htm/preact";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import { Avatar, SUMMARY_SOURCE, focusHash, hue, patchTask, rel, retiredLabel } from "./shared.js";
import { agentChips } from "./agent-chips.js";
import { TaskStatusActions } from "./task-status.js";
import { TaskTrash } from "./task-trash.js";
import { Crown } from "./queen.js";
import { readStored, writeStored } from "./storage.js";
import { hl, searchWords, wordsRe } from "./highlight.js";

/* The history view: every task as a tile, newest first, with a live text
   search. Its main job is to answer "who was working on X".

   Search runs over a flat list of *records*: tasks, and each agent's status
   lines ("working on X"). Status lines are off by default; the "status lines"
   chip turns them on, and they then show only while searching or filtering by
   agent, never under a status chip, so the plain view stays a list of tasks. Another source is one more `xxxRecords()` builder returning the same
   shape, plus a tile renderer for its `kind`. A record is:

     { key, kind, id?, status?, ts, agents: [user_id], fields: { name: text }, src }

   - `fields` is what the search matches, and what tiles highlight.
   - `agents` feeds the "who worked on this" line and the agent filter.
   - `id` is matched exactly by a query token like "#42" or "42".
   - `status` is matched by the status chips (records without one always pass).
*/

export const HISTORY_ROUTE = "#/tasks";

// The "status lines" chip is a per-viewer choice, so it lives in localStorage
// (the hash holds the shareable search). Storage can be blocked: off then.
const LINES_KEY = "agent-swarm.history.statusLines";
const readLines = () => readStored(LINES_KEY) === "1";
const saveLines = (on) => writeStored(LINES_KEY, on ? "1" : "0");

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
    src: { ...s, user_id: r.user_id, current: !r.archive_id && i === 0 },
  })));
}

// A whole query that is one task number, "310" or "#310", picks that task on
// its own: nobody types an id to read the tasks that mention it. A number that
// names no task is still text, so "310" finds notes about something else when
// there is no task 310. Several words keep the AND below instead.
function taskNumber(tokens, tasks) {
  if (tokens.length !== 1) return null;
  const m = /^#?(\d+)$/.exec(tokens[0]);
  return m ? tasks.find(t => String(t.id) === m[1]) || null : null;
}

// Every token must match somewhere in the record (AND). "#42" matches only
// task 42; a bare "42" matches task 42 or the text "42" anywhere, unless the
// whole query is that number and task 42 exists (see taskNumber).
function matches(rec, tokens) {
  return tokens.every(tok => {
    const idTok = /^#(\d+)$/.exec(tok);
    if (idTok) return rec.id === Number(idTok[1]);
    if (/^\d+$/.test(tok) && rec.id === Number(tok)) return true;
    return Object.values(rec.fields).some(v => v.toLowerCase().includes(tok));
  });
}

// "#42" picks a task by number, so it is not highlighted as text.
const markRe = (tokens) => wordsRe(tokens.filter(t => !/^#\d+$/.test(t)));

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

function TaskMeta({ task: t, fields: f, re, now }) {
  return html`<div class="h-meta">
      <span title=${fmtDate(t.created_at)}>created ${fmtDate(t.created_at)}</span>
      ${t.status === "done"
        ? html`<span title=${`last updated ${fmtDate(t.updated_at)}`}>closed ${fmtDate(t.updated_at)} · ${rel(t.updated_at, now)}</span>`
        : html`<span>updated ${rel(t.updated_at, now)}</span>`}
      ${f.team && html`<span>team ${hl(f.team, re)}</span>`}
      ${f.worktree && html`<span class="h-wt" title=${f.worktree}>${hl(f.worktree, re)}</span>`}
    </div>`;
}

function TaskDetails({ task: t, fields: f, re, now, close, agentLabel }) {
  const ref = useRef(null);
  useEffect(() => { ref.current.showModal(); }, []);

  return html`<dialog class="page-dialog task-details" ref=${ref} aria-labelledby=${`task-details-title-${t.id}`}
      onClose=${close} onKeyDown=${e => { if (e.key === "Escape") e.stopPropagation(); }}>
    <header class="task-details-header">
      <span>Task #${t.id}</span>
      <button type="button" class="mini" autofocus onClick=${() => ref.current.close()}>Close</button>
    </header>
    <div class="task-details-body" tabindex="0">
      <h2 id=${`task-details-title-${t.id}`}>${hl(f.title, re)}</h2>
      <div class="task-details-status">
        ${t.assignee && html`<a class="agent-link" href=${focusHash(t.assignee)}>${hl(agentLabel(t.assignee), re)}</a>`}
        <span class=${`pill ${t.status}`}>${t.status.replace("_", " ")}</span>
      </div>
      ${f.description && html`<div class="task-details-text">${hl(f.description, re)}</div>`}
      <${AttachmentList} files=${t.attachments} />
      ${f.note && html`<section>
        <h3>How to verify</h3>
        <div class="task-details-text">${hl(f.note, re)}</div>
      </section>`}
      <${TaskMeta} task=${t} fields=${f} re=${re} now=${now} />
    </div>
  </dialog>`;
}

function TaskTile({ rec, re, now, teams, filterAgent, refresh, agentLabel }) {
  const t = rec.src;
  const f = rec.fields;
  const [editing, setEditing] = useState(false);
  const [expanded, setExpanded] = useState(false);
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
            title=${`Open ${agentLabel(t.assignee)}`}>${hl(agentLabel(t.assignee), re)}</a><${Crown} teams=${teams} user=${t.assignee} />
          <button type="button" class="h-only" onClick=${() => filterAgent(t.assignee)}
            title=${`Show only ${t.assignee}'s tasks`} aria-label=${`Show only ${t.assignee}'s tasks`}>⌕</button>`
        : html`<span class="h-noagent">unassigned</span>`}
      <span class=${`pill ${t.status}`}>${t.status.replace("_", " ")}</span>
    </div>
    <div class="h-title"><span class="h-id">#${t.id}</span> ${hl(f.title, re)}</div>
    <${Clipped} text=${f.description} re=${re} />
    <${AttachmentList} files=${t.attachments} />
    <${Clipped} label="how to verify" text=${f.note} re=${re} />
    <${TaskMeta} task=${t} fields=${f} re=${re} now=${now} />
    <div class="h-actions">
      <button type="button" class="mini" aria-haspopup="dialog" aria-label=${`Expand task #${t.id}`}
        onClick=${e => { e.currentTarget.focus(); setExpanded(true); }}>Expand</button>
      <button type="button" class="mini" onClick=${() => setEditing(true)}
        aria-label=${`Edit task #${t.id}`}>Edit</button>
      <${TaskStatusActions} task=${t} refresh=${refresh} />
      <${TaskTrash} task=${t} refresh=${refresh} />
    </div>
    ${expanded && html`<${TaskDetails} task=${t} fields=${f} re=${re} now=${now} agentLabel=${agentLabel} close=${() => setExpanded(false)} />`}
  </article>`;
}

function StatusTile({ rec, re, now, teams, filterAgent, agentLabel }) {
  const s = rec.src;
  return html`<article class="htile status-line">
    <div class="h-who">
      <${Avatar} name=${s.user_id} size="tiny" />
      <a class="agent-link h-agent" href=${focusHash(s.user_id)}
        title=${`Open ${agentLabel(s.user_id)}`}>${hl(agentLabel(s.user_id), re)}</a><${Crown} teams=${teams} user=${s.user_id} />
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
  const [showLines, setShowLines] = useState(readLines);
  const inputRef = useRef(null);

  // Follow real navigation (links, back button, a pasted URL).
  useEffect(() => {
    const onHash = () => { if (location.hash.startsWith(HISTORY_ROUTE)) setS(parseHash(location.hash)); };
    const onKey = (e) => {
      if (e.key === "/" && !document.querySelector("dialog[open]")
          && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) {
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
  const archives = new Map((state.retired_agents || []).map(r => [r.archive_id, retiredLabel(r)]));
  const agentLabel = (id) => archives.get(id) || id;
  const lines = useMemo(() => statusRecords([
    ...state.recipients,
    ...(state.retired_agents || []).map(r => ({ ...r, user_id: r.archive_id })),
  ]), [state.recipients, state.retired_agents]);
  const tokens = searchWords(s.q);
  const re = markRe(tokens);
  const picked = taskNumber(tokens, tasks);
  // Lines can appear only while searching or filtering by agent, and never under a status chip.
  const linesPossible = !picked && !!(tokens.length || s.agent) && !s.status;
  const withLines = linesPossible && showLines;
  const records = picked ? [picked] : withLines ? tasks.concat(lines) : tasks;
  const textHits = !tokens.length || picked ? records : records.filter(r => matches(r, tokens));
  const inStatus = (r) => !s.status || r.status === s.status;
  const hasAgent = (r) => !s.agent || r.agents.includes(s.agent);
  // What the chip would add: the lines matching the search and agent filter.
  const lineCount = linesPossible
    ? lines.filter(r => (!tokens.length || matches(r, tokens)) && hasAgent(r)).length : 0;

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
      ${linesPossible && html`<button type="button" class=${`h-chip h-lines ${showLines ? "on" : ""}`} aria-pressed=${showLines}
        title=${showLines ? "Hide agents' status lines" : "Also search agents' status lines"}
        onClick=${() => { saveLines(!showLines); setShowLines(!showLines); }}>status lines <span class="n">${lineCount}</span></button>`}
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
            onClick=${() => filterAgent(a)}>${agentLabel(a)}<${Crown} teams=${state.teams} user=${a} /> <span class="n">${n}</span></button>`)}
      ${(s.q || s.status || s.agent) && html`<button type="button" class="mini" onClick=${() => update({ q: "", status: "", agent: "" })}>clear filters</button>`}
    </div>
    ${shown.length === 0
      ? html`<div class="empty">No tasks match${s.q ? html` "<b>${s.q}</b>"` : ""}.</div>`
      : html`<div class="h-grid">
          ${shown.map(r => {
            const Tile = TILE[r.kind];
            return html`<${Tile} key=${r.key} rec=${r} re=${re} now=${state.now} teams=${state.teams}
              filterAgent=${filterAgent} refresh=${refresh} agentLabel=${agentLabel} />`;
          })}
        </div>`}
  </div>`;
}
