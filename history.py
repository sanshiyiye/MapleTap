from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from analyze_batch import load_input_items
from fetch_batch import DEFAULT_SCORES_FILE, load_feed_scores
from state_utils import atomic_write_json
from watchlist import DEFAULT_WATCHLIST_PATH, load_watchlist


ROOT = Path(__file__).resolve().parent
DEFAULT_HISTORY_DIR = ROOT / "history"


def build_run_snapshot(
    *,
    topic: str,
    input_path: Path,
    output_path: Path | None,
    scores_file: Path = DEFAULT_SCORES_FILE,
    watchlist_path: Path = DEFAULT_WATCHLIST_PATH,
    errors: list[str] | None = None,
    source_stats: list[dict[str, object]] | None = None,
) -> dict[str, Any]:
    generated_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    scores = load_feed_scores(scores_file)
    watchlist = load_watchlist(watchlist_path)
    items = load_input_items(input_path)
    top_items = sorted(
        items,
        key=lambda item: (
            -float(getattr(item, "item_quality_score", 0.0)),
            item.title.lower(),
        ),
    )[:5]
    feeds = []
    for feed_url, record in sorted(
        scores.items(), key=lambda item: (-float(item[1].get("score", 0.0)), item[0])
    ):
        feeds.append(
            {
                "feed_url": feed_url,
                "source": record.get("source", feed_url),
                "score": round(float(record.get("score", 0.0)), 2),
                "quality_score": round(float(record.get("quality_score", 0.0)), 2),
                "avg_item_score": round(float(record.get("avg_item_score", 0.0)), 2),
                "duplicate_rate": round(float(record.get("duplicate_rate", 0.0)), 4),
                "last_status": record.get("last_status", "unknown"),
            }
        )
    return {
        "schema": "history_snapshot.v1",
        "generated_at": generated_at,
        "topic": topic,
        "input_path": str(input_path),
        "output_path": str(output_path) if output_path else None,
        "feeds": feeds,
        "watchlist": watchlist,
        "top_items": [
            {
                "title": item.title,
                "source": item.source,
                "source_feed": item.source_feed,
                "item_quality_score": round(float(item.item_quality_score), 2),
                "relevance_score": round(float(item.relevance_score), 2),
                "duplicate_count": int(item.duplicate_count),
                "link": item.link,
            }
            for item in top_items
        ],
        "errors": list(errors or []),
        "source_stats": list(source_stats or []),
    }


def save_history_snapshot(
    snapshot: dict[str, Any], history_dir: Path = DEFAULT_HISTORY_DIR
) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    timestamp = str(snapshot.get("generated_at", "")).replace(":", "").replace("-", "")
    timestamp = timestamp.replace("T", "-").replace(
        "Z", ""
    ) or datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    path = history_dir / f"{timestamp}-snapshot.json"
    atomic_write_json(path, snapshot)
    return path


def list_history_snapshots(history_dir: Path = DEFAULT_HISTORY_DIR) -> list[Path]:
    if not history_dir.exists():
        return []
    return sorted(history_dir.glob("*-snapshot.json"), key=lambda path: path.name)


def load_snapshot(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def load_latest_snapshots(
    history_dir: Path = DEFAULT_HISTORY_DIR,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    snapshots = list_history_snapshots(history_dir)
    if not snapshots:
        return None, None
    latest = load_snapshot(snapshots[-1])
    previous = load_snapshot(snapshots[-2]) if len(snapshots) >= 2 else None
    return latest, previous
