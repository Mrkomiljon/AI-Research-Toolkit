---
name: literature-review
description: Build a comparison matrix and an evidence-linked thematic synthesis from completed paper analyses (literature-matrix.xlsx, literature-synthesis.md, review-evidence.json). Use when the user asks to compare papers, build a literature matrix or write a literature review/synthesis (uz "taqqosla", ru "сравни / обзор"). Every claim must cite src-/ev- ids.
---

# literature-review

The engine builds the matrix and the evidence bundle from `analysis/*/paper-analysis.json`; you write the synthesis.
Every substantive paragraph you write must reference evidence (`ev-…`) or source (`src-…`) ids that exist.

## Inputs

- Completed analyses (≥ 2). Missing ones → run `paper-analyzer` first (orchestrator does this automatically).
- Optional list of `source_ids` to include; otherwise all analyzed papers.
- Themes or comparison axes the user cares about (methods, datasets, regions, outcomes).

## Workflow

1. Build the matrix and evidence bundle:
   ```bash
   rtk review matrix -p <ws> [--source-ids src-… src-…]
   ```
   → `literature/literature-matrix.xlsx` (one row per paper: objective/methods/sample/outcomes/limitations + locators,
   access level, evidence ids) and `literature/review-evidence.json`.
2. Read the matrix and `review-evidence.json`. Group papers by theme. Note access levels: a theme supported only by
   `ABSTRACT_ONLY` papers must be labelled as such.
3. Write `literature/literature-synthesis.md`: introduction, themes (each paragraph ends with the supporting ids, e.g.
   `[ev-1a2b3c4d5e; src-…]`), methodological comparison, agreements/discrepancies, limitations of the evidence base
   (number of full-text vs abstract-only papers), and a short "what this synthesis does not establish" note.
4. Validate links:
   ```bash
   rtk review validate-links -p <ws> --file literature/literature-synthesis.md
   ```
   Exit 5 lists unknown ids and unlinked paragraphs; fix and re-run until `ok: true`.
5. Checkpoint with `--needs-review`; the synthesis is interpretation and needs the user's approval.

## Outputs

`literature/literature-matrix.xlsx`, `literature/literature-synthesis.md`, `literature/review-evidence.json`.

## Validation / key gate

Every claim linked to evidence. No paper outside the registry is mentioned. Discrepancies between papers are reported,
not smoothed over.

## Failure behavior

No analyses → `blocked` with instruction to analyze papers first. Contradictory findings → report both with ids.
