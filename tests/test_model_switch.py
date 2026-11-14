"""Switching an agent's model through its harness's own /model UI."""
import json

import pytest

from agent_swarm import model_switch as ms
from agent_swarm import nodes, tmux
from tests.test_server import client  # noqa: F401  (reuse the app fixture)

CLAUDE_ROWS = ["Default (recommended)", "Opus 5.5", "Fable 5.2", "Sonnet 5.5", "Haiku 5.5"]
CODEX_ROWS = ["GPT-6.1-Sol", "GPT-6-Astra", "GPT-6.1 Terra", "GPT-6-Luna"]


@pytest.fixture(autouse=True)
def codex_cache(tmp_path, monkeypatch):
    home = tmp_path / "codex-home"
    home.mkdir()
    models = [{"slug": n.lower().replace(" ", "-"), "display_name": n, "visibility": "list"}
              for n in CODEX_ROWS]
    (home / "models_cache.json").write_text(json.dumps({"models": models}))
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(ms, "_codex_names", None)


# --- reading the model off the screen -------------------------------------

def test_claude_model_comes_from_status_line_or_banner():
    status = "❯ \n──────\n  /home/karan/x  [Sonnet 5.5 | wk:95%]\n  ⏵⏵ auto mode on\n"
    assert ms.screen_model("claude", status) == "claude-sonnet-5-5"
    banner = " ▐▛███▛█   Claude Code v2.1.325\n▝▜██████▀  Fable 5.2 · Claude Ultra\n❯ \n"
    assert ms.screen_model("claude", banner) == "claude-fable-5-2"


def test_conversation_text_does_not_relabel_an_agent():
    talk = "● I could switch to [Opus 5.5 later, or GPT-6-Luna medium · fine\n" + "x\n" * 10 + "❯ \n"
    assert ms.screen_model("claude", talk) is None
    assert ms.screen_model("codex", talk) is None


def test_codex_model_comes_from_its_status_line():
    screen = ("› Ask Codex to do anything\n"
              "  GPT-6.1 Terra high · ~/agent-swarm · Context 0% used · weekly 0% left\n"
              "  ← for agents · ? for shortcuts\n")
    assert ms.screen_model("codex", screen) == "gpt-6.1-terra"


def test_pi_model_comes_from_its_footer():
    reasoning = "~/agents (master)\n0.0%/1.0M (auto)          (openrouter) deepseek/deepseek-v4.1-flash • high\n"
    assert ms.screen_model("pi", reasoning) == "openrouter/deepseek/deepseek-v4.1-flash"
    local = "0.0%/131k (auto)     (local-llama) /mnt/storage/ai/models/b.gguf\n"
    assert ms.screen_model("pi", local) == "local-llama//mnt/storage/ai/models/b.gguf"


def test_pi_in_a_narrow_pane_is_resolved_against_the_shortlist(tmp_path, monkeypatch):
    home = tmp_path / "pi"
    home.mkdir()
    (home / "settings.json").write_text(json.dumps({"enabledModels": [
        "openrouter/thinkingmachines/inkling-2-small:free",
        "local-llama//mnt/storage/ai/models/bonsai/Ternary-Bonsai-2-27B-PQ2_0.gguf",
        "local-llama//mnt/storage/ai/models/bonsai/Ternary-Bonsai-2-27B-PQ4.gguf",
    ]}))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(home))
    no_provider = "~/oa (main)\n↑5.5M ↓389k $10.718 36.9%/1.0M (auto)      thinkingmachines/inkling-2-small:free • high\n"
    assert ms.screen_model("pi", no_provider) == "openrouter/thinkingmachines/inkling-2-small:free"
    cut = "~/agents$\n↑16k 7.1%/131k (auto)  /mnt/storage/ai/models/bonsai/Ternary-Bonsai-2-27B-PQ2_0.gg\n"
    assert ms.screen_model("pi", cut) == "local-llama//mnt/storage/ai/models/bonsai/Ternary-Bonsai-2-27B-PQ2_0.gguf"
    # Cut so short that two entries fit: no guess.
    ambiguous = "~/agents$\n↑16k 7.1%/131k (auto)  /mnt/storage/ai/models/bonsai/Ternary-Bonsai-2-27B-PQ\n"
    assert ms.screen_model("pi", ambiguous) is None
    unknown = "~/agents$\n7.1%/131k (auto)  someone/else\n"
    assert ms.screen_model("pi", unknown) is None


