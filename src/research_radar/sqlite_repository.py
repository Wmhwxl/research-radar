from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
from src.research_radar.storage.sqlite.migrator import apply_migrations, connect_sqlite


class SQLiteResearchRadarRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        apply_migrations(self.database_path)
        self.conn = connect_sqlite(self.database_path)

    def close(self) -> None:
        self.conn.close()

    def list_research_fields(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT rf.*,
                   MAX(sr.completed_at) AS last_sync_at,
                   COALESCE((SELECT status FROM research_field_sync_runs s
                             WHERE s.research_field_id = rf.id
                             ORDER BY s.started_at DESC LIMIT 1), 'available') AS sync_status,
                   (SELECT id FROM research_field_sync_runs s
                    WHERE s.research_field_id = rf.id
                    ORDER BY s.started_at DESC LIMIT 1) AS latest_sync_run_id,
                   (SELECT MAX(year)
                    FROM research_field_papers rfp
                    JOIN academic_papers ap ON ap.id = rfp.paper_id
                    WHERE rfp.research_field_id = rf.id) AS max_year
            FROM research_fields rf
            LEFT JOIN research_field_sync_runs sr ON sr.research_field_id = rf.id
            GROUP BY rf.id
            ORDER BY rf.name
            """
        ).fetchall()
        return [self._field_payload(row) for row in rows]

    def get_research_field(self, *, field_id: str | None = None, field_slug: str | None = None) -> ResearchField | None:
        if field_id:
            row = self.conn.execute("SELECT * FROM research_fields WHERE id = ?", (field_id,)).fetchone()
        elif field_slug:
            row = self.conn.execute("SELECT * FROM research_fields WHERE slug = ?", (field_slug,)).fetchone()
        else:
            raise ValueError("field_id or field_slug is required")
        return ResearchField.from_mapping(self._field_payload(row)) if row else None

    def get_research_field_row(self, field_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT rf.*,
                   MAX(sr.completed_at) AS last_sync_at,
                   COALESCE((SELECT status FROM research_field_sync_runs s
                             WHERE s.research_field_id = rf.id
                             ORDER BY s.started_at DESC LIMIT 1), 'available') AS sync_status,
                   (SELECT id FROM research_field_sync_runs s
                    WHERE s.research_field_id = rf.id
                    ORDER BY s.started_at DESC LIMIT 1) AS latest_sync_run_id,
                   (SELECT MAX(year)
                    FROM research_field_papers rfp
                    JOIN academic_papers ap ON ap.id = rfp.paper_id
                    WHERE rfp.research_field_id = rf.id) AS max_year
            FROM research_fields rf
            LEFT JOIN research_field_sync_runs sr ON sr.research_field_id = rf.id
            WHERE rf.id = ?
            GROUP BY rf.id
            """,
            (field_id,),
        ).fetchone()
        return self._field_payload(row) if row else None

    def upsert_research_field(self, field: ResearchField) -> str:
        existing = self.conn.execute("SELECT id FROM research_fields WHERE slug = ?", (field.slug,)).fetchone()
        row_id = existing["id"] if existing else field.id or _uuid()
        now = _now()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO research_fields
                  (id, slug, name, description, core_keywords, optional_keywords, excluded_keywords,
                   intent_queries, seed_papers, seed_authors, enabled, auto_sync, sync_frequency, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                  name=excluded.name,
                  description=excluded.description,
                  core_keywords=excluded.core_keywords,
                  optional_keywords=excluded.optional_keywords,
                  excluded_keywords=excluded.excluded_keywords,
                  intent_queries=excluded.intent_queries,
                  seed_papers=excluded.seed_papers,
                  seed_authors=excluded.seed_authors,
                  enabled=excluded.enabled,
                  auto_sync=excluded.auto_sync,
                  sync_frequency=excluded.sync_frequency,
                  updated_at=excluded.updated_at
                """,
                (
                    row_id,
                    field.slug,
                    field.name,
                    field.description,
                    _json(field.core_keywords),
                    _json(field.keyword_groups or field.optional_keywords),
                    _json(field.excluded_keywords),
                    _json(field.intent_queries),
                    _json(field.seed_papers),
                    _json(field.seed_authors),
                    1,
                    1,
                    "daily",
                    now,
                    now,
                ),
            )
        return row_id

    def create_research_field(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        slug = _unique_slug(self.conn, _slugify(payload.get("slug") or name))
        field = ResearchField(
            id=_uuid(),
            slug=slug,
            name=name,
            description=payload.get("description"),
            core_keywords=_string_list(payload.get("core_keywords")),
            optional_keywords=_string_list(payload.get("optional_keywords")),
            excluded_keywords=_string_list(payload.get("excluded_keywords")),
            intent_queries=_string_list(payload.get("intent_queries")),
            seed_papers=list(payload.get("seed_papers") or []),
            seed_authors=list(payload.get("seed_authors") or []),
        )
        field_id = self.upsert_research_field(field)
        self.update_research_field(
            field_id,
            {
                "enabled": payload.get("enabled", True),
                "auto_sync": payload.get("auto_sync", True),
                "sync_frequency": payload.get("sync_frequency", "daily"),
            },
        )
        return self.get_research_field_row(field_id) or {"id": field_id, "slug": slug, "name": name}

    def update_research_field(self, field_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_research_field(field_id=field_id)
        if not current:
            raise KeyError("research field not found")
        field = ResearchField(
            id=field_id,
            slug=current.slug,
            name=str(payload.get("name") or current.name).strip(),
            description=payload.get("description", current.description),
            core_keywords=_string_list(payload.get("core_keywords", current.core_keywords)),
            optional_keywords=_string_list(payload.get("optional_keywords", current.optional_keywords)),
            excluded_keywords=_string_list(payload.get("excluded_keywords", current.excluded_keywords)),
            intent_queries=_string_list(payload.get("intent_queries", current.intent_queries)),
            seed_papers=list(payload.get("seed_papers", current.seed_papers) or []),
            seed_authors=list(payload.get("seed_authors", current.seed_authors) or []),
            keyword_groups=current.keyword_groups,
        )
        self.upsert_research_field(field)
        extra: dict[str, Any] = {}
        if "enabled" in payload:
            extra["enabled"] = int(bool(payload["enabled"]))
        if "auto_sync" in payload:
            extra["auto_sync"] = int(bool(payload["auto_sync"]))
        if "sync_frequency" in payload:
            extra["sync_frequency"] = _sync_frequency(payload["sync_frequency"])
        if extra:
            extra["updated_at"] = _now()
            assignments = ", ".join(f"{key} = ?" for key in extra)
            with self.conn:
                self.conn.execute(f"UPDATE research_fields SET {assignments} WHERE id = ?", [*extra.values(), field_id])
        return self.get_research_field_row(field_id) or {}

    def touch_field_visit(self, field_id: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE research_fields SET last_visited_at = ? WHERE id = ?", (_now(), field_id))

    def get_home(self) -> dict[str, Any]:
        fields = self.list_research_fields()
        cards = []
        for field in fields:
            overview = self.get_field_overview(field["id"], {})
            last_visit = field.get("last_visited_at")
            new_papers = 0
            if last_visit:
                new_papers = self.conn.execute(
                    """
                    SELECT COUNT(*) FROM research_field_papers
                    WHERE research_field_id = ? AND first_discovered_at > ?
                    """,
                    (field["id"], last_visit),
                ).fetchone()[0]
            cards.append(
                {
                    **field,
                    "paper_count": overview["paper_count"],
                    "author_count": overview["author_count"],
                    "new_papers_since_last_visit": new_papers,
                }
            )
        return {"fields": cards}

    def get_running_sync_run(self, field_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT * FROM research_field_sync_runs
            WHERE research_field_id = ? AND status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (field_id,),
        ).fetchone()
        if not row:
            return None
        data = _row_to_dict(row)
        for key in ("queries", "checkpoint", "error_summary"):
            data[key] = _loads(data.get(key), [] if key == "queries" else {})
        return data

    def mark_interrupted_sync_runs(self) -> int:
        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE research_field_sync_runs
                SET status = 'interrupted',
                    completed_at = ?,
                    error_summary = ?
                WHERE status = 'running'
                """,
                (_now(), _json({"message": "server restarted before sync completed"})),
            )
        return cursor.rowcount

    def due_auto_sync_fields(self, *, now: datetime | None = None) -> list[ResearchField]:
        now = now or datetime.now(timezone.utc)
        rows = self.conn.execute(
            """
            SELECT rf.*
            FROM research_fields rf
            WHERE rf.enabled = 1 AND rf.auto_sync = 1
            ORDER BY rf.name
            """
        ).fetchall()
        fields: list[ResearchField] = []
        for row in rows:
            last = self.conn.execute(
                """
                SELECT completed_at FROM research_field_sync_runs
                WHERE research_field_id = ? AND status IN ('succeeded', 'partial')
                ORDER BY completed_at DESC LIMIT 1
                """,
                (row["id"],),
            ).fetchone()
            if last is None:
                continue
            last_dt = _parse_dt(last["completed_at"])
            if last_dt and (now - last_dt).total_seconds() >= _frequency_seconds(row["sync_frequency"]):
                fields.append(ResearchField.from_mapping(self._field_payload(row)))
        return fields

    def get_field_brief(self, field_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        since = filters.get("since") or _start_of_today()
        new_papers = self.conn.execute(
            """
            SELECT ap.*, v.name AS venue, rfp.relevance_score, rfp.relevance_label, rfp.relevance_evidence
            FROM research_field_papers rfp
            JOIN academic_papers ap ON ap.id = rfp.paper_id
            LEFT JOIN venues v ON v.id = ap.venue_id
            WHERE rfp.research_field_id = ? AND datetime(rfp.first_discovered_at) >= datetime(?)
            ORDER BY CASE rfp.relevance_label WHEN 'core' THEN 0 ELSE 1 END,
                     rfp.relevance_score DESC,
                     ap.publication_date DESC
            LIMIT 12
            """,
            (field_id, since),
        ).fetchall()
        new_authors = self.conn.execute(
            """
            SELECT a.id, a.name, i.name AS primary_institution, MIN(ap.year) AS first_field_year,
                   MIN(ap.title) AS first_field_paper
            FROM authors a
            JOIN paper_authors pa ON pa.author_id = a.id
            JOIN academic_papers ap ON ap.id = pa.paper_id
            JOIN research_field_papers rfp ON rfp.paper_id = ap.id
            LEFT JOIN institutions i ON i.id = a.primary_institution_id
            WHERE rfp.research_field_id = ?
            GROUP BY a.id
            HAVING datetime(MIN(rfp.first_discovered_at)) >= datetime(?)
            ORDER BY first_field_year DESC, a.name
            LIMIT 12
            """,
            (field_id, since),
        ).fetchall()
        new_collabs = self._new_collaborations(field_id, since)
        return {
            "since": since,
            "new_paper_count": len(new_papers),
            "new_author_count": len(new_authors),
            "new_collaboration_count": len(new_collabs),
            "highly_relevant_papers": [self._paper_payload(row) for row in new_papers],
            "new_authors": [_row_to_dict(row) for row in new_authors],
            "new_collaborations": new_collabs,
        }

    def create_sync_run(self, field: ResearchField, *, provider: str, from_date: str, to_date: str, queries: list[dict[str, Any]]) -> str:
        run_id = _uuid()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO research_field_sync_runs
                  (id, research_field_id, provider, status, from_date, to_date, queries, checkpoint, started_at)
                VALUES (?, ?, ?, 'running', ?, ?, ?, '{}', ?)
                """,
                (run_id, field.id, provider, from_date, to_date, _json(queries), _now()),
            )
        return run_id

    def get_sync_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM research_field_sync_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        data = _row_to_dict(row)
        for key in ("queries", "checkpoint", "error_summary"):
            data[key] = _loads(data.get(key), [] if key == "queries" else {})
        return data

    def update_sync_checkpoint(self, run_id: str, checkpoint: dict[str, Any], counters: dict[str, int] | None = None) -> None:
        payload = {"checkpoint": _json(checkpoint), **(counters or {})}
        assignments = ", ".join(f"{key} = ?" for key in payload)
        with self.conn:
            self.conn.execute(
                f"UPDATE research_field_sync_runs SET {assignments} WHERE id = ?",
                [*payload.values(), run_id],
            )

    def complete_sync_run(self, run_id: str, *, status: str, counters: dict[str, int], error_summary: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {
            **counters,
            "status": status,
            "completed_at": _now(),
            "error_summary": _json(error_summary or {}),
        }
        assignments = ", ".join(f"{key} = ?" for key in payload)
        with self.conn:
            self.conn.execute(f"UPDATE research_field_sync_runs SET {assignments} WHERE id = ?", [*payload.values(), run_id])

    def upsert_accepted_paper(self, field_id: str, candidate: CandidatePaper, decision: RelevanceDecision) -> dict[str, Any]:
        paper = candidate.paper
        with self.conn:
            venue_id = self.upsert_venue(paper.venue) if paper.venue else None
            paper_before = self.find_existing_paper(paper)
            paper_id = self.upsert_paper(paper, venue_id=venue_id)
            authors_created = 0
            institutions_created = 0
            author_links_created = 0
            for authorship in paper.authorships:
                institution_ids: list[str] = []
                for institution in authorship.institutions:
                    before = self._count("institutions")
                    institution_ids.append(self.upsert_institution(institution))
                    institutions_created += int(self._count("institutions") > before)
                before_authors = self._count("authors")
                author_id = self.upsert_author(authorship.author, primary_institution_id=institution_ids[0] if institution_ids else None)
                authors_created += int(self._count("authors") > before_authors)
                existed = self.conn.execute(
                    "SELECT 1 FROM paper_authors WHERE paper_id = ? AND author_id = ?",
                    (paper_id, author_id),
                ).fetchone()
                self.conn.execute(
                    """
                    INSERT INTO paper_authors
                      (paper_id, author_id, author_position, author_order, is_corresponding, raw_affiliation, institution_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(paper_id, author_id) DO UPDATE SET
                      author_position=excluded.author_position,
                      author_order=excluded.author_order,
                      is_corresponding=excluded.is_corresponding,
                      raw_affiliation=excluded.raw_affiliation,
                      institution_id=excluded.institution_id
                    """,
                    (
                        paper_id,
                        author_id,
                        authorship.author_position,
                        authorship.author_order,
                        _bool(authorship.is_corresponding),
                        "\n".join(authorship.raw_affiliation_strings),
                        institution_ids[0] if institution_ids else None,
                    ),
                )
                author_links_created += int(existed is None)
                for institution_id in institution_ids:
                    self.conn.execute(
                        """
                        INSERT OR IGNORE INTO paper_author_institutions(paper_id, author_id, institution_id)
                        VALUES (?, ?, ?)
                        """,
                        (paper_id, author_id, institution_id),
                    )
            existing = self.conn.execute(
                "SELECT relevance_evidence FROM research_field_papers WHERE research_field_id = ? AND paper_id = ?",
                (field_id, paper_id),
            ).fetchone()
            evidence = _merge_evidence(_loads(existing["relevance_evidence"], {}) if existing else {}, decision.evidence)
            self.conn.execute(
                """
                INSERT INTO research_field_papers
                  (research_field_id, paper_id, relevance_score, relevance_label, relevance_evidence, discovery_source, latest_seen_at)
                VALUES (?, ?, ?, ?, ?, 'openalex', ?)
                ON CONFLICT(research_field_id, paper_id) DO UPDATE SET
                  relevance_score=excluded.relevance_score,
                  relevance_label=excluded.relevance_label,
                  relevance_evidence=excluded.relevance_evidence,
                  latest_seen_at=excluded.latest_seen_at
                """,
                (field_id, paper_id, decision.score, decision.label, _json(evidence), _now()),
            )
            self.refresh_paper_search_document(paper_id)
        return {
            "paper_id": paper_id,
            "paper_inserted": int(paper_before is None),
            "authors_inserted": authors_created,
            "institutions_inserted": institutions_created,
            "paper_author_links_inserted": author_links_created,
        }

    def upsert_institution(self, institution: NormalizedInstitution) -> str:
        existing_id = self._find_identity("institutions", openalex_id=institution.openalex_id, ror_id=institution.ror_id)
        row_id = existing_id or _uuid()
        self.conn.execute(
            """
            INSERT INTO institutions(id, name, openalex_id, country, ror_id, type, homepage, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name, openalex_id=excluded.openalex_id, country=excluded.country,
              ror_id=excluded.ror_id, type=excluded.type, homepage=excluded.homepage, updated_at=excluded.updated_at
            """,
            (row_id, institution.name, institution.openalex_id, institution.country, institution.ror_id, institution.type, institution.homepage, _now()),
        )
        return row_id

    def upsert_venue(self, venue: NormalizedVenue) -> str:
        existing_id = self._find_identity("venues", openalex_id=venue.openalex_id)
        if not existing_id and venue.issn:
            for row in self.conn.execute("SELECT id, issn FROM venues").fetchall():
                if set(_loads(row["issn"], [])) & set(venue.issn):
                    existing_id = row["id"]
                    break
        row_id = existing_id or _uuid()
        self.conn.execute(
            """
            INSERT INTO venues(id, name, type, issn, publisher, openalex_id, homepage, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name, type=excluded.type, issn=excluded.issn, publisher=excluded.publisher,
              openalex_id=excluded.openalex_id, homepage=excluded.homepage, updated_at=excluded.updated_at
            """,
            (row_id, venue.name, venue.type, _json(venue.issn), venue.publisher, venue.openalex_id, venue.homepage, _now()),
        )
        return row_id

    def upsert_author(self, author: NormalizedAuthor, *, primary_institution_id: str | None = None) -> str:
        existing_id = self._find_identity("authors", openalex_id=author.openalex_id, orcid=author.orcid)
        if not existing_id:
            row = self.conn.execute(
                "SELECT id FROM authors WHERE normalized_name = ? LIMIT 1",
                (normalize_title(author.name),),
            ).fetchone()
            existing_id = row["id"] if row else None
        row_id = existing_id or _uuid()
        self.conn.execute(
            """
            INSERT INTO authors
              (id, name, normalized_name, openalex_id, orcid, semantic_scholar_id, dblp_id,
               works_count, citation_count, primary_institution_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name,
              normalized_name=excluded.normalized_name,
              openalex_id=excluded.openalex_id,
              orcid=excluded.orcid,
              semantic_scholar_id=excluded.semantic_scholar_id,
              dblp_id=excluded.dblp_id,
              works_count=excluded.works_count,
              citation_count=excluded.citation_count,
              primary_institution_id=COALESCE(excluded.primary_institution_id, authors.primary_institution_id),
              updated_at=excluded.updated_at
            """,
            (
                row_id,
                author.name,
                normalize_title(author.name),
                author.openalex_id,
                author.orcid,
                author.semantic_scholar_id,
                author.dblp_id,
                author.works_count,
                author.citation_count,
                primary_institution_id,
                _now(),
            ),
        )
        return row_id

    def upsert_paper(self, paper: NormalizedPaper, *, venue_id: str | None = None) -> str:
        existing_id = self.find_existing_paper(paper)
        row_id = existing_id or _uuid()
        existing = self.conn.execute("SELECT source_ids FROM academic_papers WHERE id = ?", (row_id,)).fetchone()
        source_ids = {**(_loads(existing["source_ids"], {}) if existing else {}), **paper.source_ids}
        self.conn.execute(
            """
            INSERT INTO academic_papers
              (id, title, normalized_title, abstract, doi, arxiv_id, openalex_id, publication_date,
               year, work_type, venue_id, citation_count, url, pdf_url, source, source_ids, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              title=excluded.title,
              normalized_title=excluded.normalized_title,
              abstract=excluded.abstract,
              doi=COALESCE(excluded.doi, academic_papers.doi),
              arxiv_id=COALESCE(excluded.arxiv_id, academic_papers.arxiv_id),
              openalex_id=COALESCE(excluded.openalex_id, academic_papers.openalex_id),
              publication_date=excluded.publication_date,
              year=excluded.year,
              work_type=excluded.work_type,
              venue_id=excluded.venue_id,
              citation_count=excluded.citation_count,
              url=excluded.url,
              pdf_url=excluded.pdf_url,
              source=excluded.source,
              source_ids=excluded.source_ids,
              updated_at=excluded.updated_at
            """,
            (
                row_id,
                paper.title,
                paper.normalized_title or normalize_title(paper.title),
                paper.abstract,
                paper.doi.casefold() if paper.doi else None,
                paper.arxiv_id.casefold() if paper.arxiv_id else None,
                paper.openalex_id,
                paper.publication_date,
                paper.year,
                paper.work_type,
                venue_id,
                paper.citation_count or 0,
                paper.url,
                paper.pdf_url,
                paper.source,
                _json(source_ids),
                _now(),
            ),
        )
        self.refresh_paper_search_document(row_id)
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
            row = self.conn.execute(f"SELECT id FROM academic_papers WHERE {key} = ? LIMIT 1", (value,)).fetchone()
            if row:
                return row["id"]
        if paper.normalized_title and paper.year:
            row = self.conn.execute(
                "SELECT id FROM academic_papers WHERE normalized_title = ? AND year = ? LIMIT 1",
                (paper.normalized_title, paper.year),
            ).fetchone()
            if row:
                return row["id"]
        return None

    def refresh_paper_search_document(self, paper_id: str) -> None:
        row = self.conn.execute(
            """
            SELECT ap.id, ap.title, ap.abstract, COALESCE(v.name, '') AS venue_name
            FROM academic_papers ap
            LEFT JOIN venues v ON v.id = ap.venue_id
            WHERE ap.id = ?
            """,
            (paper_id,),
        ).fetchone()
        if not row:
            return
        author_names = " ".join(
            item["name"]
            for item in self.conn.execute(
                """
                SELECT a.name FROM paper_authors pa
                JOIN authors a ON a.id = pa.author_id
                WHERE pa.paper_id = ?
                ORDER BY pa.author_order, a.name
                """,
                (paper_id,),
            ).fetchall()
        )
        self.conn.execute("DELETE FROM paper_search_fts WHERE paper_id = ?", (paper_id,))
        self.conn.execute(
            """
            INSERT INTO paper_search_documents(paper_id, title, abstract, venue_name, author_names, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(paper_id) DO UPDATE SET
              title=excluded.title, abstract=excluded.abstract, venue_name=excluded.venue_name,
              author_names=excluded.author_names, updated_at=excluded.updated_at
            """,
            (paper_id, row["title"] or "", row["abstract"] or "", row["venue_name"] or "", author_names, _now()),
        )
        self.conn.execute(
            "INSERT INTO paper_search_fts(paper_id, title, abstract, venue_name, author_names) VALUES (?, ?, ?, ?, ?)",
            (paper_id, row["title"] or "", row["abstract"] or "", row["venue_name"] or "", author_names),
        )

    def rebuild_collaborations(self, field_id: str) -> int:
        with self.conn:
            self.conn.execute("DELETE FROM author_collaborations WHERE research_field_id = ?", (field_id,))
            papers = self._field_paper_ids(field_id)
            edges: dict[tuple[str, str], dict[str, Any]] = {}
            for paper in papers:
                authors = [
                    row["author_id"]
                    for row in self.conn.execute(
                        "SELECT author_id FROM paper_authors WHERE paper_id = ? ORDER BY author_order, author_id",
                        (paper["paper_id"],),
                    ).fetchall()
                ]
                for index, author_a in enumerate(authors):
                    for author_b in authors[index + 1 :]:
                        a, b = sorted((author_a, author_b))
                        edge = edges.setdefault(
                            (a, b),
                            {
                                "count": 0,
                                "first_year": paper["year"],
                                "latest_year": paper["year"],
                                "latest_date": paper["publication_date"],
                            },
                        )
                        edge["count"] += 1
                        if paper["year"]:
                            edge["first_year"] = min(edge["first_year"] or paper["year"], paper["year"])
                            edge["latest_year"] = max(edge["latest_year"] or paper["year"], paper["year"])
                        if paper["publication_date"]:
                            edge["latest_date"] = max(edge["latest_date"] or paper["publication_date"], paper["publication_date"])
            for (a, b), edge in edges.items():
                self.conn.execute(
                    """
                    INSERT INTO author_collaborations
                      (research_field_id, author_a_id, author_b_id, total_collaboration_count,
                       field_collaboration_count, first_collaboration_year, latest_collaboration_year,
                       latest_collaboration_date, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (field_id, a, b, edge["count"], edge["count"], edge["first_year"], edge["latest_year"], edge["latest_date"], _now()),
                )
        return len(edges)

    def get_field_overview(self, field_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        papers = self.get_field_papers(field_id, {**(filters or {}), "limit": 10000, "offset": 0})["items"]
        authors = self.get_field_authors(field_id, {**(filters or {}), "limit": 10000, "offset": 0})["items"]
        graph = self.get_scholar_graph(field_id, {**(filters or {}), "max_nodes": "all"})
        years: dict[int, int] = {}
        for paper in papers:
            if paper.get("year"):
                years[int(paper["year"])] = years.get(int(paper["year"]), 0) + 1
        new_authors: dict[int, int] = {}
        for author in authors:
            if author.get("first_field_year"):
                year = int(author["first_field_year"])
                new_authors[year] = new_authors.get(year, 0) + 1
        return {
            "paper_count": len(papers),
            "author_count": len(authors),
            "institution_count": len({a.get("primary_institution") for a in authors if a.get("primary_institution")}),
            "collaboration_count": len(graph["edges"]),
            "venue_count": len({p.get("venue") for p in papers if p.get("venue")}),
            "yearly_paper_counts": [{"year": year, "count": years[year]} for year in sorted(years)],
            "yearly_new_author_counts": [{"year": year, "count": new_authors[year]} for year in sorted(new_authors)],
            "recent_core_papers": [p for p in papers if p.get("relevance_label") == "core"][:6],
            "active_authors": authors[:6],
        }

    def get_field_papers(self, field_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        where, params = self._paper_where(field_id, filters)
        join_fts = ""
        rank_select = "0.0 AS rank"
        query = _fts_query(filters.get("search"))
        if query:
            join_fts = "JOIN paper_search_fts fts ON fts.paper_id = ap.id"
            where.append("paper_search_fts MATCH ?")
            params.append(query)
            rank_select = "bm25(paper_search_fts) AS rank"
        sort = filters.get("sort") or "newest"
        order = {
            "oldest": "ap.year ASC, ap.title ASC",
            "relevance": "rfp.relevance_score DESC, ap.year DESC",
            "citations": "ap.citation_count DESC, ap.year DESC",
            "search": "rank ASC, ap.year DESC",
        }.get(sort, "ap.year DESC, ap.publication_date DESC, ap.title ASC")
        if query and sort == "newest":
            order = "rank ASC, ap.year DESC"
        limit = _limit(filters.get("limit"), 50)
        offset = max(int(filters.get("offset") or 0), 0)
        sql_from = f"""
            FROM research_field_papers rfp
            JOIN academic_papers ap ON ap.id = rfp.paper_id
            LEFT JOIN venues v ON v.id = ap.venue_id
            {join_fts}
            WHERE {' AND '.join(where)}
        """
        total = self.conn.execute(f"SELECT COUNT(*) AS count {sql_from}", params).fetchone()["count"]
        rows = self.conn.execute(
            f"""
            SELECT ap.*, v.name AS venue, rfp.relevance_score, rfp.relevance_label,
                   rfp.relevance_evidence, {rank_select}
            {sql_from}
            ORDER BY {order}
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        return {"items": [self._paper_payload(row) for row in rows], "total": total}

    def get_field_authors(self, field_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        where, params = self._paper_scope_where(field_id, filters)
        author_where: list[str] = []
        search = str(filters.get("search") or "").strip()
        if search:
            author_where.append("a.normalized_name LIKE ?")
            params.append(f"%{normalize_title(search)}%")
        institution = str(filters.get("institution") or "").strip()
        if institution:
            author_where.append("COALESCE(i.name, '') LIKE ?")
            params.append(f"%{institution}%")
        min_papers = max(int(filters.get("minimum_papers") or 1), 1)
        limit = _limit(filters.get("limit"), 50)
        offset = max(int(filters.get("offset") or 0), 0)
        where_sql = " AND ".join([*where, *author_where])
        base = f"""
            FROM authors a
            JOIN paper_authors pa ON pa.author_id = a.id
            JOIN academic_papers ap ON ap.id = pa.paper_id
            JOIN research_field_papers rfp ON rfp.paper_id = ap.id
            LEFT JOIN institutions i ON i.id = a.primary_institution_id
            WHERE {where_sql}
            GROUP BY a.id
            HAVING COUNT(DISTINCT ap.id) >= ?
        """
        base_params = [*params, min_papers]
        total = len(self.conn.execute(f"SELECT a.id {base}", base_params).fetchall())
        rows = self.conn.execute(
            f"""
            SELECT a.id, a.name, a.openalex_id, a.works_count, a.citation_count,
                   i.name AS primary_institution,
                   COUNT(DISTINCT ap.id) AS field_paper_count,
                   MIN(ap.year) AS first_field_year,
                   MAX(ap.year) AS latest_field_year,
                   GROUP_CONCAT(DISTINCT ap.id) AS paper_ids
            {base}
            ORDER BY field_paper_count DESC, a.name ASC
            LIMIT ? OFFSET ?
            """,
            [*base_params, limit, offset],
        ).fetchall()
        return {"items": [self._author_payload(row) for row in rows], "total": total}

    def get_scholar_graph(self, field_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        authors = self.get_field_authors(field_id, {**filters, "limit": 10000, "offset": 0})["items"]
        max_nodes = filters.get("max_nodes")
        total_nodes = len(authors)
        if max_nodes != "all":
            authors = authors[: _limit(max_nodes, 500)]
        node_ids = {author["id"] for author in authors}
        papers = self._field_paper_ids(field_id, filters)
        edges: dict[tuple[str, str], dict[str, Any]] = {}
        for paper in papers:
            author_ids = [
                row["author_id"]
                for row in self.conn.execute(
                    "SELECT author_id FROM paper_authors WHERE paper_id = ? ORDER BY author_order, author_id",
                    (paper["paper_id"],),
                ).fetchall()
                if row["author_id"] in node_ids
            ]
            for index, author_a in enumerate(author_ids):
                for author_b in author_ids[index + 1 :]:
                    source, target = sorted((author_a, author_b))
                    edge = edges.setdefault(
                        (source, target),
                        {"source": source, "target": target, "shared_paper_ids": [], "first_year": paper["year"], "latest_year": paper["year"]},
                    )
                    edge["shared_paper_ids"].append(paper["paper_id"])
                    if paper["year"]:
                        edge["first_year"] = min(edge["first_year"] or paper["year"], paper["year"])
                        edge["latest_year"] = max(edge["latest_year"] or paper["year"], paper["year"])
        min_collab = max(int(filters.get("minimum_collaborations") or 1), 1)
        graph_edges = []
        for edge in edges.values():
            count = len(edge["shared_paper_ids"])
            if count >= min_collab:
                graph_edges.append({**edge, "field_collaboration_count": count})
        return {"nodes": authors, "edges": graph_edges, "total_nodes": total_nodes}

    def get_author_detail(self, field_id: str, author_id: str, filters: dict[str, Any] | None = None) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT a.id, a.name, a.openalex_id, a.works_count, a.citation_count,
                   i.name AS primary_institution
            FROM authors a
            LEFT JOIN institutions i ON i.id = a.primary_institution_id
            WHERE a.id = ?
            """,
            (author_id,),
        ).fetchone()
        if not row:
            return None
        papers = self.get_field_papers(field_id, {**(filters or {}), "author_id": author_id, "limit": 1000})["items"]
        graph = self.get_scholar_graph(field_id, {**(filters or {}), "max_nodes": "all"})
        collaborators = []
        for edge in graph["edges"]:
            if author_id not in (edge["source"], edge["target"]):
                continue
            other_id = edge["target"] if edge["source"] == author_id else edge["source"]
            other = self.conn.execute("SELECT name FROM authors WHERE id = ?", (other_id,)).fetchone()
            collaborators.append({"id": other_id, "name": other["name"] if other else other_id, "shared_paper_count": edge["field_collaboration_count"]})
        years = [paper["year"] for paper in papers if paper.get("year")]
        return {
            **_row_to_dict(row),
            "total_works": row["works_count"],
            "field_paper_count": len(papers),
            "first_field_year": min(years) if years else None,
            "latest_field_year": max(years) if years else None,
            "papers": papers,
            "collaborators": sorted(collaborators, key=lambda item: (-item["shared_paper_count"], item["name"])),
            "openalex_url": row["openalex_id"] or "",
        }

    def get_collaboration_detail(self, field_id: str, author_a: str, author_b: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        ids = sorted((author_a, author_b))
        authors = []
        for author_id in ids:
            row = self.conn.execute(
                """
                SELECT a.id, a.name, i.name AS primary_institution, a.citation_count
                FROM authors a
                LEFT JOIN institutions i ON i.id = a.primary_institution_id
                WHERE a.id = ?
                """,
                (author_id,),
            ).fetchone()
            authors.append(_row_to_dict(row) if row else {"id": author_id, "name": author_id})
        papers = [
            paper
            for paper in self.get_field_papers(field_id, {**(filters or {}), "limit": 1000})["items"]
            if all(any(author["id"] == wanted for author in paper["authors"]) for wanted in ids)
        ]
        years = [paper["year"] for paper in papers if paper.get("year")]
        return {
            "authors": authors,
            "shared_paper_count": len(papers),
            "first_year": min(years) if years else None,
            "latest_year": max(years) if years else None,
            "papers": papers,
            "note": "",
        }

    def search_papers(self, query: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        filters = filters or {}
        match = _fts_query(query)
        if not match:
            return {"items": [], "total": 0}
        where = ["paper_search_fts MATCH ?"]
        params: list[Any] = [match]
        if filters.get("year_from"):
            where.append("ap.year >= ?")
            params.append(int(filters["year_from"]))
        if filters.get("year_to"):
            where.append("ap.year <= ?")
            params.append(int(filters["year_to"]))
        limit = _limit(filters.get("limit"), 20)
        rows = self.conn.execute(
            f"""
            SELECT ap.*, v.name AS venue, bm25(paper_search_fts) AS rank
            FROM paper_search_fts
            JOIN academic_papers ap ON ap.id = paper_search_fts.paper_id
            LEFT JOIN venues v ON v.id = ap.venue_id
            WHERE {' AND '.join(where)}
            ORDER BY rank ASC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
        items = []
        for row in rows:
            payload = self._paper_payload(row, include_field=False)
            payload["field_associations"] = self._paper_fields(row["id"])
            payload["snippet"] = _snippet((row["abstract"] or row["title"] or ""), query)
            items.append(payload)
        return {"items": items, "total": len(items)}

    def search_authors(self, query: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        term = normalize_title(query)
        if not term:
            return {"items": [], "total": 0}
        limit = _limit((filters or {}).get("limit"), 20)
        rows = self.conn.execute(
            """
            SELECT a.id, a.name, a.openalex_id, a.works_count, a.citation_count,
                   i.name AS primary_institution,
                   COUNT(DISTINCT rfp.paper_id) AS field_paper_count
            FROM authors a
            LEFT JOIN institutions i ON i.id = a.primary_institution_id
            LEFT JOIN paper_authors pa ON pa.author_id = a.id
            LEFT JOIN research_field_papers rfp ON rfp.paper_id = pa.paper_id
            WHERE a.normalized_name LIKE ?
            GROUP BY a.id
            ORDER BY a.citation_count DESC NULLS LAST, a.name ASC
            LIMIT ?
            """,
            (f"%{term}%", limit),
        ).fetchall()
        return {"items": [_row_to_dict(row) for row in rows], "total": len(rows)}

    def _paper_where(self, field_id: str, filters: dict[str, Any]) -> tuple[list[str], list[Any]]:
        where, params = self._paper_scope_where(field_id, filters)
        if filters.get("venue"):
            where.append("COALESCE(v.name, '') LIKE ?")
            params.append(f"%{filters['venue']}%")
        if filters.get("author"):
            where.append(
                """
                EXISTS (
                  SELECT 1 FROM paper_authors pa2
                  JOIN authors a2 ON a2.id = pa2.author_id
                  WHERE pa2.paper_id = ap.id AND a2.normalized_name LIKE ?
                )
                """
            )
            params.append(f"%{normalize_title(filters['author'])}%")
        if filters.get("author_id"):
            where.append("EXISTS (SELECT 1 FROM paper_authors pa3 WHERE pa3.paper_id = ap.id AND pa3.author_id = ?)")
            params.append(filters["author_id"])
        if filters.get("relevance_label"):
            where.append("rfp.relevance_label = ?")
            params.append(filters["relevance_label"])
        if filters.get("minimum_relevance") not in (None, ""):
            where.append("rfp.relevance_score >= ?")
            params.append(float(filters["minimum_relevance"]))
        return where, params

    def _paper_scope_where(self, field_id: str, filters: dict[str, Any]) -> tuple[list[str], list[Any]]:
        where = ["rfp.research_field_id = ?"]
        params: list[Any] = [field_id]
        if filters.get("start_year"):
            where.append("ap.year >= ?")
            params.append(int(filters["start_year"]))
        if filters.get("end_year"):
            where.append("ap.year <= ?")
            params.append(int(filters["end_year"]))
        if filters.get("core_only") in (True, "1", "true", "True"):
            where.append("rfp.relevance_label = 'core'")
        return where, params

    def _field_paper_ids(self, field_id: str, filters: dict[str, Any] | None = None) -> list[sqlite3.Row]:
        where, params = self._paper_scope_where(field_id, filters or {})
        return self.conn.execute(
            f"""
            SELECT ap.id AS paper_id, ap.year, ap.publication_date
            FROM research_field_papers rfp
            JOIN academic_papers ap ON ap.id = rfp.paper_id
            WHERE {' AND '.join(where)}
            """,
            params,
        ).fetchall()

    def _paper_payload(self, row: sqlite3.Row, *, include_field: bool = True) -> dict[str, Any]:
        paper_id = row["id"]
        authors = [
            {
                "id": item["id"],
                "name": item["name"],
                "institution": item["primary_institution"],
                "author_order": item["author_order"],
            }
            for item in self.conn.execute(
                """
                SELECT a.id, a.name, i.name AS primary_institution, pa.author_order
                FROM paper_authors pa
                JOIN authors a ON a.id = pa.author_id
                LEFT JOIN institutions i ON i.id = pa.institution_id
                WHERE pa.paper_id = ?
                ORDER BY pa.author_order, a.name
                """,
                (paper_id,),
            ).fetchall()
        ]
        payload = {
            "id": paper_id,
            "title": row["title"],
            "abstract": row["abstract"],
            "year": row["year"],
            "publication_date": row["publication_date"],
            "venue": row["venue"],
            "citation_count": row["citation_count"],
            "openalex_id": row["openalex_id"],
            "doi": row["doi"],
            "external_url": row["url"],
            "pdf_url": row["pdf_url"],
            "authors": authors,
        }
        if include_field:
            payload.update(
                {
                    "relevance_score": row["relevance_score"],
                    "relevance_label": row["relevance_label"],
                    "relevance_evidence": _loads(row["relevance_evidence"], {}),
                }
            )
        if "rank" in row.keys():
            payload["score"] = row["rank"]
        return payload

    def _paper_fields(self, paper_id: str) -> list[dict[str, Any]]:
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "slug": row["slug"],
                "relevance_label": row["relevance_label"],
                "relevance_score": row["relevance_score"],
            }
            for row in self.conn.execute(
                """
                SELECT rf.id, rf.name, rf.slug, rfp.relevance_label, rfp.relevance_score
                FROM research_field_papers rfp
                JOIN research_fields rf ON rf.id = rfp.research_field_id
                WHERE rfp.paper_id = ?
                ORDER BY rf.name
                """,
                (paper_id,),
            ).fetchall()
        ]

    def _author_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "openalex_id": row["openalex_id"],
            "primary_institution": row["primary_institution"],
            "field_paper_count": row["field_paper_count"],
            "total_works": row["works_count"],
            "citation_count": row["citation_count"],
            "first_field_year": row["first_field_year"],
            "latest_field_year": row["latest_field_year"],
            "paper_ids": [item for item in str(row["paper_ids"] or "").split(",") if item],
        }

    def _field_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        data = _row_to_dict(row)
        for key in ("core_keywords", "optional_keywords", "excluded_keywords", "intent_queries", "seed_papers", "seed_authors"):
            data[key] = _loads(data.get(key), [])
        data["max_year"] = data.get("max_year") or datetime.now().year
        data["enabled"] = bool(data.get("enabled", 1))
        data["auto_sync"] = bool(data.get("auto_sync", 1))
        data["sync_frequency"] = data.get("sync_frequency") or "daily"
        return data

    def _find_identity(self, table: str, **identities: str | None) -> str | None:
        for key, value in identities.items():
            if not value:
                continue
            row = self.conn.execute(f"SELECT id FROM {table} WHERE {key} = ? LIMIT 1", (value,)).fetchone()
            if row:
                return row["id"]
        return None

    def _count(self, table: str) -> int:
        return int(self.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])

    def _new_collaborations(self, field_id: str, since: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT pa.author_id AS author_a_id, pb.author_id AS author_b_id,
                   aa.name AS author_a_name, ab.name AS author_b_name,
                   ap.id AS paper_id, ap.title AS first_shared_paper, ap.year,
                   MIN(rfp.first_discovered_at) AS first_seen
            FROM research_field_papers rfp
            JOIN academic_papers ap ON ap.id = rfp.paper_id
            JOIN paper_authors pa ON pa.paper_id = ap.id
            JOIN paper_authors pb ON pb.paper_id = ap.id AND pa.author_id < pb.author_id
            JOIN authors aa ON aa.id = pa.author_id
            JOIN authors ab ON ab.id = pb.author_id
            WHERE rfp.research_field_id = ?
            GROUP BY pa.author_id, pb.author_id
            HAVING datetime(MIN(rfp.first_discovered_at)) >= datetime(?)
            ORDER BY first_seen DESC
            LIMIT 12
            """,
            (field_id, since),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()} if row else {}


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bool(value: bool | None) -> int | None:
    return None if value is None else int(bool(value))


def _merge_evidence(existing: dict[str, Any], incoming: dict[str, Any] | None) -> dict[str, Any]:
    incoming = incoming or {}
    matched_lanes = list(dict.fromkeys([*(existing.get("matched_lanes") or []), *(incoming.get("matched_lanes") or [])]))
    return {**existing, **incoming, "matched_lanes": matched_lanes}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _slugify(value: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", str(value).casefold()).strip("-")
    return slug or "research-field"


def _unique_slug(conn: sqlite3.Connection, base: str) -> str:
    slug = base
    index = 2
    while conn.execute("SELECT 1 FROM research_fields WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base}-{index}"
        index += 1
    return slug


def _limit(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, 10000))


def _fts_query(value: Any) -> str:
    import re

    tokens = re.findall(r"[\w]+", str(value or "").casefold(), flags=re.UNICODE)
    tokens = [token for token in tokens if token.strip()]
    if not tokens:
        return ""
    return " AND ".join(f"{token}*" for token in tokens[:12])


def _sync_frequency(value: Any) -> str:
    text = str(value or "daily").strip().casefold()
    return text if text in {"hourly", "daily", "weekly"} else "daily"


def _frequency_seconds(value: Any) -> int:
    return {"hourly": 3600, "daily": 86400, "weekly": 604800}.get(_sync_frequency(value), 86400)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _start_of_today() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _snippet(text: str, query: str, *, radius: int = 120) -> str:
    if not text:
        return ""
    normalized = text.casefold()
    tokens = [token for token in str(query or "").casefold().split() if token]
    positions = [normalized.find(token) for token in tokens if normalized.find(token) >= 0]
    if not positions:
        return text[: radius * 2].strip()
    pos = min(positions)
    start = max(0, pos - radius)
    end = min(len(text), pos + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(text) else ""
    return (prefix + text[start:end].strip() + suffix).strip()
