---
name: research-concept-builder
description: Turn a validated research gap and the author's own decisions into a one-page Gap Canvas and a short concept paper — problem, what is known, gap, research question, hypothesis, proposed design, data, expected contribution, risks (gap-canvas.md, concept-paper.md, concept-paper.docx). Use when the user asks for a research concept, concept note/paper, gap canvas, or to shape a gap into a study idea before writing a proposal (uz "tadqiqot konsepsiyasi", "konsepsiya hujjati", ru "концепция исследования"). Design, data and timeline come from the author; missing parts stay as placeholders.
---

# research-concept-builder

You help the author turn one candidate gap into a study concept. Literature blocks must cite registered sources;
design blocks are the author's decisions. The engine builds the documents and marks whatever is missing, unconfirmed
or unvalidated instead of smoothing it over.

## Inputs

- A gap, ideally checked by `gap-validator` (`analysis/gap-validation.json`).
- From the author: research question, design/methods they can actually run, data and sample they have access to,
  resources, ethics constraints, timeline. Ask for these; do not assume them.

## Engine

Before the first `rtk` command of a session run `rtk --version`. If the command is missing or fails, install the engine
yourself and tell the user in one line that you did: `python -m pip install -U ai-research-toolkit` (Python 3.11+; if
Python itself is missing, stop and say so). If `rtk` is still not found afterwards, use `python -m research_toolkit`
wherever this skill says `rtk`. Do not ask the user to run install commands by hand.

## Workflow

1. Create the canvas form:
   ```bash
   rtk concept init -p <ws>
   ```
   → `manuscript/gap-canvas.json` listing the validated gaps. If it warns that no gap validation exists, tell the user
   and offer to run `gap-validator` first.
2. Agree with the author which gap to pursue and set `gap_id`. Do not pick an `already_addressed` gap.
3. Fill each block's `text` and `source`:
   - `problem`, `research_question`, `hypothesis`, `expected_contribution` — draft with the author; `source` is
     `author` once they have agreed to the wording, otherwise `agent_draft`.
   - `known`, `gap` — from the literature synthesis and gap report; must cite `src-…`/`ev-…` ids; `source: literature`.
   - `methods`, `data_resources`, `risks_ethics`, `timeline` — the author's decisions. Record what they tell you with
     `source: author`. If you propose something they have not confirmed, use `source: agent_draft`; it will be printed
     as UNCONFIRMED. Leave `text` null for anything unknown.
   Phrase the contribution as what the study would add if the gap holds; never "first", "novel" or "nobody has studied".
4. Build:
   ```bash
   rtk concept build -p <ws> [--canvas manuscript/gap-canvas.json] [--force]
   ```
   Fails (exit 5) on unknown ids, literature blocks without ids, novelty over-claims, or a gap judged
   `already_addressed`. Missing blocks become `[AUTHOR INPUT NEEDED: …]`; the result lists `missing`, `unconfirmed`
   and `warnings`. It will not overwrite a concept paper the author has edited unless `--force`.
5. Show the author the `missing` and `unconfirmed` lists and ask for those inputs; rebuild after they answer.
   Checkpoint with `--needs-review`. The concept paper is a draft until the author approves it.

## Outputs

`manuscript/gap-canvas.md`, `manuscript/concept-paper.md`, `manuscript/concept-paper.docx`.

## Validation / key gate

Never invent a design, sample size, dataset, budget or timeline. A concept built on an unvalidated or inconclusive gap
says so in the "Research gap" section and in "Status of this draft".

## Failure behavior

No canvas → run `rtk concept init`. Author cannot supply design or data yet → build anyway with placeholders and list
what is needed; do not mark the stage complete.
