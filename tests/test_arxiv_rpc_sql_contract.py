"""长时间窗 RPC 的性能/安全合同；实际匿名调用由验证脚本覆盖。"""

from pathlib import Path
import unittest

SQL = (Path(__file__).resolve().parents[1] / "sql/match_arxiv_papers.sql").read_text()


def function_body(name):
    return SQL.split("FUNCTION " + name + "(", 1)[1].split("$$;", 1)[0]


class ArxivRpcTests(unittest.TestCase):
    def test_exact_preserves_exact_distance_and_late_materialization(self):
        text = function_body("match_arxiv_papers_exact")
        self.assertIn("nearest AS MATERIALIZED", text)
        self.assertIn("p.embedding <=> query_embedding", text)
        self.assertIn("ORDER BY (p.embedding <=> query_embedding) + 0", text)
        self.assertIn("JOIN public.arxiv_papers", text)
        self.assertNotIn("hnsw.", text)

    def test_bm25_filters_with_index_but_preserves_original_rank(self):
        text = function_body("match_arxiv_papers_bm25")
        self.assertIn("p.search_tsv @@ search_query", text)
        self.assertIn("to_tsvector('english', coalesce(p.title, '')", text)
        self.assertIn("plainto_tsquery('english', query_text)", text)

    def test_scoped_timeouts_custom_plans_and_invoker_security(self):
        for name in ("match_arxiv_papers_exact", "match_arxiv_papers_bm25"):
            text = function_body(name)
            self.assertIn("SECURITY INVOKER", text)
            self.assertIn("SET plan_cache_mode = force_custom_plan", text)
            self.assertIn("SET statement_timeout", text)
            self.assertIn("p.published >= filter_published_start", text)
            self.assertIn("p.published < filter_published_end", text)
            self.assertIn("LIMIT match_count", text)
        self.assertNotIn("SECURITY DEFINER", SQL)
        self.assertNotIn("ALTER ROLE", SQL)
        self.assertNotIn("DISABLE ROW LEVEL SECURITY", SQL)
        self.assertIn("NOTIFY pgrst, 'reload schema'", SQL)


if __name__ == "__main__":
    unittest.main()
