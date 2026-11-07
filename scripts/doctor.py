#!/usr/bin/env python3
"""Environment check: Python, dependencies, rtk entry point, skill manifests, agent directories, API reachability."""
from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

CHECKS_OK = True


def report(ok: bool, label: str, detail: str = "") -> None:
    global CHECKS_OK
    CHECKS_OK &= ok
    print(f"[{'OK' if ok else '!!'}] {label}" + (f" - {detail}" if detail else ""))


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to legacy code pages
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    v = sys.version_info
    report(v >= (3, 11), "Python >= 3.11", f"{v.major}.{v.minor}.{v.micro}")
    for mod, pkg in [("pydantic", "pydantic"), ("yaml", "PyYAML"), ("httpx", "httpx"), ("pandas", "pandas"), ("openpyxl", "openpyxl"),
                     ("docx", "python-docx"), ("pymupdf", "pymupdf"), ("jinja2", "jinja2"), ("pytest", "pytest")]:
        try:
            m = importlib.import_module(mod)
            report(True, f"dependency {pkg}", getattr(m, "__version__", ""))
        except ImportError:
            report(False, f"dependency {pkg}", "missing: python -m pip install -r requirements.txt")
    try:
        import research_toolkit

        report(True, "research_toolkit importable", research_toolkit.__version__)
    except ImportError as exc:
        report(False, "research_toolkit importable", f"{exc}; run: python -m pip install -e .")
    rtk = shutil.which("rtk")
    report(rtk is not None, "rtk on PATH", rtk or "run: python -m pip install -e . (or use: python -m research_toolkit)")
    try:
        out = subprocess.run([sys.executable, "-m", "research_toolkit", "validate-skills", "--skills-dir", str(REPO / "skills")],
                             capture_output=True, text=True, timeout=60)
        report(out.returncode == 0, "10 skill manifests valid", "" if out.returncode == 0 else out.stdout[-400:])
    except Exception as exc:  # noqa: BLE001
        report(False, "skill manifest validation", str(exc))
    for agent, rel in (("claude", ".claude/skills"), ("codex", ".agents/skills")):
        p = Path.cwd() / rel
        found = sorted(d.name for d in p.iterdir()) if p.exists() else []
        report(bool(found), f"{agent} project skills dir ({rel})", f"{len(found)} installed" if found else f"not installed here (python scripts/install.py --agent {agent})")
    report(shutil.which("node") is not None, "Node.js (optional, for `npx skills add`)", shutil.which("node") or "not found; manual installer still works")
    if os.environ.get("RTK_ALLOW_EXTERNAL_APIS", "1") in ("0", "false"):
        report(True, "external APIs", "disabled by RTK_ALLOW_EXTERNAL_APIS=0 (privacy mode)")
    else:
        try:
            import httpx

            r = httpx.get("https://api.openalex.org/works?search=test&per-page=1", timeout=10)
            report(r.status_code == 200, "OpenAlex reachable", f"HTTP {r.status_code}")
            r = httpx.get("https://api.crossref.org/works?query=test&rows=1", timeout=10, headers={"User-Agent": "ai-research-toolkit-doctor"})
            report(r.status_code == 200, "Crossref reachable", f"HTTP {r.status_code}")
        except Exception as exc:  # noqa: BLE001
            report(False, "scholarly APIs reachable", f"{type(exc).__name__}: {exc} (offline mode still works for local steps)")
    report(True, "pandoc (optional)", shutil.which("pandoc") or "not found; DOCX export uses python-docx, no pandoc needed")
    print("\nRESULT:", "all checks passed" if CHECKS_OK else "some checks failed (see !! lines)")
    return 0 if CHECKS_OK else 1


if __name__ == "__main__":
    sys.exit(main())
