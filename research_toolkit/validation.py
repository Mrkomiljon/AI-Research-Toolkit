"""Deterministic checks: DOI format, prompt-injection scanning, artifact presence, skill manifests."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import SKILL_NAMES
from .schemas import DOI_RE, normalize_doi, normalize_title

# Patterns that indicate instructions aimed at an AI agent inside a document. Findings are reported as DATA.
INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore (all )?(the )?(previous|prior|above) (instructions|prompts?)",
        r"disregard (your|the) (system|previous) (prompt|instructions)",
        r"you are now (an?|the) ",
        r"\bsystem prompt\b",
        r"\bas an ai (assistant|model|agent)\b.*\b(must|should|will)\b",
        r"\b(assistant|agent|claude|codex|gpt)\b.*\b(must|should) (now )?(run|execute|delete|send|upload|email)\b",
        r"\b(run|execute) the following (command|code|script)\b",
        r"\brm -rf\b|\bdel /s\b|\bformat c:",
        r"\bcurl\s+-[a-z]*\s*https?://|\bwget\s+https?://",
        r"\bmark (this|the) (paper|step|task) as (complete|verified|done)\b",
        r"\bskip (the )?(verification|validation|approval)\b",
        r"\bsend (this|the) (file|document|data) to\b",
        r"<\s*/?\s*(system|instruction|prompt)\s*>",
    )
]


@dataclass
class InjectionFinding:
    pattern: str
    locator: str
    snippet: str


def scan_for_injection(text: str, locator: str = "document") -> list[InjectionFinding]:
    """Return suspicious instruction-like passages. Never acts on them; the caller logs them as data."""
    findings: list[InjectionFinding] = []
    for pat in INJECTION_PATTERNS:
        for m in pat.finditer(text):
            start = max(0, m.start() - 60)
            snippet = text[start : m.end() + 60].replace("\n", " ")
            findings.append(InjectionFinding(pattern=pat.pattern, locator=locator, snippet=snippet))
    return findings


def check_doi_format(doi: str | None) -> tuple[bool, str]:
    d = normalize_doi(doi)
    if not d:
        return False, "missing DOI"
    if not DOI_RE.match(d):
        return False, f"malformed DOI {d!r}"
    return True, "format ok"


def titles_match(a: str, b: str, threshold: float = 0.85) -> tuple[bool, float]:
    ratio = difflib.SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()
    return ratio >= threshold, round(ratio, 3)


@dataclass
class ArtifactCheck:
    expected: list[str]
    present: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    empty: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.empty


def check_artifacts(workspace: Path, expected: list[str], search_dirs: list[str] | None = None) -> ArtifactCheck:
    """Expected artifact file names must exist (anywhere under the given dirs) and be non-empty."""
    ws = Path(workspace)
    dirs = [ws / d for d in (search_dirs or ["literature", "analysis", "manuscript", "reviews", "progress", "sources", "exports"])]
    result = ArtifactCheck(expected=list(expected))
    for name in expected:
        hits = [p for d in dirs if d.exists() for p in d.rglob(name)]
        direct = ws / name
        if direct.exists():
            hits.append(direct)
        if not hits:
            result.missing.append(name)
        elif all(p.stat().st_size == 0 for p in hits):
            result.empty.append(name)
        else:
            result.present.append(name)
    return result


# ---- skill manifest validation (Agent Skills spec) --------------------
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def validate_skill_dir(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    md = skill_dir / "SKILL.md"
    if not md.exists():
        return [f"{skill_dir.name}: SKILL.md missing"]
    text = md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return [f"{skill_dir.name}: YAML frontmatter missing"]
    parts = text.split("---", 2)
    if len(parts) < 3:
        return [f"{skill_dir.name}: frontmatter not closed"]
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        return [f"{skill_dir.name}: invalid YAML frontmatter: {exc}"]
    name = fm.get("name")
    desc = fm.get("description")
    if not name or not SKILL_NAME_RE.match(str(name)) or len(str(name)) > 64:
        errors.append(f"{skill_dir.name}: name must be lowercase-hyphenated, <=64 chars")
    if name != skill_dir.name:
        errors.append(f"{skill_dir.name}: frontmatter name {name!r} must equal directory name")
    if not desc or not str(desc).strip():
        errors.append(f"{skill_dir.name}: description required")
    elif len(str(desc)) > 1024:
        errors.append(f"{skill_dir.name}: description exceeds 1024 chars")
    for key in fm:
        if key not in {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}:
            errors.append(f"{skill_dir.name}: unexpected frontmatter key {key!r}")
    body = parts[2]
    for ref in re.findall(r"\]\((references/[^)]+|scripts/[^)]+|assets/[^)]+)\)", body):
        if not (skill_dir / ref).exists():
            errors.append(f"{skill_dir.name}: referenced file missing: {ref}")
    return errors


def validate_skills_tree(skills_root: Path) -> dict[str, list[str]]:
    report: dict[str, list[str]] = {}
    for name in SKILL_NAMES:
        report[name] = validate_skill_dir(Path(skills_root) / name)
    return report
