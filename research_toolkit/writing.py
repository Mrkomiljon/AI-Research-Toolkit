"""academic-writing engine half: deterministic prose metrics, flagged sentences, fact-preservation comparison."""
from __future__ import annotations

import re
from typing import Any

from .exporters import read_text_any, write_markdown
from .pipelines import ID_REF_RE, PLACEHOLDER_RE
from .project_manager import ProjectManager
from .schemas import AuthorReviewStatus, ValidationStatus

LONG_SENTENCE_WORDS = 35
LONG_PARAGRAPH_WORDS = 220
PASSIVE_RE = re.compile(r"\b(is|are|was|were|be|been|being)\s+(\w+ed|\w+en|shown|given|made|done|found|seen|taken)\b", re.IGNORECASE)
HEDGE_WORDS = ("may", "might", "could", "possibly", "perhaps", "seems", "appears", "suggest", "suggests", "likely", "potentially", "arguably")
ACRONYM_RE = re.compile(r"\b[A-Z]{2,6}s?\b")
DEFINED_ACRONYM_RE = re.compile(r"\(([A-Z]{2,6}s?)\)")
NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?%?(?![\w.])")
CITE_RE = re.compile(r"\\cite[tp]?\*?\{[^}]+\}|\[@[^\]]+\]|\(([A-Z][A-Za-z\-']+)(?: et al\.)?,? \d{4}[a-z]?\)")
ACRONYM_STOPLIST = {"IMRAD", "DOI", "USA", "UK", "AI", "ML", "CI", "OR", "CNN", "AUC", "AUROC", "PDF", "ID", "IDS", "MISSING", "TODO", "AUTHOR", "INPUT", "NEEDED"}


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\[\(])", text)
    return [p.strip() for p in parts if len(p.strip()) > 2]


