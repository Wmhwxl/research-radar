from __future__ import annotations

import logging
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.providers.openalex import OpenAlexProvider
from src.research_radar.config import PROJECT_ROOT, load_local_config
from src.research_radar.models import ResearchField
from src.research_radar.ollama_field_planner import OllamaFieldPlanner, needs_field_planning
from src.research_radar.sqlite_repository import SQLiteResearchRadarRepository
from src.research_radar.sync_field_history import sync_field_history


class CreateFieldRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None
    core_keywords: list[str] = []
    optional_keywords: list[str] = []
    excluded_keywords: list[str] = []
    intent_queries: list[str] = []
    seed_papers: list[Any] = []
    seed_authors: list[Any] = []
    auto_sync: bool = True
    sync_frequency: str = "daily"
    enabled: bool = True


class UpdateFieldRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    core_keywords: list[str] | None = None
    optional_keywords: list[str] | None = None
    excluded_keywords: list[str] | None = None
    intent_queries: list[str] | None = None
    seed_papers: list[Any] | None = None
    seed_authors: list[Any] | None = None
    enabled: bool | None = None
    auto_sync: bool | None = None
    sync_frequency: str | None = None


class SyncRequest(BaseModel):
    years: int = 1
    max_pages: int | None = 1
    from_date: str | None = None
    to_date: str | None = None
    resume_run_id: str | None = None


