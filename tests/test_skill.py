"""The shared agent-swarm-register skill and its installer."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SKILLS = Path(__file__).parents[1] / "skills"
SKILL = SKILLS / "agent-swarm-register"


def test_one_skill_in_agent_skills_format():
    front = (SKILL / "SKILL.md").read_text().split("---")[1]
    assert "name: agent-swarm-register" in front
    assert "description: " in front
    # Only fields every harness reads; the skill must load in all three.
    keys = {line.split(":")[0] for line in front.strip().splitlines()}
    assert keys == {"name", "description"}
    assert sorted(p.name for p in SKILLS.iterdir()) == ["agent-swarm-register", "install"]


def test_skill_tells_agents_not_to_pass_flavor():
    text = (SKILL / "SKILL.md").read_text()
    assert "buzz register" in text
    assert "Do not pass `--flavor`" in text


def _install(home: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k not in ("CODEX_HOME", "PI_CODING_AGENT_DIR")}
    subprocess.run([str(SKILLS / "install")], check=True, capture_output=True, env=env | {"HOME": str(home)})


def test_install_links_the_skill_where_each_harness_looks(tmp_path):
    _install(tmp_path)
    for dest_dir in (".agents/skills", ".claude/skills"):
        dest = tmp_path / dest_dir / "agent-swarm-register"
        assert dest.is_symlink() and dest.resolve() == SKILL.resolve()


def test_install_moves_old_copies_out_and_drops_old_links(tmp_path):
    (tmp_path / ".claude/skills/agent-swarm-register").mkdir(parents=True)
    for old in (".codex/skills", ".pi/agent/skills"):
        (tmp_path / old).mkdir(parents=True)
        (tmp_path / old / "agent-swarm-register").symlink_to(SKILLS / "codex/agent-swarm-register")
    (tmp_path / ".codex/skills/someone-elses").symlink_to("/elsewhere")
    _install(tmp_path)
    # One copy per scanned directory, so no harness loads the skill twice.
    assert [p.name for p in (tmp_path / ".claude/skills").iterdir()] == ["agent-swarm-register"]
    assert list(tmp_path.glob(".claude/skills.bak-*/agent-swarm-register"))
    assert [p.name for p in (tmp_path / ".codex/skills").iterdir()] == ["someone-elses"]
    assert list((tmp_path / ".pi/agent/skills").iterdir()) == []
