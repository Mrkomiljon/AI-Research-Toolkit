import pytest

from research_toolkit import SKILL_NAMES
from research_toolkit.cli import main as rtk
from research_toolkit.exporters import read_docx_text, read_xlsx
from research_toolkit.journal import GUIDELINES, analyse_structure, build_checklist, cover_letter
from research_toolkit.orchestrator import build_plan, detect_intent
from research_toolkit.writing import check_writing, compare_facts, measure

DRAFT = """# Learned localisation for thyroid nodules

## Abstract

We studied nodules. Results were obtained by the model. It may possibly be the case that the approach could work.

## Introduction

Thyroid nodules are common [src-db6b39b9a028]. Deep learning (DL) classifiers reach 93.3% sensitivity [src-db6b39b9a028]. The AUROC was 0.84 in a two-view pipeline [src-73632c789961], which is a very long sentence that keeps going and going with many subordinate clauses that make it hard for the reader to follow what the subject of the sentence actually is and what is being claimed about it in the end.

## Methods

[MISSING: data description] The model was trained by us using CNN features; ROI selection was performed.

## Results

[AUTHOR INPUT NEEDED: tables]

## Discussion

Ethics approval was obtained from the institutional review board. Data are available on request. The authors declare no conflicts of interest.
"""


def test_measure_flags_expected_patterns():
    m = measure(DRAFT)
    types = {f["type"] for f in m["flagged"]}
    assert "long_sentence" in types and "stacked_hedges" in types and "acronym_undefined" in types  # ROI undefined, DL defined
    assert not any(f["text"].startswith("DL ") for f in m["flagged"] if f["type"] == "acronym_undefined")
    assert m["placeholders"] == 2 and m["citations"] >= 3 and m["passive_sentences"] >= 2
    assert "Methods" in m["sections"]


def test_compare_facts_detects_changed_numbers_and_ids():
    edited = DRAFT.replace("93.3%", "95%").replace("[src-73632c789961]", "")
    cmp = compare_facts(DRAFT, edited)
    assert "93.3%" in cmp["numbers_removed"] and "95%" in cmp["numbers_added"] and cmp["ids_removed"] == ["src-73632c789961"]
    assert compare_facts(DRAFT, DRAFT) == {k: [] for k in compare_facts(DRAFT, DRAFT)}


def test_check_writing_writes_report_and_checklist(workspace):
    md = workspace.workspace / "manuscript" / "draft.md"
    md.write_text(DRAFT, encoding="utf-8")
    edited = workspace.workspace / "manuscript" / "edited-draft.md"
    edited.write_text(DRAFT.replace("93.3%", "95%"), encoding="utf-8")
    res = check_writing(workspace, "manuscript/edited-draft.md", compare_with="manuscript/draft.md")
    assert res["fact_comparison"]["numbers_removed"] == ["93.3%"]
    report = (workspace.workspace / "manuscript" / "writing-report.md").read_text(encoding="utf-8")
    assert "numbers_removed: 93.3%" in report and "Flagged passages" in report
    assert (workspace.workspace / "manuscript" / "style-checklist.md").exists()
    assert any(a.skill == "academic-writing" and a.author_review_status.value == "pending" for a in workspace.artifacts())
    with pytest.raises(ValueError):
        (workspace.workspace / "manuscript" / "empty.md").write_text("", encoding="utf-8")
        check_writing(workspace, "manuscript/empty.md")


def test_analyse_structure_and_declarations():
    st = analyse_structure(DRAFT, word_limit=50, abstract_limit=10)
    assert st["sections"]["Methods"] == "Methods" and "Conclusion" in st["missing_sections"] and "References" in st["missing_sections"]
    assert st["over_word_limit"] and st["over_abstract_limit"]
    assert st["declarations"]["ethics approval"] and st["declarations"]["data availability"] and st["declarations"]["conflicts of interest"]
    assert "funding" in st["missing_declarations"] and st["placeholders"] == 2


def test_build_checklist_and_cover_letter(workspace):
    md = workspace.workspace / "manuscript" / "draft.md"
    md.write_text(DRAFT, encoding="utf-8")
    (workspace.workspace / "reviews").mkdir(exist_ok=True)
    (workspace.workspace / "reviews" / "journal-guidelines.txt").write_text("Abstract max 250 words. Main text 3500 words.", encoding="utf-8")
    res = build_checklist(workspace, "manuscript/draft.md", "tripod", guidelines_file="reviews/journal-guidelines.txt", word_limit=3500)
    assert res["guideline"].startswith("TRIPOD") and res["items"] == len(GUIDELINES["TRIPOD"]["items"])
    rows = read_xlsx(workspace.workspace / "reviews" / "reporting-checklist.xlsx", "checklist")
    assert rows[0]["status"] in (None, "") and any("Methods" in str(r["location"]) for r in rows if r["section"] == "Methods")
    md_text = (workspace.workspace / "reviews" / "journal-compliance.md").read_text(encoding="utf-8")
    assert "Abstract max 250 words" in md_text and "not a guarantee of acceptance" in md_text and "[ ] funding" in md_text
    with pytest.raises(ValueError):
        build_checklist(workspace, "manuscript/draft.md", "NOPE")
    cl = cover_letter(workspace, "manuscript/draft.md", "Medical Image Analysis")
    text = read_docx_text(workspace.workspace / "reviews" / "cover-letter-draft.docx")
    assert "Medical Image Analysis" in text and "Learned localisation for thyroid nodules" in text and "AUTHOR INPUT NEEDED" in text
    assert cl["title"].startswith("Learned localisation")


def test_routing_and_plan_include_new_skills(workspace):
    assert detect_intent("Please polish the English of my discussion section")[0] == "writing"
    assert detect_intent("Ilmiy uslubda tahrirla")[0] == "writing"
    assert detect_intent("Does my paper meet STARD reporting guidelines for the journal?")[0] == "journal"
    assert detect_intent("Maqolani xalqaro nashr standartlariga moslashtir")[0] == "journal"
    plan = build_plan(workspace, "Prepare my article for Radiology")
    assert [s.skill for s in plan.steps] == ["manuscript-builder", "academic-writing", "citation-verifier", "claim-verifier", "academic-integrity", "journal-standards", "peer-reviewer"]
    assert len(SKILL_NAMES) == 15


def test_cli_writing_and_journal(workspace, capsys):
    import json

    (workspace.workspace / "manuscript" / "draft.md").write_text(DRAFT, encoding="utf-8")
    ws = str(workspace.workspace)
    rtk(["writing", "check", "-p", ws, "--file", "manuscript/draft.md"])
    out = json.loads(capsys.readouterr().out)
    assert out["metrics"]["placeholders"] == 2
    rtk(["journal", "checklist", "-p", ws, "--manuscript", "manuscript/draft.md", "--guideline", "STARD", "--abstract-limit", "250"])
    out = json.loads(capsys.readouterr().out)
    assert out["items"] == len(GUIDELINES["STARD"]["items"]) and out["structure"]["over_abstract_limit"] is False
    rtk(["journal", "guidelines", "-p", ws])
    assert "PRISMA" in json.loads(capsys.readouterr().out)
