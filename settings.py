from __future__ import annotations

import json
from pathlib import Path

from errors import ConfigError


ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = ROOT / "settings.json"


DEFAULT_SETTINGS = {
    "topic": "Hacker News, AI, coding, startup opportunities",
    "per_feed_limit": 5,
    "timeout": 30,
    "retries": 3,
    "retry_delay": 2.0,
    "analysis_mode": "auto",
    "log_level": "INFO",
}


def load_settings(path: Path = SETTINGS_PATH) -> dict:
    if not path.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ConfigError(f"Invalid settings file: {path}: {exc}") from exc
    settings = dict(DEFAULT_SETTINGS)
    settings.update(loaded)
    return settings
