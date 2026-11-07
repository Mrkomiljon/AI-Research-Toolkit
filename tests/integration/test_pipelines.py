"""search -> registry; PDF -> evidence; analysis -> matrix -> gaps; draft -> citation/integrity/review."""
import json

import pytest

from research_toolkit import pipelines
from research_toolkit.evidence_store import EvidenceStore
from research_toolkit.exporters import read_json, read_xlsx
from research_toolkit.project_manager import ApprovalRequired
from research_toolkit.schemas import AccessLevel, VerificationStatus
from research_toolkit.source_registry import SourceRegistry, new_source


def test_search_to_registry_dedup_and_artifacts(workspace, mock_providers):
    res = pipelines.literature_search(workspace, topic="ml crop yield", providers=mock_providers, year_from=2021, target_count=5)
    reg = SourceRegistry(workspace.workspace)
    # openalex 6 + title-dup (merged) ; crossref 4 overlapping DOIs (merged) + 1 new => 7 unique
    assert len(reg) == 7
    assert res["coverage"]["delivered"] == 5 and res["coverage"]["shortfall"] == 0
    log = read_json(workspace.workspace / "literature" / "search-log.json")
    assert log["new_sources"] == 7 and log["merged_duplicates"] == 5
    for name in ("search-strategy.md", "papers.xlsx", "papers.csv", "search-log.json"):
        assert (workspace.workspace / "literature" / name).stat().st_size > 0
    assert (workspace.workspace / "sources" / "references.bib").stat().st_size > 0
    rows = read_xlsx(workspace.workspace / "literature" / "papers.xlsx")
    assert len(rows) == 5 and all(r["access_level"] in ("ABSTRACT_ONLY", "METADATA_ONLY") for r in rows)
    assert all(a.validation_status.value == "valid" for a in workspace.artifacts() if a.skill == "literature-search")


def test_search_budget_gate(workspace, mock_providers):
    with pytest.raises(pipelines.StepBlocked):
        pipelines.literature_search(workspace, topic="x", providers=mock_providers, target_count=999)


def test_search_all_providers_down_is_blocked_with_partial_log(workspace, failing_providers):
    with pytest.raises(pipelines.StepBlocked) as exc:
        pipelines.literature_search(workspace, topic="x", providers=failing_providers, target_count=5)
    assert any("search-log.json" in p for p in exc.value.partial_artifacts)
    log = read_json(workspace.workspace / "literature" / "search-log.json")
    assert all(p["status"] == "unavailable" for p in log["providers"])


def test_paid_api_unavailable_reported(workspace, paid_providers):
    with pytest.raises(pipelines.StepBlocked) as exc:
        pipelines.literature_search(workspace, topic="x", providers=paid_providers, target_count=5)
    assert "paid" in str(exc.value).lower() or "402" in str(exc.value)


def _register_full_text(workspace, full_text_pdf):
    reg = SourceRegistry(workspace.workspace)
    src = new_source("Maize yield prediction with random forests", authors=["Doe, J"], year=2021, doi="10.1000/test.0",
                     pdf_path="papers/PDFs/paper-full.pdf")
    reg.add(src)
    reg.save()
    return src.source_id


def _analysis(source_id, access="FULL_TEXT", bad_excerpt=False, page_locator=True):
    return {
        "source_id": source_id, "access_level": access, "question": "How accurate?",
        "fields": {
            "objective": {"summary": "Predict maize yield", "locator": "p.1" if page_locator else "abstract",
                          "excerpt": "We predict maize yield with random forests using satellite data." if not bad_excerpt else "This sentence is not in the paper."},
            "methods": {"summary": "Random forest on 2,400 observations", "locator": "p.2" if page_locator else "abstract", "excerpt": None},
            "sample": {"summary": "120 farms in Iowa", "locator": "p.2" if page_locator else "abstract", "excerpt": "Data came from 120 farms in Iowa."},
            "outcomes": {"summary": "RMSE 0.41 t/ha", "locator": "p.3" if page_locator else "abstract", "excerpt": "The model reached an RMSE of 0.41 t/ha on held-out fields."},
            "limitations": {"summary": "Single region and crop", "locator": "p.3" if page_locator else "abstract", "excerpt": None},
        },
    }


