import unittest

from src.research_radar.dedupe import CandidateAggregator, primary_identity_key
from src.research_radar.models import NormalizedPaper


def paper(**kwargs):
    data = {
        "openalex_id": None,
        "title": "A Paper",
        "normalized_title": "a paper",
        "doi": None,
        "arxiv_id": None,
        "year": 2026,
    }
    data.update(kwargs)
    return NormalizedPaper(**data)


class ResearchRadarDedupeTest(unittest.TestCase):
    def test_identity_priority(self):
        identity = primary_identity_key(paper(openalex_id="https://openalex.org/W1", doi="10/x", arxiv_id="2501.1"))
        self.assertEqual(identity.key_type, "openalex_id")

    def test_same_openalex_id_aggregates(self):
        agg = CandidateAggregator()
        agg.add(paper(openalex_id="https://openalex.org/W1"), lane_id="a", query="qa")
        agg.add(paper(openalex_id="https://openalex.org/W1"), lane_id="b", query="qb")
        self.assertEqual(len(agg.values()), 1)
        self.assertEqual(agg.values()[0].matched_lanes, ["a", "b"])

    def test_same_doi_different_openalex_record_aggregates(self):
        agg = CandidateAggregator()
        agg.add(paper(openalex_id="https://openalex.org/W1", doi="10.1/a"), lane_id="a", query="qa")
        agg.add(paper(openalex_id="https://openalex.org/W2", doi="10.1/a"), lane_id="b", query="qb")
        self.assertEqual(len(agg.values()), 1)

    def test_same_arxiv_version_aggregates(self):
        agg = CandidateAggregator()
        agg.add(paper(arxiv_id="2501.12345"), lane_id="a", query="qa")
        agg.add(paper(arxiv_id="2501.12345"), lane_id="b", query="qb")
        self.assertEqual(len(agg.values()), 1)

    def test_title_year_fallback_is_exact_and_conservative(self):
        agg = CandidateAggregator()
        agg.add(paper(title="Same Title", normalized_title="same title", year=2026), lane_id="a", query="qa")
        agg.add(paper(title="Same Title", normalized_title="same title", year=2026), lane_id="b", query="qb")
        agg.add(paper(title="Same Title", normalized_title="same title", year=2025), lane_id="c", query="qc")
        agg.add(paper(title="Same Title Extended", normalized_title="same title extended", year=2026), lane_id="d", query="qd")
        self.assertEqual(len(agg.values()), 3)


if __name__ == "__main__":
    unittest.main()

