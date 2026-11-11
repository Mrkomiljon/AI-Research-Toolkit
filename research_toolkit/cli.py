"""`rtk` command line: the stable interface the SKILL.md files call. Also `python -m research_toolkit`."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import SKILL_NAMES, __version__, pipelines
from .evidence_store import EvidenceStore
from .exporters import read_json
from .orchestrator import build_plan, final_report, plan_preview, run_ready, run_step, save_new_plan
from .progress import write_progress_artifacts
from .project_manager import ApprovalRequired, ProjectManager
from .providers import make_providers
from .schemas import (
    AccessLevel,
    AuthorReviewStatus,
    BudgetConfig,
    EvidenceRecord,
    EvidenceType,
    PrivacyConfig,
    ProjectConfig,
    StepStatus,
    VerificationStatus,
    VerifiedBy,
)
from .source_registry import SourceRegistry, new_source
from .validation import validate_skills_tree
from .workflow_state import PlanError, WorkflowState


def _out(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    elif isinstance(payload, str):
        print(payload)
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def _pm(args) -> ProjectManager:
    return ProjectManager.find(Path(args.project))


def _providers(names: str | None):
    return make_providers(tuple(n.strip() for n in names.split(",")) if names else None)


# ---- commands ------------------------------------------------------------------------------------------
def cmd_init(a):
    root = Path(a.workspace or os.environ.get("RTK_WORKSPACE_ROOT") or "workspace")
    cfg = ProjectConfig(
        slug=a.slug, title=a.title or a.slug.replace("-", " ").title(), topic=a.topic, goals=a.goal or [],
        field=a.field, output_language=a.language, year_from=a.year_from, year_to=a.year_to, target_journal=a.journal,
        available_pdfs_note=a.pdfs_note,
        privacy=PrivacyConfig(allow_external_apis=not a.no_external_apis, private_data_notes=a.privacy_note,
                              cloud_caveat_acknowledged=a.ack_cloud),
        budget=BudgetConfig(allow_paid_apis=False, max_papers_per_search=a.max_papers),
    )
    pm = ProjectManager.init(root, cfg, overwrite=a.force)
    write_progress_artifacts(pm)
    _out({"workspace": str(pm.workspace), "config": str(pm.config_path),
          "cloud_caveat": "Claude Code / Codex send prompts and attached text to their providers' cloud. 'Local-first' means artifacts stay on disk, not that inference is offline."}, a.json)


def cmd_plan(a):
    pm = _pm(a)
    overrides = {}
    for k in ("target_count", "year_from", "year_to", "topic", "manuscript_path", "bib_path", "question"):
        v = getattr(a, k, None)
        if v is not None:
            overrides[k] = v
    if a.source_ids:
        overrides["source_ids"] = a.source_ids
    if a.full_text_only:
        overrides["full_text_only"] = True
    try:
        plan = build_plan(pm, a.request, overrides=overrides, chain=a.chain.split(",") if a.chain else None)
    except PlanError as exc:
        _out({"error": str(exc)}, a.json)
        sys.exit(2)
    save_new_plan(pm, plan)
    _out(plan.model_dump(mode="json") if a.json else plan_preview(plan), a.json)


def cmd_approve(a):
    pm = _pm(a)
    state = WorkflowState(pm.workspace)
    plan = state.load_plan()
    for sid in a.steps:
        state.approve_step(plan, sid)
    _out(state.summary(plan), a.json)


def cmd_run(a):
    pm = _pm(a)
    state = WorkflowState(pm.workspace)
    plan = state.load_plan()
    ctx = {"providers": _providers(a.providers)} if a.providers else {}
    if a.step:
        res = [run_step(pm, plan, a.step, context=ctx)]
    else:
        res = run_ready(pm, plan, context=ctx)
    _out({"results": res, "summary": state.summary(plan)}, a.json)


def cmd_step(a):
    pm = _pm(a)
    cfg = pm.load_config()
    state = WorkflowState(pm.workspace)
    plan = state.load_plan()
    try:
        if a.action == "start":
            state.start_step(plan, a.step_id, cfg.limits)
        elif a.action == "complete":
            for rel in a.artifacts or []:
                pm.register_artifact(rel, skill=plan.step(a.step_id).skill, run_id=plan.run_id, step_id=a.step_id,
                                     author_review=AuthorReviewStatus.PENDING if a.needs_review else AuthorReviewStatus.NOT_REQUIRED,
                                     tentative=a.tentative)
            status = StepStatus.AWAITING_USER_REVIEW if a.needs_review else StepStatus.COMPLETED
            state.finish_step(plan, a.step_id, status, artifacts=a.artifacts or [], message=a.message)
        elif a.action == "approve-review":
            step = plan.step(a.step_id)
            if step.status != StepStatus.AWAITING_USER_REVIEW:
                raise PlanError(f"step {a.step_id} is {step.status.value}, not awaiting review")
            for art in pm.artifacts():
                if art.step_id == a.step_id:
                    pm.update_artifact(art.path, author_review_status=AuthorReviewStatus.APPROVED, tentative=False)
            state.finish_step(plan, a.step_id, StepStatus.COMPLETED, message="user approved outputs")
        elif a.action in ("block", "fail", "skip"):
            status = {"block": StepStatus.BLOCKED, "fail": StepStatus.FAILED, "skip": StepStatus.SKIPPED}[a.action]
            state.finish_step(plan, a.step_id, status, error=a.message if a.action != "skip" else None, message=a.message)
    except (PlanError, FileNotFoundError, KeyError) as exc:
        _out({"error": str(exc)}, a.json)
        sys.exit(2)
    _out(state.summary(plan), a.json)


def cmd_log(a):
    """Human-readable view of workflow/runs.jsonl; --follow tails it live (watch a run from a second terminal)."""
    import time

    pm = _pm(a)
    state = WorkflowState(pm.workspace)
    path = state.runs_path
    seen = 0

    def render(ev):
        step = f" {ev.step_id}" if ev.step_id else ""
        skill = f" [{ev.skill}]" if ev.skill else ""
        msg = f" — {ev.message}" if ev.message else ""
        err = f" !! {ev.error}" if ev.error else ""
        arts = f" -> {', '.join(ev.artifacts)}" if ev.artifacts else ""
        return f"{ev.ts.strftime('%H:%M:%S')} {ev.event:<28}{step}{skill}{msg}{arts}{err}"

    while True:
        events = state.events(a.run)
        for ev in events[seen:]:
            print(render(ev), flush=True)
        seen = len(events)
        if not a.follow:
            if seen == 0:
                print(f"(no events yet in {path})")
            return
        time.sleep(a.interval)


def cmd_resume(a):
    pm = _pm(a)
    state = WorkflowState(pm.workspace)
    plan = state.load_plan()
    _out(state.resume(plan), a.json)


def cmd_report(a):
    pm = _pm(a)
    state = WorkflowState(pm.workspace)
    plan = state.load_plan()
    _out(final_report(pm, plan), a.json)


def cmd_status(a):
    pm = _pm(a)
    res = write_progress_artifacts(pm)
    _out(res if a.json else res["status"], True)


def cmd_search(a):
    pm = _pm(a)
    cfg = pm.load_config()
    if not cfg.privacy.allow_external_apis and not a.authorized:
        _out({"error": "privacy.allow_external_apis is false; re-run with --authorized after user approval"}, a.json)
        sys.exit(3)
    try:
        res = pipelines.literature_search(pm, topic=a.topic or cfg.topic, providers=_providers(a.providers),
                                          year_from=a.year_from or cfg.year_from, year_to=a.year_to or cfg.year_to,
                                          target_count=a.target_count, inclusion_criteria=a.include, exclusion_criteria=a.exclude)
    except pipelines.StepBlocked as exc:
        _out({"status": "blocked", "error": str(exc), "partial_artifacts": exc.partial_artifacts}, a.json)
        sys.exit(4)
    if a.fetch:
        from .fulltext import fetch_full_text

        res["fulltext"] = fetch_full_text(pm, res["selected"])["counts"]
    _out(res, a.json)


def cmd_fetch(a):
    from .fulltext import DEFAULT_ORDER, fetch_full_text

    pm = _pm(a)
    order = tuple(x.strip() for x in a.sources.split(",")) if a.sources else DEFAULT_ORDER
    try:
        res = fetch_full_text(pm, a.source_ids or None, order=order, limit=a.limit, overwrite=a.overwrite)
    except ApprovalRequired as exc:
        _out({"error": str(exc)}, True)
        sys.exit(3)
    if a.prepare:
        for r in res["results"]:
            if r["status"] in ("downloaded", "already_present"):
                try:
                    pipelines.prepare_paper_analysis(pm, r["source_id"])
                except pipelines.StepBlocked as exc:
                    r["prepare_error"] = str(exc)
    _out({"counts": res["counts"], "contact_email_set": res["contact_email_set"], "log": res["log"],
          "results": [{k: r.get(k) for k in ("source_id", "status", "provider", "license", "path", "error")} for r in res["results"]]}, True)


def cmd_sources(a):
    pm = _pm(a)
    reg = SourceRegistry(pm.workspace)
    if a.action == "list":
        _out([{"source_id": s.source_id, "title": s.title, "year": s.year, "doi": s.doi, "access": s.access_level.value,
               "verification": s.verification_status.value, "pdf": s.pdf_path} for s in reg.all()], True)
    elif a.action == "add":
        rec = new_source(a.title, authors=a.authors or [], year=a.year, doi=a.doi, provider="manual",
                         access_level=AccessLevel.FULL_TEXT if a.pdf else AccessLevel.METADATA_ONLY, pdf_path=a.pdf)
        rec, created = reg.add(rec)
        reg.save()
        _out({"source_id": rec.source_id, "created": created}, True)
    elif a.action == "attach-pdf":
        rec = reg.get(a.source_id)
        if not rec:
            _out({"error": f"unknown source {a.source_id}"}, True)
            sys.exit(2)
        pm.resolve(a.pdf)  # path safety
        rec.pdf_path = a.pdf
        reg.upsert(rec)
        reg.save()
        _out(pipelines.prepare_paper_analysis(pm, a.source_id, a.pdf), True)
    elif a.action == "verify":
        provs = _providers(a.providers)
        out = []
        for s in reg.all():
            if a.source_id and s.source_id != a.source_id:
                continue
            if not s.doi:
                out.append({"source_id": s.source_id, "result": "no DOI; manual check needed"})
                continue
            resolved = None
            for p in provs:
                try:
                    resolved = p.lookup_doi(s.doi)
                    if resolved:
                        break
                except Exception as exc:  # noqa: BLE001
                    out.append({"source_id": s.source_id, "provider": p.name, "error": str(exc)})
            if resolved is None:
                s.verification_status = VerificationStatus.FAILED
                out.append({"source_id": s.source_id, "result": "DOI did not resolve"})
            else:
                from .validation import titles_match

                ok, ratio = titles_match(s.title, resolved.title)
                s.verification_status = VerificationStatus.VERIFIED if ok else VerificationStatus.MISMATCH
                out.append({"source_id": s.source_id, "result": s.verification_status.value, "title_similarity": ratio})
            reg.upsert(s)
        reg.save()
        _out(out, True)
    elif a.action == "stats":
        _out(reg.stats(), True)


def cmd_analyze(a):
    pm = _pm(a)
    if a.action == "prepare":
        try:
            _out(pipelines.prepare_paper_analysis(pm, a.source_id, a.pdf, fetch=a.fetch, ocr=a.ocr, ocr_backend=a.ocr_backend), True)
        except (pipelines.StepBlocked, ApprovalRequired) as exc:
            _out({"error": str(exc)}, True)
            sys.exit(4)
    elif a.action == "finalize":
        analysis = read_json(Path(a.analysis_json))
        try:
            _out(pipelines.finalize_paper_analysis(pm, a.source_id, analysis), True)
        except pipelines.StepBlocked as exc:
            _out({"error": str(exc)}, True)
            sys.exit(4)


def cmd_setup(a):
    from . import installer

    agents = ["claude", "codex"] if a.agent == "all" else [a.agent]
    try:
        res = installer.install_skills(agents, scope=a.scope, project_dir=a.dir, force=a.force)
    except FileNotFoundError as exc:
        _out({"error": str(exc)}, a.json)
        sys.exit(1)
    _out(res if a.json else installer.render_setup(res, agents), a.json)


def cmd_doctor(a):
    from . import installer

    report = installer.doctor(a.dir, check_network=not a.offline)
    _out(report if a.json else installer.render_doctor(report), a.json)
    sys.exit(0 if report["ready"] else 1)


def cmd_ocr(a):
    from . import ocr

    _out(ocr.status(), True)


def cmd_claims(a):
    from . import verification

    pm = _pm(a)
    try:
        if a.action == "extract":
            if not a.manuscript:
                _out({"error": "--manuscript is required for extract"}, True)
                sys.exit(2)
            _out(verification.extract_claims(pm, a.manuscript, a.bib), True)
            return
        res = verification.finalize_claims(pm, read_json(pm.resolve(a.claims_json)))
    except pipelines.StepBlocked as exc:
        _out({"error": str(exc)}, True)
        sys.exit(4)
    except FileNotFoundError as exc:
        _out({"error": str(exc)}, True)
        sys.exit(2)
    _out(res, True)
    sys.exit(0 if res["passed"] else 5)


def cmd_gaps(a):
    from . import verification

    pm = _pm(a)
    try:
        if a.action == "init":
            _out(verification.init_gap_validation(pm, a.file, force=a.force), True)
        elif a.action == "search":
            cfg = pm.load_config()
            if not cfg.privacy.allow_external_apis and not a.authorized:
                _out({"error": "privacy.allow_external_apis is false; re-run with --authorized after user approval"}, True)
                sys.exit(3)
            _out(verification.search_gap_counterevidence(pm, _providers(a.providers), input_path=a.input, per_query=a.per_query,
                                                         year_from=a.year_from), True)
        else:
            res = verification.finalize_gap_validation(pm, input_path=a.input)
            _out(res, True)
            sys.exit(0 if res["passed"] else 5)
    except ApprovalRequired as exc:
        _out({"error": str(exc)}, True)
        sys.exit(3)
    except pipelines.StepBlocked as exc:
        _out({"status": "blocked", "error": str(exc), "partial_artifacts": exc.partial_artifacts}, True)
        sys.exit(4)


def cmd_concept(a):
    from . import concept

    pm = _pm(a)
    try:
        if a.action == "init":
            _out(concept.init_canvas(pm, force=a.force), True)
            return
        res = concept.build_concept(pm, a.canvas, force=a.force)
    except ApprovalRequired as exc:
        _out({"error": str(exc)}, True)
        sys.exit(3)
    except pipelines.StepBlocked as exc:
        _out({"error": str(exc)}, True)
        sys.exit(4)
    _out(res, True)
    sys.exit(0 if res["ok"] else 5)


def cmd_evidence(a):
    pm = _pm(a)
    store = EvidenceStore(pm.workspace)
    if a.action == "list":
        _out([e.model_dump(mode="json") for e in store.all() if not a.source_id or e.source_id == a.source_id], True)
    elif a.action == "add":
        reg = SourceRegistry(pm.workspace)
        rec = EvidenceRecord(evidence_id=EvidenceStore.make_id(a.source_id, a.claim, a.locator), source_id=a.source_id, claim=a.claim,
                             excerpt=a.excerpt, locator=a.locator, evidence_type=EvidenceType(a.type), verified_by=VerifiedBy(a.verified_by),
                             verification_status=VerificationStatus.VERIFIED if a.verified_by == "human" else VerificationStatus.UNVERIFIED,
                             skill=a.skill)
        try:
            rec = store.append(rec, reg.ids())
        except ValueError as exc:
            _out({"error": str(exc)}, True)
            sys.exit(2)
        _out(rec.model_dump(mode="json"), True)


def cmd_review(a):
    pm = _pm(a)
    if a.action == "matrix":
        try:
            _out(pipelines.build_literature_matrix(pm, a.source_ids), True)
        except pipelines.StepBlocked as exc:
            _out({"error": str(exc)}, True)
            sys.exit(4)
    elif a.action == "validate-links":
        text = pm.resolve(a.file).read_text(encoding="utf-8")
        res = pipelines.validate_evidence_links(pm, text)
        _out(res, True)
        sys.exit(0 if res["ok"] else 5)
    elif a.action == "gap-seed":
        try:
            _out(pipelines.collect_gap_seed(pm), True)
        except pipelines.StepBlocked as exc:
            _out({"error": str(exc)}, True)
            sys.exit(4)
    elif a.action == "validate-gaps":
        text = pm.resolve(a.file).read_text(encoding="utf-8")
        res = pipelines.validate_gap_report(pm, text)
        _out(res, True)
        sys.exit(0 if res["ok"] else 5)


def cmd_manuscript(a):
    pm = _pm(a)
    try:
        if a.action == "to-docx":
            _out(pipelines.manuscript_to_docx(pm, a.file, a.out, force=a.force), True)
        elif a.action == "check-inputs":
            text = pm.resolve(a.file).read_text(encoding="utf-8")
            _out(pipelines.check_manuscript_inputs(pm, text), True)
    except ApprovalRequired as exc:
        _out({"error": str(exc)}, True)
        sys.exit(3)


def cmd_verify_citations(a):
    pm = _pm(a)
    cfg = pm.load_config()
    provs = None if (a.offline or not cfg.privacy.allow_external_apis) else _providers(a.providers)
    res = pipelines.audit_citations(pm, a.manuscript, a.bib, providers=provs)
    _out(res, True)
    sys.exit(0 if res["passed"] else 5)


def cmd_integrity(a):
    pm = _pm(a)
    ai_use = read_json(Path(a.ai_use)) if a.ai_use else {}
    policy = Path(a.journal_policy).read_text(encoding="utf-8") if a.journal_policy else None
    _out(pipelines.integrity_audit(pm, ai_use=ai_use, journal_policy=policy, manuscript_path=a.manuscript), True)


def cmd_peer_review(a):
    pm = _pm(a)
    comments = read_json(Path(a.comments))
    report = Path(a.report).read_text(encoding="utf-8") if a.report else None
    try:
        _out(pipelines.build_review_outputs(pm, comments, report_md=report), True)
    except pipelines.StepBlocked as exc:
        _out({"error": str(exc)}, True)
        sys.exit(4)


def cmd_writing(a):
    from .writing import check_writing

    pm = _pm(a)
    try:
        _out(check_writing(pm, a.file, compare_with=a.compare_with), True)
    except ValueError as exc:
        _out({"error": str(exc)}, True)
        sys.exit(4)


def cmd_journal(a):
    from .journal import GUIDELINES, build_checklist, cover_letter

    if a.action == "guidelines":  # needs no workspace
        _out({k: {"name": v["name"], "items": len(v["items"])} for k, v in GUIDELINES.items()}, True)
        return
    pm = _pm(a)
    try:
        if a.action == "checklist":
            _out(build_checklist(pm, a.manuscript, a.guideline, guidelines_file=a.guidelines_file, word_limit=a.word_limit, abstract_limit=a.abstract_limit), True)
        elif a.action == "cover-letter":
            _out(cover_letter(pm, a.manuscript, a.journal), True)
    except ValueError as exc:
        _out({"error": str(exc)}, True)
        sys.exit(4)


def cmd_privacy_check(a):
    pm = _pm(a)
    try:
        findings = pm.check_external_transmission(a.paths, authorized=a.authorized)
    except ApprovalRequired as exc:
        _out({"allowed": False, "error": str(exc)}, True)
        sys.exit(3)
    _out({"allowed": True, "findings": findings}, True)


def cmd_validate_skills(a):
    root = Path(a.skills_dir)
    report = validate_skills_tree(root)
    errors = {k: v for k, v in report.items() if v}
    _out({"skills": list(SKILL_NAMES), "valid": [k for k, v in report.items() if not v], "errors": errors}, True)
    sys.exit(1 if errors else 0)


# ---- parser --------------------------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rtk", description=f"AI Research Toolkit engine v{__version__}")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    def proj(sp):
        sp.add_argument("--project", "-p", default=".", help="workspace dir (or any dir below it)")

    s = sub.add_parser("init", help="initialise a research workspace")
    s.add_argument("--workspace", help="root folder for workspaces (default ./workspace)")
    s.add_argument("--slug", required=True)
    s.add_argument("--topic", required=True)
    s.add_argument("--title")
    s.add_argument("--goal", action="append")
    s.add_argument("--field")
    s.add_argument("--language", default="uz")
    s.add_argument("--year-from", type=int)
    s.add_argument("--year-to", type=int)
    s.add_argument("--journal")
    s.add_argument("--pdfs-note")
    s.add_argument("--privacy-note")
    s.add_argument("--no-external-apis", action="store_true")
    s.add_argument("--ack-cloud", action="store_true", help="user acknowledged the provider cloud transmission caveat")
    s.add_argument("--max-papers", type=int, default=50)
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("setup", help="install the skills for Claude Code and/or Codex into this folder (no Node.js or git needed)")
    s.add_argument("--agent", choices=["claude", "codex", "all"], default="all")
    s.add_argument("--scope", choices=["project", "user"], default="project", help="project = this folder (default); user = every folder")
    s.add_argument("--dir", default=".", help="research folder for --scope project (default: current folder)")
    s.add_argument("--force", action="store_true", help="also replace skills you edited or that another tool installed")
    s.set_defaults(fn=cmd_setup)

    s = sub.add_parser("doctor", help="check the installation: engine, skills, agents, OCR, network")
    s.add_argument("--dir", default=".")
    s.add_argument("--offline", action="store_true", help="skip the network reachability checks")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("plan", help="build a dependency-aware workflow plan from a natural-language request")
    proj(s)
    s.add_argument("request")
    s.add_argument("--chain", help="override skill chain, comma separated")
    s.add_argument("--target-count", type=int)
    s.add_argument("--year-from", type=int)
    s.add_argument("--year-to", type=int)
    s.add_argument("--topic")
    s.add_argument("--manuscript-path")
    s.add_argument("--bib-path")
    s.add_argument("--question")
    s.add_argument("--source-ids", nargs="*")
    s.add_argument("--full-text-only", action="store_true")
    s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("approve", help="record explicit user approval for gated steps")
    proj(s)
    s.add_argument("steps", nargs="+")
    s.set_defaults(fn=cmd_approve)

    s = sub.add_parser("run", help="run ready engine steps (or one step) with checkpoints")
    proj(s)
    s.add_argument("--step")
    s.add_argument("--providers")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("step", help="checkpoint host-skill steps: start|complete|approve-review|block|fail|skip")
    proj(s)
    s.add_argument("action", choices=["start", "complete", "approve-review", "block", "fail", "skip"])
    s.add_argument("step_id")
    s.add_argument("--artifacts", nargs="*", help="workspace-relative files produced")
    s.add_argument("--message")
    s.add_argument("--needs-review", action="store_true", help="outputs need author review before counting as complete")
    s.add_argument("--tentative", action="store_true")
    s.set_defaults(fn=cmd_step)

    s = sub.add_parser("log", help="show workflow events; --follow tails workflow/runs.jsonl live")
    proj(s)
    s.add_argument("--follow", "-f", action="store_true")
    s.add_argument("--run", help="only this run id")
    s.add_argument("--interval", type=float, default=1.0)
    s.set_defaults(fn=cmd_log)

    s = sub.add_parser("resume", help="re-validate completed steps and re-queue interrupted ones")
    proj(s)
    s.set_defaults(fn=cmd_resume)

    s = sub.add_parser("report", help="final report that lists only files present on disk")
    proj(s)
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("status", help="recompute project-status.json / research-progress.xlsx / next-actions.md")
    proj(s)
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("search", help="literature-search engine step (direct)")
    proj(s)
    s.add_argument("--topic")
    s.add_argument("--year-from", type=int)
    s.add_argument("--year-to", type=int)
    s.add_argument("--target-count", type=int, default=20)
    s.add_argument("--providers", help="comma list: openalex,crossref,semantic_scholar")
    s.add_argument("--include", action="append")
    s.add_argument("--exclude", action="append")
    s.add_argument("--authorized", action="store_true")
    s.add_argument("--fetch", action="store_true", help="also try to download open-access PDFs for the selected papers")
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("fetch", help="download open-access full texts (arXiv, Europe PMC, Unpaywall, OpenAlex OA) into papers/PDFs/")
    proj(s)
    s.add_argument("--source-ids", nargs="*")
    s.add_argument("--limit", type=int)
    s.add_argument("--sources", help="comma order, default openalex,arxiv,europepmc,unpaywall")
    s.add_argument("--overwrite", action="store_true")
    s.add_argument("--prepare", action="store_true", help="run `analyze prepare` for every fetched PDF")
    s.set_defaults(fn=cmd_fetch)

    s = sub.add_parser("sources", help="source registry: list|add|attach-pdf|verify|stats")
    proj(s)
    s.add_argument("action", choices=["list", "add", "attach-pdf", "verify", "stats"])
    s.add_argument("--title")
    s.add_argument("--authors", nargs="*")
    s.add_argument("--year", type=int)
    s.add_argument("--doi")
    s.add_argument("--pdf", help="workspace-relative PDF path")
    s.add_argument("--source-id")
    s.add_argument("--providers")
    s.set_defaults(fn=cmd_sources)

    s = sub.add_parser("analyze", help="paper-analyzer: prepare (extract text) | finalize (validate LLM analysis json)")
    proj(s)
    s.add_argument("action", choices=["prepare", "finalize"])
    s.add_argument("source_id")
    s.add_argument("--pdf")
    s.add_argument("--fetch", action="store_true", help="try to download an open-access PDF first")
    s.add_argument("--analysis-json")
    s.add_argument("--ocr", choices=["auto", "off", "force"], default="auto",
                   help="scanned pages: auto = OCR pages without a text layer if a backend is installed (default); force = OCR every page")
    s.add_argument("--ocr-backend", help="docling | tesseract (default: first installed, or RTK_OCR_BACKEND)")
    s.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("ocr", help="OCR backends for scanned PDFs: status")
    s.add_argument("action", choices=["status"])
    s.set_defaults(fn=cmd_ocr)

    s = sub.add_parser("claims", help="claim-verifier: extract (cited sentences -> reviews/claims.json) | finalize (validate verdicts)")
    proj(s)
    s.add_argument("action", choices=["extract", "finalize"])
    s.add_argument("--manuscript", help="workspace-relative md/docx/txt (extract)")
    s.add_argument("--bib", help="workspace-relative .bib used to resolve citation keys (extract)")
    s.add_argument("--claims-json", default="reviews/claims.json", help="workspace-relative claims file with verdicts (finalize)")
    s.set_defaults(fn=cmd_claims)

    s = sub.add_parser("gaps", help="gap-validator: init (worksheet from research-gaps.md) | search (targeted counterevidence) | finalize")
    proj(s)
    s.add_argument("action", choices=["init", "search", "finalize"])
    s.add_argument("--file", default="analysis/research-gaps.md", help="gap report to read (init)")
    s.add_argument("--input", default="analysis/gap-validation.input.json", help="worksheet with queries / verdicts")
    s.add_argument("--per-query", type=int, default=10)
    s.add_argument("--year-from", type=int)
    s.add_argument("--providers", help="comma list: openalex,crossref,semantic_scholar")
    s.add_argument("--authorized", action="store_true", help="user approved external search although the project disables external APIs")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_gaps)

    s = sub.add_parser("concept", help="research-concept-builder: init (gap-canvas.json) | build (canvas + concept paper)")
    proj(s)
    s.add_argument("action", choices=["init", "build"])
    s.add_argument("--canvas", default="manuscript/gap-canvas.json")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_concept)

    s = sub.add_parser("evidence", help="evidence store: list|add")
    proj(s)
    s.add_argument("action", choices=["list", "add"])
    s.add_argument("--source-id")
    s.add_argument("--claim")
    s.add_argument("--locator")
    s.add_argument("--excerpt")
    s.add_argument("--type", default="paraphrase", choices=[e.value for e in EvidenceType])
    s.add_argument("--verified-by", default="llm", choices=[e.value for e in VerifiedBy])
    s.add_argument("--skill")
    s.set_defaults(fn=cmd_evidence)

    s = sub.add_parser("review", help="literature-review/gap-finder helpers: matrix|validate-links|gap-seed|validate-gaps")
    proj(s)
    s.add_argument("action", choices=["matrix", "validate-links", "gap-seed", "validate-gaps"])
    s.add_argument("--source-ids", nargs="*")
    s.add_argument("--file")
    s.set_defaults(fn=cmd_review)

    s = sub.add_parser("manuscript", help="manuscript-builder helpers: to-docx|check-inputs")
    proj(s)
    s.add_argument("action", choices=["to-docx", "check-inputs"])
    s.add_argument("--file", required=True, help="workspace-relative markdown")
    s.add_argument("--out", default="manuscript-draft.docx")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_manuscript)

    s = sub.add_parser("verify-citations", help="citation-verifier engine step")
    proj(s)
    s.add_argument("--manuscript", required=True)
    s.add_argument("--bib")
    s.add_argument("--offline", action="store_true", help="format-only, no DOI resolution")
    s.add_argument("--providers")
    s.set_defaults(fn=cmd_verify_citations)

    s = sub.add_parser("integrity", help="academic-integrity outputs from author-stated AI use")
    proj(s)
    s.add_argument("--ai-use", help="json file: {tools:[], stages:[], human_review:'', data_shared_with_tools:''}")
    s.add_argument("--journal-policy", help="text file with the journal policy")
    s.add_argument("--manuscript")
    s.set_defaults(fn=cmd_integrity)

    s = sub.add_parser("peer-review", help="peer-reviewer outputs from a comments json")
    proj(s)
    s.add_argument("--comments", required=True)
    s.add_argument("--report", help="markdown report written by the reviewing agent")
    s.set_defaults(fn=cmd_peer_review)

    s = sub.add_parser("writing", help="academic-writing metrics: check --file <md|docx> [--compare-with original]")
    proj(s)
    s.add_argument("action", choices=["check"])
    s.add_argument("--file", required=True)
    s.add_argument("--compare-with", help="original text to verify that ids/numbers/citations are unchanged")
    s.set_defaults(fn=cmd_writing)

    s = sub.add_parser("journal", help="journal-standards: checklist | cover-letter | guidelines")
    proj(s)
    s.add_argument("action", choices=["checklist", "cover-letter", "guidelines"])
    s.add_argument("--manuscript")
    s.add_argument("--guideline", default="generic", help="generic|CONSORT|STROBE|STARD|TRIPOD|PRISMA|ARRIVE|CARE")
    s.add_argument("--guidelines-file", help="text file with the journal's author guidelines")
    s.add_argument("--word-limit", type=int)
    s.add_argument("--abstract-limit", type=int)
    s.add_argument("--journal")
    s.set_defaults(fn=cmd_journal)

    s = sub.add_parser("privacy-check", help="gate before any external transmission of workspace files")
    proj(s)
    s.add_argument("paths", nargs="+")
    s.add_argument("--authorized", action="store_true")
    s.set_defaults(fn=cmd_privacy_check)

    s = sub.add_parser("validate-skills", help="validate the SKILL.md manifests")
    s.add_argument("--skills-dir", default="skills")
    s.set_defaults(fn=cmd_validate_skills)
    return p


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to legacy code pages
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
