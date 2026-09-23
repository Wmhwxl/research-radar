from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar

from src.research_radar.models import NormalizedPaper


T = TypeVar("T")


@dataclass(frozen=True)
class ProviderPage(Generic[T]):
    items: list[T]
    next_cursor: str | None
    total_count: int | None
    per_page: int
    provider: str
    request_metadata: dict[str, Any] = field(default_factory=dict)
    rate_metadata: dict[str, Any] = field(default_factory=dict)


class ProviderError(Exception):
    """Base class for provider-layer errors that are safe to show in logs."""


class ProviderRequestError(ProviderError):
    """The remote provider rejected or failed a request."""


class ProviderRateLimitError(ProviderRequestError):
    """The provider returned a rate-limit response after retries."""


class ProviderParseError(ProviderError):
    """The provider response shape was not usable."""


class AcademicProvider(Protocol):
    name: str

    def search_works(
        self,
        *,
        query: str,
        from_publication_date: str,
        to_publication_date: str,
        cursor: str = "*",
        per_page: int = 100,
        work_type: str | None = None,
    ) -> ProviderPage[NormalizedPaper]:
        ...

