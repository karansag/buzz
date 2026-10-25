import { QuickSwitcher } from "./quick-switch.js";
import { useAgentHistory } from "./agent-history.js";
import { TaskTrash } from "./task-trash.js";
import { TaskStatusActions } from "./task-status.js";
import { html, render } from "htm/preact";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";

import {
  POLL_MS,
  PEEK_MS,
  JSONH,
  FLAVOR_ICON,
  STATE,
  agentStatus,
  Avatar,
  Bee,
  MachineBadge,
  rel,
  currentTask,
  SUMMARY_SOURCE,
  pairKey,
  disp,
  focusHash,
  patchTask,
  agentShown,
  harnessStyle,
  HarnessFilter,
} from "./shared.js";
import { deliveryOutcome, draftClientId, spawnOutcome, spawnTarget, unansweredOutcome } from "./outcome.js";
import { machineColor, machineList, machineName } from "./machines.js";
import { COMPACT_LAYOUT, useMedia } from "./use-media.js";
import { CompactBees, HiveView } from "./hive.js";
import { TabView } from "./tabs.js";
import { TAB_ROUTE, stepView, tabHash } from "./views.js";
import { HistoryView, HISTORY_ROUTE, historyHash } from "./history.js";
import { AttachmentLink, AttachmentList, AttachmentPicker, useAttachments } from "./attachments.js";
import { createBottomFollower } from "./scroll-follow.js";
import { attentionReporter } from "./native.js";
import { renderMarkdown } from "./markdown.js";
import "../styles.css";
import { stepTeammate, teammates } from "./teammates.js";
import { shellNewlines } from "./newlines.js";
import { ownerChats } from "./chats.js";

/* ---------- agent controls ---------- */

// The tmux command that takes you to an agent's pane, typed at tmux's command
// prompt (prefix, then ":"). It uses the pane id, which stays valid however
// windows and panes are renumbered.
function JumpToPane({ r }) {
  const [copied, setCopied] = useState(false);
  const paneExists = r.pane_alive || (r.offline_reason || "").includes("bare shell");
  if (!paneExists || !String(r.tmux_pane).startsWith("%")) return null;
  const command = `switch-client -t ${r.tmux_pane}`;
  const copy = async (e) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      prompt("Copy this, then paste it at tmux's command prompt (prefix, then :)", command);
    }
  };
  const title = `Copy "${command}" — paste it at tmux's command prompt (prefix, then :) to jump to ${r.pane_label}`;
  return html`<span class="jump-cmd" title=${title}>
    <span class="sep">· </span><code>${command}</code>
    <button type="button" class="mini" onClick=${copy}>${copied ? "copied" : "copy"}</button>
  </span>`;
}

