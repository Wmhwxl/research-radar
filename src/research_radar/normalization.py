from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import unquote, urlsplit

from src.research_radar.models import (
    NormalizedAuthor,
    NormalizedAuthorship,
    NormalizedInstitution,
    NormalizedPaper,
    NormalizedTopic,
    NormalizedVenue,
)


OPENALEX_BASE_URL = "https://openalex.org"
OPENALEX_ID_RE = re.compile(r"^(?:https?://openalex\.org/)?([WASITPF]\d+)$", re.IGNORECASE)


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    text = unicodedata.normalize("NFKC", title).casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    text = unquote(str(value)).strip()
    if not text:
        return None
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^doi:\s*", "", text, flags=re.IGNORECASE)
    text = text.strip().strip(".")
    return text.casefold() or None


def normalize_arxiv_id(value: str | None) -> str | None:
    if not value:
        return None
    text = unquote(str(value)).strip()
    if not text:
        return None
    text = text.split("#", 1)[0].split("?", 1)[0].strip()
    text = re.sub(
        r"^https?://(?:www\.|export\.)?arxiv\.org/(?:abs|pdf|format)/",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"^arxiv:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/10\.48550/arxiv\.", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\.pdf$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"v\d+$", "", text, flags=re.IGNORECASE)
    text = text.strip()
    if not text:
        return None
    new_style = re.fullmatch(r"(\d{4}\.\d{4,5})", text)
    if new_style:
        return new_style.group(1)
    # Old-style arXiv identifiers are category-scoped, e.g. cs.LG/9901001.
    old_style = re.fullmatch(r"([a-z\-]+(?:\.[a-z]+)?/\d{7})", text, flags=re.IGNORECASE)
    if old_style:
        return old_style.group(1).casefold()
    return None


def normalize_openalex_id(value: str | None, *, expected_prefix: str | None = None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = OPENALEX_ID_RE.fullmatch(text)
    if not match:
        return None
    compact = match.group(1).upper()
    if expected_prefix and not compact.startswith(expected_prefix.upper()):
        return None
    return f"{OPENALEX_BASE_URL}/{compact}"


def compact_openalex_id(value: str | None, *, expected_prefix: str | None = None) -> str | None:
    canonical = normalize_openalex_id(value, expected_prefix=expected_prefix)
    if not canonical:
        return None
    match = OPENALEX_ID_RE.search(canonical)
    return match.group(1).upper() if match else canonical


def reconstruct_openalex_abstract(index: dict[str, Any] | None) -> str | None:
    if not index:
        return None
    positioned: list[tuple[int, str]] = []
    for word, positions in index.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int) and position >= 0:
                positioned.append((position, str(word)))
    if not positioned:
        return None
    return " ".join(word for _, word in sorted(positioned, key=lambda item: item[0]))


def normalize_openalex_institution(raw: dict[str, Any] | None) -> NormalizedInstitution | None:
    if not isinstance(raw, dict):
        return None
    name = raw.get("display_name") or raw.get("name") or ""
    if not name:
        return None
    return NormalizedInstitution(
        openalex_id=normalize_openalex_id(raw.get("id"), expected_prefix="I"),
        name=name,
        country=raw.get("country_code") or raw.get("country"),
        ror_id=_first_present(raw.get("ror"), raw.get("ror_id")),
        type=raw.get("type"),
        homepage=raw.get("homepage_url") or raw.get("homepage"),
    )


def normalize_openalex_venue(raw: dict[str, Any] | None) -> NormalizedVenue | None:
    if not isinstance(raw, dict):
        return None
    name = raw.get("display_name") or raw.get("name") or ""
    if not name:
        return None
    issn = raw.get("issn") or []
    if isinstance(issn, str):
        issn = [issn]
    return NormalizedVenue(
        openalex_id=normalize_openalex_id(raw.get("id"), expected_prefix="S"),
        name=name,
        type=raw.get("type"),
        issn=list(issn),
        publisher=raw.get("publisher"),
        homepage=raw.get("homepage_url") or raw.get("homepage"),
        host_organization=raw.get("host_organization") or raw.get("host_organization_name"),
    )


def normalize_openalex_author(raw: dict[str, Any] | None) -> NormalizedAuthor | None:
    if not isinstance(raw, dict):
        return None
    name = raw.get("display_name") or raw.get("name") or ""
    if not name:
        return None
    ids = raw.get("ids") if isinstance(raw.get("ids"), dict) else {}
    return NormalizedAuthor(
        openalex_id=normalize_openalex_id(raw.get("id"), expected_prefix="A"),
        name=name,
        orcid=_first_present(raw.get("orcid"), ids.get("orcid")),
        semantic_scholar_id=_first_present(raw.get("semantic_scholar_id"), ids.get("semantic_scholar")),
        dblp_id=_first_present(raw.get("dblp_id"), ids.get("dblp")),
        works_count=raw.get("works_count"),
        citation_count=raw.get("cited_by_count"),
    )


