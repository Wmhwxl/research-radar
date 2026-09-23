from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Protocol

import requests

from src.research_radar.models import (
    CandidatePaper,
    NormalizedAuthor,
    NormalizedInstitution,
    NormalizedPaper,
    NormalizedVenue,
    RelevanceDecision,
    ResearchField,
)
from src.research_radar.normalization import normalize_title


class ResearchRadarRepository(Protocol):
    def list_research_fields(self) -> list[dict[str, Any]]:
        ...

    def get_research_field(self, *, field_id: str | None = None, field_slug: str | None = None) -> ResearchField | None:
        ...

    def upsert_research_field(self, field: ResearchField) -> str:
        ...

    def create_sync_run(self, field: ResearchField, *, provider: str, from_date: str, to_date: str, queries: list[dict[str, Any]]) -> str:
        ...

    def get_sync_run(self, run_id: str) -> dict[str, Any] | None:
        ...

    def update_sync_checkpoint(self, run_id: str, checkpoint: dict[str, Any], counters: dict[str, int] | None = None) -> None:
        ...

    def complete_sync_run(self, run_id: str, *, status: str, counters: dict[str, int], error_summary: dict[str, Any] | None = None) -> None:
        ...

    def upsert_accepted_paper(self, field_id: str, candidate: CandidatePaper, decision: RelevanceDecision) -> dict[str, Any]:
        ...

    def rebuild_collaborations(self, field_id: str) -> int:
        ...

    def get_field_overview(self, field_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def get_field_papers(self, field_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def get_field_authors(self, field_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def get_scholar_graph(self, field_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def get_author_detail(self, field_id: str, author_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any] | None:
        ...

    def get_collaboration_detail(self, field_id: str, author_a: str, author_b: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def search_papers(self, query: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def search_authors(self, query: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


class InMemoryResearchRadarRepository:
    def __init__(self) -> None:
        self.research_fields: dict[str, dict[str, Any]] = {}
        self.sync_runs: dict[str, dict[str, Any]] = {}
        self.institutions: dict[str, dict[str, Any]] = {}
        self.venues: dict[str, dict[str, Any]] = {}
        self.authors: dict[str, dict[str, Any]] = {}
        self.papers: dict[str, dict[str, Any]] = {}
        self.paper_authors: dict[tuple[str, str], dict[str, Any]] = {}
        self.paper_author_institutions: set[tuple[str, str, str]] = set()
        self.research_field_papers: dict[tuple[str, str], dict[str, Any]] = {}
        self.author_collaborations: dict[tuple[str, str, str], dict[str, Any]] = {}

    def get_research_field(self, *, field_id: str | None = None, field_slug: str | None = None) -> ResearchField | None:
        for row in self.research_fields.values():
            if field_id and row["id"] == field_id:
                return ResearchField.from_mapping(row)
            if field_slug and row["slug"] == field_slug:
                return ResearchField.from_mapping(row)
        return None

    def upsert_research_field(self, field: ResearchField) -> str:
        existing = self.get_research_field(field_slug=field.slug)
        row_id = existing.id if existing and existing.id else field.id or _uuid()
        self.research_fields[row_id] = {
            "id": row_id,
            "slug": field.slug,
            "name": field.name,
            "description": field.description,
            "core_keywords": list(field.core_keywords),
            "optional_keywords": dict(field.keyword_groups) if field.keyword_groups else list(field.optional_keywords),
            "excluded_keywords": list(field.excluded_keywords),
            "intent_queries": list(field.intent_queries),
            "seed_papers": list(field.seed_papers),
            "seed_authors": list(field.seed_authors),
            "keyword_groups": dict(field.keyword_groups),
        }
        return row_id

    def create_sync_run(self, field: ResearchField, *, provider: str, from_date: str, to_date: str, queries: list[dict[str, Any]]) -> str:
        run_id = _uuid()
        self.sync_runs[run_id] = {
            "id": run_id,
            "research_field_id": field.id,
            "provider": provider,
            "status": "running",
            "from_date": from_date,
            "to_date": to_date,
            "queries": queries,
            "checkpoint": {},
            "started_at": _now(),
        }
        return run_id

    def get_sync_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.sync_runs.get(run_id)
        return dict(row) if row else None

    def update_sync_checkpoint(self, run_id: str, checkpoint: dict[str, Any], counters: dict[str, int] | None = None) -> None:
        self.sync_runs[run_id]["checkpoint"] = dict(checkpoint)
        for key, value in (counters or {}).items():
            self.sync_runs[run_id][key] = value

    def complete_sync_run(self, run_id: str, *, status: str, counters: dict[str, int], error_summary: dict[str, Any] | None = None) -> None:
        self.sync_runs[run_id].update(counters)
        self.sync_runs[run_id].update(status=status, completed_at=_now(), error_summary=error_summary or {})

    def upsert_accepted_paper(self, field_id: str, candidate: CandidatePaper, decision: RelevanceDecision) -> dict[str, Any]:
        paper = candidate.paper
        venue_id = self.upsert_venue(paper.venue) if paper.venue else None
        paper_id = self.upsert_paper(paper, venue_id=venue_id)
        authors_created = 0
        institutions_created = 0
        paper_author_links = 0
        for authorship in paper.authorships:
            institution_ids = []
            for institution in authorship.institutions:
                before = len(self.institutions)
                institution_ids.append(self.upsert_institution(institution))
                institutions_created += int(len(self.institutions) > before)
            before_authors = len(self.authors)
            author_id = self.upsert_author(authorship.author, primary_institution_id=institution_ids[0] if institution_ids else None)
            authors_created += int(len(self.authors) > before_authors)
            key = (paper_id, author_id)
            paper_author_links += int(key not in self.paper_authors)
            self.paper_authors[key] = {
                "paper_id": paper_id,
                "author_id": author_id,
                "author_position": authorship.author_position,
                "author_order": authorship.author_order,
                "is_corresponding": authorship.is_corresponding,
                "raw_affiliation": "\n".join(authorship.raw_affiliation_strings),
                "institution_id": institution_ids[0] if institution_ids else None,
            }
            for institution_id in institution_ids:
                self.paper_author_institutions.add((paper_id, author_id, institution_id))
        existing_field_paper = self.research_field_papers.get((field_id, paper_id), {})
        existing_evidence = existing_field_paper.get("relevance_evidence") or {}
        merged_lanes = list(
            dict.fromkeys(
                [
                    *(existing_evidence.get("matched_lanes") or []),
                    *(decision.evidence.get("matched_lanes") or []),
                ]
            )
        )
        relevance_evidence = {**existing_evidence, **decision.evidence, "matched_lanes": merged_lanes}
        self.research_field_papers[(field_id, paper_id)] = {
            "research_field_id": field_id,
            "paper_id": paper_id,
            "relevance_score": decision.score,
            "relevance_label": decision.label,
            "relevance_evidence": relevance_evidence,
            "discovery_source": "openalex",
        }
        return {
            "paper_id": paper_id,
            "authors_inserted": authors_created,
            "institutions_inserted": institutions_created,
            "paper_author_links_inserted": paper_author_links,
        }

    def upsert_institution(self, institution: NormalizedInstitution) -> str:
        existing_id = _find_by_identity(self.institutions, openalex_id=institution.openalex_id, ror_id=institution.ror_id)
        row_id = existing_id or _uuid()
        self.institutions[row_id] = {
            **self.institutions.get(row_id, {}),
            "id": row_id,
            "name": institution.name,
            "openalex_id": institution.openalex_id,
            "country": institution.country,
            "ror_id": institution.ror_id,
            "type": institution.type,
            "homepage": institution.homepage,
        }
        return row_id

    def upsert_venue(self, venue: NormalizedVenue) -> str:
        existing_id = _find_by_identity(self.venues, openalex_id=venue.openalex_id)
        if existing_id is None:
            for row_id, row in self.venues.items():
                if venue.issn and set(row.get("issn") or []) & set(venue.issn):
                    existing_id = row_id
                    break
        row_id = existing_id or _uuid()
        self.venues[row_id] = {
            **self.venues.get(row_id, {}),
            "id": row_id,
            "name": venue.name,
            "type": venue.type,
            "issn": list(venue.issn),
            "publisher": venue.publisher,
            "openalex_id": venue.openalex_id,
            "homepage": venue.homepage,
        }
        return row_id

    def upsert_author(self, author: NormalizedAuthor, *, primary_institution_id: str | None = None) -> str:
        existing_id = _find_by_identity(self.authors, openalex_id=author.openalex_id)
        if existing_id is None and author.orcid:
            existing_id = _find_by_identity(self.authors, orcid=author.orcid)
        row_id = existing_id or _uuid()
        self.authors[row_id] = {
            **self.authors.get(row_id, {}),
            "id": row_id,
            "name": author.name,
            "normalized_name": normalize_title(author.name),
            "openalex_id": author.openalex_id,
            "orcid": author.orcid,
            "semantic_scholar_id": author.semantic_scholar_id,
            "dblp_id": author.dblp_id,
            "works_count": author.works_count,
            "citation_count": author.citation_count,
            "primary_institution_id": primary_institution_id,
        }
        return row_id

    def upsert_paper(self, paper: NormalizedPaper, *, venue_id: str | None = None) -> str:
        existing_id = self.find_existing_paper(paper)
        row_id = existing_id or _uuid()
        existing_source_ids = self.papers.get(row_id, {}).get("source_ids") or {}
        self.papers[row_id] = {
            **self.papers.get(row_id, {}),
            "id": row_id,
            "title": paper.title,
            "normalized_title": paper.normalized_title,
            "abstract": paper.abstract,
            "doi": paper.doi,
            "arxiv_id": paper.arxiv_id,
            "openalex_id": paper.openalex_id,
            "publication_date": paper.publication_date,
            "year": paper.year,
            "work_type": paper.work_type,
            "citation_count": paper.citation_count or 0,
            "url": paper.url,
            "pdf_url": paper.pdf_url,
            "venue_id": venue_id,
            "source": paper.source,
            "source_ids": {**existing_source_ids, **paper.source_ids},
        }
        return row_id

    def find_existing_paper(self, paper: NormalizedPaper) -> str | None:
        identities = [
            ("openalex_id", paper.openalex_id),
            ("doi", paper.doi.casefold() if paper.doi else None),
            ("arxiv_id", paper.arxiv_id.casefold() if paper.arxiv_id else None),
        ]
        for key, value in identities:
            if not value:
                continue
            for row_id, row in self.papers.items():
                row_value = row.get(key)
                if row_value and str(row_value).casefold() == value:
                    return row_id
        if paper.normalized_title and paper.year:
            for row_id, row in self.papers.items():
                if row.get("normalized_title") == paper.normalized_title and row.get("year") == paper.year:
                    return row_id
        return None

    def rebuild_collaborations(self, field_id: str) -> int:
        self.author_collaborations = {
            key: value for key, value in self.author_collaborations.items() if key[0] != field_id
        }
        for (current_field_id, paper_id), field_paper in self.research_field_papers.items():
            if current_field_id != field_id:
                continue
            author_ids = sorted(author_id for (pa_paper_id, author_id) in self.paper_authors if pa_paper_id == paper_id)
            paper = self.papers[paper_id]
            for index, author_a in enumerate(author_ids):
                for author_b in author_ids[index + 1 :]:
                    key = (field_id, author_a, author_b)
                    row = self.author_collaborations.setdefault(
                        key,
                        {
                            "research_field_id": field_id,
                            "author_a_id": author_a,
                            "author_b_id": author_b,
                            "total_collaboration_count": 0,
                            "field_collaboration_count": 0,
                            "first_collaboration_year": paper.get("year"),
                            "latest_collaboration_year": paper.get("year"),
                            "latest_collaboration_date": paper.get("publication_date"),
                            "weighted_score": None,
                        },
                    )
                    row["total_collaboration_count"] += 1
                    row["field_collaboration_count"] += 1
                    year = paper.get("year")
                    if year:
                        row["first_collaboration_year"] = min(row["first_collaboration_year"] or year, year)
                        row["latest_collaboration_year"] = max(row["latest_collaboration_year"] or year, year)
                    if paper.get("publication_date"):
                        row["latest_collaboration_date"] = max(row["latest_collaboration_date"] or paper["publication_date"], paper["publication_date"])
        return sum(1 for key in self.author_collaborations if key[0] == field_id)


class SupabaseResearchRadarRepository:
    def __init__(self, *, url: str | None = None, service_key: str | None = None, schema: str | None = None, session: requests.Session | None = None) -> None:
        self.url = (url or os.getenv("SUPABASE_URL") or "").rstrip("/")
        self.service_key = service_key or os.getenv("SUPABASE_SERVICE_KEY")
        self.schema = schema or os.getenv("SUPABASE_SCHEMA") or "public"
        self.session = session or requests.Session()
        if not self.url or not self.service_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY are required for Research Radar writes")

    def get_research_field(self, *, field_id: str | None = None, field_slug: str | None = None) -> ResearchField | None:
        params: dict[str, str] = {"select": "*", "limit": "1"}
        if field_id:
            params["id"] = f"eq.{field_id}"
        elif field_slug:
            params["slug"] = f"eq.{field_slug}"
        else:
            raise ValueError("field_id or field_slug is required")
        rows = self._request("GET", "research_fields", params=params)
        return ResearchField.from_mapping(rows[0]) if rows else None

    def upsert_research_field(self, field: ResearchField) -> str:
        payload = {
            "id": field.id,
            "slug": field.slug,
            "name": field.name,
            "description": field.description,
            "core_keywords": field.core_keywords,
            "optional_keywords": field.keyword_groups or field.optional_keywords,
            "excluded_keywords": field.excluded_keywords,
            "intent_queries": field.intent_queries,
            "seed_papers": field.seed_papers,
            "seed_authors": field.seed_authors,
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        rows = self._request("POST", "research_fields", params={"on_conflict": "slug"}, json_body=payload, upsert=True)
        return rows[0]["id"]

    def create_sync_run(self, field: ResearchField, *, provider: str, from_date: str, to_date: str, queries: list[dict[str, Any]]) -> str:
        rows = self._request(
            "POST",
            "research_field_sync_runs",
            json_body={
                "research_field_id": field.id,
                "provider": provider,
                "status": "running",
                "from_date": from_date,
                "to_date": to_date,
                "queries": queries,
                "checkpoint": {},
            },
        )
        return rows[0]["id"]

    def get_sync_run(self, run_id: str) -> dict[str, Any] | None:
        rows = self._request("GET", "research_field_sync_runs", params={"id": f"eq.{run_id}", "select": "*", "limit": "1"})
        return rows[0] if rows else None

    def update_sync_checkpoint(self, run_id: str, checkpoint: dict[str, Any], counters: dict[str, int] | None = None) -> None:
        payload = {"checkpoint": checkpoint, **(counters or {})}
        self._request("PATCH", "research_field_sync_runs", params={"id": f"eq.{run_id}"}, json_body=payload, return_body=False)

    def complete_sync_run(self, run_id: str, *, status: str, counters: dict[str, int], error_summary: dict[str, Any] | None = None) -> None:
        self._request(
            "PATCH",
            "research_field_sync_runs",
            params={"id": f"eq.{run_id}"},
            json_body={**counters, "status": status, "completed_at": _now(), "error_summary": error_summary or {}},
            return_body=False,
        )

    def upsert_accepted_paper(self, field_id: str, candidate: CandidatePaper, decision: RelevanceDecision) -> dict[str, Any]:
        paper = candidate.paper
        venue_id = self._upsert_venue(paper.venue) if paper.venue else None
        paper_id = self._upsert_paper(paper, venue_id=venue_id)
        author_links = 0
        for authorship in paper.authorships:
            institution_ids = [self._upsert_institution(inst) for inst in authorship.institutions]
            author_id = self._upsert_author(authorship.author, primary_institution_id=institution_ids[0] if institution_ids else None)
            self._request(
                "POST",
                "paper_authors",
                params={"on_conflict": "paper_id,author_id"},
                json_body={
                    "paper_id": paper_id,
                    "author_id": author_id,
                    "author_position": authorship.author_position,
                    "author_order": authorship.author_order,
                    "is_corresponding": authorship.is_corresponding,
                    "raw_affiliation": "\n".join(authorship.raw_affiliation_strings),
                    "institution_id": institution_ids[0] if institution_ids else None,
                },
                upsert=True,
            )
            author_links += 1
            for institution_id in institution_ids:
                self._request(
                    "POST",
                    "paper_author_institutions",
                    params={"on_conflict": "paper_id,author_id,institution_id"},
                    json_body={"paper_id": paper_id, "author_id": author_id, "institution_id": institution_id},
                    upsert=True,
                )
        existing_rows = self._request(
            "GET",
            "research_field_papers",
            params={
                "research_field_id": f"eq.{field_id}",
                "paper_id": f"eq.{paper_id}",
                "select": "relevance_evidence",
                "limit": "1",
            },
        )
        existing_evidence = existing_rows[0].get("relevance_evidence") if existing_rows else {}
        evidence = _merge_relevance_evidence(existing_evidence, decision.evidence)
        field_paper_payload = {
            "research_field_id": field_id,
            "paper_id": paper_id,
            "relevance_score": decision.score,
            "relevance_label": decision.label,
            "relevance_evidence": evidence,
            "discovery_source": "openalex",
        }
        self._request(
            "POST",
            "research_field_papers",
            params={"on_conflict": "research_field_id,paper_id"},
            json_body=field_paper_payload,
            upsert=True,
        )
        return {"paper_id": paper_id, "paper_author_links_inserted": author_links}

    def rebuild_collaborations(self, field_id: str) -> int:
        # Full graph recomputation is intentionally implemented in Python for MVP correctness.
        field_papers = self._request("GET", "research_field_papers", params={"research_field_id": f"eq.{field_id}", "select": "paper_id"})
        edge_counts: dict[tuple[str, str], dict[str, Any]] = {}
        for field_paper in field_papers:
            paper_id = field_paper["paper_id"]
            paper_rows = self._request("GET", "academic_papers", params={"id": f"eq.{paper_id}", "select": "id,year,publication_date", "limit": "1"})
            paper = paper_rows[0] if paper_rows else {}
            authors = self._request("GET", "paper_authors", params={"paper_id": f"eq.{paper_id}", "select": "author_id"})
            author_ids = sorted(row["author_id"] for row in authors)
            for index, author_a in enumerate(author_ids):
                for author_b in author_ids[index + 1 :]:
                    key = (author_a, author_b)
                    row = edge_counts.setdefault(
                        key,
                        {
                            "research_field_id": field_id,
                            "author_a_id": author_a,
                            "author_b_id": author_b,
                            "total_collaboration_count": 0,
                            "field_collaboration_count": 0,
                            "first_collaboration_year": paper.get("year"),
                            "latest_collaboration_year": paper.get("year"),
                            "latest_collaboration_date": paper.get("publication_date"),
                        },
                    )
                    row["total_collaboration_count"] += 1
                    row["field_collaboration_count"] += 1
        for row in edge_counts.values():
            self._request(
                "POST",
                "author_collaborations",
                params={"on_conflict": "research_field_id,author_a_id,author_b_id"},
                json_body=row,
                upsert=True,
            )
        return len(edge_counts)

    def _upsert_institution(self, institution: NormalizedInstitution) -> str:
        conflict = "openalex_id" if institution.openalex_id else "ror_id" if institution.ror_id else None
        params = {"on_conflict": conflict} if conflict else None
        rows = self._request("POST", "institutions", params=params, json_body=asdict(institution), upsert=bool(conflict))
        return rows[0]["id"]

    def _upsert_venue(self, venue: NormalizedVenue) -> str:
        if not venue.openalex_id:
            existing = self._request("GET", "venues", params={"name": f"eq.{venue.name}", "select": "id", "limit": "1"})
            if existing:
                return existing[0]["id"]
        rows = self._request(
            "POST",
            "venues",
            params={"on_conflict": "openalex_id"} if venue.openalex_id else None,
            json_body={
                "name": venue.name,
                "type": venue.type,
                "issn": venue.issn,
                "publisher": venue.publisher,
                "openalex_id": venue.openalex_id,
                "homepage": venue.homepage,
            },
            upsert=bool(venue.openalex_id),
        )
        return rows[0]["id"]

    def _upsert_author(self, author: NormalizedAuthor, *, primary_institution_id: str | None) -> str:
        conflict = "openalex_id" if author.openalex_id else "orcid" if author.orcid else None
        if conflict is None:
            existing = self._request(
                "GET",
                "authors",
                params={"normalized_name": f"eq.{normalize_title(author.name)}", "select": "id", "limit": "1"},
            )
            if existing:
                return existing[0]["id"]
        rows = self._request(
            "POST",
            "authors",
            params={"on_conflict": conflict} if conflict else None,
            json_body={
                "name": author.name,
                "normalized_name": normalize_title(author.name),
                "openalex_id": author.openalex_id,
                "orcid": author.orcid,
                "semantic_scholar_id": author.semantic_scholar_id,
                "dblp_id": author.dblp_id,
                "works_count": author.works_count,
                "citation_count": author.citation_count,
                "primary_institution_id": primary_institution_id,
            },
            upsert=bool(conflict),
        )
        return rows[0]["id"]

    def _upsert_paper(self, paper: NormalizedPaper, *, venue_id: str | None) -> str:
        conflict = "openalex_id" if paper.openalex_id else "doi" if paper.doi else "arxiv_id" if paper.arxiv_id else None
        if conflict is None and paper.normalized_title and paper.year:
            existing = self._request(
                "GET",
                "academic_papers",
                params={
                    "normalized_title": f"eq.{paper.normalized_title}",
                    "year": f"eq.{paper.year}",
                    "select": "id",
                    "limit": "1",
                },
            )
            if existing:
                return existing[0]["id"]
        rows = self._request(
            "POST",
            "academic_papers",
            params={"on_conflict": conflict} if conflict else None,
            json_body={
                "title": paper.title,
                "normalized_title": paper.normalized_title,
                "abstract": paper.abstract,
                "doi": paper.doi,
                "arxiv_id": paper.arxiv_id,
                "openalex_id": paper.openalex_id,
                "publication_date": paper.publication_date,
                "year": paper.year,
                "venue_id": venue_id,
                "citation_count": paper.citation_count or 0,
                "url": paper.url,
                "pdf_url": paper.pdf_url,
                "source": paper.source,
                "source_ids": paper.source_ids,
            },
            upsert=bool(conflict),
        )
        return rows[0]["id"]

    def _request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        upsert: bool = False,
        return_body: bool = True,
    ) -> Any:
        headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
            "Accept-Profile": self.schema,
            "Content-Profile": self.schema,
            "Prefer": "return=representation",
        }
        if upsert:
            headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        response = self.session.request(
            method,
            f"{self.url}/rest/v1/{table}",
            params=params,
            data=json.dumps(_strip_none(json_body)) if json_body is not None else None,
            headers=headers,
            timeout=60,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Supabase Research Radar request failed: HTTP {response.status_code} {response.text[:300]}")
        if not return_body:
            return None
        return response.json() if response.text else []


def _find_by_identity(rows: dict[str, dict[str, Any]], **identities: str | None) -> str | None:
    for key, value in identities.items():
        if not value:
            continue
        for row_id, row in rows.items():
            if row.get(key) and str(row[key]).casefold() == str(value).casefold():
                return row_id
    return None


def _strip_none(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return {key: value for key, value in payload.items() if value is not None}


def _merge_relevance_evidence(existing: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any]:
    existing = existing or {}
    incoming = incoming or {}
    matched_lanes = list(
        dict.fromkeys([*(existing.get("matched_lanes") or []), *(incoming.get("matched_lanes") or [])])
    )
    return {**existing, **incoming, "matched_lanes": matched_lanes}


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


try:
    from src.research_radar.sqlite_repository import SQLiteResearchRadarRepository
except Exception:  # pragma: no cover - keeps legacy Supabase-only imports lightweight
    SQLiteResearchRadarRepository = None  # type: ignore
