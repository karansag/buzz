// Load the dashboard from a running hub in headless Chrome and report what
// happened: requests that failed, page errors, and what was drawn.
//
//   node rust/compat/dashboard_smoke.mjs http://127.0.0.1:PORT [screenshot.png]
//
// Run from the repository root so `playwright` resolves. Prints one JSON object.
import { chromium } from 'playwright';

const [base, shot] = process.argv.slice(2);
const browser = await chromium.launch({ channel: 'chrome', chromiumSandbox: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
const requests = [], errors = [];
page.on('response', r => requests.push({ path: new URL(r.url()).pathname, status: r.status() }));
page.on('requestfailed', r => errors.push(`request failed: ${new URL(r.url()).pathname}`));
page.on('pageerror', e => errors.push(`page error: ${e.message}`));
page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text().slice(0, 200)}`); });

const started = Date.now();
await page.goto(base + '/', { waitUntil: 'load' });
// The page draws after its first /api/state answer; wait for a second poll too.
await page.waitForResponse(r => r.url().includes('/api/state') && r.status() === 200, { timeout: 15000 });
await page.waitForResponse(r => r.url().includes('/api/state'), { timeout: 15000 }).catch(() => {});
await page.waitForTimeout(1500);
const drawn = await page.evaluate(() => ({
  title: document.title,
  elements: document.querySelectorAll('body *').length,
  textLength: document.body.innerText.length,
  agentTiles: document.querySelectorAll('.bee-tile').length,
  views: [...document.querySelectorAll('nav.views a')].map(a => a.textContent.trim()),
}));
if (shot) await page.screenshot({ path: shot });
await browser.close();

const byPath = {};
for (const r of requests) (byPath[`${r.status} ${r.path.replace(/\/agents\/[^/]+/, '/agents/<id>')}`] ??= 0, byPath[`${r.status} ${r.path.replace(/\/agents\/[^/]+/, '/agents/<id>')}`]++);
console.log(JSON.stringify({
  ms: Date.now() - started, drawn, requests: byPath,
  bad: requests.filter(r => r.status >= 400).map(r => `${r.status} ${r.path}`), errors,
}, null, 1));
