from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NormalizedInstitution:
    openalex_id: str | None
    name: str
    country: str | None = None
    ror_id: str | None = None
    type: str | None = None
    homepage: str | None = None


@dataclass(frozen=True)
class NormalizedVenue:
    openalex_id: str | None
    name: str
    type: str | None = None
    issn: list[str] = field(default_factory=list)
    publisher: str | None = None
    homepage: str | None = None
    host_organization: str | None = None


@dataclass(frozen=True)
class NormalizedAuthor:
    openalex_id: str | None
    name: str
    orcid: str | None = None
    semantic_scholar_id: str | None = None
    dblp_id: str | None = None
    works_count: int | None = None
    citation_count: int | None = None


@dataclass(frozen=True)
class NormalizedAuthorship:
    author: NormalizedAuthor
    author_position: str | None
    author_order: int
    is_corresponding: bool | None = None
    raw_author_name: str | None = None
    raw_affiliation_strings: list[str] = field(default_factory=list)
    institutions: list[NormalizedInstitution] = field(default_factory=list)


@dataclass(frozen=True)
class NormalizedTopic:
    openalex_id: str | None
    name: str
    score: float | None = None


@dataclass(frozen=True)
class NormalizedPaper:
    openalex_id: str | None
    title: str
    normalized_title: str
    abstract: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    publication_date: str | None = None
    year: int | None = None
    work_type: str | None = None
    citation_count: int | None = None
    url: str | None = None
    pdf_url: str | None = None
    venue: NormalizedVenue | None = None
    authorships: list[NormalizedAuthorship] = field(default_factory=list)
    topics: list[NormalizedTopic] = field(default_factory=list)
    source: str = "openalex"
    source_ids: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResearchField:
    id: str | None
    slug: str
    name: str
    description: str | None = None
    core_keywords: list[str] = field(default_factory=list)
    optional_keywords: list[str] = field(default_factory=list)
    excluded_keywords: list[str] = field(default_factory=list)
    intent_queries: list[str] = field(default_factory=list)
    seed_papers: list[Any] = field(default_factory=list)
    seed_authors: list[Any] = field(default_factory=list)
    keyword_groups: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "ResearchField":
        optional = row.get("optional_keywords") or []
        keyword_groups = row.get("keyword_groups") or {}
        if isinstance(optional, dict):
            keyword_groups = {str(k): _string_list(v) for k, v in optional.items()}
            optional_list = [term for values in keyword_groups.values() for term in values]
        else:
            optional_list = _string_list(optional)
        return cls(
            id=row.get("id"),
            slug=row.get("slug") or _slugify(row.get("name") or "research-field"),
            name=row.get("name") or "Research Field",
            description=row.get("description"),
            core_keywords=_string_list(row.get("core_keywords") or []),
            optional_keywords=optional_list,
            excluded_keywords=_string_list(row.get("excluded_keywords") or []),
            intent_queries=_string_list(row.get("intent_queries") or []),
            seed_papers=list(row.get("seed_papers") or []),
            seed_authors=list(row.get("seed_authors") or []),
            keyword_groups={str(k): _string_list(v) for k, v in keyword_groups.items()},
        )


@dataclass(frozen=True)
class QueryLane:
    id: str
    name: str
    query: str
    weight: float
    type: str
    description: str = ""


@dataclass
class CandidatePaper:
    paper: NormalizedPaper
    matched_lanes: list[str] = field(default_factory=list)
    matched_queries: list[str] = field(default_factory=list)
    retrieval_count: int = 0
    retrieval_evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RelevanceDecision:
    score: float
    label: str
    accepted: bool
    evidence: dict[str, Any] = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)
    matched_terms: dict[str, list[str]] = field(default_factory=dict)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _slugify(value: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "research-field"
