// Uses installed stable Chrome with its sandbox enabled: `npm run test:browser`.
// Uses the production bundle and isolated API fixtures; never contacts a hub.
import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { preview } from 'vite';
import { chromium } from 'playwright';
import { mock, names, file, image } from './fixtures/mobile-state.js';

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
async function setup(width, height, touch = true) {
  const page = await browser.newPage({ viewport: { width, height }, hasTouch: touch, isMobile: touch });
  page.setDefaultTimeout(5000);
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  // The Mac app's web view shows no native JS dialogs, so the page must not use them.
  page.on('dialog', d => { errors.push(`native ${d.type()}: ${d.message()}`); d.dismiss(); });
  const state = await mock(page);
  return { page, state, errors };
}
// Answers the page's own confirm or notice dialog and returns its message.
async function answer(page, button = 'OK') {
  const dialog = page.locator('dialog.page-dialog[open]');
  await dialog.waitFor();
  const message = await dialog.locator('.page-dialog-message').textContent();
  await dialog.getByRole('button', { name: button, exact: true }).click();
  await dialog.waitFor({ state: 'detached' });
  return message;
}
async function fit(page) {
  await page.locator('img').evaluateAll(images => Promise.all(images.map(img => {
    img.loading = 'eager';
    return img.complete ? Promise.resolve() : new Promise(resolve => {
      img.addEventListener('load', resolve, {once:true});
      img.addEventListener('error', resolve, {once:true});
    });
  })));
  const measured = await page.evaluate(() => {
    const stage = document.querySelector('.stage');
    const width = document.documentElement.clientWidth;
    return {
      width, page: document.documentElement.scrollWidth,
      stage: stage.scrollWidth, stageWidth: stage.clientWidth,
      overflow: [...document.querySelectorAll('.stage *')].filter(e => {
        const r = e.getBoundingClientRect();
        return r.width && r.right > width + 1 && !e.closest('.sr-only');
      }).map(e => e.className),
      small: [...document.querySelectorAll('button, select, nav.views a, .bee-tile')].filter(e => {
        const r = e.getBoundingClientRect();
        return r.width && r.height && (r.height < 43.5 || r.width < 43.5) && !e.closest('[hidden]');
      }).map(e => e.className),
    };
  });
  assert.equal(measured.page, measured.width);
  assert.ok(measured.stage <= measured.stageWidth + 1);
  assert.deepEqual(measured.overflow, []);
  assert.deepEqual(measured.small, []);
}
for (const [width, height] of [[320,568],[390,844],[430,932],[768,1024],[820,1180],[1024,768]]) {
  test(`phone/tablet ${width}x${height}: overview, chat, long names, history fit`, async () => {
    const { page, errors } = await setup(width, height);
    try {
      for (const hash of ['#/', '#/agent/stoat', `#/agent/${names[1]}`, '#/tasks']) {
        await page.goto(base + hash);
        await page.waitForSelector('.stage');
        await fit(page);
        assert.equal(await page.locator('canvas').count(), 0);
      }
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });
}

test('touch navigation, filtering, agent chips, task details and assignment', async () => {
  const { page, state, errors } = await setup(390,844);
  const patches = [];
  await page.route('**/tasks/73', async route => {
    const patch = route.request().postDataJSON();
    patches.push(patch); Object.assign(state.tasks[0], patch);
    await route.fulfill({ json: { ok: true } });
  });
  try {
    // These checks are about the tile grid, one of the phone agents views.
    await page.addInitScript(() => localStorage.setItem('agent-swarm:mobile-agents-view', 'tiles'));
    await page.goto(base);
    await page.waitForSelector('.bee-tile');
    assert.equal(await page.locator('.bee-tile').count(), 8);
    assert.equal(await page.locator('.bee-tile .bee-working-halo').count(), 2);
    const identity = await page.locator('.bee-tile').first().evaluate(tile => ({
      machine: tile.style.getPropertyValue('--machine'),
      body: tile.querySelector('ellipse[cx="26"]').getAttribute('fill'),
      harness: tile.querySelectorAll('path')[1].getAttribute('stroke'),
      halo: tile.querySelector('.bee-working-halo circle').getAttribute('stroke'),
    }));
    assert.equal(identity.machine, identity.body);
    assert.equal(identity.harness, '#56b4e9');
    assert.equal(identity.halo, '#9be879');
    await page.getByRole('button', { name: /karans-mbp.*connected/i }).tap();
    assert.equal(await page.locator('.bee-tile').count(), 4);
    await page.locator('.bee-tile').first().tap();
    await page.waitForSelector('.focus-back');
    assert.match(page.url(), /agent\/numbat/);
    assert.ok(await page.locator('.stage').evaluate(e => Math.abs(e.getBoundingClientRect().top) < 30));
    assert.equal(await page.locator('.status-history').getAttribute('open'), null);
    await page.locator('.status-history summary').tap();
    assert.notEqual(await page.locator('.status-history').getAttribute('open'), null);
    await page.locator('.focus-back').tap();
    await page.locator('.hive-task-picker select').selectOption('73');
    await page.locator('.hive-task-detail').getByRole('combobox', { name: 'Assign task #73' }).selectOption('t:1');
    await page.waitForFunction(() => document.querySelector('.hive-task-detail p').textContent.includes('team agent-swarm'));
    await page.locator('.hive-task-detail').getByRole('combobox', { name: 'Assign task #73' }).selectOption('ferret');
    await page.waitForFunction(() => document.querySelector('.hive-task-detail p').textContent.includes('ferret'));
    assert.deepEqual(patches, [{team_id:1}, {assignee:'ferret',team_id:null}]);
    await fit(page);
    // Phones have no sidebar: the agents panel at the top holds the agents,
    // and its teams view has the management controls.
    assert.equal(await page.locator('#agent-sidebar').count(), 0);
    assert.deepEqual(await page.locator('.agents-view-switch > button').allTextContents(), ['teams', 'tiles']);
    await page.locator('.agents-view-switch button', { hasText: 'teams' }).tap();
    await page.locator('.agents-panel .team-mate', { hasText: names[1] }).first().tap();
    await page.waitForSelector('.focus-back');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('task completion has one note-aware action across board, agent, and honeycomb', async () => {
  const { page, state, errors } = await setup(390,844);
  const patches = [];
  await page.route('**/tasks/*', async route => {
    if (route.request().method() !== 'PATCH') return route.continue();
    const id = Number(route.request().url().split('/').pop());
    const patch = route.request().postDataJSON();
    patches.push({ id, ...patch });
    const task = state.tasks.find(t => t.id === id);
    Object.assign(task, patch);
    await route.fulfill({ json: { ok: true, task } });
  });
  try {
    await page.goto(base);
    const card = page.locator('.col.picked_up .tcard').first();
    await card.getByRole('button', { name: 'Complete task' }).tap();
    assert.equal(patches.length, 0);
    await card.locator('.task-verification textarea').fill('Check the mobile dashboard at 390px.');
    await card.getByRole('button', { name: 'Complete task' }).tap();
    await page.waitForFunction(() => [...document.querySelectorAll('.col.done .tcard')]
      .some(e => e.textContent.includes('Make the dashboard mobile friendly')));
    assert.deepEqual(patches[0], { id: 73, status: 'done', note: 'Check the mobile dashboard at 390px.' });
    const done = page.locator('.col.done .tcard').filter({ has: page.locator('.t', { hasText: 'Make the dashboard mobile friendly' }) });
    assert.equal(await done.getByRole('combobox', { name: 'Assign task #73' }).isDisabled(), true);
    await done.getByRole('button', { name: 'Reopen' }).tap();
    await page.waitForFunction(() => [...document.querySelectorAll('.col.picked_up .tcard')]
      .some(e => e.textContent.includes('Make the dashboard mobile friendly')));
    assert.deepEqual(patches[1], { id: 73, status: 'picked_up' });
    const unassigned = page.locator('.col.open .tcard').filter({ hasText: 'Long path regression' });
    assert.equal(await unassigned.getByRole('button', { name: 'Start work' }).isDisabled(), true);
    await unassigned.getByRole('combobox', { name: 'Assign task #74' }).selectOption('stoat');
    await unassigned.getByRole('button', { name: 'Start work' }).tap();
    await page.waitForFunction(() => [...document.querySelectorAll('.col.picked_up .tcard')]
      .some(e => e.textContent.includes('Long path regression')));
    assert.deepEqual(patches[2], { id: 74, assignee: 'stoat' });
    assert.deepEqual(patches[3], { id: 74, status: 'picked_up' });

    await page.goto(base + '#/agent/stoat');
    const row = page.locator('.trow').filter({ hasText: 'Make the dashboard mobile friendly' });
    await row.getByRole('button', { name: 'Complete task' }).tap();
    await page.waitForFunction(() => [...document.querySelectorAll('.trow.done')]
      .some(e => e.textContent.includes('Make the dashboard mobile friendly')));
    assert.deepEqual(patches[4], { id: 73, status: 'done', note: 'Check the mobile dashboard at 390px.' });

    await page.goto(base);
    await page.locator('.hive-task-picker select').selectOption('74');
    const detail = page.locator('.hive-task-detail');
    await detail.getByRole('button', { name: 'Complete task' }).tap();
    await detail.locator('.task-verification textarea').fill('Open the board and inspect task #74.');
    await detail.getByRole('button', { name: 'Complete task' }).tap();
    await page.waitForFunction(() => document.querySelector('.hive-task-detail')?.textContent.includes('done'));
    assert.deepEqual(patches[5], { id: 74, status: 'done', note: 'Open the board and inspect task #74.' });
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('mobile attachments, message actions, and conversation controls stay usable', async () => {
  const { page, errors } = await setup(390,844);
  const sent = [];
  await page.route('**/attachments', r => r.fulfill({json:{name:r.request().headers()['x-attachment-filename']?.endsWith('.png') ? image : file}}));
  await page.route('**/send', async r => {
    sent.push(r.request().postDataJSON());
    await r.fulfill({json:{ok:true,status:'delivered',message_id:3}});
  });
  try {
    await page.goto(base+'#/agent/stoat');
    const composer = page.locator('.thread .composer').first();
    await composer.locator('input[type=file]').setInputFiles({name:'review.txt',mimeType:'text/plain',buffer:Buffer.from('mobile review')});
    await composer.getByRole('button',{name:/Remove/}).waitFor();
    await fit(page);
    await composer.getByRole('button',{name:/Remove/}).tap();
    assert.equal(await composer.locator('.compose-image').count(),0);
    await composer.locator('input[type=file]').setInputFiles({name:'review.txt',mimeType:'text/plain',buffer:Buffer.from('mobile review')});
    await composer.getByRole('button',{name:/Remove/}).waitFor();
    await composer.locator('textarea').fill('Verified the mobile dashboard.');
    await composer.getByRole('button',{name:'send',exact:true}).tap();
    await page.waitForTimeout(100);
    assert.equal(sent.length,1); assert.deepEqual(sent[0].attachments,[file]);
    assert.equal(sent[0].recipient,'stoat');
    const toggle=page.locator('.thread-toggle').first();
    await toggle.tap(); assert.equal(await toggle.getAttribute('aria-expanded'),'false');
    await toggle.tap(); assert.equal(await toggle.getAttribute('aria-expanded'),'true');
    await fit(page);
    await page.goto(base);
    const taskComposer = page.locator('.task-composer');
    await taskComposer.locator('input[type=file]').setInputFiles({name:'layout.png',mimeType:'image/png',buffer:Buffer.from('mock image bytes')});
    await taskComposer.getByRole('button',{name:'Remove Image'}).waitFor();
    await fit(page);
    await taskComposer.getByRole('button',{name:'Remove Image'}).tap();
    assert.deepEqual(errors,[]);
  } finally {await page.close();}
});

test('desktop baseline and rotation remount the canvas without errors', async () => {
  const {page, errors} = await setup(1001,900,false);
  try {
    await page.goto(base);
    await page.waitForSelector('canvas');
    assert.equal(await page.locator('.compact-hive').count(),0);
    await page.getByRole('button',{name:'Hide agents'}).click();
    await page.setViewportSize({width:390,height:844});
    await page.waitForSelector('.agents-panel');
    assert.equal(await page.locator('#agent-sidebar').isVisible(),false);
    assert.equal(await page.locator('canvas').count(),0);
    await page.setViewportSize({width:1440,height:900});
    await page.waitForSelector('canvas');
    assert.equal(await page.locator('.compact-hive').count(),0);
    await page.waitForFunction(()=>!!window.__hive);
    assert.equal(await page.locator('#agent-sidebar').isVisible(),false);
    assert.equal(await page.locator('canvas').count(),1);
    assert.deepEqual(errors,[]);
  } finally {await page.close();}
});

test('home-screen app gets a reload button; a browser tab does not', async () => {
  const { page, errors } = await setup(390, 844);
  try {
    await page.goto(base);
    await page.waitForSelector('.stage');
    assert.equal(await page.locator('header.top .reload').count(), 0);
    // iOS marks a page opened from the home screen with navigator.standalone.
    await page.addInitScript(() => Object.defineProperty(navigator, 'standalone', { value: true }));
    await page.reload();
    await page.waitForSelector('.stage');
    await fit(page);
    await page.evaluate(() => { window.beforeReload = true; });
    await page.locator('header.top .reload').click();
    await page.waitForSelector('.stage');
    assert.equal(await page.evaluate(() => window.beforeReload), undefined);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('a send whose answer is lost is retried under the same id, not duplicated', async () => {
  const { page, errors } = await setup(390, 844);
  const ids = [];
  await page.route('**/owner/send', async route => {
    ids.push(route.request().postDataJSON().client_id);
    // The first answer is lost on the way back; the retry gets the server's word.
    if (ids.length === 1) return route.abort('connectionreset');
    await route.fulfill({ json: { ok: true, status: 'delivered', message_id: 1 } });
  });
  try {
    await page.goto(base + '#/agent/stoat');
    const box = page.locator('form.composer textarea').first();
    await box.fill('airplane wifi');
    await box.press('Enter');
    await page.waitForFunction(() => document.querySelector('form.composer [role=status]')?.textContent === 'delivered', null, { timeout: 8000 });
    assert.equal(ids.length, 2);
    assert.ok(ids[0] && ids[0] === ids[1]);
    assert.equal(await box.inputValue(), '');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('a conversation expands to fill the window and back (button, shortcut, Esc)', async () => {
  const { page, errors } = await setup(1500, 900, false);
  try {
    await page.goto(base + '#/agent/stoat');
    await page.waitForSelector('.thread');
    const history = page.locator('.thread .msgs').first();
    const before = (await history.boundingBox()).height;
    // Messages and the reply box share one size.
    const size = sel => page.locator(sel).first().evaluate(e => getComputedStyle(e).fontSize);
    assert.equal(await size('.thread .msg .bubble'), '14px');
    assert.equal(await size('.thread .composer textarea'), '14px');
    await page.locator('.thread-focus').first().click();
    assert.equal(await page.locator('.thread.focused').count(), 1);
    assert.ok((await history.boundingBox()).height > before + 50);  // the default is already ~2/3 of the window
    const bubble = page.locator('.thread.focused .msg .bubble').first();
    const font = () => bubble.evaluate(e => getComputedStyle(e).fontSize);
    assert.equal(await font(), '16px');
    await page.getByRole('button', { name: 'Larger text' }).click();
    assert.equal(await font(), '18px');
    await page.getByRole('button', { name: 'Smaller text' }).click();
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.thread.focused').count(), 0);
    await page.keyboard.press('Control+Shift+L');
    assert.equal(await page.locator('.thread.focused').count(), 1);
    // Typing "f" into the composer is text, not the shortcut.
    const box = page.locator('.thread.focused textarea').first();
    await box.focus();
    await page.keyboard.type('f');
    assert.equal(await box.inputValue(), 'f');
    assert.equal(await page.locator('.thread.focused').count(), 1);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

for (const [width, height] of [[320,568], [390,844], [430,932], [844,390]]) {
  test(`mobile focused chat gives messages most of the screen at ${width}x${height}`, async () => {
    const { page, state, errors } = await setup(width, height);
    state.messages.push({ id: 3, sender: names[1], recipient: 'owner', content: 'A long agent handle should leave room for messages.', ts: state.now, status: 'delivered' });
    try {
      await page.goto(base + `#/agent/${names[1]}`);
      await page.getByRole('button', { name: 'Focus conversation', exact: true }).first().tap();
      const chat = page.locator('.thread.focused');
      const history = await chat.locator('.msgs').boundingBox();
      const header = await chat.locator('.thread-head').boundingBox();
      const composer = await chat.locator('.composer').boundingBox();
      assert.ok(history.height > height * (width > height ? .7 : .75), `history only ${history.height}/${height}px`);
      assert.ok(header.height <= 56, `header takes ${header.height}px`);
      assert.ok(composer.height <= 80, `empty composer takes ${composer.height}px`);
      assert.ok(Math.abs(composer.y + composer.height - height) <= 1);
      assert.equal(await chat.locator('.composer .context').isVisible(), false);
      assert.equal(await chat.getByRole('button', {name:'+ attach files', exact:true}).isVisible(), false);
      assert.equal(await chat.locator('.focus-key-hint').isVisible(), false);
      assert.equal(await chat.locator('.composer textarea').evaluate(e => document.activeElement === e), false);
      const overflow = await chat.evaluate(e => e.scrollWidth > e.clientWidth || e.scrollHeight > e.clientHeight);
      assert.equal(overflow, false);
      for (let i = 0; i < 5; i++) await chat.getByRole('button', {name:'Larger text'}).tap();
      await chat.locator('textarea').fill('Hi');
      const input = await chat.locator('textarea').evaluate(e => ({
        font: getComputedStyle(e).fontSize, height: e.clientHeight, content: e.scrollHeight,
      }));
      assert.equal(input.font, '26px');
      assert.ok(input.content <= input.height + 1, 'large text is clipped inside the composer');
      await chat.getByRole('button', { name: 'Close focused conversation' }).tap();
      assert.equal(await page.locator('.thread.focused').count(), 0);
      assert.equal(await page.locator('.thread .composer .context').first().isVisible(), true);
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });
}

test('focused mobile chat keeps attachments, context, drafts and send accessible', async () => {
  const { page, errors } = await setup(390,844);
  const sent = [];
  await page.route('**/attachments', r => r.fulfill({json:{name:file}}));
  await page.route('**/owner/send', async r => {
    sent.push(r.request().postDataJSON());
    await r.fulfill({json:{ok:true,status:'delivered',message_id:3}});
  });
  try {
    await page.goto(base + '#/agent/stoat');
    const draft = page.locator('.thread .composer textarea').first();
    await draft.fill('Keep this draft when focusing.');
    await page.getByRole('button', {name:'Focus conversation', exact:true}).first().tap();
    const chat = page.locator('.thread.focused');
    const composer = chat.locator('.composer');
    assert.equal(await composer.locator('textarea').inputValue(), 'Keep this draft when focusing.');
    const options = composer.getByRole('button', {name:'Message options'});
    await options.tap();
    assert.equal(await options.getAttribute('aria-expanded'), 'true');
    assert.equal(await composer.getByRole('button', {name:'+ attach files', exact:true}).isVisible(), true);
    await composer.getByRole('textbox', {name:'Optional context tag'}).fill('mobile-review');
    await composer.locator('input[type=file]').setInputFiles({name:'review.txt',mimeType:'text/plain',buffer:Buffer.from('chat layout')});
    await composer.getByRole('button', {name:/Remove/}).waitFor();
    await options.tap();
    assert.equal(await composer.getByRole('button', {name:/Remove/}).isVisible(), true);
    await composer.getByRole('button', {name:'send', exact:true}).tap();
    await composer.getByRole('status').filter({hasText:'delivered'}).waitFor();
    assert.equal(sent.length, 1);
    assert.equal(sent[0].content, 'Keep this draft when focusing.');
    assert.equal(sent[0].context, 'mobile-review');
    assert.deepEqual(sent[0].attachments, [file]);
    assert.equal(await composer.locator('textarea').inputValue(), '');
    assert.equal(await options.getAttribute('aria-expanded'), 'false');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('mobile focused composer follows a resized and panned visual viewport', async () => {
  const { page, errors } = await setup(390,844);
  try {
    await page.goto(base + '#/agent/stoat');
    await page.getByRole('button', {name:'Focus conversation', exact:true}).first().tap();
    await page.locator('.thread.focused textarea').fill('Typing with the keyboard open');
    // Model the viewport events iOS emits when its software keyboard opens.
    await page.evaluate(() => {
      Object.defineProperty(visualViewport, 'height', {configurable:true, value:420});
      Object.defineProperty(visualViewport, 'offsetTop', {configurable:true, value:24});
      visualViewport.dispatchEvent(new Event('resize'));
      visualViewport.dispatchEvent(new Event('scroll'));
    });
    const chat = await page.locator('.thread.focused').boundingBox();
    const composer = await page.locator('.thread.focused .composer').boundingBox();
    assert.equal(chat.y, 24);
    assert.equal(chat.height, 420);
    assert.ok(Math.abs(composer.y + composer.height - 444) <= 1);
    assert.ok((await page.locator('.thread.focused .msgs').boundingBox()).height > 250);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('desktop: the roster runs to the top and the header stops at its edge', async () => {
  const { page, errors } = await setup(1500, 900, false);
  try {
    await page.goto(base + '#/agent/stoat');
    await page.waitForSelector('.roster-drawer.is-open');
    const roster = await page.locator('.roster-drawer').boundingBox();
    const header = await page.locator('header.top').boundingBox();
    assert.ok(roster.y <= 1);
    assert.ok(header.x + header.width <= roster.x + 1);
    // The roster's own "Hide →" closes it; the floating tab would cover content.
    assert.equal(await page.locator('.roster-toggle').isVisible(), false);
    await page.getByRole('button', { name: 'Hide agents' }).click();
    await page.locator('.roster-toggle').click();
    await page.waitForSelector('.roster-drawer.is-open');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('owner messages sit on the right of a 1:1 thread, the agent on the left', async () => {
  const { page, errors } = await setup(1500, 900, false);
  try {
    await page.goto(base + '#/agent/stoat');
    await page.waitForSelector('.thread .msg');
    const sides = await page.locator('.thread .msg').first().locator('..').locator('.msg').evaluateAll(els =>
      els.map(e => [e.querySelector('.tag').textContent.split('·')[0].trim(), e.classList.contains('right')]));
    assert.ok(sides.length >= 2);
    for (const [who, right] of sides) assert.equal(right, who === 'owner', `${who} on the wrong side`);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('agent page: sections have headings; status history and the task form start folded', async () => {
  const { page, errors } = await setup(1500, 900, false);
  try {
    await page.goto(base + '#/agent/stoat');
    await page.waitForSelector('.thread');
    const headings = await page.locator('.stage h2').evaluateAll(hs => hs.map(h => h.textContent.trim().split(/\s/)[0].toLowerCase()));
    assert.deepEqual(headings.slice(0, 3), ['status', 'conversations', 'tasks']);
    // Only the newest status shows until the history is opened.
    assert.ok(await page.locator('.doing-box .now').isVisible());
    const past = page.locator('.status-history .past');
    assert.equal(await past.isVisible(), false);
    assert.equal(await page.locator('.status-history > summary').innerText(), '1 earlier update');
    await page.locator('.status-history > summary').click();
    assert.equal(await past.isVisible(), true);
    const form = page.locator('.task-compose-fold .task-composer');
    assert.equal(await form.isVisible(), false);
    await page.locator('.task-compose-fold > summary').click();
    assert.equal(await form.isVisible(), true);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('team strip and Alt+] / Alt+[ switch teammates, keeping the draft and the cursor', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  state.messages.push(
    { id: 3, sender: 'numbat-claude-opus-karansmbp', recipient: 'stoat', content: 'peer note', ts: state.now, status: 'delivered', attachments: [] });
  try {
    await page.goto(base + '#/agent/stoat');
    await page.waitForSelector('.team-strip');
    assert.equal(await page.locator('.team-strip .team-mate').count(), 3);
    assert.equal(await page.locator('.team-strip .team-mate.here').innerText().then(t => t.trim().split(/\s/)[0]), 'stoat');
    const box = page.locator('.thread .composer textarea').first();
    await box.fill('draft for stoat');
    await box.focus();
    await page.keyboard.press('Alt+BracketRight');
    await page.waitForFunction(() => location.hash === '#/agent/hoopoe-codex-gpt5-karanslinux');
    // A changed URL can still have the previous agent's focused composer.
    // Wait for the destination page before sending the next shortcut.
    await page.waitForFunction(() => document.querySelector('.fhead .nm')?.textContent.startsWith('hoopoe-codex-gpt5-karanslinux'));
    await page.waitForFunction(() => !!document.activeElement?.closest('.thread .composer'));
    await page.keyboard.press('Alt+BracketLeft');
    await page.waitForFunction(() => location.hash === '#/agent/stoat');
    await page.waitForFunction(() => document.querySelector('.thread .composer textarea')?.value === 'draft for stoat');
    // A conversation between two agents links to the other agent's page.
    await page.getByRole('button', {name:'Show agent chats', exact:true}).click();
    await page.locator('.thread-goto').click();
    await page.waitForFunction(() => location.hash === '#/agent/numbat-claude-opus-karansmbp');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('Alt+H goes back to the overview from any page, keeping the draft', async () => {
  const { page, errors } = await setup(1500, 900, false);
  try {
    await page.goto(base + '#/agent/stoat');
    const box = page.locator('.thread .composer textarea').first();
    await box.fill('draft for stoat');
    await box.focus();
    await page.keyboard.press('Alt+KeyH');
    await page.waitForFunction(() => location.hash === '#/');
    await page.waitForSelector('.harness-legend');
    await page.goto(base + '#/agent/stoat');
    await page.waitForFunction(() => document.querySelector('.thread .composer textarea')?.value === 'draft for stoat');
    await page.goto(base + '#/chats');
    await page.waitForSelector('nav.views a.on');
    await page.keyboard.press('Alt+KeyH');
    await page.waitForFunction(() => location.hash === '#/');
    // An open agent switcher keeps its keys.
    await page.goto(base + '#/agent/stoat');
    await page.waitForSelector('.thread .composer textarea');
    await page.keyboard.press('Control+KeyK');
    await page.waitForSelector('.quick-switch[open]');
    await page.keyboard.press('Alt+KeyH');
    assert.equal(await page.evaluate(() => location.hash), '#/agent/stoat');
    assert.equal(await page.locator('nav.views a[href="#/"]').getAttribute('title'), 'Overview (Alt+H)');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('a tab from AGENT_SWARM_TABS shows its page and passes shortcuts up', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  state.tabs = ['usage'];
  await page.route('**/tabs/usage/', r => r.fulfill({ contentType: 'text/html', body: '<!doctype html><title>AI Usage</title><h1>AI usage</h1><input id=q>' }));
  try {
    await page.goto(base + '#/');
    await page.locator('nav.views a', { hasText: 'usage' }).click();
    await page.waitForFunction(() => location.hash === '#/tab/usage');
    assert.equal(await page.locator('nav.views a.on').textContent(), 'usage');
    const frame = page.frameLocator('iframe.tab-frame');
    assert.equal(await frame.locator('h1').innerText(), 'AI usage');
    assert.ok(await page.locator('iframe.tab-frame').evaluate(e => e.getBoundingClientRect().height >= 480));
    // Alt+H typed inside the page still goes home.
    await frame.locator('#q').click();
    await page.keyboard.press('Alt+KeyH');
    await page.waitForFunction(() => location.hash === '#/');
    // A tab the hub no longer lists explains where tabs come from.
    await page.goto(base + '#/tab/gone');
    await page.waitForSelector('text=AGENT_SWARM_TABS');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});


for (const width of [390, 1500]) {
  test(`configured Usage and PR tabs follow built-ins and load their own pages at ${width}px`, async () => {
    const { page, state, errors } = await setup(width, 900, width < 500);
    state.tabs = ['usage', 'prs'];
    const loads = [];
    await page.route('**/tabs/*/**', async route => {
      const path = new URL(route.request().url()).pathname;
      loads.push(path);
      const name = path.split('/')[2];
      if (path.endsWith('api/data')) return route.fulfill({json: {name}});
      if (path.endsWith('style.css')) return route.fulfill({contentType:'text/css',body:'h1 { color: rgb(1, 2, 3); }'});
      return route.fulfill({contentType:'text/html',body:`<!doctype html><link rel="stylesheet" href="style.css"><h1>${name}</h1><output></output><input id=q><script>fetch('api/data').then(r=>r.json()).then(d=>document.querySelector('output').textContent=d.name)</script>`});
    });
    try {
      await page.goto(base + '#/');
      // The first assertion reads the nav as soon as it exists; without this
      // wait a loaded machine can read it a beat before the tabs render.
      await page.waitForSelector('nav.views a[href="#/tab/usage"]');
      assert.deepEqual(await page.locator('nav.views a').allTextContents(), ['overview', 'chats', 'task history', 'usage', 'prs']);
      for (const name of ['usage', 'prs']) {
        await page.locator(`nav.views a[href="#/tab/${name}"]`).click();
        const frame = page.frameLocator('iframe.tab-frame');
        await frame.locator('output').filter({hasText:name}).waitFor();
        assert.equal(await frame.locator('h1').innerText(), name);
        assert.equal(await frame.locator('h1').evaluate(e=>getComputedStyle(e).color), 'rgb(1, 2, 3)');
        assert.equal(await page.locator('.tab-bar a').getAttribute('href'), `/tabs/${name}/`);
        assert.ok(loads.includes(`/tabs/${name}/api/data`));
        assert.ok(loads.includes(`/tabs/${name}/style.css`));
      }
      await page.reload();
      await page.frameLocator('iframe.tab-frame').getByRole('heading', {name:'prs',exact:true}).waitFor();
      assert.equal(await page.locator('nav.views a.on').textContent(), 'prs');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth), width);
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });
}

test('Ctrl+Shift+[ / ] step through the header views, including extra tabs', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  state.tabs = ['usage'];
  await page.route('**/tabs/usage/', r => r.fulfill({ contentType: 'text/html', body: '<!doctype html><input id=q>' }));
  try {
    await page.goto(base + '#/agent/stoat');
    const box = page.locator('.thread .composer textarea').first();
    await box.focus();
    const go = async (key, hash) => {
      await page.keyboard.press(key);
      await page.waitForFunction(h => location.hash === h, hash);
    };
    await go('Control+Shift+BracketRight', '#/chats');
    await go('Control+Shift+BracketRight', '#/tasks');
    await go('Control+Shift+BracketRight', '#/tab/usage');
    // From inside the tab's page too.
    await page.frameLocator('iframe.tab-frame').locator('#q').click();
    await go('Control+Shift+BracketRight', '#/');
    await go('Control+Shift+BracketLeft', '#/tab/usage');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('offline agents show per team and can be retired, there or from their page', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  const ghost = { user_id: 'old-ghost', node: 'karans-linux', flavor: 'claude', pane_alive: false, team_id: 1, registered_at: state.now - 9000, summaries: [] };
  state.recipients.push(ghost);
  const asked = [];
  await page.route('**/recipients/retire', async r => {
    const ids = r.request().postDataJSON().user_ids;
    asked.push(ids);
    state.recipients = state.recipients.filter(x => !ids.includes(x.user_id));
    await r.fulfill({ json: { ok: true, retired: ids, kept_live: [], unknown: [] } });
  });
  try {
    await page.goto(base + '#/');
    const team = page.locator('#agent-sidebar .team-bees-group', { hasText: 'agent-swarm' });
    await team.locator('.team-bees-offline', { hasText: '1 offline: old-ghost' }).waitFor();
    await team.locator('button.retire').click();
    const question = await answer(page);
    await page.locator('#agent-sidebar .team-bees-offline', { hasText: 'old-ghost' }).waitFor({ state: 'detached' });
    assert.deepEqual(asked, [['old-ghost']]);
    assert.match(question, /Retire old-ghost\? It leaves the dashboard and its team\. Messages and tasks are kept, but a retired agent can no longer be resumed\./);
    // A stopped agent's own page offers retire instead of stop.
    await page.goto(base + '#/agent/stopped-agent');
    await page.locator('.fhead button.retire', { hasText: 'retire agent' }).click();
    await answer(page);
    await page.waitForFunction(() => location.hash === '#/');
    assert.deepEqual(asked[1], ['stopped-agent']);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('a stopped agent can be resumed from its page', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  const asked = [];
  await page.route('**/agents/*/resume', async r => {
    asked.push(r.request().url());
    if (asked.length === 1) return r.fulfill({ status: 409, json: { detail: { error: 'the hub does not know which folder stopped-agent ran in' } } });
    state.recipients.find(x => x.user_id === 'stopped-agent').pane_alive = true;
    await r.fulfill({ json: { ok: true, user_id: 'stopped-agent', pane_label: 'agents:7.0', cwd: '/home/k/agents', launch: 'ok' } });
  });
  try {
    await page.goto(base + '#/agent/stopped-agent');
    const resume = page.locator('.fhead').getByRole('button', { name: 'resume agent', exact: true });
    await resume.click();
    await page.getByText('Could not resume: the hub does not know which folder stopped-agent ran in', { exact: true }).waitFor();
    await resume.click();
    // Running again: the page offers stop, not resume.
    await page.locator('.fhead .stop-agent').waitFor();
    assert.equal(await resume.count(), 0);
    assert.equal(asked.length, 2);
    assert.match(asked[0], /\/agents\/stopped-agent\/resume$/);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('the first message to an agent clears the composer', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  await page.route('**/owner/send', async route => {
    const body = route.request().postDataJSON();
    state.messages.push({ id: 50, sender: 'owner', recipient: body.recipient, content: body.content, ts: state.now, status: 'delivered', attachments: [] });
    await route.fulfill({ json: { ok: true, status: 'delivered', message_id: 50 } });
  });
  try {
    // hoopoe has no conversation with the owner yet: the page shows a lone composer.
    await page.goto(base + '#/agent/hoopoe-codex-gpt5-karanslinux');
    const box = page.locator('.thread .composer textarea').first();
    await box.fill('first line\n\nsecond paragraph');
    await box.press('Enter');
    await page.waitForFunction(() => document.querySelector('.thread .composer [role=status]')?.textContent === 'delivered');
    assert.equal(await page.locator('.thread .composer textarea').first().inputValue(), '');
    assert.equal(await page.evaluate(() => localStorage.getItem('agent-swarm:draft:hoopoe-codex-gpt5-karanslinux:thread')), null);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});


for (const width of [390, 1500]) {
  test(`agent detail at ${width}px reveals peer chats only on request and keeps the owner draft`, async () => {
    const { page, state, errors } = await setup(width, 900, width < 500);
    state.messages.push(
      {id:70,sender:'stoat',recipient:'ferret',content:'peer conversation',ts:state.now,status:'delivered'},
      {id:71,sender:'stoat',recipient:'stoat',content:'private reminder',ts:state.now,status:'delivered'});
    try {
      await page.goto(base + '#/agent/stoat');
      const show = page.getByRole('button', {name:'Show agent chats',exact:true});
      await show.waitFor();
      assert.equal(await show.getAttribute('aria-expanded'), 'false');
      assert.equal(await page.locator('.thread').count(), 1);
      assert.equal(await page.locator('.thread-goto').count(), 0);
      const draft = page.locator('.thread .composer textarea');
      await draft.fill('keep my draft');
      const owner = await page.locator('.thread').evaluate(e => { e.dataset.ownerLifetime='kept'; return true; });
      assert.ok(owner);
      await show.click();
      const hide = page.getByRole('button', {name:'Hide agent chats',exact:true});
      assert.equal(await hide.getAttribute('aria-expanded'), 'true');
      assert.equal(await page.locator('.thread').count(), 3);
      assert.equal(await page.locator('.thread-goto').count(), 1);
      assert.equal(await draft.inputValue(), 'keep my draft');
      assert.equal(await page.locator('.thread').first().getAttribute('data-owner-lifetime'), 'kept');
      await hide.click();
      assert.equal(await page.locator('.thread').count(), 1);
      assert.equal(await draft.inputValue(), 'keep my draft');
      // Polling in more peer traffic must not reopen it.
      state.messages.push({id:72,sender:'tapir',recipient:'stoat',content:'new peer',ts:state.now+1,status:'delivered'});
      await page.waitForFunction(() => document.querySelector('.agent-chats-toggle').textContent.includes('3'));
      assert.equal(await page.locator('.thread').count(), 1);
      assert.equal(await show.getAttribute('aria-expanded'), 'false');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth), width);
      // Reload and another agent's page both start hidden again.
      await page.reload();
      await page.getByRole('button', {name:'Show agent chats',exact:true}).waitFor();
      assert.equal(await page.locator('.thread').count(), 1);
      await page.getByRole('button', {name:'Show agent chats',exact:true}).click();
      await page.goto(base + '#/agent/ferret');
      await page.getByRole('button', {name:'Show agent chats',exact:true}).waitFor();
      assert.equal(await page.locator('.thread').count(), 1);
      assert.equal(await page.locator('.composer textarea').count(), 1);
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });
}

test("between two agents, the page's agent sits on the right", async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  const peer = 'numbat-claude-opus-karansmbp';
  state.messages.push(
    { id: 70, sender: 'stoat', recipient: peer, content: 'from stoat', ts: state.now, status: 'delivered', attachments: [] },
    { id: 71, sender: peer, recipient: 'stoat', content: 'from numbat', ts: state.now, status: 'delivered', attachments: [] },
    { id: 72, sender: 'stoat', recipient: 'stoat', content: 'note to self', ts: state.now, status: 'delivered', attachments: [] },
    { id: 73, sender: 'hub', recipient: 'stoat', context: 'digest', content: 'Since your last digest: 1 new message(s).', ts: state.now, status: 'delivered', attachments: [] });
  const sides = () => page.locator('.thread .msg').evaluateAll(els => Object.fromEntries(
    els.map(e => [e.querySelector('.md')?.textContent.trim(), e.classList.contains('right')])));
  try {
    await page.goto(base + '#/agent/stoat');
    await page.getByRole('button', {name:'Show agent chats', exact:true}).click();
    await page.waitForSelector('.thread-goto');
    let s = await sides();
    assert.equal(s['from stoat'], true);
    assert.equal(s['from numbat'], false);
    // A thread with itself, or with the hub (supervisor nudges), has no agent page to open.
    assert.equal(await page.locator('.thread-goto').count(), 1);
    await page.goto(base + '#/agent/' + peer);
    await page.getByRole('button', {name:'Show agent chats', exact:true}).click();
    await page.waitForSelector('.thread-goto');
    s = await sides();
    assert.equal(s['from numbat'], true);
    assert.equal(s['from stoat'], false);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('a message sent with literal \\n from the shell shows line breaks', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  state.messages.push({ id: 60, sender: 'stoat', recipient: 'owner', ts: state.now, status: 'delivered', attachments: [],
    content: 'checkpoint:\\n\\ns3://bucket/step-272\\nResults: ok' });
  try {
    await page.goto(base + '#/agent/stoat');
    await page.waitForSelector('.thread .msg');
    const bubble = page.locator('.thread .msg .md').last();
    assert.equal(await bubble.locator('p').count(), 2);
    assert.ok(!(await bubble.innerText()).includes('\\n'));
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('two quick Alt+] presses step two teammates', async () => {
  const { page, errors } = await setup(1500, 900, false);
  try {
    await page.goto(base + '#/agent/stoat');
    await page.waitForSelector('.team-strip');
    // The second press comes before the first switch has rendered.
    await page.keyboard.press('Alt+BracketRight');
    await page.keyboard.press('Alt+BracketRight');
    await page.waitForFunction(() => location.hash === '#/agent/numbat-claude-opus-karansmbp');
    await page.waitForTimeout(300);
    assert.equal(await page.evaluate(() => location.hash), '#/agent/numbat-claude-opus-karansmbp');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('chats tab lists owner conversations newest first and searches them', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  state.messages.push(
    { id: 80, sender: 'owner', recipient: 'tapir', content: 'what about the zephyr reducers?', ts: state.now + 5, status: 'delivered', attachments: [] },
    { id: 81, sender: 'tapir', recipient: 'stoat', content: 'peer only', ts: state.now + 6, status: 'delivered', attachments: [] });
  try {
    await page.goto(base + '#/chats');
    await page.waitForSelector('.chat-row');
    const who = () => page.locator('.chat-who').evaluateAll(els => els.map(e => e.childNodes[0].textContent.trim()));
    assert.deepEqual(await who(), ['tapir', 'stoat']);
    await page.locator('.chats-search').fill('Zephyr');
    await page.waitForFunction(() => document.querySelectorAll('.chat-row').length === 1);
    assert.deepEqual(await who(), ['tapir']);
    assert.equal(await page.evaluate(() => location.hash), '#/chats?q=Zephyr');
    await page.locator('.chat-row').click();
    await page.waitForFunction(() => location.hash === '#/agent/tapir');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});


for (const width of [320, 1500]) {
  test(`queen chats at ${width}px filter current leads, search history, and survive reload`, async () => {
    const { page, state, errors } = await setup(width, 900, width < 500);
    state.teams.push(
      { id: 2, name: 'research', queen: 'tapir', members: ['tapir'] },
      { id: 3, name: 'another team', queen: 'stoat', members: ['stoat'] },
      { id: 4, name: 'leaderless', queen: null, members: ['ferret'] });
    state.recipients.find(a => a.user_id === 'tapir').pane_alive = false;
    state.messages.push({ id: 80, sender: 'owner', recipient: 'ferret', content: 'member conversation', ts: state.now + 10, status: 'delivered', attachments: [] });
    const history = { id: 81, sender: 'tapir', recipient: 'owner', content: 'Zephyr research report', ts: state.now - 100, status: 'delivered', attachments: [] };
    await page.route('**/messages?user=owner&limit=*', route => route.fulfill({ json: { messages: [history] } }));
    const who = () => page.locator('.chat-who').evaluateAll(els => els.map(e => e.childNodes[0].textContent.trim()));
    try {
      await page.goto(base + '#/chats');
      const switches = page.getByRole('group', { name: 'Which chats' });
      // Read the switch buttons only once they exist: a loaded machine can
      // otherwise snapshot the page mid-render.
      await switches.getByRole('button').first().waitFor();
      assert.deepEqual(await switches.getByRole('button').allTextContents(), ['with you', 'you and queens', 'between agents']);
      const buttons = await switches.getByRole('button').evaluateAll(bs => bs.map(b => {
        const r = b.getBoundingClientRect(); return { x: r.x, y: r.y, height: r.height };
      }));
      assert.ok(buttons.every(b => b.y === buttons[0].y));
      assert.ok(buttons[0].x < buttons[1].x && buttons[1].x < buttons[2].x);
      if (width < 500) assert.ok(buttons.every(b => b.height >= 44));
      await switches.getByRole('button', { name: 'you and queens', exact: true }).click();
      await page.waitForFunction(() => document.querySelectorAll('.chat-row').length === 2);
      assert.deepEqual(await who(), ['stoat', 'tapir']);
      assert.equal(await page.locator('.chat-row').nth(1).getAttribute('href'), '#/agent/tapir');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width);
      await page.getByRole('textbox', { name: 'Search your conversations with queens', exact: true }).fill('Zephyr');
      await page.waitForFunction(() => document.querySelectorAll('.chat-row').length === 1);
      assert.deepEqual(await who(), ['tapir']);
      assert.equal(await page.evaluate(() => location.hash), '#/chats?view=queens&q=Zephyr');
      await page.reload();
      await page.waitForSelector('.chat-row');
      assert.deepEqual(await who(), ['tapir']);
      assert.equal(await page.getByRole('button', { name: 'you and queens', exact: true }).getAttribute('aria-pressed'), 'true');
      assert.equal(await page.locator('.chats-search').inputValue(), 'Zephyr');
      await page.locator('.chats-search').press('Escape');
      assert.equal(await page.evaluate(() => location.hash), '#/chats?view=queens');
      // A new queen replaces the old one on the ordinary state poll, even with history loaded.
      state.teams[1].queen = 'ferret';
      await page.waitForFunction(() => [...document.querySelectorAll('.chat-who')].some(e => e.textContent.includes('ferret')));
      assert.deepEqual(await who(), ['ferret', 'stoat']);
      await switches.getByRole('button', { name: 'with you', exact: true }).click();
      await page.waitForFunction(() => document.querySelectorAll('.chat-row').length === 3);
      assert.deepEqual(await who(), ['ferret', 'stoat', 'tapir']);
      assert.equal(await page.evaluate(() => location.hash), '#/chats');
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });
}


for (const width of [390, 1500]) {
  test(`failed owner message retry at ${width}px preserves payload, reports failure, then sends`, async () => {
    const { page, state, errors } = await setup(width, 900, width < 500);
    const failed = { id: 80, sender: 'owner', recipient: 'stoat', content: 'Please review the attached plan', context: 'review', attachments: [file, image], reply_to: 1, reply_preview: { id: 1, sender: 'owner', content: 'original request' }, status: 'failed', delivery_error: 'pane vanished', ts: state.now + 1 };
    state.messages.push(failed, { id: 81, sender: 'stoat', recipient: 'owner', content: 'incoming historical failure', status: 'failed', ts: state.now + 2 });
    const requests = [];
    let release;
    const held = new Promise(resolve => { release = resolve; });
    await page.route('**/owner/send', async route => {
      const body = route.request().postDataJSON();
      requests.push(body);
      if (requests.length === 1) {
        await held;
        return route.fulfill({ json: { ok: false, status: 'failed', message_id: 82, delivery_error: 'still offline' } });
      }
      state.messages.push({ ...failed, id: 83, status: 'delivered', delivery_error: null, ts: state.now + 3 });
      await route.fulfill({ json: { ok: true, status: 'delivered', message_id: 83 } });
    });
    try {
      await page.goto(base + '#/agent/stoat');
      const row = page.locator('[data-message-id="80"]');
      const retry = row.getByRole('button', { name: 'Retry message 80', exact: true });
      await retry.waitFor();
      assert.equal(await retry.textContent(), 'retry');
      assert.equal(await page.locator('[data-message-id="81"] .resend').count(), 0);
      await retry.click();
      assert.equal(await retry.isDisabled(), true);
      assert.equal(await retry.textContent(), 'sending…');
      assert.equal(await page.locator('dialog[open]').count(), 0);
      release();
      await row.getByRole('status').waitFor();
      assert.match(await row.getByRole('status').textContent(), /failed: still offline/);
      assert.equal(await retry.isEnabled(), true);
      await retry.click();
      await page.locator('[data-message-id="83"]').waitFor();
      // The poll can show delivery before this request's receipt settles.
      await page.waitForFunction(() => document.querySelector('[data-message-id="80"] .resend').textContent === 'sent');
      assert.equal(await retry.textContent(), 'sent');
      assert.equal(await retry.isDisabled(), true);
      assert.equal(requests.length, 2);
      const {client_id, ...payload} = requests[0];
      assert.match(client_id, /^[a-f0-9]{32}$/);
      assert.deepEqual(payload, { recipient: 'stoat', content: failed.content, context: 'review', attachments: [file, image], reply_to: 1 });
      assert.deepEqual(requests[1], requests[0]);
      assert.equal(await page.locator('[data-message-id="83"] .resend').count(), 0);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width);
      assert.deepEqual(errors, []);
    } finally { release(); await page.close(); }
  });
}

test('failed message retry reuses its attempt id after an unreadable response', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  state.messages.push({ id: 80, sender: 'owner', recipient: 'stoat', content: 'retry once', status: 'failed', ts: state.now + 1 });
  const requests = [];
  await page.route('**/owner/send', async route => {
    requests.push(route.request().postDataJSON());
    if (requests.length === 1) return route.fulfill({ status: 200, body: '{', contentType: 'application/json' });
    await route.fulfill({ json: { ok: true, status: 'delivered', message_id: 82 } });
  });
  try {
    await page.goto(base + '#/agent/stoat');
    const row = page.locator('[data-message-id="80"]');
    const retry = row.getByRole('button', { name: 'Retry message 80', exact: true });
    await retry.click();
    await row.getByRole('status').waitFor();
    assert.match(await row.getByRole('status').textContent(), /uncertain:.*could not be read/);
    await retry.click();
    await page.waitForFunction(() => document.querySelector('[data-message-id="80"] .resend').textContent === 'sent');
    assert.equal(requests.length, 2);
    assert.equal(requests[1].client_id, requests[0].client_id);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('unknown delivery still requires confirmation before sending again', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  state.messages.push({ id: 80, sender: 'owner', recipient: 'stoat', content: 'possibly already sent', status: 'unknown', delivery_error: 'connection lost', ts: state.now + 1 });
  const requests = [];
  await page.route('**/owner/send', async route => {
    requests.push(route.request().postDataJSON());
    await route.fulfill({ json: { ok: true, status: 'delivered', message_id: 82 } });
  });
  try {
    await page.goto(base + '#/agent/stoat');
    const resend = page.locator('[data-message-id="80"] .resend');
    await resend.click();
    assert.match(await answer(page, 'Cancel'), /agent may already have it/);
    assert.equal(requests.length, 0);
    await resend.click();
    await answer(page);
    await page.waitForFunction(() => document.querySelector('[data-message-id="80"] .resend').textContent === 'sent');
    assert.equal(requests.length, 1);
    assert.equal(requests[0].content, 'possibly already sent');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('queen chats show an empty state when no team has a queen', async () => {
  const { page, state, errors } = await setup(390, 844);
  state.teams[0].queen = null;
  try {
    await page.goto(base + '#/chats?view=queens');
    await page.getByText('No conversations with current team queens yet.', { exact: true }).waitFor();
    assert.equal(await page.locator('.chat-row').count(), 0);
    assert.equal(await page.getByRole('button', { name: 'you and queens', exact: true }).getAttribute('aria-pressed'), 'true');
    await page.getByRole('button', { name: 'with you', exact: true }).click();
    await page.waitForSelector('.chat-row');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

// The crown is the one marker for a team queen. It belongs wherever an agent
// is listed or picked, and it reads from team data rather than from sort
// order, so a promotion or a cleared queen shows up on the next poll.
for (const width of [390, 1500]) {
  test(`a team queen wears a crown in every list and picker: ${width}`, async () => {
    const { page, state, errors } = await setup(width, 900, width < 500);
    const roster = width < 500 ? '.hive-panel' : '#agent-sidebar';
    const numbat = 'numbat-claude-opus-karansmbp';
    // A second team with no queen: the roster says so instead of staying silent.
    state.teams.push({ id: 2, name: 'leaderless', queen: null, members: ['jerboa'] });
    state.recipients.find(r => r.user_id === 'jerboa').team_id = 2;
    const crownCount = (scope) => page.locator(`${scope} .crown:not(.supervisor)`).count();
    const label = (name) => 'stoat · ♛ queen';
    try {
      await page.goto(base + '#/');
      await page.waitForSelector(`${roster} .team-bees`);
      // The roster chip and the team's own header both name the queen.
      assert.equal(await crownCount(`${roster} .team-mate[href="#/agent/stoat"]`), 1);
      assert.equal(await crownCount(`${roster} .team-mate[href="#/agent/${numbat}"]`), 0);
      assert.equal(await page.locator(`${roster} .team-bees-queen`).first().innerText(), '♛ stoat');
      assert.equal(await page.locator(`${roster} .team-bees-queen.none`).innerText(), 'no queen');

      // The tile grid.
      await page.locator(`${roster} .agents-view-switch button`, { hasText: 'tiles' }).click();
      await page.waitForSelector('.bee-tile');
      assert.equal(await crownCount('.bee-tile[href="#/agent/stoat"]'), 1);
      assert.equal(await crownCount(`.bee-tile[href="#/agent/${numbat}"]`), 0);
      await page.locator(`${roster} .agents-view-switch button`, { hasText: 'teams' }).click();

      // The agent switcher, in both its modes.
      await page.locator('.quick-switch-launchers > button').last().click();
      const dialog = page.getByRole('dialog', { name: 'Switch agent' });
      await dialog.waitFor();
      assert.equal(await crownCount('#switch-agent-stoat'), 1);
      assert.match(await dialog.locator('#switch-agent-stoat .crown-word').innerText(), /^queen$/i);
      assert.equal(await crownCount(`#switch-agent-${numbat}`), 0);
      await dialog.getByRole('button', { name: 'close' }).click();
      await page.locator('.quick-switch-launchers > button').first().click();
      const teamsDialog = page.getByRole('dialog', { name: 'Switch team' });
      await teamsDialog.waitFor();
      // A team row names the queen once, in the detail line, not also beside
      // the team name.
      assert.equal(await crownCount('#switch-team-1'), 0);
      assert.match(await teamsDialog.locator('#switch-team-1 small').first().innerText(), /opens stoat · ♛ queen/);
      assert.equal(await teamsDialog.locator('#switch-team-1 .crown-word').count(), 0);
      await teamsDialog.getByRole('button', { name: 'close' }).click();

      // Chat rows: a crown, plus the word "queen" where the row is not already
      // inside the "you and queens" list.
      await page.goto(base + '#/chats');
      await page.waitForSelector('.chat-row');
      assert.equal(await crownCount('.chat-row[href="#/agent/stoat"]'), 1);
      assert.match(await page.locator('.chat-row[href="#/agent/stoat"] .crown-word').innerText(), /^queen$/i);
      await page.getByRole('button', { name: 'you and queens', exact: true }).click();
      await page.waitForSelector('.chat-row');
      assert.equal(await crownCount('.chat-row[href="#/agent/stoat"]'), 1);
      assert.equal(await page.locator('.chat-row .crown-word').count(), 0);

      // The task board: the assignee line and the assignee menus.
      await page.goto(base + '#/');
      const card = page.locator('.col.picked_up .tcard').first();
      await card.waitFor();
      assert.equal(await crownCount('.col.picked_up .tcard .meta'), 1);
      assert.ok((await card.getByRole('combobox', { name: 'Assign task #73' }).locator('option').allTextContents()).includes(label()));
      assert.ok((await page.locator('.task-composer select[aria-label="Task assignee"] option').allTextContents()).some(t => t.startsWith(label())));

      // The hive task detail: the summary line and the agent picker.
      await page.locator('.hive-task-picker select').selectOption('73');
      const detail = page.locator('.hive-task-detail');
      await detail.waitFor();
      assert.match(await detail.locator('p').first().innerText(), /stoat · ♛ queen/);
      assert.ok((await detail.getByRole('combobox', { name: 'Assign task #73' }).locator('option').allTextContents()).includes(label()));

      // The agent's own page: the header, the teammate strip and its task rows.
      await page.goto(base + '#/agent/stoat');
      await page.waitForSelector('.fhead .nm .crown');
      assert.match(await page.locator('.fhead .nm .crown-word').innerText(), /^queen of agent-swarm$/i);
      assert.equal(await crownCount('.team-strip .team-mate[href="#/agent/stoat"]'), 1);
      assert.equal(await crownCount(`.team-strip .team-mate[href="#/agent/${numbat}"]`), 0);
      assert.ok((await page.locator('.trow select').first().locator('option').allTextContents()).includes(label()));

      // Task history: the tiles and the agent filter chips.
      await page.goto(base + '#/tasks');
      await page.waitForSelector('.htile');
      assert.equal(await crownCount('.htile'), 1);
      assert.equal(await crownCount('.h-agentchip'), 1);
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });
}

for (const width of [390, 1500]) {
  test(`the crown follows team data: promotion, clearing and an offline queen: ${width}`, async () => {
    const { page, state, errors } = await setup(width, 900, width < 500);
    const numbat = 'numbat-claude-opus-karansmbp';
    const crownCount = (scope) => page.locator(`${scope} .crown:not(.supervisor)`).count();
    try {
      await page.goto(base + '#/agent/stoat');
      await page.waitForSelector('.fhead .nm .crown');
      // A name that merely starts with the queen's name is not a queen.
      assert.equal(await crownCount(`.team-strip .team-mate[href="#/agent/${numbat}"]`), 0);

      // Promoted: the crown moves on the ordinary poll, without a reload.
      state.teams[0].queen = numbat;
      await page.waitForFunction(name => !!document.querySelector(`.team-strip .team-mate[href="#/agent/${name}"] .crown:not(.supervisor)`), numbat);
      assert.equal(await crownCount('.fhead .nm'), 0);

      // Cleared: every crown goes with it.
      state.teams[0].queen = null;
      await page.waitForFunction(() => !document.querySelector('.crown:not(.supervisor)'));
      assert.equal(await crownCount('body'), 0);

      // An offline queen keeps the crown: her team header still names her, and
      // she moves to the offline line rather than losing the role.
      state.teams[0].queen = 'stoat';
      state.recipients.find(r => r.user_id === 'stoat').pane_alive = false;
      await page.goto(base + '#/');
      await page.waitForFunction(() => !!document.querySelector('[title="queen of agent-swarm: stoat"]'));
      assert.equal(await page.locator('.team-bees-offline', { hasText: 'stoat' }).count(), 1);
      await page.goto(base + '#/agent/stoat');
      await page.waitForSelector('.fhead .nm .crown');
      assert.match(await page.locator('.fhead .nm .crown-word').innerText(), /^queen of agent-swarm$/i);
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });
}

test('chats tab: between agents groups talk into bursts and broadcasts, filters by team', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  const t = state.now;
  const talk = [
    { id: 90, sender: 'tapir', recipient: 'jerboa', content: 'can you review **#12**?', ts: t - 7200 },
    { id: 91, sender: 'jerboa', recipient: 'tapir', content: 'on it', ts: t - 7100 },
    { id: 92, sender: 'stoat', recipient: 'ferret', content: 'lock busy', ts: t - 60 },
    { id: 93, sender: 'stoat', recipient: 'hedgehog', content: 'lock busy', ts: t - 59 },
    { id: 94, sender: 'stoat', recipient: 'stoat', content: 'wake up', ts: t - 30 },
  ].map(m => ({ ...m, status: 'delivered', attachments: [] }));
  await page.route('**/messages?limit=*', route => route.fulfill({ json: { messages: [...talk].reverse() } }));
  try {
    await page.goto(base + '#/chats');
    await page.getByRole('button', { name: 'between agents' }).click();
    await page.waitForSelector('.agent-talk-thread');
    assert.equal(await page.evaluate(() => location.hash), '#/chats?view=agents');
    const rows = () => page.locator('.agent-talk-thread > summary .chat-who').evaluateAll(els => els.map(e => e.childNodes.length && e.textContent.split(/\d{1,2}:\d{2}/)[0].replace(/\s+/g, ' ').trim()));
    assert.deepEqual(await rows(), ['stoat → ferret, hedgehog', 'jerboa ↔ tapir']);
    assert.match(await page.locator('.agent-talk-note').innerText(), /1 notes agents left themselves are hidden/);
    const pair = page.locator('.agent-talk-thread').nth(1);
    await pair.locator('summary').click();
    // Messages render on the toggle event, after the click returns.
    await pair.locator('.agent-talk-msg').nth(1).waitFor();
    assert.equal(await pair.locator('.agent-talk-msg').count(), 2);
    assert.equal(await pair.locator('.agent-talk-msg strong').first().innerText(), '#12');
    // Team agent-swarm is stoat, numbat and hoopoe: only stoat's broadcast stays.
    await page.getByRole('combobox', { name: 'Team' }).selectOption('1');
    await page.waitForFunction(() => document.querySelectorAll('.agent-talk-thread').length === 1);
    await page.getByRole('combobox', { name: 'Team' }).selectOption('');
    await page.locator('.chats-search').fill('review');
    await page.waitForFunction(() => document.querySelectorAll('.agent-talk-thread').length === 1);
    assert.deepEqual(await rows(), ['jerboa ↔ tapir']);
    await page.reload();
    await page.waitForSelector('.agent-talk-thread');
    assert.equal(await page.locator('.chats-search').inputValue(), 'review');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('phone agents panel: team view groups and collapses, and the view choice sticks', async () => {
  const { page, errors } = await setup(390, 844);
  try {
    await page.goto(base + '#/');
    await page.waitForSelector('.agents-panel');
    // Default view: live agents in team boxes, then a "no team" box.
    const groups = await page.locator('.team-bees-group .team-bees-name').allInnerTexts();
    assert.equal(groups[0].toLowerCase(), 'agent-swarm');
    assert.equal(groups[groups.length - 1].toLowerCase(), 'no team');
    assert.equal(await page.locator('.team-bees-group').first().locator('.team-mate').count(), 3);
    await page.locator('.team-bees-group > summary').first().click();
    assert.equal(await page.locator('.team-bees-group').first().locator('.team-mate').first().isVisible(), false);
    await page.locator('.agents-view-switch button', { hasText: 'tiles' }).click();
    assert.ok(await page.locator('.bee-grid').isVisible());
    await page.reload();
    await page.waitForSelector('.agents-panel .bee-grid');
    await page.locator('.agents-view-switch button', { hasText: 'teams' }).click();
    // Still collapsed after the reload.
    assert.equal(await page.locator('.team-bees-group').first().evaluate(d => d.open), false);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('desktop sidebar opens on the team view, which holds new team and spawn', async () => {
  const { page, errors } = await setup(1500, 900, false);
  // A browser that last chose the removed roster view lands on teams.
  await page.addInitScript(() => localStorage.setItem('agent-swarm:sidebar-agents-view', 'roster'));
  try {
    await page.goto(base + '#/agent/stoat');
    await page.waitForSelector('#agent-sidebar .team-bees');
    assert.equal(await page.locator('#agent-sidebar .team-mate.here').innerText().then(t => t.trim().split(/\s/)[0]), 'stoat');
    assert.deepEqual(await page.locator('#agent-sidebar .agents-view-switch button').allTextContents(), ['teams', 'tiles']);
    assert.equal(await page.locator('#agent-sidebar .roster-heading').count(), 1);
    assert.ok(await page.locator('#agent-sidebar .team-bees form.newteam').isVisible());
    assert.ok(await page.locator('#agent-sidebar .team-bees form.spawn').isVisible());
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('team view: the crown button picks a queen and the ✕ removes the team', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  const patches = [], deletes = [];
  await page.route('**/teams/1', async route => {
    if (route.request().method() === 'DELETE') {
      deletes.push(1);
      state.teams = state.teams.filter(t => t.id !== 1);
      return route.fulfill({ json: { ok: true } });
    }
    const body = route.request().postDataJSON();
    patches.push(body);
    state.teams[0].queen = body.queen;
    await route.fulfill({ json: { ok: true, team: state.teams[0] } });
  });
  try {
    await page.goto(base + '#/');
    const team = page.locator('#agent-sidebar .team-bees-group', { has: page.locator('.team-bees-name', { hasText: /^agent-swarm$/ }) });
    await team.getByRole('button', { name: 'Manage team agent-swarm' }).click();
    const pick = team.getByRole('combobox', { name: 'Queen of agent-swarm' });
    assert.equal(await pick.inputValue(), 'stoat');
    const other = (await pick.locator('option').allTextContents()).find(o => o !== 'no queen' && o !== 'stoat');
    await pick.selectOption(other);
    await team.getByRole('textbox', { name: 'Objective for the queen' }).fill('ship it');
    await team.getByRole('button', { name: 'save' }).click();
    await team.locator('form.team-manage').waitFor({ state: 'detached' });
    assert.deepEqual(patches, [{ queen: other, objective: 'ship it' }]);
    await team.locator(`.team-mate[href="#/agent/${other}"] .crown`).waitFor();
    // Clicking the crown button does not fold the team.
    assert.equal(await team.evaluate(d => d.open), true);
    await team.getByRole('button', { name: 'Remove team agent-swarm' }).click();
    const question = await answer(page);
    await team.waitFor({ state: 'detached' });
    assert.deepEqual(deletes, [1]);
    assert.match(question, /Remove team agent-swarm\? Its agents keep running\./);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});


for (const width of [390, 1500]) {
  test(`team rename at ${width}px refreshes sidebar, canvas, switcher and task picker`, async () => {
    const { page, state, errors } = await setup(width, 900, width < 500);
    const patches = [];
    await page.addInitScript(() => {
      window.teamLabels = [];
      const draw = CanvasRenderingContext2D.prototype.fillText;
      CanvasRenderingContext2D.prototype.fillText = function(text, ...args) {
        if (String(text).includes('renamed crew') && !window.teamLabels.includes(text)) window.teamLabels.push(text);
        return draw.call(this, text, ...args);
      };
    });
    await page.route('**/teams/1', async route => {
      const body = route.request().postDataJSON();
      patches.push(body);
      Object.assign(state.teams[0], body);
      await route.fulfill({ json: { ok: true, team: state.teams[0] } });
    });
    try {
      await page.goto(base + '#/');
      const team = page.locator(width < 500 ? '.hive-panel .team-bees-group' : '#agent-sidebar .team-bees-group').first();
      await team.getByRole('button', { name: 'Manage team agent-swarm' }).click();
      await team.getByRole('textbox', { name: 'Team name', exact: true }).fill('  renamed crew  ');
      await team.getByRole('button', { name: 'save', exact: true }).click();
      await team.locator('form.team-manage').waitFor({ state: 'detached' });
      await team.getByRole('button', { name: 'Manage team renamed crew', exact: true }).waitFor();
      assert.deepEqual(patches, [{ name: 'renamed crew' }]);
      assert.equal(state.teams[0].queen, 'stoat');
      if (width >= 500) await page.waitForFunction(() => window.teamLabels.some(t => t.startsWith('renamed crew')));
      await page.getByRole('button', { name: /^teams .*K/ }).click();
      const dialog = page.getByRole('dialog', { name: 'Switch team' });
      assert.match(await dialog.getByRole('option').first().textContent(), /renamed crew/);
      await page.keyboard.press('Escape');
      await page.locator('.hive-task-picker select').selectOption('73');
      assert.equal(await page.locator('.hive-task-detail').getByRole('combobox', { name: 'Assign task #73' }).locator('option[value="t:1"]').textContent(), 'renamed crew');
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });
}

test('team rename refuses an empty name without sending', async () => {
  const { page, errors } = await setup(1500, 900, false);
  const patches = [];
  await page.route('**/teams/1', async route => {
    patches.push(route.request().postDataJSON());
    await route.fulfill({ json: { ok: true } });
  });
  try {
    await page.goto(base + '#/');
    await page.getByRole('button', { name: 'Manage team agent-swarm' }).click();
    const form = page.locator('#agent-sidebar .team-manage');
    await form.getByRole('textbox', { name: 'Team name', exact: true }).fill('   ');
    await form.getByRole('button', { name: 'save', exact: true }).click();
    assert.equal(await form.getByRole('alert').textContent(), 'Team name cannot be empty.');
    assert.deepEqual(patches, []);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('team rename keeps the draft and shows the duplicate-name error inline', async () => {
  const { page, errors } = await setup(1500, 900, false);
  await page.route('**/teams/1', route => route.fulfill({ status: 409, json: { detail: { error: 'A team named "spare" already exists.' } } }));
  try {
    await page.goto(base + '#/');
    await page.getByRole('button', { name: 'Manage team agent-swarm' }).click();
    const form = page.locator('#agent-sidebar .team-manage');
    const name = form.getByRole('textbox', { name: 'Team name', exact: true });
    await name.fill('spare');
    await form.getByRole('button', { name: 'save', exact: true }).click();
    await form.getByRole('alert').waitFor();
    assert.equal(await form.getByRole('alert').textContent(), 'A team named "spare" already exists.');
    assert.equal(await name.inputValue(), 'spare');
    assert.equal(await form.getByRole('button', { name: 'save', exact: true }).isEnabled(), true);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('team view: dragging a chip onto the stop zone stops that agent', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  const stops = [];
  await page.route('**/agents/*/stop', async route => {
    const user = decodeURIComponent(route.request().url().split('/agents/')[1].split('/')[0]);
    stops.push(user);
    state.recipients.find(r => r.user_id === user).pane_alive = false;
    await route.fulfill({ json: { ok: true, already_stopped: false } });
  });
  try {
    await page.goto(base + '#/agent/stoat');
    await page.waitForSelector('#agent-sidebar .team-bees');
    // The stop zone only exists during a drag.
    assert.equal(await page.locator('.team-bees-stop').count(), 0);
    const box = await page.locator('#agent-sidebar .team-mate[href="#/agent/stoat"]').boundingBox();
    await page.mouse.move(box.x + 10, box.y + 10);
    await page.mouse.down();
    await page.mouse.move(box.x + 30, box.y + 20, { steps: 5 });
    const zone = page.locator('#agent-sidebar .team-bees-stop');
    await zone.waitFor();
    assert.equal((await zone.textContent()).trim(), 'drop here to stop stoat');
    await zone.scrollIntoViewIfNeeded();
    const target = await zone.boundingBox();
    await page.mouse.move(target.x + 40, target.y + 10, { steps: 5 });
    await page.mouse.up();
    const question = await answer(page);
    await page.waitForFunction(() => location.hash !== '#/agent/stoat');
    assert.deepEqual(stops, ['stoat']);
    assert.match(question, /^Stop stoat on /);
    assert.equal(await page.locator('.team-bees-stop').count(), 0);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('harness filter: legend keys and sidebar icons filter agents by harness', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  try {
    await page.goto(base + '#/');
    await page.waitForSelector('#agent-sidebar .team-bees');
    const live = h => state.recipients.filter(r => r.pane_alive && r.flavor === h).map(r => r.user_id).sort();
    const shown = () => page.locator('#agent-sidebar .team-mate-name').allInnerTexts().then(n => n.sort());
    assert.equal((await shown()).length, live('claude').length + live('codex').length);
    // The legend key filters the sidebar (team view) and dims other bees.
    await page.locator('.harness-legend button.harness-key', { hasText: 'Claude' }).click();
    assert.deepEqual(await shown(), live('claude'));
    assert.equal(await page.locator('#agent-sidebar .roster-heading .harness-filter button[aria-pressed=true]').getAttribute('aria-label'), 'Only Claude agents');
    // Sidebar icons switch the filter; the active one clears it.
    const codex = page.locator('#agent-sidebar .roster-heading .harness-filter button', { hasText: '◇' });
    await codex.click();
    assert.deepEqual(await shown(), live('codex'));
    assert.equal(await page.locator('.harness-legend button[aria-pressed=true]').textContent().then(t => t.replace(/\s/g, '')), '◇Codex');
    // The filter stays on an agent page, where the legend is gone.
    await page.goto(base + '#/agent/stoat');
    assert.deepEqual(await shown(), live('codex'));
    await codex.click();
    assert.equal(await page.locator('#agent-sidebar .roster-heading .harness-filter button[aria-pressed=true]').count(), 0);
    // Icon-only: the filter shares the heading row, so it adds no height.
    const rows = await page.locator('#agent-sidebar .roster-heading').evaluate(e => e.getBoundingClientRect().height);
    assert.ok(rows < 40, `heading row is ${rows}px tall`);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('team view: drag an agent chip to another team or to no team', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  // A second, empty team: it shows as one folded line, and opens as a target
  // while a chip is being dragged.
  state.teams.push({ id: 2, name: 'spare', queen: null, members: [] });
  const moves = [];
  await page.route('**/agents/*/team', async route => {
    const user = decodeURIComponent(route.request().url().split('/agents/')[1].split('/')[0]);
    const { team_id } = route.request().postDataJSON();
    moves.push([user, team_id]);
    state.recipients.find(r => r.user_id === user).team_id = team_id;
    await route.fulfill({ json: { ok: true } });
  });
  try {
    await page.goto(base + '#/');
    await page.waitForSelector('#agent-sidebar .team-bees');
    const group = name => page.locator('#agent-sidebar .team-bees-group', { has: page.locator('.team-bees-name', { hasText: new RegExp(`^${name}$`) }) });
    const chip = user => page.locator(`#agent-sidebar .team-mate[href="#/agent/${user}"]`);
    assert.equal(await group('spare').evaluate(d => d.classList.contains('empty')), true);

    await chip('stoat').dragTo(group('no team').locator('summary').first());
    await page.waitForFunction(() => document.querySelector('#agent-sidebar .team-bees-group.loose a[href="#/agent/stoat"]'));
    await chip('ferret').dragTo(group('agent-swarm').locator('summary').first());
    await page.waitForFunction(() => [...document.querySelectorAll('#agent-sidebar .team-bees-group:not(.loose) a')].some(a => a.getAttribute('href') === '#/agent/ferret'));
    // Dropping a chip on its own group changes nothing.
    await chip('ferret').dragTo(group('agent-swarm').locator('summary').first());
    // An empty team is a target while dragging.
    await page.mouse.move(0, 0);
    const box = await chip('smew').boundingBox();
    await page.mouse.move(box.x + 10, box.y + 10);
    await page.mouse.down();
    await page.mouse.move(box.x + 30, box.y + 20, { steps: 5 });
    await group('spare').waitFor();
    const spare = await group('spare').boundingBox();
    await page.mouse.move(spare.x + 40, spare.y + 20, { steps: 5 });
    await page.mouse.up();
    await page.waitForFunction(() => document.querySelector('#agent-sidebar a[href="#/agent/smew"]')?.closest('details')?.querySelector('.team-bees-name')?.textContent === 'spare');
    assert.deepEqual(moves, [['stoat', null], ['ferret', 1], ['smew', 2]]);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('inside the Mac app the page reports who needs attention', async () => {
  const { page, state, errors } = await setup(1280, 800, false);
  await page.addInitScript(() => {
    window.__calls = [];
    window.__TAURI__ = { core: { invoke: async (cmd, args) => { window.__calls.push([cmd, args.agents]); } } };
  });
  const waiting = () => state.recipients
    .filter(r => r.pane_alive && r.activity?.status === 'needs_attention').map(r => r.user_id).sort();
  try {
    await page.goto(base + '#/');
    await page.waitForFunction(() => window.__calls.length === 1);
    assert.ok(waiting().length > 0);
    assert.deepEqual(await page.evaluate(() => window.__calls), [['attention', waiting()]]);
    // Same list on the next poll: nothing new is sent.
    await page.waitForTimeout(2500);
    assert.equal(await page.evaluate(() => window.__calls.length), 1);
    state.recipients.find(r => r.activity?.status === 'working').activity.status = 'needs_attention';
    await page.waitForFunction(() => window.__calls.length === 2);
    assert.deepEqual((await page.evaluate(() => window.__calls))[1], ['attention', waiting()]);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('opening the page on a gone agent falls back to the overview', async () => {
  const { page, errors } = await setup(1280, 800, false);
  try {
    await page.goto(base + '#/agent/long-gone');
    await page.waitForFunction(() => location.hash === '#/');
    // Only the first load redirects: following a link to a gone agent later
    // still says so.
    await page.evaluate(() => { location.hash = '#/agent/long-gone'; });
    await page.waitForSelector('text=No agent named');
    assert.equal(await page.evaluate(() => location.hash), '#/agent/long-gone');
    // An agent that still exists stays where it was opened.
    await page.evaluate(() => { location.hash = '#/agent/stoat'; });
    await page.reload();
    await page.waitForSelector('.stage');
    await page.waitForTimeout(500);
    assert.equal(await page.evaluate(() => location.hash), '#/agent/stoat');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

for (const rosterOpen of [true, false]) {
  test(`focused conversation fills wide windows; Escape preserves route (roster ${rosterOpen})`, async () => {
    const { page, errors } = await setup(1800, 1000, false);
    try {
      await page.addInitScript(open => localStorage.setItem('swarm-roster-open', String(open)), rosterOpen);
      await page.goto(base + '#/agent/stoat');
      await page.locator('.thread-focus').first().click();
      for (const width of [1800, 2400]) {
        await page.setViewportSize({ width, height: 1000 });
        const rect = await page.locator('.thread.focused').boundingBox();
        assert.equal(rect.x, 24);
        assert.equal(rect.width, width - 48);
      }
      // With a toolbar button focused, both old window handlers used to run.
      await page.keyboard.press('Escape');
      await page.waitForSelector('.thread.focused', { state: 'detached' });
      assert.equal(await page.locator('.roster-drawer.is-open').count(), Number(rosterOpen));
      assert.equal(await page.evaluate(() => location.hash), '#/agent/stoat');
      await page.locator('.thread-focus').first().click();
      // Escape from the composer also closes only the conversation overlay.
      await page.locator('.thread.focused textarea').first().focus();
      await page.keyboard.press('Escape');
      await page.waitForSelector('.thread.focused', { state: 'detached' });
      assert.equal(await page.locator('.roster-drawer.is-open').count(), Number(rosterOpen));
      assert.equal(await page.evaluate(() => location.hash), '#/agent/stoat');
      await page.evaluate(() => document.activeElement.blur());
      await page.keyboard.press('Escape');
      await page.keyboard.press('Escape');
      assert.equal(await page.evaluate(() => location.hash), '#/agent/stoat');
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });
}

test('detail stop confirms, handles failure, retries, and keeps history on the page', async () => {
  const { page, state, errors } = await setup(390, 844);
  let calls = 0;
  await page.route('**/agents/stoat/stop', async route => {
    calls++;
    assert.equal(route.request().method(), 'POST');
    if (calls === 1) return route.abort();
    state.recipients.find(r => r.user_id === 'stoat').pane_alive = false;
    await route.fulfill({ json: { ok: true, already_stopped: false } });
  });
  try {
    await page.goto(base + '#/agent/stoat');
    const stop = page.locator('.fhead').getByRole('button', { name: 'stop agent', exact: true });
    await stop.click();
    await answer(page, 'Cancel');
    assert.equal(calls, 0);
    assert.equal(await page.evaluate(() => document.activeElement?.textContent.trim()), 'stop agent');
    await stop.click();
    assert.match(await answer(page), /stoat on karans-linux/);
    await page.getByText('Stop not confirmed. Check the agent\'s status before retrying.', { exact: true }).waitFor();
    assert.equal(await stop.isEnabled(), true);
    await stop.click();
    await answer(page);
    await page.getByText('Agent stopped. Messages and tasks are kept.', { exact: true }).waitFor();
    await stop.waitFor({ state: 'detached' });
    assert.equal(calls, 2);
    assert.equal(await page.evaluate(() => location.hash), '#/agent/stoat');
    assert.ok(await page.locator('.thread .msg').count() > 0);
    assert.ok(await page.locator('.agent-task-row, .task-compose-fold').count() > 0);
    await page.goto(base + '#/agent/stopped-agent');
    await page.waitForSelector('.fhead');
    assert.equal(await page.locator('.fhead .stop-agent').count(), 0);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('compact and stop ask in the page: Esc cancels, Enter confirms, errors show a notice', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  state.recipients.find(r => r.user_id === 'stoat').compact_command = '/compact';
  const typed = [];
  await page.route('**/agents/stoat/terminal', async route => {
    typed.push(route.request().postDataJSON());
    if (typed.length === 1) return route.fulfill({ status: 409, json: { detail: { error: 'pane is busy' } } });
    await route.fulfill({ json: { ok: true } });
  });
  const stops = [];
  await page.route('**/agents/stoat/stop', async route => {
    stops.push(route.request().method());
    state.recipients.find(r => r.user_id === 'stoat').pane_alive = false;
    await route.fulfill({ json: { ok: true, already_stopped: false } });
  });
  const focused = () => page.evaluate(() => document.activeElement?.textContent.trim());
  try {
    await page.goto(base + '#/agent/stoat');
    const compact = page.getByRole('button', { name: 'compact', exact: true });
    const dialog = page.locator('dialog.page-dialog[open]');
    await compact.click();
    await dialog.waitFor();
    assert.equal(await dialog.locator('.page-dialog-message').textContent(),
      "Compact stoat's context? This types /compact into its pane.");
    assert.equal(await focused(), 'OK');
    await page.keyboard.press('Escape');
    await dialog.waitFor({ state: 'detached' });
    assert.deepEqual(typed, []);
    assert.equal(await focused(), 'compact');

    await compact.click();
    await dialog.waitFor();
    await page.keyboard.press('Enter');
    assert.equal(await answer(page), 'Could not compact stoat: pane is busy');
    assert.deepEqual(typed, [{ text: '/compact' }]);

    const sent = page.waitForResponse(r => r.url().endsWith('/agents/stoat/terminal'));
    await compact.click();
    await answer(page);
    await sent;
    await page.getByRole('button', { name: 'compact', exact: true }).waitFor();
    assert.equal(typed.length, 2);
    assert.equal(await dialog.count(), 0);

    const stop = page.locator('.fhead').getByRole('button', { name: 'stop agent', exact: true });
    await stop.click();
    await dialog.waitFor();
    assert.match(await dialog.locator('.page-dialog-message').textContent(), /^Stop stoat on karans-linux\? /);
    await page.keyboard.press('Enter');
    await page.getByText('Agent stopped. Messages and tasks are kept.', { exact: true }).waitFor();
    assert.deepEqual(stops, ['POST']);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('detail history survives global feed eviction, pages older, and preserves scroll', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  const history = Array.from({ length: 340 }, (_, i) => ({ id: i + 10, sender: 'owner', recipient: 'stoat', ts: state.now - 1000 + i, content: `archived-message-${i + 10}`, status: 'delivered', attachments: [] }));
  state.messages = [{ id: 999, sender: 'owner', recipient: 'ferret', ts: state.now, content: 'unrelated traffic', status: 'delivered', attachments: [] }];
  await page.route('**/api/agents/stoat/messages?*', route => {
    const q = new URL(route.request().url()).searchParams;
    const before = Number(q.get('before') || Infinity), after = Number(q.get('after') || 0);
    const rows = history.filter(m => m.id < before && m.id > after).sort((a,b) => q.has('after') ? a.id-b.id : b.id-a.id);
    return route.fulfill({json:{messages:rows.slice(0,300),has_more:rows.length > 300}});
  });
  try {
    await page.goto(base + '#/agent/stoat');
    await page.getByText('archived-message-349', { exact: true }).waitFor();
    assert.equal(await page.getByText(/Nothing yet/).count(), 0);
    const box = page.locator('.thread .msgs').first();
    await box.evaluate(el => { el.scrollTop = 250; });
    await page.waitForTimeout(100);
    const before = await box.evaluate(el => ({ top:el.scrollTop, height:el.scrollHeight }));
    await page.getByRole('button', { name: 'Load older messages', exact: true }).click();
    await page.getByText('archived-message-10', { exact: true }).waitFor({state:'attached'});
    const after = await box.evaluate(el => ({ top:el.scrollTop, height:el.scrollHeight }));
    assert.ok(Math.abs((after.top-before.top)-(after.height-before.height)) < 2);
    assert.equal(await page.getByRole('button', { name: 'Load older messages', exact: true }).count(), 0);
    history.push({ ...history[0], id: 350, ts: state.now, content: 'new scoped message' });
    await page.getByText('new scoped message', { exact: true }).waitFor({state:'attached'});
    await page.evaluate(() => { location.hash = '#/agent/ferret'; });
    await page.getByText('unrelated traffic', { exact: true }).waitFor();
    assert.equal(await page.getByText('archived-message-349', { exact: true }).count(), 0);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('failed detail history shows a retry message, never a false empty conversation', async () => {
  const { page, state, errors } = await setup(390, 844);
  state.messages = [];
  let failed = true;
  await page.route('**/api/agents/stoat/messages?*', route => failed
    ? route.fulfill({ status: 503, json: { detail: 'temporarily unavailable' } })
    : route.fulfill({ json: { messages: [{ id: 41, sender: 'owner', recipient: 'stoat', content: 'recovered history', ts:state.now, status:'delivered', attachments:[] }], has_more:false } }));
  try {
    await page.goto(base + '#/agent/stoat');
    await page.getByText('Could not load conversation history. Retrying…', {exact:true}).waitFor();
    assert.equal(await page.getByText(/Nothing yet/).count(), 0);
    failed = false;
    await page.getByText('recovered history', {exact:true}).waitFor();
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('keyboard switchers search across teams and preserve focused chat on Escape', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  state.teams.push({ id:2, name:'Research lab', queen:'ferret', members:['ferret','hedgehog'] }, {id:3,name:'Empty team',members:[]});
  state.recipients.find(a => a.user_id === 'ferret').team_id = 2;
  state.recipients.find(a => a.user_id === 'hedgehog').team_id = 2;
  try {
    await page.goto(base + '#/agent/stoat');
    await page.locator('.thread-focus').first().click();
    const composer = page.locator('.thread.focused textarea').first();
    await composer.fill('keep this draft');
    await page.keyboard.press('Control+k');
    const dialog = page.getByRole('dialog', {name:'Switch agent'});
    await dialog.waitFor();
    await page.locator('dialog[open]').getByRole('combobox').fill('research ferret');
    assert.equal(await dialog.getByRole('option').count(), 1);
    await page.keyboard.press('Escape');
    await dialog.waitFor({state:'hidden'});
    assert.equal(await page.locator('.thread.focused').count(), 1);
    assert.equal(await composer.inputValue(), 'keep this draft');
    assert.equal(await composer.evaluate(e => e === document.activeElement), true);
    await page.keyboard.press('Control+Shift+k');
    await page.getByRole('dialog', {name:'Switch team'}).waitFor();
    await page.locator('dialog[open]').getByRole('combobox').fill('research');
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => location.hash === '#/agent/ferret');
    // Offline agents are searchable too.
    await page.keyboard.press('Control+k');
    await page.locator('dialog[open]').getByRole('combobox').fill('stopped-agent');
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => location.hash === '#/agent/stopped-agent');
    await page.keyboard.press('Control+k');
    await page.locator('dialog[open]').getByRole('combobox').fill('no such agent');
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => location.hash), '#/agent/stopped-agent');
    await page.keyboard.press('Escape');
    await page.keyboard.press('Control+Shift+k');
    await page.locator('dialog[open]').getByRole('combobox').fill('empty team');
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => location.hash), '#/agent/stopped-agent');
    assert.equal(await page.locator('dialog[open]').getByRole('option').getAttribute('aria-disabled'), 'true');
    await page.keyboard.press('Escape');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('switchers support arrows, touch, team fallback, and small viewports', async () => {
  const { page, state, errors } = await setup(390, 844);
  state.recipients.find(a => a.user_id === 'stoat').pane_alive = false;
  try {
    await page.goto(base + '#/');
    await page.getByRole('button', {name:/^teams .*K/}).click();
    const dialog = page.getByRole('dialog', {name:'Switch team'});
    await dialog.waitFor();
    await dialog.getByRole('option').first().click();
    await page.waitForFunction(() => location.hash.startsWith('#/agent/'));
    assert.notEqual(await page.evaluate(() => location.hash), '#/agent/stoat');
    await page.keyboard.press('Control+k');
    const active = () => page.locator('dialog[open]').getByRole('combobox').getAttribute('aria-activedescendant');
    const first = await active();
    await page.keyboard.press('ArrowDown');
    assert.notEqual(await active(), first);
    await page.keyboard.press('ArrowUp');
    assert.equal(await active(), first);
    const rect = await page.locator('dialog[open]').boundingBox();
    assert.ok(rect.x >= 0 && rect.x+rect.width <= 390);
    await page.keyboard.press('Escape');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

for (const platform of ['MacIntel', 'Linux x86_64']) {
  test(`switcher uses the platform modifier without stealing editing keys: ${platform}`, async () => {
    const { page, errors } = await setup(1500, 900, false);
    const mac = platform === 'MacIntel';
    await page.addInitScript(platform => Object.defineProperty(navigator, 'platform', {value:platform}), platform);
    try {
      await page.goto(base + '#/agent/stoat');
      const composer = page.locator('.thread textarea').first();
      await composer.fill('text to edit');
      // Record whether the page consumed these keys; Chromium on Linux cannot
      // reproduce AppKit's actual Emacs editing bindings.
      await page.evaluate(() => {
        window.keyChecks = [];
        document.addEventListener('keydown', e => window.keyChecks.push({code:e.code, prevented:e.defaultPrevented}));
      });
      const editingModifier = mac ? 'Control' : 'Meta';
      for (const key of ['a', 'e', 'k']) await composer.press(`${editingModifier}+${key}`);
      assert.equal(await page.locator('dialog[open]').count(), 0);
      const keys = await page.evaluate(() => window.keyChecks.filter(e => ['KeyA','KeyE','KeyK'].includes(e.code)));
      assert.equal(keys.length, 3);
      assert.ok(keys.every(e => !e.prevented));
      const shortcutModifier = mac ? 'Meta' : 'Control';
      await composer.press(`${shortcutModifier}+k`);
      await page.getByRole('dialog', {name:'Switch agent'}).waitFor();
      await page.keyboard.press('Escape');
      await composer.press(`${shortcutModifier}+Shift+k`);
      await page.getByRole('dialog', {name:'Switch team'}).waitFor();
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });
}

for (const platform of ['MacIntel', 'Linux x86_64']) {
  test(`sidebar shortcut toggles and persists without stealing Mac editing keys: ${platform}`, async () => {
    const { page, errors } = await setup(1500, 900, false);
    const modifier = platform === 'MacIntel' ? 'Meta' : 'Control';
    await page.addInitScript(platform => Object.defineProperty(navigator, 'platform', {value:platform}), platform);
    try {
      await page.goto(base + '#/agent/stoat');
      const composer = page.locator('.thread textarea').first();
      await composer.fill('keep typing here');
      const toggle = page.locator('.roster-toggle');
      await composer.press(`${modifier}+b`);
      assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
      assert.equal(await composer.evaluate(e => e === document.activeElement), true);
      assert.equal(await composer.inputValue(), 'keep typing here');
      if (platform === 'MacIntel') {
        await composer.press('Control+b');
        assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
      }
      await composer.press(`${modifier}+b`);
      assert.equal(await toggle.getAttribute('aria-expanded'), 'true');
      await page.getByRole('button', {name:'Hide agents'}).focus();
      await page.keyboard.press(`${modifier}+b`);
      assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
      await page.waitForFunction(() => document.activeElement === document.querySelector('.roster-toggle'));
      assert.equal(await page.evaluate(() => location.hash), '#/agent/stoat');
      await page.reload();
      await page.waitForSelector('.roster-toggle');
      assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
      await page.setViewportSize({width:390,height:844});
      await page.waitForSelector('.roster-toggle', {state:'detached'});
      await page.keyboard.press(`${modifier}+b`);
      assert.equal(await page.evaluate(() => localStorage.getItem('swarm-roster-open')), 'false');
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });
}

test('an agent page focuses the reply box on desktop, not on touch screens', async () => {
  const desk = await setup(1500, 900, false);
  try {
    await desk.page.goto(base + '#/agent/stoat');
    const box = desk.page.locator('.thread textarea').first();
    await assert.doesNotReject(() => box.evaluate(e => new Promise((ok, no) => {
      const t0 = Date.now();
      (function wait() { document.activeElement === e ? ok() : Date.now() - t0 > 3000 ? no(new Error('not focused')) : setTimeout(wait, 50); })();
    })));
    await desk.page.keyboard.type('hi');
    assert.equal(await box.inputValue(), 'hi');
    assert.deepEqual(desk.errors, []);
  } finally { await desk.page.close(); }
  const phone = await setup(390, 844);
  try {
    await phone.page.goto(base + '#/agent/stoat');
    await phone.page.locator('.thread textarea').first().waitFor();
    await phone.page.waitForTimeout(300);
    assert.equal(await phone.page.evaluate(() => document.activeElement?.tagName), 'BODY');
  } finally { await phone.page.close(); }
});

for (const platform of ['MacIntel', 'Linux x86_64']) {
  test(`focus modifier shortcut preserves drafts and leaves Vimium f alone: ${platform}`, async () => {
    const {page, errors} = await setup(1500,900,false);
    await page.addInitScript(platform => Object.defineProperty(navigator,'platform',{value:platform}),platform);
    try {
      await page.goto(base+'#/agent/stoat');
      const box = page.locator('.thread textarea').first();
      await box.fill('unsent draft');
      const chord = platform === 'MacIntel' ? 'Meta+Shift+L' : 'Control+Shift+L';
      await box.press(chord);
      assert.equal(await page.locator('.thread.focused').count(),1);
      await box.press(chord);
      assert.equal(await page.locator('.thread.focused').count(),0);
      assert.equal(await box.inputValue(),'unsent draft');
      await page.evaluate(() => {
        document.activeElement.blur();
        window.fConsumed = null;
        document.addEventListener('keydown', e => { if(e.key === 'f') window.fConsumed=e.defaultPrevented; });
      });
      await page.keyboard.press('f');
      assert.equal(await page.evaluate(() => window.fConsumed),false);
      assert.equal(await page.locator('.thread.focused').count(),0);
      assert.equal(await page.evaluate(() => location.hash),'#/agent/stoat');
      assert.deepEqual(errors,[]);
    } finally { await page.close(); }
  });
}

test('waggle dance button sends every bee round a figure eight, then home', async () => {
  const { page, errors } = await setup(1440, 900, false);
  try {
    await page.goto(base);
    await page.waitForFunction(() => window.__hive && window.__hive.bees().size > 1);
    const spots = () => page.evaluate(() =>
      [...window.__hive.bees()].map(([name, b]) => ({ name, x: b.x, y: b.y })));
    const before = await spots();
    await page.getByRole('button', { name: /waggle dance/ }).click();
    assert.equal(await page.evaluate(() => window.__hive.dancing()), true);
    await page.waitForTimeout(2500);
    const mid = await spots();
    // Mid-dance the bees share one figure eight around the canvas middle.
    const width = await page.evaluate(() => document.querySelector('canvas').clientWidth);
    const rx = Math.min(width * .38, 300);
    for (const b of mid) {
      assert.ok(Math.abs(b.x - width / 2) <= rx + 10, `${b.name} x ${b.x}`);
      assert.ok(Math.abs(b.y - 128) <= rx * .32 + 10, `${b.name} y ${b.y}`);
    }
    assert.ok(mid.some((b, i) => Math.hypot(b.x - before[i].x, b.y - before[i].y) > 40));
    await page.waitForFunction(() => !window.__hive.dancing(), null, { timeout: 8000 });
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('task history tiles edit, complete, and reopen a task', async () => {
  const { page, state, errors } = await setup(390,844);
  const patches = [];
  await page.route('**/tasks/*', async route => {
    if (route.request().method() !== 'PATCH') return route.continue();
    const id = Number(route.request().url().split('/').pop());
    const patch = route.request().postDataJSON();
    patches.push({ id, ...patch });
    Object.assign(state.tasks.find(t => t.id === id), patch);
    await route.fulfill({ json: { ok: true } });
  });
  try {
    await page.goto(base + '#/tasks');
    const tile = () => page.locator('.htile').filter({ has: page.locator('.h-id', { hasText: '#73' }) });
    await tile().getByRole('button', { name: 'Edit task #73' }).tap();
    await tile().getByLabel('Title').fill('Mobile dashboard, renamed');
    await tile().getByLabel('Description').fill('New description');
    await tile().getByRole('button', { name: 'Save' }).tap();
    await page.waitForFunction(() => document.querySelector('.h-grid').textContent.includes('Mobile dashboard, renamed'));
    assert.deepEqual(patches[0], { id: 73, title: 'Mobile dashboard, renamed', description: 'New description' });
    await tile().getByRole('button', { name: 'Complete task' }).tap();
    await tile().locator('.task-verification textarea').fill('Open #/tasks at 390px.');
    await tile().getByRole('button', { name: 'Complete task' }).tap();
    await tile().getByRole('button', { name: 'Reopen' }).waitFor();
    assert.deepEqual(patches[1], { id: 73, status: 'done', note: 'Open #/tasks at 390px.' });
    await tile().getByRole('button', { name: 'Reopen' }).tap();
    await tile().getByRole('button', { name: 'Complete task' }).waitFor();
    assert.deepEqual(patches[2], { id: 73, status: 'picked_up' });
    await fit(page);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('desktop hive task trash: cancel, failure, success, and card drop', async () => {
  const { page, state, errors } = await setup(1440, 1000, false);
  const deleted = [];
  let fail = false;
  await page.route('**/tasks/74', async route => {
    assert.equal(route.request().method(), 'DELETE');
    deleted.push(74);
    if (fail) return route.fulfill({status:409,json:{detail:{error:'Task has dependent tasks'}}});
    state.tasks = state.tasks.filter(t => t.id !== 74);
    await route.fulfill({json:{ok:true}});
  });
  const drag = async (cancel = false) => {
    await page.waitForFunction(() => window.__hive?.taskCells().some(c => c.task.id === 74));
    const cell = await page.evaluate(() => {
      const c = window.__hive.taskCells().find(c => c.task.id === 74);
      const r = document.querySelector('canvas').getBoundingClientRect();
      return {x:r.left+c.x,y:r.top+c.y};
    });
    const zoneNode = page.locator('.hive-trash-zone');
    assert.equal(await zoneNode.isVisible(),false);
    await page.mouse.move(cell.x, cell.y);
    await page.mouse.down();
    assert.equal(await zoneNode.isVisible(),false);
    await page.mouse.move(cell.x+8,cell.y+8,{steps:2});
    await zoneNode.waitFor({state:'visible'});
    assert.match(await zoneNode.innerText(),/Trash task/);
    const zone = await zoneNode.boundingBox();
    await page.mouse.move(zone.x+zone.width/2, zone.y+zone.height/2, {steps:12});
    assert.ok(await page.locator('.hive-trash-zone.over').count());
    if (cancel) await page.locator('canvas').dispatchEvent('pointercancel',{pointerId:1});
    await page.mouse.up();
    assert.equal(await zoneNode.isVisible(),false);
  };
  try {
    await page.goto(base+'#/');
    await page.locator('canvas').waitFor();
    await page.evaluate(() => {
      const dataTransfer = new DataTransfer();
      dataTransfer.setData('text/plain','74');
      document.querySelector('canvas').dispatchEvent(new DragEvent('dragover',{bubbles:true,dataTransfer}));
    });
    assert.equal(await page.locator('.hive-trash-zone').isVisible(),false);
    if (process.env.TASK339_SCREENSHOT) await page.locator('.hive-panel').screenshot({path:process.env.TASK339_SCREENSHOT});
    await drag(true);
    assert.deepEqual(deleted,[]);
    await drag();
    assert.match(await answer(page, 'Cancel'), /#74: Long path regression/);
    assert.deepEqual(deleted, []);
    fail = true;
    await drag();
    await answer(page);
    await page.getByRole('status').filter({hasText:'Task has dependent tasks'}).waitFor();
    assert.equal(state.tasks.some(t => t.id === 74), true);
    fail = false;
    await drag();
    await answer(page);
    await page.waitForFunction(() => !window.__hive.taskCells().some(c => c.task.id === 74));
    assert.deepEqual(deleted, [74,74]);
    // HTML task-card drops use the same corner and confirmation.
    state.tasks.push({id:74,title:'Long path regression',status:'open',created_at:state.now,depends_on:[]});
    await page.reload();
    await page.locator('canvas').waitFor();
    await page.evaluate(() => {
      const canvas = document.querySelector('canvas');
      const dataTransfer = new DataTransfer();
      dataTransfer.setData('application/x-agent-swarm-task','74');
      window.dispatchEvent(new DragEvent('dragstart',{dataTransfer}));
      const r = document.querySelector('.hive-trash-zone').getBoundingClientRect();
      if (!r.width) throw Error('Task-card drag must reveal the zone before entering canvas');
      canvas.dispatchEvent(new DragEvent('dragover',{bubbles:true,clientX:r.x+10,clientY:r.y+10,dataTransfer}));
      canvas.dispatchEvent(new DragEvent('drop',{bubbles:true,clientX:r.x+10,clientY:r.y+10,dataTransfer}));
    });
    await answer(page);
    await page.waitForFunction(() => document.querySelector('[role="status"]')?.textContent.includes('Trashed task #74'));
    assert.deepEqual(deleted, [74,74,74]);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('reply to one agent message by button or right-click', async () => {
  const { page, errors } = await setup(1500, 900, false);
  const sent = [];
  await page.route('**/owner/send', async route => {
    sent.push(route.request().postDataJSON());
    await route.fulfill({ json: { ok: true, status: 'delivered', message_id: 50 + sent.length } });
  });
  try {
    await page.goto(base + '#/agent/stoat');
    const box = page.locator('form.composer textarea').first();
    await page.getByRole('button', { name: 'Reply to message 2' }).click();
    assert.match(await page.locator('.compose-reply').innerText(), /Replying to stoat: Testing phone and tablet navigation\./);
    // The composer takes focus after the render, so typing starts the reply.
    await page.waitForFunction(() => document.activeElement?.matches('form.composer textarea'));
    await box.fill('looks good');
    await box.press('Enter');
    await page.waitForFunction(() => !document.querySelector('.compose-reply'));
    assert.equal(sent[0].content, 'looks good');
    assert.equal(sent[0].reply_to, 2);

    // The owner can reply to their own message too.
    await page.getByRole('button', { name: 'Reply to message 1' }).click();
    assert.match(await page.locator('.compose-reply').innerText(), /Replying to owner:/);
    await box.fill('following up');
    await box.press('Enter');
    await page.waitForFunction(() => !document.querySelector('.compose-reply'));
    assert.equal(sent[1].content, 'following up');
    assert.equal(sent[1].reply_to, 1);

    await page.locator('[data-message-id="2"]').click({ button: 'right' });
    await page.getByRole('menuitem', { name: '↩ Reply' }).click();
    await page.locator('.compose-reply').waitFor();
    await box.press('Escape');
    await page.waitForFunction(() => !document.querySelector('.compose-reply'));
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});


for (const width of [390, 1500]) {
  test(`message emphasis, inline code and underlined links have distinct colors at ${width}px`, async () => {
    const {page,state,errors}=await setup(width,900,width<500);
    const content='**Important result**: run `buzz tasks` and read the [review notes](https://example.com/review).\n\n[**Bold link**](https://example.com/bold) and [`code link`](https://example.com/code).\n\n| Check | Result |\n|---|---|\n| API | Ready |\n\n```\nneutral fenced text\n```';
    state.messages.push({id:420,sender:'stoat',recipient:'owner',content,ts:state.now,status:'delivered',attachments:[]});
    try {
      await page.goto(base+'#/agent/stoat');
      const body=page.locator('[data-message-id="420"] .md');
      await body.locator('strong').first().waitFor();
      const colors=await body.evaluate(e=>{
        const style=s=>getComputedStyle(e.querySelector(s));
        return {strong:style('p > strong').color,weight:style('p > strong').fontWeight,
          code:style('p > code').color,codeBg:style('p > code').backgroundColor,
          link:style('a').color,decoration:style('a').textDecorationLine,
          boldLink:style('a strong').color,codeLink:style('a code').color,
          header:style('th').color,fence:style('pre code').color,
          alert:getComputedStyle(document.documentElement).getPropertyValue('--alert').trim()};
      });
      assert.equal(new Set([colors.strong,colors.code,colors.link]).size,3);
      assert.equal(colors.strong,'rgb(255, 135, 175)');
      assert.equal(colors.code,'rgb(166, 227, 161)');
      assert.ok(Number(colors.weight)>=650);
      assert.notEqual(colors.codeBg,'rgba(0, 0, 0, 0)');
      assert.ok(colors.decoration.includes('underline'));
      assert.equal(colors.boldLink,colors.link);
      assert.equal(colors.codeLink,colors.link);
      assert.equal(colors.header,'rgb(255, 247, 230)');
      assert.notEqual(colors.fence,colors.code);
      assert.equal(colors.alert,'#e06c55');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);
      assert.deepEqual(errors,[]);
    } finally {await page.close();}
  });
}

test('the terminal view shows pane colors and chat colors code, diffs and Markdown', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  const E = '\x1b';
  await page.route('**/api/peek/**', r => r.fulfill({ json: { pane_label: 'agent-swarm:0.1', error: null,
    text: `plain ${E}[31mred${E}[0m ${E}[1;38;5;174mpink${E}[0m <b>not bold</b>\n${E}[39m\n` } }));
  state.messages.push({ id: 61, sender: 'stoat', recipient: 'owner', ts: state.now, status: 'delivered', attachments: [],
    content: 'Patch:\n```\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n```\n```python\ndef f(): pass\n```\n\nRun `buzz tasks` **now**:\n\n- one\n\n| a | b |\n|---|---|\n| 1 | 2 |' });
  try {
    await page.goto(base + '#/agent/stoat');
    await page.locator('.scope summary').click();
    const pre = page.locator('.scope pre');
    await pre.getByText('red', { exact: true }).waitFor();
    const color = text => pre.locator('span', { hasText: text }).evaluate(e => {
      const s = getComputedStyle(e); return [s.color, s.fontWeight];
    });
    assert.deepEqual(await color('red'), ['rgb(224, 108, 85)', '400']);
    assert.deepEqual(await color('pink'), ['rgb(215, 135, 135)', '700']);
    assert.equal(await pre.locator('b').count(), 0);
    assert.match(await pre.innerText(), /^plain red pink <b>not bold<\/b>$/);
    const bubble = page.locator('.thread .msg .md').last();
    const tint = sel => bubble.locator(sel).first().evaluate(e => getComputedStyle(e).color);
    assert.equal(await tint('.hljs-addition'), 'rgb(143, 191, 111)');
    assert.equal(await tint('.hljs-deletion'), 'rgb(224, 108, 85)');
    assert.equal(await bubble.locator('.hljs-keyword').first().innerText(), 'def');
    // Inline code, bold and table headers are off honey (rgb(242, 169, 59)),
    // which marks the dashboard's own controls; fenced code keeps its colors.
    assert.equal(await tint('p > code'), 'rgb(166, 227, 161)');
    assert.equal(await tint('strong'), 'rgb(255, 135, 175)');
    assert.equal(await tint('th'), 'rgb(255, 247, 230)');
    assert.equal(await bubble.locator('li').first().evaluate(e => getComputedStyle(e, '::marker').color), 'rgb(168, 152, 120)');
    assert.notEqual(await tint('pre code'), 'rgb(166, 227, 161)');
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});


for (const width of [390, 1500]) {
  test(`interrupt controls at ${width}px send control keys with terminal closed and guard rapid Ctrl+C`, async () => {
    const {page, state, errors} = await setup(width, 900, width < 500);
    const sent=[];
    let outcome='ok';
    await page.route('**/agents/stoat/terminal', async route => {
      sent.push(route.request().postDataJSON());
      if(outcome==='failed') return route.fulfill({status:409,json:{detail:{error:'recipient offline'}}});
      if(outcome==='unknown') return route.fulfill({status:502,json:{detail:{status:'unknown',error:'could not type into the pane',detail:'connection lost'}}});
      return route.fulfill({json:{ok:true,user_id:'stoat'}});
    });
    try {
      await page.goto(base+'#/agent/stoat');
      const group=page.getByRole('group',{name:'Interrupt stoat',exact:true});
      const ctrlC=group.getByRole('button',{name:'Send Ctrl+C to stoat',exact:true});
      const ctrlB=group.getByRole('button',{name:'Send Ctrl+B to stoat',exact:true});
      await ctrlC.waitFor();
      assert.equal(await page.locator('details.scope').getAttribute('open'),null);
      await ctrlC.click();
      await group.getByRole('status').filter({hasText:'Ctrl+C sent.'}).waitFor();
      assert.equal(await ctrlC.isDisabled(),true);
      // Even a synthetic extra click cannot bypass the synchronous guard.
      await ctrlC.evaluate(b=>b.dispatchEvent(new MouseEvent('click',{bubbles:true})));
      assert.deepEqual(sent,[{key:'C-c'}]);
      await ctrlB.click();
      await group.getByRole('status').filter({hasText:'Ctrl+B sent.'}).waitFor();
      assert.deepEqual(sent,[{key:'C-c'},{key:'C-b'}]);
      await page.waitForFunction(()=>!document.querySelector('.agent-interrupt button').disabled);
      outcome='unknown';
      await ctrlC.click();
      await group.getByRole('status').filter({hasText:'not confirmed'}).waitFor();
      assert.equal(sent.length,3);
      outcome='failed';
      await ctrlB.click();
      await group.getByRole('status').filter({hasText:'recipient offline'}).waitFor();
      assert.equal(await ctrlB.isEnabled(),true);
      assert.equal(await page.locator('details.scope').getAttribute('open'),null);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);
      state.recipients.find(r=>r.user_id==='stoat').pane_alive=false;
      await page.waitForFunction(()=>[...document.querySelectorAll('.agent-interrupt button')].every(b=>b.disabled));
      assert.equal(await ctrlC.isDisabled(),true);
      assert.equal(await ctrlB.isDisabled(),true);
      assert.deepEqual(errors,[]);
    } finally {await page.close();}
  });
}

test('owner notes edit on the agent detail page, persist beside live status, and clear', async () => {
  const { page, state, errors } = await setup(390,844);
  let fail = false;
  await page.route('**/agents/stoat/owner-note', async route => {
    if (fail) return route.fulfill({status:403,json:{detail:{error:'owner only'}}});
    const text = route.request().postDataJSON().text;
    state.recipients[0].owner_note = text || null;
    state.recipients[0].summaries.unshift({source:'owner',text,ts:state.now});
    await route.fulfill({json:{ok:true,owner_note:text || null}});
  });
  try {
    await page.goto(base+'#/agent/stoat');
    const note = page.locator('.stage .owner-note');
    await note.waitFor();
    assert.equal(await note.count(),1);
    assert.equal(await page.locator('#agent-sidebar .owner-note').count(),0);
    await note.getByRole('button', {name:'Add owner note for stoat'}).click();
    await note.getByRole('textbox').fill('rhizome integration plan');
    await note.getByRole('button', {name:'Save note'}).click();
    await note.getByText('📌 you: rhizome integration plan').waitFor();
    assert.match(await page.locator('.doing-box .now').textContent(), /Reviewing mobile/);
    await page.locator('.status-history summary').click();
    await page.getByText('you noted: rhizome integration plan').waitFor();
    await note.getByRole('button', {name:'Edit owner note for stoat'}).click();
    await note.getByRole('textbox').fill('review design');
    fail = true;
    await note.getByRole('button', {name:'Save note'}).click();
    await note.getByRole('alert').filter({hasText:'owner only'}).waitFor();
    assert.equal(state.recipients[0].owner_note,'rhizome integration plan');
    fail = false;
    await note.getByRole('button', {name:'Save note'}).click();
    await note.getByText('📌 you: review design').waitFor();
    await page.reload();
    await note.getByText('📌 you: review design').waitFor();
    await note.getByRole('button', {name:'Edit owner note for stoat'}).click();
    await note.getByRole('button', {name:'Clear note'}).click();
    await note.getByRole('button', {name:'Add owner note for stoat'}).waitFor();
    assert.equal(state.recipients[0].owner_note,null);
    await page.goto(base+'#/');
    await page.locator('.agents-panel').waitFor();
    assert.equal(await page.locator('.owner-note').count(),0);
    await fit(page);
    assert.deepEqual(errors,[]);
  } finally { await page.close(); }
});

for (const platform of ['MacIntel','Linux x86_64']) {
  test(`terminal shortcut toggles the detail pane without losing drafts: ${platform}`, async () => {
    const {page, errors} = await setup(1440,1000,false);
    await page.addInitScript(platform => Object.defineProperty(navigator,'platform',{value:platform}),platform);
    const modifier = platform === 'MacIntel' ? 'Meta' : 'Control';
    try {
      await page.goto(base+'#/agent/stoat');
      const scope = page.locator('.scope');
      assert.equal(await scope.getAttribute('open'),null);
      const composer = page.locator('.thread .composer textarea').first();
      await composer.fill('keep this chat draft');
      await composer.press(`${modifier}+Shift+y`);
      await page.waitForFunction(() => document.querySelector('.scope').open);
      await scope.locator('pre').filter({hasText:'Reviewing mobile layouts'}).waitFor();
      assert.equal(await composer.inputValue(),'keep this chat draft');
      const input = scope.getByRole('textbox');
      await input.fill('/model');
      await input.press(`${modifier}+Shift+y`);
      await page.waitForFunction(() => !document.querySelector('.scope').open);
      assert.equal(await scope.locator('summary').evaluate(e => e === document.activeElement),true);
      await page.keyboard.press(`${modifier}+Shift+y`);
      assert.equal(await input.inputValue(),'/model');
      // Bare typing, wrong modifiers, and key repeat never toggle it.
      await page.keyboard.press('y');
      await page.keyboard.press(`${modifier}+y`);
      await page.evaluate(() => window.dispatchEvent(new KeyboardEvent('keydown',{code:'KeyY',shiftKey:true,repeat:true,ctrlKey:navigator.platform!=='MacIntel',metaKey:navigator.platform==='MacIntel'})));
      assert.equal(await scope.evaluate(e => e.open),true);
      await page.keyboard.press(`${modifier}+k`);
      await page.keyboard.press(`${modifier}+Shift+y`);
      assert.equal(await scope.evaluate(e => e.open),true);
      await page.keyboard.press('Escape');
      await page.keyboard.press(`${modifier}+Shift+y`);
      await page.waitForFunction(() => !document.querySelector('.scope').open);
      await scope.locator('summary').click();
      await page.keyboard.press(`${modifier}+Shift+y`);
      await page.waitForFunction(() => !document.querySelector('.scope').open);
      assert.deepEqual(errors,[]);
    } finally { await page.close(); }
  });
}


test('the spawn form offers each machine its own start folders and sends the pick', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  state.nodes[0].spawn_dirs = ['~/agents', '~/oa/marin'];
  state.nodes[1].spawn_dirs = ['~/agents', '~/marin'];
  await page.route('**/api/spawn-options', r => r.fulfill({ json: { harnesses: [
    { flavor: 'claude', models: [] }, { flavor: 'codex', models: [] }] } }));
  const sent = [];
  await page.route('**/agents/spawn', r => { sent.push(r.request().postDataJSON());
    r.fulfill({ json: { ok: true, user_id: 'newbie', tmux_pane: '%9', launch: 'ok' } }); });
  try {
    await page.goto(base + '#/agent/stoat');
    const form = page.locator('#agent-sidebar form.spawn');
    const folder = form.locator('select[title="start folder"]');
    await folder.waitFor();
    assert.deepEqual(await folder.locator('option').allTextContents(), ['~/agents', '~/oa/marin']);
    await folder.selectOption('~/oa/marin');
    await form.locator('button[type=submit]').click();
    for (let i = 0; i < 20 && sent.length < 1; i++) await page.waitForTimeout(50);
    await form.locator('select[title="machine"]').selectOption('karans-mbp');
    // ~/oa/marin is not a Mac folder, so the pick falls back to the Mac's first.
    assert.deepEqual(await folder.locator('option').allTextContents(), ['~/agents', '~/marin']);
    assert.equal(await folder.inputValue(), '~/agents');
    await form.locator('button[type=submit]').click();
    await form.locator('button[type=submit]', { hasText: 'spawn agent' }).waitFor();
    for (let i = 0; i < 20 && sent.length < 2; i++) await page.waitForTimeout(50);
    assert.equal(sent[0].cwd, '~/oa/marin');
    assert.equal(sent[0].node, undefined);
    assert.deepEqual([sent[1].node, sent[1].cwd], ['karans-mbp', '~/agents']);
    // A machine that lists none shows no folder choice and sends none.
    state.nodes[1].spawn_dirs = [];
    await page.reload();
    await form.locator('select[title="machine"]').selectOption('karans-mbp');
    assert.equal(await folder.count(), 0);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('an owner chat scrolled up offers a jump to the newest message, counting new ones', async () => {
  const { page, state, errors } = await setup(1500, 900, false);
  for (let i = 0; i < 40; i++) {
    state.messages.push({ id: 200 + i, sender: i % 2 ? 'stoat' : 'owner', recipient: i % 2 ? 'owner' : 'stoat',
      content: `filler ${i}`, ts: state.now, status: 'delivered', attachments: [] });
  }
  try {
    await page.goto(base + '#/agent/stoat');
    const box = page.locator('.thread .msgs', { hasText: 'filler 39' }).first();
    await box.getByText('filler 39').waitFor();
    const jump = box.locator('.jump-bottom');
    assert.equal(await jump.count(), 0);  // at the bottom: nothing to jump to
    await box.evaluate(e => { e.scrollTop = 0; e.dispatchEvent(new Event('scroll')); });
    await jump.waitFor();
    assert.equal((await jump.innerText()).trim(), '↓ Jump to bottom');
    // New agent messages while away are counted on the button; the view stays put.
    state.messages.push({ id: 300, sender: 'stoat', recipient: 'owner', content: 'fresh news', ts: state.now,
      status: 'delivered', attachments: [] });
    await jump.getByText('· 1 new').waitFor({ timeout: 15000 });
    assert.ok(await box.evaluate(e => e.scrollTop < 50));
    await jump.click();
    await jump.waitFor({ state: 'detached' });
    assert.ok(await box.evaluate(e => e.scrollHeight - e.scrollTop - e.clientHeight < 10));
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('chat history is tall by default: about two thirds of the window, at least 340px', async () => {
  for (const [w, h, want] of [[1500, 900, 585], [1500, 500, 340], [1500, 1600, 900]]) {
    const { page, errors } = await setup(w, h, false);
    try {
      await page.goto(base + '#/agent/stoat');
      const box = page.locator('.thread .msgs').first();
      await box.waitFor();
      assert.equal(Math.round(await box.evaluate(e => e.getBoundingClientRect().height)), want);
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  }
});

for (const width of [320,390,1440]) {
  test(`reply quote jumps to a loaded message without horizontal overflow: ${width}`, async () => {
    const {page,state,errors} = await setup(width,844,width<1000);
    const original = state.messages[1];
    for (let i=3;i<50;i++) state.messages.push({id:i,sender:'stoat',recipient:'owner',content:`filler message ${i}`,ts:state.now+i,status:'delivered',attachments:[]});
    state.messages.push({id:50,sender:'owner',recipient:'stoat',content:'a linked answer',reply_to:2,reply_preview:{sender:'stoat',content:original.content},ts:state.now+50,status:'delivered',attachments:[]});
    state.messages.push({id:51,sender:'owner',recipient:'stoat',content:'backfilled answer',reply_to:2,reply_preview:{sender:'stoat',content:original.content},ts:state.now+51,status:'delivered',attachments:[]});
    try {
      await page.goto(base+'#/agent/stoat');
      const quote = page.locator('[data-message-id="50"] .reply-quote');
      await quote.waitFor();
      if (width === 390 && process.env.TASK354_SCREENSHOT) await page.locator(".thread").screenshot({path:process.env.TASK354_SCREENSHOT});
      assert.match(await quote.innerText(),/stoat\nTesting phone/);
      const originalNode = page.locator('[data-message-id="2"]');
      const history = page.locator('.thread .msgs');
      assert.ok(await history.evaluate(e => e.scrollTop)>100);
      await quote.click();
      await page.waitForFunction(() => document.querySelector('[data-message-id="2"]').classList.contains('reply-highlight'));
      const [target,box] = await Promise.all([originalNode.boundingBox(),history.boundingBox()]);
      assert.ok(target.y>=box.y && target.y < box.y+box.height);
      assert.doesNotMatch(await page.locator('[data-message-id="51"] .bubble').innerText(), /reply to message/);
      assert.match(await page.locator('[data-message-id="51"] .reply-quote').innerText(),/stoat/);
      if (width < 1100) await fit(page);
      assert.deepEqual(errors,[]);
    } finally { await page.close(); }
  });
}

test('reply quote opens an unloaded original in place and handles unavailable history', async () => {
  const {page,state,errors} = await setup(390,844);
  state.messages = [{id:900,sender:'owner',recipient:'stoat',content:'answer with off-page original',reply_to:5,reply_preview:{sender:'stoat',content:'original off-page snippet'},ts:state.now,status:'delivered',attachments:[]}];
  let missing = true;
  await page.route('**/messages?id=5', r => missing
    ? r.fulfill({status:404,json:{detail:{error:'no message'}}})
    : r.fulfill({json:{messages:[{id:5,sender:'stoat',recipient:'owner',content:'The entire original message '+('longword'.repeat(30)),attachments:[]}]}}));
  try {
    await page.goto(base+'#/agent/stoat');
    const quote = page.getByRole('button',{name:'Show original message 5'});
    await quote.click();
    await page.getByRole('alert').filter({hasText:'no longer available'}).waitFor();
    missing = false;
    await quote.click();
    await page.locator('.reply-original').filter({hasText:'The entire original message'}).waitFor();
    await fit(page);
    await quote.click();
    assert.equal(await page.locator('.reply-original').count(),0);
    assert.deepEqual(errors,[]);
  } finally { await page.close(); }
});

for (const stale of ['success', 'error']) {
  test(`dashboard polls skip overlap and ignore superseded ${stale} completions`, async () => {
    const {page,state,errors} = await setup(1440,900,false);
    let calls = 0, releaseOld, releaseNew, oldStarted, newStarted;
    const oldReady = new Promise(resolve => oldStarted = resolve);
    const newReady = new Promise(resolve => newStarted = resolve);
    const oldGate = new Promise(resolve => releaseOld = resolve);
    const newGate = new Promise(resolve => releaseNew = resolve);
    await page.route('**/agents/stoat/owner-note', async route => {
      state.recipients[0].owner_note = route.request().postDataJSON().text;
      await route.fulfill({json:{ok:true}});
    });
    await page.route('**/api/state', async route => {
      const number = ++calls;
      const snapshot = structuredClone(state);
      if (number === 2) {
        snapshot.recipients[0].summaries[0].text = 'STALE SNAPSHOT';
        oldStarted(); await oldGate;
        return route.fulfill({status:stale === 'error' ? 503 : 200,json:snapshot});
      }
      if (number === 3) {
        newStarted(); await newGate;
        snapshot.recipients[0].summaries[0].text = 'CURRENT SNAPSHOT';
        snapshot.messages.push({id:3,sender:'stoat',recipient:'owner',content:'fresh after queued refresh',ts:state.now,status:'delivered',attachments:[]});
      }
      if (stale === 'error' && number === 4)
        return route.fulfill({status:503,json:snapshot});
      if (stale === 'error' && number >= 5)
        snapshot.recipients[0].summaries[0].text = 'RECOVERED SNAPSHOT';
      await route.fulfill({json:snapshot});
    });
    try {
      await page.goto(base+'#/agent/stoat');
      await page.locator('.doing-box .now').filter({hasText:'Reviewing mobile'}).waitFor();
      await oldReady;
      // At least one more periodic tick occurs while request 2 is held.
      await page.waitForTimeout(2200);
      assert.equal(calls,2);
      await page.locator('.stage').getByRole('button',{name:'Add owner note for stoat'}).click();
      await page.locator('.stage .owner-note textarea').fill('refresh after mutation');
      await page.locator('.stage .owner-note').getByRole('button',{name:'Save note'}).click();
      await page.locator('.stage .owner-note').getByRole('button',{name:'Add owner note for stoat'}).waitFor();
      assert.equal(calls,2); // mutation refresh coalesces, rather than overlaps
      releaseOld(); await newReady;
      assert.match(await page.locator('.doing-box .now').innerText(),/Reviewing mobile/);
      assert.equal(await page.locator('header.top .beacon.down').count(),0);
      releaseNew();
      await page.locator('.doing-box .now').filter({hasText:'CURRENT SNAPSHOT'}).waitFor();
      await page.locator('.msg.fresh[data-message-id="3"]').waitFor();
      assert.equal(calls,3);
      if (stale === 'error') {
        await page.locator('header.top .beacon.down').waitFor();
        await page.locator('.doing-box .now').filter({hasText:'RECOVERED SNAPSHOT'}).waitFor();
        assert.equal(await page.locator('header.top .beacon.down').count(),0);
      }
      assert.deepEqual(errors,[]);
    } finally { releaseOld(); releaseNew(); await page.close(); }
  });
}

test('a refresh queued at poll completion gets its own fresh snapshot', async () => {
  const {page,state,errors} = await setup(1440,900,false);
  let calls=0, noteRequested;
  const noteReady=new Promise(resolve => noteRequested=resolve);
  await page.exposeFunction('noteRequested',()=>noteRequested());
  await page.addInitScript(() => {
    const originalFetch=window.fetch.bind(window);
    window.fetch=(input,options)=> {
      if (String(input).endsWith('/agents/stoat/owner-note')) {
        return new Promise(resolve => {
          window.releaseNote=()=>resolve(new Response('{}',{status:200}));
          window.noteRequested();
        });
      }
      return originalFetch(input,options);
    };
    window.__TAURI__={core:{invoke:()=>{
      window.releaseNote?.();
      return Promise.resolve();
    }}};
  });
  await page.route('**/api/state',async route=>{
    const number=++calls;
    const snapshot=structuredClone(state);
    snapshot.recipients[0].summaries[0].text=`snapshot ${number}`;
    if(number===2) {
      await noteReady;
      // Changed attention invokes the bridge during snapshot application.
      // This settles the mutation before the poll's promise finalizer runs.
      snapshot.recipients[1].activity.status='idle';
    }
    if(number>=3) snapshot.recipients[0].owner_note='saved note';
    await route.fulfill({json:snapshot});
  });
  try {
    await page.goto(base+'#/agent/stoat');
    await page.locator('.doing-box .now').filter({hasText:'snapshot 1'}).waitFor();
    await page.locator('.stage').getByRole('button',{name:'Add owner note for stoat'}).click();
    await page.locator('.stage .owner-note textarea').fill('saved note');
    await page.locator('.stage .owner-note').getByRole('button',{name:'Save note'}).click();
    await page.locator('.stage .owner-note textarea').waitFor({state:'detached'});
    // A queued refresh must complete now, without waiting for the next 2s tick.
    await page.locator('.stage .owner-note').getByText('📌 you: saved note').waitFor({timeout:1000});
    assert.equal(calls,3);
    assert.deepEqual(errors,[]);
  } finally {await page.close();}
});


test('hive stop corner appears only during bee drags and preserves registration', async () => {
  const {page,state,errors} = await setup(1440,1000,false);
  await page.emulateMedia({reducedMotion:'reduce'});
  let outcome='failed';
  const mutations=[];
  page.on('request',r=>{if(r.method()!=='GET') mutations.push(new URL(r.url()).pathname);});
  await page.route('**/agents/stoat/stop',async route=>{
    if(outcome==='failed') return route.fulfill({status:500,json:{detail:{error:'node busy'}}});
    if(outcome==='unknown') return route.fulfill({status:502,json:{detail:{error:'lost reply',status:'unknown'}}});
    state.recipients[0].pane_alive=false;
    await route.fulfill({json:{ok:true}});
  });
  const drag=async()=>{
    const bee=await page.evaluate(()=>{
      const b=window.__hive.bees().get('stoat');
      const r=document.querySelector('canvas').getBoundingClientRect();
      return{x:r.x+b.x,y:r.y+b.y};
    });
    const zone=page.locator('.hive-trash-zone');
    assert.equal(await zone.isVisible(),false);
    await page.mouse.move(bee.x,bee.y);
    await page.mouse.down();
    assert.equal(await zone.isVisible(),false);
    await page.mouse.move(bee.x+8,bee.y+8,{steps:2});
    await zone.waitFor({state:'visible'});
    assert.match(await zone.innerText(),/Stop agent/);
    const box=await zone.boundingBox();
    await page.mouse.move(box.x+box.width/2,box.y+box.height/2,{steps:10});
    assert.equal(await zone.evaluate(e=>e.classList.contains('over')),true);
    await page.mouse.up();
    assert.equal(await zone.isVisible(),false);
  };
  try {
    await page.goto(base+'#/');
    await page.waitForFunction(()=>window.__hive?.bees().has('stoat'));
    const canvas=page.locator('canvas');
    assert.match(await canvas.getAttribute('aria-label'),/drop a bee.*stop its agent.*resume agent/);
    assert.equal(await page.locator('.hive-trash-zone').isVisible(),false);
    await drag();
    const prompt=await answer(page,'Cancel');
    assert.match(prompt,/Stop stoat on karans-linux/);
    assert.match(prompt, /"resume agent" on its page brings the session back later/);
    assert.deepEqual(mutations,[]);
    await drag();
    await answer(page);
    await page.getByRole('status').filter({hasText:'Could not stop agent: node busy'}).waitFor();
    assert.equal(state.recipients[0].pane_alive,true);
    outcome='unknown';
    await drag();
    await answer(page);
    await page.getByRole('status').filter({hasText:'Stop not confirmed'}).waitFor();
    assert.equal(state.recipients[0].pane_alive,true);
    outcome='ok';
    await drag();
    await answer(page);
    await page.waitForFunction(()=>!window.__hive.bees().has('stoat'));
    assert.equal(state.recipients.some(r=>r.user_id==='stoat'),true);
    assert.equal(state.recipients[0].team_id,1);
    assert.equal(state.tasks[0].assignee,'stoat');
    assert.deepEqual(mutations,Array(3).fill('/agents/stoat/stop'));
    assert.equal(await page.locator('.hive-trash-zone').isVisible(),false);
    assert.deepEqual(errors,[]);
  } finally {await page.close();}
});

for (const width of [390,1440]) {
  test(`agent switcher previews and searches note before latest status: ${width}`, async () => {
    const {page,state,errors}=await setup(width,900,width<1000);
    const note='Rhizome integration plan '+('long preview '.repeat(24))+'needle-at-end';
    state.recipients[0].owner_note=note;
    state.recipients[0].summaries=[{source:'owner',text:'ignored owner history'}, {source:'agent',text:'overridden runtime update'}];
    state.recipients[1].summaries=[{source:'owner',text:'ignored owner history'}, {source:'title',text:'Investigating query latency'}, {source:'agent',text:'outdated runtime update'}];
    try {
      await page.goto(base+'#/');
      await page.locator('.quick-switch-launchers > button').last().click();
      const dialog=page.getByRole('dialog',{name:'Switch agent'});
      await dialog.waitFor();
      const stoat=dialog.locator('#switch-agent-stoat');
      const preview=stoat.locator('.quick-switch-summary');
      assert.equal(await preview.innerText(),'📌 note: '+note);
      assert.equal(await preview.getAttribute('title'),'📌 note: '+note);
      assert.match(await stoat.locator('small').first().innerText(),/agent-swarm · karans-linux · working/);
      const clipped=await preview.evaluate(el=>{
        const s=getComputedStyle(el);
        return{whiteSpace:s.whiteSpace,overflow:s.overflow,textOverflow:s.textOverflow,clipped:el.scrollWidth>el.clientWidth};
      });
      assert.deepEqual(clipped,{whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis',clipped:true});
      const rect=await dialog.boundingBox();
      assert.ok(rect.x>=0 && rect.x+rect.width<=width+1);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      const input=dialog.getByRole('combobox');
      await input.fill('rhizome needle-at-end');
      assert.equal(await dialog.getByRole('option').count(),1);
      assert.equal(await dialog.getByRole('option').locator('b').innerText(),'stoat');
      await input.fill('overridden runtime update');
      assert.equal(await dialog.getByRole('option').count(),0);
      await input.fill('query latency');
      assert.equal(await dialog.getByRole('option').count(),1);
      assert.equal(await dialog.getByRole('option').locator('.quick-switch-summary').innerText(),'Investigating query latency');
      await input.fill('ignored owner history');
      assert.equal(await dialog.getByRole('option').count(),0);
      await input.fill('outdated runtime update');
      assert.equal(await dialog.getByRole('option').count(),0);
      assert.deepEqual(errors,[]);
    } finally {await page.close();}
  });
}

test('sidebar chip and tile tooltips prefer owner note and fall back to current status', async () => {
  const {page,state,errors}=await setup(1440,900,false);
  state.recipients[0].owner_note='Pinned integration plan';
  state.recipients[0].summaries=[{source:'owner',text:'old owner history'}, {source:'agent',text:'Current runtime fallback'}];
  state.recipients[1].summaries=[{source:'owner',text:'old owner history'}, {source:'title',text:'Current status from title'}, {source:'agent',text:'older status'}];
  try {
    await page.goto(base+'#/');
    const sidebar=page.locator('#agent-sidebar');
    const chip=sidebar.locator('.team-mate[href="#/agent/stoat"]');
    await chip.waitFor();
    await chip.hover();
    const title=await chip.getAttribute('title');
    assert.match(title,/stoat · karans-linux · working/);
    assert.match(title,/📌 note: Pinned integration plan/);
    assert.doesNotMatch(title,/Current runtime fallback|old owner history/);
    const other=sidebar.locator(`.team-mate[href="#/agent/${names[1]}"]`);
    assert.match(await other.getAttribute('title'),/Current status from title/);
    assert.doesNotMatch(await other.getAttribute('title'),/old owner history|older status/);
    assert.doesNotMatch(await sidebar.innerText(),/Pinned integration plan|Current runtime fallback/);
    await sidebar.getByRole('button',{name:'tiles',exact:true}).click();
    const tile=sidebar.locator('.bee-tile[href="#/agent/stoat"]');
    await tile.waitFor();
    await tile.hover();
    assert.equal(await tile.getAttribute('title'),title);
    assert.match(await sidebar.locator(`.bee-tile[href="#/agent/${names[1]}"]`).getAttribute('title'),/Current status from title/);
    assert.doesNotMatch(await sidebar.innerText(),/Pinned integration plan|Current runtime fallback/);
    state.recipients[0].owner_note=null;
    await page.waitForFunction(()=>document.querySelector('#agent-sidebar .bee-tile[href="#/agent/stoat"]')?.title.includes('Current runtime fallback'));
    assert.doesNotMatch(await tile.getAttribute('title'),/📌 note:|old owner history|Pinned integration plan/);
    assert.deepEqual(errors,[]);
  } finally {await page.close();}
});
