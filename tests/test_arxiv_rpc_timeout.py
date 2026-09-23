"""客户端需等到函数预算结束，同时尊重调用方显式超时。"""

import unittest
from unittest.mock import Mock, patch
from src import supabase_source as source


class RpcTimeoutTests(unittest.TestCase):
    def call_rpc(self, lane, rpc, **kwargs):
        response = Mock(status_code=200)
        response.json.return_value = []
        with patch.object(
            source, "_request_with_retries", return_value=response
        ) as request:
            common = dict(
                url="https://example.invalid",
                api_key="test",
                rpc_name=rpc,
                match_count=20,
            )
            if lane == "exact":
                source.match_papers_by_embedding(
                    **common, query_embedding=[0.1] * 384, **kwargs
                )
            else:
                source.match_papers_by_bm25(**common, query_text="ATSP", **kwargs)
            return request.call_args.kwargs["timeout"]

    def test_arxiv_function_budgets_have_http_margin(self):
        self.assertEqual(self.call_rpc("exact", "match_arxiv_papers_exact"), 75)
        self.assertEqual(self.call_rpc("bm25", "match_arxiv_papers_bm25"), 45)

    def test_explicit_timeout_and_other_sources_are_unchanged(self):
        self.assertEqual(
            self.call_rpc("exact", "match_arxiv_papers_exact", timeout=7), 7
        )
        self.assertEqual(self.call_rpc("bm25", "match_arxiv_papers_bm25", timeout=9), 9)
        self.assertEqual(self.call_rpc("exact", "match_eccv_papers_exact"), 20)
        self.assertEqual(self.call_rpc("bm25", "match_emnlp_papers_bm25"), 20)


if __name__ == "__main__":
    unittest.main()