// Types the harness's own compact command (e.g. /compact) into the agent's
// pane. The server picks the command by flavor; null means none is known.
function CompactButton({ r }) {
  const [busy, setBusy] = useState(false);
  if (!r.pane_alive || !r.compact_command) return null;
  const compact = async () => {
    if (!confirm(`Compact ${r.user_id}'s context? This types ${r.compact_command} into its pane.`)) return;
    setBusy(true);
    const res = await typeInto(r.user_id, { text: r.compact_command });
    setBusy(false);
    if (!res.ok) alert(`Could not compact ${r.user_id}: ${await failure(res)}`);
  };
  return html`<button type="button" class="mini" disabled=${busy}
    title=${`Type ${r.compact_command} into ${r.user_id}'s pane to compact its context`}
    onClick=${compact}>${busy ? "compacting…" : "compact"}</button>`;
}

// Stopping kills the agent's tmux pane. If its page is open, go to another
// running agent's page, or the overview if none are left.
async function stopAgent(r, state, focusUser, refresh) {
  if (!confirm(`Stop ${r.user_id} on ${machineName(r.node)}? This kills its tmux pane and ends the running session. Messages and tasks are kept.`)) return;
  const res = await fetch(`/agents/${encodeURIComponent(r.user_id)}/stop`, { method: "POST" }).catch(() => null);
  if (res?.ok) {
    if (focusUser === r.user_id) {
      const next = state.recipients.find(x => x.pane_alive && x.user_id !== r.user_id);
      location.hash = next ? focusHash(next.user_id) : "#/";
    }
  } else alert(`Could not stop ${r.user_id}. Check its status before trying again.`);
  refresh();
}

// Retiring forgets agents that are not running: their registration, team
// membership, and status lines. Messages and tasks stay. The hub refuses
// any that are running. Returns the hub's answer, or null if not confirmed.
async function retireAgents(ids, refresh) {
  const names = ids.length > 6 ? `${ids.slice(0, 6).join(", ")} and ${ids.length - 6} more` : ids.join(", ");
  if (!ids.length || !confirm(`Retire ${names}? ${ids.length > 1 ? "They leave" : "It leaves"} the dashboard and ${ids.length > 1 ? "their teams" : "its team"}. Messages and tasks are kept.`)) return null;
  try {
    const response = await fetch("/recipients/retire", { method: "POST", headers: JSONH, body: JSON.stringify({ user_ids: ids }) });
    const body = await response.json().catch(() => null);
    if (!response.ok || !body?.ok) { alert("Could not retire. Try again."); return null; }
    if (body.kept_live.length) alert(`Still running, so not retired: ${body.kept_live.join(", ")}`);
    return body;
  } catch { alert("Could not retire. Try again."); return null; }
  finally { refresh(); }
}

function RetireButton({ ids, refresh, label, onDone = () => {} }) {
  const [busy, setBusy] = useState(false);
  return html`<button type="button" class="mini retire" disabled=${busy || !ids.length} onClick=${async e => {
    e.preventDefault(); e.stopPropagation();
    setBusy(true);
    const body = await retireAgents(ids, refresh);
    setBusy(false);
    if (body?.retired.length) onDone(body);
  }}>${busy ? "retiring…" : label}</button>`;
}

function StopAgentButton({ r, refresh }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const stop = async () => {
    if (busy || !confirm(`Stop ${r.user_id} on ${machineName(r.node)}? This kills its tmux pane and ends the running session. Messages and tasks are kept.`)) return;
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch(`/agents/${encodeURIComponent(r.user_id)}/stop`, { method: "POST" });
      const body = await response.json().catch(() => null);
      if (response.ok && body?.ok === true) {
        setMessage(body.already_stopped ? "Already stopped." : "Agent stopped. Messages and tasks are kept.");
      } else if (body?.detail?.status === "unknown" || !body?.detail?.error) {
        setMessage("Stop not confirmed. Check the agent's status before retrying.");
      } else {
        setMessage(`Could not stop agent: ${body.detail.error}${body.detail.detail ? ` — ${body.detail.detail}` : ""}`);
      }
    } catch {
      setMessage("Stop not confirmed. Check the agent's status before retrying.");
    } finally {
      setBusy(false);
      refresh();
    }
  };
  return html`<span class="agent-stop-control">
    ${r.pane_alive
      ? html`<button type="button" class="mini stop-agent" disabled=${busy} onClick=${stop}>
          ${busy ? "stopping…" : "stop agent"}</button>`
      : html`<${RetireButton} ids=${[r.user_id]} refresh=${refresh} label="retire agent" onDone=${() => { location.hash = "#/"; }} />`}
    ${message && html`<span role="status"> ${message}</span>`}
  </span>`;
}

// "claude-opus-4-7" reads as "opus-4-7" next to the claude flavor tag.
function shortModel(model, flavor) {
  const prefix = `${flavor}-`;
  return model.toLowerCase().startsWith(prefix) ? model.slice(prefix.length) : model;
}

// The model label is display-only: it records what the agent is running so
// the roster can show it. Switching models still happens in the agent's own
// pane (e.g. /model); this just keeps the dashboard in step.
function ModelLabel({ r, refresh }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [known, setKnown] = useState([]);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);
  useEffect(() => { if (editing) inputRef.current?.focus(); }, [editing]);
  const flavor = (r.flavor || "generic").toLowerCase();
  const listId = `models-${r.user_id}`;
  const start = () => {
    setValue(r.model || "");
    setEditing(true);
    fetch("/api/spawn-options")
      .then(res => res.json())
      .then(d => setKnown(((d.harnesses || []).find(h => h.flavor === flavor) || {}).models || []))
      .catch(() => {});
  };
  const save = async () => {
    if (busy) return;
    if (value.trim() === (r.model || "")) { setEditing(false); return; }
    setBusy(true);
    const res = await fetch(`/agents/${encodeURIComponent(r.user_id)}/model`, {
      method: "POST", headers: JSONH, body: JSON.stringify({ model: value }),
    });
    setBusy(false);
    if (!res.ok) { alert(`Could not update the model label for ${r.user_id}.`); return; }
    setEditing(false);
    refresh();
  };
  if (!editing) {
    return html`<button type="button" class="model-label" onClick=${start}
      title="Edit the model label. Display only: switch the real model in the agent's pane, then update it here.">
      ${r.model ? html`<b>${r.model}</b>` : html`<span class="unset">set model</span>`} <span class="pen">✎</span>
    </button>`;
  }
  return html`<span class="model-edit">
    <input type="text" value=${value} list=${listId} placeholder="e.g. claude-opus-4-7"
      aria-label=${`Model label for ${r.user_id}`} disabled=${busy} ref=${inputRef}
      onInput=${e => setValue(e.target.value)}
      onKeyDown=${e => {
        if (e.key === "Enter") { e.preventDefault(); save(); }
        if (e.key === "Escape") setEditing(false);
      }} />
    <datalist id=${listId}>${known.map(m => html`<option key=${m} value=${m} />`)}</datalist>
    <button type="button" class="mini" disabled=${busy} onClick=${save}>${busy ? "saving…" : "save"}</button>
    <button type="button" class="mini" disabled=${busy} onClick=${() => setEditing(false)}>cancel</button>
  </span>`;
}

const DEFAULT_MODEL = "default";

function SpawnControl({ refresh, nodes }) {
  const [harnesses, setHarnesses] = useState([]);
  const [node, setNode] = useState("");
  const [flavor, setFlavor] = useState("claude");
  const [model, setModel] = useState(DEFAULT_MODEL);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    let live = true;
    fetch("/api/spawn-options")
      .then(r => r.json())
      .then(d => { if (live && d.harnesses) setHarnesses(d.harnesses); })
      .catch(() => {});
    return () => { live = false; };
  }, []);

  // Where this spawn would go. A picked machine that has gone away or
  // disconnected stays picked and blocks the form; it is never swapped for
  // the hub behind the user's back.
  const target = spawnTarget(nodes, node, harnesses);
  const offered = target.harnesses || [];
  const models = (offered.find(h => h.flavor === flavor) || {}).models || [];
  const pickFlavor = (f) => { setFlavor(f); setModel(DEFAULT_MODEL); };
  const pickNode = (n) => {
    setNode(n);
    const next = spawnTarget(nodes, n, harnesses);
    if (next.ok && next.harnesses.length && !next.harnesses.some(h => h.flavor === flavor)) pickFlavor(next.harnesses[0].flavor);
  };
  const enrolled = nodes || [];
  const choices = enrolled.some(n => n.name === node) || !node
    ? enrolled : enrolled.concat([{ name: node, connected: false, gone: true }]);

  const spawn = async (e) => {
    e.preventDefault();
    if (!target.ok) { setErr(target.reason); return; }
    setBusy(true);
    setErr("");
    const body = { flavor, model: model === DEFAULT_MODEL ? null : model };
    if (target.remote) body.node = target.node;
    try {
      const r = await fetch("/agents/spawn", {
        method: "POST", headers: JSONH, body: JSON.stringify(body),
      });
      let payload = null;
      try { payload = await r.json(); } catch { payload = null; }
      const outcome = spawnOutcome(r.ok, payload);
      if (outcome.status === "failed") setErr(`spawn failed: ${outcome.reason}`);
      else if (outcome.status === "unknown") setErr(`spawn outcome unknown: ${outcome.reason}${outcome.user ? ` (registered as ${outcome.user})` : ""}`);
      else if (outcome.status === "uncertain") setErr(`spawn not confirmed: ${outcome.reason}; check the agents list`);
    } catch (err) {
      setErr(`not confirmed: ${unansweredOutcome(err).reason}`);
    } finally {
      setBusy(false);
      refresh();
    }
  };

  const flavors = offered.length ? offered.map(h => h.flavor) : [];
  return html`<form class="spawn" onSubmit=${spawn}>
    <div class="spawn-heading">Spawn agent · choose destination</div>
    ${(enrolled.length > 1 || node) && html`<select title="machine" value=${node} onChange=${e => pickNode(e.target.value)}>
      ${choices.map(n => html`<option key=${n.name} value=${n.local ? "" : n.name} disabled=${!n.local && !n.connected}>${n.local ? `${n.name} (hub)` : n.gone ? `${n.name} (no longer enrolled)` : n.connected ? n.name : `${n.name} (not connected)`}</option>`)}
    </select>`}
    ${!target.ok && html`<span class="spawn-note">${target.reason}. Pick a connected machine.</span>`}
    <select title="harness" value=${flavor} onChange=${e => pickFlavor(e.target.value)} disabled=${!target.ok}>
      ${flavors.map(f => html`<option key=${f} value=${f}>${f}</option>`)}
    </select>
    <select title="model" value=${model} onChange=${e => setModel(e.target.value)}
      disabled=${models.length === 0}>
      <option value=${DEFAULT_MODEL}>default model</option>
      ${models.map(m => html`<option key=${m} value=${m}>${m}</option>`)}
    </select>
    <button class="act" type="submit" disabled=${busy || !target.ok}>${busy ? "spawning…" : "spawn agent"}</button>
    ${err && html`<span style="color:var(--alert); font-size:11px">${err}</span>`}
  </form>`;
}

const ACTIVITY_RANK = { working: 0, needs_attention: 1, idle: 2, unknown: 3 };
const AGENT_DRAG_TYPE = "application/x-agent-swarm-agent";

function sortByActivity(agents) {
  return agents
    .map((r, i) => [r, i])
    .sort(([a, ai], [b, bi]) =>
      (ACTIVITY_RANK[agentStatus(a)] ?? 3) - (ACTIVITY_RANK[agentStatus(b)] ?? 3) || ai - bi)
    .map(([r]) => r);
}

async function moveAgentToTeam(user, teamId, refresh) {
  await fetch(`/agents/${encodeURIComponent(user)}/team`, {
    method: "POST", headers: JSONH, body: JSON.stringify({ team_id: teamId }),
  });
  refresh();
}

function agentDropProps(setOver, onDropUser) {
  return {
    onDragOver: (e) => {
      if (![...e.dataTransfer.types].includes(AGENT_DRAG_TYPE)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      setOver(true);
    },
    onDragLeave: (e) => { if (!e.currentTarget.contains(e.relatedTarget)) setOver(false); },
    onDrop: (e) => {
      e.preventDefault();
      setOver(false);
      const user = e.dataTransfer.getData(AGENT_DRAG_TYPE);
      if (user) onDropUser(user);
    },
  };
}

function NewTeam({ refresh }) {
  const [name, setName] = useState("");
  const create = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    await fetch("/teams", {
      method: "POST", headers: JSONH, body: JSON.stringify({ name: name.trim() }),
    });
    setName("");
    refresh();
  };
  return html`<form class="newteam" onSubmit=${create}>
    <input type="text" placeholder="team name" value=${name}
      onInput=${e => setName(e.target.value)} />
    <button class="act" type="submit">new team</button>
  </form>`;
}

// A delivery whose outcome was lost is never replayed by the server. The
// owner can send the same text again, as a new message with its own id,
// knowing the agent may already have the first.
function Resend({ m, refresh }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const resend = async () => {
    if (!window.confirm(
      "The outcome of this message is unknown: the agent may already have it. Send it again as a new message?"
    )) return;
    setBusy(true);
    setNote("");
    try {
      const r = await fetch("/owner/send", {
        method: "POST", headers: JSONH,
        body: JSON.stringify({ recipient: m.recipient, content: m.content, context: m.context, attachments: m.attachments || [] }),
      });
      let body = null;
      try { body = await r.json(); } catch { body = null; }
      const outcome = deliveryOutcome(r.ok, body);
      if (outcome.status !== "delivered") setNote(`${outcome.status}: ${outcome.reason}`);
    } catch (err) {
      setNote(`not confirmed: ${unansweredOutcome(err).reason}`);
    } finally {
      setBusy(false);
      refresh();
    }
  };
  return html`<button type="button" class="resend" disabled=${busy} onClick=${resend}
    title="Send this message again as a new message">${busy ? "sending…" : "send again"}</button>${note && html` <span class="ctx">${note}</span>`}`;
}

// The same machine key drives the hive and roster, including disconnected
// or removed machines whose agents still have history here.
function MachineBar({ state, machine, selectMachine }) {
  const machines = machineList(state.nodes, state.recipients);
  return html`<section class="machine-bar" aria-label="Machine selector">
    <div class="machine-heading"><span>Machines</span><small>Color identifies the machine</small></div>
    <div class="machine-choices">
      <button class=${`machine-choice all ${machine === null ? "active" : ""}`} aria-pressed=${machine === null}
        onClick=${() => selectMachine(null)}><strong>All machines</strong><span>${machines.length} machines · ${state.recipients.filter(r => r.pane_alive).length} live agents</span></button>
      ${machines.map(n => html`<button key=${n.name} class=${`machine-choice ${machine === n.name ? "active" : ""} ${n.connected ? "" : "disconnected"}`}
          style=${`--machine:${machineColor(n.name)}`} aria-pressed=${machine === n.name}
          onClick=${() => selectMachine(machine === n.name ? null : n.name)}>
        <strong><span class="machine-mark" aria-hidden="true"></span>${n.name}${n.local && html`<small>hub</small>`}</strong>
        <span>${n.connected ? "Connected" : n.missing ? "Not enrolled" : "Disconnected"} · ${n.live} live${n.total > n.live ? ` / ${n.total} registered` : " agents"}</span>
      </button>`)}
    </div>
    ${machine !== null && html`<div class="machine-filter-note">Highlighting bees and showing agents on <b>${machine}</b>. Task board shows all machines. <button onClick=${() => selectMachine(null)}>Clear filter ×</button></div>`}
  </section>`;
}

/* ---------- overview mode ---------- */

function TaskCard({ t, agentIds, teams, blockers, refresh }) {
  const [dragging, setDragging] = useState(false);
  const [showNote, setShowNote] = useState(false);
  const [err, setErr] = useState("");
  const when = new Date(t.created_at * 1000)
    .toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const ids = t.assignee && !agentIds.includes(t.assignee)
    ? agentIds.concat(t.assignee) : agentIds;
  const act = async (p) => {
    const r = await patchTask(t.id, p);
    if (!r.ok) { setErr(r.error); return false; }
    setErr(""); refresh(); return true;
  };
  const draggable = t.status !== "done";
  const blocked = blockers.length > 0 && t.status !== "done";
  const deps = t.depends_on || [];
  const dragStart = (e) => {
    if (!draggable) return;
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("application/x-agent-swarm-task", String(t.id));
    e.dataTransfer.setData("text/plain", String(t.id));
    setDragging(true);
  };
  const onAssign = (e) => {
    const v = e.target.value;
    if (v.startsWith("t:")) act({ team_id: Number(v.slice(2)) });
    else if (v) act({ assignee: v });
    else act({ assignee: null, team_id: null });
  };
  return html`<div class=${`tcard ${dragging ? "dragging" : ""} ${blocked ? "blocked" : ""}`} draggable=${draggable}
      onDragStart=${dragStart} onDragEnd=${() => setDragging(false)}
      title=${draggable ? "Drag this task onto a bee or team in the activity view to assign it" : "Reopen this task before assigning it by drag"}>
    <div class="t">${t.title}</div>
    <div class="meta">#${t.id} · created ${when}${deps.length > 0 ? ` · after ${deps.map(d => `#${d}`).join(" ")}` : ""}${t.description ? ` · ${t.description}` : ""}${t.worktree ? ` · worktree ${t.worktree}` : ""}</div>
    ${blocked && html`<div class="meta blocked-tag" title="dependencies not yet done">blocked by ${blockers.map(d => `#${d}`).join(" ")}</div>`}
    <${AttachmentList} files=${t.attachments} />
    ${t.assignee && html`<div class="meta">${t.status === "open" ? "assigned to" : t.status === "done" ? "done by" : "picked up by"} <a class="agent-link" href=${focusHash(t.assignee)}
        title=${`Open ${t.assignee} and message it`}>${t.assignee}</a></div>`}
    ${t.note && html`<div class="tnote">
      <button type="button" class="tnote-toggle" onClick=${() => setShowNote(!showNote)}
        title="How to verify this work">${showNote ? "▾" : "▸"} how to verify</button>
      ${showNote && html`<div class="tnote-body">${t.note}</div>`}
    </div>`}
    ${err && html`<div class="meta tnote-err">${err}</div>`}
    <div class="foot">
      <${TaskTrash} task=${t} refresh=${refresh} />
      <select title="assignee" aria-label=${`Assign task #${t.id}`} disabled=${t.status === "done"}
        value=${t.team_id ? `t:${t.team_id}` : (t.assignee || "")}
        onChange=${onAssign}>
        <option value="">unassigned</option>
        ${teams.length > 0 && html`<optgroup label="teams">
          ${teams.map(x => html`<option key=${`t:${x.id}`} value=${`t:${x.id}`}>team ${x.name}</option>`)}
        </optgroup>`}
        ${ids.map(a => html`<option key=${a} value=${a}>${a}${agentIds.includes(a) ? "" : " (stopped)"}</option>`)}
      </select>
      <${TaskStatusActions} task=${t} refresh=${refresh} />
    </div>
  </div>`;
}

const DONE_ON_BOARD = 10;

// `folded` shows a one-line "+ create a task" that opens the form; it starts
// open when an unsent draft is waiting.
function TaskComposer({ state, refresh, user = "", folded = false }) {
  const draftKey = `agent-swarm:task-draft:${user || "board"}`;
  const [draft] = useState(() => {
    try { return JSON.parse(localStorage.getItem(draftKey) || "null") || {}; } catch { return {}; }
  });
  const [title, setTitle] = useState(draft.title || "");
  const [description, setDescription] = useState(draft.description || "");
  const [assignee, setAssignee] = useState(draft.assignee ?? user);
  const [files, setFiles] = useState(Array.isArray(draft.files) ? draft.files.filter(f => typeof f === "string") : []);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const attachments = useAttachments(files, setFiles, setStatus, draftKey);
  useEffect(() => {
    try {
      if (title || description || files.length) localStorage.setItem(draftKey, JSON.stringify({ title, description, assignee, files }));
      else localStorage.removeItem(draftKey);
    } catch { /* draft storage is best effort */ }
  }, [draftKey, title, description, assignee, files]);
  const agents = state.recipients.filter(r => r.pane_alive || r.user_id === user || r.user_id === assignee);
  const teams = state.teams || [];
  const targetExists = !assignee || (assignee.startsWith("t:")
    ? teams.some(t => `t:${t.id}` === assignee) : agents.some(r => r.user_id === assignee));
  const create = async e => {
    e.preventDefault();
    if (busy || attachments.uploading || !title.trim() || !targetExists) return;
    setBusy(true); setStatus("Creating task…");
    const body = { title: title.trim(), description: description.trim() || null, attachments: files };
    if (assignee.startsWith("t:")) body.team_id = Number(assignee.slice(2));
    else if (assignee) body.assignee = assignee;
    try {
      const response = await fetch("/tasks", { method: "POST", headers: JSONH, body: JSON.stringify(body) });
      const result = await response.json().catch(() => null);
      if (!response.ok || !result?.task?.id) {
        setStatus(result?.detail?.error ? `Task not created: ${result.detail.error}. Draft kept.` : "Creation not confirmed. Check the board before retrying; draft kept.");
        return;
      }
      setTitle(""); setDescription(""); setFiles([]);
      setStatus(`Created task #${result.task.id}${result.task.assignee ? ` · assigned to ${result.task.assignee}` : result.task.team_id ? " · assigned to team" : " · unassigned"}.`);
      await refresh();
    } catch {
      setStatus("Creation not confirmed. Check the board before retrying; draft kept.");
    } finally { setBusy(false); }
  };
  const form = html`<form class=${`task-composer ${attachments.dragging ? "dragging" : ""}`} onSubmit=${create} ...${busy ? {} : attachments.dropProps}>
    ${!folded && html`<div class="task-compose-heading">${user ? `Create a task for ${user}` : "New task"}</div>`}
    <input class="task-title" aria-label="Task title" placeholder="What needs doing?" value=${title} disabled=${busy} onInput=${e => setTitle(e.target.value)} onPaste=${attachments.onPaste} required />
    <textarea aria-label="Task details" placeholder="Details, context, or steps to reproduce… (optional) · Enter to create · Shift + Enter for a new line" rows="2" value=${description} disabled=${busy} onInput=${e => setDescription(e.target.value)} onPaste=${attachments.onPaste}
      onKeyDown=${e => { if (e.key === "Enter" && !e.shiftKey && !(e.metaKey || e.ctrlKey) && !e.isComposing) create(e); }} />
    <${AttachmentPicker} files=${files} controls=${attachments} disabled=${busy} />
    <div class="task-compose-actions"><label>Assign to <select aria-label="Task assignee" value=${assignee} disabled=${busy} onChange=${e => setAssignee(e.target.value)}>
      <option value="">Unassigned</option>
      ${!targetExists && html`<option value=${assignee} disabled>${assignee} (unavailable)</option>`}
      ${teams.length > 0 && html`<optgroup label="Teams">${teams.map(t => html`<option value=${`t:${t.id}`}>${t.name}</option>`)}</optgroup>`}
      <optgroup label="Agents">${agents.map(r => html`<option value=${r.user_id}>${r.user_id} · ${machineName(r.node)}${r.pane_alive ? "" : " (offline)"}</option>`)}</optgroup>
    </select></label><button class="act" disabled=${busy || attachments.uploading > 0 || !title.trim() || !targetExists}>${busy ? "Creating…" : "create task"}</button></div>
    ${!targetExists && html`<p class="task-compose-status">The selected assignee is unavailable. Choose another destination.</p>`}
    ${status && html`<p class="task-compose-status" role="status">${status}</p>`}
  </form>`;
  if (!folded) return form;
  return html`<details class="task-compose-fold" open=${!!(draft.title || draft.description || draft.files?.length)}>
    <summary>+ create a task${user ? ` for ${user}` : ""}</summary>
    ${form}
  </details>`;
}

