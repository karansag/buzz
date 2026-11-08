"""Pure step() tests with fabricated observations; no loop, no tmux."""

from agent_swarm import activity
from agent_swarm.activity import Observation

INTERVAL = 5.0
GRACE = 15.0

CLAUDE_DIALOG = "Do you want to proceed?\n❯ 1. Yes\n  2. No\nEsc to cancel"


def obs(user_id="otter", flavor="claude", pane_alive=True, capture="hello"):
    return Observation(user_id, flavor, pane_alive, capture)


def run(reg, observations, now):
    return activity.step(reg, observations, now, INTERVAL, GRACE)


def test_snapshot_hash_ignores_trailing_whitespace():
    assert activity.snapshot_hash("a   \nb\n\n") == activity.snapshot_hash("a\nb")
    assert activity.snapshot_hash("a") != activity.snapshot_hash("b")


def test_changed_capture_reads_working():
    reg = {}
    run(reg, [obs(capture="screen 1")], now=0)
    run(reg, [obs(capture="screen 2")], now=INTERVAL)
    assert reg["otter"]["status"] == "working"
    assert reg["otter"]["changed_at"] == INTERVAL


def test_static_short_keeps_previous_status():
    reg = {}
    run(reg, [obs(capture="A")], now=0)  # working
    run(reg, [obs(capture="A")], now=INTERVAL)  # < 2*interval static
    assert reg["otter"]["status"] == "working"


def test_static_long_reads_idle():
    reg = {}
    run(reg, [obs(capture="A")], now=0)
    run(reg, [obs(capture="A")], now=3 * INTERVAL)
    assert reg["otter"]["status"] == "idle"
    assert reg["otter"]["detail"] is None


def test_static_long_with_dialog_reads_needs_attention():
    reg = {}
    run(reg, [obs(capture=CLAUDE_DIALOG)], now=0)
    run(reg, [obs(capture=CLAUDE_DIALOG)], now=3 * INTERVAL)
    assert reg["otter"]["status"] == "needs_attention"
    assert reg["otter"]["detail"] == "Do you want to proceed?"


def test_capture_failure_reads_unknown():
    reg = {}
    run(reg, [obs(capture=None)], now=0)
    assert reg["otter"]["status"] == "unknown"


def test_dead_pane_reads_stopped():
    reg = {}
    run(reg, [obs(pane_alive=False, capture=None)], now=0)
    assert reg["otter"]["status"] == "stopped"


def test_dead_pane_beats_capture():
    reg = {}
    run(reg, [obs(pane_alive=False, capture="whatever")], now=0)
    assert reg["otter"]["status"] == "stopped"


def test_notification_emitted_once_then_rearmed():
    reg = {}
    # Establish the static dialog and let it become needs_attention.
    run(reg, [obs(capture=CLAUDE_DIALOG)], now=0)
    run(reg, [obs(capture=CLAUDE_DIALOG)], now=3 * INTERVAL)
    assert reg["otter"]["status"] == "needs_attention"
    since = reg["otter"]["since"]

    # Before grace elapses: no notification.
    assert run(reg, [obs(capture=CLAUDE_DIALOG)], now=since + GRACE - 1) == []
    # At/after grace: exactly one.
    notes = run(reg, [obs(capture=CLAUDE_DIALOG)], now=since + GRACE)
    assert notes == [activity.Notification("otter", "Do you want to proceed?")]
    # Still attention, already notified: silent.
    assert run(reg, [obs(capture=CLAUDE_DIALOG)], now=since + GRACE + INTERVAL) == []

    # Recovery re-arms: agent works, then a fresh dialog fires again.
    run(reg, [obs(capture="back to work")], now=since + GRACE + 2 * INTERVAL)
    assert reg["otter"]["status"] == "working"
    assert reg["otter"]["notified"] is False
    base = since + GRACE + 10 * INTERVAL
    run(reg, [obs(capture=CLAUDE_DIALOG)], now=base)
    run(reg, [obs(capture=CLAUDE_DIALOG)], now=base + 3 * INTERVAL)
    new_since = reg["otter"]["since"]
    notes2 = run(reg, [obs(capture=CLAUDE_DIALOG)], now=new_since + GRACE)
    assert notes2 == [activity.Notification("otter", "Do you want to proceed?")]


def test_unregistered_users_dropped():
    reg = {}
    run(reg, [obs(user_id="otter"), obs(user_id="tapir")], now=0)
    assert set(reg) == {"otter", "tapir"}
    run(reg, [obs(user_id="otter")], now=INTERVAL)
    assert set(reg) == {"otter"}


# Real screens (trimmed) the detector has to get right.
BADGER_PROSE = """\
• Noted. #9131 is already approved, and my pass found no additional blocker. I updated Agent Swarm task
  #12 accordingly.

  Remaining recommendations:

  - Approve #9130.
  - Hold #9128 and #9129 for the identified fixes.

─────────────────────────────────────────────────────────────────────

› Ask a follow-up question

  gpt-5.6-sol medium · ~/marin · main"""

