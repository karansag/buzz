"""Pure tests for snapshot capture, the restore plan, and resume commands."""

import json
import shutil
import subprocess
import uuid
from types import SimpleNamespace

import pytest

from agent_swarm import restore, tmux

SERVER = "100:1700000000"


@pytest.fixture(autouse=True)
def no_harness_probe(monkeypatch):
    # harness_accepts runs the installed binary; codex's --no-daemon counts as supported.
    monkeypatch.setattr(tmux, "harness_accepts", lambda binary, flag: True)


def row(session, window, pane, pane_id, command="bash", cwd="/w", layout="L1"):
    return {"session": session, "window": window, "window_name": f"w{window}", "layout": layout,
            "pane": pane, "pane_id": pane_id, "cwd": cwd, "command": command}


def recipient(handle, pane, agent_id, flavor="claude", server=SERVER, node="n1", model=None):
    return {"user_id": handle, "tmux_pane": pane, "tmux_server": server, "node": node,
            "agent_id": agent_id, "flavor": flavor, "model": model}


def test_capture_names_only_live_agents_bound_in_this_server():
    rows = [
        row("a", 0, 0, "%1", "claude", "/repo"),
        row("a", 0, 1, "%2", "node", "/repo"),
        row("a", 1, 0, "%3", "bash", "/repo"),   # registration left on a shell
        row("b", 2, 0, "%4", "claude", "/other"),
    ]
    recipients = [
        recipient("otter", "%1", "s-otter"),
        recipient("tapir", "%2", "s-tapir", flavor="codex"),
        recipient("gone", "%3", "s-gone"),
        recipient("stale", "%4", "s-stale", server="1:1"),   # bound in an older server
        recipient("elsewhere", "%1", "s-x", node="n2"),
    ]
    snap = restore.capture(rows, recipients, "n1", SERVER)
    assert [s["name"] for s in snap["sessions"]] == ["a", "b"]
    assert [w["index"] for w in snap["sessions"][0]["windows"]] == [0, 1]
    assert {a["handle"] for a in restore.agents_in(snap)} == {"otter", "tapir"}
    assert snap["sessions"][0]["windows"][0]["panes"][1]["agent"] == {
        "handle": "tapir", "flavor": "codex", "agent_id": "s-tapir", "model": None}


def test_save_skips_an_unchanged_snapshot_and_pick_skips_the_running_server(tmp_path):
    snap = restore.capture([row("a", 0, 0, "%1")], [], "n1", SERVER)
    first = restore.save(snap, tmp_path)
    assert first is not None
    assert restore.save({**snap, "taken_at": "later"}, tmp_path) is None
    assert restore.pick(tmp_path, SERVER) is None
    assert restore.pick(tmp_path, "200:1800000000") == first


def test_resume_commands_match_spawn_flags():
    cmd = restore.resume_command
    assert cmd({"flavor": "claude", "agent_id": "abc", "model": "claude-opus-5-5[1m]"}) == (
        "claude --resume abc --model 'claude-opus-5-5[1m]' --permission-mode auto")
    assert cmd({"flavor": "claude", "agent_id": "abc", "model": "claude-code"}) == (
        "claude --resume abc --permission-mode auto")
    assert cmd({"flavor": "codex", "agent_id": "t1", "model": "astra"}) == (
        "codex resume t1 -c check_for_update_on_startup=false --model astra --yolo --no-daemon")
    assert cmd({"flavor": "pi", "agent_id": "p1", "model": None}) == "pi --session p1"
    assert cmd({"flavor": "hermes", "agent_id": "h1", "model": None}) == (
        "hermes --resume h1 --yolo --accept-hooks")
    assert cmd({"flavor": "unknown", "agent_id": "x", "model": None}) is None


def test_codex_restore_always_uses_yolo(monkeypatch):
    monkeypatch.setattr(tmux.HARNESS_SPAWN["codex"], "launch_args", "")
    command = restore.resume_command({"flavor": "codex", "agent_id": "saved-session"})
    assert command == (
        "codex resume saved-session -c check_for_update_on_startup=false --yolo --no-daemon")


