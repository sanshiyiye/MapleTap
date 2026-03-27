from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any


DEFAULT_SOURCE_AUTHORITY = {
    "hacker news": 88.0,
    "the github blog": 92.0,
    "github blog": 92.0,
    "techcrunch": 74.0,
    "36kr": 68.0,
    "wired": 60.0,
    "mit technology review": 82.0,
}

SOURCE_WEIGHT_HINTS = {
    name: int(score - 60.0) for name, score in DEFAULT_SOURCE_AUTHORITY.items()
}


def get_effective_limit(base_limit: int, score: float, attempts: int) -> int:
    if attempts < 2:
        return base_limit
    if score >= 85:
        return base_limit
    if score >= 75:
        return max(3, base_limit - 1)
    if score >= 60:
        return max(2, base_limit - 2)
    return 2


def parse_item_datetime(date_text: str) -> datetime | None:
    raw = (date_text or "").strip()
    if not raw or raw.lower() == "unknown":
        return None
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        normalized = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def score_recency(date_text: str, now: datetime | None = None) -> float:
    published_at = parse_item_datetime(date_text)
    if published_at is None:
        return 55.0
    current = now or datetime.now(timezone.utc)
    age_hours = max(0.0, (current - published_at).total_seconds() / 3600.0)
    if age_hours <= 24:
        return 95.0
    if age_hours <= 72:
        return 88.0
    if age_hours <= 7 * 24:
        return 78.0
    if age_hours <= 14 * 24:
        return 68.0
    if age_hours <= 30 * 24:
        return 58.0
    return 42.0


def score_source_authority(
    source: str,
    source_feed_url: str = "",
    authority_overrides: dict[str, float] | None = None,
) -> float:
    lookup = dict(DEFAULT_SOURCE_AUTHORITY)
    if authority_overrides:
        for key, value in authority_overrides.items():
            try:
                lookup[str(key).lower()] = float(value)
            except Exception:
                continue
    source_key = (source or "").strip().lower()
    feed_key = (source_feed_url or "").strip().lower()
    if source_key in lookup:
        return lookup[source_key]
    if feed_key in lookup:
        return lookup[feed_key]
    return 62.0


def _topic_tokens(topic: str) -> list[str]:
    tokens = []
    for raw in (topic or "").lower().replace("/", " ").replace(",", " ").split():
        token = raw.strip()
        if len(token) >= 3:
            tokens.append(token)
    return tokens


def score_topic_relevance(title: str, summary: str, topic: str) -> tuple[float, str]:
    haystack = f"{title} {summary}".lower()
    topic_tokens = _topic_tokens(topic)
    if not topic_tokens:
        return 60.0, "no_topic_tokens"
    matched = [token for token in topic_tokens if token in haystack]
    match_ratio = len(set(matched)) / len(set(topic_tokens)) if topic_tokens else 0.0
    score = 45.0 + match_ratio * 50.0
    if title:
        title_lower = title.lower()
        title_hits = sum(1 for token in set(topic_tokens) if token in title_lower)
        score += min(10.0, title_hits * 4.0)
    return round(min(100.0, score), 2), (
        f"matched_topic_tokens={','.join(sorted(set(matched))) or 'none'}"
    )


def score_cross_source_convergence(item: Any, all_items: list[Any]) -> float:
    sources = {
        str(getattr(item, "source", "") or "")
        for other in all_items
        if other is not item
        and getattr(other, "dedupe_group_id", "")
        and getattr(other, "dedupe_group_id", "")
        == getattr(item, "dedupe_group_id", "")
        and str(getattr(other, "source", "") or "")
    }
    if str(getattr(item, "source", "") or ""):
        sources.add(str(getattr(item, "source", "") or ""))
    count = len(sources)
    if count >= 4:
        return 95.0
    if count == 3:
        return 85.0
    if count == 2:
        return 72.0
    return 50.0


def score_novelty(item: Any) -> float:
    duplicate_count = int(getattr(item, "duplicate_count", 0) or 0)
    if duplicate_count <= 0:
        return 92.0
    if duplicate_count == 1:
        return 78.0
    if duplicate_count == 2:
        return 66.0
    if duplicate_count == 3:
        return 54.0
    return 42.0


def summarize_item_scores(items: list[Any]) -> dict[str, float]:
    if not items:
        return {
            "avg_item_score": 0.0,
            "avg_relevance_score": 0.0,
            "avg_authority_score": 0.0,
            "avg_recency_score": 0.0,
            "avg_convergence_score": 0.0,
            "avg_novelty_score": 0.0,
        }
    count = float(len(items))
    return {
        "avg_item_score": round(
            sum(
                float(getattr(item, "item_quality_score", 0.0) or 0.0) for item in items
            )
            / count,
            2,
        ),
        "avg_relevance_score": round(
            sum(float(getattr(item, "relevance_score", 0.0) or 0.0) for item in items)
            / count,
            2,
        ),
        "avg_authority_score": round(
            sum(float(getattr(item, "authority_score", 0.0) or 0.0) for item in items)
            / count,
            2,
        ),
        "avg_recency_score": round(
            sum(float(getattr(item, "recency_score", 0.0) or 0.0) for item in items)
            / count,
            2,
        ),
        "avg_convergence_score": round(
            sum(float(getattr(item, "convergence_score", 0.0) or 0.0) for item in items)
            / count,
            2,
        ),
        "avg_novelty_score": round(
            sum(float(getattr(item, "novelty_score", 0.0) or 0.0) for item in items)
            / count,
            2,
        ),
    }


def score_item_quality(
    item: Any,
    all_items: list[Any],
    topic: str,
    scoring_weights: dict[str, float] | None = None,
    authority_overrides: dict[str, float] | None = None,
) -> dict[str, float | str]:
    weights = {
        "relevance": 0.35,
        "authority": 0.20,
        "recency": 0.20,
        "convergence": 0.15,
        "novelty": 0.10,
    }
    if scoring_weights:
        for key, value in scoring_weights.items():
            if key in weights:
                weights[key] = float(value)

    recency_score = score_recency(str(getattr(item, "date", "") or ""))
    authority_score = score_source_authority(
        str(getattr(item, "source", "") or ""),
        str(
            getattr(item, "source_feed_url", "")
            or getattr(item, "source_feed", "")
            or ""
        ),
        authority_overrides=authority_overrides,
    )
    relevance_score, relevance_reason = score_topic_relevance(
        str(getattr(item, "title", "") or ""),
        str(getattr(item, "summary", "") or ""),
        topic,
    )
    convergence_score = score_cross_source_convergence(item, all_items)
    novelty_score = score_novelty(item)
    item_quality_score = round(
        relevance_score * weights["relevance"]
        + authority_score * weights["authority"]
        + recency_score * weights["recency"]
        + convergence_score * weights["convergence"]
        + novelty_score * weights["novelty"],
        2,
    )
    return {
        "recency_score": round(recency_score, 2),
        "authority_score": round(authority_score, 2),
        "relevance_score": round(relevance_score, 2),
        "convergence_score": round(convergence_score, 2),
        "novelty_score": round(novelty_score, 2),
        "item_quality_score": item_quality_score,
        "relevance_reason": relevance_reason,
    }
