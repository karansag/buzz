// Search words and their <mark> highlighting, shared by the search views.
import { html } from "htm/preact";

export const searchWords = (query) => query.toLowerCase().split(/\s+/).filter(Boolean);

export const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// One pattern that matches any of the words, or null when there are none.
export const wordsRe = (words) => (words.length ? new RegExp(`(${words.map(escapeRe).join("|")})`, "gi") : null);

// Wrap each match in <mark>. `re` has one capture group, so split() puts the
// matches at the odd indexes.
export function hl(text, re) {
  if (!re || !text) return text;
  return text.split(re).map((part, i) => (i % 2 ? html`<mark>${part}</mark>` : part));
}