def snapshot_of(rows, recipients):
    return restore.capture(rows, recipients, "n1", SERVER)


def test_plan_recreates_a_missing_session_with_panes_layout_and_agents():
    snap = snapshot_of(
        [row("a", 3, 0, "%1", "claude", "/r1", "LAYOUT"), row("a", 3, 1, "%2", "bash", "/r2", "LAYOUT")],
        [recipient("otter", "%1", "s1")],
    )
    steps = restore.plan(snap, live=[])
    assert [s.argv[0] if s.argv else "launch" for s in steps] == [
        "new-session", "set-window-option", "split-window", "select-layout", "select-layout", "launch"]
    assert steps[0].place == ("a", 3)
    assert steps[2].argv == ["split-window", "-d", "-t", "=a:3.0", "-c", "/r2"]
    assert steps[4].argv[-1] == "LAYOUT"
    assert steps[5].target == "=a:3.0"
    assert steps[5].launch == "cd /r1 && claude --resume s1 --permission-mode auto"


def test_plan_adds_a_missing_window_to_an_existing_session():
    snap = snapshot_of([row("a", 0, 0, "%1"), row("a", 2, 0, "%2", "claude")],
                       [recipient("otter", "%2", "s1")])
    steps = restore.plan(snap, live=[row("a", 0, 0, "%9")])
    assert steps[0].argv[:4] == ["new-window", "-d", "-t", "=a:2"]
    assert steps[2].target == "=a:2.0"


def test_plan_reuses_only_a_bare_shell_at_the_old_position():
    snap = snapshot_of(
        [row("a", 0, 0, "%1", "claude"), row("a", 0, 1, "%2", "claude"), row("a", 0, 2, "%3", "claude")],
        [recipient("otter", "%1", "s1"), recipient("tapir", "%2", "s2"), recipient("mole", "%3", "s3")],
    )
    # After tmux-resurrect: same positions, new ids; one pane runs vim, one is missing.
    live = [row("a", 0, 0, "%7", "bash"), row("a", 0, 1, "%8", "vim")]
    steps = restore.plan(snap, live)
    assert steps[0].launch.endswith("claude --resume s1 --permission-mode auto")
    assert steps[0].target == "=a:0.0"
    assert "running vim" in steps[1].describe and steps[1].launch is None
    assert "without that pane" in steps[2].describe and steps[2].launch is None


def test_snapshot_round_trips_through_json(tmp_path):
    snap = snapshot_of([row("a", 0, 0, "%1", "claude")], [recipient("otter", "%1", "s1")])
    path = restore.save(snap, tmp_path)
    assert restore.plan(json.loads(path.read_text()), []) == restore.plan(snap, [])


def test_plan_never_starts_a_session_that_is_already_running():
    snap = snapshot_of([row("a", 0, 0, "%1", "claude"), row("a", 1, 0, "%2", "claude")],
                       [recipient("otter", "%1", "s1"), recipient("tapir", "%2", "s2")])
    steps = restore.plan(snap, live=[], running={"s1"})
    assert [s.describe for s in steps if s.launch is None and s.argv is None] == [
        "skip otter (claude) at a:0.0: its session is already running"]
    assert [s.target for s in steps if s.launch] == ["=a:1.0"]


def test_running_sessions_reads_the_hub_and_the_process_list(monkeypatch):
    class Done:
        stdout = "claude --resume s3 --permission-mode auto\nbash\n"
    monkeypatch.setattr(restore.subprocess, "run", lambda *a, **k: Done())
    recipients = [
        {"agent_id": "s1", "alive": True},
        {"agent_id": "s2", "alive": False},
        {"agent_id": "s3", "alive": False},
        {"agent_id": None, "alive": True},
    ]
    assert restore.running_sessions(recipients) == {"s1", "s3"}


def test_running_sessions_includes_snapshot_agents_no_longer_registered(monkeypatch):
    monkeypatch.setattr(restore.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout="claude --resume forgotten --permission-mode auto\n"))
    assert restore.running_sessions([], [{"agent_id": "forgotten"}]) == {"forgotten"}


