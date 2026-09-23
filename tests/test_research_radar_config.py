import os

from src.research_radar import config


def test_load_research_radar_env_uses_project_env_without_overriding(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SUPABASE_URL=https://from-file.invalid\n"
        "SUPABASE_ANON_KEY=anon-from-file\n"
        "SUPABASE_SERVICE_KEY=service-from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("SUPABASE_URL", "https://from-process.invalid")
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    config.load_research_radar_env()

    assert os.environ["SUPABASE_URL"] == "https://from-process.invalid"
    assert os.environ["SUPABASE_ANON_KEY"] == "anon-from-file"
    assert os.environ["SUPABASE_SERVICE_KEY"] == "service-from-file"
