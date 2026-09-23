from src.research_radar.field_seed import demo_research_field
from src.research_radar.models import (
    CandidatePaper,
    NormalizedAuthor,
    NormalizedAuthorship,
    NormalizedInstitution,
    NormalizedPaper,
    NormalizedVenue,
    RelevanceDecision,
)
from src.research_radar.sqlite_repository import SQLiteResearchRadarRepository
from src.providers.base import ProviderPage
from src.research_radar.sync_field_history import sync_field_history


def _paper(work_id="W1", *, title="Missing Modality Completion for Multimodal Recommendation"):
    suffix = "".join(ch for ch in work_id if ch.isdigit()) or "1"
    return NormalizedPaper(
        openalex_id=f"https://openalex.org/{work_id}",
        title=title,
        normalized_title=title.casefold(),
        abstract="A robust multimodal recommender handles incomplete visual and textual modalities.",
        doi=f"10.1234/demo.{suffix}",
        arxiv_id=f"2601.{int(suffix):05d}",
        year=2026,
        venue=NormalizedVenue(openalex_id="https://openalex.org/S1", name="Demo Venue"),
        authorships=[
            NormalizedAuthorship(
                author=NormalizedAuthor(openalex_id="https://openalex.org/A1", name="Ada Lovelace"),
                author_position="first",
                author_order=1,
                institutions=[
                    NormalizedInstitution(openalex_id="https://openalex.org/I1", name="University One"),
                    NormalizedInstitution(openalex_id="https://openalex.org/I2", name="Institute Two"),
                ],
            ),
            NormalizedAuthorship(
                author=NormalizedAuthor(openalex_id="https://openalex.org/A2", name="Bo Zhang"),
                author_position="middle",
                author_order=2,
            ),
            NormalizedAuthorship(
                author=NormalizedAuthor(openalex_id="https://openalex.org/A3", name="Cora Smith"),
                author_position="last",
                author_order=3,
            ),
        ],
    )


def test_sqlite_repository_idempotency_multi_institution_collaboration_and_fts(tmp_path):
    repo = SQLiteResearchRadarRepository(tmp_path / "rr.db")
    try:
        field_id = repo.upsert_research_field(demo_research_field())
        candidate = CandidatePaper(paper=_paper(), matched_lanes=["lane-a"], matched_queries=["q"], retrieval_count=1)
        decision = RelevanceDecision(score=0.91, label="core", accepted=True, evidence={"matched_lanes": ["lane-a"]})
        repo.upsert_accepted_paper(field_id, candidate, decision)
        repo.upsert_accepted_paper(field_id, candidate, decision)

        counts = {
            table: repo.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "academic_papers",
                "authors",
                "institutions",
                "venues",
                "paper_authors",
                "paper_author_institutions",
                "research_field_papers",
            )
        }
        assert counts == {
            "academic_papers": 1,
            "authors": 3,
            "institutions": 2,
            "venues": 1,
            "paper_authors": 3,
            "paper_author_institutions": 2,
            "research_field_papers": 1,
        }

        assert repo.rebuild_collaborations(field_id) == 3
        assert repo.rebuild_collaborations(field_id) == 3
        assert repo.conn.execute("SELECT SUM(field_collaboration_count) FROM author_collaborations").fetchone()[0] == 3

        papers = repo.get_field_papers(field_id, {"search": "modality", "limit": 10})
        assert papers["total"] == 1
        assert papers["items"][0]["authors"][0]["name"] == "Ada Lovelace"

        search = repo.search_papers("Ada multimodal", {"limit": 10})
        assert search["total"] == 1
    finally:
        repo.close()


def test_sqlite_repository_decodes_research_field_json_for_query_builder(tmp_path):
    repo = SQLiteResearchRadarRepository(tmp_path / "rr.db")
    try:
        field_id = repo.upsert_research_field(demo_research_field())
        field = repo.get_research_field(field_id=field_id)
        assert field.core_keywords[0] == "multimodal recommendation"
        assert field.keyword_groups["recommendation"][0] == "recommendation"
        assert field.intent_queries[0].startswith("papers studying")
    finally:
        repo.close()


class _FakeProvider:
    name = "openalex"

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def search_works(self, **kwargs):
        self.calls.append(kwargs)
        return self.pages[kwargs["cursor"]]


def test_sqlite_checkpoint_resume_replays_failed_cursor_without_duplicates(tmp_path):
    repo = SQLiteResearchRadarRepository(tmp_path / "rr.db")
    try:
        field_id = repo.upsert_research_field(demo_research_field())
        field = repo.get_research_field(field_id=field_id)
        provider = _FakeProvider(
            {
                "*": ProviderPage([_paper("W1")], "cursor-2", 2, 100, "openalex"),
                "cursor-2": ProviderPage([_paper("W2", title="Missing Modality Completion for Multimodal Recommendation Two")], None, 2, 100, "openalex"),
            }
        )
        try:
            sync_field_history(
                field=field,
                provider=provider,
                repository=repo,
                from_date="2020-01-01",
                to_date="2024-01-01",
                max_pages=2,
                test_fail_before_checkpoint_on_page=2,
            )
        except RuntimeError:
            pass
        run_id = repo.conn.execute("SELECT id FROM research_field_sync_runs LIMIT 1").fetchone()[0]
        checkpoint = repo.get_sync_run(run_id)["checkpoint"]
        assert checkpoint["cursor"] == "cursor-2"

        resumed = _FakeProvider({"cursor-2": provider.pages["cursor-2"]})
        sync_field_history(
            field=field,
            provider=resumed,
            repository=repo,
            from_date="2020-01-01",
            to_date="2024-01-01",
            max_pages=1,
            resume_run_id=run_id,
        )
        assert resumed.calls[0]["cursor"] == "cursor-2"
        assert repo.conn.execute("SELECT COUNT(*) FROM academic_papers").fetchone()[0] == 2
    finally:
        repo.close()
