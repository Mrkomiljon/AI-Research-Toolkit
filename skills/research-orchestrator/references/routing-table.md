# Routing table (TZ 7.3)

Match the user's intent (any language) to a default chain. The engine (`rtk plan`) applies the same table and then
**removes stages whose verified outputs already exist**. Routing is not a license to run every stage: reuse verified
outputs, skip unneeded tasks, never fetch or analyze more papers than the user authorized.

| Intent (examples: en / uz / ru) | Default chain | Engine / host |
|---|---|---|
| "Find papers about…" / "… haqida maqolalar top" / "Найди статьи о…" | `literature-search` | engine |
| "Analyze this PDF…" / "Bu PDF ni tahlil qil" / "Проанализируй этот PDF" | `paper-analyzer` | host |
| "Compare these papers…" / "Bu maqolalarni taqqosla" / "Сравни эти статьи" | `paper-analyzer` (missing only) → `literature-review` | host |
| "Find research gaps…" / "Tadqiqot bo'shliqlarini top" / "Найди пробелы" | `literature-search` (if none) → `paper-analyzer` → `literature-review` → `research-gap-finder` | engine → host |
| "Prepare my article…" / "Maqolamni tayyorla" / "Подготовь мою статью" | `manuscript-builder` → `citation-verifier` → `academic-integrity` → `peer-reviewer` | host → engine → host → host |
| "Audit this manuscript…" / "Qo'lyozmani tekshir" / "Проверь рукопись" | `citation-verifier` → `academic-integrity` → `peer-reviewer` | engine → host → host |
| "Where am I in my research?" / "Tadqiqotimda qayerdaman?" / "Где я в исследовании?" | `research-progress` | engine |
| Multi-stage or ambiguous goal | minimal dependency-aware plan; request only essential missing inputs | — |

Detection precedence in the engine: progress → audit → manuscript → gaps → compare → analyze → search.
When keywords collide (e.g. "find papers and gaps"), the longer chain wins because it contains the shorter one.

## Required inputs per stage

| Skill | Must have | Ask the user if missing |
|---|---|---|
| literature-search | topic, target_count (≤ budget), years | inclusion/exclusion criteria (optional) |
| paper-analyzer | registered source ids; PDF path for full-text claims | the research question driving the analysis |
| literature-review | ≥ 2 completed analyses | which sources to include |
| research-gap-finder | literature matrix + gap seed | scope constraints (methods, region, data) |
| manuscript-builder | author's real facts/results, verified sources | target journal rules, section word limits |
| citation-verifier | manuscript path (md/docx), bib path (optional) | — |
| academic-integrity | author-stated AI use (tools, stages, human review) | journal policy text |
| peer-reviewer | manuscript path, field | rubric / journal |
| research-progress | nothing | milestones the user wants tracked |
