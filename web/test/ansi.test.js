import test from "node:test";
import assert from "node:assert/strict";
import { color256, parseAnsi, runStyle, trimAnsiEnd } from "../src/ansi.js";

const E = "\x1b";

test("plain text is one unstyled run", () => {
  assert.deepEqual(parseAnsi("hello\nworld"), [{ text: "hello\nworld", style: {} }]);
});

test("basic, bright, 256 and truecolor foregrounds and backgrounds", () => {
  const runs = parseAnsi(`${E}[31mred${E}[0m ${E}[92mlime${E}[39m ${E}[38;5;174mpink ${E}[48;2;10;20;30mon${E}[49m${E}[m.`);
  assert.deepEqual(runs.map(r => r.text), ["red", " ", "lime", " ", "pink ", "on", "."]);
  assert.equal(runs[0].style.fg, "#e06c55");
  assert.deepEqual(runs[1].style, {});
  assert.equal(runs[2].style.fg, "#b5e08f");
  assert.deepEqual(runs[3].style, {});  // 39 resets the foreground
  assert.equal(runs[4].style.fg, color256(174));
  assert.deepEqual(runs[5].style, { fg: color256(174), bg: "#0a141e" });
  assert.deepEqual(runs[6].style, {});
});

test("the 256-color palette matches xterm's cube and grays", () => {
  assert.equal(color256(16), "#000000");
  assert.equal(color256(174), "#d78787");
  assert.equal(color256(231), "#ffffff");
  assert.equal(color256(232), "#080808");
  assert.equal(color256(255), "#eeeeee");
});

test("attributes set and clear one at a time", () => {
  const runs = parseAnsi(`${E}[1;3mbold-italic${E}[22mitalic${E}[23;4munder${E}[24;7mrev`);
  assert.deepEqual(runs.map(r => r.style), [
    { bold: true, italic: true }, { italic: true }, { underline: true }, { reverse: true },
  ]);
  assert.deepEqual(runStyle({ bold: true, underline: true, strike: true }),
    { fontWeight: "bold", textDecoration: "underline line-through" });
  assert.deepEqual(runStyle({ reverse: true, fg: "#111111" }), { color: "var(--term-bg)", background: "#111111" });
  assert.equal(runStyle({}), undefined);
});

test("markup in the pane stays text and other escape sequences are dropped", () => {
  const runs = parseAnsi(`<b>x</b>${E}]8;;https://e.com${E}\\link${E}]8;;${E}\\${E}[2K${E}[?25l${E}]0;title\x07 end`);
  assert.deepEqual(runs, [{ text: "<b>x</b>link end", style: {} }]);
});

test("malformed or truncated codes do not throw or leak into the text", () => {
  for (const bad of [`${E}[38;5m`, `${E}[38;5;999mx`, `${E}[38;2;1;2mx`, `${E}[38mx`, `${E}[`, `x${E}`, `${E}[;;31mx`]) {
    const runs = parseAnsi(bad);
    assert.ok(runs.every(r => !r.text.includes(E)), JSON.stringify(bad));
  }
  assert.deepEqual(parseAnsi(`${E}[38;5;999mx`), [{ text: "x", style: {} }]);
  assert.equal(parseAnsi(`${E}[;;31mx`)[0].style.fg, "#e06c55");
});

test("trailing blank lines and their reset codes are trimmed", () => {
  assert.equal(trimAnsiEnd(`prompt ${E}[39m\n\n${E}[0m  \n`), "prompt");
  assert.equal(trimAnsiEnd(""), "");
  assert.equal(trimAnsiEnd(null), "");
});
