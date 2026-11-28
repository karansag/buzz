import { html } from "htm/preact";
import { useEffect, useState } from "preact/hooks";

import { spawnOutcome, spawnTarget, unansweredOutcome } from "./outcome.js";
import { jsonInit } from "./shared.js";

const DEFAULT_MODEL = "default";

const machineLabel = (n) => (n.local ? `${n.name} (hub)`
  : n.gone ? `${n.name} (no longer enrolled)`
    : n.connected ? n.name : `${n.name} (not connected)`);

export function SpawnControl({ refresh, nodes }) {
  const [harnesses, setHarnesses] = useState([]);
  const [node, setNode] = useState("");
  const [flavor, setFlavor] = useState("claude");
  const [model, setModel] = useState(DEFAULT_MODEL);
  const [dir, setDir] = useState("");
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
  // A pick that the newly chosen machine does not list falls back to its first.
  const dirs = target.dirs || [];
  const cwd = dirs.includes(dir) ? dir : (dirs[0] || "");
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
    if (cwd) body.cwd = cwd;
    try {
      const r = await fetch("/agents/spawn", jsonInit("POST", body));
      const payload = await r.json().catch(() => null);
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
    <div class="spawn-heading">Spawn agent</div>
    ${(enrolled.length > 1 || node) && html`<select title="machine" value=${node} onChange=${e => pickNode(e.target.value)}>
      ${choices.map(n => html`<option key=${n.name} value=${n.local ? "" : n.name} disabled=${!n.local && !n.connected}>${machineLabel(n)}</option>`)}
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
    ${dirs.length > 0 && html`<select title="start folder" aria-label="start folder" value=${cwd} onChange=${e => setDir(e.target.value)}>
      ${dirs.map(d => html`<option key=${d} value=${d}>${d}</option>`)}
    </select>`}
    <button class="act" type="submit" disabled=${busy || !target.ok}>${busy ? "spawning…" : "spawn agent"}</button>
    ${err && html`<span style="color:var(--alert); font-size:11px">${err}</span>`}
  </form>`;
}
