// Pinned messages: the owner pins a message from its menu. A chat shows its
// pins as a thin strip above the messages; a pin opens in its own dialog,
// so the chat keeps its place. The chats page lists every pin, and a pin
// there goes to the message in its chat.
import { html } from "htm/preact";
import { useEffect, useRef } from "preact/hooks";
import { disp, jsonInit, pairKey, rel } from "./shared.js";
import { agentHash } from "./agent-route.js";
import { ChatMessage } from "./chat-message.js";
import { showNotice } from "./dialogs.js";

export async function setPinned(id, pinned, refresh) {
  try {
    const r = await fetch(`/api/messages/${id}/pin`, jsonInit("POST", { pinned }));
    if (!r.ok) throw new Error(String(r.status));
  } catch {
    showNotice(pinned ? "Could not pin the message. Try again." : "Could not unpin the message. Try again.");
    return;
  }
  refresh?.();
}

// One line of plain text: markdown marks (**, `, #, >) dropped.
const flat = (text, width) => {
  const one = (text || "").replace(/[*`~]+|^#+\s|^>\s?/gm, "").replace(/\s+/g, " ").trim();
  return one.length > width ? `${one.slice(0, width)}…` : one;
};

// The chat a pin belongs to: the agent's page, for the owner's own chats;
// otherwise the recipient's page, which shows its chats with other agents.
const pinPage = (m) => (m.sender === "owner" ? m.recipient : m.recipient === "owner" ? m.sender : m.recipient);
export const pinHref = (m) => agentHash(pinPage(m), m.id);

export const pinsOf = (pins, a, b) => (pins || []).filter(m => pairKey(m.sender, m.recipient) === pairKey(a, b));

export function PinStrip({ pins, open }) {
  if (!pins.length) return null;
  return html`<div class="pin-strip" role="list" aria-label="Pinned messages">
    ${pins.map(m => html`<button type="button" role="listitem" key=${m.id} class="pin-chip" onClick=${() => open(m)}
        title="Open the pinned message">
      <span aria-hidden="true">📌</span> <b>${disp(m.sender)}</b> <span class="pin-text">${flat(m.content, 140) || "(attachment)"}</span>
    </button>`)}
  </div>`;
}

export function PinDialog({ m, now, close, refresh, messages, right, inChat = null }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement;
    dialog.showModal();
    return () => { if (previous?.isConnected) previous.focus(); };
  }, []);
  // Esc is the dialog's: it must not also leave focus mode or close a panel.
  const onKey = (e) => { if (e.key === "Escape") e.stopPropagation(); };
  return html`<dialog ref=${ref} class="page-dialog pin-dialog" aria-label="Pinned message"
      onClose=${close} onKeyDown=${onKey} onClick=${e => { if (e.target === ref.current) ref.current.close(); }}>
    <div class="pin-dialog-body" tabindex="0">
      <${ChatMessage} m=${m} now=${now} messages=${messages} right=${right} pinned=${true} />
    </div>
    <div class="page-dialog-actions pin-dialog-actions">
      <button type="button" class="mini" onClick=${() => { setPinned(m.id, false, refresh); ref.current.close(); }}>unpin</button>
      ${inChat && html`<button type="button" class="mini" onClick=${() => { ref.current.close(); inChat(m); }}>show in chat</button>`}
      <button type="button" class="act" autofocus onClick=${() => ref.current.close()}>close</button>
    </div>
  </dialog>`;
}

export function PinnedList({ pins, now, refresh }) {
  if (!pins?.length) return null;
  return html`<section class="pinned-list" aria-label="Pinned messages">
    <h2>pinned <span class="count">· ${pins.length}</span></h2>
    <ul>
      ${pins.map(m => html`<li key=${m.id}>
        <a href=${pinHref(m)} title="Go to this message in its chat">
          <span class="pin-who"><span aria-hidden="true">📌</span> ${disp(m.sender)} <span class="swap">→</span> ${disp(m.recipient)} <span class="age">· ${rel(m.ts, now)}</span></span>
          <span class="pin-text">${flat(m.content, 240) || "(attachment)"}</span>
        </a>
        <button type="button" class="mini" aria-label=${`Unpin message ${m.id}`} onClick=${() => setPinned(m.id, false, refresh)}>unpin</button>
      </li>`)}
    </ul>
  </section>`;
}
