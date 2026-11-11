"""1.4.0: OCR for scanned PDFs, claim-verifier, gap-validator, research-concept-builder (all offline)."""
import json

import pytest

from research_toolkit import SKILL_NAMES, concept, ocr, pipelines, verification
from research_toolkit.cli import main as rtk
from research_toolkit.documents import extract_pdf_text
from research_toolkit.evidence_store import EvidenceStore
from research_toolkit.exporters import read_json, read_xlsx, write_json
from research_toolkit.orchestrator import build_plan, detect_intent
from research_toolkit.progress import compute_status
from research_toolkit.project_manager import ApprovalRequired
from research_toolkit.schemas import AccessLevel, VerificationStatus
from research_toolkit.source_registry import SourceRegistry, bib_key, new_source
from tests.conftest import FULL_TEXT_PAGES, make_pdf
from tests.integration.test_pipelines import _analysis


def make_scanned_pdf(path, pages):
    """A PDF whose pages are bitmaps only (no text layer), like a scanner produces."""
    import pymupdf

    src_path = make_pdf(path.with_name(path.stem + "-text.pdf"), pages)
    out = pymupdf.open()
    with pymupdf.open(src_path) as src:
        for page in src:
            pix = page.get_pixmap(dpi=50)
            new = out.new_page(width=page.rect.width, height=page.rect.height)
            new.insert_image(new.rect, pixmap=pix)
    out.save(path)
    out.close()
    src_path.unlink()
    return path


@pytest.fixture
def fake_ocr(monkeypatch):
    """Offline OCR backend that 'reads' the known page texts."""
    calls = []

    def backend(path, pages):
        calls.append(list(pages))
        return {n: FULL_TEXT_PAGES[n - 1] for n in pages}

    monkeypatch.setattr(ocr, "BACKENDS", {"fake": (lambda: True, backend)})
    monkeypatch.delenv("RTK_OCR_BACKEND", raising=False)
    return calls


@pytest.fixture
def no_ocr(monkeypatch):
    monkeypatch.setattr(ocr, "BACKENDS", {"docling": (lambda: False, None), "tesseract": (lambda: False, None)})
    monkeypatch.delenv("RTK_OCR_BACKEND", raising=False)


def _register(workspace, title, doi, pdf=None, abstract=None, authors=("Doe, J",), year=2021):
    reg = SourceRegistry(workspace.workspace)
    src = new_source(title, authors=list(authors), year=year, doi=doi, pdf_path=pdf, abstract=abstract)
    reg.add(src)
    reg.save()
    return src.source_id


# ---------------------------------------------------------------------------------------------------- OCR
def test_scanned_pdf_without_backend_is_reported_not_guessed(workspace, no_ocr):
    make_scanned_pdf(workspace.workspace / "papers" / "PDFs" / "scan.pdf", FULL_TEXT_PAGES)
    sid = _register(workspace, "Scanned maize paper", "10.1000/scan.1", pdf="papers/PDFs/scan.pdf", abstract="Yield prediction with ML.")
    parsed = extract_pdf_text(workspace.workspace / "papers" / "PDFs" / "scan.pdf")
    assert parsed.scanned_pages == [1, 2, 3] and parsed.ocr_status == "skipped" and parsed.char_count < 50
    prep = pipelines.prepare_paper_analysis(workspace, sid)
    assert prep["ocr"]["status"] == "unavailable" and "ai-research-toolkit[ocr]" in prep["ocr"]["message"]
    assert prep["access_level"] == "ABSTRACT_ONLY"  # an unread scan is never labelled full text
    assert any("NOT read" in w for w in prep["warnings"])
    assert ocr.status()["selected"] is None and ocr.status()["hint"]
    bare = _register(workspace, "Scan without abstract", "10.1000/scan.2", pdf="papers/PDFs/scan.pdf")
    assert pipelines.prepare_paper_analysis(workspace, bare)["access_level"] == "METADATA_ONLY"


