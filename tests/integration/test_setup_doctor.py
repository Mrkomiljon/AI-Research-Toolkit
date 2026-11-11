"""1.4.1: `rtk setup` (skills without Node.js or a clone) and `rtk doctor`."""
import json
from pathlib import Path

import pytest

from research_toolkit import SKILL_NAMES, installer
from research_toolkit.cli import main as rtk
from research_toolkit.validation import validate_skills_tree


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Keep the real ~/.claude and ~/.codex out of the tests."""
    fake = tmp_path / "home"
    dirs = {"claude": {"project": Path(".claude") / "skills", "user": fake / ".claude" / "skills"},
            "codex": {"project": Path(".agents") / "skills", "user": fake / ".codex" / "skills"}}
    monkeypatch.setattr(installer, "AGENT_DIRS", dirs)
    monkeypatch.delenv("RTK_CONTACT_EMAIL", raising=False)
    return fake


def test_setup_installs_updates_and_never_overwrites_user_changes(tmp_path, home):
    proj = tmp_path / "research"
    proj.mkdir()
    res = installer.install_skills(["claude", "codex"], project_dir=proj)
    assert res["counts"] == {"installed": 30} and not res["kept"]
    for rel in (".claude/skills", ".agents/skills"):
        assert sorted(p.name for p in (proj / rel).iterdir()) == sorted(SKILL_NAMES)
        assert all(not errs for errs in validate_skills_tree(proj / rel).values())
        assert (proj / rel / "research-orchestrator" / "references" / "routing-table.md").exists()
    assert installer.install_skills(["claude"], project_dir=proj)["counts"] == {"up to date": 15}
    # the user edits one skill and adds their own: both survive an update
    edited = proj / ".claude" / "skills" / "paper-analyzer" / "SKILL.md"
    edited.write_text(edited.read_text(encoding="utf-8") + "\nMy lab's extra rule.\n", encoding="utf-8")
    mine = proj / ".claude" / "skills" / "my-own-skill"
    mine.mkdir()
    (mine / "SKILL.md").write_text("---\nname: my-own-skill\ndescription: mine\n---\n", encoding="utf-8")
    res = installer.install_skills(["claude"], project_dir=proj)
    assert res["counts"] == {"up to date": 14, "kept": 1} and "My lab's extra rule" in edited.read_text(encoding="utf-8")
    state = installer.skills_state(proj / ".claude" / "skills")
    assert state["outdated"] == ["paper-analyzer"] and state["missing"] == [] and state["installed"] == 15
    res = installer.install_skills(["claude"], project_dir=proj, force=True)
    assert res["counts"] == {"up to date": 14, "updated": 1} and "My lab's extra rule" not in edited.read_text(encoding="utf-8")
    assert mine.exists()
    # a skill installed by another tool (no marker) is kept unless it is identical or --force is given
    foreign = proj / ".agents" / "skills" / "gap-validator"
    (foreign / installer.MARKER).unlink()
    (foreign / "SKILL.md").write_text("---\nname: gap-validator\ndescription: old copy\n---\nrtk gaps\n", encoding="utf-8")
    assert installer.install_skills(["codex"], project_dir=proj)["counts"] == {"up to date": 14, "kept": 1}
    # user scope goes to the home directories
    installer.install_skills(["codex"], scope="user")
    assert len(list((home / ".codex" / "skills").iterdir())) == 15


def test_doctor_reports_actionable_state(tmp_path, home, monkeypatch):
    proj = tmp_path / "research"
    proj.mkdir()
    rep = installer.doctor(proj, check_network=False)
    by = {c["check"]: c for c in rep["checks"]}
    assert rep["result"] == "fail" and not rep["ready"] and by["skills for an agent"]["fix"].startswith("run `rtk setup`")
    installer.install_skills(["claude"], project_dir=proj)
    rep = installer.doctor(proj, check_network=False)
    by = {c["check"]: c for c in rep["checks"]}
    assert rep["ready"] and by["Claude Code skills"]["level"] == "ok" and by["Codex skills"]["level"] == "warn"
    assert "OpenAlex reachable" not in by  # --offline skips the network
    # after an engine upgrade the installed skills lag behind: doctor says which and how to fix it
    (proj / ".claude" / "skills" / "claim-verifier" / "SKILL.md").write_text("---\nname: claim-verifier\ndescription: old\n---\nrtk claims\n", encoding="utf-8")
    import shutil

    shutil.rmtree(proj / ".claude" / "skills" / "gap-validator")
    by = {c["check"]: c for c in installer.doctor(proj, check_network=False)["checks"]}
    c = by["Claude Code skills"]
    assert c["level"] == "warn" and "missing: gap-validator" in c["detail"] and "claim-verifier" in c["detail"] and c["fix"] == "rtk setup --agent claude"
    text = installer.render_doctor(installer.doctor(proj, check_network=False))
    assert "[warn] Claude Code skills" in text and "-> rtk setup --agent claude" in text and text.endswith("limitations marked [warn].")
    monkeypatch.setenv("RTK_ALLOW_EXTERNAL_APIS", "0")
    by = {c["check"]: c for c in installer.doctor(proj)["checks"]}
    assert "privacy mode" in by["scholarly APIs"]["detail"]


def test_cli_setup_and_doctor(tmp_path, home, capsys):
    proj = tmp_path / "research"
    proj.mkdir()
    rtk(["setup", "--dir", str(proj)])
    out = capsys.readouterr().out
    assert "30 installed" in out and "Use research-orchestrator. Initialize my research on <your topic>." in out and "rtk doctor" in out
    rtk(["--json", "setup", "--dir", str(proj), "--agent", "codex"])
    assert json.loads(capsys.readouterr().out)["counts"] == {"up to date": 15}
    with pytest.raises(SystemExit) as exc:
        rtk(["--json", "doctor", "--dir", str(proj), "--offline"])
    assert exc.value.code == 0 and json.loads(capsys.readouterr().out)["ready"] is True
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SystemExit) as exc:
        rtk(["doctor", "--dir", str(empty), "--offline"])
    assert exc.value.code == 1 and "Not ready" in capsys.readouterr().out
