import test from "node:test";
import assert from "node:assert/strict";
import { renderMarkdown } from "../src/markdown.js";

test("tagged fences are syntax-highlighted", () => {
  const out = renderMarkdown("```python\ndef f():\n    return 'x'  # note\n```");
  assert.match(out, /<span class="hljs-keyword">def<\/span>/);
  assert.match(out, /<span class="hljs-string">&#x27;x&#x27;<\/span>|<span class="hljs-string">'x'<\/span>/);
  assert.match(out, /hljs-comment/);
});

test("an untagged unified diff is colored as a diff", () => {
  const out = renderMarkdown("```\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new\n```");
  assert.match(out, /<span class="hljs-deletion">-old/);
  assert.match(out, /<span class="hljs-addition">\+new/);
});

test("other untagged or unknown fences stay plain and escaped", () => {
  assert.equal(renderMarkdown("```\n<b>hi</b> - x\n```"), "<pre><code>&lt;b&gt;hi&lt;/b&gt; - x\n</code></pre>\n");
  assert.doesNotMatch(renderMarkdown("```cobol\nMOVE A TO B\n```"), /hljs-/);
});

test("highlighted code cannot inject markup", () => {
  const out = renderMarkdown("```python\ns = \"<img src=x onerror=alert(1)>\"\n```");
  assert.doesNotMatch(out, /<img/);
  assert.match(out, /&lt;img/);
});
