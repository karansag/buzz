"""An agent stopped by an error (usage limit, credits, API or auth) is
flagged from its screen: red text that names an error, near the bottom,
with no reply after it. Red alone and the words alone do not count."""

from pathlib import Path

from agent_swarm import activity

FIXTURES = Path(__file__).parent / "fixtures" / "screens"

RED = {
    "codex": "\x1b[38;5;1m",  # ANSI red, as tmux reports Codex's errors
    "claude": "\x1b[38;2;255;107;128m",  # Claude Code dark theme "error"
    "pi": "\x1b[38;2;234;127;129m",  # Pi dark theme "error", also its diff red
}
OFF = "\x1b[39m"


def red(flavor: str, text: str) -> str:
    return f"{RED[flavor]}{text}{OFF}"


CLAUDE_BOX = [
    "─" * 60,
    "❯ ",
    "─" * 60,
    "  ⏵⏵ auto mode on (shift+tab to cycle)",
]
PI_BOX = ["─" * 60, "", "─" * 60, "~/agent-swarm (master)", "↑12k ↓3k $0.41  42%/200k  openrouter/some-model"]


def screen(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def test_codex_usage_limit_from_a_real_pane():
    # skink's pane: the error wraps onto a second red line, and a pasted
    # message above it says "out of quota" without being red.
    text = (FIXTURES / "codex-usage-limit.ansi").read_text()
    assert activity.error_detail("codex", text) == (
        "■ You’ve hit your usage limit. Visit https://chatgpt.com/settings/usage"
        " to purchase more credits or try again at 1:32 PM."
    )


def test_claude_api_errors_and_limits():
    for line in [
        "  ⎿  API Error: 402 {\"type\":\"error\",\"error\":{\"type\":\"billing_error\"}}",
        "  ⎿  API Error: 401 Invalid API key · Please run /login",
        "  ⎿  Credit balance is too low",
        "  ⎿  You've hit your limit · resets 3pm (America/New_York)",
        "  ⎿  API Error: 529 Overloaded",
    ]:
        text = screen("> do the thing", "", red("claude", line), "", *CLAUDE_BOX)
        assert activity.error_detail("claude", text) == line.strip(), line


def test_pi_error_line():
    line = "Error: 402 Insufficient credits. Add more using https://openrouter.ai/settings/credits"
    text = screen(" ship it", "", red("pi", line), "", *PI_BOX)
    assert activity.error_detail("pi", text) == line


def test_red_that_is_not_an_error_does_not_flag():
    # Pi's diff red: removed lines, one even mentioning a 429.
    pi = screen(
        " edit server.py",
        red("pi", "- RETRY_ON = {429, 503}"),
        "\x1b[38;2;181;189;104m+ RETRY_ON = {503}\x1b[39m",
        "", *PI_BOX,
    )
    assert activity.error_detail("pi", pi) is None
    # Claude: a failing test in red, then the agent is waiting for input.
    claude = screen(red("claude", "FAILED tests/test_x.py::test_y - AssertionError"), "", *CLAUDE_BOX)
    assert activity.error_detail("claude", claude) is None
    # Codex: pink and orange status colors are not red.
    codex = screen("\x1b[38;5;175mweekly 0% left · quota\x1b[39m", "\x1b[38;5;208musage limit\x1b[39m")
    assert activity.error_detail("codex", codex) is None


def test_error_words_without_red_do_not_flag():
    text = screen("  ⎿  Notes: the API Error: 402 case is handled in billing.py", "", *CLAUDE_BOX)
    assert activity.error_detail("claude", text) is None


def test_an_error_with_a_reply_after_it_is_history():
    err = red("claude", "  ⎿  API Error: 529 Overloaded")
    assert activity.error_detail("claude", screen(err, "", "> try again", "", "● Done.", "", *CLAUDE_BOX)) is None
    err = red("codex", "■ stream error: rate limit exceeded")
    assert activity.error_detail("codex", screen(err, "", "• Retried and it worked.", "› ")) is None


def test_an_error_scrolled_far_up_is_history():
    err = red("pi", "Error: 429 Too Many Requests")
    later = [f"line {i}" for i in range(activity.ERROR_WINDOW)]
    assert activity.error_detail("pi", screen(err, *later, *PI_BOX)) is None
    assert activity.error_detail("pi", screen(err, *PI_BOX)) == "Error: 429 Too Many Requests"


def test_basic_red_and_256_color_reds():
    assert activity.error_detail(None, "\x1b[31mrate limit exceeded\x1b[0m\n> ") == "rate limit exceeded"
    assert activity.error_detail(None, "\x1b[1;91mquota exhausted\x1b[0m\n") == "quota exhausted"
    assert activity.error_detail(None, "\x1b[38;5;196mAPI Error: 500\x1b[0m\n") == "API Error: 500"


def test_colon_form_colors():
    assert activity.error_detail(None, "\x1b[38:2::234:127:129mError: 402 no credits\x1b[39m\n") == "Error: 402 no credits"
    assert activity.error_detail(None, "\x1b[38:2:0:234:127:129mquota exceeded\x1b[39m\n") == "quota exceeded"
    assert activity.error_detail(None, "\x1b[38:5:196mrate limit\x1b[39m\n") == "rate limit"
    # Green in colon form is not red, whatever the colorspace field says.
    assert activity.error_detail(None, "\x1b[38:2::0:200:0mrate limit\x1b[39m\n") is None


def test_strip_colors_gives_the_plain_screen():
    assert activity.strip_colors("\x1b[1m\x1b[38;2;1;2;3mhi\x1b[0m \x1b]0;title\x07there") == "hi there"


def test_step_flags_a_still_errored_screen_and_clears_when_it_works_again():
    reg = {}
    err = screen(red("codex", "■ You've hit your usage limit."), "› ")
    plain = activity.strip_colors(err)
    obs = activity.Observation("a", "codex", True, plain, err)
    activity.step(reg, [obs], 0, 5, 60)
    assert reg["a"]["status"] == "working" and reg["a"]["error"] is None  # just changed
    activity.step(reg, [obs], 20, 5, 60)
    assert reg["a"]["status"] == "idle" and reg["a"]["error"] == "■ You've hit your usage limit."
    busy = screen("• Working (3s)", "› ")
    activity.step(reg, [activity.Observation("a", "codex", True, busy, busy)], 25, 5, 60)
    assert reg["a"]["status"] == "working" and reg["a"]["error"] is None
