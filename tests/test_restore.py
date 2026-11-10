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
    assert cmd({"flavor": "pi", "agent_id": "p1", "model": "/m/bonsai.gguf"}) == "pi --session p1"
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
    assert restore.apply(steps, 0).failed == 1
    assert calls == [["tmux", "new-session"], ["tmux", "select-layout"]]


def test_apply_checks_shell_again_and_uses_immutable_pane_id(monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(stdout="%42\tbash\n")

    monkeypatch.setattr(restore.subprocess, "run", run)
    assert restore.apply([restore.Step("launch", target="=a:0.0", launch="echo ok")], 0).failed == 0
    assert calls[-2:] == [
        ["tmux", "send-keys", "-t", "%42", "-l", "echo ok"],
        ["tmux", "send-keys", "-t", "%42", "C-m"],
    ]
    calls.clear()
    monkeypatch.setattr(restore.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="%42\tvim\n"))
    assert restore.apply([restore.Step("launch", target="=a:0.0", launch="echo ok")], 0).failed == 1


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
    assert restore.apply(restore.plan(snap, restore.read_layout()), 0).failed == 0
    after = [r for r in restore.read_layout() if r["session"] == "saved"]
    assert len(after) == 9
    assert [(r["window"], r["pane"], r["cwd"]) for r in after] == [
        (r["window"], r["pane"], r["cwd"]) for r in before]
    assert restore.plan(snap, restore.read_layout()) == []


def test_apply_registers_each_resumed_agent_once_its_harness_runs(isolated_tmux):
    t = isolated_tmux
    t("new-session", "-d", "-s", "work")
    t("split-window", "-d", "-t", "=work:0")
    registered = []

    def register(pane, agent):
        registered.append((pane, agent["handle"]))
        return None

    # Made-up commands only: a real resume here would start a second copy of
    # a live session.
    steps = [
        restore.Step("resume a", target="=work:0.0", launch="exec sleep 30", agent={"handle": "a"}),
        restore.Step("resume b", target="=work:0.1", launch="true", agent={"handle": "b"}),
    ]
    panes = t("list-panes", "-t", "=work:0", "-F", "#{pane_id}").split()
    lines = []
    assert restore.apply(steps, 0, register=register, wait=10, log=lines.append, settle=1).failed == 1
    # b's command exits at once and leaves a shell, so it is not registered:
    # the hub would paste messages into that shell as commands.
    assert registered == [(panes[0], "a")]
    assert any(line.startswith(f"FAILED b at {panes[1]}") for line in lines)


# What Claude Code 2.1 draws when it starts in a folder it has no saved trust
# for, such as the home folder (whose trust it never saves).
CLAUDE_TRUST_SCREEN = """\
 Accessing workspace:
 /home/karan
 Quick safety check: Is this a project you created or one you trust?
 Claude Code'll be able to read, edit, and execute files here.
 ❯ No, exit
   Yes, I trust this folder
 Enter to confirm · Esc to cancel
"""


def test_apply_reports_an_agent_held_at_a_trust_prompt_and_still_registers_it(isolated_tmux, tmp_path):
    t = isolated_tmux
    t("new-session", "-d", "-s", "work")
    screen = tmp_path / "screen.txt"
    screen.write_text(CLAUDE_TRUST_SCREEN)
    registered = []
    steps = [restore.Step("resume a", target="=work:0.0", agent={"handle": "a"},
                          launch=f"cat {screen}; exec sleep 30")]
    lines = []
    outcome = restore.apply(steps, 0, register=lambda pane, agent: registered.append(agent["handle"]),
                            wait=10, log=lines.append, settle=3)
    assert (outcome.failed, outcome.blocked) == (0, 1)
    assert outcome.summary() == "done, 1 waiting at a trust prompt"
    # Registered, so the dashboard shows it waiting; the hub holds messages back.
    assert registered == ["a"]
    blocked = next(line for line in lines if line.startswith("BLOCKED a"))
    assert "Claude's workspace trust prompt for /home/karan" in blocked


def hub_row(handle="smew-claude-opus-karanslinux", **kw):
    return {"user_id": handle, "node": "here", "flavor": "claude", "agent_id": "sid-1",
            "model": None, "tmux_pane": "%5", "tmux_server": "srv", **kw}


def test_find_agent_takes_a_full_handle_or_an_unambiguous_first_part():
    rows = [hub_row(), hub_row("smewlet"), hub_row("otter-codex-a"), hub_row("otter-codex-b"), hub_row("otter")]
    assert restore.find_agent(rows, "smew")[0]["user_id"] == "smew-claude-opus-karanslinux"
    assert restore.find_agent(rows, "smew-claude-opus-karanslinux")[0]["user_id"] == "smew-claude-opus-karanslinux"
    assert restore.find_agent(rows, "otter")[0]["user_id"] == "otter"  # exact beats a prefix
    assert restore.find_agent(rows, "otter-codex") == (None, "otter-codex could mean otter-codex-a, otter-codex-b; give the full handle")
    assert restore.find_agent(rows, "smewl") == (None, "no agent named smewl")


