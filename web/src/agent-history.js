import { useEffect, useRef, useState } from "preact/hooks";
import { POLL_MS } from "./shared.js";
import { addSpan, gapsOf, spanOf } from "./history-spans.js";

const PAGE = 300;
// One click on "load the missing messages" fills up to this many pages, so a
// hole left by a jump cannot turn into an unbounded burst of requests.
const FILL_PAGES = 10;

// A conversation's loaded history. It pages backwards from the newest message,
// and it can also load the page around one message id: the chats search and
// other search UIs jump to a match that may be far back. That page need not
// touch the newest page, so the hook tracks which stretches of ids are loaded
// and reports the holes as `gaps`, for the view to offer to fill, rather than
// showing a conversation that is quietly missing its middle.
export function useAgentHistory(user) {
  const [history, setHistory] = useState({ messages: [], loaded: false, more: false, busy: false, error: "", gaps: [] });
  // The last "open at message" lookup: idle, loading, found, missing (this
  // conversation has no such message) or failed (try again).
  const [lookup, setLookup] = useState({ id: null, status: "idle" });
  const commands = useRef({ older: () => {}, around: () => {}, gap: () => {} });
  useEffect(() => {
    let active = true, polling = false, busy = false;
    // Ids loaded so far, as ascending, disjoint, non-touching spans.
    let spans = [];
    // The highest id seen, so polling asks only for what arrived after it.
    let newest = null;
    const abort = new AbortController();
    setHistory({ messages: [], loaded: false, more: false, busy: false, error: "", gaps: [] });
    setLookup({ id: null, status: "idle" });

    const read = async query => {
      const response = await fetch(`/api/agents/${encodeURIComponent(user)}/messages?${query}`, { signal: abort.signal });
      if (!response.ok) throw Error("History unavailable");
      const page = await response.json();
      if (!Array.isArray(page.messages) || typeof page.has_more !== "boolean") throw Error("Invalid history");
      return page;
    };
    const oldest = () => (spans.length ? spans[0].lo : null);
    // `more` is "there are messages older than everything loaded"; only the
    // page that establishes the bottom edge changes it.
    const merge = (page, more) => {
      if (!active) return;
      const ids = page.messages.map(m => m.id);
      const span = spanOf(ids);
      if (span) {
        spans = addSpan(spans, span.lo, span.hi);
        newest = Math.max(newest ?? 0, ...ids);
      } else if (newest === null) newest = 0;
      setHistory(prev => ({
        ...prev, loaded: true, error: "",
        more: more === undefined ? prev.more : more,
        messages: [...new Map([...prev.messages, ...page.messages].map(m => [m.id, m])).values()],
      }));
      checkGaps();
    };
    const fail = message => { if (active) setHistory(prev => ({ ...prev, error: message })); };

    // A hole between two loaded stretches is only real if the conversation
    // actually has messages between them: ids are global, so a gap in the id
    // arithmetic is usually nothing at all. Ask the hub, then keep the hole
    // with its count so the view can say how much is missing.
    const counts = new Map();
    const showGap = (gap, count) => setHistory(prev => prev.gaps.some(g => g.after === gap.after && g.before === gap.before)
      ? prev : { ...prev, gaps: [...prev.gaps, { ...gap, count }].sort((a, b) => a.after - b.after) });
    const pruneGaps = candidates => setHistory(prev => ({
      ...prev,
      gaps: prev.gaps.filter(gap => candidates.some(c => c.after === gap.after && c.before === gap.before)),
    }));
    const verify = async (gap) => {
      const key = `${gap.after}:${gap.before}`;
      if (counts.has(key)) {
        const known = counts.get(key);
        if (known) showGap(gap, known);
        return;
      }
      counts.set(key, 0);
      try {
        const response = await fetch(`/api/agents/${encodeURIComponent(user)}/messages/count?after=${gap.after}&before=${gap.before}`, { signal: abort.signal });
        if (!response.ok) throw Error("count unavailable");
        const { count } = await response.json();
        if (!active) return;
        counts.set(key, count);
        if (count) showGap(gap, count);
      } catch { counts.delete(key); }
    };
    const checkGaps = () => {
      const candidates = gapsOf(spans);
      pruneGaps(candidates);
      for (const gap of candidates) verify(gap);
    };

    const poll = async () => {
      if (polling) return;
      polling = true;
      try {
        const initial = newest === null;
        let page = await read(initial ? `limit=${PAGE}` : `after=${newest}&limit=${PAGE}`);
        merge(page, initial ? page.has_more : undefined);
        // Catch up completely even when more than one page arrived between polls.
        while (active && !initial && page.has_more) {
          page = await read(`after=${newest}&limit=${PAGE}`);
          merge(page);
        }
      } catch {
        fail("Could not load conversation history. Retrying…");
      } finally { polling = false; }
    };

    commands.current.older = async () => {
      const before = oldest();
      if (busy || before === null) return;
      busy = true;
      setHistory(prev => ({ ...prev, busy: true }));
      try {
        const page = await read(`before=${before}&limit=${PAGE}`);
        merge(page, page.has_more);
      }
      catch { fail("Could not load older messages. Please try again."); }
      finally {
        busy = false;
        if (active) setHistory(prev => ({ ...prev, busy: false }));
      }
    };

    commands.current.around = async mid => {
      if (busy) return;
      busy = true;
      setLookup({ id: mid, status: "loading" });
      setHistory(prev => ({ ...prev, busy: true }));
      try {
        const page = await read(`around=${mid}&limit=${PAGE}`);
        const found = page.messages.some(m => m.id === mid);
        const below = oldest();
        // A window that lands under everything loaded becomes the bottom edge,
        // so its has_more says whether there is still older history below.
        const extendsBottom = page.messages.length > 0 && (below === null || Math.min(...page.messages.map(m => m.id)) < below);
        merge(page, extendsBottom ? page.has_more : undefined);
        setLookup({ id: mid, status: found ? "found" : "missing" });
      } catch {
        setLookup({ id: mid, status: "failed" });
      } finally {
        busy = false;
        if (active) setHistory(prev => ({ ...prev, busy: false }));
      }
    };

    commands.current.gap = async gap => {
      if (busy) return;
      busy = true;
      setHistory(prev => ({ ...prev, busy: true }));
      try {
        let from = gap.after;
        for (let page = 0; page < FILL_PAGES && active && from < gap.before; page += 1) {
          const body = await read(`after=${from}&limit=${PAGE}`);
          const ids = body.messages.map(m => m.id);
          merge(body);
          if (!ids.length) break;
          from = Math.max(...ids);
          if (!body.has_more) break;
        }
      } catch { fail("Could not load the missing messages. Please try again."); }
      finally {
        busy = false;
        if (active) setHistory(prev => ({ ...prev, busy: false }));
      }
    };

    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => { active = false; abort.abort(); clearInterval(timer); };
  }, [user]);
  return {
    ...history,
    lookup,
    loadOlder: () => commands.current.older(),
    loadAround: mid => commands.current.around(mid),
    loadGap: gap => commands.current.gap(gap),
  };
}
