from src.research_radar.cli import main


def test_cli_init_doctor_version_with_temp_home(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RESEARCH_RADAR_HOME", str(tmp_path))
    assert main(["init"]) == 0
    assert (tmp_path / "research-radar.db").exists()
    assert main(["version"]) == 0
    assert main(["start", "--no-browser", "--check-only"]) == 0
    output = capsys.readouterr().out
    assert "Ready: http://127.0.0.1:8765/#/research-radar/" in output
