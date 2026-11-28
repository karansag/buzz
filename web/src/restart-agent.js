import { html } from "htm/preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { errorText, jsonInit } from "./shared.js";

async function restartRequest(user, force, dryRun) {
  const response = await fetch(`/agents/${encodeURIComponent(user)}/restart`, jsonInit("POST", { force, dry_run: dryRun }));
  const body = await response.json().catch(() => null);
  if (response.ok && body) return body;
  return { reason: errorText(body) };
}

const hasPlan = result => result.ok === true && result.status === "planned"
  && typeof result.launch === "string" && result.launch.length > 0;

// The endpoint reports the idle guard as a skipped result. Other skips
// (unverified pane, missing session, etc.) are never forceable.
const canForce = result => result.ok === true && result.status === "skipped"
  && result.forceable === true;

function RestartDialog({ user, initial, onClose }) {
  const dialog = useRef(null);
  const [plan, setPlan] = useState(initial);
  const [force, setForce] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const forceable = canForce(initial);
  const activity = initial.activity ?? "unknown";

  useEffect(() => { dialog.current.showModal(); }, []);

  const changeForce = async event => {
    const checked = event.currentTarget.checked;
    setForce(checked);
    setError("");
    if (!checked || hasPlan(plan)) return;
    setChecking(true);
    try {
      const result = await restartRequest(user, true, true);
      if (hasPlan(result)) setPlan(result);
      else setError(result.reason || "Could not get a restart plan.");
    } catch {
      setError("Could not get a restart plan.");
    } finally {
      setChecking(false);
    }
  };

  return html`<dialog ref=${dialog} class="page-dialog restart-dialog" aria-label=${`Restart ${user}`}
      onClose=${() => onClose(dialog.current.returnValue === "restart", force)}
      onKeyDown=${event => { if (event.key === "Escape" || event.key === "Enter") event.stopPropagation(); }}>
    <form method="dialog">
      <h2>Restart ${user}?</h2>
      <p>Restarts the harness in the same pane and resumes its saved session. Work running in the pane will stop.</p>
      ${forceable && html`
        <p>${activity === "unknown" ? "The hub could not verify that the agent is idle." : `Agent is currently ${activity.replaceAll("_", " ")}.`} Restarting may interrupt an active turn.</p>
        <label class="restart-force"><input type="checkbox" checked=${force}
          disabled=${checking} onChange=${changeForce} /> Force restart</label>
        ${!force && !hasPlan(plan) && html`<p class="restart-hint">Check Force restart to preview the launch.</p>`}`}
      ${checking && html`<p role="status">Checking restart plan…</p>`}
      ${error && html`<p class="restart-error" role="alert">${error}</p>`}
      ${hasPlan(plan) && html`<div>
        <p>${plan.node} · pane ${plan.pane}</p>
        <pre aria-label="Launch command and working directory">${plan.launch}</pre>
      </div>`}
      <div class="page-dialog-actions">
        <button type="submit" value="cancel" class="mini" autofocus>Cancel</button>
        <button type="submit" value="restart" class="act" disabled=${checking || !hasPlan(plan) || (forceable && !force)}>Restart</button>
      </div>
    </form>
  </dialog>`;
}

export function RestartAgentButton({ r, refresh }) {
  const inFlight = useRef(false);
  const [busy, setBusy] = useState("");
  const [review, setReview] = useState(null);
  const [message, setMessage] = useState("");
  const user = r.user_id;

  const preview = async event => {
    if (!r.pane_alive || inFlight.current || review) return;
    event.currentTarget.focus();
    inFlight.current = true;
    setBusy("Checking…");
    setMessage("");
    try {
      const result = await restartRequest(user, false, true);
      if (hasPlan(result) || canForce(result)) setReview(result);
      else setMessage(`Could not plan restart: ${result.reason || "the hub did not return a plan"}.`);
    } catch {
      setMessage("Could not get a restart plan. Try again.");
    } finally {
      inFlight.current = false;
      setBusy("");
    }
  };

  const confirm = async (approved, force) => {
    setReview(null);
    if (!approved || inFlight.current) return;
    inFlight.current = true;
    setBusy("Restarting…");
    try {
      const result = await restartRequest(user, force, false);
      if (result.ok === true && result.status === "restarted") {
        setMessage(`Restarted on ${result.node} in pane ${result.pane}.`);
      } else if (result.status === "skipped") {
        setMessage(`Restart skipped: ${result.reason || "the agent is no longer eligible"}.`);
      } else if (result.status === "unknown" || !result.reason) {
        setMessage(`Restart not confirmed. ${result.reason || "Check the agent's status before retrying."}`);
      } else {
        setMessage(`Could not restart agent: ${result.reason}`);
      }
    } catch {
      setMessage("Restart not confirmed. Check the agent's status before retrying.");
    } finally {
      inFlight.current = false;
      setBusy("");
      refresh();
    }
  };

  return html`<button type="button" class="mini restart-agent" disabled=${!r.pane_alive}
      aria-disabled=${busy || review ? "true" : null} onClick=${preview}>${busy || "restart agent"}</button>
    ${message && html`<span class="agent-action-result" role="status">${message}</span>`}
    ${review && html`<${RestartDialog} user=${user} initial=${review} onClose=${confirm} />`}`;
}