def test_pdf_to_evidence_full_text(workspace, full_text_pdf):
    sid = _register_full_text(workspace, full_text_pdf)
    prep = pipelines.prepare_paper_analysis(workspace, sid)
    assert prep["access_level"] == "FULL_TEXT" and prep["pages"] == 3 and prep["injection_findings"] == []
    res = pipelines.finalize_paper_analysis(workspace, sid, _analysis(sid))
    assert res["problems"] == [] and len(res["evidence_ids"]) == 5
    ev = EvidenceStore(workspace.workspace).for_source(sid)
    by_claim = {e.claim.split("]")[0][1:]: e for e in ev}
    assert by_claim["objective"].verification_status == VerificationStatus.VERIFIED and by_claim["objective"].verified_by.value == "tool"
    assert by_claim["methods"].verification_status == VerificationStatus.UNVERIFIED  # paraphrase stays unverified
    assert by_claim["outcomes"].locator == "p.3"
    assert (workspace.workspace / "analysis" / sid / "paper-analysis.md").exists()
    # wrong excerpt is rejected
    res2 = pipelines.finalize_paper_analysis(workspace, sid, _analysis(sid, bad_excerpt=True))
    assert any("excerpt not found" in p for p in res2["problems"])


def test_missing_pdf_downgrades_to_abstract_only(workspace):
    reg = SourceRegistry(workspace.workspace)
    src = new_source("Abstract only paper", year=2022, doi="10.1000/test.1", abstract="Yield prediction with ML.",
                     access_level=AccessLevel.FULL_TEXT, pdf_path="papers/PDFs/does-not-exist.pdf")
    reg.add(src)
    reg.save()
    prep = pipelines.prepare_paper_analysis(workspace, src.source_id)
    assert prep["access_level"] == "ABSTRACT_ONLY"
    assert SourceRegistry(workspace.workspace).get(src.source_id).access_level == AccessLevel.ABSTRACT_ONLY
    # page locators are not permitted; claiming FULL_TEXT is blocked
    with pytest.raises(pipelines.StepBlocked):
        pipelines.finalize_paper_analysis(workspace, src.source_id, _analysis(src.source_id, access="FULL_TEXT"))
    res = pipelines.finalize_paper_analysis(workspace, src.source_id, _analysis(src.source_id, access="ABSTRACT_ONLY"))
    assert all("not allowed for ABSTRACT_ONLY" in p for p in res["problems"]) and len(res["problems"]) == 5
    res = pipelines.finalize_paper_analysis(workspace, src.source_id, _analysis(src.source_id, access="ABSTRACT_ONLY", page_locator=False))
    assert res["problems"] == [] and all(e.locator == "abstract" for e in EvidenceStore(workspace.workspace).for_source(src.source_id))
    md = (workspace.workspace / "analysis" / src.source_id / "paper-analysis.md").read_text(encoding="utf-8")
    assert "ABSTRACT_ONLY" in md


def test_hostile_pdf_is_reported_not_obeyed(workspace, hostile_pdf):
    reg = SourceRegistry(workspace.workspace)
    src = new_source("Hostile wheat paper", year=2023, doi="10.1000/test.2", pdf_path="papers/PDFs/hostile.pdf")
    reg.add(src)
    reg.save()
    prep = pipelines.prepare_paper_analysis(workspace, src.source_id)
    assert len(prep["injection_findings"]) >= 2
    assert all(f["locator"] == "p.1" for f in prep["injection_findings"])
    extracted = read_json(workspace.workspace / "analysis" / src.source_id / "extracted-text.json")
    assert "must not be followed" in extracted["note"]


