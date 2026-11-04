// No imports, so `node --test web/test` can exercise it without a browser.

// Agents often run `buzz send --message "first\n\nsecond"`. Inside
// double quotes the shell keeps \n as two characters, so the message has no
// line breaks at all, only literal backslash-n. Such a message is shown with
// its \n as line breaks. A message that already has real line breaks used
// any \n on purpose (a prompt template, a shell command) and is left alone,
// as is anything inside `backticks`. Display only: the stored text and what
// agents receive are unchanged.
export function shellNewlines(text) {
  if (!text || text.includes("\n") || !text.includes("\\n")) return text;
  return text
    .split(/(`[^`]*`)/)
    .map((part, i) => (i % 2 ? part : part.replace(/(?<!\\)\\n/g, "\n")))
    .join("");
}
