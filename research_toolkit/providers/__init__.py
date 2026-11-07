"""Scholarly metadata providers. None of them returns full paper texts; access_level is reported honestly."""
from __future__ import annotations

from .base import (
    ExternalAccessDisabled,
    ProviderError,
    ProviderResult,
    ProviderUnavailable,
    ScholarlyProvider,
)
from .crossref import CrossrefProvider
from .openalex import OpenAlexProvider
from .semantic_scholar import SemanticScholarProvider

PROVIDERS = {
    "crossref": CrossrefProvider,
    "openalex": OpenAlexProvider,
    "semantic_scholar": SemanticScholarProvider,
}
DEFAULT_PROVIDERS = ("openalex", "crossref")


def make_providers(names: list[str] | tuple[str, ...] | None = None, **kw) -> list[ScholarlyProvider]:
    chosen = names or DEFAULT_PROVIDERS
    unknown = [n for n in chosen if n not in PROVIDERS]
    if unknown:
        raise ValueError(f"unknown providers: {unknown}; choose from {sorted(PROVIDERS)}")
    return [PROVIDERS[n](**kw) for n in chosen]


__all__ = [
    "ExternalAccessDisabled",
    "ProviderError",
    "ProviderResult",
    "ProviderUnavailable",
    "ScholarlyProvider",
    "CrossrefProvider",
    "OpenAlexProvider",
    "SemanticScholarProvider",
    "PROVIDERS",
    "DEFAULT_PROVIDERS",
    "make_providers",
]
