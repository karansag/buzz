// Talk deck screenshots from the built dashboard and made-up swarm data.
// Never contacts a hub: it mocks the same HTTP surface the browser tests use.
import { mkdirSync } from 'node:fs';
import { preview } from 'vite';
import { chromium } from 'playwright';

const E = '\x1b';
const now = Date.now() / 1000;
const ago = s => now - s;
const imgDir = new URL('../talks/2026-11-update/img/', import.meta.url).pathname;
mkdirSync(imgDir, { recursive: true });

const agents = [
  ['galago', 'claude', 'claude-opus-5', 1, 'working', 'working on #41: charge retry logic'],
  ['stoat', 'codex', 'gpt-6.1-sol', 1, 'working', 'working on #42: idempotency keys on /orders'],
  ['heron', 'claude', 'claude-sonnet-5', 1, 'idle', 'done #39: load test at 2x traffic'],
  ['otter', 'codex', 'gpt-6.1-sol', 2, 'working', 'working on #44: docs build pipeline'],
  ['ferret', 'pi', 'deepseek-v4.1-flash', 2, 'needs_attention', 'waiting on approval for theme migration'],
  ['tapir', 'claude', 'claude-sonnet-5', null, 'working', 'working on #45: flaky auth refresh test'],
  ['numbat', 'hermes', 'hermes-5', null, 'idle', 'idle'],
  ['gannet', 'claude', 'claude-opus-5', null, 'working', 'reviewing queue health'],
];
const nodeOf = i => (i % 3 === 2 ? 'remote-build' : 'demo-linux');

function historyPage(state, user, params) {
  const limit = Math.max(1, Math.min(500, Number(params.get('limit') || 300)));
  const mine = state.history.filter(m => m.sender === user || m.recipient === user);
  const around = Number(params.get('around') || 0), before = Number(params.get('before') || Infinity), after = Number(params.get('after') || 0);
  if (around) {
    const half = Math.floor(limit / 2);
    const older = mine.filter(m => m.id <= around).sort((a, b) => b.id - a.id);
    const newer = mine.filter(m => m.id > around).sort((a, b) => a.id - b.id);
    return { messages: [...older.slice(0, half).reverse(), ...newer.slice(0, half)], has_more: older.length > half };
  }
  if (after) {
    const rows = mine.filter(m => m.id > after).sort((a, b) => a.id - b.id).slice(0, limit + 1);
    return { messages: rows.slice(0, limit), has_more: rows.length > limit };
  }
  const rows = mine.filter(m => m.id < before).sort((a, b) => b.id - a.id).slice(0, limit + 1);
  return { messages: rows.slice(0, limit), has_more: rows.length > limit };
}

