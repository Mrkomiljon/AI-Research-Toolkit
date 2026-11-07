"""TZ 7.7 acceptance tests for research-orchestrator (1-8, 10 here; 9 = cross-agent, see test_cross_agent.py)."""
import json

import pytest

from research_toolkit import pipelines
from research_toolkit.cli import main as rtk
from research_toolkit.orchestrator import (
    build_plan,
    detect_intent,
    extract_constraints,
    final_report,
    run_ready,
    run_step,
    save_new_plan,
)
from research_toolkit.progress import compute_status, reconcile_summary_with_disk
from research_toolkit.project_manager import ApprovalRequired
from research_toolkit.schemas import StepStatus
from research_toolkit.source_registry import SourceRegistry, new_source
from research_toolkit.workflow_state import WorkflowState, ready_steps
from tests.conftest import FULL_TEXT_PAGES, make_pdf
from tests.integration.test_pipelines import _analysis


@pytest.mark.parametrize("text,expected", [
    ("Find 20 papers about ML crop yield prediction since 2021", "search"),
    ("Analyze this PDF for me", "analyze"),
    ("Compare these papers on irrigation", "compare"),
    ("Find research gaps in soil moisture sensing", "gaps"),
    ("Prepare my article for Field Crops Research", "manuscript"),
    ("Audit this manuscript", "audit"),
    ("Where am I in my research?", "progress"),
    ("Tadqiqotimda qayerdaman?", "progress"),
    ("Mavzu bo'yicha 15 ta maqola top", "search"),
    ("Найди пробелы в исследованиях по урожайности", "gaps"),
    ("Проверь рукопись", "audit"),
    ("hello", "ambiguous"),
])
def test_routing_multilingual(text, expected):
    assert detect_intent(text)[0] == expected


def test_extract_constraints():
    c = extract_constraints("Find 15 papers from 2019 to 2024")
    assert c == {"target_count": 15, "year_from": 2019, "year_to": 2024}


# 1. multi-step request -> validated plan and sequential artifacts
def test_1_multistep_plan_and_sequential_artifacts(workspace, mock_providers):
    plan = build_plan(workspace, "Find 5 papers about ML crop yield prediction since 2021 and find research gaps")
    assert [s.skill for s in plan.steps] == ["literature-search", "paper-analyzer", "literature-review", "research-gap-finder"]
    assert plan.steps[1].depends_on == ["s1"] and plan.steps[0].executor == "engine" and plan.steps[0].api_cost.value == "low"
    assert plan.steps[0].inputs["target_count"] == 5 and plan.steps[0].inputs["year_from"] == 2021
    save_new_plan(workspace, plan)
    assert WorkflowState(workspace.workspace).plan_path.exists()
    results = run_ready(workspace, plan, context={"providers": mock_providers})
    assert len(results) == 1 and results[0]["status"] == "completed"
    assert plan.step("s1").status == StepStatus.COMPLETED and [s.id for s in ready_steps(plan)] == ["s2"]
    rep = final_report(workspace, plan)
    assert "literature/papers.csv" in rep["files"] and rep["next_steps"] and "paper-analyzer" in rep["next_steps"][0]
    status = compute_status(workspace)
    assert status.stages["literature-search"].status == "completed"


# 2. previously verified paper is not re-analyzed
def test_2_no_reanalysis_without_reason(workspace, full_text_pdf):
    reg = SourceRegistry(workspace.workspace)
    src = new_source("Maize yield prediction with random forests", year=2021, doi="10.1000/test.0", pdf_path="papers/PDFs/paper-full.pdf")
    reg.add(src)
    s2 = new_source("Not yet analyzed", year=2022, doi="10.1000/test.5")
    reg.add(s2)
    reg.save()
    pipelines.prepare_paper_analysis(workspace, src.source_id)
    pipelines.finalize_paper_analysis(workspace, src.source_id, _analysis(src.source_id))
    plan = build_plan(workspace, "Compare these papers", overrides={"source_ids": [src.source_id, s2.source_id]})
    step = plan.step("s1")
    assert step.skill == "paper-analyzer" and step.inputs["source_ids"] == [s2.source_id] and step.inputs["already_analyzed"] == [src.source_id]
    plan2 = build_plan(workspace, "Compare these papers", overrides={"source_ids": [src.source_id]})
    assert plan2.step("s1").status == StepStatus.SKIPPED
    # literature-search is skipped when the registry already satisfies the request and artifacts exist
    for name in ("search-strategy.md", "papers.xlsx", "papers.csv", "search-log.json"):
        (workspace.workspace / "literature" / name).write_text("x", encoding="utf-8")
    plan3 = build_plan(workspace, "Find 2 papers about yield")
    assert plan3.step("s1").status == StepStatus.SKIPPED