def test_scanned_pdf_is_ocred_labelled_and_quotable(workspace, fake_ocr):
    make_scanned_pdf(workspace.workspace / "papers" / "PDFs" / "scan.pdf", FULL_TEXT_PAGES)
    sid = _register(workspace, "Scanned maize paper", "10.1000/scan.1", pdf="papers/PDFs/scan.pdf")
    prep = pipelines.prepare_paper_analysis(workspace, sid)
    assert fake_ocr == [[1, 2, 3]]
    assert prep["ocr"] == {"status": "applied", "backend": "fake", "scanned_pages": [1, 2, 3], "ocr_pages": [1, 2, 3], "message": None}
    assert prep["access_level"] == "FULL_TEXT" and "methods" in prep["sections_detected"]
    assert any("machine-read" in w for w in prep["warnings"])
    extracted = read_json(workspace.workspace / "analysis" / sid / "extracted-text.json")
    assert all(p["ocr"] for p in extracted["pages"]) and extracted["ocr"]["backend"] == "fake"
    res = pipelines.finalize_paper_analysis(workspace, sid, _analysis(sid))
    assert res["problems"] == [] and len(res["evidence_ids"]) == 5


def test_text_pdf_needs_no_ocr_and_force_and_failure_modes(workspace, full_text_pdf, fake_ocr, monkeypatch):
    parsed = extract_pdf_text(full_text_pdf, ocr="auto")
    assert parsed.scanned_pages == [] and parsed.ocr_status == "not_needed" and fake_ocr == []
    forced = extract_pdf_text(full_text_pdf, ocr="force")
    assert forced.ocr_pages == [1, 2, 3] and forced.ocr_status == "applied"
    monkeypatch.setattr(ocr, "BACKENDS", {"fake": (lambda: True, lambda path, pages: {pages[0]: "only the first page was readable " * 3})})
    partial = extract_pdf_text(full_text_pdf, ocr="force")
    assert partial.ocr_status == "partial" and partial.ocr_pages == [1] and "[2, 3]" in partial.ocr_message
    assert "random forest" in partial.pages[1].text  # the original text layer is kept where OCR returned nothing

    def boom(path, pages):
        raise RuntimeError("model download failed")

    monkeypatch.setattr(ocr, "BACKENDS", {"fake": (lambda: True, boom)})
    failed = extract_pdf_text(full_text_pdf, ocr="force")
    assert failed.ocr_status == "failed" and "model download failed" in failed.ocr_message and failed.char_count > 2500
    with pytest.raises(ocr.OcrUnavailable):
        ocr.pick_backend("nope")
    with pytest.raises(ValueError):
        extract_pdf_text(full_text_pdf, ocr="maybe")


# ----------------------------------------------------------------------------------------- claim-verifier
@pytest.fixture
def claims_ws(workspace, full_text_pdf):
    full = _register(workspace, "Maize yield prediction with random forests", "10.1000/test.0", pdf="papers/PDFs/paper-full.pdf")
    pipelines.prepare_paper_analysis(workspace, full)
    abs_only = _register(workspace, "Wheat yield under drought", "10.1000/test.9", authors=("Roe, A",), year=2022,
                         abstract="Drought reduced wheat yield by 30 percent across the 40 surveyed fields in 2020.")
    other = _register(workspace, "Unrelated soil paper", "10.1000/test.8", authors=("Poe, B",), year=2020,
                      abstract="Soil organic carbon was measured at three depths in every plot.")
    key = bib_key(SourceRegistry(workspace.workspace).get(abs_only))
    draft = (
        "# Draft\n\n## Introduction\n\n"
        f"Random forests reached an RMSE of 0.41 t/ha on held-out fields [{full}]. "
        f"Deep learning always beats random forests for yield prediction [{full}]. "
        f"The data came from 500 farms across Europe [{full}]. "
        f"Drought cut wheat yield by about a third [@{key}]. "
        f"Soil carbon drives yield in every region [{full}].\n\n"
        "An uncited sentence makes a claim that nobody checks here.\n\n"
        "## Discussion\n\nSatellite data improve prediction \\cite{ghost2020}. See also the abstract-level evidence. [src-000000000000]\n"
    )
    (workspace.workspace / "manuscript" / "draft.md").write_text(draft, encoding="utf-8")
    return workspace, full, abs_only, other