def create_app(*, database_path: str | Path | None = None, project_root: str | Path | None = None) -> FastAPI:
    config = load_local_config()
    db_path = Path(database_path or config["database_path"])
    root = Path(project_root or PROJECT_ROOT)
    repo = SQLiteResearchRadarRepository(db_path)
    app = FastAPI(title="Research Radar Local API", version="0.5.0")
    app.state.repo = repo
    app.state.project_root = root
    app.state.sync_threads = {}

    @app.on_event("shutdown")
    def _shutdown() -> None:
        repo.close()

    @app.on_event("startup")
    def _startup() -> None:
        repo.mark_interrupted_sync_runs()
        for field in repo.due_auto_sync_fields():
            if not repo.get_running_sync_run(field.id or ""):
                run_id = repo.create_sync_run(
                    field,
                    provider="openalex",
                    from_date=_resolve_dates(SyncRequest(years=1, max_pages=1))[0],
                    to_date=_resolve_dates(SyncRequest(years=1, max_pages=1))[1],
                    queries=[],
                )
                thread = threading.Thread(
                    target=_sync_worker,
                    kwargs={
                        "database_path": db_path,
                        "field_id": field.id,
                        "from_date": _resolve_dates(SyncRequest(years=1, max_pages=1))[0],
                        "to_date": _resolve_dates(SyncRequest(years=1, max_pages=1))[1],
                        "max_pages": 1,
                        "resume_run_id": run_id,
                    },
                    daemon=True,
                )
                app.state.sync_threads[run_id] = thread
                thread.start()

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "storage": "sqlite", "database": str(db_path)}

    @app.get("/api/research-fields")
    def list_fields() -> list[dict[str, Any]]:
        return repo.list_research_fields()

    @app.get("/api/home")
    def home() -> dict[str, Any]:
        return repo.get_home()

    @app.post("/api/research-fields")
    def create_field(payload: CreateFieldRequest) -> dict[str, Any]:
        try:
            return repo.create_research_field(_model_payload(payload))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/research-fields/{field_id}")
    def get_field(field_id: str) -> dict[str, Any]:
        field = repo.get_research_field_row(field_id)
        if not field:
            raise HTTPException(status_code=404, detail="research field not found")
        repo.touch_field_visit(field_id)
        return field

    @app.patch("/api/research-fields/{field_id}")
    def update_field(field_id: str, payload: UpdateFieldRequest) -> dict[str, Any]:
        _require_field(repo, field_id)
        try:
            data = {key: value for key, value in _model_payload(payload).items() if value is not None}
            return repo.update_research_field(field_id, data)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/research-fields/{field_id}/overview")
    def field_overview(field_id: str, request: Request) -> dict[str, Any]:
        _require_field(repo, field_id)
        repo.touch_field_visit(field_id)
        return repo.get_field_overview(field_id, _query(request))

    @app.get("/api/research-fields/{field_id}/brief")
    def field_brief(field_id: str, request: Request) -> dict[str, Any]:
        _require_field(repo, field_id)
        return repo.get_field_brief(field_id, _query(request))

    @app.get("/api/research-fields/{field_id}/papers")
    def field_papers(field_id: str, request: Request) -> dict[str, Any]:
        _require_field(repo, field_id)
        return repo.get_field_papers(field_id, _query(request))

    @app.get("/api/research-fields/{field_id}/authors")
    def field_authors(field_id: str, request: Request) -> dict[str, Any]:
        _require_field(repo, field_id)
        return repo.get_field_authors(field_id, _query(request))

    @app.get("/api/research-fields/{field_id}/graph")
    def field_graph(field_id: str, request: Request) -> dict[str, Any]:
        _require_field(repo, field_id)
        return repo.get_scholar_graph(field_id, _query(request))

    @app.get("/api/research-fields/{field_id}/authors/{author_id}")
    def field_author_detail(field_id: str, author_id: str, request: Request) -> dict[str, Any]:
        _require_field(repo, field_id)
        result = repo.get_author_detail(field_id, author_id, _query(request))
        if not result:
            raise HTTPException(status_code=404, detail="author not found")
        return result

    @app.get("/api/research-fields/{field_id}/collaborations/{author_a}/{author_b}")
    def field_collaboration_detail(field_id: str, author_a: str, author_b: str, request: Request) -> dict[str, Any]:
        _require_field(repo, field_id)
        return repo.get_collaboration_detail(field_id, author_a, author_b, _query(request))

    @app.get("/api/authors/{author_id}")
    def author_detail(author_id: str, request: Request) -> dict[str, Any]:
        field_id = request.query_params.get("field_id")
        if not field_id:
            raise HTTPException(status_code=422, detail="field_id is required")
        result = repo.get_author_detail(field_id, author_id, _query(request))
        if not result:
            raise HTTPException(status_code=404, detail="author not found")
        return result

    @app.get("/api/collaborations/{author_a}/{author_b}")
    def collaboration_detail(author_a: str, author_b: str, request: Request) -> dict[str, Any]:
        field_id = request.query_params.get("field_id")
        if not field_id:
            raise HTTPException(status_code=422, detail="field_id is required")
        return repo.get_collaboration_detail(field_id, author_a, author_b, _query(request))

    @app.get("/api/search")
    def search(request: Request) -> dict[str, Any]:
        query = request.query_params.get("q") or request.query_params.get("query") or ""
        filters = _query(request)
        return {
            "papers": repo.search_papers(query, filters),
            "authors": repo.search_authors(query, filters),
        }

    @app.post("/api/research-fields/{field_id}/sync")
    def start_sync(field_id: str, payload: SyncRequest, background: BackgroundTasks) -> dict[str, Any]:
        field = _require_field(repo, field_id)
        running = repo.get_running_sync_run(field_id)
        if running:
            return {"run_id": running["id"], "status": "running", "existing": True}
        from_date, to_date = _resolve_dates(payload)
        run_id = repo.create_sync_run(
            field,
            provider="openalex",
            from_date=from_date,
            to_date=to_date,
            queries=[],
        )
        thread = threading.Thread(
            target=_sync_worker,
            kwargs={
                "database_path": db_path,
                "field_id": field_id,
                "from_date": from_date,
                "to_date": to_date,
                "max_pages": payload.max_pages,
                "resume_run_id": payload.resume_run_id or run_id,
            },
            daemon=True,
        )
        app.state.sync_threads[run_id] = thread
        thread.start()
        return {"run_id": run_id, "status": "running"}

    @app.get("/api/sync-runs/{run_id}")
    def sync_status(run_id: str) -> dict[str, Any]:
        run = repo.get_sync_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="sync run not found")
        return run

    @app.get("/api/settings")
    def settings() -> dict[str, Any]:
        cfg = load_local_config()
        return {
            "application": {
                "port": cfg["app"]["port"],
                "open_browser": cfg["app"]["open_browser"],
            },
            "openalex": {"api_key_configured": bool(cfg["openalex"]["api_key"])},
            "local_ai": {
                "enabled": cfg["ollama"]["enabled"],
                "model": cfg["ollama"]["model"],
                "provider": "Ollama",
            },
            "sync": cfg["sync"],
            "storage": {"backend": cfg["storage"]["backend"], "database_path": str(db_path)},
        }

    _mount_static(app, root)
    return app


