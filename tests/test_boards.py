import pytest
from fastapi.testclient import TestClient

from agent_swarm import boards, db, server


@pytest.fixture
def board(client, tmp_path):
    conn = db.connect(tmp_path / "db.sqlite")
    team = db.create_team(conn, "board team")["id"]
    db.register(conn, "puffin", "0:0.0", "fake-pi", flavor="pi",
                node=client.app.state.nodes.local.name, tmux_server="srv-1")
    db.set_agent_team(conn, "puffin", team)
    yield conn, team, f"/teams/{team}/board"
    conn.close()


ACTOR = {"agent_id": "fake-pi"}


def _post(client, path, **data):
    response = client.post(path, json={"body": "a report", **data})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_board_post_retry_thread_and_no_delivery(client, board):
    _, team, path = board
    data = {"body": "a report @PUFFIN", "client_id": "retry"}
    root = client.post("/teams/board%20team/board", json=data)
    assert root.status_code == 201 and root.json()["team_id"] == team
    duplicate = client.post(path, json=data)
    assert duplicate.status_code == 200 and duplicate.json() == root.json()
    conflict = client.post(path, json={**data, "body": "different"})
    assert conflict.status_code == 409 and conflict.json()["detail"]["error"] == "client_id_conflict"
    mid = root.json()["id"]
    reply = _post(client, path, reply_to=mid, **ACTOR)
    assert not client._calls
    listing = client.get(path, params={"thread": mid, **ACTOR}).json()
    assert [(r["id"], r["replies"], r["mentions_me"]) for r in listing["posts"]] == [
        (mid, 1, True), (reply, 0, False),
    ]
    detail = client.get(f"{path}/{mid}").json()
    assert detail["post"]["body"] == data["body"] and detail["replies"][0]["id"] == reply
    assert client.get(f"{path}/{reply}").json()["replies"] == []


def test_board_membership_revocation_and_archive(client, board):
    conn, team, path = board
    post_id = _post(client, path)
    assert client.get(path, params={**ACTOR, "unread": 1, "mark": 1}).status_code == 200
    db.set_agent_team(conn, "puffin", None)
    for url in (path, f"{path}/{post_id}"):
        assert client.get(url, params=ACTOR).status_code == 404
    assert client.post(path, json={"body": "revoked", **ACTOR}).status_code == 404
    db.set_agent_team(conn, "puffin", team)
    assert client.get(path, params=ACTOR).json()["unread"] == 0
    db.delete_team(conn, team)
    assert client.get(path).json()["archived"] is True
    assert client.get("/teams/board%20team/board").status_code == 404
    closed = client.post(path, json={"body": "archived"})
    assert closed.status_code == 409 and closed.json()["detail"]["error"] == "board_archived"
    assert client.get(path, params=ACTOR).status_code == 404


def test_board_invalid_reply_target_and_utf8_limit(client, board):
    conn, _, path = board
    root = _post(client, path)
    reply = _post(client, path, reply_to=root)
    foreign = db.create_team(conn, "another team")["id"]
    other = _post(client, f"/teams/{foreign}/board")
    for bad in (reply, other, other + 1):
        res = client.post(path, json={"body": "reply", "reply_to": bad})
        assert res.status_code == 422 and res.json()["detail"]["error"] == "invalid_reply_target"
    assert client.post(path, json={"body": "🐝" * 4096}).status_code == 201
    assert client.post(path, json={"body": "🐝" * 4097}).status_code == 422


def test_board_read_cap_never_skips_unreturned_posts_and_new_member_backlog(client, board):
    conn, team, path = board
    expected = [_post(client, path, body="🐝" * 200) for _ in range(30)]
    db.register(conn, "late", "0:1.0", "fake-late", flavor="pi",
                node=client.app.state.nodes.local.name, tmux_server="srv-1")
    db.set_agent_team(conn, "late", team)
    newest = _post(client, path)
    assert client.get(path, params={"agent_id": "fake-late"}).json()["unread"] == 21
    seen = []
    while True:
        res = client.get(path, params={"unread": 1, "mark": 1, "limit": 50, **ACTOR})
        assert res.status_code == 200, res.text
        assert len(res.content) <= 16_384
        page = res.json()
        ids = [post["id"] for post in page["posts"]]
        seen.extend(ids)
        assert len(seen) <= 31
        if not page["has_newer"]:
            break
        assert ids
    assert seen == [*expected, newest]
    backwards = client.get(path, params={"before": newest, "limit": 50}).json()
    assert backwards["has_older"] and backwards["posts"][-1]["id"] == expected[-1]


def test_board_cursor_clamps_after_hub_restore(client, board, tmp_path):
    conn, team, path = board
    latest = _post(client, path)
    conn.execute("UPDATE board_reads SET last_read_id=9999,last_hinted_id=9999")
    conn.commit()
    restarted = TestClient(server.create_app(tmp_path / "db.sqlite", monitor=False),
                           client=("127.0.0.1", 50000))
    assert tuple(conn.execute("SELECT last_read_id,last_hinted_id FROM board_reads").fetchone()) == (latest, latest)
    assert restarted.get(f"{path}/{latest}").status_code == 200
    mid = _post(restarted, path)
    listing = restarted.get(path, params={"unread": 1, **ACTOR}).json()
    assert [r["id"] for r in listing["posts"]] == [mid]


