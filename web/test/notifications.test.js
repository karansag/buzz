import { test } from 'node:test';
import assert from 'node:assert/strict';
import { notificationReporter } from '../src/notifications.js';

const message = (id, extra = {}) => ({id, sender: 'fake-agent', recipient: 'owner', content: 'Fake job done', notify: 1, ...extra});
test('browser notifications seed history, require hidden/granted, deduplicate and open the agent', () => {
  const shown = [], opened = [], doc = {hidden: true};
  class Notice {
    static permission = 'granted';
    constructor(title, options) { this.title = title; this.options = options; shown.push(this); }
    close() { this.closed = true; }
  }
  const report = notificationReporter({Notification: Notice, document: doc, open: agent => opened.push(agent)});
  report([message(1)]);
  assert.equal(shown.length, 0);
  report([message(1), message(2)]);
  assert.equal(shown.length, 1);
  assert.equal(shown[0].title, 'fake-agent');
  assert.equal(shown[0].options.body, 'Fake job done');
  shown[0].onclick();
  assert.deepEqual(opened, ['fake-agent']);
  assert.equal(shown[0].closed, true);
  report([message(2)]);
  report([message(3, {notify: 0}), message(4, {recipient: 'another-agent'})]);
  doc.hidden = false;
  report([message(5)]);
  doc.hidden = true;
  Notice.permission = 'default';
  report([message(6)]);
  Notice.permission = 'denied';
  report([message(7)]);
  assert.equal(shown.length, 1);
});

test('native notifications forward once, retry rejected invokes, and never also use the browser', async () => {
  const calls = [];
  let reject = true;
  const report = notificationReporter({invoke: async (command, payload) => {
    calls.push([command, payload]);
    if (reject) throw new Error('temporarily unavailable');
  }, Notification: class { constructor() { throw new Error('browser delivery in app'); } }});
  report([]);
  report([message(1)]);
  await new Promise(resolve => setImmediate(resolve));
  reject = false;
  report([message(1)]);
  await new Promise(resolve => setImmediate(resolve));
  report([message(1)]);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[1], ['agent_notification', {id: 1, agent: 'fake-agent', body: 'Fake job done'}]);
});