function makeState() {
  let id = 0;
  const msg = (sender, recipient, content, seconds, context = null, reply_to = null) =>
    ({ id: ++id, sender, recipient, content, context, reply_to, ts: ago(seconds), status: 'delivered', attachments: [] });
  const peer = [
    msg('galago', 'stoat', 'You have #42. /orders should dedupe on the Idempotency-Key header.', 1400, 'task-42'),
    msg('stoat', 'galago', 'Understood. I will key the dedupe table on merchant and key, with a 24h TTL.', 1360, 'task-42'),
    msg('galago', 'tapir', 'Check the flaky refresh test on #45.', 1280, 'task-45'),
    msg('tapir', 'galago', 'The test races the refresh timer. I moved setup into beforeEach and reran it 100 times.', 1220, 'task-45'),
    msg('galago', 'otter', 'Docs pipeline is yours. #44 is behind DOCS_PIPELINE_V2.', 1100, 'task-44'),
    msg('otter', 'galago', 'I split the build and deploy jobs; preview is green.', 1030, 'task-44'),
    msg('otter', 'ferret', 'Docs build passes. Can you port the theme toggle?', 700, 'task-44'),
    msg('ferret', 'otter', 'Yes. I have the component ready; I will reuse the icon set.', 640, 'task-44'),
    msg('galago', 'heron', 'Load test checkout at 2x traffic; keep p99 under 450ms.', 500, 'task-39'),
    msg('heron', 'galago', 'p99 is 410ms at 2x traffic. #39 is ready to close.', 470, 'task-39'),
    msg('galago', 'stoat', 'Docs are ready. Can you rebase #42 once the build lands?', 230, 'task-42'),
    msg('stoat', 'galago', 'Yes. I also found a duplicated retry branch to remove.', 180, 'task-42'),
    msg('galago', 'stoat', 'Reminder: keep the rollout behind the retry flag.', 120, 'broadcast'),
    msg('galago', 'heron', 'Reminder: keep the rollout behind the retry flag.', 118, 'broadcast'),
    msg('galago', 'otter', 'Reminder: keep the rollout behind the retry flag.', 116, 'broadcast'),
  ];
  const owner = [
    msg('owner', 'galago', 'Checkout retries can double-bill when the payment API times out. Can your team fix it?', 2200),
    msg('galago', 'owner', 'I split it into #41 (retry loop), #42 (idempotency keys), and #43 (flagged rollout).', 2120),
    msg('owner', 'galago', 'Please make sure the rollout is independently reversible.', 2000, null, 17),
    msg('galago', 'owner', 'Yes. The flag is CHECKOUT_RETRY_FLAG and defaults off. idempotency key work is in #42.', 1900),
    msg('owner', 'galago', 'Before #43, show me the idempotency path.', 1000, null, 19),
    msg('galago', 'owner', 'The payment client reuses one idempotency key for every retry attempt.', 900),
    msg('owner', 'galago', 'What happens with a replay after 24h?', 700, null, 21),
    msg('galago', 'owner', 'The replay creates a new key, so merchants can retry after the old key expires.', 600),
  ];
  const messages = [...peer, ...owner].map((m, index) => ({ ...m, id: index + 1 }));
  return {
    now,
    recipients: agents.map(([user_id, flavor, model, team_id, status, line], i) => ({
      user_id, flavor, model, team_id, node: nodeOf(i), pane_alive: true,
      tmux_pane: `%${31 + i}`, pane_label: `demo:${i}.0`, registered_at: ago(7200 - i * 200),
      activity: { status, reason: status === 'needs_attention' ? 'Approve the docs migration?' : null },
      summaries: [{ text: line, ts: ago(90 + i * 20), source: 'agent' }],
    })),
    nodes: [
      { name: 'demo-linux', connected: true, local: true, harnesses: ['claude', 'codex', 'pi', 'hermes'] },
      { name: 'remote-build', connected: true, harnesses: ['codex', 'claude'] },
    ],
    teams: [
      { id: 1, name: 'payments', queen: 'galago', objective: 'Ship safe payment retries', members: ['galago', 'stoat', 'heron'] },
      { id: 2, name: 'docs', queen: 'otter', objective: 'Move docs to Astro', members: ['otter', 'ferret'] },
    ],
    supervisor: { user_id: 'gannet', objective: 'Watch the queue and summarize risks' },
    tasks: [
      { id: 41, title: 'Retry failed charges without double billing', assignee: 'galago', team_id: 1, status: 'picked_up', depends_on: [] },
      { id: 42, title: 'Idempotency keys on POST /orders', assignee: 'stoat', team_id: 1, status: 'picked_up', depends_on: [] },
      { id: 43, title: 'Ship retry rollout behind a flag', team_id: 1, status: 'open', depends_on: [41, 42] },
      { id: 44, title: 'Move docs to Astro', assignee: 'otter', team_id: 2, status: 'picked_up', depends_on: [] },
      { id: 45, title: 'Fix the flaky auth refresh test', assignee: 'tapir', status: 'picked_up', depends_on: [] },
      { id: 39, title: 'Load test payments at 2x traffic', assignee: 'heron', team_id: 1, status: 'done', depends_on: [], note: 'Run k6 run load/checkout.js; p99 under 480ms at 2x.' },
    ].map(task => ({ description: '', attachments: [], worktree: '', created_at: ago(3600), updated_at: ago(100), ...task })),
    messages,
    history: messages,
  };
}

const colorTerminal = [
  `${E}[36m$ npm test -- checkout${E}[0m`,
  `${E}[92mPASS${E}[0m src/checkout/retry.test.ts (14 tests)`,
  `${E}[91mFAIL${E}[0m src/orders/idempotency.test.ts`,
  `${E}[31m  expected replay inside 24h to return the original order${E}[0m`,
  '',
  `${E}[36m$ git diff -- src/orders/idempotency.ts${E}[0m`,
  `${E}[91m-      const previous = await db.orders.lookup({ key })${E}[0m`,
  `${E}[92m+      const previous = await db.idempotency.lookupByMerchant({ merchant, key })${E}[0m`,
  `${E}[92m+      if (previous) return previous.response${E}[0m`,
  '',
  `${E}[33mwarning${E}[0m: live test still prints one benign ${E}[2mrefresh timer${E}[0m message`,
  `${E}[36m$ npm test -- checkout idempotency${E}[0m`,
  `${E}[92mPASS${E}[0m 2 files, 17 tests (1.8s)`,
  `${E}[2mwaiting for review…${E}[0m`,
].join('\n');

