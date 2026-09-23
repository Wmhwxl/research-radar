import unittest
from unittest.mock import Mock

import requests

from src.providers.base import ProviderParseError, ProviderRateLimitError, ProviderRequestError
from src.providers.openalex import OpenAlexProvider


def work(**overrides):
    payload = {
        "id": "https://openalex.org/W1",
        "title": "Multimodal Recommendation",
        "abstract_inverted_index": {"test": [0]},
        "publication_date": "2026-01-01",
        "publication_year": 2026,
        "authorships": [],
        "primary_location": None,
    }
    payload.update(overrides)
    return payload


class FakeResponse:
    def __init__(self, status_code=200, data=None, headers=None, json_error=None):
        self.status_code = status_code
        self._data = data
        self.headers = headers or {}
        self._json_error = json_error
        self.text = ""

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._data


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def page_response(results=None, next_cursor="next", count=1, headers=None):
    return FakeResponse(
        data={"meta": {"count": count, "per_page": 100, "next_cursor": next_cursor, "cost_usd": 0.001}, "results": results or []},
        headers=headers,
    )


class ResearchRadarOpenAlexProviderTest(unittest.TestCase):
    """Mocked tests for the 2026 OpenAlex API contract: per_page<=100, cursor=*, meta.next_cursor."""

    def make_provider(self, responses, **kwargs):
        sleep = kwargs.pop("sleep", Mock())
        return OpenAlexProvider(
            session=FakeSession(responses),
            sleep=sleep,
            timeout_seconds=12,
            max_retries=kwargs.pop("max_retries", 2),
            **kwargs,
        )

    def test_basic_works_response_and_cursor_metadata(self):
        provider = self.make_provider([page_response([work()], next_cursor="cursor-two", headers={"X-RateLimit-Remaining": "99"})])
        page = provider.search_works(
            query='"multimodal recommendation"',
            from_publication_date="2025-01-01",
            to_publication_date="2026-01-01",
        )
        self.assertEqual(page.provider, "openalex")
        self.assertEqual(page.next_cursor, "cursor-two")
        self.assertEqual(page.total_count, 1)
        self.assertEqual(page.items[0].title, "Multimodal Recommendation")
        self.assertEqual(page.rate_metadata["remaining"], "99")

    def test_no_next_cursor_and_empty_results(self):
        provider = self.make_provider([page_response([], next_cursor=None, count=0)])
        page = provider.search_works(
            query="nothing",
            from_publication_date="2026-01-01",
            to_publication_date="2026-01-02",
        )
        self.assertEqual(page.items, [])
        self.assertIsNone(page.next_cursor)

    def test_per_page_contract(self):
        provider = self.make_provider([])
        with self.assertRaises(ValueError):
            provider.search_works(
                query="x",
                from_publication_date="2026-01-01",
                to_publication_date="2026-01-02",
                per_page=101,
            )
        with self.assertRaises(ValueError):
            provider.search_works(
                query="x",
                from_publication_date="2026-01-01",
                to_publication_date="2026-01-02",
                per_page=0,
            )

    def test_date_filters_type_cursor_and_boolean_query_forwarding(self):
        provider = self.make_provider([page_response([work()])])
        provider.search_works(
            query='("multimodal recommendation" OR "multimodal recommender") AND (missing OR incomplete)',
            from_publication_date="2025-09-21",
            to_publication_date="2026-09-21",
            cursor="abc",
            per_page=50,
            work_type="article",
        )
        call = provider.session.calls[0]
        self.assertEqual(call["params"]["search"], '("multimodal recommendation" OR "multimodal recommender") AND (missing OR incomplete)')
        self.assertEqual(call["params"]["cursor"], "abc")
        self.assertEqual(call["params"]["per_page"], 50)
        self.assertIn("from_publication_date:2025-09-21", call["params"]["filter"])
        self.assertIn("to_publication_date:2026-09-21", call["params"]["filter"])
        self.assertIn("type:article", call["params"]["filter"])
        self.assertIn("select", call["params"])

    def test_api_key_forwarding_and_safe_metadata(self):
        provider = self.make_provider([page_response([work()])], api_key="secret-key")
        page = provider.search_works(
            query="x",
            from_publication_date="2026-01-01",
            to_publication_date="2026-01-02",
        )
        self.assertEqual(provider.session.calls[0]["params"]["api_key"], "secret-key")
        self.assertTrue(page.request_metadata["has_api_key"])
        self.assertNotIn("api_key", page.request_metadata["params"])

    def test_no_api_key(self):
        provider = self.make_provider([page_response([work()])], api_key="")
        provider.search_works(
            query="x",
            from_publication_date="2026-01-01",
            to_publication_date="2026-01-02",
        )
        self.assertNotIn("api_key", provider.session.calls[0]["params"])

    def test_429_retry_honors_retry_after(self):
        sleep = Mock()
        provider = self.make_provider(
            [FakeResponse(429, headers={"Retry-After": "0"}), page_response([work()])],
            sleep=sleep,
        )
        page = provider.search_works(
            query="x",
            from_publication_date="2026-01-01",
            to_publication_date="2026-01-02",
        )
        self.assertEqual(len(provider.session.calls), 2)
        sleep.assert_called_once_with(0.0)
        self.assertEqual(len(page.items), 1)

    def test_429_after_retries_raises_rate_limit_error(self):
        provider = self.make_provider([FakeResponse(429), FakeResponse(429)], max_retries=1)
        with self.assertRaises(ProviderRateLimitError):
            provider.search_works(query="x", from_publication_date="2026-01-01", to_publication_date="2026-01-02")

    def test_5xx_retry(self):
        provider = self.make_provider([FakeResponse(503), page_response([work()])])
        page = provider.search_works(query="x", from_publication_date="2026-01-01", to_publication_date="2026-01-02")
        self.assertEqual(len(provider.session.calls), 2)
        self.assertEqual(len(page.items), 1)

    def test_400_no_retry(self):
        provider = self.make_provider([FakeResponse(400)])
        with self.assertRaises(ProviderRequestError):
            provider.search_works(query="x", from_publication_date="2026-01-01", to_publication_date="2026-01-02")
        self.assertEqual(len(provider.session.calls), 1)

    def test_timeout_retry(self):
        provider = self.make_provider([requests.exceptions.Timeout("timeout"), page_response([work()])])
        page = provider.search_works(query="x", from_publication_date="2026-01-01", to_publication_date="2026-01-02")
        self.assertEqual(len(provider.session.calls), 2)
        self.assertEqual(len(page.items), 1)

    def test_malformed_response(self):
        provider = self.make_provider([FakeResponse(data={"meta": {}})])
        with self.assertRaises(ProviderParseError):
            provider.search_works(query="x", from_publication_date="2026-01-01", to_publication_date="2026-01-02")
        provider = self.make_provider([FakeResponse(data={"meta": {}, "results": []}, json_error=ValueError("bad"))])
        with self.assertRaises(ProviderParseError):
            provider.search_works(query="x", from_publication_date="2026-01-01", to_publication_date="2026-01-02")

    def test_null_primary_location_authorships_and_abstract(self):
        provider = self.make_provider([page_response([work(primary_location=None, authorships=None, abstract_inverted_index=None)])])
        page = provider.search_works(query="x", from_publication_date="2026-01-01", to_publication_date="2026-01-02")
        self.assertIsNone(page.items[0].venue)
        self.assertEqual(page.items[0].authorships, [])
        self.assertIsNone(page.items[0].abstract)

    def test_batch_get_authors_uses_one_or_filter(self):
        provider = self.make_provider(
            [
                FakeResponse(
                    data={
                        "meta": {"count": 2, "per_page": 2, "next_cursor": None},
                        "results": [
                            {"id": "https://openalex.org/A1", "display_name": "Ada", "works_count": 3, "cited_by_count": 5},
                            {"id": "https://openalex.org/A2", "display_name": "Grace", "works_count": 4, "cited_by_count": 6},
                        ],
                    }
                )
            ]
        )
        page = provider.batch_get_authors(["A1", "https://openalex.org/A2", "A1"])
        self.assertEqual(len(provider.session.calls), 1)
        self.assertEqual(provider.session.calls[0]["params"]["filter"], "openalex:A1|A2")
        self.assertEqual([author.name for author in page.items], ["Ada", "Grace"])


if __name__ == "__main__":
    unittest.main()
