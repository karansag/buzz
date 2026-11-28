// localStorage can be blocked or full: reads fall back and writes are best
// effort, so every saved choice still works for the current page.
export function readStored(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

// A null value removes the key.
export function writeStored(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch { /* not kept */ }
}

export function readJSON(key, fallback = null) {
  try { return JSON.parse(localStorage.getItem(key) || "null") ?? fallback; } catch { return fallback; }
}

export function writeJSON(key, value) {
  writeStored(key, value === null ? null : JSON.stringify(value));
}
