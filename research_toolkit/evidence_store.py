"""evidence/evidence.jsonl append-only store. Every record must point to a registered source."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .schemas import EvidenceRecord, VerificationStatus, VerifiedBy


class EvidenceStore:
    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.path = self.workspace / "evidence" / "evidence.jsonl"

    def all(self) -> list[EvidenceRecord]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(EvidenceRecord.model_validate_json(line))
        return out

    def for_source(self, source_id: str) -> list[EvidenceRecord]:
        return [e for e in self.all() if e.source_id == source_id]

    def ids(self) -> set[str]:
        return {e.evidence_id for e in self.all()}

    def append(self, record: EvidenceRecord, known_source_ids: set[str] | None = None) -> EvidenceRecord:
        if known_source_ids is not None and record.source_id not in known_source_ids:
            raise ValueError(f"evidence refers to unknown source {record.source_id}")
        if record.verified_by == VerifiedBy.LLM and record.verification_status == VerificationStatus.VERIFIED:
            # An LLM reading alone cannot mark evidence verified (TZ section 8).
            record = record.model_copy(update={"verification_status": VerificationStatus.UNVERIFIED})
        if record.evidence_id in self.ids():
            return record  # idempotent append
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(record.model_dump_json() + "\n")
        return record

    @staticmethod
    def make_id(source_id: str, claim: str, locator: str) -> str:
        h = hashlib.sha1(f"{source_id}|{claim}|{locator}".encode()).hexdigest()[:10]
        return f"ev-{h}"
