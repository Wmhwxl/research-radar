import unittest

from src.research_radar.normalization import (
    normalize_arxiv_id,
    normalize_doi,
    normalize_openalex_id,
    normalize_openalex_work,
    normalize_title,
    reconstruct_openalex_abstract,
)


class ResearchRadarNormalizationTest(unittest.TestCase):
    def test_abstract_reconstruction(self):
        index = {"model": [1], "World": [0], "again": [3], "model": [1, 2]}
        self.assertEqual(reconstruct_openalex_abstract(index), "World model model again")

    def test_abstract_missing_values_are_safe(self):
        self.assertIsNone(reconstruct_openalex_abstract(None))
        self.assertIsNone(reconstruct_openalex_abstract({}))
        self.assertIsNone(reconstruct_openalex_abstract({"word": None}))

    def test_doi_normalization(self):
        cases = {
            "https://doi.org/10.xxxx/ABC": "10.xxxx/abc",
            "http://dx.doi.org/10.xxxx/ABC": "10.xxxx/abc",
            "doi:10.xxxx/ABC": "10.xxxx/abc",
            " 10.xxxx/ABC ": "10.xxxx/abc",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_doi(raw), expected)

    def test_arxiv_normalization(self):
        cases = {
            "2501.12345v1": "2501.12345",
            "2501.12345v2": "2501.12345",
            "https://arxiv.org/abs/2501.12345": "2501.12345",
            "https://arxiv.org/pdf/2501.12345.pdf": "2501.12345",
            "arXiv:2501.12345v3": "2501.12345",
            "https://arxiv.org/abs/cs.LG/9901001v2": "cs.lg/9901001",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_arxiv_id(raw), expected)
        self.assertIsNone(normalize_arxiv_id("hello"))

    def test_openalex_id_normalization(self):
        self.assertEqual(normalize_openalex_id("W123", expected_prefix="W"), "https://openalex.org/W123")
        self.assertEqual(
            normalize_openalex_id("https://openalex.org/A456", expected_prefix="A"),
            "https://openalex.org/A456",
        )
        self.assertIsNone(normalize_openalex_id("W123", expected_prefix="A"))
        self.assertIsNone(normalize_openalex_id("garbage", expected_prefix="W"))
        self.assertIsNone(normalize_openalex_id("", expected_prefix="W"))
        self.assertIsNone(normalize_openalex_id("https://example.org/W123", expected_prefix="W"))
        self.assertIsNone(normalize_openalex_id("https://openalex.org/not-an-id", expected_prefix="W"))

    def test_title_normalization(self):
        self.assertEqual(normalize_title("  Multi-Modal: Recommendation! "), "multi modal recommendation")
        self.assertEqual(normalize_title("Ａ ＆ B"), "a and b")

    def test_work_parses_venue_authors_institutions_and_topics(self):
        paper = normalize_openalex_work(
            {
                "id": "https://openalex.org/W1",
                "title": "Robust Multimodal Recommendation",
                "abstract_inverted_index": {"Robust": [0], "recommendation": [2], "multimodal": [1]},
                "doi": "https://doi.org/10.1234/ABC",
                "ids": {"arxiv": "https://arxiv.org/abs/2501.12345v2", "pmid": "123"},
                "publication_date": "2026-01-02",
                "publication_year": 2026,
                "type": "article",
                "cited_by_count": 7,
                "primary_location": {
                    "landing_page_url": "https://example.org/work",
                    "pdf_url": "https://example.org/work.pdf",
                    "source": {
                        "id": "https://openalex.org/S1",
                        "display_name": "Journal of Recsys",
                        "type": "journal",
                        "issn": ["1234-5678"],
                        "publisher": "ACM",
                        "homepage_url": "https://journal.example",
                        "host_organization": "https://openalex.org/P1",
                    },
                },
                "authorships": [
                    {
                        "author_position": "first",
                        "is_corresponding": True,
                        "raw_author_name": "A. Researcher",
                        "raw_affiliation_strings": ["Lab One", "Lab Two"],
                        "author": {
                            "id": "https://openalex.org/A1",
                            "display_name": "Ada Researcher",
                            "orcid": "https://orcid.org/0000-0000-0000-0001",
                        },
                        "institutions": [
                            {
                                "id": "https://openalex.org/I1",
                                "display_name": "University One",
                                "country_code": "US",
                                "ror": "https://ror.org/abc",
                                "type": "education",
                            },
                            {
                                "id": "https://openalex.org/I2",
                                "display_name": "Institute Two",
                                "country_code": "GB",
                            },
                        ],
                    }
                ],
                "topics": [{"id": "https://openalex.org/T1", "display_name": "Recommender Systems", "score": 0.93}],
            }
        )
        self.assertEqual(paper.openalex_id, "https://openalex.org/W1")
        self.assertEqual(paper.abstract, "Robust multimodal recommendation")
        self.assertEqual(paper.doi, "10.1234/abc")
        self.assertEqual(paper.arxiv_id, "2501.12345")
        self.assertEqual(paper.venue.name, "Journal of Recsys")
        self.assertEqual(paper.authorships[0].author.openalex_id, "https://openalex.org/A1")
        self.assertTrue(paper.authorships[0].is_corresponding)
        self.assertEqual(len(paper.authorships[0].institutions), 2)
        self.assertEqual(paper.topics[0].name, "Recommender Systems")

    def test_authorship_preserves_false_corresponding_flag(self):
        paper = normalize_openalex_work(
            {
                "id": "https://openalex.org/W3",
                "title": "Corresponding Flag",
                "authorships": [
                    {
                        "author": {"id": "https://openalex.org/A3", "display_name": "False Flag"},
                        "is_corresponding": False,
                    }
                ],
            }
        )
        self.assertFalse(paper.authorships[0].is_corresponding)

    def test_missing_optional_fields_are_safe(self):
        paper = normalize_openalex_work(
            {
                "id": "https://openalex.org/W2",
                "title": "Untitled Fields",
                "primary_location": None,
                "authorships": None,
                "abstract_inverted_index": None,
            }
        )
        self.assertIsNone(paper.venue)
        self.assertEqual(paper.authorships, [])
        self.assertIsNone(paper.abstract)


if __name__ == "__main__":
    unittest.main()