def test_unknown_harness_or_empty_screen_reads_nothing():
    assert ms.screen_model("hermes", "[Opus 5.5]") is None
    assert ms.screen_model("claude", None) is None


def test_picker_rows_skip_marks_and_find_the_cursor():
    screen = ("1. an old numbered list in the conversation\n"
              "   Select model\n   Switch between Claude models.\n"
              "     1.  Default (recommended)  Opus 5.5 · Best for everyday\n"
              "   ❯ 2.  Sonnet 5.5 ✔           Most efficient\n"
              "     ▸   More models\n")
    rows = ms.picker_rows(screen, "Select model")
    assert [(r.number, r.label, r.cursor) for r in rows] == [(1, "Default", False), (2, "Sonnet 5.5", True)]
    assert ms.picker_rows(screen, "Select Model and Effort") is None


@pytest.mark.parametrize("wanted,label,hit", [
    ("sonnet", "Sonnet 5.5", True),
    ("claude-sonnet-5-5", "Sonnet 5.5", True),
    ("claude-sonnet-5-4", "Sonnet 5.5", False),
    ("default", "Default", True),
    ("opus", "Default", False),
])
def test_claude_rows_match_aliases_and_ids(wanted, label, hit):
    assert ms.row_matches("claude", wanted, label) is hit


def test_codex_rows_match_slugs_exactly():
    assert ms.row_matches("codex", "gpt-6.1-terra", "GPT-6.1 Terra")
    assert not ms.row_matches("codex", "gpt-6-sol", "GPT-6.1-Sol")


# --- driving a fake harness -------------------------------------------------

class FakeHarness:
    """A pane that answers /model the way the real harness does."""

    def __init__(self, flavor, model, open_picker=True, effort="medium"):
        self.flavor, self.model, self.open_picker, self.effort = flavor, model, open_picker, effort
        self.screen_name = "prompt"
        self.cursor = 0
        self.keys, self.typed = [], []
        self.saved_default = False

    # The Node calls model_switch makes.
    def capture(self, pane, tmux_server, colors=False):
        return self.render(), None

    def deliver(self, op_id, pane, tmux_server, text, **kw):
        self.typed.append((text, kw.get("retry_submit")))
        if self.flavor == "pi" and text.startswith("/model "):
            self.model = text.split(" ", 1)[1]
        elif text == "/model" and self.open_picker:
            self.screen_name = "models"
            self.cursor = self.rows().index(self.current_row())
        return nodes.Result("ok")

    def send_key(self, op_id, pane, tmux_server, key):
        self.keys.append(key)
        rows = self.rows()
        if key == "Down":
            self.cursor = min(self.cursor + 1, len(rows) - 1)
        elif key == "Up":
            self.cursor = max(self.cursor - 1, 0)
        elif key == "Escape":
            self.screen_name = "prompt"
        elif self.flavor == "claude" and self.screen_name == "models" and key in ("s", "Enter"):
            self.model = rows[self.cursor]
            self.saved_default = key == "Enter"
            self.screen_name = "prompt"
        elif self.flavor == "codex" and self.screen_name == "models" and key == "Enter":
            self.picked = rows[self.cursor]
            self.screen_name = "effort"
            self.cursor = 1
        elif self.flavor == "codex" and self.screen_name == "effort" and key in ("s", "Enter"):
            self.model = self.picked
            self.effort = rows[self.cursor].split(" ")[0].lower()
            self.saved_default = key == "Enter"
            self.screen_name = "prompt"
        return nodes.Result("ok")

    def rows(self):
        if self.screen_name == "effort":
            return ["Low", "Medium (default)", "High"]
        return CLAUDE_ROWS if self.flavor == "claude" else CODEX_ROWS

    def current_row(self):
        return next(r for r in self.rows() if r.startswith(self.model))

    def render(self):
        if self.flavor == "pi":
            provider, model = self.model.split("/", 1)
            return f"~/x\n0.0%/1.0M (auto)      ({provider}) {model} • high\n"
        lines = ["some conversation"]
        titles = {"claude": "Select model", "codex": "Select Model and Effort"}
        if self.screen_name in ("models", "effort"):
            lines.append("  " + (titles[self.flavor] if self.screen_name == "models" else ms.CODEX_EFFORT_TITLE))
            mark = "❯" if self.flavor == "claude" else "›"
            for i, row in enumerate(self.rows()):
                lines.append(f"  {mark if i == self.cursor else ' '} {i + 1}. {row}   description")
            lines.append("  enter select · esc back")
        elif self.flavor == "claude":
            lines += ["❯ ", f"  /home/x  [{self.model} | wk:95%]"]
        else:
            lines += ["› Ask Codex", f"  {self.model} {self.effort} · ~/x · Context 0% used"]
        return "\n".join(lines) + "\n"