def test_claims_extract_resolves_citations(claims_ws):
    ws, full, abs_only, _ = claims_ws
    res = verification.extract_claims(ws, "manuscript/draft.md")
    assert res["claims"] == 7 and res["with_unresolved_keys"] == 2 and res["sources_without_extracted_text"] == [abs_only]
    data = read_json(ws.workspace / "reviews" / "claims.json")
    by_text = {c["text"][:20]: c for c in data["claims"]}
    assert by_text["Random forests reach"]["cited_source_ids"] == [full] and by_text["Random forests reach"]["section"] == "Introduction"
    assert by_text["Random forests reach"]["candidates"][0]["extracted_text"] == f"analysis/{full}/extracted-text.json"
    assert by_text["Drought cut wheat yi"]["cited_source_ids"] == [abs_only]  # [@bibkey] resolved through the registry
    assert by_text["Satellite data impro"]["unresolved_keys"] == ["ghost2020"] and by_text["Satellite data impro"]["section"] == "Discussion"
    assert by_text["See also the abstrac"]["unresolved_keys"] == ["src-000000000000"]  # trailing citation attaches to its sentence
    assert all(c["verdict"] is None for c in data["claims"])
    (ws.workspace / "manuscript" / "plain.md").write_text("No citations at all in this text.\n", encoding="utf-8")
    with pytest.raises(pipelines.StepBlocked):
        verification.extract_claims(ws, "manuscript/plain.md")


