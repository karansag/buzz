"""Explicit notifications use fake panes and never contact the real owner."""

import pytest

from agent_swarm import db, notifications
from tests.test_server import client  # noqa: F401


def test_notification_route_identity_history_and_cooldown(client):
    user = client.post('/register', json={'tmux_pane': '0:0.0'}).json()['user_id']
    payload = {'tmux_pane': '0:0.0', 'content': 'Fake job finished', 'context': 'test job'}
    response = client.post('/notify', json=payload)
    assert response.status_code == 200
    mid = response.json()['message_id']
    messages = client.get('/messages', params={'user': user}).json()['messages']
    m = next(m for m in messages if m['id'] == mid)
    assert (m['sender'], m['recipient'], m['notify'], m['context']) == (user, 'owner', 1, 'test job')
    assert any(m['id'] == mid and m['notify'] for m in client.get('/api/state').json()['messages'])
    assert any(m['id'] == mid and m['notify'] for m in client.get(f'/api/agents/{user}/messages').json()['messages'])
    assert not client._calls
    response = client.post('/notify', json=payload)
    assert response.status_code == 429
    assert response.headers['retry-after'] == '300'
    assert response.json()['detail'] == notifications.LIMIT_MESSAGE
    assert len(client.get('/messages').json()['messages']) == 1
    assert client.post('/send', json={**payload, 'recipient': 'owner'}).status_code == 200
    other = client.post('/register', json={'tmux_pane': '0:1.0'}).json()['user_id']
    assert other != user
    assert client.post('/notify', json={**payload, 'tmux_pane': '0:1.0'}).status_code == 200


def test_notification_rejects_unknown_sender_and_invalid_text(client):
    assert client.post('/notify', json={'tmux_pane': '0:2.0', 'content': 'hi'}).status_code == 404
    client.post('/register', json={'tmux_pane': '0:0.0'})
    for text in ['', '   ', 'bad\0text', 'a' * (notifications.MAX_TEXT_LENGTH + 1)]:
        assert client.post('/notify', json={'tmux_pane': '0:0.0', 'content': text}).status_code == 422
    assert client.get('/messages').json()['messages'] == []


def test_notification_limits_persist_and_reset_on_utc_day(tmp_path, monkeypatch):
    path = tmp_path / 'test.sqlite'
    conn = db.connect(path)
    now = [86400 * 100 + 10.0]
    monkeypatch.setattr(db.time, 'time', lambda: now[0])
    first = db.record_notification(conn, 'fake-agent', 'done')
    now[0] += notifications.COOLDOWN_SECONDS - .1
    with pytest.raises(notifications.NotificationLimit):
        db.record_notification(conn, 'fake-agent', 'too soon')
    now[0] += .1
    db.record_notification(conn, 'fake-agent', 'second')
    for _ in range(notifications.DAILY_LIMIT - 2):
        now[0] += notifications.COOLDOWN_SECONDS
        db.record_notification(conn, 'fake-agent', 'done')
    conn.close()
    conn = db.connect(path)
    now[0] += notifications.COOLDOWN_SECONDS
    with pytest.raises(notifications.NotificationLimit):
        db.record_notification(conn, 'fake-agent', 'seventh')
    assert conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 6
    now[0] = 86400 * 101
    db.record_notification(conn, 'fake-agent', 'new day')
    assert db.get_message(conn, first)['notify'] == 1
    conn.close()


def test_notify_migration_keeps_old_messages(tmp_path):
    path = tmp_path / 'old.sqlite'
    conn = db.connect(path)
    mid = db.record_message(conn, 'fake-agent', 'owner', None, 'old', 'delivered')
    conn.execute('ALTER TABLE messages DROP COLUMN notify')
    conn.close()
    conn = db.connect(path)
    assert db.get_message(conn, mid)['notify'] == 0
    db.record_notification(conn, 'fake-agent', 'new')
    assert conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 2
    conn.close()


def test_daily_api_limit_and_owner_messages_are_unaffected(client, monkeypatch):
    user = client.post('/register', json={'tmux_pane': '0:0.0'}).json()['user_id']
    now = [86400 * 100 + 1.0]
    monkeypatch.setattr(db.time, 'time', lambda: now[0])
    payload = {'tmux_pane': '0:0.0', 'content': 'Fake result'}
    for _ in range(notifications.DAILY_LIMIT):
        assert client.post('/notify', json=payload).status_code == 200
        now[0] += notifications.COOLDOWN_SECONDS
    result = client.post('/notify', json=payload)
    assert result.status_code == 429
    assert result.json()['detail'] == notifications.LIMIT_MESSAGE
    assert len(client.get('/messages').json()['messages']) == notifications.DAILY_LIMIT
    assert client.post('/owner/send', json={'recipient': user, 'content': 'owner note'}).status_code == 200


def test_notification_concurrent_connections_cannot_bypass_limit(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path = tmp_path / 'concurrent.sqlite'
    first, second = db.connect(path), db.connect(path)

    def send(conn):
        try:
            db.record_notification(conn, 'fake-agent', 'Fake result')
            return 'stored'
        except notifications.NotificationLimit:
            return 'limited'

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(send, [first, second])) == ['limited', 'stored']
        assert first.execute('SELECT COUNT(*) FROM messages').fetchone()[0] == 1
    finally:
        first.close()
        second.close()


def test_new_utc_day_still_honors_five_minute_cooldown(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / 'midnight.sqlite')
    now = [86400 * 100 - 1.0]
    monkeypatch.setattr(db.time, 'time', lambda: now[0])
    db.record_notification(conn, 'fake-agent', 'Fake result')
    now[0] += 2
    with pytest.raises(notifications.NotificationLimit) as exc:
        db.record_notification(conn, 'fake-agent', 'Too soon after midnight')
    assert exc.value.retry_after == 298
    conn.close()
