import unittest

from src.providers.base import ProviderPage
from src.research_radar.field_seed import demo_research_field
from src.research_radar.models import NormalizedPaper
from src.research_radar.repository import InMemoryResearchRadarRepository
from src.research_radar.sync_field_history import sync_field_history


def positive_paper(work_id):
    return NormalizedPaper(
        openalex_id=f"https://openalex.org/{work_id}",
        title=f"Missing Modality Completion for Multimodal Recommendation {work_id}",
        normalized_title=f"missing modality completion for multimodal recommendation {work_id.casefold()}",
        abstract="A recommender system for incomplete multimodal visual and textual modalities using imputation.",
        year=2026,
    )


class FakeProvider:
    name = "openalex"

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def search_works(self, **kwargs):
        self.calls.append(kwargs)
        cursor = kwargs["cursor"]
        return self.pages[cursor]


class FailingRepo(InMemoryResearchRadarRepository):
    def __init__(self):
        super().__init__()
        self.fail_on_work_id = "https://openalex.org/W2"

    def upsert_accepted_paper(self, field_id, candidate, decision):
        if candidate.paper.openalex_id == self.fail_on_work_id:
            raise RuntimeError("simulated db failure")
        return super().upsert_accepted_paper(field_id, candidate, decision)


class CountingRepo(InMemoryResearchRadarRepository):
    def __init__(self):
        super().__init__()
        self.accepted_upserts = 0

    def upsert_accepted_paper(self, field_id, candidate, decision):
        self.accepted_upserts += 1
        return super().upsert_accepted_paper(field_id, candidate, decision)


class ResearchRadarSyncTest(unittest.TestCase):
    def test_same_page_identity_duplicate_is_written_once(self):
        repo = CountingRepo()
        field_id = repo.upsert_research_field(demo_research_field())
        field = repo.get_research_field(field_id=field_id)
        duplicate = positive_paper("W1")
        provider = FakeProvider({"*": ProviderPage([duplicate, duplicate], None, 2, 100, "openalex")})

        sync_field_history(
            field=field,
            provider=provider,
            repository=repo,
            from_date="2025-01-01",
            to_date="2026-01-01",
            max_pages=1,
        )

        self.assertEqual(repo.accepted_upserts, 1)
        self.assertEqual(len(repo.papers), 1)

    def test_dry_run_counts_without_database_writes(self):
        field = demo_research_field()
        provider = FakeProvider(
            {
                "*": ProviderPage([positive_paper("W1")], None, 1, 100, "openalex"),
            }
        )
        summary = sync_field_history(
            field=field,
            provider=provider,
            repository=None,
            from_date="2025-01-01",
            to_date="2026-01-01",
            max_pages=1,
            dry_run=True,
        )
        self.assertEqual(summary["counters"]["candidates_retrieved"], 1)
        self.assertEqual(summary["counters"]["accepted_core"], 1)
        self.assertEqual(summary["counters"]["papers_written"], 0)

    def test_resume_keeps_checkpoint_on_failed_page_and_replays_it(self):
        repo = FailingRepo()
        field = demo_research_field()
        field_id = repo.upsert_research_field(field)
        field = repo.get_research_field(field_slug=field.slug)
        provider = FakeProvider(
            {
                "*": ProviderPage([positive_paper("W1")], "cursor-2", 2, 100, "openalex"),
                "cursor-2": ProviderPage([positive_paper("W2")], None, 2, 100, "openalex"),
            }
        )
        with self.assertRaises(RuntimeError):
            sync_field_history(
                field=field,
                provider=provider,
                repository=repo,
                from_date="2025-01-01",
                to_date="2026-01-01",
                max_pages=2,
            )
        run_id = next(iter(repo.sync_runs))
        self.assertEqual(repo.sync_runs[run_id]["checkpoint"]["cursor"], "cursor-2")
        repo.fail_on_work_id = None
        provider2 = FakeProvider(
            {
                "cursor-2": ProviderPage([positive_paper("W2")], None, 2, 100, "openalex"),
            }
        )
        sync_field_history(
            field=field,
            provider=provider2,
            repository=repo,
            from_date="2025-01-01",
            to_date="2026-01-01",
            max_pages=1,
            resume_run_id=run_id,
        )
        self.assertEqual(provider2.calls[0]["cursor"], "cursor-2")
        self.assertEqual(len(repo.papers), 2)

    def test_controlled_failure_after_writes_replays_page_idempotently(self):
        repo = InMemoryResearchRadarRepository()
        field_id = repo.upsert_research_field(demo_research_field())
        field = repo.get_research_field(field_id=field_id)
        provider = FakeProvider(
            {
                "*": ProviderPage([positive_paper("W1")], "cursor-2", 2, 100, "openalex"),
                "cursor-2": ProviderPage([positive_paper("W2")], None, 2, 100, "openalex"),
            }
        )

        with self.assertRaisesRegex(RuntimeError, "controlled failure"):
            sync_field_history(
                field=field,
                provider=provider,
                repository=repo,
                from_date="2025-01-01",
                to_date="2026-01-01",
                max_pages=2,
                test_fail_before_checkpoint_on_page=2,
            )

        run_id = next(iter(repo.sync_runs))
        self.assertEqual(repo.sync_runs[run_id]["checkpoint"]["cursor"], "cursor-2")
        self.assertEqual(len(repo.papers), 2)
        resumed_provider = FakeProvider(
            {"cursor-2": ProviderPage([positive_paper("W2")], None, 2, 100, "openalex")}
        )
        sync_field_history(
            field=field,
            provider=resumed_provider,
            repository=repo,
            from_date="2025-01-01",
            to_date="2026-01-01",
            max_pages=1,
            resume_run_id=run_id,
        )
        self.assertEqual(resumed_provider.calls[0]["cursor"], "cursor-2")
        self.assertEqual(len(repo.papers), 2)


if __name__ == "__main__":
    unittest.main()
