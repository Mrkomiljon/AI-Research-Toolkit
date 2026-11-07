# AI Research Toolkit (v1.2)

Local-first, skill-based research workflow toolkit for **Claude Code** and **OpenAI Codex**: eleven specialist Agent
Skills plus a mandatory `research-orchestrator`, backed by a deterministic Python engine (`rtk`). It helps a researcher
find papers, analyze them with locators, build evidence-linked reviews, shortlist candidate gaps, structure manuscripts,
audit citations, check integrity, simulate peer review and track progress — **without inventing papers, results or
completion marks**. It is an assistant, not an autonomous researcher and not a publication guarantee.

UI languages: Uzbek, English, Russian (skills are written in English; the agent answers in your language).

## Skills

| Skill | Does | Key gate |
|---|---|---|
| `research-orchestrator` | plans a dependency-aware workflow, previews it, gets approvals, runs/delegates, checkpoints, reports what is on disk | never fabricates outputs, never bypasses human review |
| `literature-search` | OpenAlex/Crossref/(Semantic Scholar) search, query log, dedup, ranking, access levels | never invents articles; reports coverage |
| `paper-analyzer` | objective/methods/sample/outcomes/limitations with page locators and verbatim excerpts | explicit `ABSTRACT_ONLY` if no full text |
| `literature-review` | comparison matrix + evidence-linked synthesis | every claim linked to `ev-`/`src-` ids |
| `research-gap-finder` | candidate gaps, hypotheses, feasibility | candidate gap ≠ proven novelty |
| `manuscript-builder` | IMRaD outline, author-reviewed draft, missing-info list | no fictitious methods/results |
| `citation-verifier` | DOI format + resolution, mismatches, missing/unused references | metadata check ≠ claim support |
| `academic-integrity` | attribution/provenance audit, AI-use disclosure draft, submission checklist | no plagiarism-free certificates, no detector evasion |
| `peer-reviewer` | section-wise major/minor comments, revision plan, response draft | simulated; no acceptance guarantee |
| `research-progress` | status from artifacts on disk, blockers, next actions | no evidence-free completion marks |
| `academic-writing` *(new in 1.2)* | scientific copy-editing: clarity, concision, tense/voice, acronyms, hedging; tracked edit report; before/after metrics | facts, numbers, citations and claims never change |
| `journal-standards` *(new in 1.2)* | reporting-guideline checklist (CONSORT, STROBE, STARD, TRIPOD+AI, PRISMA, ARRIVE, CARE, generic), ICMJE declarations, journal limits, cover-letter draft | readiness check, not a guarantee of acceptance |

## Requirements

Python 3.11+, pip, Claude Code or Codex (authenticated), internet for the free metadata APIs. Node.js only for the
`npx skills` route. Windows 11 / Linux tested.

## Costs and subscriptions

The toolkit itself is free (MIT) and OpenAlex/Crossref need no key or payment. What you pay for is the **agent**:

| Agent | What you need | Notes |
|---|---|---|
| Claude Code | Claude Pro or Max subscription, **or** an Anthropic API key (pay per token) | Pro has tighter hourly limits; long research sessions fit Max better |
| Codex | ChatGPT Plus / Pro / Business / Edu / Enterprise, **or** an OpenAI API key | sign in with `codex login` |

One agent is enough; the skills behave the same in both. Semantic Scholar is optional (free public tier, rate
limited; a free API key raises limits). Prices and limits change often: check claude.com/pricing and
openai.com/chatgpt/pricing before advising users.

## 1-minute quickstart

```bash
# engine from PyPI (no clone needed)
python -m pip install ai-research-toolkit
# skills into your research folder (pick the agent you use; both is fine)
cd /path/to/your/research-folder
npx skills add Mrkomiljon/AI-Research-Toolkit -a claude-code
npx skills add Mrkomiljon/AI-Research-Toolkit -a codex
rtk --help
```

Without Node.js, clone and use the Python installer instead:

```bash
git clone https://github.com/Mrkomiljon/AI-Research-Toolkit.git
cd AI-Research-Toolkit
python -m pip install -e .
python scripts/install.py --agent all --scope project --project-dir /path/to/your/research-folder
python scripts/doctor.py
```

Open Claude Code or Codex **in `/path/to/your/research-folder`** and type:

> Use research-orchestrator. Initialize my PhD research on machine learning for cotton yield prediction.

Then ask for deliverables in plain language: "Find 20 papers since 2021", "Compare these papers", "Find research gaps",
"Prepare my article", "Audit this manuscript", "Where am I?".

