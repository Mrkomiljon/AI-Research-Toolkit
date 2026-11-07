# Security, scientific integrity and governance

## Threat model

| Threat | Mitigation in the toolkit |
|---|---|
| Fabricated papers/DOIs/results by the LLM | sources only enter the registry from provider responses or explicit user `rtk sources add`; DOIs are format-checked and resolved; `citation-verifier` fails non-resolving or mismatched DOIs; manuscript placeholders `[MISSING: …]` are listed, never filled |
| Unsupported claims | every synthesis/gap paragraph must cite existing `ev-`/`src-` ids (`rtk review validate-links`); `ABSTRACT_ONLY` sources cannot carry page locators; LLM-only evidence stays `unverified` |
| Prompt injection via PDFs/web/API text | document text is treated as data, wrapped in explicit boundaries, scanned by `scan_for_injection`; findings are reported with page locators; orchestration rules live in code/skills, not in documents (acceptance test 8) |
| Path traversal / writing outside the workspace | `safe_join` rejects absolute paths, drive letters and `..`; `pdf_path` validated in the schema |
| Leaking confidential files | `privacy.restricted_globs` (default `papers/PDFs/**`, `data/private/**`) + sensitive-marker scan; `rtk privacy-check` exits 3 until `--authorized`; `privacy.allow_external_apis=false` blocks all providers (`ExternalAccessDisabled`) |
| Overwriting the author's work | artifact registry stores sha256; a changed file triggers `ApprovalRequired` on overwrite unless `--force` |
| Unbounded automation | `limits.max_stages`, `limits.max_retries_per_step`, no self-scheduling, no background workers; every step is logged |
| Budget/paid APIs | `budget.max_papers_per_search`, `budget.allow_paid_apis=false`; HTTP 402/403 → `ProviderUnavailable` (reported, not retried blindly); cost categories only (`none/low/potentially_paid`), never invented money amounts |
| Fake assurances | no plagiarism-free certificates, no AI-detector evasion, no acceptance or policy-compliance guarantees (stated in generated reports) |

## Cloud transmission caveat

Claude Code and Codex send the conversation, including file contents the agent reads, to Anthropic/OpenAI. The toolkit
is **local-first** (all artifacts and registries stay on disk; metadata APIs are called directly from your machine), but
it is not offline inference. `rtk init --ack-cloud` records that the user was informed; the orchestrator states it once
per project. Keep unpublished manuscripts, patient data and restricted datasets out of the agent context unless the
author accepts that.

## What is sent where

| Destination | Data | When |
|---|---|---|
| OpenAlex / Crossref / Semantic Scholar | search query string, year filters, DOIs, optional contact e-mail/API key | `rtk search`, `rtk verify-citations`, `rtk sources verify`; never PDFs or manuscripts |
| Model provider (via the agent) | whatever the agent reads or you paste | any host-skill step |
| Nowhere else | no telemetry, no uploads, no e-mail, no submissions | — |

## Git hygiene

`.gitignore` excludes `.env`, workspaces, PDFs, exports and the installer-generated `.claude/skills` / `.agents/skills`.
Never commit `papers/PDFs`, `data/private` or `exports/`.

## Dependencies and licences

Runtime: pydantic (MIT), PyYAML (MIT), httpx (BSD-3), pandas (BSD-3), openpyxl (MIT), python-docx (MIT), jinja2 (BSD-3),
PyMuPDF (**AGPL-3.0** or commercial — relevant if you redistribute a closed product), pytest (MIT). No third-party code
is vendored. External skill instructions are not imported. Review `pip audit` output before releases.

## AI-use disclosure

`academic-integrity` drafts a disclosure from the author's own statement of tools, stages, human review and data
shared. It must be edited to the journal's required wording; the toolkit does not guarantee compliance.
