import { html } from "htm/preact";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import { mentionParts } from "./board-mentions.js";
import { ChatMessage } from "./chat-message.js";
import { disp, jsonInit, newClientId, plural, rel } from "./shared.js";

export const BOARD_ROUTE = "#/board";
const POLL_MS = 5000;
const BODY_LIMIT = 16384;
const SUBJECT_LIMIT = 120;

export function boardHash(team, post) {
  const params = new URLSearchParams();
  if (team != null) params.set("team", team);
  if (post != null) params.set("post", post);
  return params.size ? `${BOARD_ROUTE}?${params}` : BOARD_ROUTE;
}

export function parseBoardRoute(hash) {
  const [path, search] = hash.split("?");
  if (path !== BOARD_ROUTE) return null;
  const params = new URLSearchParams(search);
  const id = name => {
    const value = params.get(name);
    return /^[1-9]\d*$/.test(value ?? "") && Number.isSafeInteger(Number(value)) ? Number(value) : null;
  };
  return { team: id("team"), post: id("post") };
}

function UnreadBadge({ count }) {
  return count > 0 ? html`<span class="board-unread" aria-label=${`${count} unread posts`}>${count}</span>` : null;
}

export function BoardLink({ team }) {
  return html`<a class="team-board-link" href=${boardHash(team.id)}
      aria-label=${`${team.name} board${team.board_unread > 0 ? `, ${team.board_unread} unread posts` : ""}`}>
    Board <${UnreadBadge} count=${team.board_unread} />
  </a>`;
}

const BOARD_ERRORS = {
  board_archived: "This board is archived. Posts can still be read.",
  invalid_reply_target: "This post can no longer be replied to.",
  client_id_conflict: "The server has a different post under this submission ID.",
};

async function boardRequest(url, options, failure) {
  const response = await fetch(url, options).catch(error => {
    if (error.name === "AbortError") throw error;
    throw Error(failure);
  });
  const result = await response.json().catch(() => null);
  if (!response.ok || !result) {
    const error = result?.detail?.error;
    throw Error(Object.hasOwn(BOARD_ERRORS, error) ? BOARD_ERRORS[error] : typeof error === "string" ? error : failure);
  }
  return result;
}

function useBoard(teamId, postId) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const readRef = useRef(null);

  useEffect(() => {
    if (teamId === null) return;
    const controller = new AbortController();
    const { signal } = controller;
    const endpoint = `/teams/${teamId}/board`;
    let current = null;
    let reading = false;
    let queued = false;
    let timer;

    const read = async mode => {
      if (signal.aborted) return;
      if (document.hidden) {
        clearTimeout(timer);
        timer = setTimeout(() => read("refresh"), POLL_MS);
        return;
      }
      if (reading) {
        if (mode === "afterWrite") queued = true;
        return;
      }
      const older = mode === "older";
      if (older && !current?.has_older) return;
      clearTimeout(timer);
      reading = true;
      setBusy(true);

      try {
        if (postId !== null) {
          current = await boardRequest(`${endpoint}/${postId}`, { signal, cache: "no-store" }, "Could not load the post.");
        } else {
          const query = new URLSearchParams({ mark: "1" });
          if (older) query.set("before", current.posts[0].id);
          else if (current) query.set("after", current.posts.at(-1)?.id ?? 0);
          const page = await boardRequest(`${endpoint}?${query}`, { signal, cache: "no-store" }, "Could not load the board.");
          current = current ? {
            ...page,
            posts: older ? [...page.posts, ...current.posts] : [...current.posts, ...page.posts],
            has_older: older ? page.has_older : current.has_older,
            has_newer: older ? current.has_newer : page.has_newer,
          } : page;
        }
        if (!signal.aborted) {
          setData(current);
          setError("");
        }
      } catch (error) {
        if (!signal.aborted) setError(error.message);
      } finally {
        reading = false;
        if (!signal.aborted) {
          setBusy(false);
          if (queued) {
            queued = false;
            read("refresh");
          } else {
            timer = setTimeout(() => read("refresh"), POLL_MS);
          }
        }
      }
    };

    readRef.current = read;
    read("refresh");
    return () => {
      clearTimeout(timer);
      controller.abort();
      readRef.current = null;
    };
  }, [teamId, postId]);

  return { data, busy, error, read: mode => readRef.current?.(mode) };
}

function MentionText({ text, members }) {
  return mentionParts(text, members).map(({ text, mention }) =>
    mention ? html`<mark class="board-mention">${text}</mark>` : text);
}

