import { html } from "htm/preact";
import { useState } from "preact/hooks";

export async function trashTask(task) {
  if (!confirm(`Permanently trash task #${task.id}: ${task.title}? This cannot be undone. Agent conversations and working files will remain.`)) return false;
  const response = await fetch(`/tasks/${task.id}`, { method: "DELETE" });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail?.error || "Could not trash task.");
  return true;
}

export function TaskTrash({ task, refresh, onDeleted }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const remove = async () => {
    setBusy(true); setError("");
    try {
      if (!await trashTask(task)) return;
      onDeleted?.(); refresh();
    } catch (err) {
      setError(`${err.message} Refresh to check the task before retrying.`);
    } finally { setBusy(false); }
  };
  return html`<span class="task-trash"><button type="button" class="mini danger" disabled=${busy}
    title=${`Permanently trash task #${task.id}`} onClick=${remove}>${busy ? "Trashing…" : "⌫ Trash"}</button>
    ${error && html`<span role="alert" class="tnote-err">${error}</span>`}</span>`;
}
