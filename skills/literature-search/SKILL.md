---
name: literature-search
description: Search scholarly metadata APIs (OpenAlex, Crossref, optional Semantic Scholar) for papers on a topic with year range and target count, record the exact query, deduplicate, rank, register sources with honest access levels, and fetch open-access full texts (arXiv, Europe PMC, Unpaywall, OpenAlex OA) into papers/PDFs/. Use when the user asks to find papers, articles, studies or literature on a topic (uz "maqolalar top", ru "найди статьи"). Never invents articles.
---

# literature-search

Deterministic skill: the engine performs the search; you set the parameters, explain coverage and never add papers
that did not come from a provider response.

## Inputs

- `topic` (query string; refine it with the user: key terms, synonyms, English wording for APIs)
- `year_from`, `year_to` (optional; default from `project.yaml`)
- `target_count` (must be ≤ `budget.max_papers_per_search`; ask for approval otherwise)
- inclusion / exclusion criteria (free text, recorded in `search-strategy.md`)
- providers: default `openalex,crossref`; add `semantic_scholar` only if the user wants it (public rate limits apply)

## Engine

Before the first `rtk` command of a session run `rtk --version`. If the command is missing or fails, install the engine
yourself and tell the user in one line that you did: `python -m pip install -U ai-research-toolkit` (Python 3.11+; if
Python itself is missing, stop and say so). If `rtk` is still not found afterwards, use `python -m research_toolkit`
wherever this skill says `rtk`. Do not ask the user to run install commands by hand.

## Workflow

1. Confirm the workspace: `rtk sources stats -p <ws>`. If `privacy.allow_external_apis` is false, stop and ask; the
   engine refuses without `--authorized`.
2. Build the query string with the user when the topic is vague (two or three variants are fine: run them one at a time,
   each run is logged with its own `query_id`).
3. Run:
   ```bash
   rtk --json search -p <ws> --topic "<query>" --year-from 2021 --target-count 20 \
     --include "peer-reviewed" --exclude "non-English" [--providers openalex,crossref,semantic_scholar]
   ```
   Inside an orchestrated plan the same step is `rtk run -p <ws> --step s1`.
4. Read the result: `coverage` (requested vs delivered vs shortfall), `access_levels`, `errors`. If a provider was
   unavailable, say so; do not fill the gap by inventing records.
5. Fetch open-access full texts for the selected papers (or pass `--fetch` to `rtk search`):
   ```bash
   rtk fetch -p <ws> --source-ids <ids…> --prepare      # or --limit 20 for the whole registry
   ```
   Tries OpenAlex OA locations, arXiv (title/id match), Europe PMC (PMC open access) and Unpaywall (only when
   `RTK_CONTACT_EMAIL` is set). Downloaded PDFs land in `papers/PDFs/<source_id>.pdf`, the source becomes
   `FULL_TEXT`, and `literature/fulltext-log.json` records provider, URL and licence per paper. Paywalled papers stay
   `ABSTRACT_ONLY`; never try to bypass paywalls or institutional logins. The user can still add PDFs manually
   (`rtk sources attach-pdf --source-id <id> --pdf papers/PDFs/<file>.pdf`).
6. Present the top results from `literature/papers.csv` with title, year, venue, DOI, access level (after fetching)
   and citation count. Say how many full texts were obtained and which remain abstract-only.
7. Let the user remove off-topic hits before analysis; selection is theirs.

## Outputs (all written by the engine)

`literature/search-strategy.md`, `literature/papers.xlsx`, `literature/papers.csv`, `sources/references.bib`,
`literature/search-log.json`, `literature/fulltext-log.json` and fetched `papers/PDFs/<source_id>.pdf`; registry `sources/sources.json` updated with dedup (DOI exact, then title similarity ≥ 0.92 with year ±1).

## Validation / key gate

- Every record has `provider`, `retrieved_at`, `access_level`, `verification_status` (`verified` only when a DOI came from the provider).
- Coverage and shortfall are stated explicitly. "20 requested, 14 delivered" is a valid result; "20 delivered" with 6 invented is not.
- Only open-access full texts are downloaded, each with provider/licence logged; paywalled papers are reported as such.

## Failure behavior

All providers unavailable → step `blocked`, `search-log.json` still written with the errors, suggest retry later or
another provider. Rate limited (HTTP 429) → wait and retry at most `max_retries_per_step` times.
