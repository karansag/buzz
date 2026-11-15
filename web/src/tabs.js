import { html } from "htm/preact";

// Keys pressed inside the page would otherwise never reach the dashboard,
// so shortcuts with a modifier (Alt+H, Alt+T, Cmd/Ctrl+K, Cmd/Ctrl+B) are passed up.
function forwardShortcuts(frame) {
  let win;
  try { win = frame.contentWindow; win.document; } catch { return; } // another origin
  win.addEventListener("keydown", e => {
    if (!(e.altKey || e.ctrlKey || e.metaKey)) return;
    const copy = new KeyboardEvent("keydown", {
      key: e.key, code: e.code, altKey: e.altKey, ctrlKey: e.ctrlKey,
      metaKey: e.metaKey, shiftKey: e.shiftKey, repeat: e.repeat, cancelable: true,
    });
    if (!window.dispatchEvent(copy)) e.preventDefault();
  });
}

export function TabView({ name, tabs }) {
  if (!tabs.includes(name)) {
    return html`<div class="empty">No tab named <b>${name}</b>. Tabs come from the hub's
      <code>AGENT_SWARM_TABS</code> setting, e.g. <code>usage=http://127.0.0.1:8531</code>.</div>`;
  }
  const src = `/tabs/${encodeURIComponent(name)}/`;
  return html`<section class="tab-view">
    <div class="tab-bar"><h2>${name}</h2><a class="mini" href=${src} target="_blank" rel="noopener">open alone ↗</a></div>
    <iframe key=${name} class="tab-frame" src=${src} title=${name} onLoad=${e => forwardShortcuts(e.currentTarget)}></iframe>
  </section>`;
}
