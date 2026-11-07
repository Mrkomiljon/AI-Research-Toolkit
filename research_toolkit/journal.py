"""journal-standards engine half: reporting-guideline checklists, structural/declaration detection, cover letter."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .exporters import read_text_any, write_docx, write_markdown, write_xlsx
from .pipelines import PLACEHOLDER_RE
from .project_manager import ProjectManager
from .schemas import AuthorReviewStatus, ValidationStatus

# Condensed working checklists (not the official statements; see skills/journal-standards/references/reporting-guidelines.md)
GUIDELINES: dict[str, dict[str, Any]] = {
    "generic": {"name": "IMRaD + ICMJE (generic)", "version": "n/a", "items": [
        ("T1", "Title", "Informative title; study design indicated where relevant"),
        ("A1", "Abstract", "Structured or unstructured per journal; background, methods, results, conclusion"),
        ("I1", "Introduction", "Scientific background, rationale and explicit objectives/hypotheses"),
        ("M1", "Methods", "Design, setting, participants/data, variables, measurements, analysis, software"),
        ("M2", "Methods", "Ethics approval and consent, or statement why not required"),
        ("R1", "Results", "Main results with effect sizes and uncertainty (CI); numbers consistent across text, tables, figures"),
        ("D1", "Discussion", "Key results, limitations, interpretation, generalisability"),
        ("O1", "Other", "Funding, conflicts of interest, data availability, code availability, author contributions"),
    ]},
    "CONSORT": {"name": "CONSORT 2010", "version": "2010", "items": [
        ("1a", "Title", "Identification as a randomised trial in the title"), ("1b", "Abstract", "Structured summary of design, methods, results, conclusions"),
        ("2a", "Introduction", "Scientific background and rationale"), ("2b", "Introduction", "Specific objectives or hypotheses"),
        ("3a", "Methods", "Trial design incl. allocation ratio"), ("4a", "Methods", "Eligibility criteria for participants"), ("4b", "Methods", "Settings and locations"),
        ("5", "Methods", "Interventions with sufficient detail to replicate"), ("6a", "Methods", "Pre-specified primary and secondary outcomes"),
        ("7a", "Methods", "Sample size determination"), ("8a", "Methods", "Random allocation sequence generation"), ("9", "Methods", "Allocation concealment"),
        ("11a", "Methods", "Blinding"), ("12a", "Methods", "Statistical methods for primary/secondary outcomes"),
        ("13a", "Results", "Participant flow (CONSORT diagram)"), ("15", "Results", "Baseline characteristics table"), ("17a", "Results", "Outcomes and estimation with effect size and CI"),
        ("19", "Results", "Harms"), ("20", "Discussion", "Limitations"), ("21", "Discussion", "Generalisability"), ("22", "Discussion", "Interpretation"),
        ("23", "Other", "Registration number and registry"), ("24", "Other", "Protocol access"), ("25", "Other", "Funding"),
    ]},
    "STROBE": {"name": "STROBE", "version": "v4 2007", "items": [
        ("1", "Title/Abstract", "Design indicated; informative abstract"), ("2", "Introduction", "Background/rationale"), ("3", "Introduction", "Objectives"),
        ("4", "Methods", "Study design"), ("5", "Methods", "Setting, locations, dates"), ("6", "Methods", "Participants: eligibility, sources, selection"),
        ("7", "Methods", "Variables: outcomes, exposures, confounders"), ("8", "Methods", "Data sources/measurement"), ("9", "Methods", "Bias"),
        ("10", "Methods", "Study size"), ("11", "Methods", "Quantitative variables handling"), ("12", "Methods", "Statistical methods incl. missing data"),
        ("13", "Results", "Participants numbers at each stage"), ("14", "Results", "Descriptive data"), ("15", "Results", "Outcome data"),
        ("16", "Results", "Main results with CI; confounders adjusted"), ("17", "Results", "Other analyses"), ("18", "Discussion", "Key results"),
        ("19", "Discussion", "Limitations"), ("20", "Discussion", "Interpretation"), ("21", "Discussion", "Generalisability"), ("22", "Other", "Funding"),
    ]},
    "STARD": {"name": "STARD 2015", "version": "2015", "items": [
        ("1", "Title/Abstract", "Identification as diagnostic accuracy study"), ("2", "Abstract", "Structured abstract (STARD for abstracts)"),
        ("3", "Introduction", "Scientific and clinical background incl. intended use and role of index test"), ("4", "Introduction", "Study objectives and hypotheses"),
        ("5", "Methods", "Prospective or retrospective data collection"), ("6", "Methods", "Eligibility criteria"), ("7", "Methods", "Basis for identifying participants"),
        ("8", "Methods", "Setting, location, dates"), ("9", "Methods", "Consecutive, random or convenience series"), ("10a", "Methods", "Index test details to allow replication"),
        ("10b", "Methods", "Reference standard details"), ("11", "Methods", "Rationale for reference standard"), ("12a", "Methods", "Definition of positivity cut-offs, pre-specified or exploratory"),
        ("13a", "Methods", "Whether index test readers had clinical/reference information"), ("14", "Methods", "Methods for estimating diagnostic accuracy"),
        ("15", "Methods", "Handling indeterminate results"), ("16", "Methods", "Handling missing data"), ("17", "Methods", "Variability analyses pre-specified or exploratory"),
        ("18", "Methods", "Sample size and how determined"), ("19", "Results", "Flow of participants (diagram)"), ("20", "Results", "Baseline characteristics"),
        ("21a", "Results", "Distribution of severity in those with target condition"), ("23", "Results", "Cross tabulation index test vs reference standard"),
        ("24", "Results", "Estimates of accuracy with precision (CI)"), ("25", "Results", "Adverse events"), ("26", "Discussion", "Limitations incl. bias and generalisability"),
        ("27", "Discussion", "Implications for practice incl. intended use"), ("28", "Other", "Registration"), ("29", "Other", "Protocol"), ("30", "Other", "Funding and roles"),
    ]},
    "TRIPOD": {"name": "TRIPOD 2015 (+AI 2024 extension items marked AI)", "version": "2015 / TRIPOD+AI 2024", "items": [
        ("1", "Title", "Identify as developing/validating a prediction model; target population; outcome"), ("2", "Abstract", "Summary of objectives, design, setting, participants, sample size, predictors, outcome, analysis, results, conclusions"),
        ("3a", "Introduction", "Medical context and rationale"), ("3b", "Introduction", "Objectives: development and/or validation"),
        ("4a", "Methods", "Source of data (study design)"), ("4b", "Methods", "Dates of recruitment and follow-up"), ("5a", "Methods", "Setting(s)/centres"),
        ("5b", "Methods", "Eligibility criteria"), ("6a", "Methods", "Outcome definition and assessment"), ("7a", "Methods", "Predictors definition and measurement"),
        ("8", "Methods", "Sample size"), ("9", "Methods", "Missing data handling"), ("10a", "Methods", "Predictor handling in analysis"),
        ("10b", "Methods", "Model type, building procedure, internal validation"), ("10d", "Methods", "Performance measures (discrimination, calibration)"),
        ("10e", "Methods", "Model updating / adaptation if any"), ("AI-1", "Methods", "AI: data preprocessing, image acquisition, annotation and labelling process"),
        ("AI-2", "Methods", "AI: model architecture, training, hyperparameters, software/hardware"), ("AI-3", "Methods", "AI: fairness and subgroup evaluation plan"),
        ("13a", "Results", "Participant flow and numbers per centre"), ("13b", "Results", "Characteristics incl. outcome prevalence per dataset"),
        ("15a", "Results", "Full model specification or enough to apply it"), ("16", "Results", "Performance with CI, incl. external validation per site"),
        ("18", "Discussion", "Limitations"), ("19b", "Discussion", "Interpretation incl. comparison with similar studies"), ("20", "Discussion", "Implications for use"),
        ("21", "Other", "Supplementary information / availability of code and model"), ("22", "Other", "Funding"),
    ]},
    "PRISMA": {"name": "PRISMA 2020", "version": "2020", "items": [
        ("1", "Title", "Identify as systematic review"), ("2", "Abstract", "PRISMA abstract checklist"), ("3", "Introduction", "Rationale"), ("4", "Introduction", "Objectives"),
        ("5", "Methods", "Eligibility criteria"), ("6", "Methods", "Information sources with dates"), ("7", "Methods", "Full search strategies"), ("8", "Methods", "Selection process"),
        ("9", "Methods", "Data collection process"), ("10a", "Methods", "Data items: outcomes"), ("11", "Methods", "Risk of bias assessment"), ("13a", "Methods", "Synthesis methods"),
        ("14", "Methods", "Reporting bias assessment"), ("15", "Methods", "Certainty assessment"), ("16a", "Results", "Study selection with flow diagram"), ("17", "Results", "Study characteristics"),
        ("18", "Results", "Risk of bias in studies"), ("20b", "Results", "Results of syntheses"), ("23a", "Discussion", "Interpretation"), ("23c", "Discussion", "Limitations of review"),
        ("24a", "Other", "Registration and protocol"), ("25", "Other", "Support/funding"), ("27", "Other", "Availability of data, code and materials"),
    ]},
    "ARRIVE": {"name": "ARRIVE 2.0 Essential 10", "version": "2.0", "items": [
        ("1", "Methods", "Study design: groups, experimental unit"), ("2", "Methods", "Sample size and how decided"), ("3", "Methods", "Inclusion/exclusion criteria"),
        ("4", "Methods", "Randomisation"), ("5", "Methods", "Blinding"), ("6", "Methods", "Outcome measures"), ("7", "Methods", "Statistical methods"),
        ("8", "Methods", "Experimental animals: species, strain, sex, age, weight"), ("9", "Methods", "Experimental procedures"), ("10", "Results", "Results with descriptive and inferential statistics per group"),
    ]},
    "CARE": {"name": "CARE case report", "version": "2013", "items": [
        ("1", "Title", "Diagnosis/intervention of focus and 'case report'"), ("3", "Abstract", "Introduction, presentation, conclusions"), ("4", "Introduction", "Why case is unique with references"),
        ("5", "Patient information", "De-identified demographics, concerns, history"), ("6", "Clinical findings", "Physical examination"), ("7", "Timeline", "Dates and times of care"),
        ("8", "Diagnostic assessment", "Methods, challenges, reasoning, prognosis"), ("9", "Therapeutic intervention", "Types, administration, changes"), ("10", "Follow-up", "Outcomes, adherence, adverse events"),
        ("11", "Discussion", "Strengths/limitations, literature, rationale, take-away"), ("12", "Patient perspective", "Patient's view"), ("13", "Informed consent", "Consent obtained"),
    ]},
}

SECTION_PATTERNS = {
    "Title": r"^#\s", "Abstract": r"abstract", "Introduction": r"introduction|background", "Methods": r"methods|materials and methods|methodology|patients and methods",
    "Results": r"results|findings", "Discussion": r"discussion", "Conclusion": r"conclusion", "References": r"references|bibliography",
}
DECLARATION_PATTERNS = {
    "ethics approval": r"ethic(s|al) (approval|committee)|institutional review board|\bIRB\b",
    "informed consent": r"informed consent|consent (was|were) (obtained|waived)",
    "conflicts of interest": r"conflicts? of interest|competing interests|nothing to disclose",
    "funding": r"\bfunding\b|\bgrant\b|supported by",
    "data availability": r"data (availability|are available|is available|sharing)",
    "code availability": r"code (availability|is available|are available)|github\.com",
    "author contributions": r"author contributions|CRediT|contributed to",
    "AI-use statement": r"(generative )?AI (use|tools?)|large language model|ChatGPT|Claude",
    "trial/protocol registration": r"registered (at|with|in)|registration number|NCT\d+|PROSPERO",
}


def _section_texts(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    current = "(preamble)"
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            found[current] = found.get(current, "") + "\n".join(buf)
            current, buf = line.lstrip("#").strip(), []
        else:
            buf.append(line)
    found[current] = found.get(current, "") + "\n".join(buf)
    return found


def analyse_structure(text: str, *, word_limit: int | None = None, abstract_limit: int | None = None) -> dict[str, Any]:
    secs = _section_texts(text)
    detected: dict[str, str | None] = {}
    for canon, pat in SECTION_PATTERNS.items():
        hit = None
        if canon == "Title":
            hit = next((h for h in secs if h != "(preamble)"), None)
        else:
            hit = next((h for h in secs if re.search(pat, h, re.IGNORECASE)), None)
        detected[canon] = hit
    body_words = sum(len(v.split()) for h, v in secs.items() if h != "(preamble)" and not re.search(r"references|bibliography|declarations", h, re.IGNORECASE))
    abstract_words = len(secs.get(detected["Abstract"], "").split()) if detected["Abstract"] else 0
    declarations = {k: bool(re.search(p, text, re.IGNORECASE)) for k, p in DECLARATION_PATTERNS.items()}
    placeholders = PLACEHOLDER_RE.findall(text)
    numeric_refs = len(re.findall(r"\[\d+(?:[-–,]\s*\d+)*\]", text))
    author_year = len(re.findall(r"\([A-Z][A-Za-z\-']+(?: et al\.)?,? \d{4}[a-z]?\)", text))
    style_hint = "numeric (Vancouver-like)" if numeric_refs > author_year else ("author-year (APA/Harvard-like)" if author_year else "toolkit ids / none detected")
    return {
        "sections": detected,
        "missing_sections": [k for k, v in detected.items() if v is None and k != "Title"],
        "body_words": body_words, "word_limit": word_limit, "over_word_limit": bool(word_limit and body_words > word_limit),
        "abstract_words": abstract_words, "abstract_limit": abstract_limit, "over_abstract_limit": bool(abstract_limit and abstract_words > abstract_limit),
        "declarations": declarations, "missing_declarations": [k for k, v in declarations.items() if not v],
        "placeholders": len(placeholders), "citation_style_hint": style_hint,
        "figures_tables_referenced": len(re.findall(r"\b(Fig(?:ure)?|Table)\s*\d+", text)),
    }


def _guess_location(item_section: str, detected: dict[str, str | None]) -> str:
    key = next((k for k in detected if k.lower() in item_section.lower()), None)
    return detected.get(key) or "" if key else ""


def build_checklist(pm: ProjectManager, manuscript_rel: str, guideline: str = "generic", *, guidelines_file: str | None = None,
                    word_limit: int | None = None, abstract_limit: int | None = None, run_id=None, step_id=None) -> dict[str, Any]:
    key = guideline.upper() if guideline.upper() in GUIDELINES else guideline.lower()
    if key not in GUIDELINES:
        raise ValueError(f"unknown guideline {guideline!r}; choose from {sorted(GUIDELINES)}")
    g = GUIDELINES[key]
    text = read_text_any(pm.resolve(manuscript_rel))
    if not text.strip():
        raise ValueError(f"{manuscript_rel} is empty")
    st = analyse_structure(text, word_limit=word_limit, abstract_limit=abstract_limit)
    rows = [{"item": i, "section": s, "requirement": r, "status": "", "location": _guess_location(s, st["sections"]) and f"section '{_guess_location(s, st['sections'])}' (verify)",
             "comment": ""} for i, s, r in g["items"]]
    reviews = pm.workspace / "reviews"
    xlsx = write_xlsx({"checklist": rows, "structure": [{"check": k, "value": str(v)} for k, v in st.items() if k not in ("sections", "declarations")],
                       "declarations": [{"declaration": k, "found": v} for k, v in st["declarations"].items()]},
                      reviews / "reporting-checklist.xlsx",
                      {"checklist": ["item", "section", "requirement", "status", "location", "comment"], "structure": ["check", "value"], "declarations": ["declaration", "found"]})
    guide_text = Path(pm.resolve(guidelines_file)).read_text(encoding="utf-8", errors="replace") if guidelines_file else None
    sections_md = [
        ("Guideline", f"- {g['name']} (version {g['version']}); {len(g['items'])} condensed items in `reporting-checklist.xlsx` — status/location/comment to be filled by the reviewer. Cite the official checklist in the submission."),
        ("Structure detected", "\n".join(f"- {k}: {v or '**missing**'}" for k, v in st["sections"].items())),
        ("Limits", f"- Body words: {st['body_words']}" + (f" / limit {word_limit} → {'OVER' if st['over_word_limit'] else 'ok'}" if word_limit else " (limit not checked)") +
                   f"\n- Abstract words: {st['abstract_words']}" + (f" / limit {abstract_limit} → {'OVER' if st['over_abstract_limit'] else 'ok'}" if abstract_limit else " (limit not checked)") +
                   f"\n- Figures/tables referenced: {st['figures_tables_referenced']}\n- Citation style hint: {st['citation_style_hint']}"),
        ("Declarations found", "\n".join(f"- {'[x]' if v else '[ ]'} {k}" for k, v in st["declarations"].items())),
        ("Placeholders left", f"- {st['placeholders']} `[MISSING]`/`[AUTHOR INPUT NEEDED]` markers" if st["placeholders"] else "- none"),
        ("Journal author guidelines", (guide_text[:4000] + ("…" if len(guide_text) > 4000 else "")) if guide_text else "_Not supplied; formatting limits not checked. Paste them into reviews/journal-guidelines.txt and re-run._"),
        ("Scope", "Structural detection is heuristic (headings, keywords). Content items must be judged by the reviewer. This is a readiness check, not a guarantee of acceptance or policy compliance."),
    ]
    md = write_markdown(reviews / "journal-compliance.md", "Journal and reporting-standard compliance", sections_md,
                        front_note=f"Generated by journal-standards for `{manuscript_rel}` with {g['name']}.")
    for p in (xlsx, md):
        pm.register_artifact(p, skill="journal-standards", run_id=run_id, step_id=step_id, validation_status=ValidationStatus.VALID,
                             author_review=AuthorReviewStatus.PENDING)
    return {"guideline": g["name"], "items": len(rows), "structure": st, "artifacts": [str(xlsx), str(md)]}


def cover_letter(pm: ProjectManager, manuscript_rel: str, journal: str | None = None, *, run_id=None, step_id=None) -> dict[str, Any]:
    text = read_text_any(pm.resolve(manuscript_rel))
    title = next((ln.lstrip("#").strip() for ln in text.splitlines() if ln.startswith("# ")), "[TITLE]")
    out = write_docx(
        pm.workspace / "reviews" / "cover-letter-draft.docx", "Cover letter (draft)",
        [
            ("", f"Dear Editor of {journal or '[JOURNAL NAME]'},\n\nWe are pleased to submit the manuscript entitled \"{title}\" for consideration as an original research article."),
            ("Summary", "[AUTHOR INPUT NEEDED: two or three sentences on the question, approach and main finding, using only results that appear in the manuscript.]"),
            ("Why this journal", "[AUTHOR INPUT NEEDED: fit with the journal's scope and readership.]"),
            ("Novelty and significance", "[AUTHOR INPUT NEEDED: what is new relative to prior work; the toolkit does not assert novelty on your behalf. See analysis/research-gaps.md for candidate gaps that still require full-text verification.]"),
            ("Declarations", "This manuscript has not been published and is not under consideration elsewhere. All authors approved the submission. [AUTHOR INPUT NEEDED: conflicts of interest, funding, ethics approval number, data/code availability, AI-use statement if required by the journal.]"),
            ("Suggested reviewers", "[AUTHOR INPUT NEEDED or 'none']"),
            ("", "Sincerely,\n[CORRESPONDING AUTHOR, affiliation, e-mail]"),
        ],
        metadata_note="Draft generated by journal-standards. Every bracketed item must be completed by the authors.",
    )
    pm.register_artifact(out, skill="journal-standards", run_id=run_id, step_id=step_id, validation_status=ValidationStatus.VALID,
                         author_review=AuthorReviewStatus.PENDING, tentative=True)
    return {"artifact": str(out), "title": title}
