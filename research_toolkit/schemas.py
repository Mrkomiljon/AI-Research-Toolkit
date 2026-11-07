"""Pydantic data contracts (section 5 of the TZ). All on-disk JSON/YAML carries schema_version."""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from . import SCHEMA_VERSION, SKILL_NAMES

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
SOURCE_ID_RE = re.compile(r"^src-[a-z0-9][a-z0-9-]{3,}$")


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_doi(value: str | None) -> str | None:
    """Strip resolver prefixes, lowercase, trim. Returns None for empty input; never guesses."""
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    v = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", v, flags=re.IGNORECASE)
    v = re.sub(r"^doi:\s*", "", v, flags=re.IGNORECASE)
    v = v.strip().rstrip(".,;")
    return v.lower()


def is_valid_doi_format(value: str | None) -> bool:
    d = normalize_doi(value)
    return bool(d and DOI_RE.match(d))


def normalize_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[^a-z0-9Ѐ-ӿÀ-ɏ ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def make_source_id(doi: str | None, title: str, year: int | None) -> str:
    key = normalize_doi(doi) or f"{normalize_title(title)}|{year or ''}"
    return "src-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


class AccessLevel(str, Enum):
    FULL_TEXT = "FULL_TEXT"
    ABSTRACT_ONLY = "ABSTRACT_ONLY"
    METADATA_ONLY = "METADATA_ONLY"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"  # metadata resolved against a provider / human confirmed
    MISMATCH = "mismatch"  # DOI resolves but metadata disagrees
    FAILED = "failed"  # DOI invalid or not found
    PARTIAL = "partial"


class EvidenceType(str, Enum):
    DIRECT_QUOTE = "direct_quote"
    PARAPHRASE = "paraphrase"
    TABLE = "table"
    FIGURE = "figure"
    ABSTRACT = "abstract"
    METADATA = "metadata"


class VerifiedBy(str, Enum):
    HUMAN = "human"
    TOOL = "tool"
    LLM = "llm"  # LLM-only readings never count as 'verified' until a human or tool confirms


class StepStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED = "skipped"
    AWAITING_USER_REVIEW = "awaiting_user_review"


class ApiCostCategory(str, Enum):
    NONE = "none"
    LOW = "low"
    POTENTIALLY_PAID = "potentially_paid"


class ValidationStatus(str, Enum):
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"


class AuthorReviewStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SourceRecord(BaseModel):
    schema_version: str = SCHEMA_VERSION
    source_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)
    provider: str = "manual"
    retrieved_at: datetime = Field(default_factory=utcnow)
    access_level: AccessLevel = AccessLevel.METADATA_ONLY
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    abstract: str | None = None
    venue: str | None = None
    url: str | None = None
    pdf_path: str | None = None  # relative to workspace, never absolute
    cited_by_count: int | None = None
    query_id: str | None = None
    notes: str | None = None

    @field_validator("doi", mode="before")
    @classmethod
    def _norm_doi(cls, v: Any) -> str | None:
        return normalize_doi(v) if isinstance(v, str) else v

    @field_validator("source_id")
    @classmethod
    def _check_id(cls, v: str) -> str:
        if not SOURCE_ID_RE.match(v):
            raise ValueError(f"invalid source_id {v!r}; expected src-<hex>")
        return v

    @field_validator("title")
    @classmethod
    def _check_title(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title must not be empty")
        return v.strip()

    @field_validator("pdf_path")
    @classmethod
    def _rel_pdf(cls, v: str | None) -> str | None:
        if v is None:
            return v
        norm = v.replace("\\", "/")
        if norm.startswith("/") or re.match(r"^[A-Za-z]:/", norm) or ".." in norm.split("/"):
            raise ValueError("pdf_path must be workspace-relative without '..'")
        return norm


class EvidenceRecord(BaseModel):
    schema_version: str = SCHEMA_VERSION
    evidence_id: str
    source_id: str
    claim: str
    excerpt: str | None = None
    locator: str  # e.g. "p.4 para 2", "abstract", "Table 3"
    evidence_type: EvidenceType = EvidenceType.PARAPHRASE
    verified_by: VerifiedBy = VerifiedBy.LLM
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    created_at: datetime = Field(default_factory=utcnow)
    skill: str | None = None

    @field_validator("claim", "locator")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class ArtifactRecord(BaseModel):
    schema_version: str = SCHEMA_VERSION
    artifact_id: str
    type: str  # canonical file name, e.g. "papers.csv", "literature-matrix.xlsx"
    path: str  # workspace-relative
    created_at: datetime = Field(default_factory=utcnow)
    source_ids: list[str] = Field(default_factory=list)
    workflow_run_id: str | None = None
    step_id: str | None = None
    skill: str | None = None
    validation_status: ValidationStatus = ValidationStatus.PENDING
    author_review_status: AuthorReviewStatus = AuthorReviewStatus.NOT_REQUIRED
    tentative: bool = False
    sha256: str | None = None
    notes: str | None = None


class PrivacyConfig(BaseModel):
    allow_external_apis: bool = True
    restricted_globs: list[str] = Field(default_factory=lambda: ["papers/PDFs/**", "data/private/**"])
    private_data_notes: str | None = None
    cloud_caveat_acknowledged: bool = False


class BudgetConfig(BaseModel):
    allow_paid_apis: bool = False
    max_papers_per_search: int = 50
    max_total_sources: int = 500


class OrchestratorLimits(BaseModel):
    max_stages: int = 12
    max_retries_per_step: int = 2


class ProjectConfig(BaseModel):
    schema_version: str = SCHEMA_VERSION
    slug: str
    title: str
    topic: str
    goals: list[str] = Field(default_factory=list)
    field: str | None = None
    output_language: str = "uz"
    year_from: int | None = None
    year_to: int | None = None
    target_journal: str | None = None
    available_pdfs_note: str | None = None
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    limits: OrchestratorLimits = Field(default_factory=OrchestratorLimits)
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9][a-z0-9-]{1,62}$", v):
            raise ValueError("slug must be lowercase letters, digits and hyphens")
        return v