## Install with the Skills CLI (after publishing on GitHub)

```bash
npx skills add Mrkomiljon/AI-Research-Toolkit                 # interactive: choose skills and agent(s)
npx skills add Mrkomiljon/AI-Research-Toolkit -a claude-code  # Claude Code only
npx skills add Mrkomiljon/AI-Research-Toolkit -a codex        # Codex only
npx skills add Mrkomiljon/AI-Research-Toolkit --all -g        # all skills, all agents, user-level
```

Flags checked against `skills` 1.7.6 (`npx skills add --help`, 2026-11-07). The Python engine must still be installed
(`python -m pip install -e .` from a clone, or the package once published) because every skill calls `rtk`.
Full details, Windows PowerShell steps, update and uninstall: [docs/installation.md](docs/installation.md).

### Claude Code

Skills are read from `<project>/.claude/skills/<skill>/SKILL.md` (or `~/.claude/skills`). `python scripts/install.py
--agent claude --scope project --project-dir <project>` creates them. Invoke by natural language; `CLAUDE.md` in this
repo carries the reliability rules.

### Codex

Skills are read from `<project>/.agents/skills/<skill>/SKILL.md` (or `~/.codex/skills`). `python scripts/install.py
--agent codex --scope project --project-dir <project>`. `AGENTS.md` carries the same rules. No vendor-specific slash
syntax is required by any skill (tested).

## Watching what happens

In an interactive session (`claude` or `codex` in a terminal or the VS Code extension) you see every step live: the
plan preview, approval questions, each `rtk` call and the files it writes. The non-interactive forms (`claude -p`,
`codex exec`) print only the final answer. Either way everything is written to disk, so a second terminal can follow
the run:

```bash
rtk log -p workspace/<slug> --follow     # tails workflow/runs.jsonl: step_started, step_completed, blocked, ...
rtk status -p workspace/<slug>           # stage table derived from artifacts
```

Outputs are ordinary files (`.md`, `.xlsx`, `.docx`, `.json`) under the workspace; open them in VS Code or Excel/Word.

## Sample prompts

- `Use research-orchestrator. Find 15 papers on Sentinel-2 wheat yield prediction 2020-2025, then find research gaps.`
- `Use paper-analyzer. Analyze papers/PDFs/smith2023.pdf for the question "which features drive accuracy?"`
- `Use citation-verifier. Check manuscript/draft.docx against sources/references.bib.`
- `Use research-progress. What is done, what is blocked, what next?`
- `Use academic-writing. Polish the English of manuscript/manuscript-outline.md without changing any numbers or citations.`
- `Use journal-standards. Check manuscript/manuscript-draft.docx against TRIPOD+AI and the author guidelines in reviews/journal-guidelines.txt.`
- Uzbek: `Use journal-standards. Maqolani xalqaro nashr standartlariga moslashtir.`
- Uzbek: `Use research-orchestrator. Paxta hosildorligi va ML bo'yicha 20 ta maqola top va bo'shliqlarni aniqla.`
- Russian: `Use research-orchestrator. Найди 20 статей о прогнозировании урожайности хлопка и пробелы в исследованиях.`

## What a run looks like (engine only, no LLM needed)

```bash
rtk init --workspace ./workspace --slug crop-yield --topic "machine learning crop yield prediction" --year-from 2021 --ack-cloud
rtk plan -p workspace/crop-yield "Find 5 papers about ML crop yield prediction since 2021 and find research gaps"
rtk --json run -p workspace/crop-yield        # runs literature-search; next steps are host-skill steps
rtk status -p workspace/crop-yield
rtk report -p workspace/crop-yield            # lists only files that exist on disk
```

`examples/agriculture-research/` contains a real run (live OpenAlex + Crossref, 2026-11-07) with 16 deduplicated,
DOI-bearing sources, an abstract-only example analysis with tool-verified excerpts, a matrix, status files and the
workflow log. See its README for what is and is not demonstrated.

## Workspace layout

```
workspace/<slug>/
├── project.yaml                 # topic, goals, years, journal, privacy, budget, limits
├── sources/sources.json|references.bib
├── papers/PDFs/                 # your PDFs (git-ignored)
├── evidence/evidence.jsonl
├── literature/ analysis/ manuscript/ reviews/
├── progress/project-status.json|artifacts.json|research-progress.xlsx|next-actions.md
├── workflow/plan.yaml|runs.jsonl|history/
└── exports/
```

