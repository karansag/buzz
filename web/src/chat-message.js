// The conversation and the expanded pin use the same message bubble.
import { html } from "htm/preact";
import { AttachmentLink } from "./attachments.js";
import { highlightSearch } from "./conversation-search.js";
import { renderMarkdown } from "./markdown.js";
import { shellNewlines } from "./newlines.js";
import { ReplyPreview } from "./reply-preview.js";
import { disp, rel } from "./shared.js";

export function ChatMessage({
  m, now, messages, right, pinned, fresh, words = [],
  historyId, onContextMenu, children,
}) {
  return html`<div data-message-id=${historyId} tabindex=${historyId === undefined ? null : "-1"}
      onAnimationEnd=${e => e.currentTarget.classList.remove("reply-highlight")}
      onContextMenu=${onContextMenu} class=${[
        "msg", right ? "right" : "", fresh ? "fresh" : "",
        m.status === "failed" ? "failed" : m.status === "unknown" ? "unknown" : "",
        m.sender === "owner" ? "from-owner" : "", m.pending ? "pending" : "",
      ].join(" ")}>
    <div class="bubble">
      <${ReplyPreview} message=${m} messages=${messages} />
      ${m.content && html`<div class="md" dangerouslySetInnerHTML=${{
        __html: highlightSearch(renderMarkdown(shellNewlines(m.content)), words),
      }} />`}
      ${m.attachments?.length > 0 && html`<div class=${`msg-images ${m.content ? "" : "only"}`}>
        ${m.attachments.map(name => html`<${AttachmentLink} key=${name} name=${name} />`)}
      </div>`}
    </div>
    <div class="tag">${pinned && html`<span class="pin-mark" role="img" aria-label="pinned" title="Pinned">📌</span> `}
      ${!!m.notify && html`<span class="notification-mark" role="img" aria-label="notification" title="Agent notification">🔔</span> `}
      ${disp(m.sender)}${m.context && html` · <span class="ctx">${m.context}</span>`} · ${m.pending ? "sending…" : rel(m.ts, now)}
      ${m.status === "failed" && html` · <span class="ctx">undelivered${m.delivery_error ? `: ${m.delivery_error}` : ""}</span>`}
      ${m.status === "unknown" && html` · <span class="ctx">outcome unknown${m.delivery_error ? `: ${m.delivery_error}` : ""}</span>`}
      ${children}
    </div>
  </div>`;
}
