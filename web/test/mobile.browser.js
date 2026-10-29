// Run `npx playwright install chromium` once, then `npm run test:browser`.
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
  browser = await chromium.launch();
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
  const state = await mock(page);
  return { page, state, errors };
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
    assert.ok((await history.boundingBox()).height > before + 200);
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
    await page.waitForFunction(() => !!document.activeElement?.closest('.thread .composer'));
    await page.keyboard.press('Alt+BracketLeft');
    await page.waitForFunction(() => location.hash === '#/agent/stoat');
    await page.waitForFunction(() => document.querySelector('.thread .composer textarea')?.value === 'draft for stoat');
    // A conversation between two agents links to the other agent's page.
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
    await go('Control+Shift+BracketRight', '#/tab/usage');
    // From inside the tab's page too.
    await page.frameLocator('iframe.tab-frame').locator('#q').click();
    await go('Control+Shift+BracketRight', '#/tasks');
    await go('Control+Shift+BracketRight', '#/');
    await go('Control+Shift+BracketLeft', '#/tasks');
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
  const dialogs = [];
  page.on('dialog', d => { dialogs.push(d.message()); d.accept(); });
  try {
    await page.goto(base + '#/');
    const team = page.locator('#agent-sidebar .team-bees-group', { hasText: 'agent-swarm' });
    await team.locator('.team-bees-offline', { hasText: '1 offline: old-ghost' }).waitFor();
    await team.locator('button.retire').click();
    await page.locator('#agent-sidebar .team-bees-offline', { hasText: 'old-ghost' }).waitFor({ state: 'detached' });
    assert.deepEqual(asked, [['old-ghost']]);
    assert.match(dialogs[0], /Retire old-ghost\? It leaves the dashboard and its team\. Messages and tasks are kept\./);
    // A stopped agent's own page offers retire instead of stop.
    await page.goto(base + '#/agent/stopped-agent');
    await page.locator('.fhead button.retire', { hasText: 'retire agent' }).click();
    await page.waitForFunction(() => location.hash === '#/');
    assert.deepEqual(asked[1], ['stopped-agent']);
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
    await page.waitForSelector('.thread-goto');
    let s = await sides();
    assert.equal(s['from stoat'], true);
    assert.equal(s['from numbat'], false);
    // A thread with itself, or with the hub (supervisor nudges), has no agent page to open.
    assert.equal(await page.locator('.thread-goto').count(), 1);
    await page.goto(base + '#/agent/' + peer);
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
  const dialogs = [];
  page.on('dialog', d => { dialogs.push(d.message()); d.accept(); });
  try {
    await page.goto(base + '#/');
    const team = page.locator('#agent-sidebar .team-bees-group', { has: page.locator('.team-bees-name', { hasText: /^agent-swarm$/ }) });
    await team.getByRole('button', { name: 'Pick queen for agent-swarm' }).click();
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
    await team.waitFor({ state: 'detached' });
    assert.deepEqual(deletes, [1]);
    assert.match(dialogs[0], /Remove team agent-swarm\? Its agents keep running\./);
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
  const dialogs = [];
  page.on('dialog', d => { dialogs.push(d.message()); d.accept(); });
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
    await page.waitForFunction(() => location.hash !== '#/agent/stoat');
    assert.deepEqual(stops, ['stoat']);
    assert.match(dialogs[0], /^Stop stoat on /);
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

    await chip('stoat').dragTo(group('no team'));
    await page.waitForFunction(() => document.querySelector('#agent-sidebar .team-bees-group.loose a[href="#/agent/stoat"]'));
    await chip('ferret').dragTo(group('agent-swarm'));
    await page.waitForFunction(() => [...document.querySelectorAll('#agent-sidebar .team-bees-group:not(.loose) a')].some(a => a.getAttribute('href') === '#/agent/ferret'));
    // Dropping a chip on its own group changes nothing.
    await chip('ferret').dragTo(group('agent-swarm'));
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
    page.once('dialog', dialog => dialog.dismiss());
    await stop.click();
    assert.equal(calls, 0);
    page.once('dialog', dialog => {
      assert.match(dialog.message(), /stoat on karans-linux/);
      return dialog.accept();
    });
    await stop.click();
    await page.getByText('Stop not confirmed. Check the agent\'s status before retrying.', { exact: true }).waitFor();
    assert.equal(await stop.isEnabled(), true);
    page.once('dialog', dialog => dialog.accept());
    await stop.click();
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