def test_board_rename_and_retirement_preserve_history_not_new_handle_state(client, board):
    conn, team, path = board
    mid = _post(client, path, **ACTOR)
    db.rename_recipient(conn, "puffin", "tern")
    assert client.get(f"{path}/{mid}").json()["post"]["author"] == "tern"
    retired = db.retire_recipient(conn, db.get_recipient(conn, "tern"))
    archive = retired["archive_id"]
    assert client.get(f"{path}/{mid}").json()["post"]["author"] == archive
    assert conn.execute("SELECT user_id FROM board_reads").fetchone()[0] == archive
    db.register(conn, "tern", "0:1.0", "fresh-pi", flavor="pi",
                node=client.app.state.nodes.local.name, tmux_server="srv-1")
    db.set_agent_team(conn, "tern", team)
    assert client.get(path, params={"agent_id": "fresh-pi", "unread": 1}).json()["unread"] == 1


def test_board_hint_only_in_existing_deliveries_and_summary_is_scoped(client, board):
    _, team, path = board
    _post(client, path, body="mail@puffin.test @PUFFIN @puffin")
    assert not client._calls
    for n in range(2):
        r = client.post("/owner/send", json={"recipient": "puffin", "content": f"normal {n}"})
        assert r.status_code == 200 and r.json()["status"] == "delivered"
    assert "[board board team: 1 new, 1 mentions you · buzz board read]" in client._calls[-2][1]
    assert "[board " not in client._calls[-1][1]
    assert all("[board " not in msg["content"] for msg in client.get("/messages").json()["messages"])
    view = client.get(f"/teams/{team}/view", params=ACTOR).json()
    assert view["board"]["unread"] == 1 and "board: 1 posts" in view["text"]
    digest = client.get("/digest", params={"team": team, **ACTOR}).json()
    assert digest["board"] == view["board"]
    assert digest["text"].splitlines()[-1].startswith("next:")
    assert client.get("/api/state").json()["teams"][0]["board_unread"] == 0
    assert boards.hint(board[0], team, "puffin") is None


def test_board_hint_remains_eligible_after_definite_delivery_failure(client, board, monkeypatch):
    from agent_swarm import nodes

    _, _, path = board
    _post(client, path)
    local = client.app.state.nodes.local
    deliver = local.deliver
    attempts = []

    def fail_once(op_id, pane, tmux_server, text, **kw):
        attempts.append(text)
        if len(attempts) == 1:
            return nodes.Result("failed", "pane unavailable")
        return deliver(op_id, pane, tmux_server, text, **kw)

    monkeypatch.setattr(local, "deliver", fail_once)
    outcomes = [client.post("/owner/send", json={"recipient": "puffin", "content": "normal"}).json()
                for _ in range(3)]
    assert [r["status"] for r in outcomes] == ["failed", "delivered", "delivered"]
    assert ["[board " in content for content in attempts] == [True, True, False]


def test_node_credential_cannot_read_board_as_owner(client, board):
    conn, _, path = board
    db.set_node_token(conn, "other-node", "fake-token")
    remote = TestClient(client.app, client=("100.64.0.5", 5000),
                        headers={"Authorization": "Bearer fake-token"})
    _post(client, path)
    assert remote.get(path).status_code == 403
    assert remote.post(path, json={"body": "spoof owner"}).status_code == 403


def test_numeric_board_links_cannot_be_shadowed_by_a_team_name(client, board):
    conn, team, path = board
    assert team == 1
    shadow = db.create_team(conn, "1")["id"]
    assert shadow != team
    original = _post(client, path, body="original board")
    other = _post(client, f"/teams/{shadow}/board", body="other board")
    response = client.get(path).json()
    assert response["team_id"] == team
    assert [p["id"] for p in response["posts"]] == [original]
    assert client.get(f"{path}/{other}").status_code == 404
    assert client.get(f"/teams/{team}/view").json()["team"]["id"] == team

    db.delete_team(conn, team)
    archive = client.get(path).json()
    assert archive["archived"] and archive["team_id"] == team
    assert client.get(f"{path}/{original}").json()["post"]["body"] == "original board"
    assert client.post(path, json={"body": "blocked"}).status_code == 409
    assert client.get(f"/teams/{team}/view").json()["team"]["id"] == shadow


def test_board_unread_count_reflects_the_marked_page(client, board):
    _, _, path = board
    for _ in range(3):
        _post(client, path)
    query = {**ACTOR, "unread": 1, "limit": 1}
    assert client.get(path, params=query).json()["unread"] == 3
    assert client.get(path, params={**query, "mark": 1}).json()["unread"] == 2
