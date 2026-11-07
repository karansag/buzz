// Terminal colors for the dashboard's terminal view.
//
// The hub captures a pane with `tmux capture-pane -e`, which keeps SGR
// escape codes (colors, bold, ...). parseAnsi turns that text into runs of
// plain text with a style each. The caller renders the runs as text nodes,
// so nothing from the pane is ever inserted as HTML. Every other escape
// sequence (cursor moves, OSC titles and hyperlinks) is dropped.

// The 16 basic colors. Agents pick these expecting a dark terminal; these
// values are tuned for the dashboard's dark brown background.
const BASIC = [
  "#2b2419", "#e06c55", "#8fbf6f", "#f2c14e", "#6fa8dc", "#c38fd6", "#5fc4bf", "#d8ccb4",
  "#7a6a52", "#ff8f78", "#b5e08f", "#ffd97a", "#9cc8f0", "#ddb0ee", "#8ee6e0", "#f8f1e3",
];

const CUBE = [0, 95, 135, 175, 215, 255];

function hex(r, g, b) {
  return "#" + [r, g, b].map(v => v.toString(16).padStart(2, "0")).join("");
}

// xterm's 256-color palette: 16 basic, a 6x6x6 cube, then 24 grays.
export function color256(n) {
  if (n < 16) return BASIC[n];
  if (n < 232) {
    const i = n - 16;
    return hex(CUBE[Math.floor(i / 36)], CUBE[Math.floor(i / 6) % 6], CUBE[i % 6]);
  }
  const v = 8 + (n - 232) * 10;
  return hex(v, v, v);
}

const byte = v => Number.isInteger(v) && v >= 0 && v <= 255;

// Reads an extended color (38/48/58 ;5;n or ;2;r;g;b) starting at codes[i].
// Returns [color or null, how many codes it used].
function extended(codes, i) {
  if (codes[i + 1] === 5) {
    return [byte(codes[i + 2]) ? color256(codes[i + 2]) : null, 3];
  }
  if (codes[i + 1] === 2) {
    const [r, g, b] = codes.slice(i + 2, i + 5);
    return [byte(r) && byte(g) && byte(b) ? hex(r, g, b) : null, 5];
  }
  return [null, 1];
}

function apply(style, params) {
  // "ESC[m" means reset, same as "ESC[0m".
  const codes = params === "" ? [0] : params.split(/[;:]/).map(p => (p === "" ? 0 : Number(p)));
  const s = { ...style };
  for (let i = 0; i < codes.length; i++) {
    const c = codes[i];
    if (c === 0) Object.keys(s).forEach(k => delete s[k]);
    else if (c === 1) s.bold = true;
    else if (c === 2) s.dim = true;
    else if (c === 3) s.italic = true;
    else if (c === 4) s.underline = true;
    else if (c === 7) s.reverse = true;
    else if (c === 9) s.strike = true;
    else if (c === 22) { delete s.bold; delete s.dim; }
    else if (c === 23) delete s.italic;
    else if (c === 24) delete s.underline;
    else if (c === 27) delete s.reverse;
    else if (c === 29) delete s.strike;
    else if (c >= 30 && c <= 37) s.fg = BASIC[c - 30];
    else if (c >= 90 && c <= 97) s.fg = BASIC[c - 90 + 8];
    else if (c >= 40 && c <= 47) s.bg = BASIC[c - 40];
    else if (c >= 100 && c <= 107) s.bg = BASIC[c - 100 + 8];
    else if (c === 39) delete s.fg;
    else if (c === 49) delete s.bg;
    else if (c === 38 || c === 48 || c === 58) {
      const [value, used] = extended(codes, i);
      if (value && c === 38) s.fg = value;
      if (value && c === 48) s.bg = value;
      i += used - 1;
    }
  }
  return s;
}

// CSI ... final byte, OSC ... (BEL or ST), or any other two-byte escape.
const ESCAPE = /\x1b(?:\[([0-9;:?<=>]*)([@-~])|\][^\x07\x1b]*(?:\x07|\x1b\\)?|[@-Z\\-_]?)/g;

// Returns [{ text, style }], where style holds only the attributes that are set.
export function parseAnsi(input) {
  const text = input || "";
  const runs = [];
  let style = {};
  let last = 0;
  const push = (chunk) => {
    if (!chunk) return;
    const prev = runs[runs.length - 1];
    if (prev && prev.style === style) prev.text += chunk;
    else runs.push({ text: chunk, style });
  };
  for (const m of text.matchAll(ESCAPE)) {
    push(text.slice(last, m.index));
    last = m.index + m[0].length;
    // Only SGR ("m" with plain numeric parameters) changes the style.
    if (m[2] === "m" && /^[0-9;:]*$/.test(m[1])) style = apply(style, m[1]);
  }
  push(text.slice(last));
  return runs;
}

// Inline CSS for one run, or undefined for plain text.
export function runStyle(style) {
  let fg = style.fg, bg = style.bg;
  if (style.reverse) [fg, bg] = [bg || "var(--term-bg)", fg || "var(--term-fg)"];
  const css = {};
  if (fg) css.color = fg;
  if (bg) css.background = bg;
  if (style.bold) css.fontWeight = "bold";
  if (style.dim) css.opacity = "0.65";
  if (style.italic) css.fontStyle = "italic";
  const lines = [style.underline && "underline", style.strike && "line-through"].filter(Boolean);
  if (lines.length) css.textDecoration = lines.join(" ");
  return Object.keys(css).length ? css : undefined;
}

// Drops trailing whitespace, including blank lines that only carry escape codes.
export function trimAnsiEnd(text) {
  return (text || "").replace(/(?:\s|\x1b\[[0-9;:]*m)+$/, "");
}