function BoardComposer({ teamId, replyTo, onPosted }) {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const attempt = useRef(null);
  const inFlight = useRef(false);
  const tooLong = new TextEncoder().encode(body).length > BODY_LIMIT;
  const valid = body.trim() && !tooLong;

  const submit = async event => {
    event.preventDefault();
    if (!valid || inFlight.current) return;
    const title = subject.trim() || null;
    const same = attempt.current?.body === body && attempt.current.subject === title;
    const clientId = same ? attempt.current.id : newClientId();
    attempt.current = { body, subject: title, id: clientId };
    inFlight.current = true;
    setBusy(true);
    setError("");
    const uncertain = "Could not confirm the post. Retry to check without posting a duplicate.";
    try {
      const result = await boardRequest(`/teams/${teamId}/board`,
        jsonInit("POST", { body, subject: title, reply_to: replyTo, client_id: clientId }), uncertain);
      if (!Number.isSafeInteger(result.id)) throw Error(uncertain);
      attempt.current = null;
      setSubject("");
      setBody("");
      onPosted();
    } catch (error) {
      setError(error.message);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return html`<form class="board-composer" onSubmit=${submit}>
    ${replyTo === null && html`<label>Subject (optional)<input value=${subject}
      maxlength=${SUBJECT_LIMIT} disabled=${busy} onInput=${e => setSubject(e.target.value)} /></label>`}
    <label>${replyTo === null ? "New post" : "Reply"}
      <textarea value=${body} rows="4" disabled=${busy} onInput=${e => setBody(e.target.value)}></textarea>
    </label>
    <div class="board-compose-actions">
      <button type="submit" class="act" disabled=${busy || !valid}>${busy ? "posting…" : replyTo === null ? "post" : "reply"}</button>
      ${tooLong && html`<span role="alert">Post exceeds the 16 KB limit.</span>`}
      ${error && html`<span role="alert">${error}</span>`}
    </div>
  </form>`;
}

function BoardFeed({ data, read, busy, teamId, members, now }) {
  return html`<div class="board-feed">
    ${data.has_older && html`<button type="button" class="mini board-page-button" disabled=${busy}
      onClick=${() => read("older")}>${busy ? "loading…" : "load older posts"}</button>`}
    ${data.posts.length === 0 && html`<p class="board-status">No posts yet.</p>`}
    <ol class="board-posts">
      ${data.posts.map(post => html`<li key=${post.id} class="board-preview">
        <a class="board-preview-link" href=${boardHash(teamId, post.id)}>
          <${MentionText} text=${post.preview} members=${members} />
        </a>
        <div class="board-post-meta">
          <span>#${post.id} · ${disp(post.author)} · ${rel(post.created_at, now)}</span>
          ${post.reply_to !== null
            ? html`<a href=${boardHash(teamId, post.reply_to)}>Reply to #${post.reply_to}</a>`
            : post.replies > 0 && html`<a href=${boardHash(teamId, post.id)}>${plural(post.replies, "reply", "replies")}</a>`}
        </div>
      </li>`)}
    </ol>
    ${data.has_newer && html`<button type="button" class="mini board-page-button" disabled=${busy}
      onClick=${() => read("refresh")}>load newer posts</button>`}
  </div>`;
}

function BoardPost({ post, teamId, now, members }) {
  const message = { sender: post.author, content: post.body, ts: post.created_at };
  return html`<article class="board-post" aria-label=${`Post #${post.id}`}>
    ${post.subject && html`<h2><${MentionText} text=${post.subject} members=${members} /></h2>`}
    <${ChatMessage} m=${message} now=${now} right=${post.author === "owner"} mentions=${members}>
      <a class="board-permalink" href=${boardHash(teamId, post.id)} aria-label=${`Permalink to post #${post.id}`}>#${post.id}</a>
    </${ChatMessage}>
  </article>`;
}

export function BoardView({ teamId, postId, teams, now }) {
  const { data, busy, error, read } = useBoard(teamId, postId);
  const team = teams.find(team => team.id === teamId);
  const members = useMemo(() => new Set((team?.members || []).map(name => name.toLowerCase())), [team?.members]);
  const archived = !team || data?.archived;
  const title = data?.name || team?.name || `Team #${teamId}`;

  if (teamId === null) return html`<section class="team-board" aria-label="Team boards">
    <h2>Team boards</h2>
    ${teams.length ? html`<ul class="board-teams">
      ${teams.map(team => html`<li key=${team.id}><a href=${boardHash(team.id)}>
        ${team.name} <${UnreadBadge} count=${team.board_unread} />
      </a></li>`)}
    </ul>` : html`<p class="board-status">No teams yet.</p>`}
  </section>`;

  return html`<section class="team-board" aria-label=${`${title} board`}>
    <header class="board-head">
      <a href=${boardHash()}>Team boards</a>
      <h2>${title} board</h2>
      ${postId !== null && html`<a href=${boardHash(teamId)}>Back to feed</a>`}
      ${archived && data && html`<span class="board-status">Archived · read-only</span>`}
    </header>
    ${error && html`<div class="board-error" role="alert">${error}
      <button type="button" class="mini" onClick=${() => read("refresh")}>retry</button>
    </div>`}
    ${!data && !error && html`<p class="board-status" role="status">Loading board…</p>`}
    ${data && (postId === null
      ? html`<${BoardFeed} data=${data} read=${read} busy=${busy} teamId=${teamId} members=${members} now=${now} />`
      : html`<div class="board-thread">
          ${data.post.reply_to !== null && html`<a href=${boardHash(teamId, data.post.reply_to)}>Open thread #${data.post.reply_to}</a>`}
          <${BoardPost} post=${data.post} teamId=${teamId} members=${members} now=${now} />
          ${data.replies.length > 0 && html`<ol class="board-replies" aria-label="Replies">
            ${data.replies.map(post => html`<li key=${post.id}>
              <${BoardPost} post=${post} teamId=${teamId} members=${members} now=${now} />
            </li>`)}
          </ol>`}
        </div>`)}
    ${data && !archived && (postId === null || data.post.reply_to === null) && html`
      <${BoardComposer} teamId=${teamId} replyTo=${postId} onPosted=${() => read("afterWrite")} />`}
  </section>`;
}
