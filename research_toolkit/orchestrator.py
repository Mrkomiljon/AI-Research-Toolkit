"""research-orchestrator engine: intent routing, dependency-aware planning, gated execution, reporting.

The LLM host agent interprets ambiguous requests; this module gives it a deterministic, inspectable plan,
runs the engine-executable steps, checkpoints everything and never invents outputs.
"""
from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import pipelines
from .exporters import read_json
from .progress import write_progress_artifacts
from .project_manager import ApprovalRequired, ProjectManager
from .providers import ExternalAccessDisabled, ScholarlyProvider, make_providers
from .schemas import (
    AccessLevel,
    ProjectConfig,
    RunEvent,
    StepStatus,
    WorkflowPlan,
    WorkflowStep,
    utcnow,
)
from .skill_contracts import CONTRACTS
from .source_registry import SourceRegistry
from .validation import check_artifacts
from .workflow_state import PlanError, WorkflowState, ready_steps, validate_plan

# ---- intent routing (TZ 7.3). Keywords in English, Uzbek (Latin/Cyrillic) and Russian ---------------------
INTENTS: list[tuple[str, list[str], list[str]]] = [
    ("progress", [r"where am i", r"progress", r"status", r"qayerda", r"holat", r"jarayon", r"прогресс", r"статус", r"где я"],
     ["research-progress"]),
    ("writing", [r"\b(edit|polish|proofread|rewrite|tighten|improve (the|my) (english|writing|prose|text))\b", r"copy-?edit", r"language edit",
                 r"tahrirla", r"uslub", r"ilmiy uslub", r"отредактируй", r"улучши (текст|язык)", r"стил"],
     ["academic-writing"]),
    ("journal", [r"journal (requirements|guidelines|standards|format)", r"reporting (guideline|checklist)", r"\b(consort|strobe|stard|tripod|prisma|arrive)\b",
                 r"submission (ready|readiness|checklist)", r"adapt (to|for) (the )?journal", r"cover letter", r"xalqaro (nashr )?standart", r"jurnal talab", r"moslashtir",
                 r"требован\w* журнала", r"стандарт\w* публикац", r"сопроводительн"],
     ["journal-standards"]),
    ("audit", [r"\baudit", r"check (my|the) (manuscript|citations|references)", r"tekshir", r"audit", r"проверь", r"аудит"],
     ["citation-verifier", "academic-integrity", "journal-standards", "peer-reviewer"]),
    ("manuscript", [r"prepare (my|the|an?) (article|manuscript|paper)", r"write (my|the|an?) (article|manuscript|paper)", r"draft", r"maqola(ni)? (tayyorla|yoz)",
                    r"qo'lyozma", r"подготов\w* стать", r"напиш\w* стать", r"рукопис"],
     ["manuscript-builder", "academic-writing", "citation-verifier", "academic-integrity", "journal-standards", "peer-reviewer"]),
    ("gaps", [r"research gap", r"\bgaps?\b", r"bo'shliq", r"пробел", r"gap"],
     ["literature-search", "paper-analyzer", "literature-review", "research-gap-finder"]),
    ("compare", [r"compare", r"comparison", r"matrix", r"synthes", r"review (these|the) papers", r"taqqosla", r"solishtir", r"сравн", r"обзор"],
     ["paper-analyzer", "literature-review"]),
    ("analyze", [r"analy[sz]e", r"this pdf", r"summari[sz]e (this|the) (paper|pdf|article)", r"tahlil", r"pdf", r"проанализ", r"анализ"],
     ["paper-analyzer"]),
    ("search", [r"find (\d+ )?(papers|articles|studies|literature)", r"search", r"literature", r"maqola(lar)?(ni)? top", r"maqola(lar)?", r"adabiyot", r"izla", r"qidir",
                r"найд", r"поиск", r"литератур", r"стать"],
     ["literature-search"]),
]


def detect_intent(text: str) -> tuple[str, list[str]]:
    t = text.lower()
    for key, patterns, chain in INTENTS:
        if any(re.search(p, t) for p in patterns):
            return key, list(chain)
    return "ambiguous", []


