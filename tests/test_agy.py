"""The Antigravity CLI (`agy`) as a Buzz harness.

Screens and transcript records are trimmed copies of what agy 1.5.11 drew
and wrote in a scratch session.
"""

from __future__ import annotations

import json

import pytest

from agent_swarm import activity, client, handoff, nodes, restore, tmux
from agent_swarm import model_switch as ms

CATALOG = (
    "gemini-4-neon-high\tGemini 4 Neon (High)\n"
    "gemini-4-carbon-medium\tGemini 4 Carbon (Medium)\n"
    "gemini-4-carbon-high\tGemini 4 Carbon (High)\n"
    "gemini-4-argon-medium\tGemini 4 Argon (Medium)\n"
    "gemini-4-argon-high\tGemini 4 Argon (High)\n"
    "claude-opus-5-5-high\tClaude Opus 5.5 (High)\n"
)

RULE = "─" * 60


def footer(model="Gemini 4 Neon · high", busy=False):
    hint = "esc to cancel" if busy else "? for shortcuts"
    return f"{RULE}\n>\n{RULE}\n{hint}{' ' * 40}{model}\n"


@pytest.fixture()
def catalog(monkeypatch):
    monkeypatch.setattr(tmux, "_agy_models_output", lambda: CATALOG)


# --- finding agy and its session -------------------------------------------

def _tree(monkeypatch, *chain, pane_pid=100):
    monkeypatch.setattr(tmux, "ancestors", lambda pid=None: [(9, "python agent-swarm"), (8, "/bin/bash -c x"), *chain])
    monkeypatch.setattr(tmux, "pane_process", lambda pane: pane_pid)


def test_agy_in_its_pane_is_its_own_and_one_shot_runs_are_not(monkeypatch):
    # agy runs the agent's shell commands as its own children.
    assert client.harness_of("/home/k/.local/bin/agy --dangerously-skip-permissions") == "agy"
    _tree(monkeypatch, (7, "agy --dangerously-skip-permissions"), (100, "-bash"))
    assert client.own_pane_harness("%5") == ("agy", "")
    for command in ("agy --conversation 81ff1259 --model gemini-4-argon-medium",
                    "agy -i 'read the handoff'"):
        _tree(monkeypatch, (7, command), (100, "bash"))
        assert client.own_pane_harness("%5") == ("agy", ""), command
    for command in ("agy -p hello", "agy --print hello", "agy --prompt=hi", "agy models", "agy acp"):
        _tree(monkeypatch, (7, command), (100, "bash"))
        harness, why = client.own_pane_harness("%5")
        assert harness is None and "not an interactive" in why, command


def test_agy_session_is_its_conversation_id(monkeypatch):
    # agy also sets ANTIGRAVITY_TRAJECTORY_ID, a different id that resumes nothing.
    monkeypatch.setenv("ANTIGRAVITY_TRAJECTORY_ID", "e42c1ada-ed08-400f-a58c-15af6e5009c6")
    monkeypatch.setenv("ANTIGRAVITY_CONVERSATION_ID", "81ff1259-b2c0-4306-ab8f-b31ccc6e8d9b")
    assert client.harness_session() == ("agy", "81ff1259-b2c0-4306-ab8f-b31ccc6e8d9b")


# --- launching and resuming --------------------------------------------------

def test_spawn_skips_permission_prompts_and_takes_a_listed_model(catalog):
    assert tmux.spawn_launch_command("agy") == "agy --dangerously-skip-permissions"
    assert tmux.spawn_launch_command("agy", "gemini-4-argon-medium") == (
        "agy --model gemini-4-argon-medium --dangerously-skip-permissions")
    assert tmux.spawn_launch_command("agy", "gemini-9-nope") == "agy --dangerously-skip-permissions"
    assert tmux.submit_key_for_flavor("agy") == "Enter"
    assert tmux.compact_command_for_flavor("agy") == "/compact"


def test_models_come_from_agy_and_fall_back_when_it_cannot_answer(monkeypatch, catalog):
    assert tmux.agy_models()[:2] == ["gemini-4-neon-high", "gemini-4-carbon-medium"]
    monkeypatch.setattr(tmux, "_agy_models", None)
    monkeypatch.setattr(tmux, "_agy_models_output", lambda: "Error: Please sign in to view available models.\n")
    assert tmux.agy_models() == tmux.AGY_FALLBACK_MODELS