## About the security scan shown by `npx skills add`

The Skills CLI runs three automated scanners (Gen Agent Trust Hub, Socket, Snyk) over every SKILL.md before
installation. For this toolkit they report "Safe"/"Pass" with a few Socket alerts and Snyk "Medium" on
`literature-search` and `research-orchestrator`. The skills instruct the agent to run a local command (`rtk`), call
public scholarly APIs (OpenAlex, Crossref) and write files in your workspace; scanners flag exactly those behaviours.
Nothing is downloaded or executed from the skill text itself, no credentials are read, and the full source is in this
repository. Review `skills/` yourself if in doubt, then answer "Yes".

## Data privacy

- Artifacts, registries and PDFs stay on your disk. Metadata APIs receive only query strings and DOIs.
- Claude Code / Codex send prompts and the text they read to their providers; **local-first is not offline inference**.
- `privacy.allow_external_apis: false` in `project.yaml` (or `RTK_ALLOW_EXTERNAL_APIS=0`) forbids all outbound calls.
- `rtk privacy-check <files>` blocks external transmission of restricted or sensitive files until you authorize it.
- Never commit `workspace/`, PDFs, `.env`. See [docs/security.md](docs/security.md).

## Testing and status

```bash
python -m pip install -e ".[dev]"
ruff check .
rtk validate-skills --skills-dir skills
pytest -q
```

 tests (unit, integration, acceptance) pass offline on Windows 11 / Python 3.11.9 (2026-11-07); CI runs them on
Ubuntu and Windows with Python 3.11 and 3.12. Acceptance criteria from the specification:

| # | Criterion | Status |
|---|---|---|
| 1 | multi-step request → validated plan and sequential artifacts | pass (`test_1_…`) |
| 2 | verified paper not re-analyzed without reason | pass |
| 3 | missing PDF → abstract-only / full-text claims blocked | pass |
| 4 | invalid DOI does not pass citation verification | pass |
| 5 | stops before external transmission of confidential files | pass |
| 6 | failed API step → partial artifacts + truthful `blocked` | pass |
| 7 | interruption persists state; resume skips valid steps | pass |
| 8 | injected instruction in a PDF does not change orchestration | pass |
| 9 | Claude Code and Codex run the same skill workflow | installer/manifest part passes (`test_cross_agent.py`). Conversational run verified in **Claude Code** (2026-11-07: `claude -p` with `Use research-orchestrator. Initialize … then find 3 papers` created the workspace, ran the plan and reported only on-disk files; a second run `… 10 ta maqola top va bo'shliqlarni aniqla` completed the full search → analyzer → review → gap-finder chain with 26 artifacts, all labelled ABSTRACT_ONLY/METADATA_ONLY because no PDFs were supplied). **Codex** conversational run still pending (account/model login issue on the test machine) |
| 10 | workflow summary matches artifacts on disk | pass |

## Known limitations

- Full texts are never downloaded; you supply PDFs. Scanned PDFs without a text layer are not OCR'd.
- Author-year citation matching is heuristic; use `\cite{}`, `[@key]` or `[src-…]` for reliable audits.
- Intent routing is keyword-based; ambiguous requests produce an empty plan and a question, by design.
- Semantic Scholar public tier is rate-limited; it is optional.
- Templates in `templates/` are starting points, not journal-specific formats. No LaTeX/pandoc pipeline yet.
- PyMuPDF is AGPL-licensed (see `LICENSE` note).

## Repository map

`skills/` canonical skills (12) · `research_toolkit/` engine · `scripts/` install, doctor, init_project, validate_sources,
export_report, build_templates · `templates/` · `examples/agriculture-research/` · `tests/` · `docs/` (installation,
user-guide-uz, architecture, security) · `.github/workflows/ci.yml`.

Published on PyPI: https://pypi.org/project/ai-research-toolkit/ (v1.2.0, 2026-11-07).

## Releasing to PyPI (maintainers)

1. Create a PyPI API token (pypi.org → Account settings → API tokens) and store it as the GitHub secret `PYPI_API_TOKEN`.
2. Bump `version` in `pyproject.toml`, commit, then tag and push: `git tag v1.1.0 && git push origin v1.1.0`.
3. `.github/workflows/release.yml` runs lint + tests, checks the tag matches the version, builds, uploads to PyPI and
   creates a GitHub release. Users can then `python -m pip install ai-research-toolkit`.

## License

MIT (see `LICENSE`, including the dependency licence audit note).
