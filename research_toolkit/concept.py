"""research-concept-builder: Gap Canvas -> concept paper.

The canvas is a small JSON form. Literature fields must cite registered ids; design fields (methods, data, timeline)
belong to the author, so anything the agent drafted there is labelled unconfirmed and anything missing becomes an
explicit placeholder. The engine never fills a field on its own.
"""
from __future__ import annotations

from typing import Any

from .evidence_store import EvidenceStore
from .exporters import read_json, write_docx, write_json, write_markdown
from .pipelines import ID_REF_RE, NOVELTY_RE, PLACEHOLDER_RE, StepBlocked
from .project_manager import ApprovalRequired, ProjectManager
from .schemas import AuthorReviewStatus, ValidationStatus, utcnow
from .source_registry import SourceRegistry

CANVAS_PATH = "manuscript/gap-canvas.json"

# name, heading, needs registered ids, author-owned (agent drafts are flagged), optional
CANVAS_FIELDS: list[tuple[str, str, bool, bool, bool]] = [
    ("problem", "Background and problem", False, False, False),
    ("known", "What is already known", True, False, False),
    ("gap", "Research gap", True, False, False),
    ("research_question", "Research question", False, False, False),
    ("hypothesis", "Hypothesis", False, False, False),
    ("methods", "Proposed design and methods", False, True, False),
    ("data_resources", "Data, sample and resources", False, True, False),
    ("expected_contribution", "Expected contribution", False, False, False),
    ("risks_ethics", "Risks, limitations and ethics", False, True, False),
    ("timeline", "Timeline", False, True, True),
]
SOURCES = ("author", "literature", "agent_draft")


def _gap_validation(pm: ProjectManager) -> dict[str, dict[str, Any]]:
    path = pm.workspace / "analysis" / "gap-validation.json"
    if not path.exists():
        return {}
    return {g["gap_id"]: g for g in read_json(path).get("gaps", [])}


def init_canvas(pm: ProjectManager, *, force: bool = False) -> dict[str, Any]:
    cfg = pm.load_config()
    out = pm.resolve(CANVAS_PATH)
    if out.exists() and not force:
        raise ApprovalRequired(f"{CANVAS_PATH} already exists; re-run with --force to replace it")
    validated = _gap_validation(pm)
    payload = {
        "schema_version": "1.1", "generated_at": utcnow().isoformat(),
        "title": None, "topic": cfg.topic, "field": cfg.field, "gap_id": None,
        "validated_gaps": [{"gap_id": g["gap_id"], "title": g["title"], "verdict": g["verdict"], "statement": g["statement"]} for g in validated.values()],
        "instructions": ("Choose one gap (gap_id) with the author. Fill each field's `text` and set `source` to author | literature | agent_draft. "
                         "`known` and `gap` must cite src-/ev- ids. methods, data_resources, risks_ethics and timeline are the author's decisions: "
                         "ask the author; an agent_draft there is labelled unconfirmed in the outputs. Leave text null for anything unknown; "
                         "the engine writes a placeholder instead of guessing."),
        "fields": {name: {"label": label, "text": None, "source": None} for name, label, *_ in CANVAS_FIELDS},
    }
    path = write_json(out, payload)
    return {"artifact": str(path), "validated_gaps": len(validated),
            "warning": None if validated else "no analysis/gap-validation.json: the gap has not been checked for counterevidence (run gap-validator first)"}


