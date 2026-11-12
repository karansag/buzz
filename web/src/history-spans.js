// No imports, so `node --test web/test` can exercise it without a browser.

// Which stretches of message ids a conversation has loaded. Jumping to a far
// back message loads a window that need not touch the newest page, so the view
// needs to know where the holes are: that is what "messages not loaded" means,
// rather than showing a conversation that is quietly missing its middle.

// Add the inclusive range [lo, hi] to the spans, merging overlaps and touching
// ranges. Returns the new list, ascending and disjoint.
export function addSpan(spans, lo, hi) {
  const merged = [];
  for (const span of [...spans, { lo, hi }].sort((a, b) => a.lo - b.lo)) {
    const last = merged[merged.length - 1];
    if (last && span.lo <= last.hi + 1) last.hi = Math.max(last.hi, span.hi);
    else merged.push({ ...span });
  }
  return merged;
}

// Spans from a page of message ids, so a caller does not need the min and max.
export function spanOf(ids) {
  return ids.length ? { lo: Math.min(...ids), hi: Math.max(...ids) } : null;
}

// The holes between spans, as the loaded ids on each side of them.
export function gapsOf(spans) {
  return spans.slice(1).map((span, i) => ({ after: spans[i].hi, before: span.lo }));
}
