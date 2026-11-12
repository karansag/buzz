"""Conversation search covers full history and keeps owner authorization."""
import pytest

from agent_swarm import db, search
from tests.test_server import client  # noqa: F401
from tests.test_auth import hub, owner, remote, enrol  # noqa: F401


def test_plain_query_is_literal_unicode_casefolded_all_words(tmp_path):
    conn = db.connect(tmp_path / 'search.sqlite')
    wanted = db.record_message(conn, 'fake', 'owner', 'deploy', 'Straße has 50%_ done', 'delivered')
    db.record_message(conn, 'fake', 'owner', None, 'STRASSE only', 'delivered')
    assert [m['id'] for m in db.search_agent_messages(conn, 'fake', 'STRASSE 50%_ deploy')['matches']] == [wanted]
    assert db.search_agent_messages(conn, 'fake', "' OR 1=1 --")['total'] == 0
    assert db.search_agent_messages(conn, 'fake', '50X_')['total'] == 0
    assert db.search_agent_messages(conn, 'fake', '   ') == {'matches': [], 'total': 0, 'terms': []}
    clause, params = search.matches('one TWO one')
    assert clause.count('?') == 2 and params == ['one', 'two']
    conn.close()


def test_endpoint_searches_all_owner_history_not_loaded_pages(client, tmp_path):
    user = client.post('/register', json={'tmux_pane': '0:0.0'}).json()['user_id']
    # Use the fixture's isolated SQLite DB, not a real hub or pane.
    conn = db.connect(tmp_path / "db.sqlite")
    old = db.record_message(conn, user, 'owner', None, 'Rare NEEDLE near the start', 'delivered')
    for i in range(605):
        db.record_message(conn, user, 'owner', None, f'ordinary newer message {i}', 'delivered')
    newer = db.record_message(conn, 'owner', user, None, 'needle is here too', 'delivered')
    db.record_message(conn, user, 'someone-else', None, 'needle peer chat', 'delivered')
    db.record_message(conn, 'someone-else', user, None, 'needle inbound peer', 'delivered')
    db.record_message(conn, 'someone-else', 'owner', None, 'needle another owner conversation', 'delivered')
    conn.close()
    initial = client.get(f'/api/agents/{user}/messages').json()['messages']
    assert old not in [m['id'] for m in initial]
    result = client.get(f'/api/agents/{user}/messages/search', params={'q': 'Needle', 'limit': 1}).json()
    assert result['total'] == 2
    assert result['matches'][0]['id'] == newer
    assert set(result['matches'][0]) == {'id', 'ts', 'sender', 'snippet'}
    second = client.get(f'/api/agents/{user}/messages/search', params={'q': 'needle', 'limit': 1, 'offset': 1}).json()
    assert second['matches'][0]['id'] == old
    assert 'NEEDLE' in second['matches'][0]['snippet']
    assert client.get(f'/api/agents/{user}/messages/search', params={'q': 'never exists'}).json()['total'] == 0
    assert client.get(f'/api/agents/{user}/messages/search', params={'q': 'needle rare'}).json()['total'] == 1
    assert client.get(f'/api/agents/{user}/messages/search').json() == {'matches': [], 'total': 0, 'terms': []}
    for params in [{'limit': 0}, {'limit': 501}, {'offset': -1}, {'q': 'a' * 1001}]:
        assert client.get(f'/api/agents/{user}/messages/search', params=params).status_code == 422


def test_search_endpoint_is_owner_only(hub):
    path = '/api/agents/fake/messages/search?q=example'
    assert remote(hub).get(path).status_code == 401
    assert remote(hub, enrol(hub, 'test-node')).get(path).status_code == 403
    assert owner(hub).get(path).status_code == 200
