import { html } from "htm/preact";
import { useEffect, useRef, useState } from "preact/hooks";

import { showNotice } from "./dialogs.js";
import { jsonInit } from "./shared.js";

// For Claude Code, Codex and Pi the model label is a switcher: saving drives
// the harness's own /model command in the agent's pane, for its current
// session only, and the hub reads the result back off the screen. An idle
// agy agent is restarted into its conversation on the new model instead.
// The hub also keeps the label in step when /model is typed in the pane.
// Other harnesses keep a display-only label.
const SWITCHABLE = ["claude", "codex", "pi", "agy"];
const OTHER_MODEL = "\u0000other";

export function ModelLabel({ r, refresh }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [known, setKnown] = useState([]);
  const [busy, setBusy] = useState(false);
  const [other, setOther] = useState(false);
  const inputRef = useRef(null);
  useEffect(() => { if (editing) inputRef.current?.focus(); }, [editing, other]);
  const flavor = (r.flavor || "generic").toLowerCase();
  const start = () => {
    setValue(r.model || "");
    setOther(false);
    setEditing(true);
    fetch("/api/spawn-options")
      .then(res => res.json())
      .then(d => setKnown(((d.harnesses || []).find(h => h.flavor === flavor) || {}).models || []))
      .catch(() => {});
  };
  const switchable = SWITCHABLE.includes(flavor);
  const save = async () => {
    if (busy) return;
    if (value.trim() === (r.model || "")) { setEditing(false); return; }
    if (switchable && !value.trim()) return;
    setBusy(true);
    const path = switchable ? "switch-model" : "model";
    const res = await fetch(`/agents/${encodeURIComponent(r.user_id)}/${path}`, jsonInit("POST", { model: value.trim() }))
      .catch(() => null);
    setBusy(false);
    if (!res || !res.ok) {
      const body = res ? await res.json().catch(() => ({})) : {};
      const why = body.detail?.error || (res ? `error ${res.status}` : "no answer from the hub");
      const screen = body.detail?.screen ? `\n\nLast screen:\n${body.detail.screen}` : "";
      await showNotice(switchable
        ? `Could not switch ${r.user_id} to ${value.trim()}: ${why}${screen}`
        : `Could not update the model label for ${r.user_id}: ${why}`);
      return;
    }
    setEditing(false);
    refresh();
  };
  if (!editing) {
    return html`<button type="button" class="model-label" onClick=${start}
      title=${switchable
        ? "Switch this agent's model for its current session (drives /model in its pane)."
        : "Edit the model label. Display only: switch the real model in the agent's pane first."}>
      ${r.model ? html`<b>${r.model}</b>` : html`<span class="unset">set model</span>`} <span class="pen">✎</span>
    </button>`;
  }
  // A real <select> of the known models: a datalist arrow did nothing on
  // desktop once the box held a value, and mobile hid it. "other…" opens a
  // text box for a model the list does not offer.
  const options = [...new Set([...(r.model ? [r.model] : []), ...known])];
  const typing = other || options.length === 0;
  const keys = e => {
    if (e.key === "Enter") { e.preventDefault(); save(); }
    if (e.key === "Escape") setEditing(false);
  };
  return html`<span class="model-edit">
    ${typing
      ? html`<input type="text" value=${value} placeholder="e.g. claude-opus-4-7"
          aria-label=${`Model for ${r.user_id}`} disabled=${busy} ref=${inputRef}
          onInput=${e => setValue(e.target.value)} onKeyDown=${keys} />`
      : html`<select value=${value} aria-label=${`Model for ${r.user_id}`} disabled=${busy} ref=${inputRef}
          onChange=${e => e.target.value === OTHER_MODEL ? (setOther(true), setValue("")) : setValue(e.target.value)}
          onKeyDown=${keys}>
          ${!value && html`<option value="" disabled>pick a model</option>`}
          ${options.map(m => html`<option key=${m} value=${m}>${m}</option>`)}
          <option value=${OTHER_MODEL}>other…</option>
        </select>`}
    <button type="button" class="mini" disabled=${busy} onClick=${save}>${busy
      ? (switchable ? "switching…" : "saving…")
      : (switchable ? "switch" : "save")}</button>
    <button type="button" class="mini" disabled=${busy} onClick=${() => setEditing(false)}>cancel</button>
  </span>`;
}
