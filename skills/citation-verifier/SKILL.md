---
name: citation-verifier
description: Audit a manuscript's citations against its bibliography and the source registry — DOI format and resolution (Crossref/OpenAlex), title/DOI mismatches, cited-but-missing and unused references — producing citation-audit.xlsx/md and verified-references.bib. Use when the user asks to check, verify or audit references, citations, DOIs or a bibliography (uz "iqtiboslarni tekshir", ru "проверь ссылки"). Metadata verification is not claim-support verification.
---

# citation-verifier

Deterministic skill. The engine parses the manuscript (`.md`, `.docx`, `.txt`), extracts citation keys
(`\cite{}`, `[@key]`, `[src-…]`, author-year mentions), parses BibTeX, checks DOIs and writes the audit. You explain
the findings and help the author fix them; you never "fix" a reference by inventing a DOI.

## Inputs

- `manuscript_path` (workspace-relative) — required
- `bib_path` (optional; default `sources/references.bib`)
- Offline mode when external APIs are disabled (`--offline`): format checks only, stated in the report.

## Engine

Before the first `rtk` command of a session run `rtk --version`. If the command is missing or fails, install the engine
yourself and tell the user in one line that you did: `python -m pip install -U ai-research-toolkit` (Python 3.11+; if
Python itself is missing, stop and say so). If `rtk` is still not found afterwards, use `python -m research_toolkit`
wherever this skill says `rtk`. Do not ask the user to run install commands by hand.

## Workflow

1. Run:
   ```bash
   rtk verify-citations -p <ws> --manuscript manuscript/manuscript-draft.docx [--bib sources/references.bib] [--offline]
   ```
   Exit code 0 = passed; 5 = failures or cited-but-missing references.
2. Read `reviews/citation-audit.md`. For each failure explain the category:
   - malformed DOI → ask the author for the correct one (do not guess)
   - DOI does not resolve → possible typo or fabricated reference; the author must locate the real record
   - title/DOI mismatch → the DOI belongs to another paper
   - cited but missing in bibliography / unused entry → editing task
3. Re-run after fixes. Only references that resolved with matching metadata appear in `reviews/verified-references.bib`.
4. Say explicitly: the audit verifies metadata only. Whether a cited paper actually supports the claim is checked by
   the `claim-verifier` skill (`rtk claims extract` / `rtk claims finalize`) and finally by the author.

## Outputs

`reviews/citation-audit.xlsx`, `reviews/citation-audit.md`, `reviews/verified-references.bib`.

## Validation / key gate

Invalid or non-resolving DOIs never pass. Metadata check ≠ claim-support verification.

## Failure behavior

Provider unavailable → entries marked `blocked: provider unavailable`, the step is `blocked`, partial audit kept; retry later.
