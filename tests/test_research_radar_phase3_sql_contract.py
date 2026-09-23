from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "sql" / "extend_research_radar_phase3.sql"
SQL = SQL_PATH.read_text(encoding="utf-8").lower()
COMPACT = re.sub(r"\s+", " ", SQL)


class ResearchRadarPhase3SqlContractTest(unittest.TestCase):
    def test_identity_indexes_support_postgrest_on_conflict(self):
        phase1_sql = (ROOT / "sql" / "create_research_radar_schema.sql").read_text(encoding="utf-8").lower()
        for index_name in (
            "institutions_openalex_id_unique",
            "institutions_ror_id_unique",
            "venues_openalex_id_unique",
            "academic_papers_openalex_id_unique",
            "academic_papers_doi_unique",
            "academic_papers_arxiv_id_unique",
            "authors_openalex_id_unique",
            "authors_orcid_unique",
        ):
            definition = phase1_sql.split(f"create unique index if not exists {index_name}", 1)[1].split(";", 1)[0]
            self.assertNotIn(" where ", definition)

    def test_service_role_can_write_multi_institution_links(self):
        self.assertIn(
            "grant select, insert, update, delete on table public.paper_author_institutions to service_role",
            SQL,
        )

    def test_relevance_columns_are_additive(self):
        self.assertIn("alter table public.research_field_papers", SQL)
        self.assertIn("add column if not exists relevance_label text", COMPACT)
        self.assertIn("add column if not exists relevance_evidence jsonb not null default '{}'::jsonb", COMPACT)
        self.assertIn("research_field_papers_relevance_label_allowed", SQL)
        self.assertIn("relevance_label in ('core', 'related')", COMPACT)
        self.assertNotIn("'rejected'", SQL)

    def test_sync_checkpoint_columns_are_additive(self):
        self.assertIn("add column if not exists checkpoint jsonb not null default '{}'::jsonb", COMPACT)
        for column in ["accepted_core", "accepted_related", "rejected"]:
            self.assertIn(f"add column if not exists {column} int not null default 0", COMPACT)

    def test_paper_author_institutions_contract(self):
        self.assertIn("create table if not exists public.paper_author_institutions", SQL)
        self.assertIn("paper_id uuid not null references public.academic_papers(id) on delete cascade", COMPACT)
        self.assertIn("author_id uuid not null references public.authors(id) on delete cascade", COMPACT)
        self.assertIn("institution_id uuid not null references public.institutions(id) on delete cascade", COMPACT)
        self.assertIn("primary key (paper_id, author_id, institution_id)", COMPACT)

    def test_read_only_public_policy(self):
        self.assertIn("alter table public.paper_author_institutions enable row level security", SQL)
        self.assertIn("grant select on table public.paper_author_institutions to anon, authenticated", SQL)
        self.assertIn("for select", SQL)
        self.assertNotRegex(SQL, r"grant\s+(insert|update|delete|all)")
        self.assertNotRegex(SQL, r"for\s+(insert|update|delete|all)\b")

    def test_additive_safety(self):
        for pattern in [r"\bdrop\s+table\b", r"\btruncate\b", r"\bdelete\s+from\s+public\.", r"\balter\s+table\s+public\.arxiv_papers\b"]:
            self.assertNotRegex(SQL, pattern)
        self.assertIn("notify pgrst, 'reload schema'", SQL)


if __name__ == "__main__":
    unittest.main()