def test_claims_finalize_only_downgrades_and_records_evidence(claims_ws):
    ws, full, abs_only, other = claims_ws
    verification.extract_claims(ws, "manuscript/draft.md")
    path = ws.workspace / "reviews" / "claims.json"
    data = read_json(path)
    c = {x["text"][:20]: x for x in data["claims"]}
    c["Random forests reach"].update(verdict="supported", rationale="The reported RMSE matches.",
                                     evidence=[{"source_id": full, "excerpt": "The model reached an RMSE of 0.41 t/ha on held-out fields."}])
    c["Deep learning always"].update(verdict="supported", rationale="The paper says so.",
                                     evidence=[{"source_id": full, "excerpt": "Deep learning always outperforms random forests in every setting."}])
    c["The data came from 5"].update(verdict="contradicted", rationale="The paper reports 120 farms in Iowa, not 500 in Europe.",
                                     evidence=[{"source_id": full, "excerpt": "Data came from\n120 farms in Iowa."}])
    c["Drought cut wheat yi"].update(verdict="supported", rationale="30 percent is about a third.",
                                     evidence=[{"source_id": abs_only, "excerpt": "Drought reduced wheat yield by 30 percent"}])
    c["Soil carbon drives y"].update(verdict="supported", rationale="Measured carbon.",
                                     evidence=[{"source_id": other, "excerpt": "Soil organic carbon was measured at three depths in every plot."}])
    c["Satellite data impro"].update(verdict="insufficient", rationale="The cited key is not in the registry.")
    write_json(path, data)
    before = len(EvidenceStore(ws.workspace).all())
    res = verification.finalize_claims(ws, read_json(path))
    assert res["counts"] == {"supported": 2, "contradicted": 1, "insufficient": 3, "not_assessed": 1, "downgraded": 2}
    assert not res["passed"]
    out = {r["claim"][:20]: r for r in read_json(ws.workspace / "reviews" / "claim-verification.json")["claims"]}
    ok = out["Random forests reach"]
    assert ok["verdict"] == "supported" and ok["quotes"][0]["locator"] == "p.3" and ok["quotes"][0]["basis"] == "full_text" and not ok["problems"]
    fake = out["Deep learning always"]  # invented quote: never accepted
    assert fake["verdict"] == "insufficient" and fake["downgraded"] and any("not found verbatim" in p for p in fake["problems"]) and fake["quotes"] == []
    assert out["The data came from 5"]["verdict"] == "contradicted" and out["The data came from 5"]["quotes"][0]["locator"] == "p.2"
    absr = out["Drought cut wheat yi"]
    assert absr["verdict"] == "supported" and absr["quotes"][0]["locator"] == "abstract" and any("abstract only" in n for n in absr["notes"])
    wrong = out["Soil carbon drives y"]  # real quote, but from a paper the sentence does not cite
    assert wrong["verdict"] == "insufficient" and any("does not cite" in p for p in wrong["problems"])
    assert out["See also the abstrac"]["verdict"] == "not_assessed"
    assert all(r["human_review"] == "pending" for r in out.values())
    new_ev = EvidenceStore(ws.workspace).all()[before:]
    assert len(new_ev) == 3 and all(e.verified_by.value == "tool" and e.verification_status == VerificationStatus.VERIFIED and e.skill == "claim-verifier" for e in new_ev)
    md = (ws.workspace / "reviews" / "claim-verification.md").read_text(encoding="utf-8")
    assert "It does not judge meaning" in md and md.index("## Contradicted") < md.index("## Supported")
    rows = read_xlsx(ws.workspace / "reviews" / "claim-verification.xlsx")
    assert len(rows) == 7 and {r["human_review"] for r in rows} == {"pending"}
    stage = compute_status(ws).stages["claim-verifier"]
    assert stage.status == "in_progress" and stage.blockers  # problems keep the stage from counting as done
    # too-short quotes and unknown sources are rejected; an all-clean file passes
    clean = {"manuscript": "m", "claims": [{"claim_id": "clm-1", "text": "RMSE was 0.41.", "cited_source_ids": [full], "verdict": "supported", "rationale": "match",
                                           "evidence": [{"source_id": full, "excerpt": "RMSE of 0.41"}]}]}
    assert verification.finalize_claims(ws, clean)["counts"]["insufficient"] == 1
    clean["claims"][0]["evidence"] = [{"source_id": "src-ffffffffffff", "excerpt": "The model reached an RMSE of 0.41 t/ha"}]
    assert verification.finalize_claims(ws, clean)["counts"]["insufficient"] == 1
    clean["claims"][0]["evidence"] = [{"source_id": full, "excerpt": "The model reached an RMSE of 0.41 t/ha"}]
    good = verification.finalize_claims(ws, clean)
    assert good["passed"] and good["counts"]["supported"] == 1
    assert compute_status(ws).stages["claim-verifier"].status == "awaiting_user_review"


def test_claims_quote_from_ocr_page_is_flagged(workspace, fake_ocr):
    make_scanned_pdf(workspace.workspace / "papers" / "PDFs" / "scan.pdf", FULL_TEXT_PAGES)
    sid = _register(workspace, "Scanned maize paper", "10.1000/scan.1", pdf="papers/PDFs/scan.pdf")
    pipelines.prepare_paper_analysis(workspace, sid)
    data = {"manuscript": "m", "claims": [{"claim_id": "clm-1", "text": "x", "cited_source_ids": [sid], "verdict": "supported", "rationale": "r",
                                           "evidence": [{"source_id": sid, "excerpt": "Data came from 120 farms in Iowa."}]}]}
    verification.finalize_claims(workspace, data)
    row = read_json(workspace.workspace / "reviews" / "claim-verification.json")["claims"][0]
    assert row["quotes"][0]["ocr"] is True and any("OCR text" in n for n in row["notes"])


