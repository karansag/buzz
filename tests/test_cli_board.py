"""`buzz board`: the CLI side of team boards."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import httpx
import pytest

from agent_swarm import client


def _response(status: int = 200, body: dict | None = None) -> SimpleNamespace:
    body = {} if body is None else body
    return SimpleNamespace(
        is_success=status < 400,
        status_code=status,
        text=json.dumps(body),
        headers={"content-type": "application/json"},
        json=lambda: body,
    )


def _page(**over) -> dict:
    post = {
        "id": 42, "author": "gannet", "subject": None, "reply_to": None, "replies": 2,
        "created_at": 1_000.0, "preview": "how the footer should read", "mentions_me": True,
    }
    post.update(over.pop("post", {}))
    page = {"team_id": 7, "name": "Buzz", "archived": False, "posts": [post],
            "has_older": False, "has_newer": False, "unread": 3}
    page.update(over)
    return page


@pytest.fixture()
def hub(monkeypatch):
    """A hub that answers the board routes and records every call."""
    gets: list[tuple[str, dict]] = []
    posts: list[tuple[str, dict]] = []
    monkeypatch.setattr(client, "base_url", lambda: "http://hub.test")
    monkeypatch.setattr(client, "_own_team", lambda: "7")
    monkeypatch.setattr(client, "_headers", lambda: {})
    monkeypatch.setattr(client, "_acting_fields", lambda: {})
    monkeypatch.setattr(client.time, "time", lambda: 1_600.0)

    def get(url, params=None, **kw):
        gets.append((url, dict(params or {})))
        if url.endswith("/board/42"):
            return _response(200, {"post": {"id": 42, "author": "gannet", "subject": "Footer rules",
                                            "body": "one line per batch, not per post",
                                            "created_at": 1_600.0, "reply_to": None},
                                   "replies": [{"id": 43, "author": "skink", "body": "agreed",
                                                "created_at": 1_590.0, "reply_to": 42}]})
        if "/teams/missing/" in url:
            return _response(404, {"detail": {"error": "no such team", "detail": "give a team name or id"}})
        return _response(200, _page())

    def post(url, json=None, **_kw):
        posts.append((url, dict(json or {})))
        return _response(201, {"id": 44, "team_id": 7, "author": "otter", "created_at": 1_600.0,
                               "reply_to": json.get("reply_to")})

    monkeypatch.setattr(client.httpx, "get", get)
    monkeypatch.setattr(client.httpx, "post", post)
    return SimpleNamespace(gets=gets, posts=posts)


def test_a_bare_board_reads_the_unread_posts_and_marks_them(hub, capsys):
    assert client.main(["board"]) == 0
    (url, params), = hub.gets
    assert url == "http://hub.test/teams/7/board"
    assert params == {"mark": 1, "unread": 1}
    out = capsys.readouterr().out
    assert "board Buzz (team 7): 1 new" in out
    assert "#42 gannet 10m ago, 2 replies, mentions you" in out
    assert "how the footer should read" in out


def test_read_pages_by_id_without_the_unread_filter(hub, capsys):
    assert client.main(["board", "read", "--after", "41", "--limit", "5"]) == 0
    (_, params), = hub.gets
    assert params == {"mark": 1, "after": 41, "limit": 5}
    assert "unread" not in params


def test_read_takes_a_team_name_and_passes_it_through(hub):
    assert client.main(["board", "read", "--team", "Buzz"]) == 0
    assert hub.gets[0][0] == "http://hub.test/teams/Buzz/board"


def test_a_team_given_before_the_subcommand_survives(hub):
    assert client.main(["board", "--team", "Buzz", "read"]) == 0
    assert hub.gets[0][0] == "http://hub.test/teams/Buzz/board"


def test_the_page_says_where_the_rest_of_it_is(hub, capsys):
    hub.gets.clear()
    client.httpx.get = lambda url, params=None, **kw: _response(200, _page(
        posts=[{"id": 42, "author": "gannet", "created_at": 1_600.0, "preview": "b"},
               {"id": 51, "author": "skink", "created_at": 1_600.0, "preview": "c"}],
        has_older=True, has_newer=True))
    assert client.main(["board", "read"]) == 0
    out = capsys.readouterr().out
    assert "older: buzz board read --team 7 --before #42" in out
    assert "newer: buzz board read --team 7 --after #51" in out


def test_read_can_print_the_hub_json(hub, capsys):
    assert client.main(["board", "read", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "Buzz"


def test_show_prints_the_post_and_its_replies(hub, capsys):
    assert client.main(["board", "show", "42"]) == 0
    assert hub.gets[0][0] == "http://hub.test/teams/7/board/42"
    out = capsys.readouterr().out
    assert "#42 gannet" in out and "subject: Footer rules" in out
    assert "one line per batch, not per post" in out
    assert "1 reply:" in out and "#43 skink" in out and "agreed" in out


def test_a_post_prints_its_id(hub, capsys):
    assert client.main(["board", "post", "--subject", "Results", "the table is below"]) == 0
    (url, payload), = hub.posts
    assert url == "http://hub.test/teams/7/board"
    assert payload["body"] == "the table is below"
    assert payload["subject"] == "Results"
    assert len(payload["client_id"]) == 32
    assert "posted #44 on board 7" in capsys.readouterr().out


def test_a_reply_points_at_its_root(hub, capsys):
    assert client.main(["board", "reply", "42", "agreed"]) == 0
    (_, payload), = hub.posts
    assert payload["reply_to"] == 42 and payload["body"] == "agreed"
    assert "replied to #42: #44 on board 7" in capsys.readouterr().out


def test_a_long_body_can_come_from_stdin(hub, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("a long finding\n"))
    assert client.main(["board", "post", "-"]) == 0
    assert hub.posts[0][1]["body"] == "a long finding\n"


def test_a_timeout_is_retried_once_with_the_same_client_id(hub, monkeypatch, capsys):
    calls: list[dict] = []
    real_post = client.httpx.post

    def flaky(url, json=None, **kw):
        calls.append(dict(json))
        if len(calls) == 1:
            raise httpx.TimeoutException("timed out")
        return real_post(url, json=json, **kw)

    monkeypatch.setattr(client.httpx, "post", flaky)
    assert client.main(["board", "post", "hello"]) == 0
    assert len(calls) == 2 and calls[0]["client_id"] == calls[1]["client_id"]
    assert "retrying once with the same client id" in capsys.readouterr().err


def test_a_second_timeout_says_the_post_is_not_there(hub, monkeypatch, capsys):
    def dead(url, json=None, **kw):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(client.httpx, "post", dead)
    assert client.main(["board", "post", "hello"]) == 1
    assert "not on the board" in capsys.readouterr().err


def test_a_refusal_shows_the_hub_reason(hub, capsys):
    assert client.main(["board", "read", "--team", "missing"]) == 1
    assert "error: no such team (give a team name or id)" in capsys.readouterr().err


def test_no_team_and_no_team_flag_is_an_error(monkeypatch, capsys):
    monkeypatch.setattr(client, "_own_team", lambda: None)
    assert client.main(["board"]) == 2
    assert "you are on no team" in capsys.readouterr().err

def test_the_request_says_who_is_asking(hub, monkeypatch):
    # A loopback request with no actor fields is taken for the owner, which is
    # how a live post ended up authored by "owner" instead of the agent.
    monkeypatch.setattr(client, "_acting_fields",
                        lambda: {"tmux_pane": "%0", "node": "karans-linux", "pane_in_tree": True})
    assert client.main(["board"]) == 0
    assert hub.gets[0][1] == {"tmux_pane": "%0", "node": "karans-linux",
                              "pane_in_tree": True, "mark": 1, "unread": 1}
    assert client.main(["board", "post", "hi"]) == 0
    assert hub.posts[0][1]["tmux_pane"] == "%0"
    client.main(["board", "show", "42"])
    assert hub.gets[-1][1]["node"] == "karans-linux"
