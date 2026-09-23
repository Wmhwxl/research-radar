from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "sql" / "create_research_radar_schema.sql"
SQL = SQL_PATH.read_text(encoding="utf-8")
SQL_LOWER = SQL.lower()
SQL_COMPACT = re.sub(r"\s+", " ", SQL_LOWER)


TABLES = [
    "research_fields",
    "institutions",
    "venues",
    "academic_papers",
    "authors",
    "paper_authors",
    "research_field_papers",
    "research_field_sync_runs",
    "author_collaborations",
]


def table_body(table_name: str) -> str:
    marker = f"create table if not exists public.{table_name} ("
    start = SQL_LOWER.index(marker) + len(marker)
    depth = 1
    idx = start
    while idx < len(SQL_LOWER):
        char = SQL_LOWER[idx]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return SQL_LOWER[start:idx]
        idx += 1
    raise AssertionError(f"table body not found: {table_name}")


class ResearchRadarSqlContractTest(unittest.TestCase):
    def test_expected_tables_exist(self):
        self.assertTrue(SQL_PATH.exists(), f"missing {SQL_PATH}")
        for table in TABLES:
            with self.subTest(table=table):
                self.assertIn(f"create table if not exists public.{table}", SQL_LOWER)

    def test_research_fields_contract(self):
        body = table_body("research_fields")
        self.assertIn("id uuid primary key default gen_random_uuid()", body)
        self.assertIn("name text not null", body)
        self.assertIn("slug text not null unique", body)
        for column in [
            "core_keywords",
            "optional_keywords",
            "excluded_keywords",
            "intent_queries",
            "seed_papers",
            "seed_authors",
        ]:
            self.assertRegex(body, rf"\b{column}\s+jsonb\s+not null\s+default\s+'\[\]'::jsonb")
        self.assertIn("enabled boolean not null default true", body)
        self.assertIn("created_at timestamptz not null default now()", body)
        self.assertIn("updated_at timestamptz not null default now()", body)

    def test_relationship_contracts(self):
        checks = {
            "paper_authors -> academic_papers": (
                "paper_authors",
                "paper_id uuid not null references public.academic_papers(id) on delete cascade",
            ),
            "paper_authors -> authors": (
                "paper_authors",
                "author_id uuid not null references public.authors(id) on delete cascade",
            ),
            "paper_authors -> institutions": (
                "paper_authors",
                "institution_id uuid references public.institutions(id) on delete set null",
            ),
            "research_field_papers -> research_fields": (
                "research_field_papers",
                "research_field_id uuid not null references public.research_fields(id) on delete cascade",
            ),
            "research_field_papers -> academic_papers": (
                "research_field_papers",
                "paper_id uuid not null references public.academic_papers(id) on delete cascade",
            ),
            "authors -> institutions": (
                "authors",
                "primary_institution_id uuid references public.institutions(id) on delete set null",
            ),
            "academic_papers -> venues": (
                "academic_papers",
                "venue_id uuid references public.venues(id) on delete set null",
            ),
            "author_collaborations -> research_fields": (
                "author_collaborations",
                "research_field_id uuid not null references public.research_fields(id) on delete cascade",
            ),
            "author_collaborations -> author_a": (
                "author_collaborations",
                "author_a_id uuid not null references public.authors(id) on delete cascade",
            ),
            "author_collaborations -> author_b": (
                "author_collaborations",
                "author_b_id uuid not null references public.authors(id) on delete cascade",
            ),
            "sync_runs -> research_fields": (
                "research_field_sync_runs",
                "research_field_id uuid not null references public.research_fields(id) on delete cascade",
            ),
        }
        for label, (table, expected) in checks.items():
            with self.subTest(label=label):
                self.assertIn(expected, re.sub(r"\s+", " ", table_body(table)))

    def test_primary_keys_and_many_to_many_contracts(self):
        self.assertIn("primary key (paper_id, author_id)", table_body("paper_authors"))
        self.assertIn(
            "primary key (research_field_id, paper_id)",
            table_body("research_field_papers"),
        )
        self.assertIn(
            "primary key (research_field_id, author_a_id, author_b_id)",
            table_body("author_collaborations"),
        )
        self.assertNotIn("field_id", table_body("academic_papers"))

    def test_identity_unique_contracts(self):
        self.assertIn("slug text not null unique", table_body("research_fields"))
        unique_indexes = [
            "institutions_openalex_id_unique",
            "venues_openalex_id_unique",
            "academic_papers_openalex_id_unique",
            "academic_papers_doi_unique",
            "academic_papers_arxiv_id_unique",
            "authors_openalex_id_unique",
        ]
        for index_name in unique_indexes:
            with self.subTest(index=index_name):
                self.assertIn(f"create unique index if not exists {index_name}", SQL_LOWER)
                definition = SQL_LOWER.split(
                    f"create unique index if not exists {index_name}", 1
                )[1].split(";", 1)[0]
                self.assertNotIn(" where ", definition)
        self.assertIn("authors_orcid_unique", SQL_LOWER)
        self.assertIn("institutions_ror_id_unique", SQL_LOWER)

    def test_collaboration_order_contract(self):
        body = table_body("author_collaborations")
        self.assertIn("author_a_id uuid not null references public.authors(id) on delete cascade", body)
        self.assertIn("author_b_id uuid not null references public.authors(id) on delete cascade", body)
        self.assertIn(
            "constraint author_collaborations_distinct_ordered_authors check (author_a_id < author_b_id)",
            re.sub(r"\s+", " ", body),
        )

    def test_sync_runs_support_incremental_audit(self):
        body = table_body("research_field_sync_runs")
        for column in [
            "provider text not null",
            "status text not null",
            "from_date date",
            "to_date date",
            "started_at timestamptz not null default now()",
            "completed_at timestamptz",
            "queries jsonb not null default '[]'::jsonb",
            "candidates_retrieved int not null default 0",
            "papers_inserted int not null default 0",
            "papers_updated int not null default 0",
            "authors_inserted int not null default 0",
            "institutions_inserted int not null default 0",
            "venues_inserted int not null default 0",
            "paper_author_links_inserted int not null default 0",
            "collaborations_created int not null default 0",
            "duplicates_skipped int not null default 0",
            "failures int not null default 0",
            "partial_failures int not null default 0",
            "error_summary jsonb not null default '{}'::jsonb",
        ]:
            with self.subTest(column=column):
                self.assertIn(column, re.sub(r"\s+", " ", body))

    def test_required_indexes_exist_without_repeating_primary_keys(self):
        expected_indexes = [
            "academic_papers_year_idx",
            "academic_papers_publication_date_idx",
            "academic_papers_venue_id_idx",
            "academic_papers_normalized_title_year_idx",
            "authors_primary_institution_id_idx",
            "paper_authors_author_id_idx",
            "paper_authors_institution_id_idx",
            "research_field_papers_paper_id_idx",
            "research_field_papers_field_relevance_idx",
            "research_field_sync_runs_field_started_idx",
            "author_collaborations_field_idx",
            "author_collaborations_field_author_a_idx",
            "author_collaborations_field_author_b_idx",
        ]
        for index_name in expected_indexes:
            with self.subTest(index=index_name):
                self.assertIn(f"create index if not exists {index_name}", SQL_LOWER)
        self.assertNotIn("paper_authors_paper_id_idx", SQL_LOWER)
        self.assertNotIn("research_field_papers_research_field_id_idx", SQL_LOWER)

    def test_updated_at_trigger_is_research_radar_scoped(self):
        self.assertIn("create or replace function public.set_research_radar_updated_at()", SQL_LOWER)
        for trigger_name in [
            "research_fields_set_updated_at",
            "institutions_set_updated_at",
            "venues_set_updated_at",
            "academic_papers_set_updated_at",
            "authors_set_updated_at",
            "author_collaborations_set_updated_at",
        ]:
            with self.subTest(trigger=trigger_name):
                self.assertIn(trigger_name, SQL_LOWER)
        self.assertNotIn("on public.arxiv_papers", SQL_LOWER)

    def test_rls_and_read_only_anon_contract(self):
        for table in TABLES:
            with self.subTest(table=table):
                self.assertIn(f"alter table public.{table} enable row level security", SQL_LOWER)
                self.assertIn(f"grant select on table public.{table} to anon, authenticated", SQL_LOWER)

    def test_service_role_has_explicit_write_contract(self):
        tables = [
            "research_fields",
            "institutions",
            "venues",
            "academic_papers",
            "authors",
            "paper_authors",
            "research_field_papers",
            "research_field_sync_runs",
            "author_collaborations",
        ]
        for table in tables:
            with self.subTest(table=table):
                self.assertIn(
                    f"grant select, insert, update, delete on table public.{table} to service_role",
                    SQL_LOWER,
                )
        self.assertIn("pg_policies", SQL_LOWER)
        self.assertNotRegex(SQL_LOWER, r"grant\s+(insert|update|delete|all)")
        self.assertNotRegex(SQL_LOWER, r"for\s+(insert|update|delete|all)\b")

    def test_additive_safety_contract(self):
        destructive_patterns = [
            r"\bdrop\s+table\b",
            r"\bdrop\s+function\b",
            r"\btruncate\b",
            r"\bdelete\s+from\s+public\.",
            r"\balter\s+table\s+public\.(arxiv_papers|papers|biorxiv_papers|medrxiv_papers|chemrxiv_papers)\b",
            r"\balter\s+table\s+public\.(neurips_openreview_papers|icml_openreview_papers|iclr_openreview_papers)\b",
            r"\balter\s+table\s+public\.(aaai_papers|acl_papers|emnlp_papers|cvpr_papers|eccv_papers|ijcai_papers)\b",
            r"\balter\s+table\s+public\.(osdi_papers|sosp_papers|ieee_sp_papers|ndss_papers)\b",
            r"\bcreate\s+or\s+replace\s+function\s+match_",
        ]
        for pattern in destructive_patterns:
            with self.subTest(pattern=pattern):
                self.assertNotRegex(SQL_LOWER, pattern)
        self.assertIn("notify pgrst, 'reload schema'", SQL_LOWER)


if __name__ == "__main__":
    unittest.main()
