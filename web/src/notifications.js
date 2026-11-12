// Explicit notifications are messages, so polling and history use the same IDs.
// Seed on first snapshot: opening/reloading Buzz must not replay old alerts.
export function notificationReporter({ invoke, Notification: Notice = globalThis.Notification,
  document: doc = globalThis.document, open = agent => {
    globalThis.focus();
    location.hash = `#/agent/${encodeURIComponent(agent)}`;
  } } = {}) {
  let cursor = null;
  const pending = new Map();
  return messages => {
    const newest = Math.max(0, ...messages.map(m => m.id));
    if (cursor === null) { cursor = newest; return; }
    for (const m of messages) {
      if (m.id > cursor && m.notify && m.recipient === "owner") pending.set(m.id, m);
    }
    cursor = Math.max(cursor, newest);
    for (const [id, m] of pending) {
      pending.delete(id);
      if (invoke) {
        Promise.resolve().then(() => invoke("agent_notification", {
          id, agent: m.sender, body: m.content,
        })).catch(() => pending.set(id, m));
      } else if (doc?.hidden && Notice?.permission === "granted") {
        try {
          const notice = new Notice(m.sender, { body: m.content, tag: `buzz-message-${id}` });
          notice.onclick = () => { notice.close(); open(m.sender); };
        } catch { /* Unsupported browser surfaces still show the message and bell. */ }
      }
    }
  };
}