def _pane(fake):
    return ms.Pane(fake, "%9", None, "Enter", fake.flavor)


def no_sleep(_):
    pass


def test_claude_switch_moves_the_cursor_and_applies_for_this_session_only():
    fake = FakeHarness("claude", "Sonnet 5.5")
    assert ms.switch(_pane(fake), "opus", sleep=no_sleep) == "claude-opus-5-5"
    assert fake.typed == [("/model", False)]
    assert fake.keys == ["Up", "Up", "s"]
    assert not fake.saved_default


def test_codex_switch_keeps_the_agents_reasoning_level_for_this_session_only():
    fake = FakeHarness("codex", "GPT-6.1-Sol", effort="high")
    assert ms.switch(_pane(fake), "gpt-6-luna", sleep=no_sleep) == "gpt-6-luna"
    # The level screen opens on the model's default (Medium); High is kept.
    assert fake.keys == ["Down", "Down", "Down", "Enter", "Down", "s"]
    assert (fake.effort, fake.saved_default) == ("high", False)


def test_codex_takes_the_models_default_level_when_the_old_one_is_not_offered():
    fake = FakeHarness("codex", "GPT-6.1-Sol", effort="ultra")
    assert ms.switch(_pane(fake), "gpt-6-astra", sleep=no_sleep) == "gpt-6-astra"
    assert fake.keys == ["Down", "Enter", "s"]
    assert fake.effort == "medium"


def test_pi_switch_types_the_model_and_retries_the_submit():
    fake = FakeHarness("pi", "openrouter/meta/muse")
    assert ms.switch(_pane(fake), "openrouter/deepseek/flash", sleep=no_sleep) == "openrouter/deepseek/flash"
    assert fake.typed == [("/model openrouter/deepseek/flash", True)]
    assert fake.keys == []


def test_a_model_missing_from_the_picker_closes_it_and_says_what_is_there():
    fake = FakeHarness("claude", "Sonnet 5.5")
    with pytest.raises(ms.SwitchFailed, match="nonsense is not in the picker .*Opus 5.5"):
        ms.switch(_pane(fake), "nonsense", sleep=no_sleep)
    assert fake.keys == ["Escape"] and fake.model == "Sonnet 5.5"


def test_no_picker_means_no_escape(monkeypatch):
    # Escape would interrupt a working agent; only an open picker gets one.
    monkeypatch.setattr(ms, "STEP_TIMEOUT", 0.0)
    fake = FakeHarness("claude", "Sonnet 5.5", open_picker=False)
    with pytest.raises(ms.SwitchFailed, match="Select model.* picker") as failed:
        ms.switch(_pane(fake), "opus", sleep=no_sleep)
    assert fake.keys == []
    assert "Sonnet 5.5" in failed.value.screen


# --- the endpoint ---------------------------------------------------------