def test_analysis_to_matrix_to_gaps(workspace, full_text_pdf):
    sid = _register_full_text(workspace, full_text_pdf)
    pipelines.prepare_paper_analysis(workspace, sid)
    pipelines.finalize_paper_analysis(workspace, sid, _analysis(sid))
    reg = SourceRegistry(workspace.workspace)
    s2 = new_source("Second paper", year=2022, doi="10.1000/test.3", abstract="Yield prediction with ML.")
    reg.add(s2)
    reg.save()
    pipelines.prepare_paper_analysis(workspace, s2.source_id)
    pipelines.finalize_paper_analysis(workspace, s2.source_id, _analysis(s2.source_id, access="ABSTRACT_ONLY", page_locator=False))
    res = pipelines.build_literature_matrix(workspace)
    assert set(res["sources"]) == {sid, s2.source_id} and res["evidence_count"] == 10
    rows = read_xlsx(workspace.workspace / "literature" / "literature-matrix.xlsx")
    assert len(rows) == 2 and {r["access_level"] for r in rows} == {"FULL_TEXT", "ABSTRACT_ONLY"}
    ev_ids = EvidenceStore(workspace.workspace).ids()
    good = f"# Synthesis\n\nBoth studies rely on tree ensembles and report regional limits, which constrains generalisation across crops and climates [{sorted(ev_ids)[0]}; {sid}].\n\nShort note.\n"
    assert pipelines.validate_evidence_links(workspace, good)["ok"]
    bad = "# Synthesis\n\nThis long paragraph makes a claim about accuracy without any linked identifier and should therefore be flagged by the validator as unlinked.\n\nAnother paragraph cites a fake id [ev-0000000000] which does not exist in the store at all, so it fails.\n"
    r = pipelines.validate_evidence_links(workspace, bad)
    assert not r["ok"] and r["unknown_ids"] == ["ev-0000000000"] and len(r["unlinked_paragraphs"]) == 1
    seed = pipelines.collect_gap_seed(workspace)
    assert seed["papers"] == 2 and (workspace.workspace / "analysis" / "gap-seed.json").exists()
    gaps_ok = f"# Gaps\n\n## Gap 1\n\nCandidate gap: multi-region validation of tree ensembles is missing because both studies are single-region [{sid}; {s2.source_id}]. This rests on two papers and is not proven novelty.\n"
    assert pipelines.validate_gap_report(workspace, gaps_ok)["ok"]
    gaps_bad = f"# Gaps\n\nThis is proven novel: nobody has ever studied multi-region validation, as both sources show [{sid}; {s2.source_id}] and we are certain about it.\n"
    r = pipelines.validate_gap_report(workspace, gaps_bad)
    assert not r["ok"] and r["overclaims"]


