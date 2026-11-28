"""Task attachments persist, survive cleanup, and accompany assignments."""
import hashlib
import os
import time

from agent_swarm import node
from tests.test_attachments import png, register, upload


def test_task_keeps_images_and_files_and_delivers_both(client):
    user = register(client)
    image = upload(client, png()).json()
    file = client.post('/attachments', content=b'context and instructions', headers={
        'x-attachment-filename': 'notes.md', 'content-type': 'text/plain',
    }).json()
    result = client.post('/tasks', json={'title': 'Check this', 'assignee': user,
        'attachments': [image['name'], file['name']]} )
    assert result.status_code == 200
    task = result.json()['task']
    assert task['attachments'] == [image['name'], file['name']]
    assert '[attached image: ' + image['path'] + ']' in client._calls[-1][1]
    assert '[attached file: ' + file['path'] + ']' in client._calls[-1][1]
    assert client.get('/tasks').json()['tasks'][0]['attachments'] == task['attachments']
    assert client.get('/api/state').json()['tasks'][0]['attachments'] == task['attachments']
    assert client.get('/api/state').json()['messages'][-1]['attachments'] == task['attachments']


def test_unassigned_and_completed_tasks_keep_files_through_cleanup(client):
    file = upload(client, png()).json()
    task = client.post('/tasks', json={'title': 'Later', 'attachments': [file['name']]}).json()['task']
    old = time.time() - 400 * 86400
    os.utime(file['path'], (old, old))
    assert file['name'] not in client.app.state.cleanup()['images']
    client.patch('/tasks/' + str(task['id']), json={'status': 'done', 'note': 'checked'})
    assert file['name'] not in client.app.state.cleanup()['images']
    assert client.get(file['url']).status_code == 200


def test_bad_files_or_dependencies_do_not_leave_partial_tasks(client):
    for body in [ {'attachments': ['0' * 64 + '.png']}, {'depends_on': [999]}, {'attachments': ['x'] * 11} ]:
        result = client.post('/tasks', json={'title': 'Bad', **body})
        assert result.status_code in (400, 422)
        assert client.get('/tasks').json()['tasks'] == []
    assert client._calls == []


def test_assignment_after_creation_includes_files(client):
    file = upload(client, png()).json()
    task = client.post('/tasks', json={'title': 'Later', 'attachments': [file['name']]}).json()['task']
    user = register(client)
    client.patch('/tasks/' + str(task['id']), json={'assignee': user})
    assert file['path'] in client._calls[-1][1]


def test_named_active_content_is_a_forced_download(client):
    content = b'<html><script>alert(1)</script></html>'
    result = client.post('/attachments', content=content, headers={'x-attachment-filename': '../../demo.html'})
    assert result.status_code == 200
    data = result.json()
    assert data['name'].endswith('.file.demo.html')
    response = client.get(data['url'])
    assert response.content == content
    assert response.headers['content-type'] == 'application/octet-stream'
    assert response.headers['content-disposition'] == 'attachment; filename="demo.html"'
    assert response.headers['x-content-type-options'] == 'nosniff'


def test_remote_cache_fetches_generic_files_and_checks_the_hash(tmp_path, monkeypatch):
    content = b'notes for a remote task'
    name = hashlib.sha256(content).hexdigest() + '.file.notes.txt'
    class Response:
        is_success = True
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def iter_bytes(self): yield content
    monkeypatch.setattr(node.httpx, 'stream', lambda *a, **k: Response())
    cache = node.AttachmentCache(tmp_path / 'cache', 'http://hub', None)
    assert cache.path_for(name).read_bytes() == content
    import pytest
    with pytest.raises(ValueError, match='content does not match'):
        cache.path_for('0' * 64 + '.file.notes.txt')
