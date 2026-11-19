// Uses installed stable Chrome with its sandbox enabled: `npm run test:browser`.
// Uses the production bundle and isolated API fixtures; never contacts a hub.
import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { preview } from 'vite';
import { chromium } from 'playwright';
import { fixture, mock } from './fixtures/mobile-state.js';

let browser, server, base;
before(async () => {
  server = await preview({ preview: { host: '127.0.0.1', port: 0, open: false } });
  base = `http://127.0.0.1:${server.httpServer.address().port}/portal.html`;
  browser = await chromium.launch({ channel: 'chrome', chromiumSandbox: true });
});
after(async () => {
  await browser?.close();
  await new Promise(resolve => server.httpServer.close(resolve));
});

// Three tasks whose text mentions the fourth one's number, and an agent
// status line that does too: typing "310" used to list all four.
function historyState() {
  const state = fixture();
  const now = state.now;
  const task = (id, title, description, status) => ({
    id, title, description, status, created_at: now - id, updated_at: now - id / 2,
    depends_on: [], attachments: [],
  });
  state.tasks = [
    task(310, 'Search by task number', 'A bare number should find its own task.', 'picked_up'),
    task(311, 'Mention 310 in passing', 'Unrelated work: 310 was fixed elsewhere.', 'open'),
    task(312, 'Search fix for 310', 'Both words appear here, so a two-word query still matches.', 'done'),
    task(313, 'Notes about 999', 'No such task exists, so 999 is searched as text.', 'open'),
  ];
  state.recipients[0].summaries = [
    { text: 'working on #310 search', ts: now, source: 'agent' },
  ];
  return state;
}

async function openHistory() {
  const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
  page.setDefaultTimeout(5000);
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('dialog', d => { errors.push(`native ${d.type()}: ${d.message()}`); d.dismiss(); });
  await mock(page, historyState());
  await page.goto(base + '#/tasks');
  await page.waitForSelector('.h-search');
  return { page, errors };
}

// The ids of the task tiles on screen, in order, and the header's count.
async function shownIds(page) {
  return page.locator('.h-grid .htile').evaluateAll(tiles => tiles.map(t =>
    t.classList.contains('status-line') ? 'status' : (t.querySelector('.h-id')?.textContent || '?')));
}

async function search(page, text, expected) {
  await page.locator('.h-search').fill(text);
  await page.waitForFunction(
    n => document.querySelectorAll('.h-grid .htile').length === n, expected.length);
  return shownIds(page);
}

test('a bare task number shows only that task, not every mention of it', async () => {
  const { page, errors } = await openHistory();
  try {
    assert.deepEqual(await search(page, '310', ['#310']), ['#310']);
    // No status line either, though one says "working on #310 search".
    assert.equal(await page.locator('.htile.status-line').count(), 0);
    assert.equal(await page.locator('.history h2 .count').textContent(), '· 1 of 4 tasks');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('#310 picks the same task', async () => {
  const { page, errors } = await openHistory();
  try {
    assert.deepEqual(await search(page, '#310', ['#310']), ['#310']);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('a number that is no task id is still searched as text', async () => {
  const { page, errors } = await openHistory();
  try {
    // Task 313's text mentions 999; no task has that id.
    assert.deepEqual(await search(page, '999', ['#313']), ['#313']);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('several words keep the usual AND search', async () => {
  const { page, errors } = await openHistory();
  try {
    // In a longer query a number still matches its task's id, as before, and
    // "search" then has to appear too: 310's title and 312's both have it.
    // The status line holds both words and is the newest record.
    assert.deepEqual(await search(page, '310 search', ['status', '#310', '#312']),
                     ['status', '#310', '#312']);
    // No task 310 here, so the number is plain text: only 311's title fits.
    assert.deepEqual(await search(page, '310 passing', ['#311']), ['#311']);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});