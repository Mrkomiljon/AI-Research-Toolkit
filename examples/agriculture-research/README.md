# Example workspace — ML crop yield prediction from remote sensing (agriculture)

A real, reproducible run of the toolkit engine, generated on 2026-11-07 with live OpenAlex + Crossref calls.
**Nothing in `sources/` or `literature/` was typed by hand**: every record came from a provider response logged in
`literature/search-log.json` (query id `q-…`, providers, counts, errors).

## What was run

```bash
rtk init --workspace examples --slug agriculture-research \
  --topic "machine learning crop yield prediction remote sensing" --field agronomy --year-from 2021 --year-to 2025 \
  --goal "Map ML methods used for crop yield prediction from satellite data" \
  --goal "Shortlist candidate research gaps for an Uzbek irrigated-cotton context" --ack-cloud
rtk plan -p examples/agriculture-research "Find 8 papers about machine learning crop yield prediction with remote sensing since 2021"
rtk --json run -p examples/agriculture-research          # literature-search (engine step)
rtk analyze prepare  -p examples/agriculture-research src-7adcd4c385fd
rtk analyze finalize -p examples/agriculture-research src-7adcd4c385fd --analysis-json analysis/example-analysis-input.json
rtk review matrix    -p examples/agriculture-research
rtk review gap-seed  -p examples/agriculture-research
rtk status           -p examples/agriculture-research
python scripts/export_report.py -p examples/agriculture-research --docx
```

## What the files show

| File | Meaning |
|---|---|
| `sources/sources.json`, `sources/references.bib` | 16 unique works after DOI/title deduplication of 20 provider hits; all have DOIs, all `ABSTRACT_ONLY` (no PDFs were downloaded) |
| `literature/papers.csv` / `.xlsx` | the 8 ranked papers delivered for the request; `search-strategy.md` records query, providers, coverage |
| `analysis/src-7adcd4c385fd/` | one **abstract-only** analysis written as a demonstration (`example-analysis-input.json` is the LLM-side input; `paper-analysis.json/md` the validated output). Two excerpts were found verbatim in the abstract and are `verified_by: tool`; paraphrased fields stay `unverified` |
| `evidence/evidence.jsonl` | 5 evidence records linked to that source |
| `literature/literature-matrix.xlsx`, `review-evidence.json` | matrix built from the single analysis (a real review needs ≥ 2 full-text papers) |
| `analysis/gap-seed.json` | deterministic input for `research-gap-finder`; no gaps were written because one abstract-only paper is not a basis for gap claims |
| `progress/project-status.json`, `research-progress.xlsx`, `next-actions.md` | status derived from artifacts: literature-search `completed`, paper-analyzer `awaiting_user_review`, literature-review `in_progress` (synthesis missing), everything else `not_started` |
| `workflow/plan.yaml`, `runs.jsonl` | the plan and the event log of the engine run |

## Limitations of this example

- Metadata is verified (DOIs resolved by the providers at retrieval time); the scientific content of the papers was **not** read beyond one abstract.
- No full texts, therefore no literature synthesis, no gap report, no manuscript. Continue by adding PDFs to
  `papers/PDFs/`, running `rtk sources attach-pdf`, and following `skills/paper-analyzer/SKILL.md`.
- Results of a re-run will differ as OpenAlex/Crossref indexes change; compare against `search-log.json`.
