// Renders the dashboard screenshots in the README from made-up swarm data.
// Uses the production bundle (npm run build) and mocked API responses, the
// same way web/test/mobile.browser.js does, so it never contacts a hub.
//
//   npm ci && npm run build
//   google-chrome --version          # patched stable Chrome required
//   node demo/capture.mjs              # needs ffmpeg and ImageMagick
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { preview } from 'vite';
import { chromium } from 'playwright';

const now = Date.now() / 1000;
const ago = s => now - s;
const agents = [
  ['galago', 'claude', 'claude-opus-5-5', 1, 'working', 'working on #41: checkout retry logic'],
  ['stoat', 'codex', 'gpt-6.1-sol', 1, 'working', 'working on #42: idempotency keys on /orders'],
  ['heron', 'claude', 'claude-sonnet-5-5', 1, 'idle', 'done #39: load test, p99 410ms'],
  ['otter', 'codex', 'gpt-6.1-sol', 2, 'working', 'working on #44: migrate docs site to Astro'],
  ['ferret', 'pi', 'qwen4-coder', 2, 'needs_attention', 'waiting on approval: rm -rf dist'],
  ['tapir', 'claude', 'claude-opus-5-5', null, 'working', 'working on #45: flaky auth test'],
  ['numbat', 'hermes', 'hermes-5', null, 'idle', 'idle'],
  ['gannet', 'claude', 'claude-opus-5-5', null, 'working', 'reviewing PR #212'],
];
const nodeOf = i => (i % 3 === 2 ? 'macbook' : 'linux-box');
const peek = `● Read(src/checkout/retry.ts)
  ⎿  Read 142 lines

● The retry loop resends the charge without the original idempotency key,
  so a timeout followed by a retry can bill twice. I'll thread the key
  through and add a test for the timeout path.

● Update(src/checkout/retry.ts)
  ⎿  Updated src/checkout/retry.ts with 6 additions and 2 removals

● Bash(npm test -- checkout)
  ⎿  PASS  src/checkout/retry.test.ts (14 tests)

● Bash(buzz send --to stoat --context task-42 --message "I now pass
      the order's idempotency key on every retry. Does /orders dedupe on it?")
  ⎿  {"ok": true, "status": "delivered"}

✻ Waiting for stoat… (1m 12s · ↓ 3.4k tokens)

────────────────────────────────────────────────────────────────────────
> `;

