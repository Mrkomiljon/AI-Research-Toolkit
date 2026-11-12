---
name: academic-integrity
description: Check attribution, source provenance, AI-use disclosure and an ethics/submission checklist for a manuscript against the target journal's policy, producing integrity-audit.md, ai-disclosure-draft.docx and submission-checklist.md. Use when the user asks about plagiarism risk, AI disclosure, research ethics or submission readiness (uz "akademik halollik", ru "академическая честность"). Never issues plagiarism-free certificates or helps evade AI detectors.
---

# academic-integrity

You collect the author's actual AI use and the journal policy, the engine writes the audit scaffold and disclosure
draft, and you review the manuscript for attribution problems. Outputs are drafts for the author, not certificates.

## Inputs

- Author-stated AI use as JSON (`reviews/ai-use.json`):
  `{"tools": ["Claude Code"], "stages": ["literature search", "outline"], "human_review": "all text reviewed by author",
  "data_shared_with_tools": "abstracts only; no unpublished data"}` — ask, do not assume.
- Journal policy text (paste into `reviews/journal-policy.txt`) if available.
- Manuscript path (optional, for attribution checks).

## Engine

Before the first `rtk` command of a session run `rtk --version`. If the command is missing or fails, install the engine
yourself and tell the user in one line that you did: `python -m pip install -U ai-research-toolkit` (Python 3.11+; if
Python itself is missing, stop and say so). If `rtk` is still not found afterwards, use `python -m research_toolkit`
wherever this skill says `rtk`. Do not ask the user to run install commands by hand.

## Workflow

1. Ask the author what AI tools were used, for which stages, what they reviewed, and what data was shared. Write the JSON.
2. Run:
   ```bash
   rtk integrity -p <ws> --ai-use reviews/ai-use.json [--journal-policy reviews/journal-policy.txt] [--manuscript manuscript/manuscript-draft.docx]
   ```
3. Review the manuscript yourself for: quotations without locators, paraphrases of registry sources without citation,
   cited ids missing from the registry (listed by the engine), self-plagiarism risks the author mentions, data/ethics
   statements. Append findings to `reviews/integrity-audit.md` with ids and locations.
4. Compare the disclosure draft with the journal policy wording; adjust the draft, keep it truthful to actual use.
5. Checkpoint with `--needs-review`.

## Outputs

`reviews/integrity-audit.md`, `reviews/ai-disclosure-draft.docx`, `reviews/submission-checklist.md`.

## Validation / key gate

No fake plagiarism-free certificates, no AI-detector evasion, no guarantee of policy compliance. Disclosure reflects
the author's stated use only.

## Failure behavior

AI-use statement missing → produce the checklist with placeholders and leave the step `awaiting_user_review`.