def test_resume_takes_the_conversation_and_a_session_only_model():
    command = restore.resume_command({"flavor": "agy", "agent_id": "81ff1259", "model": "gemini-4-argon-medium"})
    assert command == "agy --conversation 81ff1259 --model gemini-4-argon-medium --dangerously-skip-permissions"


# --- reading the screen ------------------------------------------------------

TRUST = """Accessing workspace:
/home/k/proj
Do you trust the contents of this project?
Antigravity CLI requires permission to read, edit, and execute files here.
> Yes, I trust this folder
  No, exit
  ↑/↓ Navigate · enter Confirm
"""

APPROVAL = """● Running (env | grep agy) (ctrl+o to expand)
Command
────────────────────────────────
Requesting permission for:
   env | grep agy
Run this command?
> 1. Yes
  2. Yes, and always allow in this conversation for commands that start with 'env | grep agy'
  3. Yes, and always allow for commands that start with 'env | grep agy' (Persist to settings.json)
  4. No, cancel
  ↑/↓ Navigate · tab Amend · ctrl+g edit/expand command
esc to cancel                                                       Gemini 4 Neon · high
"""


def test_trust_and_approval_prompts_need_the_owner_and_idle_does_not():
    # Its trust screen also says "Accessing workspace:", Claude's heading.
    assert activity.trust_prompt(TRUST) == "Antigravity's workspace trust prompt"
    assert activity._attention_detail("agy", APPROVAL) == "env | grep agy"
    assert activity._attention_detail("agy", "> Reply with PONG.\n  PONG\n" + footer()) is None


def test_footer_names_the_model_by_agy_id(catalog):
    assert ms.screen_model("agy", "  PONG\n" + footer("Gemini 4 Argon · medium")) == "gemini-4-argon-medium"
    assert ms.screen_model("agy", footer("Claude Opus 5.5 · high", busy=True)) == "claude-opus-5-5-high"
    # Words in the conversation are not the footer.
    assert ms.screen_model("agy", "Gemini 4 Argon · medium\n" + "\n" * 2) is None


def test_a_family_alias_keeps_the_effort_when_it_can(catalog):
    assert ms.agy_model("argon", "gemini-4-carbon-high") == "gemini-4-argon-high"
    assert ms.agy_model("argon", "gemini-4-neon-xhigh") == "gemini-4-argon-medium"
    assert ms.agy_model("Gemini 4 Carbon (High)", None) == "gemini-4-carbon-high"
    assert ms.agy_model("hydrogen", None) is None
    assert ms.same_model("agy", "argon", "gemini-4-argon-high")
    assert not ms.same_model("agy", "argon", "gemini-4-carbon-high")


# --- switching models ----------------------------------------------------------

class FakeAgy:
    """A pane running agy, then a shell after /quit, then agy again."""

    def __init__(self, model="Gemini 4 Neon · high", busy=False):
        self.model, self.busy, self.running = model, busy, True
        self.typed = []

    def capture(self, pane, tmux_server, colors=False):
        if self.running:
            return "  PONG\n" + footer(self.model, self.busy), None
        return "karan@host:~/proj$ \n", None

    def snapshot(self):
        live = frozenset({"%9"}) if self.running else frozenset()
        return nodes.PaneSnapshot(None, None, frozenset({"%9"}), live, {})

    def deliver(self, op_id, pane, tmux_server, text, **kw):
        self.typed.append(text)
        if text == "/quit":
            self.running = False
        elif text.startswith("agy --conversation"):
            words = text.split()
            label = dict(line.split("\t")[::-1] for line in CATALOG.splitlines())
            name = {v: k for k, v in label.items()}[words[words.index("--model") + 1]]
            family, effort = name[:-1].split(" (")
            self.model, self.running = f"{family} · {effort.lower()}", True
        return nodes.Result("ok")

    def send_key(self, op_id, pane, tmux_server, key, literal=False):
        raise AssertionError(f"agy's switch presses no keys, got {key}")


def _pane(fake, session="81ff1259"):
    return ms.Pane(fake, "%9", None, "Enter", "agy", session=session)


def test_switch_restarts_an_idle_agent_into_its_conversation(catalog):
    fake = FakeAgy()  # on Neon, high effort: Argon keeps it
    assert ms.switch(_pane(fake), "argon", sleep=lambda _: None) == "gemini-4-argon-high"
    assert fake.typed == [
        "/quit",
        "agy --conversation 81ff1259 --model gemini-4-argon-high --dangerously-skip-permissions",
    ]