function makeState() {
  let id = 0;
  const msg = (sender, recipient, content, s, context = null) =>
    ({ id: ++id, sender, recipient, content, context, ts: ago(s), status: 'delivered', attachments: [] });
  return {
    now,
    recipients: agents.map(([user_id, flavor, model, team_id, status, line], i) => ({
      user_id, flavor, model, team_id, node: nodeOf(i), pane_alive: true,
      tmux_pane: `%${20 + i}`, pane_label: `work:${i}.0`, registered_at: ago(7200 - i * 400),
      activity: { status, reason: status === 'needs_attention' ? 'Do you want to run rm -rf dist?' : null },
      summaries: [{ text: line, ts: ago(60 + i * 90), source: 'agent' }],
    })),
    nodes: [
      { name: 'linux-box', connected: true, local: true, harnesses: ['claude', 'codex', 'pi', 'hermes'] },
      { name: 'macbook', connected: true, harnesses: ['claude', 'codex'] },
    ],
    teams: [
      { id: 1, name: 'checkout', queen: 'galago', objective: 'Ship safe payment retries',
        members: ['galago', 'stoat', 'heron'] },
      { id: 2, name: 'docs', queen: 'otter', objective: 'New docs site', members: ['otter', 'ferret'] },
    ],
    supervisor: { user_id: 'gannet', objective: 'Watch the board and tell me what needs me' },
    tasks: [
      { id: 41, title: 'Retry failed charges without double billing', assignee: 'galago', team_id: 1, status: 'picked_up', depends_on: [] },
      { id: 42, title: 'Idempotency keys on POST /orders', assignee: 'stoat', team_id: 1, status: 'picked_up', depends_on: [] },
      { id: 43, title: 'Ship the retry change behind a flag', team_id: 1, status: 'open', depends_on: [41, 42] },
      { id: 44, title: 'Move the docs site to Astro', assignee: 'otter', team_id: 2, status: 'picked_up', depends_on: [] },
      { id: 45, title: 'Fix the flaky auth refresh test', assignee: 'tapir', status: 'picked_up', depends_on: [] },
      { id: 46, title: 'Write the API reference page', status: 'open', depends_on: [44] },
      { id: 47, title: 'Bump the Node runtime to 24', status: 'open', depends_on: [] },
      { id: 48, title: 'Triage last night\'s alerts', status: 'open', depends_on: [] },
      { id: 39, title: 'Load test checkout at 2x traffic', assignee: 'heron', team_id: 1, status: 'done', depends_on: [],
        note: 'Run k6 run load/checkout.js; p99 stays under 450ms at 2x.' },
      { id: 38, title: 'Add a dark theme to the docs', assignee: 'ferret', team_id: 2, status: 'done', depends_on: [],
        note: 'Open /docs and toggle the theme in the header.' },
    ].map((t, i) => ({ description: '', attachments: [], created_at: ago(9000 - i * 300), updated_at: ago(600 - i * 30), ...t })),
    messages: [
      msg('owner', 'galago', 'Checkout retries can bill twice when the payment API times out. Can your team fix it? Keep the change behind a flag.', 2400),
      msg('galago', 'owner', 'On it. I split it into #41 (retry loop, me), #42 (idempotency keys, stoat) and #43 (flag rollout, after both). heron already load tested the current path: p99 410ms at 2x.', 2300),
      msg('galago', 'stoat', 'You have #42. Make /orders dedupe on the Idempotency-Key header; I will send it on every retry.', 2250, 'task-42'),
      msg('stoat', 'galago', 'Sounds good. I will key the dedupe table on (merchant, key) with a 24h TTL.', 2200, 'task-42'),
      msg('owner', 'galago', 'Sounds good. Ping me before #43 goes out.', 900),
      msg('galago', 'owner', 'Will do. The retry loop now passes the key on every attempt and the timeout test is green. Waiting on stoat for #42 before the flag rollout.', 120),
      msg('galago', 'stoat', 'I now pass the order\'s idempotency key on every retry. Does /orders dedupe on it?', 60, 'task-42'),
    ],
  };
}

// New traffic the overview animation plays while it records.
const script = [
  [1500, s => s.messages.push({ sender: 'stoat', recipient: 'galago', content: 'Yes, as of 3f2c1e. A replay inside 24h returns the first response.', context: 'task-42' })],
  [3500, s => { Object.assign(s.tasks.find(t => t.id === 42), { status: 'done', note: 'curl -XPOST /orders twice with one Idempotency-Key; the second returns the first order.' }); }],
  [4500, s => s.messages.push({ sender: 'galago', recipient: 'owner', content: '#41 and #42 are in. Ready to roll out #43 behind the flag?' })],
  [6000, s => s.messages.push({ sender: 'owner', recipient: 'galago', content: 'Yes, go ahead.' })],
  [7500, s => s.messages.push({ sender: 'otter', recipient: 'ferret', content: 'The Astro build passes. Can you port the theme toggle?', context: 'task-44' })],
  [9000, s => { Object.assign(s.tasks.find(t => t.id === 45), { status: 'done', note: 'npm test -- auth --repeat 50 passes.' }); }],
  [10000, s => s.messages.push({ sender: 'tapir', recipient: 'owner', content: 'Fixed #45: the test raced the token refresh timer.' })],
];

