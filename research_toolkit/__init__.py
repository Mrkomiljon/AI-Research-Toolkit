"""AI Research Toolkit - deterministic engine shared by the fifteen Agent Skills.

LLM agents (Claude Code, Codex) do interpretation and drafting; this package does
the verifiable parts: schemas, registries, DOI checks, deduplication, document
parsing, exports, workflow checkpoints and progress computation.
"""

__version__ = "1.4.2"
SCHEMA_VERSION = "1.1"
SKILL_NAMES = (
    "research-orchestrator",
    "literature-search",
    "paper-analyzer",
    "literature-review",
    "research-gap-finder",
    "manuscript-builder",
    "citation-verifier",
    "academic-integrity",
    "peer-reviewer",
    "research-progress",
    "academic-writing",
    "journal-standards",
    "claim-verifier",
    "gap-validator",
    "research-concept-builder",
)
SPECIALIST_SKILLS = SKILL_NAMES[1:]