# ------------------------------------------------------------------------------------------ gap-validator
GAPS_MD = """# Candidate research gaps

## Scope

Maize, tree ensembles.

## Gap 1: Multi-region validation

Tree-ensemble yield models have only been validated in single regions, so machine learning crop yield transfer is untested [{a}; {b}].

Risks: data access.

## Gap 2: Smallholder farms

No study covers smallholder plots under two hectares [{a}].
"""


@pytest.fixture
def gaps_ws(workspace):
    a = _register(workspace, "Maize yield prediction with random forests", "10.1000/gap.a")
    b = _register(workspace, "Second regional paper", "10.1000/gap.b", year=2022)
    (workspace.workspace / "analysis" / "research-gaps.md").write_text(GAPS_MD.format(a=a, b=b), encoding="utf-8")
    return workspace, a, b


def _fill(ws, **by_gap):
    path = ws.workspace / "analysis" / "gap-validation.input.json"
    data = read_json(path)
    for g in data["gaps"]:
        g.update(by_gap.get(g["gap_id"].replace("-", "_"), {}))
    write_json(path, data)


def test_gap_validation_end_to_end(gaps_ws, mock_providers):
    ws, a, b = gaps_ws
    res = verification.init_gap_validation(ws)
    assert res["gaps"] == 2
    data = read_json(ws.workspace / "analysis" / "gap-validation.input.json")
    assert [g["title"] for g in data["gaps"]] == ["Gap 1: Multi-region validation", "Gap 2: Smallholder farms"]
    assert data["gaps"][0]["motivating_source_ids"] == sorted([a, b]) and data["gaps"][0]["statement"].startswith("Tree-ensemble")
    with pytest.raises(ApprovalRequired):
        verification.init_gap_validation(ws)
    with pytest.raises(pipelines.StepBlocked, match="no queries"):
        verification.search_gap_counterevidence(ws, mock_providers)
    with pytest.raises(pipelines.StepBlocked, match="gap-counterevidence"):
        verification.finalize_gap_validation(ws)
    _fill(ws, gap_1={"queries": ["multi-region machine learning crop yield validation", "cross-region transfer yield model"] + ["q"] * 5},
          gap_2={"queries": []})
    with pytest.raises(pipelines.StepBlocked, match="budget"):
        verification.search_gap_counterevidence(ws, mock_providers, per_query=999)
    before = len(SourceRegistry(ws.workspace))
    res = verification.search_gap_counterevidence(ws, mock_providers, per_query=5)
    assert res["queries_ok"] == 10 and res["hits_per_gap"] == {"gap-1": 7, "gap-2": 0} and res["new_sources"] == 7
    assert len(SourceRegistry(ws.workspace)) == before + 7
    ce = read_json(ws.workspace / "analysis" / "gap-counterevidence.json")
    g1 = ce["gaps"][0]
    assert g1["queries_ok"] == 10 and len(g1["queries_dropped_over_limit"]) == 2  # at most 5 queries per gap are run
    assert g1["hits"][0]["keyword_overlap"] >= g1["hits"][-1]["keyword_overlap"] and "yield" in g1["hits"][0]["matched_terms"]
    assert ce["gaps"][1]["queries_ok"] == 0
    counter = g1["hits"][0]["source_id"]
    _fill(ws, gap_1={"verdict": "partially_addressed", "counter_source_ids": [counter], "rationale": "One study validates across two regions; transfer to other crops remains."},
          gap_2={"verdict": "open", "rationale": "Nothing found."})
    res = verification.finalize_gap_validation(ws)
    assert res["counts"] == {"open": 0, "partially_addressed": 1, "already_addressed": 0, "inconclusive": 1} and not res["passed"]
    out = {g["gap_id"]: g for g in read_json(ws.workspace / "analysis" / "gap-validation.json")["gaps"]}
    assert out["gap-1"]["verdict"] == "partially_addressed" and out["gap-1"]["hits_screened"] == 7 and not out["gap-1"]["problems"]
    assert any("abstract/metadata only" in n for n in out["gap-1"]["notes"])
    assert out["gap-2"]["verdict"] == "inconclusive" and out["gap-2"]["downgraded"]  # 'open' without any search is not accepted
    md = (ws.workspace / "analysis" / "gap-validation.md").read_text(encoding="utf-8")
    assert "not a proof of novelty" in md and "Scopus" in md
    # verdict rules
    _fill(ws, gap_1={"verdict": "already_addressed", "counter_source_ids": [], "rationale": "x"}, gap_2={"verdict": "maybe", "rationale": ""})
    res = verification.finalize_gap_validation(ws)
    assert "needs at least one registered counter source" in " ".join(res["problems"]["gap-1"]) and "invalid verdict" in " ".join(res["problems"]["gap-2"])
    _fill(ws, gap_1={"verdict": "open", "counter_source_ids": ["src-ffffffffffff"], "rationale": "This is proven novel and nobody has studied it."})
    res = verification.finalize_gap_validation(ws)
    joined = " ".join(res["problems"]["gap-1"])
    assert "not in the registry" in joined and "novelty over-claim" in joined
    _fill(ws, gap_1={"verdict": "open", "counter_source_ids": [], "rationale": "Ten query runs returned nothing that validates across regions."})
    res = verification.finalize_gap_validation(ws)
    assert "gap-1" not in res["problems"]
    assert "open — no counterevidence found by this search (candidate, not proven novelty)" in (ws.workspace / "analysis" / "gap-validation.md").read_text(encoding="utf-8")


