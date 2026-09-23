from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_NAME = "ResearchRadar"
DEFAULT_PORT = 8765


def load_research_radar_env() -> None:
    """Load local Research Radar settings without overriding process values."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def get_data_dir() -> Path:
    override = os.getenv("RESEARCH_RADAR_HOME")
    if override:
        return Path(override).expanduser().resolve()
    try:
        from platformdirs import user_data_dir

        return Path(user_data_dir(APP_NAME, appauthor=False)).resolve()
    except Exception:
        return (Path.home() / ".research-radar").resolve()


def ensure_data_dir(home: Path | None = None) -> Path:
    root = (home or get_data_dir()).resolve()
    for child in (root, root / "logs", root / "cache", root / "papers", root / "exports"):
        child.mkdir(parents=True, exist_ok=True)
    return root


def default_config_text() -> str:
    return "\n".join(
        [
            "[app]",
            'host = "127.0.0.1"',
            f"port = {DEFAULT_PORT}",
            "open_browser = true",
            "",
            "[storage]",
            'backend = "sqlite"',
            "",
            "[openalex]",
            'api_key = ""',
            "",
            "[ollama]",
            "enabled = true",
            'base_url = "http://127.0.0.1:11434"',
            'model = "qwen3:8b"',
            "timeout_seconds = 60",
            "",
            "[sync]",
            "historical_years = 5",
            "",
        ]
    )


def ensure_default_config(home: Path | None = None) -> Path:
    root = ensure_data_dir(home)
    path = root / "config.toml"
    if not path.exists():
        path.write_text(default_config_text(), encoding="utf-8")
    return path


def load_local_config(home: Path | None = None) -> dict:
    root = ensure_data_dir(home)
    config_path = ensure_default_config(root)
    try:
        import tomllib

        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    app = dict(data.get("app") or {})
    storage = dict(data.get("storage") or {})
    openalex = dict(data.get("openalex") or {})
    ollama = dict(data.get("ollama") or {})
    sync = dict(data.get("sync") or {})
    port = int(os.getenv("RESEARCH_RADAR_PORT") or app.get("port") or DEFAULT_PORT)
    open_browser_env = os.getenv("RESEARCH_RADAR_OPEN_BROWSER")
    open_browser = app.get("open_browser", True)
    if open_browser_env is not None:
        open_browser = open_browser_env.strip().lower() not in {"0", "false", "no", "off"}
    ollama_enabled_env = os.getenv("RESEARCH_RADAR_OLLAMA_ENABLED")
    ollama_enabled = ollama.get("enabled", True)
    if ollama_enabled_env is not None:
        ollama_enabled = ollama_enabled_env.strip().lower() not in {"0", "false", "no", "off"}
    return {
        "home": root,
        "config_path": config_path,
        "database_path": root / "research-radar.db",
        "log_path": root / "logs" / "research-radar.log",
        "app": {
            "host": str(app.get("host") or "127.0.0.1"),
            "port": port,
            "open_browser": bool(open_browser),
        },
        "storage": {"backend": str(storage.get("backend") or "sqlite")},
        "openalex": {"api_key": os.getenv("OPENALEX_API_KEY") or openalex.get("api_key") or ""},
        "ollama": {
            "enabled": bool(ollama_enabled),
            "base_url": str(os.getenv("RESEARCH_RADAR_OLLAMA_URL") or ollama.get("base_url") or "http://127.0.0.1:11434").rstrip("/"),
            "model": str(os.getenv("RESEARCH_RADAR_OLLAMA_MODEL") or ollama.get("model") or "qwen3:8b"),
            "timeout_seconds": int(os.getenv("RESEARCH_RADAR_OLLAMA_TIMEOUT_SECONDS") or ollama.get("timeout_seconds") or 60),
        },
        "sync": {"historical_years": int(sync.get("historical_years") or 5)},
    }