def _sections(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    cur, buf = "(preamble)", []
    for line in text.splitlines():
        if line.startswith("#"):
            out.append((cur, "\n".join(buf)))
            cur, buf = line.lstrip("#").strip(), []
        else:
            buf.append(line)
    out.append((cur, "\n".join(buf)))
    return [(h, b) for h, b in out if b.strip()]


def measure(text: str) -> dict[str, Any]:
    body = "\n".join(ln for ln in text.splitlines() if not ln.startswith(">"))
    sections = _sections(body)
    flagged: list[dict[str, str]] = []
    total_words = total_sent = passive = hedges = 0
    defined = set(DEFINED_ACRONYM_RE.findall(body))
    seen_acronyms: dict[str, str] = {}
    for head, sec_text in sections:
        paragraphs = [p for p in re.split(r"\n\s*\n", sec_text) if p.strip() and not p.strip().startswith(("|", "-", "*", "1.", "```"))]
        for para in paragraphs:
            words = len(para.split())
            if words > LONG_PARAGRAPH_WORDS:
                flagged.append({"section": head, "type": "long_paragraph", "text": f"{words} words: {para[:80]}…"})
            for s in _sentences(para):
                n = len(s.split())
                total_words += n
                total_sent += 1
                if n > LONG_SENTENCE_WORDS:
                    flagged.append({"section": head, "type": "long_sentence", "text": f"{n} words: {s[:110]}…"})
                if PASSIVE_RE.search(s):
                    passive += 1
                h = sum(1 for w in re.findall(r"[a-z']+", s.lower()) if w in HEDGE_WORDS)
                hedges += h
                if h >= 2:
                    flagged.append({"section": head, "type": "stacked_hedges", "text": s[:110]})
                for ac in ACRONYM_RE.findall(s):
                    base = ac.rstrip("s")
                    if base in ACRONYM_STOPLIST or len(base) < 2:
                        continue
                    if base not in seen_acronyms:
                        seen_acronyms[base] = head
                        if base not in defined and not re.search(rf"\({re.escape(base)}s?\)", body):
                            flagged.append({"section": head, "type": "acronym_undefined", "text": f"{base} first used here without definition"})
    placeholders = PLACEHOLDER_RE.findall(text)
    return {
        "sections": [h for h, _ in sections],
        "words": total_words,
        "sentences": total_sent,
        "avg_sentence_words": round(total_words / total_sent, 1) if total_sent else 0,
        "passive_sentences": passive,
        "passive_ratio": round(passive / total_sent, 3) if total_sent else 0,
        "hedge_words": hedges,
        "placeholders": len(placeholders),
        "citations": len(CITE_RE.findall(text)) + len(ID_REF_RE.findall(text)),
        "flagged": flagged,
    }


def compare_facts(original: str, edited: str) -> dict[str, list[str]]:
    """Facts that must survive editing: source/evidence ids, numbers, LaTeX/pandoc citations, placeholders."""
    def facts(t: str) -> dict[str, set[str]]:
        return {
            "ids": set(ID_REF_RE.findall(t)),
            "numbers": set(NUMBER_RE.findall(t)),
            "citations": {m.group(0) for m in CITE_RE.finditer(t)},
            "placeholders": set(PLACEHOLDER_RE.findall(t)),
        }
    a, b = facts(original), facts(edited)
    return {
        "ids_removed": sorted(a["ids"] - b["ids"]), "ids_added": sorted(b["ids"] - a["ids"]),
        "numbers_removed": sorted(a["numbers"] - b["numbers"]), "numbers_added": sorted(b["numbers"] - a["numbers"]),
        "citations_removed": sorted(a["citations"] - b["citations"]), "citations_added": sorted(b["citations"] - a["citations"]),
        "placeholders_removed": sorted(a["placeholders"] - b["placeholders"]),
    }


STYLE_CHECKLIST = [
    "Title states the question/finding, no undefined abbreviations",
    "Abstract follows the journal format and contains no information absent from the main text",
    "Each paragraph has one topic sentence and one idea",
    "Methods written so another group could repeat the study",
    "Results report numbers with units, CIs/uncertainty and the test used; no interpretation",
    "Discussion separates findings, comparison with literature, limitations, implications",
    "Tense: past for what was done/found, present for established facts and figure references",
    "Voice: active where the actor matters; consistent within sections",
    "Acronyms defined at first use; terminology consistent (one term per concept)",
    "Hedging matches evidence strength; no hedges on measured results",
    "Sentences mostly under 30 words; no stacked subordinate clauses",
    "Numbers, citations and claims unchanged by editing (see fact comparison)",
    "British or American spelling consistent with the journal",
    "All [MISSING]/[AUTHOR INPUT NEEDED] placeholders resolved before submission",
]


def check_writing(pm: ProjectManager, rel_path: str, *, compare_with: str | None = None, run_id=None, step_id=None) -> dict[str, Any]:
    text = read_text_any(pm.resolve(rel_path))
    if not text.strip():
        raise ValueError(f"{rel_path} is empty")
    m = measure(text)
    sections: list[tuple[str, str]] = [
        ("File", f"`{rel_path}`"),
        ("Metrics", "\n".join([
            f"- Words: {m['words']}; sentences: {m['sentences']}; average sentence length: {m['avg_sentence_words']} words",
            f"- Passive constructions: {m['passive_sentences']} ({m['passive_ratio'] * 100:.0f}% of sentences; heuristic)",
            f"- Hedge words: {m['hedge_words']}",
            f"- Citations/ids found: {m['citations']}; placeholders left: {m['placeholders']}",
            f"- Sections detected: {', '.join(m['sections']) or 'none'}",
        ])),
        ("Flagged passages", "\n".join(f"- **{f['type']}** [{f['section']}]: {f['text']}" for f in m["flagged"]) or "- none"),
    ]
    cmp = None
    if compare_with:
        cmp = compare_facts(read_text_any(pm.resolve(compare_with)), text)
        diffs = {k: v for k, v in cmp.items() if v}
        sections.append(("Fact preservation vs " + compare_with,
                         "\n".join(f"- {k}: {', '.join(v)}" for k, v in diffs.items()) if diffs else "- no ids, numbers, citations or placeholders changed"))
    sections.append(("Edits", "_Editor lists each substantive change here as `original → edited (reason)`._"))
    sections.append(("Scope", "Heuristic metrics (regex-based); they guide editing and never judge scientific content. Facts, numbers, citations and claims must not change."))
    report = write_markdown(pm.workspace / "manuscript" / "writing-report.md", "Writing report", sections,
                            front_note="Generated by academic-writing (engine metrics). Editing itself is done by the agent and reviewed by the author.")
    checklist_path = pm.workspace / "manuscript" / "style-checklist.md"
    if not checklist_path.exists():
        write_markdown(checklist_path, "Style checklist", [("Checklist", "\n".join(f"- [ ] {item}" for item in STYLE_CHECKLIST))])
    for p in (report, checklist_path):
        pm.register_artifact(p, skill="academic-writing", run_id=run_id, step_id=step_id, validation_status=ValidationStatus.VALID,
                             author_review=AuthorReviewStatus.PENDING)
    return {"metrics": {k: v for k, v in m.items() if k != "flagged"}, "flagged": len(m["flagged"]), "fact_comparison": cmp,
            "artifacts": [str(report), str(checklist_path)]}


__all__ = ["measure", "compare_facts", "check_writing", "STYLE_CHECKLIST"]
