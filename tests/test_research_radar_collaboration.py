import unittest

from src.research_radar.collaboration import rebuild_author_collaborations
from src.research_radar.field_seed import demo_research_field
from src.research_radar.models import CandidatePaper, NormalizedAuthor, NormalizedAuthorship, NormalizedPaper, RelevanceDecision
from src.research_radar.repository import InMemoryResearchRadarRepository


class ResearchRadarCollaborationTest(unittest.TestCase):
    def test_rebuild_collaboration_pairs(self):
        repo = InMemoryResearchRadarRepository()
        field_id = repo.upsert_research_field(demo_research_field())
        paper = NormalizedPaper(
            openalex_id="https://openalex.org/W10",
            title="Team Paper",
            normalized_title="team paper",
            year=2026,
            publication_date="2026-01-01",
            authorships=[
                NormalizedAuthorship(NormalizedAuthor("https://openalex.org/A1", "A"), None, 1),
                NormalizedAuthorship(NormalizedAuthor("https://openalex.org/A2", "B"), None, 2),
                NormalizedAuthorship(NormalizedAuthor("https://openalex.org/A3", "C"), None, 3),
            ],
        )
        decision = RelevanceDecision(0.9, "core", True, {"matched_lanes": ["x"]})
        repo.upsert_accepted_paper(field_id, CandidatePaper(paper), decision)
        self.assertEqual(rebuild_author_collaborations(repo, field_id), 3)
        self.assertEqual(len(repo.author_collaborations), 3)
        self.assertTrue(all(row["field_collaboration_count"] == 1 for row in repo.author_collaborations.values()))


if __name__ == "__main__":
    unittest.main()

