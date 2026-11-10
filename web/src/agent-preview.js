// Keep read-only previews consistent with the detail page's current status.
export function agentPreview(agent) {
  const note = (agent.owner_note || "").trim();
  if (note) return `📌 note: ${note}`;
  return (agent.summaries || []).find(s => s.source !== "owner")?.text || "";
}
