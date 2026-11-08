import test from "node:test";
import assert from "node:assert/strict";

import { deliveryOutcome, draftClientId, spawnOutcome, spawnTarget, unansweredOutcome } from "../src/outcome.js";

test("a returned draft keeps its client id only while unchanged", () => {
  const draft = { text: "deploy", context: "", images: ["a.png"] };
  const retryOf = { ...draft, clientId: "first" };
  assert.equal(draftClientId(draft, retryOf, () => "new"), "first");
  assert.equal(draftClientId({ ...draft, text: "deploy now" }, retryOf, () => "new"), "new");
  assert.equal(draftClientId({ ...draft, images: [] }, retryOf, () => "new"), "new");
  assert.equal(draftClientId(draft, null, () => "new"), "new");
});

test("a delivery is judged by its status, not by the HTTP status", () => {
  assert.deepEqual(deliveryOutcome(true, { ok: true, status: "delivered" }), { status: "delivered", reason: null });
  assert.deepEqual(
    deliveryOutcome(true, { ok: false, status: "unknown", delivery_error: "socket closed" }),
    { status: "unknown", reason: "socket closed" },
  );
  assert.deepEqual(
    deliveryOutcome(true, { ok: false, status: "failed", delivery_error: "pane gone" }),
    { status: "failed", reason: "pane gone" },
  );
  assert.deepEqual(
    deliveryOutcome(false, { detail: { error: "recipient offline: node laptop is not connected" } }),
    { status: "failed", reason: "recipient offline: node laptop is not connected" },
  );
  assert.equal(unansweredOutcome(new TypeError("Failed to fetch")).status, "uncertain");
});

const HARNESSES = [{ flavor: "claude", models: [] }, { flavor: "codex", models: [] }];
const HUB = { name: "hub", local: true, connected: true };

test("no pick, or the hub picked, spawns on the hub with every harness", () => {
  assert.equal(spawnTarget([HUB], "", HARNESSES).node, null);
  assert.deepEqual(spawnTarget([HUB], "hub", HARNESSES).harnesses, HARNESSES);
});

test("a connected remote offers only the harnesses it reported", () => {
  const nodes = [HUB, { name: "laptop", connected: true, harnesses: ["codex"] }];
  const t = spawnTarget(nodes, "laptop", HARNESSES);
  assert.equal(t.ok, true);
  assert.equal(t.node, "laptop");
  assert.deepEqual(t.harnesses.map(h => h.flavor), ["codex"]);
});

test("a picked remote that disconnects or is revoked is kept and refused, never swapped for the hub", () => {
  const gone = spawnTarget([HUB], "laptop", HARNESSES);
  assert.equal(gone.ok, false);
  assert.equal(gone.node, "laptop");
  assert.match(gone.reason, /no longer enrolled/);
  const down = spawnTarget([HUB, { name: "laptop", connected: false, harnesses: ["codex"] }], "laptop", HARNESSES);
  assert.equal(down.ok, false);
  assert.match(down.reason, /not connected/);
});

test("a remote with nothing spawnable cannot be spawned on", () => {
  const t = spawnTarget([HUB, { name: "laptop", connected: true, harnesses: [] }], "laptop", HARNESSES);
  assert.equal(t.ok, false);
  assert.match(t.reason, /no spawnable harness/);
  assert.deepEqual(t.harnesses, []);
});

test("a spawn answer distinguishes ok, unknown launch, and unknown creation", () => {
  assert.equal(spawnOutcome(true, { user_id: "otter", launch: "ok" }).status, "ok");
  const launch = spawnOutcome(true, { user_id: "otter", launch: "unknown", launch_error: "timed out" });
  assert.equal(launch.status, "unknown");
  assert.equal(launch.user, "otter");
  assert.equal(spawnOutcome(false, { detail: { status: "unknown", detail: "no report" } }).status, "unknown");
  assert.equal(spawnOutcome(false, { detail: { status: "failed", detail: "no space" } }).status, "failed");
});


test("an unreadable or unrecognised answer proves nothing either way", () => {
  for (const body of [null, undefined, "<html>502</html>", [], {}, { ok: true }]) {
    assert.equal(deliveryOutcome(true, body).status, "uncertain", JSON.stringify(body));
    assert.equal(deliveryOutcome(false, body).status, "uncertain", JSON.stringify(body));
    assert.notEqual(spawnOutcome(true, body).status, "ok", JSON.stringify(body));
    assert.equal(spawnOutcome(true, body).status, "uncertain", JSON.stringify(body));
    assert.equal(spawnOutcome(false, body).status, "uncertain", JSON.stringify(body));
  }
});

test("an explicit unknown is honoured whatever the HTTP status", () => {
  assert.equal(deliveryOutcome(false, { status: "unknown", delivery_error: "lost" }).status, "unknown");
  assert.equal(deliveryOutcome(false, { detail: { status: "unknown", error: "lost" } }).status, "unknown");
  assert.equal(spawnOutcome(true, { detail: { status: "unknown" } }).status, "unknown");
  // A recorded refusal with a reason is a real failure; a bare non-2xx is not.
  assert.equal(deliveryOutcome(false, { detail: { error: "recipient not registered" } }).status, "failed");
  assert.equal(deliveryOutcome(false, { detail: {} }).status, "uncertain");
  assert.equal(spawnOutcome(false, { detail: { error: "owner only" } }).status, "failed");
});

test("a spawn target lists the start folders of the machine it goes to", () => {
  const hub = { ...HUB, spawn_dirs: ["~/agents", "~/oa/marin"] };
  const mac = { name: "mac", connected: true, harnesses: ["claude"], spawn_dirs: ["~/agents", "~/marin"] };
  assert.deepEqual(spawnTarget([hub, mac], "", HARNESSES).dirs, ["~/agents", "~/oa/marin"]);
  assert.deepEqual(spawnTarget([hub, mac], "mac", HARNESSES).dirs, ["~/agents", "~/marin"]);
  assert.deepEqual(spawnTarget([HUB], "", HARNESSES).dirs, []);
  assert.deepEqual(spawnTarget([hub, { ...mac, connected: false }], "mac", HARNESSES).dirs, []);
});
