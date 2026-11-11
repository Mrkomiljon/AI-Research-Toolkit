# Installation

(Toolkit v1.4: 15 skills. Commands below are unchanged from 1.1.)

Optional OCR for scanned PDFs: `python -m pip install "ai-research-toolkit[ocr]"` installs Docling (PyTorch and OCR
models, several GB on first use). Alternatively install Tesseract and put it on PATH. Check with `rtk ocr status`.
Without either, scanned pages are reported as unread and the paper stays abstract-only.

Two parts are always needed: (1) the **skills** in your agent's skills directory and (2) the **Python engine**
(`rtk`) that the skills call. Copying `SKILL.md` files alone is not enough.

## Requirements

- Python 3.11 or 3.12 (tested 3.11.9 on Windows 11, Ubuntu in CI)
- pip; optionally Node.js 18+ for the `skills` CLI route
- Claude Code **or** OpenAI Codex, authenticated with its provider (independent of this toolkit)
- Internet access for OpenAlex/Crossref (free, no key); optional Semantic Scholar key

## Costs and subscriptions

The toolkit itself is free (MIT) and OpenAlex/Crossref need no key or payment. What you pay for is the **agent**:

| Agent | What you need | Notes |
|---|---|---|
| Claude Code | Claude Pro or Max subscription, **or** an Anthropic API key (pay per token) | Pro has tighter hourly limits; long research sessions fit Max better |
| Codex | ChatGPT Plus / Pro / Business / Edu / Enterprise, **or** an OpenAI API key | sign in with `codex login` |

One agent is enough; the skills behave the same in both. Semantic Scholar is optional (free public tier, rate
limited; a free API key raises limits). Prices and limits change often: check claude.com/pricing and
openai.com/chatgpt/pricing before advising users.

## Route 0 — Fastest (no clone)

```bash
python -m pip install ai-research-toolkit
cd /path/to/your/research-folder
npx skills add Mrkomiljon/AI-Research-Toolkit -a claude-code   # and/or -a codex
rtk --help
```

## Route A — Skills CLI

```bash
# interactive: pick skills and agents
npx skills add Mrkomiljon/AI-Research-Toolkit
# one agent explicitly
npx skills add Mrkomiljon/AI-Research-Toolkit -a claude-code
npx skills add Mrkomiljon/AI-Research-Toolkit -a codex
# everything, non-interactive, user-level
npx skills add Mrkomiljon/AI-Research-Toolkit --all -g
# list what the repo offers without installing
npx skills add Mrkomiljon/AI-Research-Toolkit --list
```

Flags verified against `skills` CLI 1.7.6 on 2026-11-07 (`-a/--agent`, `-s/--skill`, `-g/--global`, `--all`, `--list`,
`--copy`, `-y`). Agent identifiers (`claude-code`, `codex`) come from the CLI's agent list; if a name is rejected run
the interactive form and choose from the menu. Then install the engine:

```bash
git clone https://github.com/Mrkomiljon/AI-Research-Toolkit.git
cd AI-Research-Toolkit
python -m pip install -e .
rtk --help
```

## Route B — Manual (works today, no Node.js)

```bash
git clone https://github.com/Mrkomiljon/AI-Research-Toolkit.git
cd AI-Research-Toolkit
python -m pip install -e .
# project scope: run inside the folder you open with Claude Code / Codex
python scripts/install.py --agent claude --scope project --project-dir /path/to/your/project
python scripts/install.py --agent codex  --scope project --project-dir /path/to/your/project
# user scope (all projects): ~/.claude/skills and ~/.codex/skills
python scripts/install.py --agent all --scope user
python scripts/doctor.py
```

`install.py` symlinks the canonical `skills/` directories; on Windows without symlink permission it copies them
(re-run after `git pull`). It never overwrites directories it did not create (`--force` to replace), and
`--uninstall` removes only its own entries.

### Windows PowerShell

```powershell
git clone https://github.com/Mrkomiljon/AI-Research-Toolkit.git
Set-Location AI-Research-Toolkit
py -3.11 -m pip install -e .
py -3.11 scripts\install.py --agent all --scope project --project-dir C:\Users\you\my-research
py -3.11 scripts\doctor.py
rtk init --workspace C:\Users\you\my-research\workspace --slug my-phd --topic "..." --ack-cloud
```

If `rtk` is not found, the Scripts folder of your Python is not on PATH; use `py -3.11 -m research_toolkit …` instead.

## Where skills must be for each agent

| Agent | Project scope | User scope |
|---|---|---|
| Claude Code | `<project>/.claude/skills/<skill>/SKILL.md` | `~/.claude/skills/<skill>/SKILL.md` |
| Codex | `<project>/.agents/skills/<skill>/SKILL.md` | `~/.codex/skills/<skill>/SKILL.md` |

Open the agent **in the project directory** that contains `.claude/` or `.agents/`. Invocation is natural language in
both agents: `Use research-orchestrator. Initialize my PhD research on …`.

## Update

```bash
cd AI-Research-Toolkit && git pull && python -m pip install -e .
python scripts/install.py --agent all --scope project --project-dir /path/to/your/project   # re-copy if not symlinked
# or, Skills CLI route:
npx skills update
```

## Uninstall

```bash
python scripts/install.py --agent all --scope project --project-dir /path/to/your/project --uninstall
python scripts/install.py --agent all --scope user --uninstall
python -m pip uninstall ai-research-toolkit
# Skills CLI route: npx skills remove
```

## Optional configuration

Copy `.env.example` to `.env` (never commit it): `RTK_CONTACT_EMAIL` (polite pools), `SEMANTIC_SCHOLAR_API_KEY`,
`RTK_ALLOW_EXTERNAL_APIS=0` to forbid all outbound calls, `RTK_WORKSPACE_ROOT`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `rtk: command not found` | `python -m pip install -e .` in the repo; or call `python -m research_toolkit` |
| Agent does not see the skills | wrong directory: check `.claude/skills` / `.agents/skills` in the folder you opened; run `python scripts/doctor.py` there |
| `UnicodeEncodeError` on Windows | fixed in 1.1 (UTF-8 forced); update the package |
| HTTP 429 from a provider | wait, or set `RTK_CONTACT_EMAIL`; the step is `blocked`, not failed silently |
| `privacy.allow_external_apis is false` | intended: approve explicitly (`rtk search --authorized`) or change `project.yaml` |
| pymupdf import error | `python -m pip install pymupdf` (1.24+ or 2.x) |
