// Run with `npm run test:browser` (see fixtures/browser.js).
import assert from "node:assert/strict";
import { test } from "node:test";
import { launch, openPage } from "./fixtures/browser.js";
import { fixture, mock } from "./fixtures/mobile-state.js";

let browser, base;
launch(started => ({ browser, base } = started));

async function setup(width) {
  const phone = width < 600;
  const { page, errors } = await openPage(browser, { viewport: { width, height: 800 }, isMobile: phone, hasTouch: phone });
  const state = fixture();
  const [team] = state.teams;
  team.board_unread = 3;
  const row = (id, body, fields = {}) => ({
    id, team_id: 1, body, author: "stoat", created_at: state.now - 60 + id,
    subject: null, reply_to: null, ...fields,
  });
  const posts = [
    row(1, "Older post"), row(3, "Unrelated post"),
    row(7, "## Build report\n\n- Ask **@STOAT** and `@stoat`.\n- Ignore user@stoat, @outside and @stoat-old.\n\n| Job | State |\n| --- | --- |\n| Web | Green |", {
      subject: "Release for @stoat",
    }),
    row(8, "Existing reply", { reply_to: 7 }),
  ];
  const submissions = [];
  const requests = [];
  let lost = false, nextId = 20, cursor = 1;
  const byClientId = new Map();
  await mock(page, state);
  await page.route(/\/teams\/\d+\/board(?:\/\d+)?(?:\?.*)?$/, async route => {
    const req = route.request();
    const url = new URL(req.url());
    const [, , teamId, , postId] = url.pathname.split("/");
    if (req.method() === "POST") {
      const payload = req.postDataJSON();
      submissions.push(payload);
      let post = byClientId.get(payload.client_id);
      const created = !post;
      if (created) {
        post = row(nextId++, payload.body, {
          author: "owner", subject: payload.subject, reply_to: payload.reply_to,
        });
        byClientId.set(payload.client_id, post);
        posts.push(post);
      }
      if (lost) {
        lost = false;
        return route.fulfill({ status: 200, body: "Unparseable response" });
      }
      const { id, team_id, author, created_at, reply_to } = post;
      return route.fulfill({ status: created ? 201 : 200, json: { id, team_id, author, created_at, reply_to } });
    }
    requests.push(url);
    if (postId) {
      const post = posts.find(post => post.id === Number(postId));
      if (!post) return route.fulfill({ status: 404, json: { detail: { error: "no such board post" } } });
      const replies = posts.filter(p => p.reply_to === post.id);
      return route.fulfill({ json: { post, replies } });
    }
    const before = Number(url.searchParams.get("before") ?? Infinity);
    const after = url.searchParams.has("after") ? Number(url.searchParams.get("after")) : null;
    const eligible = posts.filter(post => post.id < before && (after === null || post.id > after));
    // Use small cursor pages so the tests can exercise both directions.
    const selected = after === null ? eligible.slice(-2) : eligible.slice(0, 2);
    if (url.searchParams.get("mark") === "1" && selected.length) {
      cursor = Math.max(cursor, selected.at(-1).id);
      team.board_unread = posts.filter(p => p.id > cursor && p.author !== "owner").length;
    }
    const rows = selected.map(({ id, author, subject, created_at, reply_to, body }) => ({
      id, author, subject, created_at, reply_to,
      preview: subject || body.slice(0, 200),
      mentions_me: false, replies: posts.filter(p => p.reply_to === id).length,
    }));
    return route.fulfill({ json: {
      team_id: Number(teamId), name: state.teams.length ? team.name : `Team #${teamId}`,
      archived: !state.teams.length, posts: rows,
      has_older: Boolean(rows.length && posts[0].id < rows[0].id),
      has_newer: Boolean(rows.length && posts.at(-1).id > rows.at(-1).id),
      unread: team.board_unread,
    } });
  });
  return { page, state, requests, submissions, errors,
    add: (id, body) => posts.push(row(id, body)), loseNextPost: () => { lost = true; } };
}

