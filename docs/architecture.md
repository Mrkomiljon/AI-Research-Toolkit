# Architecture

## Two layers

```
┌───────────────────────────────── host agent (Claude Code / Codex) ─────────────────────────────────┐
│ skills/<name>/SKILL.md  — instructions the LLM follows: interpretation, drafting, review, dialogue │
│   research-orchestrator → plans, delegates, checkpoints, reports                                   │
└────────────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                             │ calls `rtk …` (stable CLI contract)
┌────────────────────────────────────────────▼───────────────────────────────────────────────────────┐
│ research_toolkit/ — deterministic engine (Python 3.11+, pydantic v2)                               │
│   schemas · paths · project_manager · source_registry · evidence_store · documents · validation    │
│   providers/{openalex,crossref,semantic_scholar} · pipelines · workflow_state · orchestrator       │
│   progress · exporters · skill_contracts · cli                                                     │
└────────────────────────────────────────────┬───────────────────────────────────────────────────────┘
                                             │ reads/writes
                         workspace/<slug>/ (project.yaml, sources/, evidence/, literature/, analysis/,
                                             manuscript/, reviews/, progress/, workflow/, exports/)
```

Rule of thumb from the TZ: LLMs interpret, draft and decide; code transforms, checks and records.
Every skill has an `executor`:

| executor | skills | meaning |
|---|---|---|
| `engine` | literature-search, citation-verifier, research-progress | `rtk run` executes the whole step with checkpoints |
| `host-skill` | paper-analyzer, literature-review, research-gap-finder, manuscript-builder, academic-integrity, peer-reviewer | the agent does the reading/writing; engine prepares inputs, validates outputs, checkpoints via `rtk step` |

## Modules

| Module | Responsibility |
|---|---|
| `schemas.py` | Pydantic contracts (`SourceRecord`, `EvidenceRecord`, `ArtifactRecord`, `ProjectConfig`, `WorkflowPlan/Step`, `RunEvent`, `ProjectStatus`), DOI/title normalisation, deterministic ids (`src-<sha1[:12]>`, `ev-<sha1[:10]>`) |
| `paths.py` | workspace layout, `safe_join` (rejects absolute paths, drive letters, `..`) |
| `project_manager.py` | `project.yaml`, artifact registry with sha256 (detects user edits → overwrite guard), restricted-path and sensitive-marker scan → `ApprovalRequired` |
| `source_registry.py` | `sources.json` + `references.bib`; dedup: DOI exact → (different DOIs never merge) → normalised-title similarity ≥ 0.92 with year ±1; merges never downgrade access/verification; minimal BibTeX parser |
| `evidence_store.py` | append-only JSONL; refuses unknown sources; LLM-only readings can never be `verified` |
| `documents.py` | PyMuPDF text per page, IMRaD heuristic split, verbatim excerpt locator, injection scan, untrusted-data wrapper |
| `validation.py` | DOI format, injection patterns, artifact presence/non-empty check, Agent-Skills frontmatter validation |
| `providers/` | httpx clients with throttling, polite headers, honest error classes (`ProviderUnavailable`, `ExternalAccessDisabled`); mock transport injectable for tests |
| `pipelines.py` | deterministic halves of the nine skills + validators for LLM text (`validate_evidence_links`, `validate_gap_report`, `check_manuscript_inputs`) |
| `workflow_state.py` | plan persistence, DAG validation (cycles, unknown deps, self-scheduling, `max_stages`), `ready_steps`, start/finish with retry limit and output re-check, resume |
| `orchestrator.py` | multilingual intent routing, constraint extraction, reuse/skip logic, approval flags, engine handlers, `final_report` that lists only files on disk |
| `progress.py` | stage status from artifacts + registry + events; counts, never estimates |
| `exporters.py` | CSV/XLSX/DOCX/MD/JSON writers and readers |
| `cli.py` | `rtk` (also `python -m research_toolkit`); UTF-8 forced on Windows consoles |

## Data contract (schema 1.1)

See TZ section 5. All JSON/YAML files carry `schema_version`. Changing a schema: bump `SCHEMA_VERSION`, keep readers
tolerant of older files, document the migration here.

- `sources/sources.json` → `{schema_version, sources:[SourceRecord], queries:[…]}`
- `evidence/evidence.jsonl` → one `EvidenceRecord` per line
- `progress/artifacts.json` → `{schema_version, artifacts:[ArtifactRecord]}`
- `workflow/plan.yaml` → `WorkflowPlan`; `workflow/runs.jsonl` → `RunEvent` per line
- `progress/project-status.json` → `ProjectStatus`

## Step life cycle

```
planned ──start──▶ running ──finish──▶ completed | blocked | failed | skipped | awaiting_user_review ──approve-review──▶ completed
   ▲                  │ (interrupted)
   └──── resume ◀─────┘
```

`finish_step(COMPLETED)` re-checks every declared output; missing/empty → `BLOCKED`. `resume()` re-validates completed
steps against disk and re-queues `running` ones. Retries are capped by `limits.max_retries_per_step`; plans by
`limits.max_stages`; the orchestrator may never schedule itself.

## Cross-agent strategy

One canonical `skills/` tree. `scripts/install.py` links/copies it into `.claude/skills` and `.agents/skills`
(or user-level). SKILL.md bodies contain no vendor slash syntax (tested) and call only `rtk`. The `skills` CLI route
(`npx skills add …`) targets the same tree. Acceptance test 9 verifies identical trees and manifests for both agents;
the conversational half (both agents follow the same plan in natural language) is a release checklist item, not CI.

## Testing

- unit: schemas, DOI, dedup, BibTeX, exporters, path traversal, injection scan, DAG rules, checkpoints/resume, guards
- integration: search→registry (mock transports), PDF→evidence, analysis→matrix→gaps, draft→citation/integrity/review
- acceptance: TZ 7.7 items 1–8 and 10, cross-agent installer (9), CLI offline end-to-end
- adversarial fixtures: nonexistent DOI, mismatched title/DOI, malformed DOI, abstract-only record, hostile PDF text,
  provider 503 and 402, duplicate articles (title and DOI), sensitive file in workspace, no author results (placeholders)
- live API tests are opt-in (`RTK_LIVE_API=1`); CI runs with `RTK_ALLOW_EXTERNAL_APIS=0`
