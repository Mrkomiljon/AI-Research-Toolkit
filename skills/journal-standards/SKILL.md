---
name: journal-standards
description: Check a manuscript against international publication standards — IMRaD structure, a reporting guideline checklist (CONSORT, STROBE, STARD, TRIPOD, PRISMA, ARRIVE, CARE or generic), ICMJE authorship and declarations, a target journal's author guidelines (word/figure limits, abstract format, reference style) — and draft a cover letter (reporting-checklist.xlsx, journal-compliance.md, cover-letter-draft.docx). Use when the user asks whether a paper meets journal or reporting requirements, how to adapt it to a journal, or for a submission checklist (uz "xalqaro standartga moslashtir", ru "привести к требованиям журнала"). No guarantee of acceptance or compliance.
---

# journal-standards

You map the manuscript onto the reporting guideline that fits its study design and onto the target journal's
author instructions, then say precisely what is present, missing or non-compliant. The engine builds the checklist
and detects sections, word counts and declarations; you judge content items and write the cover letter draft.

## Inputs

- Manuscript path (`.md`/`.docx`).
- Study design (ask if unclear): randomised trial → CONSORT; observational → STROBE; diagnostic accuracy → STARD;
  prediction model / AI → TRIPOD (TRIPOD+AI); systematic review → PRISMA; animal study → ARRIVE; case report → CARE;
  otherwise `generic` (IMRaD + ICMJE). See [references/reporting-guidelines.md](references/reporting-guidelines.md).
- Target journal author guidelines: paste the relevant text into `reviews/journal-guidelines.txt` (word limits,
  abstract type, reference style, figure limits, required statements). Do not guess limits; if unknown, say so.

## Engine

Before the first `rtk` command of a session run `rtk --version`. If the command is missing or fails, install the engine
yourself and tell the user in one line that you did: `python -m pip install -U ai-research-toolkit` (Python 3.11+; if
Python itself is missing, stop and say so). If `rtk` is still not found afterwards, use `python -m research_toolkit`
wherever this skill says `rtk`. Do not ask the user to run install commands by hand.

## Workflow

1. Build the checklist and structural report:
   ```bash
   rtk journal checklist -p <ws> --manuscript manuscript/manuscript-draft.docx --guideline STARD [--guidelines-file reviews/journal-guidelines.txt] [--word-limit 3500] [--abstract-limit 250]
   ```
   → `reviews/reporting-checklist.xlsx` (one row per guideline item with `status` to fill: present / partial /
   missing / not applicable, and `location`), `reviews/journal-compliance.md` (sections detected, word counts vs
   limits, declarations found, placeholders left, citation style hints).
2. Read the manuscript and fill the checklist `status`/`location`/`comment` columns item by item. Quote the manuscript
   location (section, paragraph) for every "present"; do not mark present without a location.
3. Append to `reviews/journal-compliance.md`: items missing or partial with a concrete fix for each; declarations
   missing (ethics, consent, data availability, code availability, funding, conflicts, author contributions per
   ICMJE, AI-use statement if the journal requires it); structural fixes (abstract format, section order, limits).
4. Draft `reviews/cover-letter-draft.docx` with `rtk journal cover-letter -p <ws> --manuscript <path> --journal "<name>"`
   — it contains `[AUTHOR INPUT NEEDED]` for novelty statement, suggested reviewers and conflicts; never claim the
   work is novel on the author's behalf.
5. Checkpoint with `--needs-review`.

## Outputs

`reviews/reporting-checklist.xlsx`, `reviews/journal-compliance.md`, `reviews/cover-letter-draft.docx`.

## Validation / key gate

Every "present" item has a manuscript location. The report distinguishes *guideline items* (content) from *journal
formatting* (limits/style) and states which guideline version was used. This is a readiness check, not a promise
of acceptance or of compliance with a journal's current policy, which the author must re-check on the journal site.

## Failure behavior

Study design cannot be determined → use `generic` and ask the author. Journal guidelines not supplied → report
structure and declarations only and mark limits as "not checked".
