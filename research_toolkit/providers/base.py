"""Common provider contract. Providers return SourceRecords and never fabricate; absence is reported."""
from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from ..schemas import SourceRecord


class ProviderError(RuntimeError):
    pass


class ProviderUnavailable(ProviderError):
    """Network down, rate-limited, auth missing or paid access required."""


class ExternalAccessDisabled(ProviderError):
    """Raised when privacy settings forbid outbound API calls."""


@dataclass
class ProviderResult:
    provider: str
    query: str
    records: list[SourceRecord]
    total_available: int | None
    note: str | None = None


def external_apis_allowed() -> bool:
    return os.environ.get("RTK_ALLOW_EXTERNAL_APIS", "1") not in ("0", "false", "False")


class ScholarlyProvider(ABC):
    name: str = "base"
    base_url: str = ""
    min_interval_s: float = 1.0
    cost_category: str = "low"  # free public APIs; may be rate limited

    def __init__(self, *, transport: httpx.BaseTransport | None = None, timeout: float = 20.0, contact: str | None = None):
        self.contact = contact or os.environ.get("RTK_CONTACT_EMAIL") or None
        ua = "ai-research-toolkit/1.1 (https://github.com/Mrkomiljon/AI-Research-Toolkit"
        ua += f"; mailto:{self.contact})" if self.contact else ")"
        self._client = httpx.Client(timeout=timeout, transport=transport, headers={"User-Agent": ua})
        self._last_call = 0.0

    def _throttle(self) -> None:
        wait = self.min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _get(self, url: str, params: dict | None = None, headers: dict | None = None) -> dict:
        if not external_apis_allowed():
            raise ExternalAccessDisabled("RTK_ALLOW_EXTERNAL_APIS=0: outbound API calls are disabled")
        self._throttle()
        try:
            resp = self._client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{self.name}: network error: {exc}") from exc
        if resp.status_code == 404:
            return {}
        if resp.status_code in (401, 402, 403):
            raise ProviderUnavailable(f"{self.name}: access denied/paid tier required (HTTP {resp.status_code})")
        if resp.status_code == 429:
            raise ProviderUnavailable(f"{self.name}: rate limited (HTTP 429)")
        if resp.status_code >= 500:
            raise ProviderUnavailable(f"{self.name}: server error HTTP {resp.status_code}")
        if resp.status_code != 200:
            raise ProviderError(f"{self.name}: unexpected HTTP {resp.status_code}")
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError(f"{self.name}: non-JSON response") from exc

    @abstractmethod
    def search(self, query: str, *, year_from: int | None = None, year_to: int | None = None, limit: int = 20) -> ProviderResult: ...

    @abstractmethod
    def lookup_doi(self, doi: str) -> SourceRecord | None: ...

    def close(self) -> None:
        self._client.close()