function Kanban({ state, refresh }) {
  const agentIds = state.recipients.filter(r => r.pane_alive).map(r => r.user_id);
  const teams = state.teams || [];
  const byId = new Map(state.tasks.map(t => [t.id, t]));
  const cols = [
    ["open", "open"],
    ["picked_up", "picked up"],
    ["done", "done"],
  ];
  return html`<div>
    <h2>tasks ${state.tasks.length > 0 && html`<span class="count">· ${state.tasks.length}</span>`}</h2>
    <${TaskComposer} key="board" state=${state} refresh=${refresh} />
    <div class="board">
      ${cols.map(([status, label]) => {
        const all = state.tasks.filter(t => t.status === status);
        // Done keeps growing forever; the board shows only the latest few and
        // the history view holds the rest.
        const items = status === "done"
          ? [...all].sort((a, b) => b.updated_at - a.updated_at).slice(0, DONE_ON_BOARD)
          : all;
        return html`<div key=${status} class=${`col ${status}`}>
          <div class="colhead">${label}<span class="n">${all.length}</span></div>
          <div class="cards">
            ${items.length === 0
              ? html`<div class="colempty">none</div>`
              : items.map(t => html`<${TaskCard} key=${t.id} t=${t}
                  agentIds=${agentIds} teams=${teams}
                  blockers=${(t.depends_on || []).filter(d => (byId.get(d) || {}).status !== "done")}
                  refresh=${refresh} />`)}
          </div>
          ${status === "done" && all.length > 0 && html`<a class="col-more" href=${historyHash({ status: "done" })}
            title="Search every task in the history view">${all.length > items.length ? `all ${all.length} done tasks →` : "search done tasks →"}</a>`}
        </div>`;
      })}
    </div>
  </div>`;
}

// Agents panel: a switcher between the team view, which holds every agent
// control, and the original tile grid. It sits at the
// top of the phone overview and is the desktop sidebar; each place keeps its
// own choice per browser, and both start on the team view.
const AGENTS_VIEW_KEY = "agent-swarm:mobile-agents-view";
const SIDEBAR_VIEW_KEY = "agent-swarm:sidebar-agents-view";
const AGENTS_VIEWS = [["teams", "teams"], ["tiles", "tiles"]];
const COLLAPSED_TEAMS_KEY = "agent-swarm:collapsed-teams";

function readJSON(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key) || "null") ?? fallback; } catch { return fallback; }
}

// A team's ♛ button opens this: pick the queen from its running members
// (with an optional objective for her), or disband the team.
function TeamManage({ team, members, refresh, onDone }) {
  const [queen, setQueen] = useState(team.queen || "");
  const [objective, setObjective] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async (e) => {
    e.preventDefault();
    if (queen === (team.queen || "")) { onDone(); return; }
    setBusy(true);
    const body = queen ? { queen, objective: objective.trim() || null } : { queen: null };
    const res = await fetch(`/teams/${team.id}`, { method: "PATCH", headers: JSONH, body: JSON.stringify(body) }).catch(() => null);
    setBusy(false);
    if (!res?.ok) { alert(`Could not change the queen of ${team.name}.`); return; }
    onDone();
    refresh();
  };
  const disband = async () => {
    if (!confirm(`Disband team ${team.name}? Its agents keep running.`)) return;
    const res = await fetch(`/teams/${team.id}`, { method: "DELETE" }).catch(() => null);
    if (!res?.ok) { alert(`Could not disband ${team.name}.`); return; }
    onDone();
    refresh();
  };
  const offlineQueen = team.queen && !members.some(r => r.user_id === team.queen);
  return html`<form class="team-manage" onSubmit=${save}>
    <label>queen <select aria-label=${`Queen of ${team.name}`} value=${queen} disabled=${busy} onChange=${e => setQueen(e.target.value)}>
      <option value="">no queen</option>
      ${members.map(r => html`<option key=${r.user_id} value=${r.user_id}>${r.user_id}</option>`)}
      ${offlineQueen && html`<option value=${team.queen}>${team.queen} (offline)</option>`}
    </select></label>
    ${queen && queen !== team.queen && html`<input type="text" aria-label="Objective for the queen" placeholder="objective (optional)"
      value=${objective} disabled=${busy} onInput=${e => setObjective(e.target.value)} />`}
    <div class="team-manage-actions">
      <button class="act" disabled=${busy}>${busy ? "saving…" : "save"}</button>
      <button type="button" class="mini" onClick=${onDone}>cancel</button>
      <button type="button" class="mini disband" onClick=${disband}>disband team</button>
    </div>
  </form>`;
}

