// No imports, so `node --test web/test` can exercise it without a browser.

// The agent page's context chip, from the harness's own footer figure
// ({percent, window}, see agent_swarm/context_usage.py). Null when the screen
// shows none, so the page says nothing rather than guessing.
export function contextChip(context) {
  if (!context) return null;
  const { percent, window } = context;
  const span = window ? ` of a ${window}-token window` : "";
  if (typeof percent !== "number") {
    return { text: "context ?", level: "normal", title: `The harness shows no context figure right now${window ? ` (window ${window})` : ""}` };
  }
  const shown = Number.isInteger(percent) ? String(percent) : percent.toFixed(1);
  return {
    text: `context ${shown}%`,
    level: percent >= 90 ? "critical" : percent >= 70 ? "warn" : "normal",
    title: `Context window ${shown}% full${span}, as the harness's own footer shows it`,
  };
}