def test_gap_search_all_providers_down_is_blocked(gaps_ws, failing_providers):
    ws, *_ = gaps_ws
    verification.init_gap_validation(ws)
    _fill(ws, gap_1={"queries": ["multi-region yield validation"]})
    with pytest.raises(pipelines.StepBlocked) as exc:
        verification.search_gap_counterevidence(ws, failing_providers)
    assert any("gap-counterevidence.json" in p for p in exc.value.partial_artifacts)
    _fill(ws, gap_1={"verdict": "open", "rationale": "nothing found"}, gap_2={"verdict": "inconclusive", "rationale": "not searched"})
    res = verification.finalize_gap_validation(ws)
    assert res["counts"]["open"] == 0 and res["counts"]["inconclusive"] == 2


def test_gap_init_needs_gap_report(workspace):
    with pytest.raises(pipelines.StepBlocked):
        verification.init_gap_validation(workspace)
    (workspace.workspace / "analysis" / "research-gaps.md").write_text("# Gaps\n\nNo headings below the title.\n", encoding="utf-8")
    with pytest.raises(pipelines.StepBlocked, match="no gap sections"):
        verification.init_gap_validation(workspace)


# ------------------------------------------------------------------------------- research-concept-builder
def test_concept_builder_marks_missing_unconfirmed_and_unvalidated(gaps_ws, mock_providers):
    ws, a, b = gaps_ws
    res = concept.init_canvas(ws)
    assert res["validated_gaps"] == 0 and "gap-validator" in res["warning"]
    with pytest.raises(ApprovalRequired):
        concept.init_canvas(ws)
    path = ws.workspace / "manuscript" / "gap-canvas.json"
    canvas = read_json(path)
    f = canvas["fields"]
    f["problem"].update(text="Yield models are trained and tested in one region.", source="author")
    f["known"].update(text=f"Random forests predict maize yield well within one region [{a}; {b}].", source="literature")
    f["gap"].update(text="Cross-region validation is missing.", source="literature")  # no ids -> problem
    f["research_question"].update(text="Does a model trained in one region hold in another?", source="author")
    f["methods"].update(text="Leave-one-region-out validation.", source="agent_draft")
    f["expected_contribution"].update(text="This would be the first and proven novel cross-region test [src-000000000000].", source="agent_draft")
    write_json(path, canvas)
    res = concept.build_concept(ws)
    assert not res["ok"]
    joined = " ".join(res["problems"])
    assert "gap: must cite" in joined and "unknown ids src-000000000000" in joined and "novelty over-claim" in joined
    assert res["missing"] == ["Hypothesis", "Data, sample and resources", "Risks, limitations and ethics"]
    assert res["unconfirmed"] == ["Proposed design and methods"] and any("no gap_id" in w for w in res["warnings"])
    md = (ws.workspace / "manuscript" / "concept-paper.md").read_text(encoding="utf-8")
    assert "[AUTHOR INPUT NEEDED: Hypothesis]" in md and "[UNCONFIRMED — drafted by the AI agent" in md and "## Timeline" not in md
    assert compute_status(ws).stages["research-concept-builder"].status == "in_progress"
    # validate the gap, then fix the canvas
    verification.init_gap_validation(ws)
    _fill(ws, gap_1={"queries": ["cross-region yield model validation"]})
    verification.search_gap_counterevidence(ws, mock_providers, per_query=5)
    _fill(ws, gap_1={"verdict": "open", "rationale": "No cross-region validation among the screened records."},
          gap_2={"verdict": "already_addressed", "counter_source_ids": [b], "rationale": "Covered by the second paper."})
    verification.finalize_gap_validation(ws)
    canvas = read_json(path)
    canvas.update(title="Cross-region validation of maize yield models", gap_id="gap-2")
    f = canvas["fields"]
    f["gap"].update(text=f"Cross-region validation is missing [{a}; {b}].")
    f["hypothesis"].update(text="Accuracy drops outside the training region.", source="author")
    f["methods"].update(source="author")
    f["data_resources"].update(text="Public yield statistics for two regions, 2015-2020.", source="author")
    f["risks_ethics"].update(text="No personal data; risk of unequal data quality.", source="author")
    f["expected_contribution"].update(text="A cross-region accuracy estimate for tree ensembles.", source="author")
    write_json(path, canvas)
    res = concept.build_concept(ws)
    assert not res["ok"] and "already_addressed" in " ".join(res["problems"])  # a closed gap cannot carry a concept
    canvas["gap_id"] = "gap-1"
    write_json(path, canvas)
    res = concept.build_concept(ws)
    assert res["ok"] and res["missing"] == [] and res["unconfirmed"] == [] and res["cited_sources"] == [a, b]
    assert any("awaits author review" in w for w in res["warnings"])
    md = (ws.workspace / "manuscript" / "concept-paper.md").read_text(encoding="utf-8")
    assert "`gap-1` — open after 2 successful targeted query run(s)" in md and "candidate gap, not proven novelty" in md
    assert "10.1000/gap.a" in md and "UNCONFIRMED" not in md
    canvas_md = (ws.workspace / "manuscript" / "gap-canvas.md").read_text(encoding="utf-8")
    assert "| Research question | author |" in canvas_md
    from research_toolkit.exporters import read_docx_text

    assert "Cross-region validation of maize yield models" in read_docx_text(ws.workspace / "manuscript" / "concept-paper.docx")
    assert compute_status(ws).stages["research-concept-builder"].status == "awaiting_user_review"
    # an author-edited concept paper is never overwritten silently
    (ws.workspace / "manuscript" / "concept-paper.md").write_text(md + "\nAuthor's own paragraph.\n", encoding="utf-8")
    with pytest.raises(ApprovalRequired):
        concept.build_concept(ws)
    assert concept.build_concept(ws, force=True)["ok"]


