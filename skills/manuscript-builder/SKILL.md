---
name: manuscript-builder
description: Turn the author's real facts, results and verified sources into an IMRaD manuscript outline and an author-reviewed draft (manuscript-outline.md, manuscript-draft.docx, missing-information.md) following target journal rules. Use when the user asks to prepare, outline, draft or structure an article/manuscript/paper (uz "maqola tayyorla", ru "подготовь статью"). Never generates fictitious methods, results or data.
---

# manuscript-builder

You structure and draft; the author supplies every fact. Where a fact is missing you insert `[MISSING: …]` and the
engine lists it in `missing-information.md`. Drafting is a gated step (approval required) because it writes files the
author owns.

## Inputs

- Author facts: research question, actual methods, data, results (tables/numbers as given), interpretation notes.
- Verified sources (`sources/sources.json`, `verification_status=verified`) and evidence ids.
- Journal rules: structure, word limits, citation style (ask; default IMRaD).
- Optional existing draft (`manuscript/*.md` or `.docx`) — never overwritten silently.

## Workflow

1. Confirm approval for drafting (`rtk approve -p <ws> <step>` after the user says yes) and collect the inputs above.
   If results or methods are absent, say so and produce only the outline with placeholders.
2. Write `manuscript/manuscript-outline.md`: title, abstract skeleton, Introduction, Methods, Results, Discussion,
   Conclusion, References. Cite with source ids in brackets (`[src-…]`) so the verifier can map them; use `[MISSING: …]`
   for anything the author has not provided.
3. Check inputs:
   ```bash
   rtk manuscript check-inputs -p <ws> --file manuscript/manuscript-outline.md
   ```
   → `manuscript/missing-information.md` (placeholders, unknown or unverified source ids).
4. Draft section by section **after** the author reviews the outline. Keep author wording for results; do not add
   statistics, effect sizes or participants that are not in the author's material.
5. Export:
   ```bash
   rtk manuscript to-docx -p <ws> --file manuscript/manuscript-outline.md --out manuscript-draft.docx
   ```
   The engine refuses to overwrite a file the user edited since the toolkit wrote it (exit 3) unless the user
   explicitly asks for `--force`.
6. Checkpoint with `--needs-review --tentative`. Remind the user the draft is not submission-ready.

## Outputs

`manuscript/manuscript-outline.md`, `manuscript/manuscript-draft.docx`, `manuscript/missing-information.md`.

## Validation / key gate

Never generate fictitious methods/results. All cited ids exist and are verified; otherwise they appear in
`missing-information.md`. Author approves every section.

## Failure behavior

Missing essential author data → outline only, step `blocked` or `awaiting_user_review` with the exact list of what is needed.