def write_snapshot(directory, cwd="/work/dir", agent_id="sid-1"):
    directory.mkdir(exist_ok=True)
    snap = {"version": 1, "node": "here", "tmux_server": "old", "taken_at": "t", "sessions": [
        {"name": "system", "windows": [{"index": 0, "name": "agents", "layout": "x", "panes": [
            {"index": 0, "cwd": cwd, "command": "claude",
             "agent": {"handle": "smew", "flavor": "claude", "agent_id": agent_id, "model": None}}]}]}]}
    (directory / "20261101T000000000000.json").write_text(json.dumps(snap))


def live_pane(pane_id="%5", command="bash", cwd="/elsewhere", session="system"):
    return {"session": session, "window": 0, "window_name": "agents", "layout": "x", "pane": 0,
            "pane_id": pane_id, "cwd": cwd, "command": command}


def test_plan_one_resumes_into_its_own_pane_once_it_is_back_at_a_shell(tmp_path):
    write_snapshot(tmp_path)
    steps, why = restore.plan_one(hub_row(), [live_pane()], "here", "srv", set(), tmp_path)
    assert why is None and len(steps) == 1
    # The folder the session ran in (from the snapshot), not where the shell is now.
    assert steps[0].target == "%5"
    assert steps[0].launch.startswith("cd /work/dir && claude --resume sid-1")
    assert steps[0].agent["handle"] == "smew-claude-opus-karanslinux"


def test_plan_one_refuses_what_it_must_not_touch(tmp_path):
    write_snapshot(tmp_path)
    plan = lambda r, live=(), running=frozenset(): restore.plan_one(r, list(live), "here", "srv", set(running), tmp_path)
    assert plan(hub_row(), [live_pane(command="vim")]) == ([], "its pane %5 is running vim; restore leaves it alone")
    assert plan(hub_row(), running={"sid-1"})[1].startswith("smew-claude-opus-karanslinux is already running")
    assert plan(hub_row(node="mac"))[1] == "smew-claude-opus-karanslinux runs on mac; run restore there"
    assert plan(hub_row(agent_id=None))[1] == "smew-claude-opus-karanslinux has no saved session to resume"
    assert plan(hub_row(flavor="generic"))[1] == "no resume command for generic"
    steps, why = restore.plan_one(hub_row(), [], "here", "srv", set(), tmp_path / "none")
    assert steps == [] and "knows its folder" in why


def test_plan_one_puts_an_agent_whose_pane_is_gone_in_a_new_window_where_it_ran(tmp_path):
    write_snapshot(tmp_path)
    # Its pane id is from an earlier tmux server, so a live %5 is someone else's.
    steps, why = restore.plan_one(hub_row(tmux_server="old"), [live_pane(command="vim")], "here", "srv", set(), tmp_path)
    assert why is None
    assert steps[0].argv[:5] == ["new-window", "-d", "-P", "-F", "#{pane_id}"]
    assert steps[0].argv[-2:] == ["-c", "/work/dir"]
    assert steps[1].target is None and steps[1].launch.startswith("cd /work/dir && claude --resume sid-1")
    steps, _ = restore.plan_one(hub_row(tmux_server="old"), [], "here", "srv", set(), tmp_path)
    assert steps[0].argv[:7] == ["new-session", "-d", "-P", "-F", "#{pane_id}", "-s", "system"]


def test_restore_one_agent_into_a_new_window_end_to_end(isolated_tmux, tmp_path):
    t = isolated_tmux
    t("new-session", "-d", "-s", "system")
    folder = tmp_path / "project"
    folder.mkdir()
    write_snapshot(tmp_path / "snaps", cwd=str(folder))
    steps, why = restore.plan_one(hub_row(tmux_server="old"), restore.read_layout(), "here", "srv", set(), tmp_path / "snaps")
    assert why is None
    # Made-up command in place of the real resume: never resume a real session in a test.
    steps[1].launch = steps[1].launch.split(" && ")[0] + " && exec sleep 30"
    registered = []
    outcome = restore.apply(steps, 0, register=lambda pane, agent: registered.append(pane), wait=10,
                            log=lambda line: None, settle=1)
    assert (outcome.failed, outcome.blocked) == (0, 0)
    panes = t("list-panes", "-s", "-t", "=system", "-F", "#{pane_id} #{pane_current_path} #{pane_current_command}").splitlines()
    assert len(panes) == 2
    new = panes[1].split()
    assert registered == [new[0]] and new[1:] == [str(folder), "sleep"]


def test_plan_one_uses_the_hub_recorded_folder_without_a_snapshot(tmp_path):
    steps, why = restore.plan_one(hub_row(cwd="/work/smew"), [], "here", "srv", set(), tmp_path / "none")
    assert why is None
    assert steps[0].argv[:2] == ["new-session", "-d"] and "/work/smew" in steps[0].argv
    assert steps[1].launch.startswith("cd /work/smew && ")