for (const width of [390, 1280]) {
  test(`team board paging, mentions, permalink and owner composer at ${width}px`, async () => {
    const { page, requests, submissions, errors } = await setup(width);
    try {
      await page.goto(base + "#/board");
      const boardLink = page.locator(".board-teams a").getByText("agent-swarm");
      await boardLink.waitFor();
      assert.equal(await page.locator(".board-unread").first().textContent(), "3");
      assert.equal(requests.length, 0);
      await boardLink.click();

      const feed = page.locator(".board-posts .board-preview-link");
      await feed.first().waitFor();
      assert.deepEqual(await feed.allTextContents(), ["Release for @stoat", "Existing reply"]);
      assert.equal(requests[0].searchParams.get("mark"), "1");
      await page.getByRole("button", { name: "load older posts" }).click();
      await page.getByText("Older post", { exact: true }).waitFor();
      assert.deepEqual(await feed.allTextContents(), ["Older post", "Unrelated post", "Release for @stoat", "Existing reply"]);
      assert.equal(requests[1].searchParams.get("before"), "7");

      await page.getByRole("link", { name: "Release for @stoat" }).click();
      const detail = page.getByRole("article", { name: "Post #7" });
      await detail.waitFor();
      assert.equal(await detail.locator(".msg .bubble .md table td").count(), 2);
      assert.deepEqual(await detail.locator(".msg .board-mention").allTextContents(), ["@STOAT", "@stoat"]);
      assert.equal(await detail.locator("h2 .board-mention").textContent(), "@stoat");
      assert.equal(await detail.getByRole("link", { name: "Permalink to post #7" }).getAttribute("href"), "#/board?team=1&post=7");
      assert.ok(requests.some(url => url.pathname.endsWith("/board/7") && !url.searchParams.has("mark")));
      assert.equal(await page.locator(".board-replies article").count(), 1);

      await page.getByRole("textbox", { name: "Reply", exact: true }).fill("Reply from the owner.");
      await page.getByRole("button", { name: "reply", exact: true }).click();
      const reply = page.getByRole("article", { name: "Post #20" });
      await reply.locator(".msg.from-owner").waitFor();
      assert.equal(submissions[0].reply_to, 7);
      assert.equal(submissions[0].subject, null);
      assert.equal(await page.locator(".board-replies .board-replies").count(), 0);
      await reply.getByRole("link", { name: "Permalink to post #20" }).click();
      await page.getByRole("link", { name: "Open thread #7" }).waitFor();
      assert.equal(await page.getByRole("textbox", { name: "Reply", exact: true }).count(), 0);

      await page.getByRole("link", { name: "Back to feed" }).click();
      await page.getByRole("textbox", { name: "Subject (optional)" }).fill("New root");
      await page.getByRole("textbox", { name: "New post" }).fill("A root post.");
      await page.getByRole("button", { name: "post", exact: true }).click();
      await page.getByRole("link", { name: "New root", exact: true }).waitFor();
      assert.equal(submissions[1].reply_to, null);
      assert.equal(submissions[1].subject, "New root");
      assert.ok(!("author" in submissions[1]));
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });
}

test("a lost post acknowledgement keeps the draft and retries the same client ID", async () => {
  const { page, loseNextPost, submissions } = await setup(1280);
  try {
    await page.goto(base + "#/board?team=1");
    const body = page.getByRole("textbox", { name: "New post" });
    await body.fill("Keep only one copy.");
    const submit = page.getByRole("button", { name: "post", exact: true });
    loseNextPost();
    await submit.click();
    await page.getByRole("alert").getByText(/Could not confirm/).waitFor();
    assert.equal(await body.inputValue(), "Keep only one copy.");
    await submit.click();
    await page.getByRole("link", { name: "Keep only one copy.", exact: true }).waitFor();
    assert.deepEqual(submissions[1], submissions[0]);
    assert.equal(await body.inputValue(), "");
  } finally { await page.close(); }
});

test("only the open feed polls, reads forward, and archived links stay read-only", async () => {
  const { page, state, requests, add } = await setup(390);
  try {
    await page.clock.install();
    await page.goto(base + "#/board?team=1");
    await page.getByText("Existing reply", { exact: true }).waitFor();
    assert.equal(requests.length, 1);
    add(12, "New since the last page");
    await page.clock.runFor(4500);
    assert.equal(requests.length, 1);
    await page.clock.runFor(700);
    await page.getByText("New since the last page", { exact: true }).waitFor();
    assert.equal(requests[1].searchParams.get("after"), "8");

    await page.getByRole("link", { name: "Team boards", exact: true }).click();
    await page.getByRole("region", { name: "Team boards", exact: true }).waitFor();
    await page.locator(".board-teams .board-unread").waitFor({ state: "detached" });
    const count = requests.length;
    await page.clock.runFor(6000);
    assert.equal(requests.length, count);

    state.teams = [];
    await page.goto(base + "#/board?team=1&post=7");
    await page.getByText("Archived · read-only").waitFor();
    assert.equal(await page.getByRole("textbox", { name: "Reply", exact: true }).count(), 0);
  } finally { await page.close(); }
});