def _sync_worker(
    *,
    database_path: Path,
    field_id: str,
    from_date: str,
    to_date: str,
    max_pages: int | None,
    resume_run_id: str,
) -> None:
    worker_repo = SQLiteResearchRadarRepository(database_path)
    try:
        field = worker_repo.get_research_field(field_id=field_id)
        if not field:
            raise ValueError("research field not found")
        config = load_local_config()
        if config["ollama"]["enabled"] and needs_field_planning(field):
            worker_repo.update_sync_checkpoint(resume_run_id, {"stage": "planning", "pages_completed": 0})
            try:
                plan = OllamaFieldPlanner(
                    base_url=config["ollama"]["base_url"],
                    model=config["ollama"]["model"],
                    timeout_seconds=config["ollama"]["timeout_seconds"],
                ).plan(field)
                worker_repo.update_research_field(
                    field_id,
                    {
                        "core_keywords": plan["core_keywords"],
                        "intent_queries": plan["intent_queries"],
                        "optional_keywords": plan["optional_keywords"],
                    },
                )
                field = worker_repo.get_research_field(field_id=field_id) or field
            except Exception:
                logging.getLogger(__name__).warning(
                    "Local Ollama field planning failed; using the existing field definition",
                    exc_info=True,
                )
        worker_repo.update_sync_checkpoint(resume_run_id, {"stage": "searching", "pages_completed": 0})
        sync_field_history(
            field=field,
            provider=OpenAlexProvider(),
            repository=worker_repo,
            from_date=from_date,
            to_date=to_date,
            max_pages=max_pages,
            resume_run_id=resume_run_id,
        )
    except Exception as exc:
        logging.getLogger(__name__).exception("Research Radar sync failed")
        worker_repo.complete_sync_run(
            resume_run_id,
            status="failed",
            counters={"failures": 1},
            error_summary={"message": str(exc)},
        )
    finally:
        worker_repo.close()


def _mount_static(app: FastAPI, root: Path) -> None:
    safe_dirs = ["app", "docs", "archive", "fixtures"]
    for name in safe_dirs:
        path = root / name
        if path.exists():
            app.mount(f"/{name}", StaticFiles(directory=str(path)), name=f"static-{name}")

    @app.get("/research-radar-runtime-config.js")
    def runtime_config() -> PlainTextResponse:
        return PlainTextResponse(
            "window.RESEARCH_RADAR_CONFIG = { mode: 'local', baseUrl: '' };\n",
            media_type="application/javascript",
        )

    @app.get("/")
    def index() -> HTMLResponse:
        return _index_response(root)

    @app.get("/{path:path}")
    def docsify_fallback(path: str):
        return JSONResponse({"detail": "not found"}, status_code=404)


def _query(request: Request) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, value in request.query_params.items():
        if value == "":
            continue
        data[key] = value
    return data


def _index_response(root: Path) -> HTMLResponse:
    html = (root / "index.html").read_text(encoding="utf-8")
    script = '<script src="/research-radar-runtime-config.js"></script>'
    if script not in html:
        html = html.replace("</head>", script + "\n</head>")
    return HTMLResponse(html)


def _require_field(repo: SQLiteResearchRadarRepository, field_id: str) -> ResearchField:
    field = repo.get_research_field(field_id=field_id)
    if not field:
        raise HTTPException(status_code=404, detail="research field not found")
    return field


def _resolve_dates(payload: SyncRequest) -> tuple[str, str]:
    if payload.from_date and payload.to_date:
        return payload.from_date, payload.to_date
    end = date.fromisoformat(payload.to_date) if payload.to_date else date.today()
    start = date.fromisoformat(payload.from_date) if payload.from_date else end - timedelta(days=max(payload.years, 1) * 365)
    return start.isoformat(), end.isoformat()


def _model_payload(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
