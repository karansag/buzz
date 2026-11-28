import { html } from "htm/preact";
import { useState } from "preact/hooks";
import { jsonInit } from "./shared.js";

export function OwnerNote({ agent, refresh }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async value => {
    setBusy(true); setError("");
    try {
      const response = await fetch(`/agents/${encodeURIComponent(agent.user_id)}/owner-note`, jsonInit("PUT", { text: value }));
      if (!response.ok) {
        const body = await response.json();
        throw new Error(body.detail?.error || "Could not save note.");
      }
      setEditing(false); refresh?.();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };
  return html`<div class="owner-note" aria-label=${`Owner note for ${agent.user_id}`}>
    ${editing ? html`<form onSubmit=${e => { e.preventDefault(); save(text); }}>
      <label>Your note<textarea aria-label=${`Your note for ${agent.user_id}`} maxLength="1000" rows="2"
        value=${text} disabled=${busy} onInput=${e => setText(e.target.value)} /></label>
      <div class="owner-note-actions"><button type="submit" disabled=${busy}>save note</button>
        <button type="button" disabled=${busy} onClick=${() => { setEditing(false); setError(""); }}>cancel</button>
        ${agent.owner_note && html`<button type="button" disabled=${busy} onClick=${() => save("")}>clear note</button>`}</div>
    </form>` : html`<button type="button" class="owner-note-edit" aria-label=${`${agent.owner_note ? "Edit" : "Add"} owner note for ${agent.user_id}`}
      onClick=${() => { setText(agent.owner_note || ""); setError(""); setEditing(true); }}>
      ${agent.owner_note ? `📌 you: ${agent.owner_note}` : "+ your note"}</button>`}
    ${error && html`<span role="alert">${error}</span>`}
  </div>`;
}