# 3. missing PDF -> abstract-only / full-text claims blocked
def test_3_missing_pdf_downgrade(workspace):
    reg = SourceRegistry(workspace.workspace)
    src = new_source("No pdf paper", year=2022, doi="10.1000/test.1", abstract="An abstract.", pdf_path="papers/PDFs/missing.pdf")
    reg.add(src)
    reg.save()
    prep = pipelines.prepare_paper_analysis(workspace, src.source_id)
    assert prep["access_level"] == "ABSTRACT_ONLY"
    with pytest.raises(pipelines.StepBlocked):
        pipelines.finalize_paper_analysis(workspace, src.source_id, _analysis(src.source_id, access="FULL_TEXT"))


# 4. invalid DOI does not pass citation verification
def test_4_invalid_doi_fails_verification(workspace, mock_providers):
    reg = SourceRegistry(workspace.workspace)
    bad = new_source("Fabricated reference", year=2020, doi="10.1000/does-not-exist")
    reg.add(bad)
    reg.save()
    (workspace.workspace / "manuscript" / "m.md").write_text(f"# M\n\nClaim [{bad.source_id}].\n", encoding="utf-8")
    plan = build_plan(workspace, "Audit this manuscript", overrides={"manuscript_path": "manuscript/m.md"})
    save_new_plan(workspace, plan)
    res = run_step(workspace, plan, "s1", context={"providers": mock_providers})
    assert res["status"] == "completed" and bad.source_id in res["result"]["failures"] and res["result"]["passed"] is False
    assert [a for a in workspace.artifacts() if a.type == "citation-audit.md"][0].validation_status.value == "invalid"


# 5. stops before external transmission of confidential files
def test_5_external_transmission_gate(workspace):
    (workspace.workspace / "papers" / "PDFs" / "unpublished.pdf").write_bytes(b"%PDF")
    with pytest.raises(ApprovalRequired):
        workspace.check_external_transmission(["papers/PDFs/unpublished.pdf"])
    with pytest.raises(SystemExit) as e:
        rtk(["privacy-check", "-p", str(workspace.workspace), "papers/PDFs/unpublished.pdf"])
    assert e.value.code == 3
    rtk(["privacy-check", "-p", str(workspace.workspace), "papers/PDFs/unpublished.pdf", "--authorized"])
    cfg = workspace.load_config()
    cfg.privacy.allow_external_apis = False
    workspace.save_config(cfg)
    plan = build_plan(workspace, "Find 3 papers on yield")
    assert plan.step("s1").approval_required and "privacy" in plan.step("s1").approval_reason
    save_new_plan(workspace, plan)
    assert run_ready(workspace, plan) == []  # gated step is not run without approval


# 6. failed API step -> partial artifacts + truthful blocked status
def test_6_failed_api_step_blocked_with_partials(workspace, failing_providers):
    plan = build_plan(workspace, "Find 4 papers on yield")
    save_new_plan(workspace, plan)
    res = run_step(workspace, plan, "s1", context={"providers": failing_providers})
    assert res["status"] == "blocked" and any("search-log.json" in p for p in res["partial_artifacts"])
    assert plan.step("s1").status == StepStatus.BLOCKED and "unavailable" in plan.step("s1").error
    events = WorkflowState(workspace.workspace).events(plan.run_id)
    assert events[-1].event == "step_blocked"
    rep = final_report(workspace, plan)
    assert rep["blocked"][0]["step"] == "s1" and rep["status"] == "blocked"
    assert compute_status(workspace).stages["literature-search"].status == "blocked"


# 7. interruption persists state; resume skips finished valid steps
def test_7_interrupt_and_resume(workspace, mock_providers):
    plan = build_plan(workspace, "Find 3 papers about yield and find research gaps")
    save_new_plan(workspace, plan)
    run_ready(workspace, plan, context={"providers": mock_providers})
    cfg = workspace.load_config()
    WorkflowState(workspace.workspace).start_step(plan, "s2", cfg.limits)  # host step running, then "crash"
    del plan
    state = WorkflowState(workspace.workspace)
    reloaded = state.load_plan()
    assert reloaded.step("s1").status == StepStatus.COMPLETED and reloaded.step("s2").status == StepStatus.RUNNING
    summary = state.resume(reloaded)
    assert summary["kept"] == ["s1"] and summary["reset"] == ["s2"] and summary["ready"] == ["s2"]
    assert run_ready(workspace, reloaded, context={"providers": mock_providers}) == []  # s1 not repeated
    assert reloaded.step("s1").attempts == 1


