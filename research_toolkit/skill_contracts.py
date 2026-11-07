"""Per-skill contract shared by orchestrator, progress and validators (TZ section 6 table)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .schemas import ApiCostCategory


@dataclass(frozen=True)
class SkillContract:
    name: str
    required_outputs: tuple[str, ...]
    output_dir: str
    executor: str  # "engine" = fully deterministic; "host-skill" = LLM does interpretation, engine validates
    api_cost: ApiCostCategory
    needs_author_review: bool
    key_gate: str
    inputs: tuple[str, ...] = field(default_factory=tuple)


CONTRACTS: dict[str, SkillContract] = {
    "literature-search": SkillContract(
        "literature-search",
        ("search-strategy.md", "papers.xlsx", "papers.csv", "references.bib", "search-log.json"),
        "literature", "engine", ApiCostCategory.LOW, False,
        "Never invent articles; report coverage and access level", ("topic", "year_from", "year_to", "target_count"),
    ),
    "paper-analyzer": SkillContract(
        "paper-analyzer", ("paper-analysis.md", "paper-analysis.json"), "analysis", "host-skill", ApiCostCategory.NONE, True,
        "Explicit ABSTRACT_ONLY label if no full text", ("source_ids", "question"),
    ),
    "literature-review": SkillContract(
        "literature-review", ("literature-matrix.xlsx", "literature-synthesis.md", "review-evidence.json"), "literature",
        "host-skill", ApiCostCategory.NONE, True, "Every claim linked to evidence", ("source_ids",),
    ),
    "research-gap-finder": SkillContract(
        "research-gap-finder", ("research-gaps.md", "candidate-hypotheses.md", "feasibility-report.md"), "analysis",
        "host-skill", ApiCostCategory.NONE, True, "Candidate gap is not proven novelty", ("scope", "constraints"),
    ),
    "manuscript-builder": SkillContract(
        "manuscript-builder", ("manuscript-outline.md", "manuscript-draft.docx", "missing-information.md"), "manuscript",
        "host-skill", ApiCostCategory.NONE, True, "Never generate fictitious methods/results", ("author_facts", "journal_rules"),
    ),
    "citation-verifier": SkillContract(
        "citation-verifier", ("citation-audit.xlsx", "citation-audit.md", "verified-references.bib"), "reviews",
        "engine", ApiCostCategory.LOW, False, "Metadata check is not claim-support verification", ("manuscript_path", "bib_path"),
    ),
    "academic-integrity": SkillContract(
        "academic-integrity", ("integrity-audit.md", "ai-disclosure-draft.docx", "submission-checklist.md"), "reviews",
        "host-skill", ApiCostCategory.NONE, True, "No fake plagiarism-free certificates or AI detector evasion", ("ai_use", "journal_policy"),
    ),
    "peer-reviewer": SkillContract(
        "peer-reviewer", ("peer-review-report.md", "revision-plan.xlsx", "response-to-reviewers-draft.docx"), "reviews",
        "host-skill", ApiCostCategory.NONE, True, "Simulated review; no acceptance guarantee", ("manuscript_path", "rubric"),
    ),
    "research-progress": SkillContract(
        "research-progress", ("project-status.json", "research-progress.xlsx", "next-actions.md"), "progress",
        "engine", ApiCostCategory.NONE, False, "No evidence-free completion marks", (),
    ),
}

PIPELINE_ORDER = [
    "literature-search", "paper-analyzer", "literature-review", "research-gap-finder",
    "manuscript-builder", "citation-verifier", "academic-integrity", "peer-reviewer", "research-progress",
]
