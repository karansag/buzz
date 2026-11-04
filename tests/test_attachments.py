"""Images pasted into the dashboard: upload, serve, and delivery as a file path."""

import os
import sqlite3
import struct
import time
import zlib

from fastapi.testclient import TestClient

from agent_swarm import attachments, server, tmux
from tests.test_server import client  # noqa: F401  (reuse the app fixture)


def png(color: int = 0) -> bytes:
    """A valid 1x1 PNG; `color` varies the bytes so hashes differ."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    raw = b"\x00" + bytes([color, 0, 0])
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def upload(client, data: bytes, content_type: str = "image/png"):
    return client.post("/attachments", content=data, headers={"content-type": content_type})


def register(client, pane="0:0.0"):
    r = client.post("/register", json={"tmux_pane": pane})
    assert r.status_code == 200
    return r.json()["user_id"]


def test_upload_stores_by_content_and_serves_the_image(client):
    r = upload(client, png())
    assert r.status_code == 200
    body = r.json()
    assert body["name"].endswith(".png") and body["url"] == f"/attachments/{body['name']}"
    assert body["path"].endswith(f"/attachments/{body['name']}")

    # The same bytes land on the same name.
    assert upload(client, png()).json()["name"] == body["name"]

    got = client.get(body["url"])
    assert got.status_code == 200
    assert got.headers["content-type"] == "image/png"
    assert got.headers["x-content-type-options"] == "nosniff"
    assert got.content == png()


def test_upload_trusts_bytes_not_the_claimed_type(client):
    # SVG can carry script; it is refused even when labelled as an image.
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    assert upload(client, svg, "image/svg+xml").status_code == 415
    assert upload(client, b"", "image/png").status_code == 415
    # A real PNG is accepted whatever the client calls it.
    assert upload(client, png(), "application/octet-stream").status_code == 200


def test_upload_rejects_oversized_images(client, monkeypatch):
    monkeypatch.setattr(attachments, "MAX_BYTES", 16)
    assert upload(client, png()).status_code == 413


def test_unknown_or_malformed_attachment_names_are_404(client):
    assert client.get("/attachments/" + "0" * 64 + ".png").status_code == 404
    assert client.get("/attachments/..%2Fdb.sqlite").status_code == 404
    assert client.get("/attachments/notahash.png").status_code == 404


def test_owner_message_delivers_image_paths_and_records_them(client):
    user = register(client)
    first = upload(client, png(1)).json()
    second = upload(client, png(2)).json()

    r = client.post("/owner/send", json={
        "recipient": user, "content": "what is wrong here?",
        "attachments": [first["name"], second["name"]],
    })
    assert r.status_code == 200 and r.json()["ok"]

    delivered = client._calls[-1][1]
    assert "what is wrong here?" in delivered
    assert f"[attached image: {first['path']}]" in delivered
    assert f"[attached image: {second['path']}]" in delivered

    msg = client.get("/api/state").json()["messages"][-1]
    assert msg["content"] == "what is wrong here?"
    assert msg["attachments"] == [first["name"], second["name"]]


def test_owner_can_send_an_image_without_text(client):
    user = register(client)
    image = upload(client, png()).json()
    r = client.post("/owner/send", json={"recipient": user, "attachments": [image["name"]]})
    assert r.status_code == 200
    assert client._calls[-1][1].rstrip().endswith(f"[attached image: {image['path']}]")


def test_owner_send_needs_text_or_a_known_image(client):
    user = register(client)
    assert client.post("/owner/send", json={"recipient": user, "content": "  "}).status_code == 422
    r = client.post("/owner/send", json={
        "recipient": user, "content": "hi", "attachments": ["0" * 64 + ".png"],
    })
    assert r.status_code == 400
    assert client._calls == []


def test_messages_without_images_report_an_empty_list(client):
    user = register(client)
    client.post("/owner/send", json={"recipient": user, "content": "plain"})
    assert client.get("/api/state").json()["messages"][-1]["attachments"] == []


DAY = 24 * 60 * 60


def age_file(path, days):
    t = time.time() - days * DAY
    os.utime(path, (t, t))


def age_messages(tmp_path, days):
    conn = sqlite3.connect(tmp_path / "db.sqlite")
    conn.execute("UPDATE messages SET ts = ?", (time.time() - days * DAY,))
    conn.commit()
    conn.close()


def send_image(client, user, color=0):
    image = upload(client, png(color)).json()
    assert client.post(
        "/owner/send", json={"recipient": user, "attachments": [image["name"]]}
    ).status_code == 200
    return image


def test_cleanup_drops_stale_drafts_but_keeps_fresh_ones(client, tmp_path):
    stale = upload(client, png(1)).json()
    fresh = upload(client, png(2)).json()
    age_file(stale["path"], 2)

    assert client.app.state.cleanup()["images"] == [stale["name"]]
    assert client.get(stale["url"]).status_code == 404
    assert client.get(fresh["url"]).status_code == 200


def test_repasting_an_old_upload_restarts_its_grace(client):
    image = upload(client, png()).json()
    age_file(image["path"], 2)
    upload(client, png())
    assert client.app.state.cleanup()["images"] == []


def test_cleanup_keeps_sent_images_within_retention(client, tmp_path):
    user = register(client)
    image = send_image(client, user)
    age_file(image["path"], 10)  # file is old, but a recent message uses it
    age_messages(tmp_path, 10)
    assert client.app.state.cleanup() == {"messages": 0, "images": []}
    assert client.get(image["url"]).status_code == 200


def test_cleanup_expires_images_past_retention_and_the_thread_keeps_the_message(client, tmp_path):
    user = register(client)
    image = send_image(client, user)
    age_file(image["path"], 40)
    age_messages(tmp_path, 40)

    assert client.app.state.cleanup() == {"messages": 0, "images": [image["name"]]}
    msg = client.get("/api/state").json()["messages"][-1]
    assert msg["attachments"] == [image["name"]]  # the dashboard shows it as expired
    assert client.get(image["url"]).status_code == 404


def test_cleanup_deletes_old_messages_and_their_images(client, tmp_path):
    user = register(client)
    image = send_image(client, user)
    age_file(image["path"], 121)
    age_messages(tmp_path, 121)
    client.post("/owner/send", json={"recipient": user, "content": "recent"})

    result = client.app.state.cleanup()
    assert result == {"messages": 1, "images": [image["name"]]}
    assert [m["content"] for m in client.get("/api/state").json()["messages"]] == ["recent"]


def test_retention_settings_of_zero_keep_everything(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_SWARM_ATTACHMENT_RETENTION_DAYS", "0")
    monkeypatch.setenv("AGENT_SWARM_MESSAGE_RETENTION_DAYS", "0")
    monkeypatch.setattr(tmux, "deliver", lambda *a, **k: (True, None))
    monkeypatch.setattr(tmux, "list_panes", lambda: {"0:0.0"})
    monkeypatch.setattr(tmux, "live_agent_panes", lambda: {"0:0.0"})
    monkeypatch.setattr(tmux, "rename_window", lambda *a: (True, None))
    monkeypatch.setattr(tmux, "resolve_pane", lambda t: (t, t) if t == "0:0.0" else None)
    monkeypatch.setattr(tmux, "server_id", lambda: "srv-1")
    monkeypatch.setattr(
        tmux, "pane_table",
        lambda: {"0:0.0": {"label": "0:0.0", "command": "claude", "title": ""}},
    )
    monkeypatch.setattr(tmux, "tag_pane", lambda *a: (True, None))
    c = TestClient(server.create_app(tmp_path / "db.sqlite", monitor=False), client=("127.0.0.1", 50000))
    user = register(c)
    image = send_image(c, user)
    age_file(image["path"], 400)
    age_messages(tmp_path, 400)
    assert c.app.state.cleanup() == {"messages": 0, "images": []}


def test_sweep_leaves_foreign_files_and_clears_interrupted_uploads(tmp_path):
    root = tmp_path / "attachments"
    root.mkdir()
    (root / "notes.txt").write_text("mine")
    part = root / ".abc.png.1.2.part"
    part.write_bytes(b"x")
    age_file(root / "notes.txt", 100)
    age_file(part, 2)
    assert attachments.sweep(root, {}, time.time(), retention=None) == []
    assert (root / "notes.txt").exists() and not part.exists()