def test_manuscript_citation_integrity_review_pipeline(workspace, mock_providers):
    reg = SourceRegistry(workspace.workspace)
    good = new_source("Machine learning crop yield study 1", authors=["Author, 1"], year=2022, doi="10.1000/test.1")
    bad_doi = new_source("Paper with fake DOI", authors=["Fake, F"], year=2020, doi="10.1000/does-not-exist")
    mismatch = new_source("Paper whose DOI points elsewhere", authors=["Mis, M"], year=2019, doi="10.1000/mismatch")
    malformed = new_source("Malformed DOI paper", authors=["Mal, M"], year=2018)
    malformed.doi = None
    for s in (good, bad_doi, mismatch, malformed):
        reg.add(s)
    reg.save()
    bib = reg.bib_path.read_text(encoding="utf-8") + "\n@article{broken2001, title={Broken}, doi={not-a-doi}, year={2001}}\n@article{unused2005, title={Unused}, doi={10.1000/test.2}}\n"
    (workspace.workspace / "sources" / "refs.bib").write_text(bib, encoding="utf-8")
    outline = (f"# Yield paper\n\n## Introduction\n\nPrior work [{good.source_id}] and [{bad_doi.source_id}] and [{mismatch.source_id}] "
               f"and \\cite{{broken2001}} and (Mal, 2018) and a ghost [src-000000000000].\n\n## Methods\n\n[MISSING: sampling design]\n\n## Results\n\n[AUTHOR INPUT NEEDED: tables]\n")
    (workspace.workspace / "manuscript" / "manuscript-outline.md").write_text(outline, encoding="utf-8")
    chk = pipelines.check_manuscript_inputs(workspace, outline)
    assert len(chk["placeholders"]) == 2 and chk["unknown_sources"] == ["src-000000000000"]
    pipelines.manuscript_to_docx(workspace, "manuscript/manuscript-outline.md")
    assert (workspace.workspace / "manuscript" / "manuscript-draft.docx").exists()
    (workspace.workspace / "manuscript" / "manuscript-draft.docx").write_bytes(b"user edited bytes")
    with pytest.raises(ApprovalRequired):
        pipelines.manuscript_to_docx(workspace, "manuscript/manuscript-outline.md")
    pipelines.manuscript_to_docx(workspace, "manuscript/manuscript-outline.md", force=True)
    audit = pipelines.audit_citations(workspace, "manuscript/manuscript-outline.md", "sources/refs.bib", providers=mock_providers)
    assert not audit["passed"]
    fails = set(audit["failures"])
    assert bad_doi.source_id in fails and mismatch.source_id in fails and "broken2001" in fails
    assert good.source_id not in fails and "unused2005" in audit["unused"]
    assert "src-000000000000" in audit["missing_in_bibliography"]
    reg2 = SourceRegistry(workspace.workspace)
    assert reg2.get(mismatch.source_id).verification_status == VerificationStatus.MISMATCH
    assert reg2.get(good.source_id).verification_status == VerificationStatus.VERIFIED
    vbib = (workspace.workspace / "reviews" / "verified-references.bib").read_text(encoding="utf-8")
    assert "10.1000/test.1" in vbib and "does-not-exist" not in vbib
    md = (workspace.workspace / "reviews" / "citation-audit.md").read_text(encoding="utf-8")
    assert "does **not** verify that a cited paper supports the claim" in md
    # offline audit: format only
    off = pipelines.audit_citations(workspace, "manuscript/manuscript-outline.md", "sources/refs.bib", providers=None)
    assert "broken2001" in off["failures"] and bad_doi.source_id not in off["failures"]
    integ = pipelines.integrity_audit(workspace, ai_use={"tools": ["Claude Code"], "stages": ["search"], "human_review": "all"},
                                      manuscript_path="manuscript/manuscript-outline.md")
    assert integ["unknown_sources"] == ["src-000000000000"]
    text = (workspace.workspace / "reviews" / "integrity-audit.md").read_text(encoding="utf-8")
    assert "does not certify the manuscript as plagiarism-free" in text
    with pytest.raises(pipelines.StepBlocked):
        pipelines.build_review_outputs(workspace, [])
    with pytest.raises(pipelines.StepBlocked):
        pipelines.build_review_outputs(workspace, [{"section": "Methods", "severity": "huge", "comment": "x"}])
    rev = pipelines.build_review_outputs(workspace, [
        {"section": "Methods", "severity": "major", "comment": "Sampling not described", "suggested_action": "Add design"},
        {"section": "Results", "severity": "minor", "comment": "Units missing", "suggested_action": "Add t/ha"},
    ])
    assert rev["major"] == 1 and rev["minor"] == 1
    rows = read_xlsx(workspace.workspace / "reviews" / "revision-plan.xlsx")
    assert [r["id"] for r in rows] == ["R1", "R2"] and rows[0]["status"] == "open"
    report = (workspace.workspace / "reviews" / "peer-review-report.md").read_text(encoding="utf-8")
    assert "not a journal decision" in report
    assert len(json.loads((workspace.workspace / "progress" / "artifacts.json").read_text(encoding="utf-8"))["artifacts"]) >= 10