async function mock(page, state) {
  await page.route('**/api/state', route => route.fulfill({ json: state }));
  await page.route('**/api/peek/**', route => route.fulfill({ json: { pane_label: 'demo:0.0', text: colorTerminal } }));
  await page.route('**/api/spawn-options**', route => route.fulfill({ json: { harnesses: {} } }));
  await page.route('**/messages?**', route => {
    const url = new URL(route.request().url());
    const user = url.searchParams.get('user');
    const messages = user && user !== 'owner' ? state.messages.filter(m => m.sender === user || m.recipient === user) : state.messages;
    return route.fulfill({ json: { messages } });
  });
  await page.route('**/api/agents/*/messages/search?*', route => {
    const url = new URL(route.request().url());
    const q = (url.searchParams.get('q') || '').toLowerCase();
    const found = state.messages.filter(m => m.content.toLowerCase().includes(q));
    const matches = found.sort((a, b) => b.ts - a.ts).slice(0, 3).map(m => ({ id: m.id, ts: m.ts, sender: m.sender, snippet: m.content }));
    return route.fulfill({ json: { matches, total: matches.length } });
  });
  await page.route('**/api/agents/*/messages?*', route => {
    const url = new URL(route.request().url());
    const user = decodeURIComponent(url.pathname.split('/')[3]);
    return route.fulfill({ json: historyPage(state, user, url.searchParams) });
  });
  await page.route('**/api/agents/*/messages/count?*', route => {
    const url = new URL(route.request().url());
    const user = decodeURIComponent(url.pathname.split('/')[3]);
    const after = Number(url.searchParams.get('after')), before = Number(url.searchParams.get('before'));
    const count = state.history.filter(m => (m.sender === user || m.recipient === user) && m.id > after && m.id < before).length;
    return route.fulfill({ json: { count } });
  });
}

const server = await preview({ preview: { host: '127.0.0.1', port: 0, open: false } });
const base = `http://127.0.0.1:${server.httpServer.address().port}/portal.html`;
const browser = await chromium.launch({ channel: 'chrome', chromiumSandbox: true });

async function open(hash) {
  const state = makeState();
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 }, deviceScaleFactor: 2, colorScheme: 'dark' });
  const page = await context.newPage();
  await mock(page, state);
  await page.goto(base + hash);
  await page.waitForSelector('.stage');
  return { context, page, state };
}

try {
  { // (a) Chats -> between agents: token cards and broadcast grouping.
    const { context, page } = await open('#/chats?view=agents');
    await page.addStyleTag({ content: 'html, body, main.dashboard-layout, .main-col { height: auto !important; min-height: 100vh !important; overflow: visible !important; }' });
    await page.setViewportSize({ width: 1400, height: 1150 });
    await page.evaluate(() => { window.scrollTo(0, 0); document.querySelector('.stage')?.scrollTo(0, 0); });
    await page.waitForSelector('.agent-talk');
    await page.waitForTimeout(250);
    const bounds = await page.locator('.chats').boundingBox();
    await page.screenshot({ path: `${imgDir}/chats-between-agents.png`, clip: { x: 0, y: 0, width: bounds.width + 68, height: bounds.y + bounds.height + 30 } });
    await context.close();
  }
  { // (b) A reply with its quote visible in the owner conversation.
    const { context, page } = await open('#/agent/galago');
    await page.waitForSelector('.reply-reference');
    const target = page.locator('[data-message-id="18"]');
    await target.scrollIntoViewIfNeeded();
    await page.waitForTimeout(250);
    await page.locator('.thread').first().screenshot({ path: `${imgDir}/reply-quote.png` });
    await context.close();
  }
  { // (c) In-conversation search with results highlighted.
    const { context, page } = await open('#/agent/galago');
    await page.locator('.thread-toggle').first().click();
    await page.keyboard.press('Control+f');
    const input = page.getByRole('searchbox', { name: 'Search conversation history' });
    await input.fill('idempotency');
    await page.getByRole('status').filter({ hasText: /of 3/ }).waitFor();
    await page.waitForTimeout(200);
    const thread = await page.locator('.thread').first().boundingBox();
    await page.screenshot({ path: `${imgDir}/search.png`, clip: { x: thread.x, y: thread.y, width: thread.width, height: 390 } });
    await context.close();
  }
  { // (d) Cmd/Ctrl+K style agent switcher; queen crown is visible.
    const { context, page } = await open('#/');
    await page.locator('.quick-switch-launchers > button').last().click();
    const dialog = page.getByRole('dialog', { name: 'Switch agent' });
    await dialog.waitFor();
    await page.waitForTimeout(250);
    await dialog.screenshot({ path: `${imgDir}/switcher.png` });
    await context.close();
  }
  { // (e) Terminal scope with ANSI diagnostics and a diff.
    const { context, page } = await open('#/agent/galago');
    await page.locator('.scope summary').click();
    await page.waitForSelector('.scope pre span');
    await page.waitForTimeout(250);
    await page.locator('.scope').screenshot({ path: `${imgDir}/terminal-colors.png` });
    await context.close();
  }
} finally {
  await browser.close();
  await new Promise(resolve => server.httpServer.close(resolve));
}
