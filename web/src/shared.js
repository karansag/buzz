import { html } from "htm/preact";
import { machineColor, machineName } from "./machines.js";
import { agentHash } from "./agent-route.js";

export const POLL_MS = 2000;
export const PEEK_MS = 2000;
export const JSONH = { "content-type": "application/json" };

export function stopAgentPrompt(agent) {
  return `Stop ${agent.user_id} on ${machineName(agent.node)}? This kills its tmux pane and ends the running session. Messages and tasks are kept, and "resume agent" on its page brings the session back later.`;
}

export const FLAVOR_ICON = { claude: "✳", codex: "◇", pi: "π", hermes: "☿", generic: "▪" };

// Harness glyphs identify the runtime; machine colors live in machines.js.
export const HARNESSES = Object.freeze({
  claude:  { key: "claude",  label: "Claude",  color: "#d8905f", mark: "✳" },
  codex:   { key: "codex",   label: "Codex",   color: "#56b4e9", mark: "◇" },
  pi:      { key: "pi",      label: "Pi",      color: "#3cb44b", mark: "π" },
  hermes:  { key: "hermes",  label: "Hermes",  color: "#e5c14f", mark: "☿" },
  generic: { key: "generic", label: "Generic", color: "#9aa1a8", mark: "▪" },
});

export function harnessStyle(flavor) {
  return HARNESSES[String(flavor || "generic").toLowerCase()] || HARNESSES.generic;
}

// The harnesses a filter or legend offers: every spawnable one, plus
// generic only while a generic agent is live.
export function harnessChoices(recipients = []) {
  const generic = recipients.some(r => r.pane_alive && harnessStyle(r.flavor).key === "generic");
  return Object.values(HARNESSES).filter(h => h.key !== "generic" || generic);
}

// The machine and harness filters together; null means "all".
export function agentShown(r, machine, harness) {
  return (machine === null || machineName(r.node) === machine)
    && (harness === null || harnessStyle(r.flavor).key === harness);
}

// One small icon button per harness. Clicking the active one clears it.
export function HarnessFilter({ recipients, harness, setHarness }) {
  return html`<span class="harness-filter" role="group" aria-label="Filter agents by harness">
    ${harnessChoices(recipients).map(h => html`<button key=${h.key} type="button" class="harness-swatch"
      style=${`--harness:${h.color}`} aria-pressed=${harness === h.key} aria-label=${`Only ${h.label} agents`}
      title=${harness === h.key ? `Showing only ${h.label} agents. Click to show all.` : `Show only ${h.label} agents`}
      onClick=${() => setHarness(harness === h.key ? null : h.key)}>${h.mark}</button>`)}
  </span>`;
}

// Activity state -> dot class, display word, and color. One color per
// state, matching the --state-* CSS custom properties.
export const WORKING_HALO = { color: "#9be879", fill: "rgba(155,232,121,.14)" };

export const STATE = {
  working:         { cls: "working",   word: "working",         color: "var(--state-working)" },
  needs_attention: { cls: "attention", word: "needs attention", color: "var(--state-attention)" },
  idle:            { cls: "idle",      word: "idle",            color: "var(--state-idle)" },
  unknown:         { cls: "unknown",   word: "unknown",         color: "var(--state-unknown)" },
  stopped:         { cls: "stopped",   word: "stopped",         color: "var(--state-stopped)" },
};
// Prefer the monitor's classification; fall back to raw liveness before it
// has data (a dead pane still reads "stopped", a live one "unknown").
export function agentStatus(r) {
  if (!r.pane_alive) return "stopped";
  const s = r.activity && r.activity.status;
  if (s && s !== "unknown") return s;
  return "unknown";
}
export const ANIMAL_EMOJI = {
  otter: "\u{1F9A6}", badger: "\u{1F9A1}", panda: "\u{1F43C}", raccoon: "\u{1F99D}",
  hedgehog: "\u{1F994}", viper: "\u{1F40D}", gecko: "\u{1F98E}", newt: "\u{1F98E}",
  salamander: "\u{1F98E}", capybara: "\u{1F9AB}", manatee: "\u{1F9AD}", lemur: "\u{1F412}",
  kestrel: "\u{1F985}", magpie: "\u{1F426}\u{200D}⬛", ibis: "\u{1F9A9}", heron: "\u{1FABF}",
  puffin: "\u{1F427}", narwhal: "\u{1F433}", axolotl: "\u{1F41F}", quokka: "\u{1F428}",
  wombat: "\u{1F428}", dormouse: "\u{1F401}", shrew: "\u{1F401}", fennec: "\u{1F98A}",
  mongoose: "\u{1F9A6}", stoat: "\u{1F9A6}", marten: "\u{1F9A6}", ferret: "\u{1F9A6}",
  ocelot: "\u{1F406}", pangolin: "\u{1F98E}", tapir: "\u{1F417}", civet: "\u{1F431}",
};

