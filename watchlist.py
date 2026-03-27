from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from analyze_batch import NewsItem, load_input_items
from state_utils import atomic_write_json


ROOT = Path(__file__).resolve().parent
DEFAULT_WATCHLIST_PATH = ROOT / "watchlist.json"
MAX_SAMPLE_ITEMS = 5
WATCHLIST_SCHEMA = "watchlist.v1"


def _normalize_topic_entry(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, str):
        name = raw.strip()
        if not name:
            return None
        return {
            "name": name,
            "keywords": [name],
            "hit_count": 0,
            "last_hit_at": None,
            "matched_feeds": {},
            "sample_items": [],
            "last_run_hits": 0,
        }
    if isinstance(raw, dict):
        name = str(raw.get("name", "")).strip()
        keywords = [str(x).strip() for x in raw.get("keywords", []) if str(x).strip()]
        if not name:
            return None
        if not keywords:
            keywords = [name]
        return {
            "name": name,
            "keywords": keywords,
            "hit_count": int(raw.get("hit_count", 0) or 0),
            "last_hit_at": raw.get("last_hit_at"),
            "matched_feeds": dict(raw.get("matched_feeds", {})),
            "sample_items": list(raw.get("sample_items", [])),
            "last_run_hits": int(raw.get("last_run_hits", 0) or 0),
        }
    return None