def build_concept(pm: ProjectManager, canvas_path: str = CANVAS_PATH, *, force: bool = False, run_id=None, step_id=None) -> dict[str, Any]:
    src_path = pm.resolve(canvas_path)
    if not src_path.exists():
        raise StepBlocked(f"{canvas_path} not found; run `rtk concept init` first")
    canvas = read_json(src_path)
    registry = SourceRegistry(pm.workspace)
    known_src, known_ev = registry.ids(), EvidenceStore(pm.workspace).ids()
    fields = canvas.get("fields") or {}
    problems: list[str] = []
    warnings: list[str] = []
    missing: list[str] = []
    unconfirmed: list[str] = []
    cited: list[str] = []
    rendered: dict[str, str] = {}
    for name, label, needs_ids, author_owned, optional in CANVAS_FIELDS:
        f = fields.get(name) or {}
        text = (f.get("text") or "").strip()
        source = f.get("source")
        if not text or PLACEHOLDER_RE.fullmatch(text):
            if not optional:
                missing.append(label)
            rendered[name] = "" if optional else f"[AUTHOR INPUT NEEDED: {label}]"
            continue
        if source not in SOURCES:
            problems.append(f"{name}: source must be one of {' | '.join(SOURCES)}")
        refs = ID_REF_RE.findall(text)
        bad = sorted({r for r in refs if (r.startswith("src-") and r not in known_src) or (r.startswith("ev-") and r not in known_ev)})
        if bad:
            problems.append(f"{name}: unknown ids {', '.join(bad)}")
        if needs_ids and not [r for r in refs if r not in bad]:
            problems.append(f"{name}: must cite at least one registered src-/ev- id")
        for r in refs:
            if r.startswith("src-") and r in known_src and r not in cited:
                cited.append(r)
        over = [m.group(0) for m in NOVELTY_RE.finditer(text)]
        if over:
            problems.append(f"{name}: novelty over-claim ({', '.join(over)})")
        placeholders = [m.group(0) for m in PLACEHOLDER_RE.finditer(text)]
        if placeholders:
            missing.append(f"{label}: {'; '.join(placeholders)}")
        if author_owned and source != "author":
            unconfirmed.append(label)
            text = f"[UNCONFIRMED — drafted by the AI agent, not yet confirmed by the author]\n\n{text}"
        rendered[name] = text
    gap_id = canvas.get("gap_id")
    validated = _gap_validation(pm)
    if not gap_id:
        warnings.append("no gap_id chosen: the concept is not tied to a validated gap")
        gap_line = "Validation: not linked to a gap checked by gap-validator."
    elif gap_id not in validated:
        warnings.append(f"{gap_id} has no entry in analysis/gap-validation.json: run gap-validator before presenting this as a gap")
        gap_line = f"Validation: `{gap_id}` has not been checked for counterevidence."
    else:
        g = validated[gap_id]
        if g["verdict"] == "already_addressed":
            problems.append(f"{gap_id} was judged already_addressed by gap-validator; choose another gap or reframe it")
        elif g["verdict"] == "inconclusive":
            warnings.append(f"{gap_id} validation is inconclusive")
        if g.get("human_review") == "pending":
            warnings.append(f"{gap_id} validation verdict still awaits author review")
        gap_line = (f"Validation: `{gap_id}` — {g['verdict']} after {g.get('queries_ok', 0)} successful targeted query run(s), "
                    f"{g.get('hits_screened', 0)} record(s) screened. This is a candidate gap, not proven novelty.")
    title = (canvas.get("title") or "").strip() or f"Concept paper: {canvas.get('topic') or pm.load_config().topic}"
    refs_body = "\n".join(
        f"- `{sid}` {('; '.join(registry.get(sid).authors[:3]) + '. ') if registry.get(sid).authors else ''}{registry.get(sid).title} "
        f"({registry.get(sid).year or 'n.d.'})" + (f". doi:{registry.get(sid).doi}" if registry.get(sid).doi else "") for sid in cited) or "- none cited"
    status_body = "\n".join([
        "- Draft concept paper generated from the Gap Canvas; not approved by the author yet.",
        f"- Fields still missing: {len(missing)}" + (f" ({'; '.join(missing)})" if missing else ""),
        f"- Fields drafted by the agent and unconfirmed: {len(unconfirmed)}" + (f" ({'; '.join(unconfirmed)})" if unconfirmed else ""),
        *[f"- Warning: {w}" for w in warnings], *[f"- Problem: {p}" for p in problems],
    ])
    sections: list[tuple[str, str]] = []
    for name, label, *_ in CANVAS_FIELDS:
        if not rendered[name]:
            continue
        body = rendered[name] + (f"\n\n{gap_line}" if name == "gap" else "")
        sections.append((label, body))
    sections += [("References", refs_body), ("Status of this draft", status_body)]
    out_dir = pm.workspace / "manuscript"
    for rel in ("manuscript/concept-paper.md", "manuscript/concept-paper.docx", "manuscript/gap-canvas.md"):
        pm.guard_overwrite(rel, force=force)
    canvas_rows = "\n".join(f"| {label} | {(fields.get(name) or {}).get('source') or '—'} | {(rendered[name] or '—').replace(chr(10), ' ').replace('|', '/')} |"
                            for name, label, *_ in CANVAS_FIELDS)
    canvas_md = write_markdown(out_dir / "gap-canvas.md", f"Gap Canvas — {title}", [
        ("Canvas", "| Block | Source | Content |\n|---|---|---|\n" + canvas_rows), ("Gap validation", gap_line), ("Status", status_body)],
        front_note="One-page view of the concept. `Source` shows who supplied each block: author, literature or agent_draft.")
    note = "DRAFT concept paper. Design, data and timeline are the author's decisions; unconfirmed and missing parts are marked in the text."
    md = write_markdown(out_dir / "concept-paper.md", title, sections, front_note=note)
    docx = write_docx(out_dir / "concept-paper.docx", title, sections, metadata_note=note)
    status = ValidationStatus.VALID if not problems else ValidationStatus.INVALID
    for p in (canvas_md, md, docx):
        pm.register_artifact(p, skill="research-concept-builder", run_id=run_id, step_id=step_id, source_ids=cited,
                             validation_status=status, author_review=AuthorReviewStatus.PENDING, tentative=True)
    return {"title": title, "gap_id": gap_id, "missing": missing, "unconfirmed": unconfirmed, "warnings": warnings, "problems": problems,
            "cited_sources": cited, "artifacts": [str(canvas_md), str(md), str(docx)], "ok": not problems}
