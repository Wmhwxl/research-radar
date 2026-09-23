import unittest

from src.research_radar.field_seed import demo_research_field
from src.research_radar.models import (
    CandidatePaper,
    NormalizedAuthor,
    NormalizedAuthorship,
    NormalizedInstitution,
    NormalizedPaper,
    RelevanceDecision,
)
from src.research_radar.repository import InMemoryResearchRadarRepository


class ResearchRadarRepositoryTest(unittest.TestCase):
    def test_idempotent_upsert_and_multi_institution(self):
        repo = InMemoryResearchRadarRepository()
        field = demo_research_field()
        field_id = repo.upsert_research_field(field)
        paper = NormalizedPaper(
            openalex_id="https://openalex.org/W1",
            title="Missing Modality Completion for Multimodal Recommendation",
            normalized_title="missing modality completion for multimodal recommendation",
            year=2026,
            authorships=[
                NormalizedAuthorship(
                    author=NormalizedAuthor(openalex_id="https://openalex.org/A1", name="Ada"),
                    author_position="first",
                    author_order=1,
                    raw_affiliation_strings=["University One; Institute Two"],
                    institutions=[
                        NormalizedInstitution(openalex_id="https://openalex.org/I1", name="University One"),
                        NormalizedInstitution(openalex_id="https://openalex.org/I2", name="Institute Two"),
                    ],
                )
            ],
        )
        candidate = CandidatePaper(paper=paper, matched_lanes=["broad_missing"], matched_queries=["q"], retrieval_count=1)
        decision = RelevanceDecision(score=0.9, label="core", accepted=True, evidence={"matched_lanes": ["broad_missing"]})
        repo.upsert_accepted_paper(field_id, candidate, decision)
        repo.upsert_accepted_paper(field_id, candidate, decision)
        self.assertEqual(len(repo.papers), 1)
        self.assertEqual(len(repo.authors), 1)
        self.assertEqual(len(repo.paper_authors), 1)
        self.assertEqual(len(repo.paper_author_institutions), 2)
        self.assertEqual(len(repo.research_field_papers), 1)


if __name__ == "__main__":
    unittest.main()

