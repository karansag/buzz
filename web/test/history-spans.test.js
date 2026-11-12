import test from "node:test";
import assert from "node:assert/strict";
import { addSpan, gapsOf, spanOf } from "../src/history-spans.js";

test("a page becomes one span, however its ids are ordered", () => {
  assert.equal(spanOf([]), null);
  assert.deepEqual(spanOf([9, 4, 7]), { lo: 4, hi: 9 });
});

test("overlapping and touching ranges merge; separate ones do not", () => {
  let spans = addSpan([], 401, 700);
  assert.deepEqual(gapsOf(spans), []);
  // A window far below the first one leaves one hole.
  spans = addSpan(spans, 1, 170);
  assert.deepEqual(spans, [{ lo: 1, hi: 170 }, { lo: 401, hi: 700 }]);
  assert.deepEqual(gapsOf(spans), [{ after: 170, before: 401 }]);
  // Filling the hole from its lower edge closes it when it reaches the top.
  spans = addSpan(spans, 171, 400);
  assert.deepEqual(spans, [{ lo: 1, hi: 700 }]);
  assert.deepEqual(gapsOf(spans), []);
  // A range that only touches the edge is contiguous, not a hole of one id.
  assert.deepEqual(addSpan([{ lo: 10, hi: 20 }], 21, 30), [{ lo: 10, hi: 30 }]);
  assert.deepEqual(gapsOf(addSpan([{ lo: 10, hi: 20 }], 22, 30)), [{ after: 20, before: 22 }]);
});

test("a page inside a loaded range changes nothing", () => {
  const spans = [{ lo: 1, hi: 700 }];
  assert.deepEqual(addSpan(spans, 100, 200), [{ lo: 1, hi: 700 }]);
  assert.deepEqual(addSpan(spans, 1, 700), spans);
});

test("several holes are reported in order", () => {
  let spans = addSpan([], 1, 10);
  spans = addSpan(spans, 30, 40);
  spans = addSpan(spans, 60, 70);
  assert.deepEqual(gapsOf(spans), [
    { after: 10, before: 30 },
    { after: 40, before: 60 },
  ]);
});
