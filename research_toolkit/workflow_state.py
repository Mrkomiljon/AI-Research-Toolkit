"""Workflow plan persistence (workflow/plan.yaml), event log (workflow/runs.jsonl), DAG rules and resume."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import yaml

from .schemas import OrchestratorLimits, RunEvent, StepStatus, WorkflowPlan, WorkflowStep, utcnow
from .validation import check_artifacts

TERMINAL_OK = {StepStatus.COMPLETED, StepStatus.SKIPPED}


class PlanError(ValueError):
    pass


def validate_plan(plan: WorkflowPlan, limits: OrchestratorLimits | None = None) -> list[str]:
    """Return a list of problems; an empty list means the plan is executable."""
    limits = limits or OrchestratorLimits()
    problems: list[str] = []
    ids = [s.id for s in plan.steps]
    if len(ids) != len(set(ids)):
        problems.append("duplicate step ids")
    if len(plan.steps) > limits.max_stages:
        problems.append(f"plan has {len(plan.steps)} steps; max_stages is {limits.max_stages}")
    if not plan.steps:
        problems.append("plan has no steps")
    known = set(ids)
    for s in plan.steps:
        for d in s.depends_on:
            if d not in known:
                problems.append(f"step {s.id} depends on unknown step {d}")
            if d == s.id:
                problems.append(f"step {s.id} depends on itself")
        if s.skill == "research-orchestrator":
            problems.append(f"step {s.id}: orchestrator must not schedule itself (no recursive chains)")
    if _has_cycle(plan.steps):
        problems.append("dependency cycle detected")
    return problems


def _has_cycle(steps: list[WorkflowStep]) -> bool:
    graph = {s.id: list(s.depends_on) for s in steps}
    state: dict[str, int] = {}

    def visit(n: str) -> bool:
        st = state.get(n, 0)
        if st == 1:
            return True
        if st == 2:
            return False
        state[n] = 1
        for m in graph.get(n, []):
            if m in graph and visit(m):
                return True
        state[n] = 2
        return False

    return any(visit(n) for n in graph)


def ready_steps(plan: WorkflowPlan) -> list[WorkflowStep]:
    """Steps whose dependencies are all completed/skipped and that are still planned."""
    done = {s.id for s in plan.steps if s.status in TERMINAL_OK}
    return [
        s
        for s in plan.steps
        if s.status == StepStatus.PLANNED and all(d in done for d in s.depends_on)
    ]


def blocked_by_dependency(plan: WorkflowPlan) -> list[WorkflowStep]:
    bad = {s.id for s in plan.steps if s.status in (StepStatus.FAILED, StepStatus.BLOCKED)}
    return [s for s in plan.steps if s.status == StepStatus.PLANNED and any(d in bad for d in s.depends_on)]


def derive_plan_status(plan: WorkflowPlan) -> StepStatus:
    statuses = {s.status for s in plan.steps}
    if statuses and statuses <= TERMINAL_OK:
        return StepStatus.COMPLETED
    if StepStatus.RUNNING in statuses:
        return StepStatus.RUNNING
    if StepStatus.AWAITING_USER_REVIEW in statuses:
        return StepStatus.AWAITING_USER_REVIEW
    if StepStatus.BLOCKED in statuses or StepStatus.FAILED in statuses:
        return StepStatus.BLOCKED
    return StepStatus.PLANNED


class WorkflowState:
    """Disk-backed state so a cancelled run can be resumed without repeating verified steps."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.plan_path = self.workspace / "workflow" / "plan.yaml"
        self.runs_path = self.workspace / "workflow" / "runs.jsonl"
        self.history_dir = self.workspace / "workflow" / "history"

    # ---- plan persistence ------------------------------------------------
    def has_plan(self) -> bool:
        return self.plan_path.exists()

    def load_plan(self) -> WorkflowPlan:
        if not self.plan_path.exists():
            raise FileNotFoundError(self.plan_path)
        return WorkflowPlan.model_validate(yaml.safe_load(self.plan_path.read_text(encoding="utf-8")))

    def save_plan(self, plan: WorkflowPlan) -> None:
        plan.updated_at = utcnow()
        plan.status = derive_plan_status(plan)
        self.plan_path.parent.mkdir(parents=True, exist_ok=True)
        self.plan_path.write_text(
            yaml.safe_dump(plan.model_dump(mode="json"), sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        self.history_dir.mkdir(parents=True, exist_ok=True)
        (self.history_dir / f"{plan.run_id}.yaml").write_text(self.plan_path.read_text(encoding="utf-8"), encoding="utf-8")

    # ---- event log -------------------------------------------------------
    def log(self, event: RunEvent) -> None:
        self.runs_path.parent.mkdir(parents=True, exist_ok=True)
        with self.runs_path.open("a", encoding="utf-8") as fh:
            fh.write(event.model_dump_json() + "\n")

    def events(self, run_id: str | None = None) -> list[RunEvent]:
        if not self.runs_path.exists():
            return []
        out = []
        for line in self.runs_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ev = RunEvent.model_validate_json(line)
                if run_id is None or ev.run_id == run_id:
                    out.append(ev)
        return out

    # ---- checkpoints -----------------------------------------------------
    def start_step(self, plan: WorkflowPlan, step_id: str, limits: OrchestratorLimits) -> WorkflowStep:
        step = plan.step(step_id)
        if step.approval_required and not step.approved:
            raise PlanError(f"step {step_id} requires explicit user approval: {step.approval_reason}")
        unmet = [d for d in step.depends_on if plan.step(d).status not in TERMINAL_OK]
        if unmet:
            raise PlanError(f"step {step_id} has unmet dependencies: {unmet}")
        if step.attempts >= limits.max_retries_per_step + 1:
            raise PlanError(f"step {step_id} exceeded max retries ({limits.max_retries_per_step})")
        step.status = StepStatus.RUNNING
        step.attempts += 1
        step.started_at = utcnow()
        step.error = None
        self.save_plan(plan)
        self.log(RunEvent(run_id=plan.run_id, step_id=step.id, skill=step.skill, event="step_started", status="running"))
        return step

    def finish_step(
        self,
        plan: WorkflowPlan,
        step_id: str,
        status: StepStatus,
        *,
        artifacts: list[str] | None = None,
        message: str | None = None,
        error: str | None = None,
    ) -> WorkflowStep:
        if status in (StepStatus.PLANNED, StepStatus.RUNNING):
            raise PlanError("finish_step needs a terminal or review status")
        step = plan.step(step_id)
        if status == StepStatus.COMPLETED:
            check = check_artifacts(self.workspace, step.produces)
            if not check.ok:
                status = StepStatus.BLOCKED
                error = f"declared outputs missing/empty: {check.missing + check.empty}"
        step.status = status
        step.finished_at = utcnow()
        step.error = error
        if message:
            step.notes = message
        self.save_plan(plan)
        self.log(
            RunEvent(
                run_id=plan.run_id,
                step_id=step.id,
                skill=step.skill,
                event=f"step_{status.value}",
                status=status.value,
                message=message,
                artifacts=artifacts or [],
                error=error,
            )
        )
        return step

    def approve_step(self, plan: WorkflowPlan, step_id: str) -> WorkflowStep:
        step = plan.step(step_id)
        step.approved = True
        self.save_plan(plan)
        self.log(RunEvent(run_id=plan.run_id, step_id=step_id, skill=step.skill, event="approval_granted"))
        return step

    def resume(self, plan: WorkflowPlan) -> dict:
        """Re-validate completed steps against disk; reset interrupted RUNNING steps; return a summary."""
        kept, reset, invalidated = [], [], []
        for s in plan.steps:
            if s.status == StepStatus.RUNNING:
                s.status = StepStatus.PLANNED
                s.notes = (s.notes or "") + " [interrupted; re-queued on resume]"
                reset.append(s.id)
            elif s.status == StepStatus.COMPLETED:
                check = check_artifacts(self.workspace, s.produces)
                if check.ok:
                    kept.append(s.id)
                else:
                    s.status = StepStatus.PLANNED
                    s.error = f"outputs no longer valid on disk: {check.missing + check.empty}"
                    invalidated.append(s.id)
        self.save_plan(plan)
        self.log(
            RunEvent(
                run_id=plan.run_id,
                event="run_resumed",
                message=json.dumps({"kept": kept, "reset": reset, "invalidated": invalidated}),
            )
        )
        return {"kept": kept, "reset": reset, "invalidated": invalidated, "ready": [s.id for s in ready_steps(plan)]}

    def summary(self, plan: WorkflowPlan) -> dict:
        return {
            "run_id": plan.run_id,
            "status": derive_plan_status(plan).value,
            "steps": [
                {
                    "id": s.id,
                    "skill": s.skill,
                    "status": s.status.value,
                    "executor": s.executor,
                    "api_cost": s.api_cost.value,
                    "approval_required": s.approval_required,
                    "approved": s.approved,
                    "produces": s.produces,
                    "error": s.error,
                    "attempts": s.attempts,
                }
                for s in plan.steps
            ],
            "ready": [s.id for s in ready_steps(plan)],
            "blocked_by_dependency": [s.id for s in blocked_by_dependency(plan)],
        }


def _dt(v: datetime | None) -> str | None:
    return v.isoformat() if v else None