# ------------------------------------------------------------------------------------- routing, plan, CLI
@pytest.mark.parametrize("text,expected", [
    ("Do my sources support the claims in this draft?", "claims"),
    ("Qo'lyozmadagi da'volarni tekshir", "claims"),
    ("Проверь утверждения в рукописи", "claims"),
    ("Validate these research gaps against new literature", "gap-validation"),
    ("Is this gap already studied? Look for counterevidence", "gap-validation"),
    ("Bo'shliqlarni tekshir", "gap-validation"),
    ("Build a concept paper from the gap", "concept"),
    ("Tadqiqot konsepsiyasini tuzib ber", "concept"),
    ("Find research gaps in soil moisture sensing", "gaps"),
    ("Audit this manuscript", "audit"),
])
def test_routing_new_intents(text, expected):
    assert detect_intent(text)[0] == expected


def test_plans_and_contracts_for_new_skills(workspace):
    assert len(SKILL_NAMES) == 15
    plan = build_plan(workspace, "Audit this manuscript", overrides={"manuscript_path": "manuscript/draft.md"})
    assert [s.skill for s in plan.steps] == ["citation-verifier", "claim-verifier", "academic-integrity", "journal-standards", "peer-reviewer"]
    step = plan.steps[1]
    assert step.executor == "host-skill" and step.inputs["manuscript_path"] == "manuscript/draft.md" and "claim-verification.md" in step.produces
    plan = build_plan(workspace, "Validate these research gaps")
    assert [s.skill for s in plan.steps] == ["gap-validator"] and not plan.steps[0].approval_required and "research-gaps.md not found" in plan.steps[0].notes
    cfg = workspace.load_config()
    cfg.privacy.allow_external_apis = False
    workspace.save_config(cfg)
    assert build_plan(workspace, "Validate these research gaps").steps[0].approval_required  # new searches need consent
    plan = build_plan(workspace, "Build a research concept paper")
    assert [s.skill for s in plan.steps] == ["research-concept-builder"] and "unvalidated gap" in plan.steps[0].notes
    stages = compute_status(workspace).stages
    assert {"claim-verifier", "gap-validator", "research-concept-builder"} <= set(stages) and len(stages) == 13


