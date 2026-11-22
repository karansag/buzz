"""Switching an agent to another harness: transcripts in, transcripts out.

Every test runs against fake transcripts in a tmp HOME/CODEX_HOME/
PI_CODING_AGENT_DIR, so no real session is ever read, written or resumed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_swarm import handoff, tmux


@pytest.fixture(autouse=True)
def fake_homes(tmp_path, monkeypatch):
    home = tmp_path / "home"
    codex = home / ".codex"
    pi = home / ".pi" / "agent"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(codex))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(pi))
    monkeypatch.setenv("ANTIGRAVITY_APP_DATA_DIR", str(home / ".gemini" / "antigravity-cli"))
    # Never probe the real harness binaries from a test.
    monkeypatch.setattr(tmux, "harness_accepts", lambda binary, flag: False)
    return {"home": home, "codex": codex, "pi": pi, "agy": home / ".gemini" / "antigravity-cli"}


def claude_session(home: Path, session_id: str, cwd: str, records: list[dict]) -> Path:
    path = home / ".claude" / "projects" / handoff.claude_project_dir(cwd) / f"{session_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def codex_session(codex: Path, session_id: str, cwd: str, items: list[dict]) -> Path:
    folder = codex / "sessions" / "2026" / "05" / "04"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"rollout-2026-05-04T10-00-00-{session_id}.jsonl"
    meta = {"timestamp": "2026-05-04T10:00:00.000Z", "ordinal": 0, "type": "session_meta",
            "payload": {"session_id": session_id, "id": session_id, "cwd": cwd}}
    lines = [meta] + [
        {"timestamp": "2026-05-04T10:00:01.000Z", "ordinal": i + 1, "type": "response_item", "payload": item}
        for i, item in enumerate(items)
    ]
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    return path


def pi_session(pi: Path, session_id: str, cwd: str, messages: list[dict]) -> Path:
    folder = handoff.pi_session_dir(cwd, pi)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"2026-05-04T10-00-00-000Z_{session_id}.jsonl"
    lines = [{"type": "session", "version": 3, "id": session_id, "timestamp": "2026-05-04T10:00:00.000Z", "cwd": cwd}]
    lines += [{"type": "message", "id": f"0000000{i}", "parentId": None,
               "timestamp": "2026-05-04T10:00:01.000Z", "message": m} for i, m in enumerate(messages)]
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    return path


def agy_session(agy: Path, conversation: str, records: list[dict]) -> Path:
    path = agy / "brain" / conversation / ".system_generated" / "logs" / "transcript.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


CWD = "/work/repo"

CLAUDE_RECORDS = [
    {"type": "mode", "mode": "normal"},
    {"type": "user", "message": {"role": "user", "content": "Build the parser, the ticket is 4417."}},
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "I should look at the repo first."},
        {"type": "text", "text": "Reading the repo."},
        {"type": "tool_use", "name": "bash", "input": {"command": "ls"}},
    ]}},
    {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "content": [{"type": "text", "text": "README.md\nsrc"}]},
    ]}},
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "The parser is in src and the ticket number is 4417."},
    ]}},
]

CODEX_ITEMS = [
    {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "<skills>ignore me</skills>"}]},
    {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Build the parser, the ticket is 4417."}]},
    {"type": "reasoning", "summary": [], "encrypted_content": "xxxx"},
    {"type": "function_call", "name": "shell", "arguments": "{\"command\":[\"ls\"]}", "call_id": "c1"},
    {"type": "function_call_output", "call_id": "c1", "output": [{"type": "input_text", "text": "README.md\nsrc"}]},
    {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "The parser is in src and the ticket number is 4417."}]},
]

PI_MESSAGES = [
    {"role": "system", "content": "You are an expert coding assistant."},
    {"role": "user", "content": [{"type": "text", "text": "Build the parser, the ticket is 4417."}]},
    {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "Look at the repo first."},
        {"type": "toolCall", "name": "bash", "arguments": {"command": "ls"}},
    ]},
    {"role": "toolResult", "content": [{"type": "text", "text": "README.md\nsrc"}]},
    {"role": "assistant", "content": [{"type": "text", "text": "The parser is in src and the ticket number is 4417."}]},
]


AGY_RECORDS = [
    {"source": "SYSTEM", "type": "SYSTEM_MESSAGE", "content": "You are an expert coding assistant."},
    {"source": "USER_EXPLICIT", "type": "USER_INPUT", "content":
        "<USER_REQUEST>\nBuild the parser, the ticket is 4417.\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nx\n</ADDITIONAL_METADATA>"},
    {"source": "MODEL", "type": "PLANNER_RESPONSE", "thinking": "I should look at the repo first.",
     "tool_calls": [{"name": "bash", "args": {"CommandLine": "ls"}}]},
    {"source": "MODEL", "type": "GENERIC", "content": "Command exited with code 0.\n\nCommand output:\nREADME.md\nsrc"},
    {"source": "MODEL", "type": "PLANNER_RESPONSE", "content": "The parser is in src and the ticket number is 4417."},
]


def source_for(flavor: str, homes) -> tuple[str, Path]:
    if flavor == "claude":
        return "claude-src", claude_session(homes["home"], "claude-src", CWD, CLAUDE_RECORDS)
    if flavor == "codex":
        return "codex-src", codex_session(homes["codex"], "codex-src", CWD, CODEX_ITEMS)
    if flavor == "agy":
        return "agy-src", agy_session(homes["agy"], "agy-src", AGY_RECORDS)
    return "pi-src", pi_session(homes["pi"], "pi-src", CWD, PI_MESSAGES)


@pytest.mark.parametrize("flavor", handoff.FLAVORS)
def test_find_source_locates_the_harness_session(flavor, fake_homes):
    session_id, path = source_for(flavor, fake_homes)
    assert handoff.find_source(flavor, session_id) == path
    assert handoff.find_source(flavor, "not-a-session") is None
    assert handoff.find_source(flavor, None) is None
    assert handoff.find_source("hermes", session_id) is None


@pytest.mark.parametrize("flavor", handoff.FLAVORS)
def test_read_turns_keeps_the_conversation_and_flattens_tools(flavor, fake_homes):
    session_id, path = source_for(flavor, fake_homes)
    turns = handoff.read_turns(flavor, path)
    roles = [turn.role for turn in turns]
    assert roles[0] == "user" and "ticket" in turns[0].text
    assert roles[-1] == "assistant" and "4417" in turns[-1].text
    # The middle is tool noise, as notes, and thinking never travels.
    body = "\n".join(turn.text for turn in turns)
    assert "[called bash" in body or "[called shell" in body
    assert "[tool result]" in body
    assert "thinking" not in body.lower() or "I should look" not in body
    # Developer/system instructions are not the conversation.
    assert "You are an expert coding assistant" not in body


def test_fit_keeps_the_newest_turns_and_says_how_many_went():
    turns = [handoff.Turn("user", "a" * 100), handoff.Turn("assistant", "b" * 100),
             handoff.Turn("user", "c" * 100)]
    kept, dropped = handoff.fit(turns, 250)
    assert dropped == 1
    assert [t.text[0] for t in kept] == ["b", "c"]
    # Always keep at least the last turn, however small the budget.
    kept, dropped = handoff.fit(turns, 10)
    assert [t.text[0] for t in kept] == ["c"] and dropped == 2


def test_large_tool_output_and_turns_are_clipped():
    record = {"type": "user", "message": {"role": "user", "content": [
        {"type": "text", "text": "x" * 20_000},
    ]}}
    turn = handoff._claude_turn(record)
    assert len(turn.text) < handoff.TURN_CLIP + 100 and "clipped" in turn.text
    result = handoff._claude_turn({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "content": [{"type": "text", "text": "y" * 50_000}]},
    ]}})
    assert len(result.text) < handoff.NOTE_CLIP + 100 and "clipped" in result.text


@pytest.mark.parametrize("target", ["claude", "pi"])
def test_written_session_is_resumable_and_the_source_is_untouched(target, fake_homes):
    session_id, source = source_for("claude", fake_homes)
    before = source.read_bytes()
    item = handoff.Switch(handle="otter", to=target, model=None, from_flavor="claude",
                          from_agent_id=session_id, source_path=source, cwd=CWD, pane="%1")
    item.command = handoff.restore.resume_command({"flavor": target, "agent_id": item.session_id})
    path = handoff.write(item)
    assert path == item.session_path if item.session_path else True
    assert path.is_file() and path.stat().st_mode & 0o777 == 0o600
    # The source is the way back: byte for byte unchanged.
    assert source.read_bytes() == before
    # The new session reads back as the conversation, plus the handoff note.
    turns = handoff.read_turns(target, path)
    assert turns[0].role == "user" and "handoff" in turns[0].text
    assert "4417" in "\n".join(t.text for t in turns[1:])
    assert [t.role for t in turns[1:]][:2] == ["user", "assistant"]
    # And it sits where that harness looks for its own sessions.
    if target == "claude":
        assert path.parent.name == handoff.claude_project_dir(CWD)
        assert path.stem == item.session_id
    else:
        assert path.parent == handoff.pi_session_dir(CWD)
        assert path.name.endswith(f"_{item.session_id}.jsonl")


@pytest.mark.parametrize("target", ["claude", "pi"])
def test_the_launch_command_resumes_the_new_session(target, fake_homes):
    command = handoff.restore.resume_command({"flavor": target, "agent_id": "session-42", "model": None})
    flag = {"claude": "--resume", "codex": "resume", "pi": "--session"}[target]
    assert command is not None and flag in command and "session-42" in command


def recipient(**over):
    row = {"user_id": "otter", "flavor": "claude", "agent_id": "claude-src", "cwd": CWD,
           "tmux_pane": "%1", "node": "karans-linux", "tmux_server": "s"}
    row.update(over)
    return row


def test_plan_explains_every_reason_to_skip_before_writing_anything(fake_homes):
    session_id, path = source_for("claude", fake_homes)
    assert handoff.plan(recipient(), "claude").skip.startswith("it is already running claude")
    assert handoff.plan(recipient(), "claude", force=True).skip is None
    assert "not a harness" in handoff.plan(recipient(), "hermes").skip
    assert "no session id" in handoff.plan(recipient(agent_id=None), "pi").skip
    assert "no claude transcript" in handoff.plan(recipient(agent_id="ghost"), "pi").skip
    assert "folder" in handoff.plan(recipient(cwd=None), "pi").skip
    assert "unknown" in handoff.plan(recipient(flavor=""), "pi").skip
    # A refused plan writes nothing.
    assert not (fake_homes["home"] / ".pi").exists()


def test_plan_counts_what_will_travel_and_shows_the_command(fake_homes):
    session_id, path = source_for("claude", fake_homes)
    item = handoff.plan(recipient(), "pi")
    assert item.skip is None
    assert item.from_flavor == "claude" and item.from_agent_id == session_id
    assert item.turns >= 3 and item.chars > 0 and item.dropped == 0
    assert "pi --session" in item.command and item.session_id in item.command
    assert str(item.session_path).endswith(".jsonl")


def test_a_tight_budget_drops_old_turns_and_says_so(fake_homes):
    # A long conversation: 30 turns of 400 characters each.
    records = []
    for i in range(30):
        role = "user" if i % 2 == 0 else "assistant"
        records.append({"type": role, "message": {"role": role, "content": f"turn {i} " + "x" * 400}})
    records.append({"type": "assistant", "message": {"role": "assistant", "content": "the ticket is 4417"}})
    claude_session(fake_homes["home"], "long", CWD, records)
    item = handoff.plan(recipient(agent_id="long"), "pi", max_chars=2000)
    assert item.skip is None and item.dropped > 0
    written = handoff.write(item, max_chars=2000)
    turns = handoff.read_turns("pi", written)
    assert "left out" in turns[0].text
    assert "4417" in "\n".join(t.text for t in turns)


def test_apply_respawns_the_pane_and_launches_the_resume_command(fake_homes, monkeypatch):
    session_id, path = source_for("claude", fake_homes)
    calls = []
    monkeypatch.setattr(tmux, "respawn_pane", lambda pane, cwd=None: calls.append(("respawn", pane, cwd)) or (True, None))
    monkeypatch.setattr(tmux, "type_line", lambda pane, line: calls.append(("type", pane, line)) or (True, None))
    item = handoff.plan(recipient(), "pi")
    assert handoff.apply(item) is None
    assert calls[0] == ("respawn", "%1", CWD)
    assert calls[1][0] == "type" and calls[1][1] == "%1"
    assert calls[1][2].startswith(f"cd {CWD} && pi --session {item.session_id}")
    assert item.session_path.is_file()


def test_apply_reports_a_respawn_failure_without_typing(fake_homes, monkeypatch, tmp_path):
    session_id, path = source_for("claude", fake_homes)
    typed = []
    monkeypatch.setattr(tmux, "respawn_pane", lambda pane, cwd=None: (False, "no such pane"))
    monkeypatch.setattr(tmux, "type_line", lambda pane, line: typed.append(line) or (True, None))
    item = handoff.plan(recipient(cwd=str(tmp_path)), "codex")
    error = handoff.apply(item)
    assert error and "no such pane" in error
    assert typed == []


def test_apply_refuses_a_skipped_plan(fake_homes, monkeypatch):
    monkeypatch.setattr(tmux, "respawn_pane", lambda pane, cwd=None: pytest.fail("should not respawn"))
    item = handoff.plan(recipient(agent_id=None), "pi")
    assert handoff.apply(item) == "it has no session id, so its conversation cannot be found"


def test_codex_target_is_seeded_with_a_handoff_file(fake_homes, monkeypatch, tmp_path):
    # Codex's own rollout files are written by its app server and a hand-written
    # one was not picked up by `codex resume` in testing, so a switch into Codex
    # writes the conversation to a file and starts a fresh session that reads it.
    session_id, path = source_for("claude", fake_homes)
    monkeypatch.setattr(tmux, "harness_accepts", lambda binary, flag: False)
    calls = []
    monkeypatch.setattr(tmux, "respawn_pane", lambda pane, cwd=None: (True, None))
    monkeypatch.setattr(tmux, "type_line", lambda pane, line: calls.append(line) or (True, None))
    item = handoff.plan(recipient(cwd=str(tmp_path)), "codex")
    assert item.skip is None and item.route == "seed"
    # The handoff lives in Buzz's own directory, not in the agent's repo.
    assert item.session_path.parent == fake_homes["home"] / ".agent-swarm" / "handoffs"
    assert handoff.apply(item) is None
    handed = item.session_path
    assert handed.is_file() and handed.stat().st_mode & 0o777 == 0o600
    assert handed.name.startswith("otter-") and handed.name.endswith(".md")
    assert not (tmp_path / ".buzz-handoff-otter.md").exists()
    body = handed.read_text()
    assert "handoff" in body and "4417" in body
    assert calls and "codex" in calls[0] and str(handed) in calls[0]
    assert "Read " in calls[0]


def compact_fixture(tmp_path, records, name="fake-session.jsonl"):
    path = tmp_path / name
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    return path


def test_claude_handoff_keeps_the_latest_summary_and_preserved_segment(tmp_path):
    def message(uid, content, **fields):
        return {"type": "user", "uuid": uid, "message": {"content": content}, **fields}

    path = compact_fixture(tmp_path, [
        message("old", "discarded"),
        {"type": "system", "subtype": "compact_boundary"},
        message("first", "superseded", isCompactSummary=True),
        message("kept", "kept", parentUuid="first"),
        message("end", "end of retained segment", parentUuid="kept"),
        message("noise", "outside retained segment"),
        {"type": "system", "subtype": "compact_boundary", "compactMetadata": {
            "preservedSegment": {"headUuid": "kept", "tailUuid": "end", "anchorUuid": "latest"},
        }},
        message("latest", "latest summary", isMeta=True, isCompactSummary=True),
        message("last", "new turn", parentUuid="latest"),
    ])
    turns = handoff.read_turns("claude", path)
    assert turns[0].summary and turns[0].text.endswith("latest summary")
    assert [t.text for t in turns[1:]] == ["kept", "end of retained segment", "new turn"]


@pytest.mark.parametrize("encrypted", [False, True])
def test_codex_handoff_uses_replacement_history(tmp_path, encrypted):
    def message(text, role="user"):
        return {"type": "message", "role": role, "content": [{"type": "input_text", "text": text}]}

    path = compact_fixture(tmp_path, [
        {"type": "response_item", "payload": message("discarded")},
        {"type": "compacted", "payload": {"message": "superseded", "replacement_history": []}},
        {"type": "compacted", "payload": {
            "message": "" if encrypted else "latest summary",
            "replacement_history": [message("developer instructions", "developer"), message("kept"),
                                    {"type": "compaction", "encrypted_content": "opaque"}],
        }},
        {"type": "response_item", "payload": message("new turn")},
    ])
    turns = handoff.read_turns("codex", path)
    assert turns[0].summary
    assert ("encrypted form" if encrypted else "latest summary") in turns[0].text
    assert [t.text for t in turns[1:]] == ["kept", "new turn"]


def test_pi_handoff_uses_latest_compaction_on_active_branch(tmp_path):
    def message(uid, parent, text):
        return {"type": "message", "id": uid, "parentId": parent, "message": {"role": "user", "content": text}}

    def compact(uid, parent, first):
        return {"type": "compaction", "id": uid, "parentId": parent,
                "firstKeptEntryId": first, "summary": uid + " summary"}

    path = compact_fixture(tmp_path, [
        message("root", None, "discarded"),
        compact("older", "root", "root"),
        message("kept", "older", "kept"),
        compact("active", "kept", "kept"),
        message("other", "root", "other branch"),
        compact("abandoned", "other", "other"),
        message("last", "active", "new turn"),
    ])
    turns = handoff.read_turns("pi", path)
    assert turns[0].summary and turns[0].text.endswith("active summary")
    assert [t.text for t in turns[1:]] == ["kept", "new turn"]


def test_agy_handoff_reads_the_latest_checkpoint_from_the_full_log(tmp_path):
    def checkpoint(index, content, status="DONE"):
        return {"type": "CHECKPOINT", "source": "SYSTEM", "status": status,
                "step_index": index, "content": content}

    prefix = [*AGY_RECORDS, checkpoint(5, "superseded"), AGY_RECORDS[-1]]
    tail = [checkpoint(8, "", "RUNNING"), {"type": "PLANNER_RESPONSE", "content": "new turn"}]
    path = compact_fixture(tmp_path, prefix + [checkpoint(7, "clipped")] + tail, "transcript.jsonl")
    compact_fixture(tmp_path, prefix + [checkpoint(7, "complete summary")] + tail, "transcript_full.jsonl")
    turns = handoff.read_turns("agy", path)
    assert turns[0].summary and turns[0].text.endswith("complete summary")
    assert [t.text for t in turns[1:]] == ["new turn"]


def test_fit_keeps_the_complete_summary_and_last_turn_under_pressure():
    summary = handoff.Turn("user", "summary " * 2000, summary=True)
    last = handoff.Turn("assistant", "last turn")
    turns = [summary] + [handoff.Turn("user", "x" * 8000)] * 30 + [last]
    kept, dropped = handoff.fit(turns, 20000)
    assert kept == [summary, last] and dropped == 30
    assert handoff.fit(turns, 1) == ([summary, last], 30)
    assert handoff.fit([summary], 1) == ([summary], 0)
