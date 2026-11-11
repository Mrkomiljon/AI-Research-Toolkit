"""`rtk setup` and `rtk doctor`: get a researcher from `pip install` to a working agent without Node.js or a git clone.

The wheel carries a copy of the canonical `skills/` tree (`research_toolkit/_skills`, added at build time by setup.py);
in a source checkout the repository's `skills/` directory is used directly.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from . import SKILL_NAMES, __version__

MARKER = ".ai-research-toolkit-installed.json"
AGENT_DIRS = {
    "claude": {"project": Path(".claude") / "skills", "user": Path.home() / ".claude" / "skills"},
    "codex": {"project": Path(".agents") / "skills", "user": Path.home() / ".codex" / "skills"},
}
AGENT_LABEL = {"claude": "Claude Code", "codex": "Codex"}


def skills_source() -> Path | None:
    here = Path(__file__).resolve().parent
    for cand in (here / "_skills", here.parent / "skills"):
        if (cand / "research-orchestrator" / "SKILL.md").exists():
            return cand
    return None


def _digest(skill_dir: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(skill_dir.rglob("*")):
        if p.is_file() and p.name != MARKER:
            h.update(p.relative_to(skill_dir).as_posix().encode())
            h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def _dest_root(agent: str, scope: str, project_dir: Path) -> Path:
    base = AGENT_DIRS[agent][scope]
    return (project_dir.resolve() / base) if scope == "project" else base


def install_skills(agents: list[str], *, scope: str = "project", project_dir: Path | str = ".", force: bool = False) -> dict[str, Any]:
    """Copy the bundled skills into the agent directories. Skills the user made or changed are never replaced silently."""
    src = skills_source()
    if src is None:
        raise FileNotFoundError("bundled skills not found; reinstall the package: python -m pip install -U ai-research-toolkit")
    results: list[dict[str, str]] = []
    for agent in agents:
        root = _dest_root(agent, scope, Path(project_dir))
        root.mkdir(parents=True, exist_ok=True)
        for name in SKILL_NAMES:
            dest = root / name
            action = "installed"
            if dest.is_symlink():
                dest.unlink()
                action = "updated"
            elif dest.exists():
                same = dest.is_dir() and _digest(dest) == _digest(src / name)
                ours = dest.is_dir() and (dest / MARKER).exists()
                if same:
                    results.append({"agent": agent, "skill": name, "action": "up to date", "path": str(dest)})
                    continue
                # A copy we made carries a marker with the digest we wrote; a different digest now means the user edited it.
                edited = False
                if ours:
                    try:
                        edited = json.loads((dest / MARKER).read_text(encoding="utf-8")).get("digest") not in (None, _digest(dest))
                    except ValueError:
                        edited = True
                if (not ours or edited) and not force:
                    results.append({"agent": agent, "skill": name, "action": "kept (modified or not installed by rtk; use --force to replace)", "path": str(dest)})
                    continue
                shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
                action = "updated"
            shutil.copytree(src / name, dest)
            (dest / MARKER).write_text(json.dumps({"source": "rtk setup", "version": __version__, "mode": "copy", "digest": _digest(dest)}), encoding="utf-8")
            results.append({"agent": agent, "skill": name, "action": action, "path": str(dest)})
    counts: dict[str, int] = {}
    for r in results:
        key = r["action"].split(" (")[0]
        counts[key] = counts.get(key, 0) + 1
    return {"version": __version__, "scope": scope, "targets": {a: str(_dest_root(a, scope, Path(project_dir))) for a in agents},
            "counts": counts, "kept": [r for r in results if r["action"].startswith("kept")], "results": results}


def skills_state(root: Path) -> dict[str, Any]:
    """How the skills under one agent directory compare with the ones this engine version ships."""
    src = skills_source()
    missing, outdated, ok = [], [], []
    for name in SKILL_NAMES:
        d = root / name
        if not (d / "SKILL.md").exists():
            missing.append(name)
        elif src is not None and _digest(d) != _digest(src / name):
            outdated.append(name)
        else:
            ok.append(name)
    return {"path": str(root), "installed": len(ok) + len(outdated), "missing": missing, "outdated": outdated}


def doctor(project_dir: Path | str = ".", *, check_network: bool = True) -> dict[str, Any]:
    """Checks a researcher can act on. level: ok | warn (works, with a limitation) | fail (will not work)."""
    checks: list[dict[str, str]] = []

    def add(level: str, name: str, detail: str, fix: str | None = None) -> None:
        checks.append({"level": level, "check": name, "detail": detail, **({"fix": fix} if fix else {})})

    v = sys.version_info
    add("ok" if v >= (3, 11) else "fail", "Python", f"{v.major}.{v.minor}.{v.micro}", None if v >= (3, 11) else "install Python 3.11 or newer")
    add("ok", "engine", f"ai-research-toolkit {__version__}")
    on_path = shutil.which("rtk")
    add("ok" if on_path else "warn", "rtk on PATH", on_path or "not found",
        None if on_path else "the skills call `rtk`; add Python's Scripts folder to PATH, or reinstall with: python -m pip install -U ai-research-toolkit")
    src = skills_source()
    add("ok" if src else "fail", "bundled skills", str(src) if src else "missing", None if src else "python -m pip install -U --force-reinstall ai-research-toolkit")
    project = Path(project_dir).resolve()
    found_any = False
    for agent in ("claude", "codex"):
        states = [(scope, skills_state(_dest_root(agent, scope, project))) for scope in ("project", "user")]
        best = max(states, key=lambda s: s[1]["installed"])
        scope, st = best
        if st["installed"] == 0:
            add("warn", f"{AGENT_LABEL[agent]} skills", "not installed in this folder or user-wide")
            continue
        found_any = True
        if st["missing"] or st["outdated"]:
            add("warn", f"{AGENT_LABEL[agent]} skills", f"{st['installed']} of {len(SKILL_NAMES)} in {st['path']}; missing: {', '.join(st['missing']) or 'none'}; "
                f"differ from engine {__version__}: {', '.join(st['outdated']) or 'none'}", f"rtk setup --agent {agent}" + (" --scope user" if scope == "user" else ""))
        else:
            add("ok", f"{AGENT_LABEL[agent]} skills", f"{len(SKILL_NAMES)} of {len(SKILL_NAMES)}, match engine {__version__} ({st['path']})")
    if not found_any:
        add("fail", "skills for an agent", "no skills found for Claude Code or Codex", "run `rtk setup` in your research folder")
    for agent, exe in (("claude", "claude"), ("codex", "codex")):
        add("ok" if shutil.which(exe) else "warn", f"{AGENT_LABEL[agent]} CLI", shutil.which(exe) or "not on PATH (fine if you use the desktop app or IDE extension, or the other agent)")
    from . import ocr

    st = ocr.status()
    add("ok" if st["selected"] else "warn", "OCR for scanned PDFs", f"backend: {st['selected']}" if st["selected"] else "no backend; scanned pages will be reported as unread",
        None if st["selected"] else 'optional: python -m pip install "ai-research-toolkit[ocr]"')
    add("ok" if os.environ.get("RTK_CONTACT_EMAIL") else "warn", "RTK_CONTACT_EMAIL", "set" if os.environ.get("RTK_CONTACT_EMAIL") else "not set; Unpaywall lookups are skipped",
        None if os.environ.get("RTK_CONTACT_EMAIL") else "optional: set RTK_CONTACT_EMAIL to your e-mail to find more open-access PDFs")
    if os.environ.get("RTK_ALLOW_EXTERNAL_APIS", "1") in ("0", "false", "False"):
        add("ok", "scholarly APIs", "disabled by RTK_ALLOW_EXTERNAL_APIS=0 (privacy mode)")
    elif check_network:
        import httpx

        for name, url in (("OpenAlex", "https://api.openalex.org/works?search=test&per-page=1"), ("Crossref", "https://api.crossref.org/works?query=test&rows=1")):
            try:
                r = httpx.get(url, timeout=10, headers={"User-Agent": f"ai-research-toolkit/{__version__} doctor"})
                note = " (rate limited right now; searches will work again shortly)" if r.status_code == 429 else ""
                add("ok" if r.status_code == 200 else "warn", f"{name} reachable", f"HTTP {r.status_code}{note}")
            except httpx.HTTPError as exc:
                add("warn", f"{name} reachable", f"{type(exc).__name__}", "check the internet connection; local steps still work offline")
    ws = [p.parent for p in list(project.glob("project.yaml")) + list(project.glob("workspace/*/project.yaml"))]
    add("ok", "research workspace", ", ".join(str(p) for p in ws[:3]) if ws else 'none yet; ask the agent: "Use research-orchestrator. Initialize my research on <topic>"')
    worst = "fail" if any(c["level"] == "fail" for c in checks) else ("warn" if any(c["level"] == "warn" for c in checks) else "ok")
    return {"result": worst, "ready": worst != "fail", "checks": checks}


def render_doctor(report: dict[str, Any]) -> str:
    mark = {"ok": "[ OK ]", "warn": "[warn]", "fail": "[FAIL]"}
    lines = []
    for c in report["checks"]:
        lines.append(f"{mark[c['level']]} {c['check']}: {c['detail']}")
        if c.get("fix"):
            lines.append(f"       -> {c['fix']}")
    lines.append("")
    lines.append({"ok": "Ready.", "warn": "Ready, with the limitations marked [warn].", "fail": "Not ready: fix the [FAIL] lines first."}[report["result"]])
    return "\n".join(lines)


def render_setup(res: dict[str, Any], agents: list[str]) -> str:
    lines = [f"AI Research Toolkit {res['version']}: skills installed"]
    for agent in agents:
        lines.append(f"  {AGENT_LABEL[agent]}: {res['targets'][agent]}")
    lines.append("  " + ", ".join(f"{n} {k}" for k, n in res["counts"].items()))
    for r in res["kept"]:
        lines.append(f"  kept {r['path']} ({r['action']})")
    opener = " or ".join(f"`{'claude' if a == 'claude' else 'codex'}`" for a in agents)
    where = "this folder" if res["scope"] == "project" else "any folder"
    lines += ["", "Next:", f"  1. Open your agent in {where}: {opener} (or the desktop app / IDE extension).",
              "  2. Type, in your own language:",
              '       Use research-orchestrator. Initialize my research on <your topic>.',
              "     then, for example:",
              '       Find 20 papers since 2021.   |   2021 yildan beri 20 ta maqola top.',
              '       Check whether my sources support my claims.   |   Qo\'lyozmadagi da\'volarni tekshir.',
              "  3. `rtk doctor` checks the installation at any time."]
    return "\n".join(lines)