@pytest.fixture()
def switched(monkeypatch):
    calls = []

    def fake_switch(pane, wanted, sleep=None):
        calls.append((pane.pane, pane.flavor, wanted))
        return f"seen-{wanted}"

    monkeypatch.setattr(ms, "switch", fake_switch)
    return calls


def _team_of_two(client):
    queen = client.post("/register", json={"tmux_pane": "0:0.0", "flavor": "claude"}).json()["user_id"]
    worker = client.post("/register", json={"tmux_pane": "0:1.0", "flavor": "codex"}).json()["user_id"]
    team = client.post("/teams", json={"name": "hive"}).json()["team"]
    for user in (queen, worker):
        client.post(f"/agents/{user}/team", json={"team_id": team["id"]})
    client.patch(f"/teams/{team['id']}", json={"queen": queen})
    return queen, worker


def test_owner_switches_an_agent_and_the_label_follows(client, switched):
    _, worker = _team_of_two(client)
    r = client.post(f"/agents/{worker}/switch-model", json={"model": "gpt-6-luna"})
    assert r.status_code == 200, r.text
    assert switched == [("0:1.0", "codex", "gpt-6-luna")]
    assert r.json()["model"] == "seen-gpt-6-luna"
    worker_row = next(x for x in client.get("/recipients").json()["recipients"] if x["user_id"] == worker)
    assert worker_row["model"] == "seen-gpt-6-luna"


def test_a_queen_switches_her_team_but_nobody_else_can(client, switched):
    queen, worker = _team_of_two(client)
    as_queen = {"model": "gpt-6-luna", "tmux_pane": "0:0.0", "pane_verified": True}
    assert client.post(f"/agents/{worker}/switch-model", json=as_queen).status_code == 200
    as_worker = {"model": "opus", "tmux_pane": "0:1.0", "pane_verified": True}
    assert client.post(f"/agents/{queen}/switch-model", json=as_worker).status_code == 403
    # A queen switching herself would type into her own turn.
    assert client.post(f"/agents/{queen}/switch-model", json={**as_queen, "model": "opus"}).status_code == 403
    assert switched == [("0:1.0", "codex", "gpt-6-luna")]


def test_switch_refuses_unsupported_harnesses_dead_panes_and_reports_failures(client, monkeypatch):
    hermes = client.post("/register", json={"tmux_pane": "0:0.0", "flavor": "hermes"}).json()["user_id"]
    assert client.post(f"/agents/{hermes}/switch-model", json={"model": "x"}).status_code == 422
    shell = client.post("/register", json={"tmux_pane": "0:2.0", "flavor": "claude"}).json()["user_id"]
    assert client.post(f"/agents/{shell}/switch-model", json={"model": "opus"}).status_code == 409
    assert client.post("/agents/ghost/switch-model", json={"model": "opus"}).status_code == 404

    def broken(pane, wanted, sleep=None):
        raise ms.SwitchFailed("timed out waiting for the /model picker", "line 1\nline 2")

    monkeypatch.setattr(ms, "switch", broken)
    claude = client.post("/register", json={"tmux_pane": "0:1.0", "flavor": "claude"}).json()["user_id"]
    r = client.post(f"/agents/{claude}/switch-model", json={"model": "opus"})
    assert r.status_code == 502
    assert r.json()["detail"] == {"error": "timed out waiting for the /model picker", "screen": "line 1\nline 2"}


def test_monitor_keeps_the_label_in_step_with_the_screen(client, monkeypatch):
    user = client.post("/register", json={"tmux_pane": "0:1.0", "flavor": "claude", "model": "claude-opus-5-5"}).json()["user_id"]
    monkeypatch.setattr(tmux, "capture_pane", lambda pane, colors=False: ("❯ \n  /x  [Haiku 5.5 | wk:1%]\n", None))
    import asyncio
    asyncio.run(client.app.state.monitor_tick())
    row = next(x for x in client.get("/recipients").json()["recipients"] if x["user_id"] == user)
    assert row["model"] == "claude-haiku-5-5"