def test_cli_claims_gaps_concept_ocr(claims_ws, capsys, monkeypatch):
    ws, full, abs_only, _ = claims_ws
    root = str(ws.workspace)

    def run(argv, code=0):
        if code:
            with pytest.raises(SystemExit) as exc:
                rtk(argv)
            assert exc.value.code == code
        else:
            try:
                rtk(argv)
            except SystemExit as exc:
                assert exc.code == 0
        return json.loads(capsys.readouterr().out)

    assert set(run(["ocr", "status"])["backends"]) >= {"docling", "tesseract"}
    assert run(["claims", "extract", "-p", root, "--manuscript", "manuscript/draft.md"])["claims"] == 7
    assert run(["claims", "extract", "-p", root], code=2)["error"]
    out = run(["claims", "finalize", "-p", root], code=5)  # nothing assessed yet
    assert out["counts"]["not_assessed"] == 7
    assert "error" in run(["claims", "finalize", "-p", root, "--claims-json", "reviews/missing.json"], code=2)
    assert "error" in run(["gaps", "init", "-p", root], code=4)
    (ws.workspace / "analysis" / "research-gaps.md").write_text(GAPS_MD.format(a=full, b=abs_only), encoding="utf-8")
    assert run(["gaps", "init", "-p", root])["gaps"] == 2
    assert "error" in run(["gaps", "init", "-p", root], code=3)
    assert run(["gaps", "search", "-p", root], code=4)["status"] == "blocked"
    cfg = ws.load_config()
    cfg.privacy.allow_external_apis = False
    ws.save_config(cfg)
    assert "allow_external_apis" in run(["gaps", "search", "-p", root], code=3)["error"]
    assert "error" in run(["gaps", "finalize", "-p", root], code=4)
    assert run(["concept", "init", "-p", root])["validated_gaps"] == 0
    out = run(["concept", "build", "-p", root])
    assert out["ok"] and len(out["missing"]) == 9  # an empty canvas is all placeholders, not invented text
    prep = run(["analyze", "prepare", "-p", root, full, "--ocr", "off"])
    assert prep["ocr"]["status"] == "not_needed" and prep["access_level"] == AccessLevel.FULL_TEXT.value
