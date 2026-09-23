from pathlib import Path


SQL = (Path(__file__).resolve().parents[1] / "sql/research_radar_graph_rpc.sql").read_text(encoding="utf-8").lower()


RPCS = [
    "get_research_field_overview",
    "get_research_field_papers",
    "get_research_field_authors",
    "get_research_field_scholar_graph",
    "get_research_field_author_detail",
    "get_research_field_collaboration_detail",
]


def test_phase4_read_rpcs_exist_and_are_security_invoker():
    for name in RPCS:
        assert f"function public.{name}" in SQL
        function_block = SQL.split(f"function public.{name}", 1)[1].split("; $$;", 1)[0]
        assert "security invoker" in function_block
        assert "stable" in function_block


def test_phase4_rpcs_are_anon_read_only():
    for name in RPCS:
        assert f"revoke all on function public.{name}" in SQL
        assert f"grant execute on function public.{name}" in SQL
    assert "to anon,authenticated" in SQL
    assert "service_role" not in SQL


def test_graph_recomputes_counts_inside_requested_time_range():
    graph = SQL.split("function public.get_research_field_scholar_graph", 1)[1].split("; $$;", 1)[0]
    assert "p.year>=p_start_year" in graph
    assert "p.year<=p_end_year" in graph
    assert "count(distinct fp.id)" in graph
    assert "p_max_nodes" in graph


def test_papers_rpc_is_paginated_and_filterable():
    papers = SQL.split("function public.get_research_field_papers", 1)[1].split("; $$;", 1)[0]
    for token in ("p_search", "p_venue", "p_author", "p_relevance_label", "p_min_relevance", "p_limit", "p_offset"):
        assert token in papers
    assert "limit greatest" in papers
    assert "offset greatest" in papers


def test_rpc_migration_only_references_research_radar_tables():
    for forbidden in ("alter table", "drop table", "truncate", "src/main.py"):
        assert forbidden not in SQL