export function hue(name) {
  let h = 0;
  for (const c of name) h = (h * 31 + c.codePointAt(0)) % 360;
  return h;
}
export function rel(ts, now) {
  const d = Math.max(0, now - ts);
  if (d < 50) return "just now";
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}
// Where a status line came from: the agent said it, or its harness put it in
// the tmux pane title.
export const SUMMARY_SOURCE = { owner: "noted by you", agent: "said by the agent", title: "from its pane title" };

export function currentTask(tasks, user) {
  const mine = (tasks || []).filter(t => t.assignee === user && t.status !== "done");
  if (!mine.length) return null;
  const picked = mine.filter(t => t.status === "picked_up");
  return (picked.length ? picked : mine).sort((a, b) => b.updated_at - a.updated_at)[0];
}
export function pairKey(a, b) { return [a, b].sort().join(" "); }
export const disp = (u) => u === "owner" ? html`<span class="owner-name">owner</span>` : u;
export const focusHash = (u) => agentHash(u);

export async function patchTask(id, patch) {
  try {
    const r = await fetch(`/tasks/${id}`, { method: "PATCH", headers: JSONH, body: JSON.stringify(patch) });
    if (r.ok) return { ok: true };
    const body = await r.json().catch(() => null);
    return { ok: false, error: body?.detail?.error || `request failed (${r.status})` };
  } catch {
    return { ok: false, error: "Update not confirmed. Refresh the board before retrying." };
  }
}

export function Avatar({ name, size }) {
  const base = name.replace(/-\d+$/, "");
  const emoji = ANIMAL_EMOJI[base];
  return html`<div class=${`hex ${size || ""}`} style=${`--hue: hsl(${hue(name)} 42% 58%)`}>
    ${emoji || html`<span class="mono2">${base.slice(0, 2)}</span>`}
  </div>`;
}

export function MachineBadge({ node }) {
  return html`<span class="machine-badge" style=${`--machine:${machineColor(node)}`} title=${`Machine: ${machineName(node)}`}><span class="machine-mark" aria-hidden="true"></span>${machineName(node)}</span>`;
}

// The bee flies to the right: head at x=44, tail at x=7. Both wings are drawn
// tilted back over the abdomen, so their outer ends point away from the head.
export function Bee({ node, flavor, size = "", working = false }) {
  const harness = harnessStyle(flavor);
  return html`<svg class=${`agent-bee ${size}`} style=${`--machine:${machineColor(node)}`} viewBox="0 0 56 42" role="img" aria-label=${`${machineName(node)} machine, ${harness.label} harness${working ? ", working" : ""}`}>
    <title>${harness.label} harness: ${harness.mark} and stripes · ${machineName(node)}: body and border</title>
    ${working && html`<g class="bee-working-halo" style=${`--working:${WORKING_HALO.color}`}>
      <circle cx="27" cy="21" r="28" fill=${WORKING_HALO.fill} stroke=${WORKING_HALO.color} stroke-width="2.5" />
    </g>`}
    <ellipse cx="23" cy="10" rx="11" ry="6" fill="#f0e6d2" opacity=".65" transform="rotate(25 23 10)" />
    <ellipse cx="23" cy="32" rx="11" ry="6" fill="#f0e6d2" opacity=".65" transform="rotate(-25 23 32)" />
    <ellipse cx="26" cy="21" rx="19" ry="10" fill=${machineColor(node)} />
    <path d="M19 12v18M29 11v20" stroke="#16120c" stroke-width="7" />
    <path d="M19 12v18M29 11v20" stroke=${harness.color} stroke-width="4" />
    <circle cx="44" cy="21" r="6" fill="#16120c" /><circle cx="46" cy="19" r="1.3" fill="#f0e6d2" />
  </svg>`;
}