// Every agent control lives here. Running agents sit in outlined,
// collapsible team boxes, queen first; agents with no team come last. Each
// agent is one small chip that opens its page (which has "stop agent", the
// way to stop one on a touch screen). Chips drag between groups to change
// team, or onto the stop zone that shows during a drag. Each team's ♛
// button picks its queen or disbands it. Offline agents can be retired.
// New teams and spawning sit at the bottom.
function TeamBees({ state, refresh, machine, harness = null, unreadFor, focusUser = null }) {
  const [dragging, setDragging] = useState(null);
  const [over, setOver] = useState(null);
  const [managing, setManaging] = useState(null);
  const [collapsed, setCollapsed] = useState(() => new Set(readJSON(COLLAPSED_TEAMS_KEY, [])));
  const toggle = (key, open) => setCollapsed(prev => {
    const next = new Set(prev);
    if (open) next.delete(key); else next.add(key);
    try { localStorage.setItem(COLLAPSED_TEAMS_KEY, JSON.stringify([...next])); } catch { /* not kept */ }
    return next;
  });
  const live = state.recipients.filter(r => r.pane_alive && agentShown(r, machine, harness));
  const offline = state.recipients.filter(r => !r.pane_alive && !r.reserved && agentShown(r, machine, harness));
  const teams = state.teams || [];
  const groups = teams.map(t => ({
    key: `t:${t.id}`, name: t.name, queen: t.queen,
    members: live.filter(r => r.team_id === t.id)
      .sort((a, b) => (b.user_id === t.queen) - (a.user_id === t.queen) || a.user_id.localeCompare(b.user_id)),
    gone: offline.filter(r => r.team_id === t.id).map(r => r.user_id).sort(),
    teamId: t.id,
  }));
  const loners = live.filter(r => !teams.some(t => t.id === r.team_id)).sort((a, b) => a.user_id.localeCompare(b.user_id));
  const lonersGone = offline.filter(r => !teams.some(t => t.id === r.team_id)).map(r => r.user_id).sort();
  groups.push({ key: "none", name: "no team", queen: null, members: loners, gone: lonersGone, teamId: null });
  // Groups with no one running go last, so nothing moves under the pointer
  // during a drag. Empty teams still show (as one line), so they can be
  // managed and dropped onto; "no team" only shows when it has someone or
  // during a drag.
  groups.sort((a, b) => !a.members.length - !b.members.length);
  if (!dragging) groups.splice(0, groups.length, ...groups.filter(g => g.teamId !== null || g.members.length || g.gone.length));
  const stopOver = over === "stop";
  const stopDrop = agentDropProps(
    on => setOver(cur => on ? "stop" : cur === "stop" ? null : cur),
    user => {
      setDragging(null);
      const r = live.find(x => x.user_id === user);
      if (r) stopAgent(r, state, focusUser, refresh);
    });
  return html`<div class="team-bees">
    ${!live.length && html`<p class="compact-hive-empty">No live ${harness ? `${harnessStyle(harness).label} ` : ""}agents${machine ? ` on ${machine}` : ""}.</p>`}
    ${groups.map(g => {
    const busy = g.members.filter(r => agentStatus(r) === "working").length;
    const attention = g.members.filter(r => agentStatus(r) === "needs_attention").length;
    const drop = agentDropProps(
      on => setOver(cur => on ? g.key : cur === g.key ? null : cur),
      user => {
        setDragging(null);
        const from = live.find(r => r.user_id === user);
        if (from && (teams.some(t => t.id === from.team_id) ? from.team_id : null) !== g.teamId)
          moveAgentToTeam(user, g.teamId, refresh);
      });
    const team = g.teamId === null ? null : teams.find(t => t.id === g.teamId);
    const empty = !g.members.length && !g.gone.length;
    return html`<details key=${g.key} class=${`team-bees-group ${g.key === "none" ? "loose" : ""} ${empty && !dragging ? "empty" : ""} ${over === g.key ? "over" : ""}`}
        open=${!collapsed.has(g.key) || managing === g.key} onToggle=${e => toggle(g.key, e.currentTarget.open)} ...${drop}>
      <summary><span class="team-bees-name">${g.name}</span>
        <span class="team-bees-counts">${g.members.length}${busy ? html` · <span class="working">${busy} working</span>` : ""}${attention ? html` · <span class="attn">${attention} need you</span>` : ""}</span>
        ${team && html`<button type="button" class="team-bees-manage" aria-pressed=${managing === g.key}
          aria-label=${`Queen and settings for ${g.name}`} title=${team.queen ? `queen: ${team.queen} · change queen or disband` : "pick a queen or disband"}
          onClick=${e => { e.preventDefault(); e.stopPropagation(); setManaging(m => m === g.key ? null : g.key); }}>♛</button>`}</summary>
      ${managing === g.key && team && html`<${TeamManage} key=${`${g.key}:${team.queen}`} team=${team} members=${g.members} refresh=${refresh} onDone=${() => setManaging(null)} />`}
      <div class="team-bees-chips">${empty && dragging && html`<span class="team-bees-empty">drop here</span>`}${g.members.map(r => {
        const st = STATE[agentStatus(r)] || STATE.unknown;
        return html`<a key=${r.user_id} class=${`team-mate ${focusUser === r.user_id ? "here" : ""}`}
          aria-current=${focusUser === r.user_id ? "page" : null} href=${`#/agent/${encodeURIComponent(r.user_id)}`}
          style=${`--machine:${machineColor(r.node)}`} title=${`${r.user_id} · ${machineName(r.node)} · ${st.word}`}
          draggable="true" onDragStart=${e => {
            e.dataTransfer.effectAllowed = "move";
            e.dataTransfer.setData(AGENT_DRAG_TYPE, r.user_id);
            e.dataTransfer.setData("text/plain", r.user_id);
            setDragging(r.user_id);
          }} onDragEnd=${() => { setDragging(null); setOver(null); }}>
          <${Bee} node=${r.node} flavor=${r.flavor} size="small" working=${st.cls === "working"} />
          <span class="team-mate-name">${r.user_id}</span>
          ${g.queen === r.user_id && html`<span class="crown" title="team queen">♛</span>`}
          ${state.supervisor && state.supervisor.user_id === r.user_id && html`<span class="crown supervisor" title="swarm supervisor">✪</span>`}
          <span class=${`status ${st.cls}`}></span>
          ${unreadFor(r.user_id) && html`<span class="team-mate-unread" title="new reply">●</span>`}
        </a>`;
      })}</div>
      ${g.gone.length > 0 && html`<div class="team-bees-offline"><span title=${g.gone.join(", ")}>${g.gone.length} offline: ${g.gone.join(", ")}</span>
        <${RetireButton} ids=${g.gone} refresh=${refresh} label=${g.gone.length > 1 ? `retire all ${g.gone.length}` : "retire"} /></div>`}
    </details>`;
  })}
    ${dragging && html`<div class=${`team-bees-stop ${stopOver ? "over" : ""}`} ...${stopDrop}>drop here to stop ${dragging}</div>`}
    <${NewTeam} refresh=${refresh} />
    <${SpawnControl} refresh=${refresh} nodes=${state.nodes || []} />
  </div>`;
}

// `onClose` (the desktop sidebar) adds a heading with "Hide →" above every view.
function AgentsPanel({ state, refresh, machine, harness, setHarness, unreadFor, storageKey = AGENTS_VIEW_KEY, focusUser = null, onClose = null }) {
  const [view, setView] = useState(() => {
    try { return localStorage.getItem(storageKey) === "tiles" ? "tiles" : "teams"; } catch { return "teams"; }
  });
  const pick = (v) => {
    setView(v);
    try { localStorage.setItem(storageKey, v); } catch { /* not kept */ }
  };
  const live = state.recipients.filter(r => r.pane_alive && agentShown(r, machine, harness)).length;
  // The desktop sidebar has room in its heading row; elsewhere the filter
  // ends the view row.
  const filter = html`<${HarnessFilter} recipients=${state.recipients} harness=${harness} setHarness=${setHarness} />`;
  return html`<div class="agents-panel">
    ${onClose && html`<div class="roster-heading"><h2>agents ${live > 0 && html`<span class="count">· ${live}</span>`}</h2>
      ${filter}
      <button type="button" class="mini" aria-label="Hide agents" onClick=${onClose}>Hide →</button></div>`}
    <div class="agents-view-switch" role="group" aria-label="Agents view">
      <span>view</span>
      ${AGENTS_VIEWS.map(([v, label]) => html`<button key=${v} type="button" aria-pressed=${view === v} onClick=${() => pick(v)}>${label}</button>`)}
      ${!onClose && filter}
    </div>
    ${view === "tiles"
      ? html`<${CompactBees} state=${state} machine=${machine} harness=${harness} />`
      : html`<${TeamBees} state=${state} refresh=${refresh} machine=${machine} harness=${harness} unreadFor=${unreadFor} focusUser=${focusUser} />`}
  </div>`;
}

function Overview({ state, refresh, machine, harness, setHarness, unreadFor }) {
  return html`<div>
    <h2>activity</h2>
    <${HiveView} state=${state} refresh=${refresh} machine=${machine} harness=${harness} setHarness=${setHarness}
      compactBody=${html`<${AgentsPanel} state=${state} refresh=${refresh} machine=${machine} harness=${harness} setHarness=${setHarness} unreadFor=${unreadFor} />`} />
    <${Kanban} state=${state} refresh=${refresh} />
  </div>`;
}

/* ---------- agent focus mode ---------- */

function Scope({ user, refresh }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const preRef = useRef(null);
  const pinned = useRef(true);
  useEffect(() => {
    let live = true;
    setData(null);
    if (!open) return;
    pinned.current = true;
    const load = async () => {
      try {
        const r = await fetch(`/api/peek/${encodeURIComponent(user)}`);
        const d = await r.json();
        if (live) setData(d);
      } catch { /* next tick */ }
    };
    load();
    const t = setInterval(load, PEEK_MS);
    return () => { live = false; clearInterval(t); };
  }, [user, open]);
  useEffect(() => {
    const pre = preRef.current;
    if (pre && pinned.current) pre.scrollTop = pre.scrollHeight;
  }, [data]);
  const onScroll = (e) => {
    const el = e.target;
    pinned.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 8;
  };
  return html`<details class="scope" onToggle=${e => setOpen(e.currentTarget.open)}>
    <summary class="bar">
      <span class="t">terminal</span>
      <span>${data ? data.pane_label : ""}</span>
      <span style="margin-left:auto">${open ? "live capture · 2s" : "show terminal"}</span>
    </summary>
    ${data && data.error
      ? html`<div class="err">could not capture pane: ${data.error}</div>`
      : html`<pre ref=${preRef} onScroll=${onScroll}>${data
          ? ((data.text || "").replace(/\s+$/, "") || "(pane is blank)")
          : "capturing pane…"}</pre>`}
    <${TerminalInput} user=${user} />
  </details>`;
}

// tmux key names the server accepts (tmux.TERMINAL_KEYS), for menus a
// command opens, such as Codex's /model picker.
const TERMINAL_KEYS = [["Escape", "esc"], ["Up", "↑"], ["Down", "↓"], ["Enter", "⏎"], ["Tab", "tab"]];

function typeInto(user, body) {
  return fetch(`/agents/${encodeURIComponent(user)}/terminal`, {
    method: "POST", headers: JSONH, body: JSON.stringify(body),
  });
}

async function failure(res) {
  const body = await res.json().catch(() => ({}));
  return body.detail?.error || `error ${res.status}`;
}

// Types straight into the agent's pane, as if at its keyboard: `/fast`,
// `/model sonnet`. Unlike the conversation thread, nothing is wrapped as a
// message and no reply is expected.
function TerminalInput({ user }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const send = async (body) => {
    setBusy(true);
    setStatus("");
    const res = await typeInto(user, body);
    setBusy(false);
    if (!res.ok) { setStatus(await failure(res)); return false; }
    return true;
  };
  const submit = async (e) => {
    e.preventDefault();
    if (!text.trim() || busy) return;
    if (await send({ text })) setText("");
  };
  return html`<form class="composer terminal-input" onSubmit=${submit}>
    <div class="compose-row">
      <span class="mark">$</span>
      <input type="text" value=${text} disabled=${busy} aria-label=${`Type into ${user}'s terminal`}
        placeholder="type into the terminal, e.g. /fast or /model sonnet"
        onInput=${e => setText(e.target.value)} />
      <button type="submit" class="mini" disabled=${busy || !text.trim()}>enter</button>
    </div>
    <div class="compose-meta">
      <span>keys</span>
      ${TERMINAL_KEYS.map(([key, label]) => html`<button key=${key} type="button" class="mini"
        disabled=${busy} title=${`Press ${key} in ${user}'s pane`} onClick=${() => send({ key })}>${label}</button>`)}
      ${status && html`<span class="err">${status}</span>`}
    </div>
  </form>`;
}

// Messages the owner has sent that the server has not confirmed yet. Composers
// announce them here so the thread can show them the moment send is pressed.
const pendingSends = new EventTarget();
let pendingSeq = 0;

// crypto.randomUUID needs a secure context; the dashboard is often opened
// over plain http on a LAN or tailnet address, where getRandomValues works.
function newClientId() {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, "0")).join("");
}

// Waits before re-sending a message whose answer was lost. The server knows
// the message by its client id, so a re-send never delivers it twice.
const RESEND_DELAYS_MS = [1000, 3000, 6000];

function MessageComposer({ recipient, refresh, autoFocus = false }) {
  const [text, setText] = useState("");
  const [context, setContext] = useState("");
  const [images, setImages] = useState([]);
  const [status, setStatus] = useState("");
  const [sending, setSending] = useState(false);
  // The unconfirmed send this draft came back from: {clientId, text, context, images}.
  const [retryOf, setRetryOf] = useState(null);
  const composerRef = useRef(null);
  const draftKey = `agent-swarm:draft:${recipient}:thread`;
  const attachments = useAttachments(images, setImages, setStatus, draftKey);
  const { uploading, dragging } = attachments;
  useEffect(() => {
    try {
      const draft = JSON.parse(localStorage.getItem(draftKey) || "null");
      setText(draft?.text || "");
      setContext(draft?.context || "");
      setImages(Array.isArray(draft?.images) ? draft.images : []);
      setRetryOf(draft?.retryOf || null);
      setStatus("");
    } catch { /* an invalid saved draft should not block messaging */ }
  }, [draftKey]);
  // On an agent's page the reply box takes focus, so typing starts the reply
  // without clicking it first. Not on touch screens, where focus opens the
  // keyboard, and not away from a field the owner is already typing in.
  useEffect(() => {
    const el = composerRef.current;
    const busy = document.activeElement?.closest?.("input, textarea, select, [contenteditable]");
    if (autoFocus && el && (!busy || busy === el) && !matchMedia("(pointer: coarse)").matches) {
      el.focus({ preventScroll: true });
    }
  }, [autoFocus, recipient]);
  useEffect(() => {
    const el = composerRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);
  useEffect(() => {
    let timer;
    const onOutcome = (e) => {
      if (e.detail.draftKey !== draftKey) return;
      const { status: next, draft } = e.detail;
      if (draft) {
        setText(t => t || draft.text);
        setContext(c => c || draft.context);
        setImages(imgs => (imgs.length ? imgs : draft.images));
        setRetryOf(draft.retryOf || null);
      }
      setStatus(next);
      clearTimeout(timer);
      if (next === "delivered") timer = setTimeout(() => setStatus(s => (s === "delivered" ? "" : s)), 2500);
    };
    pendingSends.addEventListener("outcome", onOutcome);
    return () => { clearTimeout(timer); pendingSends.removeEventListener("outcome", onOutcome); };
  }, [draftKey]);
  // Keep the draft (text, tag, and uploaded images) across reloads. Saved in
  // a layout effect, which runs with the render, so a key press that leaves
  // the page right after typing (Alt+] to a teammate) cannot outrun it.
  const loadedKey = useRef(null);
  useLayoutEffect(() => {
    if (loadedKey.current !== draftKey) { loadedKey.current = draftKey; return; }
    try {
      if (text || context || images.length) localStorage.setItem(draftKey, JSON.stringify({ text, context, images, retryOf }));
      else localStorage.removeItem(draftKey);
    } catch { /* storage full or blocked: the draft just isn't kept */ }
  }, [draftKey, text, context, images, retryOf]);
  const canSend = !sending && uploading === 0 && (text.trim() || images.length > 0);
  const send = async (e) => {
    e.preventDefault();
    const content = text.trim();
    if (!canSend) return;
    // Clear the composer and show the message in the thread right away; the
    // server confirms delivery afterwards, and a failure restores the draft.
    const clientId = draftClientId({ text, context, images }, retryOf, newClientId);
    const draft = { text, context, images, retryOf: { clientId, text, context, images } };
    const pending = {
      id: `pending-${++pendingSeq}`, pending: true, delivered: true, status: "delivered",
      sender: "owner", recipient, content, context: context.trim() || null,
      attachments: images, ts: Date.now() / 1000,
    };
    setSending(true);
    setStatus("sending…");
    setText("");
    setContext("");
    setImages([]);
    setRetryOf(null);
    // Forget the saved draft now, not in the save effect: the first message
    // to an agent turns this lone composer into a thread with a new one,
    // which mounts before this one's effect runs and would load the old
    // draft back. A failed or unconfirmed send writes it back (keepDraft).
    try { localStorage.removeItem(draftKey); } catch { /* best effort */ }
    pendingSends.dispatchEvent(new CustomEvent("add", { detail: pending }));
    // The outcome is addressed by draft key, not to this component: sending
    // the first message turns the empty panel into a thread with its own
    // composer, and that one has to show the result and get the draft back.
    const report = (detail) => pendingSends.dispatchEvent(
      new CustomEvent("outcome", { detail: { draftKey, ...detail } }));
    const keepDraft = () => {
      try { localStorage.setItem(draftKey, JSON.stringify(draft)); } catch { /* best effort */ }
    };
    const attempt = async () => {
      try {
        const r = await fetch("/owner/send", {
          method: "POST", headers: JSONH,
          body: JSON.stringify({ recipient, content, context: pending.context, attachments: images, client_id: clientId }),
        });
        let body = null;
        try { body = await r.json(); } catch { body = null; }
        return deliveryOutcome(r.ok, body);
      } catch (err) {
        return unansweredOutcome(err);
      }
    };
    // On a flaky connection the answer, not the message, is often what got
    // lost. Asking again with the same client id finds out which.
    let outcome = await attempt();
    for (const delay of RESEND_DELAYS_MS) {
      if (outcome.status !== "uncertain") break;
      report({ status: `not confirmed (${outcome.reason}); checking again…` });
      await new Promise(resolve => setTimeout(resolve, delay));
      outcome = await attempt();
    }
    if (outcome.status === "delivered") {
      report({ status: "delivered" });
    } else if (outcome.status === "unknown") {
      // The paste may have landed. No draft comes back: resending is a
      // deliberate act on the marked message, not a reflex.
      report({ status: `outcome unknown: ${outcome.reason}. The agent may have it; see the marked message.` });
    } else if (outcome.status === "uncertain") {
      keepDraft();
      report({ status: `not confirmed: ${outcome.reason}. Draft kept; sending it unchanged is safe, it will not arrive twice`, draft });
    } else {
      keepDraft();
      report({ status: `delivery failed: ${outcome.reason}. Draft kept`, draft });
    }
    // Swap the placeholder for the server's copy in one step, no flicker.
    await refresh();
    pendingSends.dispatchEvent(new CustomEvent("settle", { detail: pending.id }));
    setSending(false);
  };
  const clearDraft = () => {
    setText("");
    setContext("");
    setImages([]);
    setStatus("");
    composerRef.current?.focus();
  };
  return html`<form class=${`composer ${dragging ? "dragging" : ""}`} onSubmit=${send} ...${sending ? {} : attachments.dropProps}>
    <div class="compose-row">
      <span class="mark">❯</span>
      <textarea ref=${composerRef} value=${text} rows="2"
        onInput=${e => setText(e.target.value)}
        onPaste=${sending ? undefined : attachments.onPaste}
        onKeyDown=${e => {
          if (e.key === "Enter" && !e.shiftKey && !(e.metaKey || e.ctrlKey)) send(e);
        }}
        placeholder=${`Message ${recipient}… (paste or drop files)`} aria-label=${`Message ${recipient} as owner`} />
    </div>
    <${AttachmentPicker} files=${images} controls=${attachments} disabled=${sending} />
    <div class="compose-meta">
      <input class="context" type="text" value=${context} onInput=${e => setContext(e.target.value)}
        placeholder="context tag (optional)" aria-label="Optional context tag" />
      <span class="count">${text.length} character${text.length === 1 ? "" : "s"}${images.length > 0 ? ` · ${images.length} file${images.length === 1 ? "" : "s"}` : ""}</span>
      <span class="hint">Enter to send · Shift + Enter for a new line</span>
      <div class="actions">
        ${status && html`<span class=${status.startsWith("delivery failed") || status.startsWith("image not added") ? "error" : "sent"} role="status">${status}</span>`}
        ${(text || context || images.length > 0) && html`<button type="button" class="mini" onClick=${clearDraft}>clear</button>`}
        <button class="act" type="submit" disabled=${!canSend}>
          ${sending ? "sending…" : uploading ? "uploading…" : "send"}
        </button>
      </div>
    </div>
  </form>`;
}

// Text size in focus mode, in px; A− / A+ step it and the choice is kept.
const FOCUS_FONT = { min: 12, max: 26, start: 16, step: 2 };
const FOCUS_FONT_KEY = "agent-swarm:focus-font";

// Chat convention: the sender whose side you are on sits on the right. In a
// thread with the owner that is the owner. Between two agents it is the
// agent whose page this is; off any agent's page, the second of the pair.
function sentByViewer(sender, a, b, page) {
  if (a === "owner" || b === "owner") return sender === "owner";
  if (page === a || page === b) return sender === page;
  return sender !== a;
}

function Thread({ a, b, msgs, freshIds, now, refresh, page = null, agents = null }) {
  const boxRef = useRef(null);
  const follower = useRef(null);
  if (!follower.current) follower.current = createBottomFollower();
  const resizeRef = useRef(null);
  const previousHistory = useRef(null);
  const [historyHeight, setHistoryHeight] = useState(null);
  const recipient = a === "owner" ? b : b === "owner" ? a : null;
  // In a thread between two agents, the one whose page this is not: a link
  // in the header goes to that agent's page to message them.
  const other = recipient || a === b ? null : page === a ? b : page === b ? a : null;
  // Only a registered agent has a page; the hub (supervisor nudges) has none.
  const peer = other && agents?.has(other) ? other : null;
  const [expanded, setExpanded] = useState(!!recipient);
  // Focus mode: the thread fills the window for reading. The owner's thread
  // also answers to Cmd/Ctrl+Shift+L, including from the reply box; Esc leaves.
  // A teammate switch made in focus mode lands in focus mode.
  const [focused, setFocused] = useState(() => !!(recipient && switchCarry?.focus));
  const focusMac = /Mac|iPhone|iPad/.test(navigator.platform);
  const focusShortcut = focusMac ? "⌘⇧L" : "Ctrl+Shift+L";
  const [focusFont, setFocusFont] = useState(() => {
    try { return Number(localStorage.getItem(FOCUS_FONT_KEY)) || FOCUS_FONT.start; } catch { return FOCUS_FONT.start; }
  });
  const stepFont = (by) => setFocusFont(size => {
    const next = Math.max(FOCUS_FONT.min, Math.min(FOCUS_FONT.max, size + by));
    try { localStorage.setItem(FOCUS_FONT_KEY, String(next)); } catch { /* not kept, still applied */ }
    return next;
  });
  const savedScroll = useRef(0);
  const bodyId = `thread-${encodeURIComponent(pairKey(a, b))}`;
  useLayoutEffect(() => {
    if (expanded && boxRef.current) boxRef.current.scrollTop = savedScroll.current;
  }, [expanded]);
  // Follow synchronously after rendering, before a queued browser scroll
  // event can mistake the new bottom distance for the reader scrolling up.
  // Stay pinned to the newest message whenever the history box or any bubble
  // changes size (drag-resize, window resize, late font/layout), not only
  // when a message arrives.
  const lastId = msgs.length ? msgs[msgs.length - 1].id : null;
  useLayoutEffect(() => {
    const el = boxRef.current;
    if (!el || !expanded) return;
    const previous = previousHistory.current;
    if (previous && previous.first !== msgs[0]?.id && msgs.some(m => m.id === previous.first)) {
      el.scrollTop = previous.top + el.scrollHeight - previous.height;
    }
    const stick = () => {
      follower.current.follow(el);
      previousHistory.current = { first: msgs[0]?.id, height: el.scrollHeight, top: el.scrollTop };
    };
    const ro = new ResizeObserver(stick);
    ro.observe(el);
    for (const child of el.children) ro.observe(child);
    stick();
    return () => ro.disconnect();
  }, [msgs.length, lastId, historyHeight, expanded]);
  const toggleFocus = () => {
    setExpanded(true);
    setFocused(v => !v);
  };
  useEffect(() => {
    document.documentElement.classList.toggle("thread-focus-open", focused);
    return () => document.documentElement.classList.remove("thread-focus-open");
  }, [focused]);
  useLayoutEffect(() => {
    const onKey = (e) => {
      if (e.isComposing || document.querySelector(".quick-switch[open]")) return;
      if (e.key === "Escape" && focused) {
        e.preventDefault();
        e.stopImmediatePropagation();
        setFocused(false);
        return;
      }
      const modifier = focusMac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
      if (page && (recipient || focused) && (!document.querySelector(".thread.focused") || focused)
          && e.code === "KeyL" && e.shiftKey && modifier && !e.altKey) {
        e.preventDefault();
        e.stopImmediatePropagation();
        if (!e.repeat) toggleFocus();
      }
    };
    // Consume Escape before page-level shortcuts, regardless of listener order.
    addEventListener("keydown", onKey, true);
    return () => removeEventListener("keydown", onKey, true);
  }, [focused, recipient]);
  const onScroll = (e) => {
    if (!expanded) return;
    savedScroll.current = e.currentTarget.scrollTop;
    if (previousHistory.current) previousHistory.current.top = e.currentTarget.scrollTop;
    follower.current.onScroll(e.currentTarget);
  };
  const resizeBounds = () => ({ min: 120, max: Math.max(120, Math.floor(innerHeight * .85)) });
  const resizeTo = (height) => {
    const { min, max } = resizeBounds();
    setHistoryHeight(Math.max(min, Math.min(max, Math.round(height))));
  };
  const resizeStart = (e) => {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    resizeRef.current = { y: e.clientY, height: boxRef.current.getBoundingClientRect().height };
  };
  const resizeMove = (e) => {
    if (!resizeRef.current) return;
    resizeTo(resizeRef.current.height + e.clientY - resizeRef.current.y);
  };
  const resizeEnd = (e) => {
    if (!resizeRef.current) return;
    resizeRef.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
  };
  const resizeKey = (e) => {
    const current = historyHeight ?? boxRef.current.getBoundingClientRect().height;
    const { min, max } = resizeBounds();
    const next = e.key === "ArrowUp" ? current - 40
      : e.key === "ArrowDown" ? current + 40
        : e.key === "Home" ? min
          : e.key === "End" ? max : null;
    if (next === null) return;
    e.preventDefault();
    resizeTo(next);
  };
  return html`<div class=${`thread ${focused ? "focused" : ""}`} role=${focused ? "dialog" : null}
      style=${focused ? { "--focus-font": `${focusFont}px` } : null}
      aria-label=${focused ? `Conversation ${a} and ${b}` : null}>
    <div class="thread-head">
      <button type="button" class="bar thread-toggle" aria-expanded=${expanded} aria-controls=${bodyId}
          disabled=${focused} onClick=${() => setExpanded(v => !v)}>
        <span class="thread-chevron" aria-hidden="true">${expanded ? "▾" : "▸"}</span>
        ${disp(a)} <span class="swap">⇄</span> ${disp(b)}
        <span class="n">${msgs.length} msg${msgs.length === 1 ? "" : "s"}</span>
      </button>
      ${focused && html`
        <button type="button" class="thread-focus" title="Smaller text" aria-label="Smaller text"
          disabled=${focusFont <= FOCUS_FONT.min} onClick=${() => stepFont(-FOCUS_FONT.step)}>A−</button>
        <button type="button" class="thread-focus" title="Larger text" aria-label="Larger text"
          disabled=${focusFont >= FOCUS_FONT.max} onClick=${() => stepFont(FOCUS_FONT.step)}>A+</button>`}
      ${peer && !focused && html`<a class="thread-focus thread-goto" href=${`#/agent/${encodeURIComponent(peer)}`}
        title=${`Go to ${peer}'s page to message them`}>open ${peer} →</a>`}
      <button type="button" class="thread-focus" aria-pressed=${focused} onClick=${toggleFocus}
        title=${focused ? `Back to the page (Esc or ${focusShortcut})` : `Expand this conversation to fill the window${recipient ? ` (${focusShortcut})` : ""}`}>
        ${focused ? "✕ close" : "⤢ focus"}${recipient && html` <span class="focus-key-hint">${focusShortcut}</span>`}</button>
    </div>
    <div id=${bodyId} class="thread-body" hidden=${!expanded}>
    <div class="msgs" ref=${boxRef} onScroll=${onScroll}
      style=${historyHeight === null ? null : { height: `${historyHeight}px` }}>
      ${msgs.map(m => html`
        <div key=${m.id} class=${[
            "msg",
            sentByViewer(m.sender, a, b, page) ? "right" : "",
            freshIds.has(m.id) ? "fresh" : "",
            m.status === "failed" ? "failed" : m.status === "unknown" ? "unknown" : "",
            m.sender === "owner" ? "from-owner" : "",
            m.pending ? "pending" : "",
          ].join(" ")}>
          <div class="bubble">${m.content && html`<div class="md"
            dangerouslySetInnerHTML=${{ __html: renderMarkdown(shellNewlines(m.content)) }} />`}${m.attachments?.length > 0 && html`<div class=${`msg-images ${m.content ? "" : "only"}`}>
            ${m.attachments.map(name => html`<${AttachmentLink} key=${name} name=${name} />`)}
          </div>`}</div>
          <div class="tag">${disp(m.sender)}${m.context && html` · <span class="ctx">${m.context}</span>`} · ${m.pending ? "sending…" : rel(m.ts, now)}${m.status === "failed" && html` · <span class="ctx">undelivered${m.delivery_error ? `: ${m.delivery_error}` : ""}</span>`}${m.status === "unknown" && html` · <span class="ctx">outcome unknown${m.delivery_error ? `: ${m.delivery_error}` : ""}</span>${m.sender === "owner" && html` <${Resend} m=${m} refresh=${refresh} />`}`}</div>
        </div>`)}
    </div>
    <button type="button" class="history-resizer" role="separator" aria-orientation="horizontal"
      aria-label="Resize conversation history"
      aria-valuemin="120" aria-valuemax=${resizeBounds().max}
      aria-valuenow=${historyHeight ?? 340} title="Drag to resize conversation history"
      onPointerDown=${resizeStart} onPointerMove=${resizeMove}
      onPointerUp=${resizeEnd} onPointerCancel=${resizeEnd} onKeyDown=${resizeKey}>
      <span>drag to resize history</span>
    </button>
    ${recipient && html`<${MessageComposer} recipient=${recipient} refresh=${refresh} autoFocus=${!!page} />`}
    </div>
  </div>`;
}

// What the agent is doing now, then what it did before, newest first.
function Doing({ summaries, now }) {
  if (summaries.length === 0) {
    return html`<div class="doing-box empty-doing">No status yet. Agents post one with
      <code>agent-swarm status "working on …"</code>; Claude Code and Codex pane titles
      show up here too.</div>`;
  }
  const [cur, ...past] = summaries.slice(0, 6);
  const line = (s) => html`<span class="src" title=${SUMMARY_SOURCE[s.source] || s.source}>${s.source === "agent" ? "✎" : "▭"}</span>`;
  return html`<div class="doing-box">
    <div class="now">${line(cur)} ${cur.text} <span class="age">· ${rel(cur.ts, now)}</span></div>
    ${past.length > 0 && html`<details class="status-history"><summary>${past.length} earlier ${past.length === 1 ? "update" : "updates"}</summary><ol class="past">
      ${past.map(s => html`<li>${line(s)} ${s.text} <span class="age">· ${rel(s.ts, now)}</span></li>`)}
    </ol></details>`}
  </div>`;
}

function AgentTaskRow({ t, taskIds, agentIds, refresh }) {
  const [error, setError] = useState("");
  const assign = async e => {
    const result = await patchTask(t.id, { assignee: e.target.value || null });
    if (!result.ok) { setError(result.error); return; }
    setError("");
    refresh();
  };
  return html`<div class=${`trow ${t.status}`}>
    <span class="tid">#${t.id}</span>
    <span class="t">${t.title}<${AttachmentList} files=${t.attachments} />
      ${t.note && html`<details class="task-row-note"><summary>How to verify</summary><div>${t.note}</div></details>`}
    </span>
    <span class=${`pill ${t.status}`}>${t.status.replace("_", " ")}</span>
    <select title="assignee" aria-label=${`Assign task #${t.id}`} value=${t.assignee || ""}
      disabled=${t.status === "done"} onChange=${assign}>
      <option value="">unassigned</option>
      ${taskIds.map(a => html`<option key=${a} value=${a}>${a}${agentIds.includes(a) ? "" : " (stopped)"}</option>`)}
    </select>
    <${TaskStatusActions} task=${t} refresh=${refresh} />
    ${error && html`<span class="task-action-error" role="alert">${error}</span>`}
  </div>`;
}

// What a teammate switch carries to the next agent's page: whether the reply
// box had the cursor and whether the conversation was in focus mode.
let switchCarry = null;

// Alt+[ / Alt+] step through the agent's team, from anywhere on the page,
// including the reply box. Matched by physical key: on a Mac, Option+[ is a
// typed character. Vimium only binds keys outside text fields, and Chrome
// leaves Alt+brackets free (Alt+digits switch tabs on Linux).
function useTeammateKeys(members) {
  // One listener for the page's lifetime. The agent to step from is read
  // from the URL, not the rendered page: a second Alt+] pressed before the
  // last switch has rendered must step from where the URL already is, or it
  // lands on the wrong teammate.
  const current = useRef(null);
  current.current = members;
  useEffect(() => {
    const onKey = (e) => {
      if (!e.altKey || e.ctrlKey || e.metaKey || document.querySelector(".quick-switch[open]")) return;
      const members = current.current;
      const here = location.hash.startsWith("#/agent/")
        ? decodeURIComponent(location.hash.slice("#/agent/".length)) : null;
      const by = e.code === "BracketRight" ? 1 : e.code === "BracketLeft" ? -1 : 0;
      const known = members && members.some(m => m.user_id === here);
      const next = by && known && stepTeammate(members, here, by);
      if (!next) return;
      e.preventDefault();
      switchCarry = {
        composer: !!document.activeElement?.closest?.(".thread .composer"),
        focus: !!document.querySelector(".thread.focused"),
      };
      location.hash = `#/agent/${encodeURIComponent(next)}`;
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, []);
}

function TeamStrip({ crew, user, unreadFor }) {
  return html`<nav class="team-strip" aria-label=${`Team ${crew.team.name}`}>
    <span class="team-strip-name">${crew.team.name}</span>
    ${crew.members.map(m => {
      const st = STATE[agentStatus(m)] || STATE.unknown;
      const here = m.user_id === user;
      return html`<a key=${m.user_id} href=${`#/agent/${encodeURIComponent(m.user_id)}`}
        class=${`team-mate ${here ? "here" : ""}`} aria-current=${here ? "page" : null}
        title=${`${m.user_id} · ${st.word}`}>
        <${Bee} node=${m.node} flavor=${m.flavor} size="small" working=${st.cls === "working"} />
        <span class="team-mate-name">${m.user_id}</span>
        ${crew.team.queen === m.user_id && html`<span class="crown" title="team queen">♛</span>`}
        <span class=${`status ${st.cls}`}></span>
        ${unreadFor(m.user_id) && html`<span class="team-mate-unread" title="new reply">●</span>`}
      </a>`;
    })}
    ${crew.members.length > 1 && html`<span class="team-strip-hint">Alt+[ / Alt+]</span>`}
  </nav>`;
}

// Every conversation the owner has had, one row per agent, newest first, to
// find whom you asked about something that never became a task. The full
// history loads once when the tab opens; new messages come from the poll.
const CHATS_ROUTE = "#/chats";
const chatsQuery = () => new URLSearchParams(location.hash.split("?")[1] || "").get("q") || "";

function snippet(text, words, width = 240) {
  const flat = (text || "").replace(/\s+/g, " ").trim();
  const at = words.length ? flat.toLowerCase().indexOf(words[0]) : -1;
  const start = at > 80 ? at - 60 : 0;
  const cut = flat.slice(start, start + width);
  return `${start ? "…" : ""}${cut}${start + width < flat.length ? "…" : ""}`;
}

function marked(text, words) {
  if (!words.length) return text;
  const re = new RegExp(`(${words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return text.split(re).map((part, i) => (i % 2 ? html`<mark>${part}</mark>` : part));
}

function ChatsView({ state, unreadFor }) {
  const [full, setFull] = useState(null);
  const [query, setQuery] = useState(chatsQuery);
  useEffect(() => {
    let live = true;
    fetch("/messages?user=owner&limit=100000")
      .then(r => r.json())
      .then(d => { if (live) setFull(d.messages || []); })
      .catch(() => { if (live) setFull([]); });
    return () => { live = false; };
  }, []);
  const update = (q) => {
    setQuery(q);
    history.replaceState(null, "", q ? `${CHATS_ROUTE}?q=${encodeURIComponent(q)}` : CHATS_ROUTE);
  };
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const chats = useMemo(
    () => ownerChats([...state.messages, ...(full || [])], query),
    [state.messages, full, query],
  );
  const byId = new Map(state.recipients.map(r => [r.user_id, r]));
  return html`<div class="chats">
    <h2>chats <span class="count">· ${chats.length}${full === null ? " · loading full history…" : ""}</span></h2>
    <input type="text" class="h-search chats-search" value=${query} autofocus
      placeholder="search your conversations: who did I ask about…"
      aria-label="Search your conversations" onInput=${e => update(e.target.value)}
      onKeyDown=${e => { if (e.key === "Escape" && query) { e.stopPropagation(); update(""); } }} />
    ${chats.length === 0
      ? html`<div class="empty">${query ? html`No conversation mentions "<b>${query}</b>".` : "No conversations yet."}</div>`
      : html`<div class="chat-list">${chats.map(c => {
          const r = byId.get(c.agent);
          const st = STATE[r ? agentStatus(r) : "unknown"] || STATE.unknown;
          const m = c.match || c.last;
          return html`<a key=${c.agent} class="chat-row" href=${`#/agent/${encodeURIComponent(c.agent)}`}>
            ${r ? html`<${Bee} node=${r.node} flavor=${r.flavor} size="small" working=${st.cls === "working"} />`
              : html`<span class="chat-gone" aria-hidden="true">◌</span>`}
            <span class="chat-main">
              <span class="chat-who">${c.agent}<span class=${`status ${st.cls}`} title=${r ? st.word : "no longer registered"}></span>
                ${unreadFor(c.agent) && html`<span class="team-mate-unread" title="new reply">●</span>`}
                <span class="chat-when">${rel(m.ts, state.now)}${c.match ? ` · ${c.matches} match${c.matches === 1 ? "" : "es"}` : ` · ${c.count} msg${c.count === 1 ? "" : "s"}`}</span></span>
              <span class="chat-line"><b>${m.sender === "owner" ? "you" : m.sender}:</b> ${marked(snippet(m.content, words), words)}</span>
            </span>
          </a>`;
        })}</div>`}
  </div>`;
}

function FocusView({ user, state, refresh, freshIds, unreadFor }) {
  const history = useAgentHistory(user);
  const messages = [...new Map([...history.messages, ...state.messages]
    .filter(m => m.sender === user || m.recipient === user).map(m => [m.id, m])).values()]
    .sort((a, b) => a.ts - b.ts || a.id - b.id);
  const crew = useMemo(() => teammates(state.recipients, state.teams, user), [state.recipients, state.teams, user]);
  const members = useMemo(() => crew && crew.members, [crew && crew.members.map(m => m.user_id).join(" ")]);
  useTeammateKeys(members);
  // Arriving by a teammate switch: put the cursor back in the reply box.
  useEffect(() => {
    const carry = switchCarry;
    switchCarry = null;
    if (carry?.composer) requestAnimationFrame(() => document.querySelector(".thread .composer textarea")?.focus());
  }, [user]);
  // A thread's rank is assigned once, so a new peer message cannot reorder
  // every existing conversation on the next polling render.
  const threadOrder = useRef(new Map());
  const nextThreadOrder = useRef(0);
  const registered = new Set(state.recipients.map(x => x.user_id));
  const r = state.recipients.find(x => x.user_id === user);
  if (!r) return html`<div class="empty">No agent named "${user}".
    <br /><br /><button class="mini" onClick=${() => { location.hash = "#/"; }}>back to overview</button></div>`;
  const flavor = (r.flavor || "generic").toLowerCase();
  const status = agentStatus(r);
  const st = STATE[status] || STATE.unknown;
  const detail = r.activity && r.activity.detail;
  const myTasks = state.tasks.filter(t => t.assignee === user);
  const agentIds = state.recipients.filter(x => x.pane_alive).map(x => x.user_id);
  const taskIds = agentIds.includes(user) ? agentIds : agentIds.concat(user);
  const groups = new Map();
  for (const m of messages) {
    if (m.sender !== user && m.recipient !== user) continue;
    const k = pairKey(m.sender, m.recipient);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(m);
  }
  for (const key of groups.keys()) {
    if (!threadOrder.current.has(key)) {
      threadOrder.current.set(key, nextThreadOrder.current++);
    }
  }
  const ownerThread = pairKey("owner", user);
  const threads = [...groups.entries()]
    .sort(([a], [b]) => {
      if (a === ownerThread) return -1;
      if (b === ownerThread) return 1;
      return threadOrder.current.get(a) - threadOrder.current.get(b);
    })
    .map(([, msgs]) => msgs);
  const hasOwnerThread = groups.has(ownerThread);
  return html`<div>
    <div class="focus-top">
      <button type="button" class="focus-back" onClick=${() => { location.hash = "#/"; }}>← back to overview</button>
      ${crew && html`<${TeamStrip} crew=${crew} user=${user} unreadFor=${unreadFor} />`}
    </div>
    <div class="fhead">
      <${Bee} node=${r.node} flavor=${r.flavor} working=${status === "working"} />
      <div class="who">
        <div class="nm">${user}<span class=${`status ${st.cls}`} title=${st.word}></span></div>
        <div class="meta">
          <span class="chip">${FLAVOR_ICON[flavor] || FLAVOR_ICON.generic} ${flavor}</span>
          <${ModelLabel} r=${r} refresh=${refresh} /> · <${MachineBadge} node=${r.node} /> · pane <b>${r.pane_label}</b>${r.pane_alive ? "" : " (stopped)"}
          <${JumpToPane} r=${r} />
          <${CompactButton} r=${r} />
          <${StopAgentButton} key=${user} r=${r} refresh=${refresh} />
          · joined ${rel(r.registered_at, state.now)}
          · <span style=${`color:${st.color}`}>${st.word}</span>${status === "needs_attention" && detail ? html` <span class="attn">${detail}</span>` : ""}
        </div>
        ${r.instructions && html`<div class="inst">"${r.instructions}"</div>`}
      </div>
    </div>
    <h2>status updates</h2>
    <${Doing} summaries=${r.summaries || []} now=${state.now} />
    <${Scope} key=${user} user=${user} refresh=${refresh} />
    <h2>conversations ${threads.length > 0 && html`<span class="count">· ${threads.length}</span>`}</h2>
    ${history.error && html`<p role="status">${history.error}</p>`}
    ${!history.loaded && !history.error && html`<p role="status">Loading conversation history…</p>`}
    ${history.more && html`<button type="button" class="mini" disabled=${history.busy} onClick=${history.loadOlder}>
      ${history.busy ? "Loading older messages…" : "Load older messages"}</button>`}
    ${threads.length === 0
      ? html`<div class="thread">${history.loaded && html`<div class="empty">Nothing yet. Start a conversation with ${user} below.</div>`}
          <${MessageComposer} recipient=${user} refresh=${refresh} autoFocus /></div>`
      : threads.map(msgs => {
          const [a, b] = pairKey(msgs[0].sender, msgs[0].recipient).split(" ");
          return html`<${Thread} key=${pairKey(a, b)} a=${a} b=${b} msgs=${msgs} page=${user} agents=${registered}
            freshIds=${freshIds} now=${state.now} refresh=${refresh} />`;
        })}
    ${threads.length > 0 && !hasOwnerThread && html`<div class="thread" style="margin-top:14px">
      <div class="bar">${disp("owner")} <span class="swap">⇄</span> ${user}</div>
      <${MessageComposer} recipient=${user} refresh=${refresh} autoFocus />
    </div>`}
    <h2 style="margin-top:26px">tasks ${myTasks.length > 0 && html`<span class="count">· ${myTasks.length}</span>`}
      ${myTasks.length > 0 && html`<a class="h2-link" href=${historyHash({ agent: user })}>search ${user}'s history →</a>`}</h2>
    <${TaskComposer} key=${user} user=${user} state=${state} refresh=${refresh} folded />
    ${myTasks.length === 0
      ? html`<div class="empty">No tasks assigned to ${user} yet.</div>`
      : myTasks.map(t => html`<${AgentTaskRow} key=${t.id} t=${t} taskIds=${taskIds}
          agentIds=${agentIds} refresh=${refresh} />`)}
  </div>`;
}

/* ---------- app ---------- */

// A page saved to the iOS home screen opens without Safari's address bar,
// so it has no reload button and no pull-to-refresh. It gets its own.
const STANDALONE = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

const reportAttention = attentionReporter(globalThis.__TAURI__?.core?.invoke);

function App() {
  const compact = useMedia(COMPACT_LAYOUT);
  const [state, setState] = useState(null);
  const [machine, setMachine] = useState(null);
  const [harness, setHarness] = useState(null);
  const tabsRef = useRef([]);
  tabsRef.current = state?.tabs || [];
  const [rosterOpen, setRosterOpen] = useState(() => {
    try { const saved = localStorage.getItem("swarm-roster-open"); return saved === null ? true : saved === "true"; }
    catch { return true; }
  });
  const rosterOpenRef = useRef(rosterOpen);
  rosterOpenRef.current = rosterOpen;
  const toggleRef = useRef(null);
  const updateRoster = open => {
    rosterOpenRef.current = open;
    setRosterOpen(open);
    try { localStorage.setItem("swarm-roster-open", String(open)); } catch {}
  };
  // Desktop only: the compact layout has no drawer (the overview's agents
  // panel holds the roster).
  const toggleRoster = () => updateRoster(!rosterOpen);
  const closeRoster = () => { updateRoster(false); requestAnimationFrame(() => toggleRef.current?.focus()); };
  const mac = /Mac|iPhone|iPad/.test(navigator.platform);
  const rosterShortcut = mac ? "⌘B" : "Ctrl+B";
  useLayoutEffect(() => {
    const onKey = e => {
      const modifier = mac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
      if (compact || !modifier || e.code !== "KeyB" || e.shiftKey || e.altKey
          || e.isComposing || e.defaultPrevented || document.activeElement?.isContentEditable
          || document.querySelector("dialog[open], .thread.focused")) return;
      e.preventDefault();
      if (e.repeat) return;
      // Move focus out of a drawer that is about to become inert; otherwise
      // keep the cursor in the composer so a toggle does not interrupt typing.
      if (rosterOpenRef.current && document.activeElement?.closest?.("#agent-sidebar")) closeRoster();
      else updateRoster(!rosterOpenRef.current);
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [compact, mac]);
  const [connected, setConnected] = useState(true);
  const [clock, setClock] = useState(new Date().toLocaleTimeString());
  const [route, setRoute] = useState(location.hash);
  const [freshIds, setFreshIds] = useState(new Set());
  const seen = useRef({ maxId: 0, first: true, byAgent: {} });
  const [pending, setPending] = useState([]);
  useEffect(() => {
    const add = (e) => setPending(p => [...p, e.detail]);
    const settle = (e) => setPending(p => p.filter(m => m.id !== e.detail));
    pendingSends.addEventListener("add", add);
    pendingSends.addEventListener("settle", settle);
    return () => {
      pendingSends.removeEventListener("add", add);
      pendingSends.removeEventListener("settle", settle);
    };
  }, []);

  const focusUser = route.startsWith("#/agent/")
    ? decodeURIComponent(route.slice("#/agent/".length)) : null;
  const onHistory = route.startsWith(HISTORY_ROUTE);
  const onChats = route.startsWith(CHATS_ROUTE);
  const onTab = route.startsWith(TAB_ROUTE) ? decodeURIComponent(route.slice(TAB_ROUTE.length)) : null;
  const onOverview = !focusUser && !onHistory && !onChats && !onTab;
  // A roster link may be several screens down on a phone. Bring the new
  // view into sight; polling and task-history filters must not move it.
  const previousView = useRef({ focusUser, onHistory });
  useEffect(() => {
    const before = previousView.current;
    previousView.current = { focusUser, onHistory };
    if ((before.focusUser !== focusUser || before.onHistory !== onHistory) && compact)
      document.querySelector(".stage")?.scrollIntoView({ block: "start" });
  }, [focusUser, onHistory, compact]);

  const poll = async () => {
    try {
      const r = await fetch("/api/state");
      const s = await r.json();
      const st = seen.current;
      const maxId = Math.max(st.maxId, ...s.messages.map(m => m.id), 0);
      const fresh = s.messages.filter(m => m.id > st.maxId);
      if (!st.first && fresh.length) {
        setFreshIds(new Set(fresh.map(m => m.id)));
      }
      for (const rec of s.recipients) {
        if (st.first || !(rec.user_id in st.byAgent)) st.byAgent[rec.user_id] = maxId;
      }
      st.maxId = maxId;
      // A page opened straight onto an agent that has since gone (a
      // bookmark, or the Mac app reopening where it was) shows the overview.
      if (st.first && location.hash.startsWith("#/agent/")
          && !s.recipients.some(r => r.user_id === decodeURIComponent(location.hash.slice("#/agent/".length))))
        location.replace("#/");
      st.first = false;
      setState(s);
      setConnected(true);
      reportAttention(s.recipients);
    } catch {
      setConnected(false);
    }
  };
  useEffect(() => {
    poll();
    const t = setInterval(poll, POLL_MS);
    const c = setInterval(() => setClock(new Date().toLocaleTimeString()), 1000);
    const onHash = () => setRoute(location.hash);
    const onKey = (e) => {
      if (e.key === "Escape" && !e.defaultPrevented && !e.repeat
          && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)
          && !document.activeElement.isContentEditable) {
        if (rosterOpenRef.current) closeRoster();
      }
      // Alt+H goes home to the overview from any page, even while typing:
      // drafts are saved as they are typed. Matched by physical key, since
      // Option+H types a character on a Mac.
      if (e.code === "KeyH" && e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey
          && !e.isComposing && !document.querySelector(".quick-switch[open]")
          && location.hash !== "#/" && location.hash !== "") {
        e.preventDefault();
        location.hash = "#/";
      }
      // Cmd+Shift+[ / ] (Ctrl+Shift elsewhere) step through the header's
      // views. Browsers keep these keys for their own tabs; the Mac app and
      // an installed app window pass them to the page.
      const modifier = mac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
      const by = e.code === "BracketRight" ? 1 : e.code === "BracketLeft" ? -1 : 0;
      if (by && modifier && e.shiftKey && !e.altKey && !e.isComposing
          && !document.querySelector(".quick-switch[open]")) {
        e.preventDefault();
        location.hash = stepView(location.hash, ["#/", CHATS_ROUTE, ...tabsRef.current.map(tabHash), HISTORY_ROUTE], by);
      }
    };
    addEventListener("hashchange", onHash);
    addEventListener("keydown", onKey);
    return () => {
      clearInterval(t); clearInterval(c);
      removeEventListener("hashchange", onHash);
      removeEventListener("keydown", onKey);
    };
  }, []);

  // messages involving the focused agent count as read
  if (focusUser && seen.current.byAgent[focusUser] !== undefined) {
    seen.current.byAgent[focusUser] = seen.current.maxId;
  }
  const unreadFor = (u) => {
    if (!state || u === focusUser) return false;
    const since = seen.current.byAgent[u] ?? seen.current.maxId;
    return state.messages.some(m =>
      m.id > since && m.sender === u && m.recipient === "owner");
  };

  const header = html`<header class="top">
    <h1 style="cursor:pointer" onClick=${() => { location.hash = "#/"; }}>Buzz</h1>
    <nav class="views" aria-label="views" title=${`Switch views: ${mac ? "⌘⇧[ / ⌘⇧]" : "Ctrl+Shift+[ / ]"}`}>
      <a href="#/" class=${onOverview ? "on" : ""} title=${`Overview (${mac ? "⌥H" : "Alt+H"})`} aria-keyshortcuts="Alt+h">overview</a>
      <a href=${CHATS_ROUTE} class=${onChats ? "on" : ""}>chats</a>
      ${(state?.tabs || []).map(t => html`<a key=${t} href=${tabHash(t)} class=${onTab === t ? "on" : ""}>${t}</a>`)}
      <a href=${HISTORY_ROUTE} class=${onHistory ? "on" : ""}>task history</a>
    </nav>
    <${QuickSwitcher} state=${state} navigate=${(user, previous) => {
      if (location.hash === focusHash(user)) return;
      switchCarry = { composer: !!previous?.closest?.(".thread .composer"), focus: !!document.querySelector(".thread.focused") };
      setMachine(null);
      location.hash = focusHash(user);
    }} />
    <div class="right">
      <span><span class=${`beacon ${connected ? "" : "down"}`}></span>${connected ? "watching" : "server unreachable"}</span>
      <span>${clock}</span>
      ${STANDALONE && html`<button type="button" class="reload" title="Reload the dashboard"
        onClick=${() => location.reload()}>↻ reload</button>`}
    </div>
  </header>`;

  if (!state) return html`${header}<main><div class="stage"><div class="empty">connecting…</div></div></main>`;
  const view = pending.length ? { ...state, messages: [...state.messages, ...pending] } : state;

  // The header and machine bar sit in the left column, so the roster can run
  // the full height of the window beside them.
  return html`<main class=${`dashboard-layout ${rosterOpen ? "roster-open" : ""}`}>
    <div class="main-col">
    ${header}
    ${onOverview && html`<${MachineBar} state=${state} machine=${machine} selectMachine=${setMachine} />`}
    ${!compact && html`<button type="button" ref=${toggleRef} class=${`roster-toggle ${rosterOpen ? "is-open" : ""}`}
      aria-expanded=${rosterOpen} aria-controls="agent-sidebar" onClick=${toggleRoster}
      title=${`Toggle agent sidebar (${rosterShortcut})`} aria-keyshortcuts=${mac ? "Meta+b" : "Control+b"}>
      ${rosterOpen ? "Agents ›" : "‹ Agents"} · ${state.recipients.filter(r => r.pane_alive).length} · ${rosterShortcut}
    </button>`}
    <div class="stage">
      ${focusUser
        ? html`<${FocusView} key=${focusUser} user=${focusUser} state=${view} refresh=${poll} freshIds=${freshIds} unreadFor=${unreadFor} />`
        : onHistory
          ? html`<${HistoryView} state=${state} />`
          : onChats
            ? html`<${ChatsView} state=${state} unreadFor=${unreadFor} />`
            : onTab !== null
              ? html`<${TabView} name=${onTab} tabs=${state.tabs || []} />`
              : html`<${Overview} state=${state} refresh=${poll} machine=${machine} harness=${harness} setHarness=${setHarness} unreadFor=${unreadFor} />`}
    </div>
    </div>
    ${!compact && html`<div id="agent-sidebar" class=${`roster-drawer ${rosterOpen ? "is-open" : ""}`} inert=${!rosterOpen} aria-hidden=${!rosterOpen}>
      <aside class="roster">
        <${AgentsPanel} state=${state} refresh=${poll} machine=${onOverview ? machine : null} harness=${harness} setHarness=${setHarness} unreadFor=${unreadFor}
          storageKey=${SIDEBAR_VIEW_KEY} focusUser=${focusUser} onClose=${closeRoster} />
      </aside>
    </div>`}
  </main>`;
}

render(html`<${App} />`, document.getElementById("app"));
