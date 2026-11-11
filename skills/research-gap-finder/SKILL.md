---
name: research-gap-finder
description: Compare limitations, methods and discrepancies across analyzed papers to propose candidate research gaps, testable hypotheses and a feasibility report (research-gaps.md, candidate-hypotheses.md, feasibility-report.md). Use when the user asks for research gaps, open questions, novelty or hypothesis ideas (uz "tadqiqot bo'shliqlari", ru "пробелы в исследованиях"). A candidate gap is never presented as proven novelty.
---

# research-gap-finder

You reason over the literature matrix and the gap seed to propose **candidate** gaps. The engine supplies the seed
and validates that every gap is evidence-linked and free of novelty over-claims.

## Inputs

- Completed literature matrix (`literature-review`); the orchestrator runs earlier stages if missing.
- Scope and constraints from the user: field, region, data availability, methods they can use, time/budget.

## Workflow

1. Collect the seed:
   ```bash
   rtk review gap-seed -p <ws>
   ```
   → `analysis/gap-seed.json` with limitations/methods/outcomes/sample per paper and evidence ids.
2. For each candidate gap write: statement; which papers' limitations or discrepancies motivate it (ids); what would
   count as evidence that it is already filled (so the user can check); risks. Minimum two source ids per gap, or an
   explicit "rests on a single paper" label.
3. Write `analysis/research-gaps.md` (ranked candidates), `analysis/candidate-hypotheses.md` (each hypothesis:
   variables, expected direction, testable design, ids) and `analysis/feasibility-report.md` (data, methods, time,
   ethics, constraints from the user; mark unknowns as unknowns).
4. Validate:
   ```bash
   rtk review validate-gaps -p <ws> --file analysis/research-gaps.md
   ```
   Fails on unknown ids, unlinked paragraphs or phrases like "proven novel", "nobody has studied".
5. Checkpoint with `--needs-review`. Tell the user that novelty must be confirmed by a broader search and expert
   judgement, and offer `gap-validator` (targeted counterevidence search per gap) as the next step. Keep the
   `## Gap N: <title>` heading format; `rtk gaps init` reads it.

## Outputs

`analysis/research-gaps.md`, `analysis/candidate-hypotheses.md`, `analysis/feasibility-report.md`.

## Validation / key gate

Candidate gap ≠ proven novelty. Gaps derived only from `ABSTRACT_ONLY` papers are labelled low-confidence.

## Failure behavior

Fewer than two analyzed papers → `blocked`; suggest extending the search or adding PDFs.
