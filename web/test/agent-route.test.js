import test from "node:test";
import assert from "node:assert/strict";
import { AGENT_ROUTE, agentHash, messageParam, parseAgentRoute, showAgentMessage } from "../src/agent-route.js";

test("an agent route reads a handle and an optional message id", () => {
  assert.deepEqual(parseAgentRoute("#/agent/stoat"), { user: "stoat", messageId: null });
  assert.deepEqual(parseAgentRoute("#/agent/stoat?m=42"), { user: "stoat", messageId: 42 });
  // Handles are percent-encoded, so only the first ? starts the query.
  assert.equal(parseAgentRoute("#/agent/a%20b?m=7").user, "a b");
  assert.deepEqual(parseAgentRoute("#/agent/a%3Fb?m=7"), { user: "a?b", messageId: 7 });
});

test("anything else is not an agent route", () => {
  assert.equal(parseAgentRoute("#/"), null);
  assert.equal(parseAgentRoute("#/chats?view=queens"), null);
  assert.equal(parseAgentRoute("#/task/agent/stoat"), null);
  assert.equal(parseAgentRoute(AGENT_ROUTE), null, "an empty handle opens nothing");
  assert.equal(parseAgentRoute(), null);
});

test("a message id that cannot be used is ignored, not fatal", () => {
  for (const query of ["m=", "m=abc", "m=0", "m=-3", "m=1.5", "view=queens"]) {
    assert.deepEqual(parseAgentRoute(`#/agent/stoat?${query}`), { user: "stoat", messageId: null });
  }
  assert.equal(messageParam("m=12&q=x"), 12);
});

test("links round-trip through the parser", () => {
  assert.equal(agentHash("stoat"), "#/agent/stoat");
  assert.equal(agentHash("stoat", 42), "#/agent/stoat?m=42");
  assert.equal(agentHash("odd name/1"), "#/agent/odd%20name%2F1");
  assert.deepEqual(parseAgentRoute(agentHash("odd name/1", 9)), { user: "odd name/1", messageId: 9 });
});

test("a search UI can open a message without a page reload", () => {
  const seen = [];
  const real = { history: globalThis.history, dispatchEvent: globalThis.dispatchEvent, HashChangeEvent: globalThis.HashChangeEvent };
  try {
    globalThis.history = { replaceState: (_state, _title, url) => seen.push(["url", url]) };
    globalThis.dispatchEvent = event => seen.push(["event", event.type]);
    // Node has Event but not HashChangeEvent; the app only reads location.hash.
    globalThis.HashChangeEvent = undefined;
    showAgentMessage("stoat", 42);
    assert.deepEqual(seen, [["url", "#/agent/stoat?m=42"], ["event", "hashchange"]]);
  } finally {
    globalThis.history = real.history;
    globalThis.dispatchEvent = real.dispatchEvent;
    globalThis.HashChangeEvent = real.HashChangeEvent;
  }
});
