import test from "node:test";
import assert from "node:assert/strict";
import { ownerChats } from "../src/chats.js";

const m = (id, sender, recipient, content, ts) => ({ id, sender, recipient, content, ts });
const messages = [
  m(1, "owner", "otter", "can you check the zephyr reducers?", 10),
  m(2, "otter", "owner", "yes, skew is small", 20),
  m(3, "owner", "tapir", "deploy the dashboard", 30),
  m(4, "tapir", "stoat", "peer chatter", 40),
  m(2, "otter", "owner", "yes, skew is small", 20),
];

test("one row per agent the owner talked with, newest first", () => {
  const chats = ownerChats(messages);
  assert.deepEqual(chats.map(c => [c.agent, c.count, c.last.id]), [["tapir", 1, 3], ["otter", 2, 2]]);
});

test("a search keeps conversations with a message containing every word", () => {
  const chats = ownerChats(messages, "Zephyr REDUCERS");
  assert.deepEqual(chats.map(c => [c.agent, c.match.id, c.matches]), [["otter", 1, 1]]);
  assert.deepEqual(ownerChats(messages, "zephyr deploy"), []);
});

import { agentThreads } from "../src/chats.js";

const talk = [
  m(10, "otter", "tapir", "can you review #12?", 100),
  m(11, "tapir", "otter", "on it", 160),
  m(12, "otter", "tapir", "thanks", 2000),          // after a quiet gap: a new thread
  m(13, "stoat", "otter", "STOP: lock busy", 2010),
  m(14, "stoat", "tapir", "STOP: lock busy", 2015),  // same text to two agents: a broadcast
  m(15, "stoat", "stoat", "wake up at 10", 2020),    // a note to itself
  m(16, "owner", "otter", "status?", 2030),          // the owner's chats are elsewhere
  m(11, "tapir", "otter", "on it", 160),             // a duplicate id
];

test("agent talk groups into bursts per pair, newest first, without owner chats or self notes", () => {
  const { threads, selfNotes } = agentThreads(talk);
  assert.equal(selfNotes, 1);
  assert.deepEqual(threads.map(t => [t.people.join("+"), t.broadcast, t.count, t.items.map(i => i.m.id)]), [
    ["stoat", true, 2, [13]],
    ["otter+tapir", false, 1, [12]],
    ["otter+tapir", false, 2, [10, 11]],
  ]);
  assert.deepEqual(threads[0].to, ["otter", "tapir"]);
  assert.deepEqual(threads[0].items[0].to, ["otter", "tapir"]);
});

test("search matches words in messages or agent names; members narrows to a team", () => {
  assert.deepEqual(agentThreads(talk, { query: "review TAPIR" }).threads.map(t => t.items[0].m.id), [10]);
  assert.deepEqual(agentThreads(talk, { query: "stoat" }).threads.map(t => t.items[0].m.id), [13]);
  assert.deepEqual(agentThreads(talk, { members: new Set(["stoat"]) }).threads.map(t => t.items[0].m.id), [13]);
});

test("a repeat of the same text much later is a new message, not part of the broadcast", () => {
  const { threads } = agentThreads([m(1, "a", "b", "ping", 0), m(2, "a", "c", "ping", 500)]);
  assert.deepEqual(threads.map(t => [t.broadcast, t.people.join("+")]), [[false, "a+c"], [false, "a+b"]]);
});
