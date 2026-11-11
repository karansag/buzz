"""Extra dashboard tabs: pages named in AGENT_SWARM_TABS, served under /tabs/<name>/."""

import http.server
import json
import threading

import pytest
from fastapi.testclient import TestClient

from agent_swarm import server


@pytest.fixture()
def upstream():
    """A stand-in for a page like the usage page; it echoes what it was asked."""
    seen = []

    class Page(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}})
            if self.path == "/moved":
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/there")
                self.end_headers()
                return
            body = json.dumps({"path": self.path}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Secret", "upstream-only")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", seen
    httpd.shutdown()


@pytest.fixture()
def hub(tmp_path):
    return TestClient(server.create_app(tmp_path / "db.sqlite", monitor=False), client=("127.0.0.1", 40000))


def test_state_lists_tab_names_and_skips_bad_entries(hub, monkeypatch):
    assert hub.get("/api/state").json()["tabs"] == []
    monkeypatch.setenv(
        "AGENT_SWARM_TABS",
        " Usage = https://box.example:8447/ , bad name=https://x, ftp=ftp://x,"
        " usage=https://dup, grafana=http://127.0.0.1:3000/d/abc,,",
    )
    # Names only: the page urls stay on the hub.
    assert hub.get("/api/state").json()["tabs"] == ["usage", "grafana"]


def test_a_tab_serves_its_page_paths_and_queries(hub, upstream, monkeypatch):
    url, seen = upstream
    monkeypatch.setenv("AGENT_SWARM_TABS", f"usage={url}/")
    r = hub.get("/tabs/usage/", headers={"Tailscale-User-Login": "me@example.com", "Accept": "text/html"})
    assert r.status_code == 200 and r.json() == {"path": "/"}
    assert r.headers["content-type"] == "application/json"
    assert "x-secret" not in r.headers
    # The caller's identity never reaches the page.
    assert "tailscale-user-login" not in seen[-1]["headers"] and seen[-1]["headers"]["accept"] == "text/html"
    assert hub.get("/tabs/usage/api/usage?fresh=1").json() == {"path": "/api/usage?fresh=1"}
    r = hub.get("/tabs/usage/moved", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/tabs/usage/there"


def test_a_tab_without_the_slash_redirects_so_relative_links_work(hub, upstream, monkeypatch):
    monkeypatch.setenv("AGENT_SWARM_TABS", f"usage={upstream[0]}")
    r = hub.get("/tabs/usage", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/tabs/usage/"


def test_unknown_and_unreachable_tabs(hub, monkeypatch):
    assert hub.get("/tabs/usage/").status_code == 404
    monkeypatch.setenv("AGENT_SWARM_TABS", "usage=http://127.0.0.1:9")
    r = hub.get("/tabs/usage/")
    assert r.status_code == 502 and "usage is unreachable" in r.text


def test_multiple_tabs_keep_their_configured_base_paths(hub, upstream, monkeypatch):
    url, seen = upstream
    monkeypatch.setenv("AGENT_SWARM_TABS", f"usage={url}/metrics,prs={url}/dashboard")
    assert hub.get("/api/state").json()["tabs"] == ["usage", "prs"]
    assert hub.get("/tabs/usage/api/usage").json()["path"] == "/metrics/api/usage"
    assert hub.get("/tabs/prs/api/prs?repo=a%2Fb").json()["path"] == "/dashboard/api/prs?repo=a%2Fb"
    assert [r["path"] for r in seen] == ["/metrics/api/usage", "/dashboard/api/prs?repo=a%2Fb"]


def test_tab_pages_require_owner_access(hub, upstream, monkeypatch):
    monkeypatch.setenv("AGENT_SWARM_TABS", f"prs={upstream[0]}")
    with TestClient(hub.app, client=("100.64.0.9", 40001)) as remote:
        assert remote.get("/tabs/prs/").status_code == 401
    assert upstream[1] == []
