from __future__ import annotations

import os
import time
from typing import Any, Callable

import requests

from src.providers.base import (
    ProviderPage,
    ProviderParseError,
    ProviderRateLimitError,
    ProviderRequestError,
)
from src.research_radar.models import NormalizedAuthor, NormalizedPaper
from src.research_radar.normalization import (
    compact_openalex_id,
    normalize_openalex_author,
    normalize_openalex_work,
)


DEFAULT_SELECT_FIELDS = (
    "id,title,abstract_inverted_index,doi,ids,publication_date,publication_year,"
    "type,cited_by_count,primary_location,locations,best_oa_location,authorships,"
    "topics,primary_topic"
)
RETRY_STATUSES = {429, 500, 502, 503, 504}
PERMANENT_ERROR_STATUSES = {400, 401, 403, 404}


class OpenAlexProvider:
    """Stateless OpenAlex page fetcher for Phase 2.

    Official API contract adopted on 2026-09-21:
    - Base URL is https://api.openalex.org.
    - /works and /authors are REST endpoints supporting search, filter, select, and paging.
    - per_page is capped at 100; legacy 200 behavior is deprecated.
    - Cursor pagination starts with cursor=* and resumes with meta.next_cursor until it is null
      or results is empty.
    - API keys are optional and passed as api_key when OPENALEX_API_KEY is available.
    - 429 means daily budget or >100 req/s; retry with exponential backoff, honoring Retry-After.
    """

    name = "openalex"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = "https://api.openalex.org",
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("OPENALEX_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = _positive_int(
            timeout_seconds if timeout_seconds is not None else os.getenv("OPENALEX_TIMEOUT_SECONDS"),
            default=30,
        )
        self.max_retries = _positive_int(
            max_retries if max_retries is not None else os.getenv("OPENALEX_MAX_RETRIES"),
            default=4,
            allow_zero=True,
        )
        self.session = session or requests.Session()
        self.sleep = sleep

    def search_works(
        self,
        *,
        query: str,
        from_publication_date: str,
        to_publication_date: str,
        cursor: str = "*",
        per_page: int = 100,
        work_type: str | None = None,
        select_fields: str = DEFAULT_SELECT_FIELDS,
    ) -> ProviderPage[NormalizedPaper]:
        per_page = _validate_per_page(per_page)
        filters = [
            f"from_publication_date:{from_publication_date}",
            f"to_publication_date:{to_publication_date}",
        ]
        if work_type:
            filters.append(f"type:{work_type}")
        params: dict[str, Any] = {
            "search": query,
            "filter": ",".join(filters),
            "select": select_fields,
            "cursor": cursor,
            "per_page": per_page,
        }
        data, rate_metadata = self._get_json("/works", params)
        results = _expect_results(data)
        meta = _expect_meta(data)
        return ProviderPage(
            items=[normalize_openalex_work(item) for item in results],
            next_cursor=meta.get("next_cursor"),
            total_count=meta.get("count"),
            per_page=meta.get("per_page") or per_page,
            provider=self.name,
            request_metadata=self._safe_request_metadata("/works", params),
            rate_metadata=rate_metadata,
        )

    def get_work(self, openalex_id: str) -> NormalizedPaper:
        compact = compact_openalex_id(openalex_id, expected_prefix="W")
        if not compact:
            raise ValueError("openalex_id must identify a work")
        data, _ = self._get_json(f"/works/{compact}", {"select": DEFAULT_SELECT_FIELDS})
        if not isinstance(data, dict):
            raise ProviderParseError("OpenAlex work response was not an object")
        return normalize_openalex_work(data)

    def batch_get_authors(self, openalex_ids: list[str]) -> ProviderPage[NormalizedAuthor]:
        compact_ids = [item for item in (compact_openalex_id(value, expected_prefix="A") for value in openalex_ids) if item]
        compact_ids = list(dict.fromkeys(compact_ids))
        if len(compact_ids) > 100:
            raise ValueError("OpenAlex OR filters support at most 100 IDs per request")
        if not compact_ids:
            return ProviderPage([], None, 0, 0, self.name, {"endpoint": "/authors"}, {})
        params = {
            "filter": "openalex:" + "|".join(compact_ids),
            "per_page": len(compact_ids),
            "select": "id,display_name,orcid,works_count,cited_by_count,ids",
        }
        data, rate_metadata = self._get_json("/authors", params)
        results = _expect_results(data)
        meta = _expect_meta(data)
        return ProviderPage(
            items=[author for author in (normalize_openalex_author(item) for item in results) if author is not None],
            next_cursor=meta.get("next_cursor"),
            total_count=meta.get("count"),
            per_page=meta.get("per_page") or len(compact_ids),
            provider=self.name,
            request_metadata=self._safe_request_metadata("/authors", params),
            rate_metadata=rate_metadata,
        )

    def _get_json(self, path: str, params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        url = self.base_url + path
        request_params = dict(params)
        if self.api_key:
            request_params["api_key"] = self.api_key
        last_error: ProviderRequestError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(url, params=request_params, timeout=self.timeout_seconds)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_error = ProviderRequestError(f"OpenAlex request failed: {type(exc).__name__}")
                if attempt >= self.max_retries:
                    raise last_error from exc
                self.sleep(_backoff_seconds(attempt, None))
                continue
            status = response.status_code
            if 200 <= status < 300:
                try:
                    data = response.json()
                except ValueError as exc:
                    raise ProviderParseError("OpenAlex response was not valid JSON") from exc
                if not isinstance(data, dict):
                    raise ProviderParseError("OpenAlex response was not a JSON object")
                return data, _rate_metadata(response, data)
            if status in RETRY_STATUSES:
                error_cls = ProviderRateLimitError if status == 429 else ProviderRequestError
                last_error = error_cls(f"OpenAlex request failed with HTTP {status}")
                if attempt >= self.max_retries:
                    raise last_error
                self.sleep(_backoff_seconds(attempt, response.headers.get("Retry-After")))
                continue
            if status in PERMANENT_ERROR_STATUSES or 400 <= status < 500:
                raise ProviderRequestError(f"OpenAlex request failed with HTTP {status}")
            raise ProviderRequestError(f"OpenAlex request failed with HTTP {status}")
        raise last_error or ProviderRequestError("OpenAlex request failed")

    def _safe_request_metadata(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        metadata = {"endpoint": endpoint, "params": dict(params), "has_api_key": bool(self.api_key)}
        metadata["params"].pop("api_key", None)
        return metadata


def _validate_per_page(per_page: int) -> int:
    value = int(per_page)
    if value < 1 or value > 100:
        raise ValueError("OpenAlex per_page must be between 1 and 100")
    return value


def _positive_int(value: Any, *, default: int, allow_zero: bool = False) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    minimum = 0 if allow_zero else 1
    return parsed if parsed >= minimum else default


def _backoff_seconds(attempt: int, retry_after: str | None) -> float:
    if retry_after:
        try:
            return max(float(retry_after), 0.0)
        except ValueError:
            pass
    return min(2.0**attempt, 30.0)


def _expect_results(data: dict[str, Any]) -> list[dict[str, Any]]:
    results = data.get("results")
    if not isinstance(results, list):
        raise ProviderParseError("OpenAlex list response missing results[]")
    return [item for item in results if isinstance(item, dict)]


def _expect_meta(data: dict[str, Any]) -> dict[str, Any]:
    meta = data.get("meta")
    if not isinstance(meta, dict):
        raise ProviderParseError("OpenAlex list response missing meta{}")
    return meta


def _rate_metadata(response: requests.Response, data: dict[str, Any]) -> dict[str, Any]:
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    headers = response.headers
    return {
        "limit": headers.get("X-RateLimit-Limit"),
        "remaining": headers.get("X-RateLimit-Remaining"),
        "credits_used": headers.get("X-RateLimit-Credits-Used"),
        "reset": headers.get("X-RateLimit-Reset"),
        "cost_usd": meta.get("cost_usd"),
        "db_response_time_ms": meta.get("db_response_time_ms"),
    }
