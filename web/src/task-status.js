import { html } from "htm/preact";
import { useState } from "preact/hooks";
import { patchTask } from "./shared.js";

// One completion action across the board, agent page, and honeycomb detail.
// The server requires a verification note; ask for it only when the task lacks one.
export function TaskStatusActions({ task, refresh }) {
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState(task.note || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const change = async patch => {
    setBusy(true);
    setError("");
    try {
      const result = await patchTask(task.id, patch);
      if (!result.ok) { setError(result.error); return; }
      setEditing(false);
      await refresh();
    } catch {
      setError("Could not update the task. Try again.");
    } finally { setBusy(false); }
  };
  const complete = () => {
    const verification = (editing ? note : task.note || "").trim();
    if (!verification) { setEditing(true); return; }
    change({ status: "done", note: verification });
  };

  return html`<div class=${`task-status-actions ${editing ? "editing" : ""}`}>
    ${task.status === "done"
      ? html`<button type="button" class="mini" disabled=${busy}
          onClick=${() => change({ status: task.assignee || task.team_id ? "picked_up" : "open" })}>reopen</button>`
      : html`${task.status === "open" && html`<button type="button" class="mini"
          disabled=${busy || !(task.assignee || task.team_id)}
          title=${task.assignee || task.team_id ? "Start work on this task" : "Assign this task first"}
          onClick=${() => change({ status: "picked_up" })}>start work</button>`}
        <button type="button" class="mini" disabled=${busy || (editing && !note.trim())}
          onClick=${complete}>${busy ? "updating…" : "complete task"}</button>`}
    ${editing && task.status !== "done" && html`<div class="task-verification">
      <label>Verification note <span aria-hidden="true">*</span>
        <textarea rows="3" value=${note} autofocus
          placeholder="How to use or verify the result, and where to look."
          onInput=${e => setNote(e.target.value)}></textarea>
      </label>
      <button type="button" class="mini" disabled=${busy}
        onClick=${() => { setEditing(false); setError(""); }}>cancel</button>
    </div>`}
    ${error && html`<span class="task-action-error" role="alert">${error}</span>`}
  </div>`;
}