def load_watchlist(
    path: Path = DEFAULT_WATCHLIST_PATH, defaults: list[Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"schema": WATCHLIST_SCHEMA, "topics": []}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {"schema": WATCHLIST_SCHEMA, "topics": []}
    raw_topics: list[Any] = []
    if isinstance(payload, dict) and payload.get("schema") == WATCHLIST_SCHEMA:
        maybe_topics = payload.get("topics", [])
        raw_topics = maybe_topics if isinstance(maybe_topics, list) else []
    elif isinstance(payload, dict):
        maybe_topics = payload.get("topics", [])
        raw_topics = maybe_topics if isinstance(maybe_topics, list) else []
    topics = []
    seen_names: set[str] = set()
    for raw in raw_topics:
        topic = _normalize_topic_entry(raw)
        if not topic:
            continue
        seen_names.add(str(topic["name"]).casefold())
        topics.append(topic)
    for raw in defaults or []:
        topic = _normalize_topic_entry(raw)
        if not topic:
            continue
        if str(topic["name"]).casefold() in seen_names:
            continue
        topics.append(topic)
        seen_names.add(str(topic["name"]).casefold())
    return {"schema": WATCHLIST_SCHEMA, "topics": topics}


def save_watchlist(data: dict[str, Any], path: Path = DEFAULT_WATCHLIST_PATH) -> None:
    atomic_write_json(
        path,
        {
            "schema": WATCHLIST_SCHEMA,
            "updated_at": data.get("updated_at"),
            "topics": data.get("topics", []),
        },
    )


def init_watchlist(
    path: Path = DEFAULT_WATCHLIST_PATH, defaults: list[Any] | None = None
) -> dict[str, Any]:
    watchlist = load_watchlist(path=path, defaults=defaults)
    watchlist["updated_at"] = None
    save_watchlist(watchlist, path)
    return watchlist


def add_watch_topic(
    name: str,
    *,
    keywords: list[str] | None = None,
    path: Path = DEFAULT_WATCHLIST_PATH,
    defaults: list[Any] | None = None,
) -> dict[str, Any]:
    watchlist = load_watchlist(path=path, defaults=defaults)
    entry = _normalize_topic_entry({"name": name, "keywords": keywords or [name]})
    if entry is None:
        return watchlist
    topics = list(watchlist.get("topics", []))
    for index, topic in enumerate(topics):
        if str(topic.get("name", "")).casefold() == str(entry["name"]).casefold():
            preserved = dict(topic)
            preserved["keywords"] = entry["keywords"]
            topics[index] = preserved
            watchlist["topics"] = topics
            save_watchlist(watchlist, path)
            return watchlist
    topics.append(entry)
    watchlist["topics"] = topics
    save_watchlist(watchlist, path)
    return watchlist


def remove_watch_topic(
    name: str,
    *,
    path: Path = DEFAULT_WATCHLIST_PATH,
    defaults: list[Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    watchlist = load_watchlist(path=path, defaults=defaults)
    topics = list(watchlist.get("topics", []))
    kept_topics = [
        topic
        for topic in topics
        if str(topic.get("name", "")).casefold() != name.casefold()
    ]
    removed = len(kept_topics) != len(topics)
    watchlist["topics"] = kept_topics
    save_watchlist(watchlist, path)
    return watchlist, removed


def reset_watchlist(
    *,
    path: Path = DEFAULT_WATCHLIST_PATH,
    defaults: list[Any] | None = None,
    topic_name: str | None = None,
) -> tuple[dict[str, Any], bool]:
    watchlist = load_watchlist(path=path, defaults=defaults)
    changed = False
    topics = list(watchlist.get("topics", []))
    for topic in topics:
        if (
            topic_name
            and str(topic.get("name", "")).casefold() != topic_name.casefold()
        ):
            continue
        topic["hit_count"] = 0
        topic["last_hit_at"] = None
        topic["matched_feeds"] = {}
        topic["sample_items"] = []
        topic["last_run_hits"] = 0
        changed = True
    watchlist["topics"] = topics
    save_watchlist(watchlist, path)
    return watchlist, changed


def match_watch_topics(
    item: NewsItem, topics: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    haystack = f"{item.title} {item.summary} {item.source}".lower()
    matched: list[dict[str, Any]] = []
    for topic in topics:
        keywords = [str(x).lower() for x in topic.get("keywords", [])]
        if any(keyword and keyword in haystack for keyword in keywords):
            matched.append(topic)
    return matched


def _append_sample_item(topic: dict[str, Any], item: NewsItem, seen_at: str) -> None:
    samples = list(topic.get("sample_items", []))
    sample = {
        "title": item.title,
        "link": item.link,
        "source": item.source,
        "matched_at": seen_at,
        "score": round(float(item.item_quality_score), 2),
    }
    dedupe_key = f"{sample['title']}::{sample['link']}"
    filtered = [
        row
        for row in samples
        if f"{row.get('title', '')}::{row.get('link', '')}" != dedupe_key
    ]
    filtered.insert(0, sample)
    topic["sample_items"] = filtered[:MAX_SAMPLE_ITEMS]


def update_watchlist_from_items(
    watchlist: dict[str, Any],
    items: list[NewsItem],
    seen_at: str,
) -> dict[str, Any]:
    topics = list(watchlist.get("topics", []))
    for topic in topics:
        topic["last_run_hits"] = 0
    for item in items:
        for topic in match_watch_topics(item, topics):
            topic["hit_count"] = int(topic.get("hit_count", 0)) + 1
            topic["last_run_hits"] = int(topic.get("last_run_hits", 0)) + 1
            topic["last_hit_at"] = seen_at
            matched_feeds = dict(topic.get("matched_feeds", {}))
            matched_feeds[item.source_feed] = (
                int(matched_feeds.get(item.source_feed, 0)) + 1
            )
            topic["matched_feeds"] = matched_feeds
            _append_sample_item(topic, item, seen_at)
    watchlist["schema"] = WATCHLIST_SCHEMA
    watchlist["updated_at"] = seen_at
    watchlist["topics"] = topics
    return watchlist


def update_watchlist_from_batch(
    input_path: Path,
    *,
    watchlist_path: Path = DEFAULT_WATCHLIST_PATH,
    defaults: list[Any] | None = None,
    seen_at: str,
) -> dict[str, Any]:
    watchlist = load_watchlist(watchlist_path, defaults=defaults)
    items = load_input_items(input_path)
    updated = update_watchlist_from_items(watchlist, items, seen_at)
    save_watchlist(updated, watchlist_path)
    return updated
