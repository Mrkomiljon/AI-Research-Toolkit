"""Acceptance test 9: both Claude Code and Codex see the same ten skills through their own directories.

The LLM part (natural-language invocation) cannot run in CI; what can be verified is that the installer produces
identical, spec-valid skill trees under .claude/skills and .agents/skills and that every SKILL.md only relies on the
`rtk` CLI (no vendor-specific slash commands).
"""
import re
import subprocess
import sys
from pathlib import Path

from research_toolkit import SKILL_NAMES
from research_toolkit.validation import validate_skills_tree

REPO = Path(__file__).resolve().parents[2]


def test_installer_creates_identical_trees_for_both_agents(tmp_path):
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "install.py"), "--agent", "all", "--scope", "project",
                          "--project-dir", str(tmp_path), "--copy"], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    claude = tmp_path / ".claude" / "skills"
    codex = tmp_path / ".agents" / "skills"
    assert sorted(p.name for p in claude.iterdir()) == sorted(SKILL_NAMES)
    assert sorted(p.name for p in codex.iterdir()) == sorted(SKILL_NAMES)
    for name in SKILL_NAMES:
        assert (claude / name / "SKILL.md").read_text(encoding="utf-8") == (codex / name / "SKILL.md").read_text(encoding="utf-8")
    assert all(not errs for errs in validate_skills_tree(claude).values())
    assert all(not errs for errs in validate_skills_tree(codex).values())
    # re-running is idempotent and uninstall only removes what it installed
    again = subprocess.run([sys.executable, str(REPO / "scripts" / "install.py"), "--agent", "claude", "--scope", "project",
                            "--project-dir", str(tmp_path), "--copy"], capture_output=True, text=True, timeout=120)
    assert again.returncode == 0 and "SKIP" not in again.stdout
    foreign = codex / "user-made-skill"
    foreign.mkdir()
    (foreign / "SKILL.md").write_text("---\nname: user-made-skill\ndescription: mine\n---\n", encoding="utf-8")
    un = subprocess.run([sys.executable, str(REPO / "scripts" / "install.py"), "--agent", "codex", "--scope", "project",
                         "--project-dir", str(tmp_path), "--uninstall"], capture_output=True, text=True, timeout=120)
    assert un.returncode == 0 and foreign.exists() and not (codex / "research-orchestrator").exists()


def test_skills_do_not_depend_on_vendor_slash_syntax():
    for name in SKILL_NAMES:
        text = (REPO / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        body = text.split("---", 2)[2]
        assert not re.search(r"(^|\s)/(plugin|skill|mcp)\b", body), f"{name} relies on vendor slash syntax"
        assert "rtk " in body, f"{name} must call the shared engine so both agents run the same workflow"


def test_canonical_tree_is_valid_and_complete():
    report = validate_skills_tree(REPO / "skills")
    assert set(report) == set(SKILL_NAMES) and all(not v for v in report.values()), report
