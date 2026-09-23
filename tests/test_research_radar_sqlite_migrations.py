import sqlite3

from src.research_radar.storage.sqlite.migrator import apply_migrations


def test_sqlite_migrations_create_expected_tables_and_repeat(tmp_path):
    db = tmp_path / "research-radar.db"
    assert apply_migrations(db) == ["001", "002", "003"]
    assert apply_migrations(db) == []
    conn = sqlite3.connect(db)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual')").fetchall()
        }
    finally:
        conn.close()
    expected = {
        "research_fields",
        "institutions",
        "venues",
        "academic_papers",
        "authors",
        "paper_authors",
        "paper_author_institutions",
        "research_field_papers",
        "research_field_sync_runs",
        "author_collaborations",
        "paper_search_documents",
        "paper_search_fts",
    }
    assert expected.issubset(tables)
