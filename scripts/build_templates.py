#!/usr/bin/env python3
"""(Re)generate the binary templates in templates/ deterministically with openpyxl and python-docx.

  python scripts/build_templates.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_toolkit.exporters import write_docx, write_xlsx  # noqa: E402
from research_toolkit.pipelines import ANALYSIS_FIELDS  # noqa: E402
from research_toolkit.skill_contracts import PIPELINE_ORDER  # noqa: E402

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


def main() -> None:
    TEMPLATES.mkdir(exist_ok=True)
    matrix_cols = ["source_id", "title", "year", "doi", "access_level"] + [c for f in ANALYSIS_FIELDS for c in (f, f"{f}_locator")] + ["evidence_ids", "problems"]
    write_xlsx({"matrix": [], "legend": [{"column": c, "meaning": "filled by `rtk review matrix`"} for c in matrix_cols]},
               TEMPLATES / "literature-matrix.xlsx", {"matrix": matrix_cols, "legend": ["column", "meaning"]})
    write_xlsx({"stages": [{"stage": s, "status": "not_started", "artifacts": "", "missing_required": "", "blockers": "", "last_run_id": "", "last_updated": ""} for s in PIPELINE_ORDER if s != "research-progress"],
                "milestones": [{"milestone": "", "reached": False, "evidence": ""}]},
               TEMPLATES / "progress-tracker.xlsx")
    write_docx(TEMPLATES / "manuscript.docx", "[Title]", [
        ("Abstract", "[AUTHOR INPUT NEEDED: 150–250 words]"),
        ("Introduction", "[Background and research question. Cite registered sources as [src-…].]"),
        ("Methods", "[MISSING: author's actual methods, data, participants, analysis]"),
        ("Results", "[MISSING: author's actual results; no generated numbers]"),
        ("Discussion", "[Interpretation linked to evidence ids; limitations]"),
        ("Conclusion", "[Short, no overclaiming]"),
        ("References", "[Generated from reviews/verified-references.bib after citation-verifier passes]"),
    ], metadata_note="IMRaD template of the AI Research Toolkit. Every bracketed item must be replaced by the author.")
    for p in sorted(TEMPLATES.iterdir()):
        print(p)


if __name__ == "__main__":
    main()
