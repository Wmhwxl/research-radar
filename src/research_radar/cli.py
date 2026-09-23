from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import time
import webbrowser
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests

from src.providers.openalex import OpenAlexProvider
from src.research_radar import __version__
from src.research_radar.config import ensure_data_dir, ensure_default_config, load_local_config
from src.research_radar.server.app import create_app
from src.research_radar.sqlite_repository import SQLiteResearchRadarRepository
from src.research_radar.storage.sqlite.migrator import apply_migrations, connect_sqlite
from src.research_radar.sync_field_history import sync_field_history


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="research-radar")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize local Research Radar data.")
    start = sub.add_parser("start", help="Start the local Research Radar app.")
    start.add_argument("--host")
    start.add_argument("--port", type=int)
    start.add_argument("--no-browser", action="store_true")
    start.add_argument("--check-only", action="store_true", help=argparse.SUPPRESS)

    sync = sub.add_parser("sync", help="Sync a local research field from OpenAlex.")
    sync.add_argument("--field", "--field-slug", dest="field_slug")
    sync.add_argument("--field-id")
    sync.add_argument("--years", type=int, default=1)
    sync.add_argument("--max-pages", type=int, default=1)
    sync.add_argument("--from-date")
    sync.add_argument("--to-date")
    sync.add_argument("--resume-run-id")

    sub.add_parser("doctor", help="Check local Research Radar runtime health.")
    sub.add_parser("version", help="Print Research Radar version.")
    args = parser.parse_args(argv)

    if args.command == "init":
        return cmd_init()
    if args.command == "start":
        return cmd_start(args)
    if args.command == "sync":
        return cmd_sync(args)
    if args.command == "doctor":
        return cmd_doctor()
    if args.command == "version":
        print(__version__)
        return 0
    return 2


def cmd_init() -> int:
    config = load_local_config()
    home = ensure_data_dir(config["home"])
    ensure_default_config(home)
    applied = apply_migrations(config["database_path"])
    print(f"Data directory: {home}")
    print(f"Database: {config['database_path']}")
    print("Migrations: " + ("applied " + ", ".join(applied) if applied else "up to date"))
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    config = load_local_config()
    ensure_logging(config["log_path"])
    apply_migrations(config["database_path"])
    host = args.host or config["app"]["host"]
    port = args.port or config["app"]["port"]
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Research Radar local server only binds to localhost by default")
    if args.check_only:
        print(f"Ready: http://{host}:{port}/#/research-radar/")
        return 0
    try:
        import uvicorn
    except Exception as exc:
        raise SystemExit("uvicorn is required to start Research Radar") from exc
    app = create_app(database_path=config["database_path"])
    server_config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(server_config)
    url = f"http://{host}:{port}/#/research-radar/"
    if not args.no_browser and config["app"]["open_browser"]:
        import threading

        def opener() -> None:
            health = f"http://{host}:{port}/api/health"
            for _ in range(100):
                try:
                    if requests.get(health, timeout=0.5).ok:
                        webbrowser.open(url)
                        return
                except requests.RequestException:
                    time.sleep(0.1)

        threading.Thread(target=opener, daemon=True).start()
    print(f"Research Radar: {url}")
    server.run()
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    config = load_local_config()
    repo = SQLiteResearchRadarRepository(config["database_path"])
    try:
        field = None
        if args.field_id:
            field = repo.get_research_field(field_id=args.field_id)
        if field is None and args.field_slug:
            field = repo.get_research_field(field_slug=args.field_slug)
        if field is None:
            raise SystemExit("Research field not found. Create one in the UI or via API first.")
        from_date, to_date = _resolve_dates(args)
        summary = sync_field_history(
            field=field,
            provider=OpenAlexProvider(api_key=config["openalex"]["api_key"] or None),
            repository=repo,
            from_date=from_date,
            to_date=to_date,
            max_pages=args.max_pages,
            resume_run_id=args.resume_run_id,
        )
        counters = summary["counters"]
        print(f"run_id: {summary['run_id']}")
        print(f"pages: {counters.get('pages', 0)}")
        print(f"candidates: {counters.get('candidates_retrieved', 0)}")
        print(f"core: {counters.get('accepted_core', 0)}")
        print(f"related: {counters.get('accepted_related', 0)}")
        print(f"rejected: {counters.get('rejected', 0)}")
        return 0
    finally:
        repo.close()


def cmd_doctor() -> int:
    config = load_local_config()
    results: list[tuple[str, str, str]] = []
    home = ensure_data_dir(config["home"])
    results.append(("PASS", "data directory", str(home)))
    ensure_default_config(home)
    results.append(("PASS", "config", str(config["config_path"])))
    try:
        applied = apply_migrations(config["database_path"])
        results.append(("PASS", "migrations", "applied " + ", ".join(applied) if applied else "up to date"))
    except Exception as exc:
        results.append(("FAIL", "migrations", str(exc)))
    try:
        conn = connect_sqlite(config["database_path"])
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts5_probe USING fts5(value)")
        conn.execute("DROP TABLE fts5_probe")
        conn.execute("CREATE TABLE IF NOT EXISTS write_probe(value TEXT)")
        conn.execute("INSERT INTO write_probe(value) VALUES ('ok')")
        conn.execute("DELETE FROM write_probe")
        conn.commit()
        conn.close()
        results.append(("PASS", "SQLite FTS5", "available"))
        results.append(("PASS", "database writable", str(config["database_path"])))
    except Exception as exc:
        results.append(("FAIL", "SQLite", str(exc)))
    port = int(config["app"]["port"])
    results.append(("PASS" if _port_available(port) else "WARN", "port", str(port)))
    for rel in ("index.html", "app/research-radar.js", "docs/research-radar/README.md"):
        results.append(("PASS" if (Path(__file__).resolve().parents[2] / rel).exists() else "FAIL", "frontend file", rel))
    try:
        response = requests.get("https://api.openalex.org/works?per_page=1", timeout=5)
        results.append(("PASS" if response.ok else "WARN", "OpenAlex connectivity", f"HTTP {response.status_code}"))
    except requests.RequestException as exc:
        results.append(("WARN", "OpenAlex connectivity", type(exc).__name__))
    for status, label, detail in results:
        print(f"{status} {label}: {detail}")
    return 1 if any(status == "FAIL" for status, _, _ in results) else 0


def ensure_logging(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(path), level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger(__name__).info("Research Radar startup")


def _resolve_dates(args: argparse.Namespace) -> tuple[str, str]:
    if args.from_date and args.to_date:
        return args.from_date, args.to_date
    end = date.fromisoformat(args.to_date) if args.to_date else date.today()
    start = date.fromisoformat(args.from_date) if args.from_date else end - timedelta(days=max(args.years, 1) * 365)
    return start.isoformat(), end.isoformat()


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) != 0


if __name__ == "__main__":
    raise SystemExit(main())
