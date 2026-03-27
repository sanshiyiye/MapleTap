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
    "dedupe_similarity_threshold": 0.82,
    "tracking_query_params": [
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "source",
        "src",
        "utm_campaign",
        "utm_content",
        "utm_medium",
        "utm_source",
        "utm_term",
    ],
    "scoring_weights": {
        "relevance": 0.35,
        "authority": 0.2,
        "recency": 0.2,
        "convergence": 0.15,
        "novelty": 0.1,
    },
    "source_authority_overrides": {},
    "watchlist_topics": [
        {
            "name": "ai coding",
            "keywords": ["ai", "coding", "copilot", "agent", "developer tool"],
        },
        {
            "name": "startup opportunities",
            "keywords": ["startup", "founder", "saas", "funding", "automation"],
        },
        {
            "name": "infra signals",
            "keywords": [
                "security",
                "incident",
                "outage",
                "supply chain",
                "infrastructure",
            ],
        },
    ],
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
