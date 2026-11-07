---
name: research-progress
description: Compute auditable research progress from artifacts on disk, workflow runs and user confirmations — stage statuses, blockers, next actions and milestones (project-status.json, research-progress.xlsx, next-actions.md). Use when the user asks where they are, what is done, what is blocked or what to do next (uz "qayerdaman / holat", ru "где я / статус"). No evidence-free completion marks and no guessed percentages.
---

# research-progress

Deterministic skill. The engine derives every status from validated artifacts, the artifact registry and the event log.
You present it in the user's language and record user-confirmed milestones.

## Inputs

- Workspace. Optional: milestones the user wants tracked (recorded as notes in `next-actions.md`).
- User confirmations (e.g. "I approved the synthesis") → `rtk step approve-review -p <ws> <step>`.

## Workflow

1. Run:
   ```bash
   rtk status -p <ws>
   ```
   → `progress/project-status.json`, `progress/research-progress.xlsx`, `progress/next-actions.md`.
2. Present per stage: `not_started` / `in_progress` / `awaiting_user_review` / `completed` / `blocked`, the artifacts
   that justify it, and blockers with their recorded reasons. Report counts (sources, verified, full-text, evidence),
   never a percentage estimate.
3. Propose next actions from `next_actions` plus anything the user mentions. If the user says a stage is done but no
   artifact exists, say that it cannot be marked complete until the output is on disk.
4. For an orchestrated plan, also show `rtk report -p <ws>` so the plan status and files match disk.

## Outputs

`progress/project-status.json`, `progress/research-progress.xlsx`, `progress/next-actions.md`.

## Validation / key gate

No evidence-free completion marks. Completed = all required outputs present, valid and (where required) author-approved.

## Failure behavior

Corrupt registry or plan → report the parse error and the file path; do not estimate.