def test_plan_resumes_a_linked_session_only_once():
    snap = snapshot_of([row("a", 0, 0, "%1", "claude"), row("b", 0, 0, "%1", "claude")],
                       [recipient("otter", "%1", "s1")])
    assert len([s for s in restore.plan(snap, []) if s.launch]) == 1


def test_save_keeps_changes_made_in_the_same_second(tmp_path):
    snap = snapshot_of([row("a", 0, 0, "%1")], [])
    first = restore.save(snap, tmp_path)
    snap["sessions"][0]["windows"][0]["panes"][0]["cwd"] = "/other"
    second = restore.save(snap, tmp_path)
    assert first != second
    assert len(list(tmp_path.glob("*.json"))) == 2
    assert not list(tmp_path.glob("*.tmp"))


def test_apply_stops_a_failed_window_but_continues_other_windows(monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if "new-session" in argv:
            raise subprocess.CalledProcessError(1, argv, stderr="bad directory")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(restore.subprocess, "run", run)
    steps = [
        restore.Step("create", argv=["new-session"], window="=a:0"),
        restore.Step("launch", target="=a:0.0", launch="should not run", window="=a:0"),
        restore.Step("other", argv=["select-layout"], window="=b:0"),
    ]
    assert restore.apply(steps, 0) == 1
    assert calls == [["tmux", "new-session"], ["tmux", "select-layout"]]


def test_apply_checks_shell_again_and_uses_immutable_pane_id(monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(stdout="%42\tbash\n")

    monkeypatch.setattr(restore.subprocess, "run", run)
    assert restore.apply([restore.Step("launch", target="=a:0.0", launch="echo ok")], 0) == 0
    assert calls[-2:] == [
        ["tmux", "send-keys", "-t", "%42", "-l", "echo ok"],
        ["tmux", "send-keys", "-t", "%42", "C-m"],
    ]
    calls.clear()
    monkeypatch.setattr(restore.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="%42\tvim\n"))
    assert restore.apply([restore.Step("launch", target="=a:0.0", launch="echo ok")], 0) == 1


@pytest.fixture
def isolated_tmux(monkeypatch):
    if not shutil.which("tmux"):
        pytest.skip("tmux is not installed")
    sock = "restore-test-" + uuid.uuid4().hex
    original = subprocess.run

    def t(*args):
        return original(["tmux", "-L", sock, "-f", "/dev/null", *args],
                        capture_output=True, text=True, check=True, timeout=10).stdout

    def run(argv, **kwargs):
        if argv[0] == "tmux":
            argv = ["tmux", "-L", sock, "-f", "/dev/null", *argv[1:]]
        return original(argv, **kwargs)

    monkeypatch.setattr(restore.subprocess, "run", run)
    try:
        t("new-session", "-d", "-s", "keeper")
        yield t
    finally:
        t("kill-server")


@pytest.mark.parametrize("pane_base", [0, 1])
def test_restore_nine_panes_with_saved_numbering_and_directories(isolated_tmux, tmp_path, pane_base):
    t = isolated_tmux
    t("set-option", "-g", "base-index", "1")
    t("new-session", "-d", "-s", "saved", "-x", "220", "-y", "80", "-c", str(tmp_path))
    t("set-window-option", "-t", "=saved:1", "pane-base-index", str(pane_base))
    for _ in range(8):
        t("split-window", "-d", "-t", "=saved:1", "-c", str(tmp_path))
        t("select-layout", "-t", "=saved:1", "tiled")
    before = [r for r in restore.read_layout() if r["session"] == "saved"]
    snap = restore.capture(before, [], "test", SERVER)
    t("kill-session", "-t", "=saved")
    t("set-window-option", "-g", "pane-base-index", str(1 - pane_base))
    t("set-option", "-g", "base-index", "0")
    assert restore.apply(restore.plan(snap, restore.read_layout()), 0) == 0
    after = [r for r in restore.read_layout() if r["session"] == "saved"]
    assert len(after) == 9
    assert [(r["window"], r["pane"], r["cwd"]) for r in after] == [
        (r["window"], r["pane"], r["cwd"]) for r in before]
    assert restore.plan(snap, restore.read_layout()) == []
