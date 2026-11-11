#!/usr/bin/env python3
"""Install the canonical skills/ tree into agent-recognized directories.

  python scripts/install.py --agent claude --scope project      # -> ./.claude/skills/<skill>
  python scripts/install.py --agent codex  --scope project      # -> ./.agents/skills/<skill>
  python scripts/install.py --agent all    --scope user         # -> ~/.claude/skills and ~/.codex/skills
  python scripts/install.py --agent claude --uninstall

Default mode is a symlink (falls back to copying on Windows when symlinks are not permitted); --copy forces copies.
Existing directories that were not created by this installer are never overwritten (use --force to replace).
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS_SRC = REPO / "skills"
MARKER = ".ai-research-toolkit-installed.json"

AGENT_DIRS = {
    "claude": {"project": Path(".claude") / "skills", "user": Path.home() / ".claude" / "skills"},
    "codex": {"project": Path(".agents") / "skills", "user": Path.home() / ".codex" / "skills"},
}


def skill_dirs() -> list[Path]:
    return sorted(p for p in SKILLS_SRC.iterdir() if (p / "SKILL.md").exists())


def can_symlink(target_dir: Path) -> bool:
    if platform.system() != "Windows":
        return True
    probe = target_dir / ".symlink-probe"
    try:
        probe.symlink_to(SKILLS_SRC, target_is_directory=True)
        probe.unlink()
        return True
    except (OSError, NotImplementedError):
        return False


def install_one(src: Path, dest_root: Path, *, copy: bool, force: bool) -> str:
    dest = dest_root / src.name
    if dest.exists() or dest.is_symlink():
        marker = dest / MARKER if dest.is_dir() and not dest.is_symlink() else None
        ours = dest.is_symlink() or (marker is not None and marker.exists())
        if not ours and not force:
            return f"SKIP  {dest} exists and was not created by this installer (use --force)"
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    if copy:
        shutil.copytree(src, dest)
        (dest / MARKER).write_text(json.dumps({"source": str(src), "mode": "copy"}), encoding="utf-8")
        return f"COPY  {src.name} -> {dest}"
    dest.symlink_to(src, target_is_directory=True)
    return f"LINK  {src.name} -> {dest}"


def uninstall_one(name: str, dest_root: Path) -> str:
    dest = dest_root / name
    if dest.is_symlink():
        dest.unlink()
        return f"REMOVED link {dest}"
    if dest.is_dir() and (dest / MARKER).exists():
        shutil.rmtree(dest)
        return f"REMOVED copy {dest}"
    if dest.exists():
        return f"KEPT  {dest} (not installed by this tool)"
    return f"NONE  {dest}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", choices=["claude", "codex", "all"], default="all")
    ap.add_argument("--scope", choices=["project", "user"], default="project")
    ap.add_argument("--project-dir", default=".", help="project root for --scope project (default: current directory)")
    ap.add_argument("--copy", action="store_true", help="copy instead of symlink")
    ap.add_argument("--force", action="store_true", help="replace existing directories not created by this installer")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not SKILLS_SRC.exists():
        print(f"skills directory not found: {SKILLS_SRC}", file=sys.stderr)
        return 1
    agents = ["claude", "codex"] if a.agent == "all" else [a.agent]
    results = []
    for agent in agents:
        base = AGENT_DIRS[agent][a.scope]
        dest_root = (Path(a.project_dir).resolve() / base) if a.scope == "project" else base
        if a.dry_run:
            for s in skill_dirs():
                results.append(f"DRY   {s.name} -> {dest_root / s.name}")
            continue
        dest_root.mkdir(parents=True, exist_ok=True)
        if a.uninstall:
            results += [uninstall_one(s.name, dest_root) for s in skill_dirs()]
            continue
        copy = a.copy or not can_symlink(dest_root)
        if copy and not a.copy:
            results.append(f"NOTE  symlinks unavailable in {dest_root}; copying instead (re-run after updating the repo)")
        results += [install_one(s, dest_root, copy=copy, force=a.force) for s in skill_dirs()]
    print("\n".join(results))
    print(f"\n{len(skill_dirs())} skills processed for agent(s): {', '.join(agents)} (scope={a.scope})")
    print("The skills call the `rtk` engine: `python -m pip install ai-research-toolkit` (or `pip install -e .` in this repo), then check with `rtk doctor`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
