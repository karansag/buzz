import test from "node:test";
import assert from "node:assert/strict";
import { stepView, tabHash } from "../src/views.js";

const views = ["#/", "#/chats", "#/tasks", tabHash("usage"), tabHash("prs")];

test("views step in header order and wrap at both ends", () => {
  assert.equal(stepView("#/", views, 1), "#/chats");
  assert.equal(stepView("#/chats?q=deploy", views, 1), "#/tasks");
  assert.equal(stepView("#/tasks", views, 1), "#/tab/usage");
  assert.equal(stepView("#/tab/prs", views, -1), "#/tab/usage");
  assert.equal(stepView("#/tab/prs", views, 1), "#/");
  assert.equal(stepView("#/", views, -1), "#/tab/prs");
});

test("an agent page or an empty hash counts as the overview", () => {
  assert.equal(stepView("#/agent/stoat", views, 1), "#/chats");
  assert.equal(stepView("", views, -1), "#/tab/prs");
});
