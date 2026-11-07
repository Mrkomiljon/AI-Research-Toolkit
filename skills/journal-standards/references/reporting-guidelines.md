# Reporting guidelines — which one applies

| Study design | Guideline | Engine key | Where to read the full statement |
|---|---|---|---|
| Randomised controlled trial | CONSORT 2010 (2025 update exists) | `CONSORT` | consort-statement.org |
| Observational (cohort, case-control, cross-sectional) | STROBE | `STROBE` | strobe-statement.org |
| Diagnostic / prognostic accuracy study | STARD 2015 | `STARD` | equator-network.org |
| Prediction model, incl. machine-learning / AI models | TRIPOD 2015, TRIPOD+AI 2024 | `TRIPOD` | tripod-statement.org |
| Systematic review / meta-analysis | PRISMA 2020 | `PRISMA` | prisma-statement.org |
| Animal research | ARRIVE 2.0 | `ARRIVE` | arriveguidelines.org |
| Case report | CARE | `CARE` | care-statement.org |
| Anything else / engineering, computational | IMRaD + ICMJE recommendations | `generic` | icmje.org |

The engine ships a condensed item list for each key (`research_toolkit/journal.py`); it is a working checklist,
not the official statement. Always cite the official checklist in the submission and verify the current version on
the EQUATOR Network (equator-network.org), because items and numbering change between versions.

## ICMJE essentials (apply to every manuscript)

- Authorship: all four ICMJE criteria met by every author; contributions stated (CRediT taxonomy is widely accepted).
- Declarations: ethics approval / IRB number and consent; conflicts of interest; funding; data availability; code
  availability (for computational work); clinical trial registration where applicable.
- AI use: many journals now require a statement on generative-AI use in writing or analysis; AI tools cannot be
  authors. The toolkit's `academic-integrity` skill drafts this statement from the author's actual use.

## Typical journal formatting checks

- Abstract: structured vs unstructured, word limit (commonly 150–350).
- Main text word limit (commonly 3,000–5,000 for original research), number of figures/tables, references.
- Reference style (Vancouver numeric, APA, journal-specific); the `citation-verifier` skill checks resolution,
  not style.
- Title page items: full title, running title, authors and affiliations, corresponding author, keywords.
- Supplementary material limits and file formats.

Do not assume limits. If the author has not supplied the journal's instructions, report "not checked".
