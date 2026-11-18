import { test } from 'node:test';
import assert from 'node:assert/strict';
import { contextChip } from '../src/context.js';

test('the context chip shows the harness figure, escalates when full and says nothing without one', () => {
  assert.equal(contextChip(null), null);
  assert.equal(contextChip(undefined), null);
  assert.deepEqual(contextChip({percent: 6, window: null}), {
    text: 'context 6%', level: 'normal',
    title: "Context window 6% full, as the harness's own footer shows it",
  });
  assert.equal(contextChip({percent: 13.1, window: '1.0M'}).text, 'context 13.1%');
  assert.match(contextChip({percent: 13.1, window: '1.0M'}).title, /of a 1\.0M-token window/);
  assert.equal(contextChip({percent: 69.9, window: null}).level, 'normal');
  assert.equal(contextChip({percent: 70, window: null}).level, 'warn');
  assert.equal(contextChip({percent: 89, window: null}).level, 'warn');
  assert.equal(contextChip({percent: 90, window: null}).level, 'critical');
  const unknown = contextChip({percent: null, window: '131K'});
  assert.equal(unknown.text, 'context ?');
  assert.match(unknown.title, /131K/);
});
