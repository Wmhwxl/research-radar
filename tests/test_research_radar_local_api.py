from fastapi.testclient import TestClient

import src.research_radar.server.app as server_app
from src.research_radar.server.app import create_app


def test_local_api_empty_create_and_search(tmp_path):
    app = create_app(database_path=tmp_path / "rr.db")
    client = TestClient(app)
    assert client.get("/api/health").json()["storage"] == "sqlite"
    assert client.get("/api/research-fields").json() == []
    created = client.post(
        "/api/research-fields",
        json={"name": "Incomplete Multimodal Recommendation", "core_keywords": ["multimodal recommendation"]},
    )
    assert created.status_code == 200
    field = created.json()
    assert field["slug"] == "incomplete-multimodal-recommendation"
    assert client.get(f"/api/research-fields/{field['id']}/overview").status_code == 200
    assert client.get("/api/search?q=multimodal").json()["papers"]["items"] == []


def test_phase6_home_brief_field_edit_and_duplicate_sync(tmp_path, monkeypatch):
    monkeypatch.setattr(server_app, "_sync_worker", lambda **kwargs: None)
    app = create_app(database_path=tmp_path / "rr.db")
    client = TestClient(app)
    field = client.post(
        "/api/research-fields",
        json={"name": "Graph Recommenders", "core_keywords": ["graph recommender"]},
    ).json()
    home = client.get("/api/home").json()
    assert home["fields"][0]["name"] == "Graph Recommenders"

    updated = client.patch(
        f"/api/research-fields/{field['id']}",
        json={"enabled": False, "auto_sync": False, "sync_frequency": "weekly"},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["auto_sync"] is False
    assert updated.json()["sync_frequency"] == "weekly"

    brief = client.get(f"/api/research-fields/{field['id']}/brief").json()
    assert brief["new_paper_count"] == 0

    first = client.post(f"/api/research-fields/{field['id']}/sync", json={"years": 1, "max_pages": 1}).json()
    second = client.post(f"/api/research-fields/{field['id']}/sync", json={"years": 1, "max_pages": 1}).json()
    assert second["run_id"] == first["run_id"]
    assert second["existing"] is True
    listed = client.get("/api/research-fields").json()[0]
    assert listed["latest_sync_run_id"] == first["run_id"]

    settings = client.get("/api/settings").json()
    assert settings["storage"]["backend"] == "sqlite"
    assert settings["local_ai"]["provider"] == "Ollama"
