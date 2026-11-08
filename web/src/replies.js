export function replySnippet(message, limit = 100) {
  const text = (message.content || "").replace(/\s+/g, " ").trim() || "(files)";
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}
