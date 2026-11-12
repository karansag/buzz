import { html } from 'htm/preact';
import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks';

import { showAgentMessage } from './agent-route.js';

const PAGE_SIZE = 100;
export function useConversationSearch(user) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [result, setResult] = useState({total: 0, index: 0, busy: false, error: '', current: null});
  const input = useRef(null), previousFocus = useRef(null), session = useRef(null);
  const show = () => {
    if (!open) previousFocus.current = document.activeElement;
    setOpen(true);
    requestAnimationFrame(() => { input.current?.focus(); input.current?.select(); });
  };
  const close = () => {
    session.current?.abort.abort();
    setOpen(false);
    if (previousFocus.current?.isConnected) previousFocus.current.focus({preventScroll: true});
  };
  useLayoutEffect(() => {
    const key = event => {
      if (event.isComposing || document.querySelector('.quick-switch[open], dialog.page-dialog[open]')) return;
      if ((event.metaKey || event.ctrlKey) && !event.altKey && event.key.toLowerCase() === 'f') {
        event.preventDefault(); event.stopImmediatePropagation(); show();
      } else if (open && event.key === 'Escape') {
        event.preventDefault(); event.stopImmediatePropagation(); close();
      }
    };
    addEventListener('keydown', key, true);
    return () => removeEventListener('keydown', key, true);
  }, [open, user]);

  const read = async (s, index) => {
    const offset = Math.floor(index / PAGE_SIZE) * PAGE_SIZE;
    if (!s.pages.has(offset)) {
      const response = await fetch(`/api/agents/${encodeURIComponent(user)}/messages/search?${new URLSearchParams({q: s.query, limit: PAGE_SIZE, offset})}`,
        {signal: s.abort.signal});
      if (!response.ok) throw Error('Could not search this conversation. Please try again.');
      const page = await response.json();
      if (!Array.isArray(page.matches) || !Number.isInteger(page.total)) throw Error('Invalid search response.');
      s.total = page.total;
      s.pages.set(offset, page.matches);
    }
    return s.pages.get(offset)[index - offset] || null;
  };
  useEffect(() => {
    const s = {query: query.trim(), pages: new Map(), abort: new AbortController(), index: 0, total: 0, sequence: 0};
    session.current = s;
    setResult({total: 0, index: 0, busy: open && !!s.query, error: '', current: null});
    if (!open || !s.query) return () => { s.abort.abort(); };
    const timer = setTimeout(async () => {
      try {
        const current = await read(s, 0);
        if (session.current !== s || s.abort.signal.aborted) return;
        setResult({total: s.total, index: 0, busy: false, error: '', current});
        if (current) showAgentMessage(user, current.id);
      } catch (error) {
        if (!s.abort.signal.aborted) setResult({total: 0, index: 0, busy: false, error: error.message, current: null});
      }
    }, 200);
    return () => { clearTimeout(timer); s.abort.abort(); };
  }, [user, query, open]);
  const move = async delta => {
    const s = session.current;
    if (!s?.total || s.abort.signal.aborted) return;
    const index = (s.index + delta + s.total) % s.total;
    s.index = index;
    const sequence = ++s.sequence;
    setResult(prev => ({...prev, index, busy: true, error: ''}));
    try {
      const current = await read(s, index);
      if (session.current !== s || sequence !== s.sequence || s.abort.signal.aborted) return;
      setResult({total: s.total, index, busy: false, error: '', current});
      if (current) showAgentMessage(user, current.id);
    } catch (error) {
      if (!s.abort.signal.aborted && sequence === s.sequence)
        setResult(prev => ({...prev, busy: false, error: error.message}));
    }
  };
  return {open, query, setQuery, input, show, close, ...result, move,
    words: open ? query.trim().split(/\s+/).filter(Boolean) : []};
}

export function ConversationSearchBar({search}) {
  if (!search.open) return null;
  return html`<div class="conversation-search" role="search" aria-label="Search this conversation">
    <div class="conversation-search-controls">
      <input ref=${search.input} type="search" value=${search.query} aria-label="Search conversation history"
        placeholder="Search full conversation…" onInput=${e => search.setQuery(e.target.value)}
        onKeyDown=${e => {
          if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); e.stopPropagation(); search.move(e.shiftKey ? -1 : 1); }
        }} />
      <span class="conversation-search-count" role="status">${search.busy ? 'Searching…' : search.error ? 'Search unavailable' : search.total ? `${search.index + 1} of ${search.total}` : search.query.trim() ? 'No matches' : 'Full history'}</span>
      <button type="button" aria-label="Previous match" title="Previous match (Shift+Enter)" disabled=${!search.total || search.busy} onClick=${() => search.move(-1)}>↑</button>
      <button type="button" aria-label="Next match" title="Next match (Enter)" disabled=${!search.total || search.busy} onClick=${() => search.move(1)}>↓</button>
      <button type="button" aria-label="Close conversation search" title="Close search (Esc)" onClick=${search.close}>✕</button>
    </div>
    ${search.error && html`<div role="alert">${search.error}</div>`}
  </div>`;
}

// Highlight text nodes only: never alter link destinations or inject query HTML.
const highlights = new Map();
export function highlightSearch(html, words) {
  if (!words.length) return html;
  const key = JSON.stringify([html, words]);
  if (highlights.has(key)) return highlights.get(key);
  const expression = new RegExp(words.slice().sort((a, b) => b.length - a.length)
    .map(word => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'giu');
  const root = document.createElement('div');
  root.innerHTML = html;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    const text = node.textContent;
    expression.lastIndex = 0;
    const matches = [...text.matchAll(expression)];
    if (!matches.length) continue;
    const fragment = document.createDocumentFragment();
    let offset = 0;
    for (const match of matches) {
      fragment.append(document.createTextNode(text.slice(offset, match.index)));
      const mark = document.createElement('mark');
      mark.className = 'conversation-match'; mark.textContent = match[0]; fragment.append(mark);
      offset = match.index + match[0].length;
    }
    fragment.append(document.createTextNode(text.slice(offset)));
    node.replaceWith(fragment);
  }
  const out = root.innerHTML;
  if (highlights.size >= 500) highlights.delete(highlights.keys().next().value);
  highlights.set(key, out);
  return out;
}
