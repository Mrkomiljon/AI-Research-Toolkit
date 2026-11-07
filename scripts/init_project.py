#!/usr/bin/env python3
"""Interactive workspace setup (the "setup interview" of TZ section 2). Non-interactive flags are passed through to `rtk init`.

  python scripts/init_project.py                      # interactive questions
  python scripts/init_project.py --slug x --topic "y" # non-interactive (same flags as `rtk init`)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_toolkit.cli import main as rtk_main  # noqa: E402

QUESTIONS = [
    ("slug", "Project slug (lowercase-with-hyphens) / Loyiha nomi (kichik harf, defis)", True),
    ("topic", "Research topic / Tadqiqot mavzusi", True),
    ("title", "Title (optional) / Sarlavha", False),
    ("field", "Field (e.g. agronomy) / Soha", False),
    ("language", "Output language uz|en|ru [uz]", False),
    ("year_from", "Year from (e.g. 2019) / Boshlang'ich yil", False),
    ("year_to", "Year to / Oxirgi yil", False),
    ("journal", "Target journal (optional) / Maqsadli jurnal", False),
    ("pdfs_note", "Available PDFs? (where) / Mavjud PDF fayllar", False),
    ("privacy_note", "Data/privacy constraints / Maxfiylik cheklovlari", False),
]


def main() -> None:
    argv = sys.argv[1:]
    if argv:
        rtk_main(["init", *argv])
        return
    print("AI Research Toolkit — workspace setup / ish maydonini sozlash\n")
    args: list[str] = ["init"]
    for key, prompt, required in QUESTIONS:
        while True:
            val = input(f"{prompt}: ").strip()
            if val or not required:
                break
            print("  required / majburiy")
        if val:
            args += [f"--{key.replace('_', '-')}", val]
    goals = input("Goals, separated by ';' / Maqsadlar (';' bilan): ").strip()
    for g in filter(None, (x.strip() for x in goals.split(";"))):
        args += ["--goal", g]
    ext = input("Allow outbound metadata API calls (OpenAlex/Crossref)? [Y/n]: ").strip().lower()
    if ext == "n":
        args.append("--no-external-apis")
    print("\nNote: Claude Code / Codex send your prompts and the text they read to their provider's cloud. "
          "Local-first means your files stay on disk; it does not mean offline inference.")
    ack = input("Acknowledged? [y/N]: ").strip().lower()
    if ack == "y":
        args.append("--ack-cloud")
    rtk_main(args)


if __name__ == "__main__":
    main()
