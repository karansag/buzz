// Shared start-up for the browser tests: the production bundle behind
// `vite preview`, and installed stable Chrome with its sandbox enabled.
// The tests use isolated API fixtures and never contact a hub.
import { before, after } from 'node:test';
import { preview } from 'vite';
import { chromium } from 'playwright';

// Starts the server and browser for one test file and stops them at the end.
// `ready` receives { browser, base } once both are up.
export function launch(ready) {
  let browser, server;
  before(async () => {
    server = await preview({ preview: { host: '127.0.0.1', port: 0, open: false } });
    browser = await chromium.launch({ channel: 'chrome', chromiumSandbox: true });
    ready({ browser, base: `http://127.0.0.1:${server.httpServer.address().port}/portal.html` });
  });
  after(async () => {
    await browser?.close();
    if (server) await new Promise(resolve => server.httpServer.close(resolve));
  });
}

// A new page that records page errors. The Mac app's web view shows no native
// JS dialogs, so the page must not use them: one counts as an error.
export async function openPage(browser, options) {
  const page = await browser.newPage(options);
  page.setDefaultTimeout(5000);
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('dialog', d => { errors.push(`native ${d.type()}: ${d.message()}`); d.dismiss(); });
  return { page, errors };
}
