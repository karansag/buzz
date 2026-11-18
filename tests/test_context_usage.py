"""Context figures read from a harness footer; screens here are fabricated."""

from agent_swarm import context_usage as cu

CLAUDE = "❯ \n" + "─" * 40 + "\n  /home/x/repo  [Opus 5.5 | ctx:6% | wk:33%]\n  ⏵⏵ auto mode on (shift+tab to cycle)\n"
CODEX = ("› Ask Codex to do anything\n\n  GPT-6.2-Sol medium · ~/repo · Context 55% used · weekly 24% left · 01a1 · repo\n"
         "  ← for agents · ? for shortcuts\n")
PI = "─" * 40 + "\n~/agents\n↑11M ↓490k R322M CH93.2% $0.97 13.1%/1.0M (auto)    (openrouter) deepseek/v4 • high\n"


def test_each_harness_footer_gives_percent_used_and_window():
    assert cu.parse("claude", CLAUDE) == {"percent": 6.0, "window": None}
    assert cu.parse("codex", CODEX) == {"percent": 55.0, "window": None}
    assert cu.parse("pi", PI) == {"percent": 13.1, "window": "1.0M"}
    assert cu.parse("pi", "↑16k ↓1.5k 7.1%/131k (auto)  local/model\n") == {"percent": 7.1, "window": "131K"}


def test_codex_older_context_left_wording_becomes_percent_used():
    assert cu.parse("codex", "  GPT-6 medium · ~/r · 41% context left\n") == {"percent": 59.0, "window": None}


def test_pi_unknown_percent_keeps_the_window():
    assert cu.parse("pi", "↑1k ↓1k ?/131k (auto)  local/model\n") == {"percent": None, "window": "131K"}


def test_no_figure_when_the_screen_has_none_or_the_harness_does_not_print_one():
    assert cu.parse("claude", "❯ \n  /home/x/repo\n  ⏵⏵ auto mode on\n") is None
    assert cu.parse("agy", "? for shortcuts        Gemini 4 Neon · high\n") is None
    assert cu.parse("codex", None) is None and cu.parse(None, CLAUDE) is None and cu.parse("claude", "") is None


def test_a_figure_in_the_conversation_does_not_count():
    talk = "I said ctx:99% and Context 98% used\n" + "\n".join(f"line {i}" for i in range(12)) + "\n"
    assert cu.parse("claude", talk) is None and cu.parse("codex", talk) is None
    # Another harness's pattern is ignored, too.
    assert cu.parse("codex", CLAUDE) is None and cu.parse("claude", CODEX) is None


def test_impossible_percentages_are_dropped():
    assert cu.parse("claude", "[Opus 5.5 | ctx:140%]\n") is None
    assert cu.parse("codex", "Context 120% used\n") is None