def extract_constraints(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    m = re.search(r"\b(\d{1,3})\s*(papers|articles|studies|ta maqola|maqola|статей|статьи)", text.lower())
    if m:
        out["target_count"] = int(m.group(1))
    years = re.findall(r"\b(19|20)(\d{2})\b", text)
    if years:
        ys = sorted(int(a + b) for a, b in years)
        out["year_from"] = ys[0]
        if len(ys) > 1:
            out["year_to"] = ys[-1]
    return out


# ---- planning ------------------------------------------------------------------------------------------
def build_plan(pm: ProjectManager, request_text: str, *, overrides: dict[str, Any] | None = None, chain: list[str] | None = None) -> WorkflowPlan:
    cfg = pm.load_config()
    intent, default_chain = detect_intent(request_text)
    chain = chain or default_chain
    constraints = {**extract_constraints(request_text), **(overrides or {})}
    plan = WorkflowPlan(run_id=f"run-{utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}", project=cfg.slug,
                        goal=f"{intent}: {request_text.strip()[:120]}", request_text=request_text)
    if not chain:
        plan.warnings.append("ambiguous request: orchestrator must ask the user which deliverable is wanted; no steps planned")
        return plan
    registry = SourceRegistry(pm.workspace)
    analyzed = pipelines.analyzed_source_ids(pm)
    target = int(constraints.get("target_count") or cfg.budget.max_papers_per_search if "target_count" in constraints else 20)
    prev_id: str | None = None
    for i, skill in enumerate(chain, start=1):
        c = CONTRACTS[skill]
        step = WorkflowStep(id=f"s{i}", skill=skill, produces=list(c.required_outputs), executor=c.executor, api_cost=c.api_cost,
                            depends_on=[prev_id] if prev_id else [])
        # ---- reuse verified outputs / skip unneeded work --------------------------------------------
        if skill == "literature-search":
            step.inputs = {"topic": constraints.get("topic") or cfg.topic, "year_from": constraints.get("year_from", cfg.year_from),
                           "year_to": constraints.get("year_to", cfg.year_to), "target_count": target,
                           "fetch_full_text": bool(constraints.get("fetch_full_text", True)) and cfg.privacy.allow_external_apis}
            if len(registry) >= target and check_artifacts(pm.workspace, list(c.required_outputs), ["literature", "sources"]).ok:
                step.status = StepStatus.SKIPPED
                step.notes = f"registry already holds {len(registry)} sources (>= {target}); reuse. Re-run explicitly to search again."
            if target > cfg.budget.max_papers_per_search:
                step.approval_required, step.approval_reason = True, f"target_count {target} exceeds budget {cfg.budget.max_papers_per_search}"
            if not cfg.privacy.allow_external_apis:
                step.approval_required, step.approval_reason = True, "privacy.allow_external_apis is false; external search needs explicit approval"
        elif skill == "paper-analyzer":
            wanted = constraints.get("source_ids") or [s.source_id for s in registry.all()]
            if constraints.get("full_text_only"):
                wanted = [s for s in wanted if registry.get(s) and registry.get(s).access_level == AccessLevel.FULL_TEXT]
            todo = [s for s in wanted if s not in analyzed]
            search_pending = any(st.skill == "literature-search" and st.status == StepStatus.PLANNED for st in plan.steps)
            step.inputs = {"source_ids": todo, "already_analyzed": sorted(set(wanted) & analyzed), "question": constraints.get("question"),
                           "fetch_full_text": cfg.privacy.allow_external_apis}
            step.notes = f"{len(set(wanted) & analyzed)} source(s) already analyzed and reused; {len(todo)} to analyze"
            if search_pending:
                step.inputs["source_ids"] = "resolve after literature-search completes (rtk sources list); analyze only sources the user selected"
                step.notes = "source list resolved at run time from the new search results; already-analyzed sources are reused"
            elif not todo and (set(wanted) & analyzed):
                step.status = StepStatus.SKIPPED
            if not registry.all() and "literature-search" not in chain:
                step.status = StepStatus.BLOCKED
                step.error = "no sources registered; provide a PDF/DOI or run literature-search first"
        elif skill == "literature-review":
            step.inputs = {"source_ids": constraints.get("source_ids") or "all-analyzed"}
            ev_path = pm.workspace / "literature" / "review-evidence.json"
            if ev_path.exists() and check_artifacts(pm.workspace, list(c.required_outputs), ["literature"]).ok:
                covered = set(read_json(ev_path).get("sources", []))
                if analyzed and covered >= analyzed:
                    step.status = StepStatus.SKIPPED
                    step.notes = "literature matrix already covers every analyzed source"
        elif skill == "citation-verifier":
            step.inputs = {"manuscript_path": constraints.get("manuscript_path"), "bib_path": constraints.get("bib_path")}
            if not constraints.get("manuscript_path"):
                step.executor = "host-skill"
                step.notes = "manuscript_path not given: orchestrator must ask the user which manuscript to audit, then run `rtk verify-citations`"
            if not cfg.privacy.allow_external_apis:
                step.notes = (step.notes or "") + " external DOI resolution disabled; format-only audit"
        elif skill == "manuscript-builder":
            step.inputs = {"journal": cfg.target_journal, "author_facts": "REQUIRED from user", "existing_draft": constraints.get("manuscript_path")}
            step.approval_required, step.approval_reason = True, "drafting writes manuscript files; author must confirm facts/results exist and approve drafting"
        elif skill == "academic-integrity":
            step.inputs = {"ai_use": "REQUIRED: tools, stages, human review (as stated by author)", "journal_policy": cfg.target_journal}
        elif skill == "peer-reviewer":
            step.inputs = {"manuscript_path": constraints.get("manuscript_path"), "field": cfg.field, "journal": cfg.target_journal}
        elif skill == "research-gap-finder":
            step.inputs = {"scope": cfg.topic, "constraints": constraints.get("constraints")}
        elif skill == "academic-writing":
            step.inputs = {"manuscript_path": constraints.get("manuscript_path"), "journal_style": cfg.target_journal}
            if not constraints.get("manuscript_path") and "manuscript-builder" not in chain:
                step.notes = "manuscript_path not given: ask the user which text to edit"
        elif skill == "journal-standards":
            step.inputs = {"manuscript_path": constraints.get("manuscript_path"), "guideline": constraints.get("guideline", "generic"), "journal": cfg.target_journal}
            if not cfg.target_journal:
                step.notes = "target_journal not set: formatting limits will be reported as not checked unless the user supplies guidelines"
        plan.steps.append(step)
        prev_id = step.id
    plan.approval_required = any(s.approval_required for s in plan.steps)
    if plan.approval_required:
        plan.warnings.append("one or more steps need explicit user approval before execution")
    if len(plan.steps) > cfg.limits.max_stages:
        plan.warnings.append(f"plan truncated: max_stages={cfg.limits.max_stages}")
        plan.steps = plan.steps[: cfg.limits.max_stages]
    problems = validate_plan(plan, cfg.limits)
    if problems:
        raise PlanError("; ".join(problems))
    return plan


def save_new_plan(pm: ProjectManager, plan: WorkflowPlan) -> WorkflowPlan:
    state = WorkflowState(pm.workspace)
    state.save_plan(plan)
    state.log(RunEvent(run_id=plan.run_id, event="plan_created", status=plan.status.value, message=plan.goal))
    for s in plan.steps:
        if s.status in (StepStatus.SKIPPED, StepStatus.BLOCKED):
            state.log(RunEvent(run_id=plan.run_id, step_id=s.id, skill=s.skill, event=f"step_{s.status.value}", status=s.status.value, message=s.notes, error=s.error))
    return plan


def plan_preview(plan: WorkflowPlan) -> str:
    lines = [f"Plan {plan.run_id} — {plan.goal}", f"status: {plan.status.value}; approval required: {plan.approval_required}"]
    for s in plan.steps:
        flag = " [NEEDS APPROVAL: " + (s.approval_reason or "") + "]" if s.approval_required and not s.approved else ""
        dep = f" (after {', '.join(s.depends_on)})" if s.depends_on else ""
        lines.append(f"  {s.id}: {s.skill}{dep} · executor={s.executor} · api_cost={s.api_cost.value} · status={s.status.value}{flag}")
        if s.notes:
            lines.append(f"      note: {s.notes}")
        if s.error:
            lines.append(f"      error: {s.error}")
        lines.append(f"      produces: {', '.join(s.produces)}")
    for w in plan.warnings:
        lines.append(f"  ! {w}")
    return "\n".join(lines)


# ---- execution -----------------------------------------------------------------------------------------
EngineHandler = Callable[[ProjectManager, WorkflowPlan, WorkflowStep, dict[str, Any]], dict[str, Any]]


def _h_literature_search(pm, plan, step, ctx):
    provs: list[ScholarlyProvider] = ctx.get("providers") or make_providers()
    res = pipelines.literature_search(pm, topic=step.inputs["topic"], providers=provs, year_from=step.inputs.get("year_from"),
                                      year_to=step.inputs.get("year_to"), target_count=int(step.inputs.get("target_count") or 20),
                                      run_id=plan.run_id, step_id=step.id)
    if step.inputs.get("fetch_full_text") and res.get("selected"):
        from .fulltext import fetch_full_text

        try:
            res["fulltext"] = fetch_full_text(pm, res["selected"], fetcher=ctx.get("fetcher"), run_id=plan.run_id, step_id=step.id)["counts"]
        except Exception as exc:  # noqa: BLE001 - fetching is best effort; the search itself succeeded
            res["errors"] = (res.get("errors") or []) + [f"full-text fetch: {type(exc).__name__}: {exc}"]
    return res


def _h_citation_verifier(pm, plan, step, ctx):
    mp = step.inputs.get("manuscript_path")
    if not mp:
        raise pipelines.StepBlocked("manuscript_path missing; ask the user which manuscript to audit")
    cfg: ProjectConfig = pm.load_config()
    provs = None if not cfg.privacy.allow_external_apis else (ctx.get("providers") or make_providers(("crossref", "openalex")))
    return pipelines.audit_citations(pm, mp, step.inputs.get("bib_path"), providers=provs, run_id=plan.run_id, step_id=step.id)


def _h_research_progress(pm, plan, step, ctx):
    return write_progress_artifacts(pm, run_id=plan.run_id, step_id=step.id)


ENGINE_HANDLERS: dict[str, EngineHandler] = {
    "literature-search": _h_literature_search,
    "citation-verifier": _h_citation_verifier,
    "research-progress": _h_research_progress,
}


def run_step(pm: ProjectManager, plan: WorkflowPlan, step_id: str, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute one engine step with checkpoints. Host-skill steps are not executed here."""
    cfg = pm.load_config()
    state = WorkflowState(pm.workspace)
    step = plan.step(step_id)
    if step.executor != "engine":
        return {"step": step_id, "status": step.status.value,
                "message": f"{step.skill} is executed by the host agent via its SKILL.md; call `rtk step start/complete` around it"}
    handler = ENGINE_HANDLERS.get(step.skill)
    if handler is None:
        return {"step": step_id, "status": step.status.value, "message": "no engine handler"}
    state.start_step(plan, step_id, cfg.limits)
    try:
        result = handler(pm, plan, step, context or {})
    except pipelines.StepBlocked as exc:
        state.finish_step(plan, step_id, StepStatus.BLOCKED, error=str(exc), artifacts=exc.partial_artifacts,
                          message="partial artifacts preserved; see error")
        return {"step": step_id, "status": "blocked", "error": str(exc), "partial_artifacts": exc.partial_artifacts}
    except (ApprovalRequired, ExternalAccessDisabled) as exc:
        state.finish_step(plan, step_id, StepStatus.BLOCKED, error=str(exc), message="awaiting user authorization")
        return {"step": step_id, "status": "blocked", "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - any failure must be recorded truthfully
        state.finish_step(plan, step_id, StepStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
        return {"step": step_id, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    warnings = result.get("errors") or []
    state.finish_step(plan, step_id, StepStatus.COMPLETED, artifacts=result.get("artifacts", []),
                      message=("provider warnings: " + "; ".join(warnings)) if warnings else None)
    return {"step": step_id, "status": plan.step(step_id).status.value, "result": result}


def run_ready(pm: ProjectManager, plan: WorkflowPlan, *, context: dict[str, Any] | None = None, max_steps: int = 20) -> list[dict[str, Any]]:
    """Run engine steps that are ready, in dependency order, until a host-skill step or a block is reached."""
    results: list[dict[str, Any]] = []
    for _ in range(max_steps):
        ready = [s for s in ready_steps(plan) if not (s.approval_required and not s.approved)]
        engine_ready = [s for s in ready if s.executor == "engine"]
        if not engine_ready:
            break
        res = run_step(pm, plan, engine_ready[0].id, context=context)
        results.append(res)
        if res["status"] in ("blocked", "failed"):
            break
    return results


def final_report(pm: ProjectManager, plan: WorkflowPlan) -> dict[str, Any]:
    """Report that only lists files which really exist on disk (acceptance test 10)."""
    state = WorkflowState(pm.workspace)
    ws = Path(pm.workspace)
    completed, blocked, pending, awaiting = [], [], [], []
    files: list[str] = []
    for s in plan.steps:
        entry = {"step": s.id, "skill": s.skill, "status": s.status.value, "error": s.error, "notes": s.notes}
        if s.status == StepStatus.COMPLETED:
            found = []
            for name in s.produces:
                hits = [p.relative_to(ws).as_posix() for p in ws.rglob(name) if "history" not in p.parts]
                found.extend(hits)
            entry["files"] = sorted(set(found))
            files.extend(entry["files"])
            completed.append(entry)
        elif s.status in (StepStatus.BLOCKED, StepStatus.FAILED):
            blocked.append(entry)
        elif s.status == StepStatus.AWAITING_USER_REVIEW:
            awaiting.append(entry)
        elif s.status == StepStatus.PLANNED:
            pending.append(entry)
    next_steps = []
    for s in ready_steps(plan):
        if s.approval_required and not s.approved:
            next_steps.append(f"approve {s.id} ({s.skill}): {s.approval_reason}")
        elif s.executor == "engine":
            next_steps.append(f"run engine step {s.id} ({s.skill}): rtk run --step {s.id}")
        else:
            next_steps.append(f"host agent executes {s.id} ({s.skill}) per skills/{s.skill}/SKILL.md, then `rtk step complete {s.id}`")
    return {
        "run_id": plan.run_id,
        "status": plan.status.value,
        "completed": completed,
        "blocked": blocked,
        "awaiting_user_review": awaiting,
        "pending": pending,
        "skipped": [{"step": s.id, "skill": s.skill, "notes": s.notes} for s in plan.steps if s.status == StepStatus.SKIPPED],
        "files": sorted(set(files)),
        "warnings": plan.warnings,
        "next_steps": next_steps,
        "events_logged": len(state.events(plan.run_id)),
    }
