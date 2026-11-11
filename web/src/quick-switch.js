import { agentPreview } from "./agent-preview.js";
import { html } from "htm/preact";
import { useLayoutEffect, useRef, useState } from "preact/hooks";
import { Bee } from "./shared.js";
import { Crown, queenSuffix } from "./queen.js";

export function switchOptions(state, mode, query) {
  if (!state) return [];
  const teams = state.teams || [];
  const agents = state.recipients;
  let options;
  if (mode === "teams") {
    options = teams.map(team => {
      const members = agents.filter(a => a.team_id === team.id).sort((a, b) =>
        Number(b.pane_alive) - Number(a.pane_alive)
        || Number(b.user_id === team.queen) - Number(a.user_id === team.queen)
        || a.user_id.localeCompare(b.user_id));
      const target = members[0];
      // A team row names the team, not the agent it opens, so its queen is
      // marked in the detail line rather than with a crown beside the name.
      return { id: `team-${team.id}`, name: team.name, target,
        detail: target ? `${members.filter(a => a.pane_alive).length} live · opens ${target.user_id}${queenSuffix(teams, target.user_id)}${target.pane_alive ? "" : " (offline)"}` : "No registered agents",
        search: [team.name, ...members.map(a => a.user_id)].join(" ") };
    });
  } else {
    options = agents.map(a => {
      const team = teams.find(t => t.id === a.team_id)?.name || "no team";
      const summary = agentPreview(a);
      return { id: `agent-${a.user_id}`, name: a.user_id, target: a, summary,
        detail: `${team} · ${a.node || "unknown machine"} · ${a.pane_alive ? (a.activity?.status || "online").replaceAll("_", " ") : "offline"}`,
        search: [a.user_id, team, a.node, a.flavor, a.model, summary].filter(Boolean).join(" ") };
    });
  }
  const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  return options.filter(o => words.every(w => o.search.toLowerCase().includes(w)))
    .sort((a, b) => Number(!a.target) - Number(!b.target)
      || Number(!a.target?.pane_alive) - Number(!b.target?.pane_alive)
      || a.name.localeCompare(b.name));
}

export function QuickSwitcher({ state, navigate }) {
  const [mode, setMode] = useState(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);
  const dialog = useRef(null), input = useRef(null), previous = useRef(null);
  const mac = /Mac|iPhone|iPad/.test(navigator.platform);
  const shortcut = mac ? "⌘" : "Ctrl+";
  const open = next => {
    if (!state) return;
    if (!dialog.current?.open) previous.current = document.activeElement;
    setQuery(""); setSelected(null); setMode(next);
  };
  const close = () => { dialog.current?.close(); setMode(null); };
  useLayoutEffect(() => {
    const onKey = e => {
      const platformModifier = mac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
      if (e.isComposing || e.altKey || !platformModifier || e.code !== "KeyK") return;
      e.preventDefault(); e.stopImmediatePropagation();
      if (!e.repeat) open(e.shiftKey ? "teams" : "agents");
    };
    addEventListener("keydown", onKey, true);
    return () => removeEventListener("keydown", onKey, true);
  });
  useLayoutEffect(() => {
    if (mode) { if (!dialog.current.open) dialog.current.showModal(); input.current?.focus(); }
  }, [mode]);
  const options = switchOptions(state, mode, query);
  const enabled = options.filter(o => o.target);
  const current = enabled.find(o => o.id === selected) || enabled[0];
  useLayoutEffect(() => {
    if (mode && current) document.getElementById(`switch-${current.id}`)?.scrollIntoView({ block: "nearest" });
  }, [mode, current?.id]);
  const choose = option => {
    if (!option?.target) return;
    close();
    navigate(option.target.user_id, previous.current);
  };
  const onKey = e => {
    e.stopPropagation();
    if (e.isComposing) return;
    if (e.key === "Escape") { e.preventDefault(); close(); }
    if (["ArrowDown", "ArrowUp"].includes(e.key)) {
      e.preventDefault();
      if (enabled.length) {
        const index = enabled.findIndex(o => o.id === current?.id);
        setSelected(enabled[(index + (e.key === "ArrowDown" ? 1 : -1) + enabled.length) % enabled.length].id);
      }
    }
    if (e.key === "Enter" && e.target === input.current) { e.preventDefault(); choose(current); }
  };
  return html`<div class="quick-switch-launchers">
    <button type="button" class="mini" disabled=${!state} onClick=${() => open("teams")} title=${`Switch teams (${shortcut}Shift+K)`}>teams <kbd>${shortcut}⇧K</kbd></button>
    <button type="button" class="mini" disabled=${!state} onClick=${() => open("agents")} title=${`Switch agents (${shortcut}K)`}>agents <kbd>${shortcut}K</kbd></button>
    <dialog class="quick-switch" ref=${dialog} aria-labelledby="switch-title" onKeyDown=${onKey}
      onCancel=${e => { e.preventDefault(); close(); }}>
      <div class="quick-switch-head"><h2 id="switch-title">${mode === "teams" ? "Switch team" : "Switch agent"}</h2>
        <button type="button" class="mini" onClick=${close}>close</button></div>
      <input ref=${input} type="search" aria-label=${mode === "teams" ? "Find team" : "Find agent"}
        role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls="switch-results"
        aria-activedescendant=${current ? `switch-${current.id}` : undefined}
        placeholder=${mode === "teams" ? "Search teams…" : "Search name, team, machine, harness, note, or status…"}
        value=${query} onInput=${e => { setQuery(e.target.value); setSelected(null); }} />
      <div id="switch-results" role="listbox" aria-label="Matches" class="quick-switch-results">
        ${options.map(o => html`<div key=${o.id} id=${`switch-${o.id}`} role="option" aria-selected=${current?.id === o.id}
          aria-disabled=${!o.target} class=${`quick-switch-option ${current?.id === o.id ? "selected" : ""}`}
          onClick=${() => choose(o)}>
          ${o.target && html`<${Bee} node=${o.target.node} flavor=${o.target.flavor} size="small" working=${o.target.activity?.status === "working"} />`}
          <span><b>${o.name}</b>${mode === "agents" && html`<${Crown} teams=${state.teams} user=${o.target?.user_id} word=${true} />`}<small>${o.detail}</small>
            ${o.summary && html`<small class="quick-switch-summary" title=${o.summary}>${o.summary}</small>`}</span>
        </div>`)}
        ${!options.length && html`<p class="empty">No matches.</p>`}
      </div>
      <p class="quick-switch-help">↑ ↓ select · Enter open · Esc close</p>
    </dialog>
  </div>`;
}
