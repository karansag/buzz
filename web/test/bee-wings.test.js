import test from "node:test";
import assert from "node:assert/strict";
import { Bee } from "../src/shared.js";

// The bee faces right: head at x=44, tail at x=7. A wing tilted the other way
// puts its outer end over the head, which reads as a fish tail on the wrong
// end. These checks pin the sweep direction rather than the exact numbers.
const HEAD_X = 44;

function collect(node, type, out = []) {
  if (!node || typeof node !== "object") return out;
  if (node.type === type) out.push(node.props);
  const children = node.props?.children ?? node.children;
  for (const child of Array.isArray(children) ? children : [children]) collect(child, type, out);
  return out;
}

// The two ends of a wing ellipse's long axis, from `rotate(deg cx cy)`.
function tips({ transform, rx }) {
  const match = /^rotate\((-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\)$/.exec(transform);
  assert.ok(match, `wing transform ${transform} is not a plain rotate(deg cx cy)`);
  const [deg, cx, cy] = match.slice(1).map(Number);
  const rad = deg * Math.PI / 180;
  const dx = Number(rx) * Math.cos(rad);
  const dy = Number(rx) * Math.sin(rad);
  // The outer end is the one furthest from the body's centre line at y=21.
  const ends = [[cx - dx, cy - dy], [cx + dx, cy + dy]];
  ends.sort((a, b) => Math.abs(b[1] - 21) - Math.abs(a[1] - 21));
  return { cx, cy, outer: ends[0] };
}

test("each bee wing tilts back toward the tail", () => {
  const wings = collect(Bee({ node: "karans-linux", flavor: "pi" }), "ellipse")
    .filter(e => Number(e.rx) === 11);
  assert.equal(wings.length, 2, "expected a top wing and a bottom wing");

  for (const wing of wings) {
    const { cx, cy, outer } = tips(wing);
    assert.notEqual(cy, 21, "wings sit above and below the body's centre line");
    assert.ok(outer[0] < cx, `wing tip x=${outer[0].toFixed(1)} is forward of its anchor x=${cx}`);
    assert.ok(
      Math.abs(outer[0] - HEAD_X) > Math.abs(cx - HEAD_X),
      "the wing tip must sit further from the head than the wing's anchor",
    );
  }
});

test("the machine and harness encoding is unchanged", () => {
  const bee = Bee({ node: "karans-mbp", flavor: "codex", working: true });
  const body = collect(bee, "ellipse").find(e => Number(e.rx) === 19);
  assert.match(body.fill, /^#[0-9a-f]{6}$/i, "body is filled with the machine colour");
  const stripes = collect(bee, "path");
  assert.equal(stripes.length, 2, "one dark stripe pair and one harness stripe pair");
  assert.equal(stripes[1].stroke, "#56b4e9", "harness accent stays on the stripes");
  assert.ok(collect(bee, "circle").some(c => Number(c.r) === 28), "working halo still drawn");
});