def normalize_openalex_work(work: dict[str, Any]) -> NormalizedPaper:
    if not isinstance(work, dict):
        raise TypeError("OpenAlex work must be a mapping")
    primary_location = work.get("primary_location") if isinstance(work.get("primary_location"), dict) else {}
    source = primary_location.get("source") if isinstance(primary_location.get("source"), dict) else None
    ids = work.get("ids") if isinstance(work.get("ids"), dict) else {}
    title = work.get("title") or work.get("display_name") or ""
    doi = normalize_doi(work.get("doi") or ids.get("doi"))
    arxiv_id = _extract_arxiv_id(work)
    return NormalizedPaper(
        openalex_id=normalize_openalex_id(work.get("id"), expected_prefix="W"),
        title=title,
        normalized_title=normalize_title(title),
        abstract=reconstruct_openalex_abstract(work.get("abstract_inverted_index")),
        doi=doi,
        arxiv_id=arxiv_id,
        publication_date=work.get("publication_date"),
        year=work.get("publication_year"),
        work_type=work.get("type"),
        citation_count=work.get("cited_by_count"),
        url=_first_present(
            primary_location.get("landing_page_url"),
            ids.get("doi"),
            work.get("doi"),
            work.get("id"),
        ),
        pdf_url=_extract_pdf_url(work),
        venue=normalize_openalex_venue(source),
        authorships=_normalize_authorships(work.get("authorships")),
        topics=_normalize_topics(work),
        source="openalex",
        source_ids=_normalize_source_ids(work, doi, arxiv_id),
    )


def _normalize_authorships(raw_authorships: Any) -> list[NormalizedAuthorship]:
    if not isinstance(raw_authorships, list):
        return []
    authorships: list[NormalizedAuthorship] = []
    for index, raw in enumerate(raw_authorships, start=1):
        if not isinstance(raw, dict):
            continue
        author = normalize_openalex_author(raw.get("author"))
        if not author:
            continue
        raw_affiliations = raw.get("raw_affiliation_strings") or []
        if isinstance(raw_affiliations, str):
            raw_affiliations = [raw_affiliations]
        institutions = [
            inst
            for inst in (normalize_openalex_institution(item) for item in raw.get("institutions") or [])
            if inst is not None
        ]
        authorships.append(
            NormalizedAuthorship(
                author=author,
                author_position=raw.get("author_position"),
                author_order=index,
                is_corresponding=_first_present(raw.get("is_corresponding"), raw.get("corresponding")),
                raw_author_name=raw.get("raw_author_name") or author.name,
                raw_affiliation_strings=list(raw_affiliations),
                institutions=institutions,
            )
        )
    return authorships


def _normalize_topics(work: dict[str, Any]) -> list[NormalizedTopic]:
    raw_topics = work.get("topics") if isinstance(work.get("topics"), list) else []
    topics = []
    for raw in raw_topics:
        if not isinstance(raw, dict):
            continue
        name = raw.get("display_name") or raw.get("name")
        if not name:
            continue
        topics.append(
            NormalizedTopic(
                openalex_id=normalize_openalex_id(raw.get("id"), expected_prefix="T"),
                name=name,
                score=raw.get("score"),
            )
        )
    if topics:
        return topics
    primary_topic = work.get("primary_topic")
    if isinstance(primary_topic, dict) and (primary_topic.get("display_name") or primary_topic.get("name")):
        return [
            NormalizedTopic(
                openalex_id=normalize_openalex_id(primary_topic.get("id"), expected_prefix="T"),
                name=primary_topic.get("display_name") or primary_topic.get("name"),
                score=primary_topic.get("score"),
            )
        ]
    return []


def _normalize_source_ids(work: dict[str, Any], doi: str | None, arxiv_id: str | None) -> dict[str, Any]:
    ids = work.get("ids") if isinstance(work.get("ids"), dict) else {}
    source_ids: dict[str, Any] = {"openalex": normalize_openalex_id(work.get("id"), expected_prefix="W")}
    if doi:
        source_ids["doi"] = doi
    if arxiv_id:
        source_ids["arxiv"] = arxiv_id
    for key in ("pmid", "pmcid", "mag"):
        if ids.get(key):
            source_ids[key] = ids[key]
    return {key: value for key, value in source_ids.items() if value}


def _extract_arxiv_id(work: dict[str, Any]) -> str | None:
    candidates: list[str] = []
    ids = work.get("ids") if isinstance(work.get("ids"), dict) else {}
    candidates.extend(str(value) for value in ids.values() if value)
    for location_key in ("primary_location", "best_oa_location"):
        location = work.get(location_key)
        if isinstance(location, dict):
            candidates.extend(_location_urls(location))
    locations = work.get("locations")
    if isinstance(locations, list):
        for location in locations:
            if isinstance(location, dict):
                candidates.extend(_location_urls(location))
    for candidate in candidates:
        normalized = normalize_arxiv_id(candidate)
        if normalized and (_looks_like_arxiv_url(candidate) or re.fullmatch(r"\d{4}\.\d{4,5}|[a-z\-]+(?:\.[a-z]+)?/\d{7}", normalized)):
            return normalized
    return None


def _extract_pdf_url(work: dict[str, Any]) -> str | None:
    for location_key in ("primary_location", "best_oa_location"):
        location = work.get(location_key)
        if isinstance(location, dict) and location.get("pdf_url"):
            return location.get("pdf_url")
    locations = work.get("locations")
    if isinstance(locations, list):
        for location in locations:
            if isinstance(location, dict) and location.get("pdf_url"):
                return location.get("pdf_url")
    return None


def _location_urls(location: dict[str, Any]) -> list[str]:
    return [
        str(location[key])
        for key in ("landing_page_url", "pdf_url")
        if location.get(key)
    ]


def _looks_like_arxiv_url(value: str) -> bool:
    parsed = urlsplit(str(value))
    text = str(value).casefold()
    return "arxiv.org" in parsed.netloc.casefold() or "arxiv" in text


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None
