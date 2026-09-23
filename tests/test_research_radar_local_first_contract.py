from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_first_architecture_records_required_boundaries():
    text = (ROOT / "docs/LOCAL_FIRST_ARCHITECTURE.md").read_text(encoding="utf-8")
    for term in (
        "Local-first, cloud-optional",
        "SQLiteRepository",
        "SupabaseRepository",
        "LocalApiDataSource",
        "FixtureDataSource",
        "SupabaseDataSource",
        "FTS5",
        "~/.research-radar/",
        "Phase 5",
    ):
        assert term in text


def test_frontend_has_local_adapter_without_service_credentials():
    source = (ROOT / "app/research-radar-api.js").read_text(encoding="utf-8")
    assert "function LocalApiDataSource" in source
    assert "'/api/research-fields'" in source
    assert "SUPABASE_SERVICE_KEY" not in source