class WorkflowStep(BaseModel):
    id: str
    skill: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)
    status: StepStatus = StepStatus.PLANNED
    api_cost: ApiCostCategory = ApiCostCategory.NONE
    approval_required: bool = False
    approval_reason: str | None = None
    approved: bool = False
    attempts: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    notes: str | None = None
    executor: str = "host-skill"  # "engine" = deterministic Python handler; "host-skill" = LLM via agent

    @field_validator("skill")
    @classmethod
    def _skill(cls, v: str) -> str:
        if v not in SKILL_NAMES:
            raise ValueError(f"unknown skill {v!r}")
        return v


class WorkflowPlan(BaseModel):
    workflow_version: int = 1
    schema_version: str = SCHEMA_VERSION
    run_id: str
    project: str
    goal: str
    request_text: str | None = None
    status: StepStatus = StepStatus.PLANNED
    steps: list[WorkflowStep] = Field(default_factory=list)
    approval_required: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    warnings: list[str] = Field(default_factory=list)

    def step(self, step_id: str) -> WorkflowStep:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(step_id)


class RunEvent(BaseModel):
    schema_version: str = SCHEMA_VERSION
    ts: datetime = Field(default_factory=utcnow)
    run_id: str
    step_id: str | None = None
    skill: str | None = None
    event: str  # plan_created|step_started|step_completed|step_failed|step_blocked|step_skipped|...
    status: str | None = None
    message: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    error: str | None = None


class StageStatus(BaseModel):
    skill: str
    status: str = "not_started"  # not_started|in_progress|completed|blocked|awaiting_user_review
    artifacts: list[str] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list)
    last_run_id: str | None = None
    last_updated: datetime | None = None
    blockers: list[str] = Field(default_factory=list)


class ProjectStatus(BaseModel):
    schema_version: str = SCHEMA_VERSION
    project: str
    updated_at: datetime = Field(default_factory=utcnow)
    derived_from: str = "artifacts on disk + workflow/runs.jsonl (no LLM-estimated percentages)"
    sources_total: int = 0
    sources_verified: int = 0
    sources_full_text: int = 0
    evidence_total: int = 0
    stages: dict[str, StageStatus] = Field(default_factory=dict)
    stages_completed: int = 0
    stages_total: int = 0
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    milestones: list[dict[str, Any]] = Field(default_factory=list)