async function mock(page, state) {
  await page.route('**/api/state', r => r.fulfill({ json: state }));
  await page.route('**/api/peek/**', r => r.fulfill({ json: { pane_label: 'work:0.0', text: peek } }));
  await page.route('**/api/spawn-options**', r => r.fulfill({ json: { harnesses: {} } }));
  await page.route('**/messages?**', r => r.fulfill({ json: { messages: state.messages } }));
}

const out = new URL('.', import.meta.url).pathname;
const server = await preview({ preview: { host: '127.0.0.1', port: 0, open: false } });
const base = `http://127.0.0.1:${server.httpServer.address().port}/portal.html`;
const browser = await chromium.launch({ channel: 'chrome', chromiumSandbox: true });

async function open(viewport, hash, extra = {}) {
  const state = makeState();
  const context = await browser.newContext({ viewport, deviceScaleFactor: 2, colorScheme: 'dark', ...extra });
  const page = await context.newPage();
  await mock(page, state);
  await page.goto(base + hash);
  await page.waitForSelector('.stage');
  return { context, page, state };
}

try {
  // 1. The overview, recorded while messages fly and tasks ship.
  {
    const video = mkdtempSync(join(tmpdir(), 'swarm-demo-'));
    const state = makeState();
    const context = await browser.newContext({
      viewport: { width: 1440, height: 760 }, colorScheme: 'dark',
      recordVideo: { dir: video, size: { width: 1440, height: 760 } },
    });
    const page = await context.newPage();
    await mock(page, state);
    await page.goto(base + '#/');
    await page.waitForSelector('canvas');
    const start = Date.now();
    for (const [at, change] of script) {
      await page.waitForTimeout(Math.max(0, at - (Date.now() - start)));
      const before = state.messages.length;
      change(state);
      for (const m of state.messages.slice(before))
        Object.assign(m, { id: state.messages.length, ts: Date.now() / 1000, status: 'delivered', attachments: [], context: m.context ?? null });
      for (const t of state.tasks) t.updated_at ??= Date.now() / 1000;
    }
    await page.waitForTimeout(3000);
    await context.close();
    const webm = join(video, readdirSync(video)[0]);
    // Skip the page load, keep the header, hive and sidebar, 10 fps, one palette.
    execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-ss', '1.2', '-i', webm, '-vf',
      'crop=1440:500:0:0,fps=8,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle',
      join(out, 'dashboard.gif')]);
    rmSync(video, { recursive: true });
  }

  // 2. An agent's page: its live terminal, the owner thread, the team sidebar.
  {
    const { context, page } = await open({ width: 1440, height: 1560 }, '#/agent/galago');
    await page.click('details.scope > summary');
    await page.waitForFunction(() => document.querySelector('details.scope pre')?.textContent.includes('Waiting'));
    await page.waitForTimeout(500);
    const full = join(tmpdir(), 'swarm-agent.png');
    await page.screenshot({ path: full });
    execFileSync('convert', [full, '-resize', '1600x', '-colors', '256', join(out, 'agent-page.png')]);
    rmSync(full);
    await context.close();
  }

  // 3. The phone: the overview and an agent's chat, side by side.
  {
    const phone = { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true };
    const shots = [];
    for (const hash of ['#/', '#/agent/galago']) {
      const { context, page } = await open(phone.viewport, hash, { hasTouch: true, isMobile: true });
      if (hash !== '#/') await page.locator('.thread').first().locator('button[aria-pressed]').click();
      await page.waitForTimeout(500);
      const path = join(tmpdir(), `swarm-phone-${shots.length}.png`);
      await page.screenshot({ path });
      shots.push(path);
      await context.close();
    }
    execFileSync('convert', ['-background', '#14110c', ...shots.flatMap(s => [s, '-bordercolor', '#14110c', '-border', '24']),
      '+append', '-resize', '50%', '-colors', '256', join(out, 'phone.png')]);
    for (const s of shots) rmSync(s);
  }
} finally {
  await browser.close();
  await new Promise(resolve => server.httpServer.close(resolve));
}
