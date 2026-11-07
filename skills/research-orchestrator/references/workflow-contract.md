# Workflow contract

## Files

| File | Purpose |
|---|---|
| `workflow/plan.yaml` | current plan (schema `WorkflowPlan`), rewritten on every checkpoint |
| `workflow/history/<run_id>.yaml` | copy per run |
| `workflow/runs.jsonl` | append-only event log (`plan_created`, `step_started`, `step_completed`, `step_blocked`, `step_failed`, `step_skipped`, `step_awaiting_user_review`, `approval_granted`, `run_resumed`) |
| `progress/artifacts.json` | artifact registry: path, sha256, skill, validation_status, author_review_status, tentative |
| `progress/project-status.json` | derived status (never LLM-estimated) |

## Step statuses

`planned` → `running` → `completed` | `blocked` | `failed` | `skipped` | `awaiting_user_review` → (`approve-review`) → `completed`

- `blocked`: cannot proceed truthfully (missing PDF, provider down, budget exceeded, approval missing). Partial artifacts are kept.
- `failed`: unexpected error; the message holds the exception.
- `skipped`: verified outputs already existed or the stage was not needed.
- `awaiting_user_review`: artifacts exist but contain interpretation that the user must approve.

A step can only start when all `depends_on` steps are `completed` or `skipped`, its approval (if required) is recorded,
and `attempts <= max_retries_per_step + 1`.

## Checkpoint protocol for host-skill steps

```bash
rtk step start -p <ws> s2
# do the work described in the specialist SKILL.md; write every file in `produces`
rtk step complete -p <ws> s2 --artifacts <rel paths...> [--needs-review] [--tentative] [--message "..."]
```

`step complete` re-checks that every declared output exists and is non-empty; otherwise the step becomes `blocked`.
`--needs-review` registers the artifacts with `author_review_status=pending` and parks the step in `awaiting_user_review`.
After the user approves: `rtk step approve-review -p <ws> s2`.

## Resume

`rtk resume -p <ws>`:
1. `running` steps (interrupted) → `planned` and re-queued.
2. `completed` steps are re-validated against disk; missing/empty outputs → `planned` again with the reason.
3. Valid completed steps are kept; nothing verified is repeated.

## Validation per stage (minimum)

| Stage | Engine check |
|---|---|
| literature-search | `search-log.json` coverage, access levels, errors; registry stats |
| paper-analyzer | `rtk analyze finalize` — locator rules by access level, verbatim excerpt check, evidence records |
| literature-review | `rtk review matrix`; `rtk review validate-links --file literature/literature-synthesis.md` |
| research-gap-finder | `rtk review gap-seed`; `rtk review validate-gaps --file analysis/research-gaps.md` |
| manuscript-builder | `rtk manuscript check-inputs --file manuscript/manuscript-outline.md`; `rtk manuscript to-docx` |
| citation-verifier | `rtk verify-citations --manuscript <path>` (exit 5 on failures) |
| academic-integrity | `rtk integrity --ai-use <json>` |
| peer-reviewer | `rtk peer-review --comments <json> --report <md>` |
| research-progress | `rtk status` |
| academic-writing | `rtk writing check --file <edited> --compare-with <original>` (ids/numbers/citations unchanged) |
| journal-standards | `rtk journal checklist --manuscript <path> --guideline <KEY>`; `rtk journal cover-letter` |

## Reporting rule

`rtk report` lists only files present on disk. Your summary to the user must match it (acceptance test 10).