def test_switch_leaves_a_busy_or_unresumable_agent_alone(catalog):
    busy = FakeAgy(busy=True)
    with pytest.raises(ms.SwitchFailed, match="busy"):
        ms.switch(_pane(busy), "argon", sleep=lambda _: None)
    assert busy.typed == []
    with pytest.raises(ms.SwitchFailed, match="no agy conversation id"):
        ms.switch(_pane(FakeAgy(), session=None), "argon", sleep=lambda _: None)
    unknown = FakeAgy()
    with pytest.raises(ms.SwitchFailed, match="no model hydrogen"):
        ms.switch(_pane(unknown), "hydrogen", sleep=lambda _: None)
    assert unknown.typed == []


def test_switch_to_the_current_model_does_not_restart(catalog):
    fake = FakeAgy("Gemini 4 Argon · medium")
    assert ms.switch(_pane(fake), "gemini-4-argon-medium", sleep=lambda _: None) == "gemini-4-argon-medium"
    assert fake.typed == []


# --- handing a conversation over ----------------------------------------------

def _transcript(tmp_path, monkeypatch, conversation="81ff1259"):
    home = tmp_path / "agy"
    monkeypatch.setenv("ANTIGRAVITY_APP_DATA_DIR", str(home))
    logs = home / "brain" / conversation / ".system_generated" / "logs"
    logs.mkdir(parents=True)
    records = [
        {"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "status": "DONE",
         "content": "<USER_REQUEST>\nReply with exactly the word PONG.\n</USER_REQUEST>\n"
                    "<ADDITIONAL_METADATA>\nThe current local time is: 2026-11-18T16:25:36-05:00.\n"
                    "</ADDITIONAL_METADATA>\n<USER_SETTINGS_CHANGE>\nThe user changed setting "
                    "`Model Selection`\n</USER_SETTINGS_CHANGE>"},
        {"step_index": 1, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "content": "PONG"},
        {"step_index": 2, "source": "USER_EXPLICIT", "type": "USER_INPUT", "status": "DONE",
         "content": "<USER_REQUEST>\nList the files.\n</USER_REQUEST>"},
        {"step_index": 3, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE",
         "tool_calls": [{"name": "run_command", "args": {"CommandLine": "ls"}}]},
        {"step_index": 4, "source": "MODEL", "type": "GENERIC", "status": "DONE",
         "content": "Command exited with code 0.\n\nCommand output:\nREADME.md"},
        {"step_index": 5, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "status": "DONE", "content": "[Message]"},
        {"step_index": 6, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "content": "One file: README.md."},
    ]
    path = logs / "transcript.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def test_agy_transcript_reads_as_plain_turns(tmp_path, monkeypatch):
    path = _transcript(tmp_path, monkeypatch)
    assert handoff.find_source("agy", "81ff1259") == path
    assert handoff.find_source("agy", "../81ff1259") is None
    turns = handoff.read_turns("agy", path)
    assert [t.role for t in turns] == ["user", "assistant", "user", "assistant", "assistant", "assistant"]
    assert turns[0].text == "Reply with exactly the word PONG."
    assert turns[3].text.startswith("[called run_command")
    assert "README.md" in turns[4].text and turns[4].text.startswith("[tool result]")


def test_switching_to_agy_seeds_a_new_session_with_the_handoff(tmp_path, monkeypatch):
    _transcript(tmp_path, monkeypatch)
    monkeypatch.setenv("AGENT_SWARM_HANDOFF_DIR", str(tmp_path / "handoffs"))
    row = {"user_id": "wren", "flavor": "agy", "agent_id": "81ff1259", "tmux_pane": "%9", "cwd": "/home/k/proj"}
    item = handoff.plan(row, "claude")
    assert item.skip is None and item.turns == 6
    into = handoff.plan({**row, "flavor": "claude", "agent_id": "x"}, "agy")
    assert into.skip is not None  # no claude transcript in this test, but agy is a valid target
    assert "agy is not a harness" not in into.skip
    item = handoff.plan(row, "agy", force=True)
    assert item.route == "seed"
    assert item.command.startswith("agy --dangerously-skip-permissions -i ")
