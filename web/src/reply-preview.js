import { html } from "htm/preact";
import { useState } from "preact/hooks";
import { replySnippet } from "./replies.js";
import { renderMarkdown } from "./markdown.js";
import { AttachmentList } from "./attachments.js";
import { shellNewlines } from "./newlines.js";

export function ReplyPreview({ message, messages }) {
  const id = message.reply_to;
  const [original, setOriginal] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(false);
  if (!id) return null;
  const preview = messages.find(m => m.id === id) || original || message.reply_preview;
  const open = async (event) => {
    const quote = event.currentTarget;
    // A pinned reply opens its quote in the dialog, keeping the chat in place.
    const thread = quote.closest("dialog") ? null : quote.closest(".thread, .agent-talk-thread");
    const target = thread?.querySelector(`[data-message-id="${id}"]`);
    if (target) {
      target.scrollIntoView({ block: "center", behavior: "instant" });
      target.focus({ preventScroll: true });
      target.classList.remove("reply-highlight");
      void target.offsetWidth;
      target.classList.add("reply-highlight");
      return;
    }
    if (original) { setShow(value => !value); return; }
    const loaded = messages.find(m => m.id === id);
    if (loaded) { setOriginal(loaded); setShow(true); return; }
    setBusy(true); setError("");
    try {
      const response = await fetch(`/messages?id=${id}`);
      if (!response.ok) throw Error("Original message is no longer available.");
      const body = await response.json();
      const found = body.messages?.find(m => m.id === id);
      if (!found) throw Error("Original message is no longer available.");
      setOriginal(found); setShow(true);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };
  return html`<div class="reply-reference">
    <button type="button" class="reply-quote" onClick=${open} disabled=${busy}
      aria-label=${`Show original message ${id}`} aria-expanded=${show}>
      <strong>${preview?.sender || `message #${id}`}</strong>
      <span>${busy ? "loading original…" : preview ? replySnippet(preview) : "show original message"}</span>
    </button>
    ${show && original && html`<div class="reply-original" tabindex="0">
      <strong>${original.sender} · message #${id}</strong>
      <div class="md" dangerouslySetInnerHTML=${{__html: renderMarkdown(shellNewlines(original.content))}} />
      <${AttachmentList} files=${original.attachments} />
    </div>`}
    ${error && html`<span class="reply-error" role="alert">${error}</span>`}
  </div>`;
}
