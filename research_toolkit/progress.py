"""research-progress: status derived strictly from artifacts on disk, the artifact registry and run events."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .evidence_store import EvidenceStore
from .exporters import write_json, write_markdown, write_xlsx
from .project_manager import ProjectManager
from .schemas import AuthorReviewStatus, ProjectStatus, StageStatus, ValidationStatus
from .skill_contracts import CONTRACTS, PIPELINE_ORDER
from .source_registry import SourceRegistry
from .validation import check_artifacts
from .workflow_state import WorkflowState


def compute_status(pm: ProjectManager) -> ProjectStatus:
    cfg = pm.load_config()
    registry = SourceRegistry(pm.workspace)
    evidence = EvidenceStore(pm.workspace).all()
    artifacts = pm.artifacts()
    stats = registry.stats()
    state = WorkflowState(pm.workspace)
    events = state.events()
    status = ProjectStatus(
        project=cfg.slug,
        sources_total=stats["total"],
        sources_verified=stats["verified"],
        sources_full_text=stats["full_text"],
        evidence_total=len(evidence),
    )
    blockers: list[str] = []
    next_actions: list[str] = []
    for skill in PIPELINE_ORDER:
        if skill == "research-progress":
            continue
        c = CONTRACTS[skill]
        check = check_artifacts(pm.workspace, list(c.required_outputs), [c.output_dir, "sources"])
        regs = [a for a in artifacts if a.skill == skill]
        stage = StageStatus(skill=skill, artifacts=sorted({a.path for a in regs}), missing_required=check.missing + check.empty)
        last_events = [e for e in events if e.skill == skill]
        if last_events:
            stage.last_run_id = last_events[-1].run_id
            stage.last_updated = last_events[-1].ts
        invalid = [a.path for a in regs if a.validation_status == ValidationStatus.INVALID]
        pending_review = [a.path for a in regs if a.author_review_status == AuthorReviewStatus.PENDING]
        rejected = [a.path for a in regs if a.author_review_status == AuthorReviewStatus.REJECTED]
        last_terminal = last_events[-1].status if last_events else None
        if check.ok and not invalid and not rejected:
            if c.needs_author_review and pending_review:
                stage.status = "awaiting_user_review"
                next_actions.append(f"Review and approve {skill} outputs: {', '.join(pending_review[:3])}")
            else:
                stage.status = "completed"
        elif last_terminal in ("blocked", "failed"):
            stage.status = "blocked"
            err = last_events[-1].error or last_events[-1].message or "see workflow/runs.jsonl"
            stage.blockers.append(err)
            blockers.append(f"{skill}: {err}")
        elif stage.artifacts or (check.present and not check.ok):
            stage.status = "in_progress"
            if invalid:
                stage.blockers.append("invalid artifacts: " + ", ".join(invalid))
                blockers.append(f"{skill}: invalid artifacts {invalid}")
            if rejected:
                stage.blockers.append("author rejected: " + ", ".join(rejected))
        else:
            stage.status = "not_started"
        status.stages[skill] = stage
    status.stages_total = len(status.stages)
    status.stages_completed = sum(1 for s in status.stages.values() if s.status == "completed")
    # evidence-based next actions
    if stats["total"] == 0:
        next_actions.insert(0, "Run literature-search (no sources registered yet)")
    elif status.stages["paper-analyzer"].status == "not_started":
        next_actions.append(f"Analyze available papers ({stats['full_text']} full-text, {stats['abstract_only']} abstract-only)")
    if status.stages["literature-review"].status == "completed" and status.stages["research-gap-finder"].status == "not_started":
        next_actions.append("Derive candidate research gaps from the literature matrix")
    if status.stages["research-gap-finder"].status in ("completed", "awaiting_user_review") and status.stages["gap-validator"].status == "not_started":
        next_actions.append("Validate candidate gaps with a targeted counterevidence search (gap-validator)")
    status.blockers = blockers
    status.next_actions = next_actions
    status.milestones = [
        {"milestone": f"{s.skill} completed", "reached": s.status == "completed", "evidence": s.artifacts[:5]}
        for s in status.stages.values()
    ]
    return status


def write_progress_artifacts(pm: ProjectManager, *, run_id: str | None = None, step_id: str | None = None) -> dict[str, Any]:
    status = compute_status(pm)
    prog = pm.workspace / "progress"
    js = write_json(prog / "project-status.json", status.model_dump(mode="json"))
    rows = [
        {"stage": s.skill, "status": s.status, "artifacts": "; ".join(s.artifacts), "missing_required": "; ".join(s.missing_required),
         "blockers": "; ".join(s.blockers), "last_run_id": s.last_run_id or "", "last_updated": s.last_updated.isoformat() if s.last_updated else ""}
        for s in status.stages.values()
    ]
    xlsx = write_xlsx({"stages": rows, "milestones": status.milestones}, prog / "research-progress.xlsx")
    md = write_markdown(
        prog / "next-actions.md",
        "Next actions",
        [
            ("Summary", f"- Stages completed: {status.stages_completed} of {status.stages_total} (counted from validated artifacts, not estimated)\n- Sources: {status.sources_total} (verified {status.sources_verified}, full text {status.sources_full_text})\n- Evidence records: {status.evidence_total}"),
            ("Blockers", "\n".join(f"- {b}" for b in status.blockers) or "- none"),
            ("Next actions", "\n".join(f"- {a}" for a in status.next_actions) or "- none"),
        ],
        front_note=status.derived_from,
    )
    for p in (js, xlsx, md):
        pm.register_artifact(p, skill="research-progress", run_id=run_id, step_id=step_id, validation_status=ValidationStatus.VALID)
    return {"status": status.model_dump(mode="json"), "artifacts": [str(js), str(xlsx), str(md)]}


def reconcile_summary_with_disk(pm: ProjectManager, claimed_paths: list[str]) -> dict[str, list[str]]:
    """Acceptance test 10: a workflow summary may only list files that exist."""
    ws = Path(pm.workspace)
    present, absent = [], []
    for rel in claimed_paths:
        (present if (ws / rel).exists() else absent).append(rel)
    return {"present": present, "absent": absent}
