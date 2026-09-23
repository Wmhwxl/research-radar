import unittest

from src.research_radar.field_seed import demo_research_field
from src.research_radar.models import CandidatePaper, NormalizedPaper, ResearchField
from src.research_radar.query_builder import build_query_lanes
from src.research_radar.relevance import CORE, REJECTED, RELATED, evaluate_candidate


def paper(title, abstract="", year=2026):
    return NormalizedPaper(
        openalex_id=f"https://openalex.org/W{abs(hash(title)) % 100000}",
        title=title,
        normalized_title=title.casefold(),
        abstract=abstract,
        year=year,
    )


class ResearchRadarRelevanceTest(unittest.TestCase):
    def setUp(self):
        self.field = demo_research_field()
        self.lanes = build_query_lanes(self.field)

    def decision(self, title, abstract="", lanes=None):
        candidate = CandidatePaper(
            paper=paper(title, abstract),
            matched_lanes=lanes or ["broad_missing"],
            matched_queries=["query"],
            retrieval_count=1,
        )
        return evaluate_candidate(candidate, self.field, self.lanes)

    def test_positive_core(self):
        decision = self.decision(
            "Missing Modality Completion for Multimodal Recommendation",
            "We study recommender systems with incomplete visual and textual modalities and perform imputation.",
            lanes=["exact_1", "broad_missing"],
        )
        self.assertEqual(decision.label, CORE)
        self.assertTrue(decision.accepted)
        self.assertIn("missingness_or_recovery_signal", decision.reason_codes)

    def test_negative_medical_classification(self):
        decision = self.decision(
            "Missing Modalities in Medical Image Classification",
            "A multimodal medical classifier handles missing MRI and image inputs.",
        )
        self.assertEqual(decision.label, REJECTED)
        self.assertFalse(decision.accepted)

    def test_borderline_related_complete_modalities(self):
        decision = self.decision(
            "Multimodal Recommendation with Complete Modalities",
            "A recommender system using visual and textual features under complete modalities.",
            lanes=["broad_recovery"],
        )
        self.assertEqual(decision.label, RELATED)
        self.assertTrue(decision.accepted)

    def test_robust_without_missingness_is_related_not_core(self):
        decision = self.decision(
            "Robust Multimodal Recommendation with Visual Features",
            "A recommender system improves robust multimodal representation learning.",
            lanes=["broad_recovery"],
        )
        self.assertEqual(decision.label, RELATED)

    def test_generic_field_accepts_field_name_match(self):
        field = ResearchField(id="field-1", slug="multimodal", name="Multimodal")
        lanes = build_query_lanes(field)
        decision = evaluate_candidate(
            CandidatePaper(
                paper=paper("Multimodal Representation Learning for Retrieval", "A survey of multimodal models."),
                matched_lanes=["generic_1"],
                matched_queries=["Multimodal"],
                retrieval_count=1,
            ),
            field,
            lanes,
        )
        self.assertEqual(decision.label, RELATED)
        self.assertIn("generic_field_match", decision.reason_codes)


if __name__ == "__main__":
    unittest.main()
