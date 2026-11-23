"""`buzz switch a b c --to <harness>`: several agents in one call."""

from __future__ import annotations

import json
from types import SimpleNamespace

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


@pytest.fixture()
def hub(monkeypatch):
    """Recipients on the hub, and a record of what the switch posted."""
    recipients = [
        {"user_id": "otter", "team_id": 7, "flavor": "claude"},
        {"user_id": "stoat", "team_id": 7, "flavor": "claude"},
        {"user_id": "marten", "team_id": 7, "flavor": "codex"},
        {"user_id": "loner", "team_id": None, "flavor": "claude"},
    ]
    posts: list[tuple[str, dict]] = []
    failing: set[str] = set()

    monkeypatch.setattr(client.httpx, "get",
                        lambda url, **kw: _response(200, {"recipients": recipients}))
    monkeypatch.setattr(client, "caller", lambda *a, **k: {"pane": "%1"})
    monkeypatch.setattr(client, "whoami_lookup", lambda who: {"user_id": "otter"})

    def post(url, json=None, **_kw):
        handle = url.rsplit("/", 2)[-2]
        posts.append((handle, json))
        if handle in failing:
            return _response(409, {"detail": {"error": "otter is not running"}})
        return _response(200, {"ok": True, "applied": json.get("dry_run") is False,
                               "plan": {"handle": handle, "to": json["to"], "route": "native",
                                        "session_id": f"session-{handle}", "turns": 3, "chars": 900}})

    monkeypatch.setattr(client.httpx, "post", post)
    return SimpleNamespace(posts=posts, failing=failing)


def run(*handles, to="codex", apply=False, team=False) -> int:
    return client.main(["switch", *handles, "--to", to]
                       + (["--apply"] if apply else []) + (["--team"] if team else []))


def test_several_handles_switch_one_after_another(hub, capsys):
    assert run("stoat", "marten", to="codex", apply=True) == 0
    assert [h for h, _ in hub.posts] == ["stoat", "marten"]
    assert all(p["to"] == "codex" and p["dry_run"] is False for _, p in hub.posts)
    out = capsys.readouterr()
    assert "stoat: now codex (session session-stoat)" in out.out
    assert "marten: now codex (session session-marten)" in out.out


def test_one_line_per_agent_names_the_session(hub, capsys):
    assert run("stoat", apply=True) == 0
    assert capsys.readouterr().out.strip() == "stoat: now codex (session session-stoat)"


def test_a_dry_run_keeps_printing_the_plan(hub, capsys):
    assert run("stoat", "marten") == 0
    assert [h for h, _ in hub.posts] == ["stoat", "marten"]
    assert all(p["dry_run"] is True for _, p in hub.posts)
    out = capsys.readouterr().out
    assert out.count('"plan"') == 2 and '"applied": false' in out


def test_an_unknown_handle_switches_nothing(hub, capsys):
    assert run("stoat", "nobody", apply=True) == 2
    assert hub.posts == []
    assert "unknown agent(s): nobody" in capsys.readouterr().err


def test_a_failure_does_not_stop_the_rest_and_exits_one(hub, capsys):
    hub.failing.add("stoat")
    assert run("stoat", "marten", apply=True) == 1
    assert [h for h, _ in hub.posts] == ["stoat", "marten"]
    err = capsys.readouterr().err
    assert "stoat: failed: otter is not running" in err


def test_team_switches_the_members_but_not_the_caller(hub, capsys):
    assert run(team=True, apply=False) == 0
    # otter is the caller, so it is not part of --team; loner is on no team.
    assert [h for h, _ in hub.posts] == ["stoat", "marten"]


def test_team_and_handles_add_up(hub):
    assert run("loner", team=True, apply=False) == 0
    assert [h for h, _ in hub.posts] == ["loner", "stoat", "marten"]


def test_the_caller_is_switched_last(hub, capsys):
    assert run("marten", "otter", "stoat", apply=True) == 0
    assert [h for h, _ in hub.posts] == ["marten", "stoat", "otter"]
    err = capsys.readouterr().err
    assert "otter: switching last" in err


def test_the_model_and_budget_reach_every_agent(hub):
    assert client.main(["switch", "stoat", "marten", "--to", "codex",
                        "--model", "gpt-6.1-sol", "--max-chars", "5000", "--force"]) == 0
    assert {(p["model"], p["max_chars"], p["force"]) for _, p in hub.posts} == {
        ("gpt-6.1-sol", 5000, True),
    }