# 8. injected instruction in a PDF does not change orchestration rules
def test_8_prompt_injection_does_not_alter_plan(workspace, hostile_pdf):
    reg = SourceRegistry(workspace.workspace)
    src = new_source("Hostile wheat paper", year=2023, doi="10.1000/test.2", pdf_path="papers/PDFs/hostile.pdf")
    reg.add(src)
    reg.save()
    plan = build_plan(workspace, "Analyze this PDF", overrides={"source_ids": [src.source_id]})
    save_new_plan(workspace, plan)
    before = json.dumps(plan.model_dump(mode="json"), sort_keys=True, default=str)
    prep = pipelines.prepare_paper_analysis(workspace, src.source_id)
    assert prep["injection_findings"]
    after = WorkflowState(workspace.workspace).load_plan()
    assert json.dumps(after.model_dump(mode="json"), sort_keys=True, default=str) == before
    assert after.step("s1").status == StepStatus.PLANNED  # not "marked complete", verification not skipped
    assert "verification" not in json.dumps([s.status.value for s in after.steps])


# 10. workflow summary matches artifacts on disk
def test_10_summary_matches_disk(workspace, mock_providers):
    plan = build_plan(workspace, "Find 3 papers on yield")
    save_new_plan(workspace, plan)
    run_ready(workspace, plan, context={"providers": mock_providers})
    rep = final_report(workspace, plan)
    rec = reconcile_summary_with_disk(workspace, rep["files"])
    assert rec["absent"] == [] and set(rec["present"]) == set(rep["files"]) and len(rep["files"]) == 5
    (workspace.workspace / "literature" / "papers.csv").unlink()
    assert "literature/papers.csv" not in final_report(workspace, plan)["files"]
    assert "s1" in WorkflowState(workspace.workspace).resume(plan)["invalidated"]


def test_ambiguous_request_plans_nothing(workspace):
    plan = build_plan(workspace, "hello there")
    assert plan.steps == [] and "ambiguous" in plan.warnings[0]


def test_cli_end_to_end_offline(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RTK_ALLOW_EXTERNAL_APIS", "0")
    rtk(["init", "--workspace", str(tmp_path), "--slug", "cli-demo", "--topic", "demo", "--no-external-apis", "--ack-cloud"])
    ws = str(tmp_path / "cli-demo")
    rtk(["plan", "-p", ws, "Where am I in my research?"])
    out = capsys.readouterr().out
    assert "research-progress" in out
    rtk(["--json", "run", "-p", ws])
    data = json.loads(capsys.readouterr().out)
    assert data["results"][0]["status"] == "completed"
    rtk(["report", "-p", ws])
    rep = json.loads(capsys.readouterr().out)
    assert "progress/project-status.json" in rep["files"]
    make_pdf(tmp_path / "cli-demo" / "papers" / "PDFs" / "p.pdf", FULL_TEXT_PAGES)
    rtk(["sources", "add", "-p", ws, "--title", "Maize yield prediction with random forests", "--year", "2021", "--doi", "10.1000/test.0", "--pdf", "papers/PDFs/p.pdf"])
    sid = json.loads(capsys.readouterr().out)["source_id"]
    rtk(["analyze", "prepare", "-p", ws, sid])
    assert json.loads(capsys.readouterr().out)["access_level"] == "FULL_TEXT"
    (tmp_path / "a.json").write_text(json.dumps(_analysis(sid)), encoding="utf-8")
    rtk(["analyze", "finalize", "-p", ws, sid, "--analysis-json", str(tmp_path / "a.json")])
    assert json.loads(capsys.readouterr().out)["problems"] == []
    rtk(["plan", "-p", ws, "Compare these papers"])
    out = capsys.readouterr().out
    assert "already analyzed" in out
    rtk(["step", "start", "-p", ws, "s2"])
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:  # unknown step id is refused with exit code 2
        rtk(["step", "complete", "-p", ws, "s9"])
    assert e.value.code == 2
    capsys.readouterr()
    rtk(["step", "complete", "-p", ws, "s2"])  # no files on disk -> engine downgrades to blocked, never completed
    summary = json.loads(capsys.readouterr().out)
    assert [s for s in summary["steps"] if s["id"] == "s2"][0]["status"] == "blocked"