CODEX_APPROVAL = """\
• I need to run the test suite.

  Would you like to run the following command?

  $ uv run pytest -q

› 1. Yes, proceed (y)
  2. Yes, and don't ask again for this command in this session (a)
  3. No, and tell Codex what to do differently (esc)

  Press enter to confirm or esc to cancel"""

CLAUDE_PROSE = """\
⏺ Cleanup is on master and pushed. Do you want to restart the launchd service now?

❯ 
  ? for shortcuts"""


def detail(flavor, capture):
    return activity._attention_detail(flavor, capture)


def test_agent_prose_is_not_a_prompt():
    assert detail("codex", BADGER_PROSE) is None
    assert detail("claude", CLAUDE_PROSE) is None
    assert detail("codex", "I'd answer y/n here, and Approve the PR.") is None


def test_codex_approval_prompt_reports_its_question():
    assert detail("codex", CODEX_APPROVAL) == "Would you like to run the following command?"
    # Without the question on screen, the option line still flags it.
    options_only = CODEX_APPROVAL.split("› 1.")[1]
    assert detail("codex", "› 1." + options_only) == "› 1. Yes, proceed (y)"


def test_codex_legacy_allow_command_prompt():
    assert detail("codex", "▌Allow command?\n▌ Yes (y)  No (n)") == "▌Allow command?"


def test_claude_dialog_reports_its_question():
    assert detail("claude", CLAUDE_DIALOG) == "Do you want to proceed?"


def test_generic_prompts():
    assert detail("generic", "[sudo] password for karan: ") == "[sudo] password for karan:"
    assert detail("pi", "Overwrite file? [y/N]") == "Overwrite file? [y/N]"
    assert detail("generic", "set the password: in config.yaml first") is None


def test_badger_screen_reads_idle_not_attention():
    reg = {}
    run(reg, [obs(flavor="codex", capture=BADGER_PROSE)], now=0)
    run(reg, [obs(flavor="codex", capture=BADGER_PROSE)], now=3 * INTERVAL)
    assert reg["otter"]["status"] == "idle"


CODEX_QUESTION = """\
  └ {"ok":true,"message_id":751,"delivered_to_pane":null,"delivery_error":null}


  Question 1/2 (2 unanswered)
  Which Pi package should task #20 install?

  › 1. Current official (Recommended)  Install @earendil-works/pi-coding-agent.
    2. Deprecated legacy               Install @mariozechner/pi-coding-agent.
    3. None of the above               Optionally, add details in notes (tab).

  tab to add notes | enter to submit answer | ←/→ to navigate questions | esc to interrupt"""


def test_codex_question_form_needs_attention_and_shows_the_question():
    assert detail("codex", CODEX_QUESTION) == "Which Pi package should task #20 install?"
    reg = {}
    run(reg, [obs(flavor="codex", capture=CODEX_QUESTION)], now=0)
    run(reg, [obs(flavor="codex", capture=CODEX_QUESTION)], now=3 * INTERVAL)
    assert reg["otter"]["status"] == "needs_attention"


def test_prose_about_questions_is_not_a_question_form():
    assert detail("codex", "I answered question 3 and moved on.") is None


CLAUDE_TRUST = """\
 Accessing workspace:

 /home/karan

 Quick safety check: Is this a project you created or one you trust?
 ❯ No, exit
   Yes, I trust this folder

 Enter to confirm · Esc to cancel
"""

CODEX_TRUST = """\
  Trust this folder?
  Codex can read, edit, and run files here, subject to your permission settings.
› 1. Trust and continue
  2. Open restricted
"""


def test_trust_prompts_are_recognized_with_their_folder():
    assert activity.trust_prompt(CLAUDE_TRUST) == "Claude's workspace trust prompt for /home/karan"
    assert activity.trust_prompt(CODEX_TRUST) == "Codex's workspace trust prompt"
    old_codex = "Do you trust the contents of this directory?\n› 1. Yes, continue\n  2. No, quit\n"
    assert activity.trust_prompt(old_codex) == "Codex's workspace trust prompt"


def test_quoting_a_trust_prompt_is_not_one():
    # An agent's own prose can mention the words; only the title with its answer counts.
    assert activity.trust_prompt("● It stopped at Accessing workspace: and I said Yes, I trust this folder.") is None
    assert activity.trust_prompt("Accessing workspace:\n/home/karan\n") is None
    assert activity.trust_prompt("") is None


def test_a_trust_prompt_shows_as_needing_attention_with_a_clear_reason():
    registry = {}
    obs = [activity.Observation("smew", "claude", True, CLAUDE_TRUST)]
    for now in (0.0, 2.0, 4.0, 6.0):
        activity.step(registry, obs, now, interval=2.0, grace=0.0)
    assert registry["smew"]["status"] == "needs_attention"
    assert registry["smew"]["detail"] == (
        "waiting at Claude's workspace trust prompt for /home/karan: answer it in the pane")
