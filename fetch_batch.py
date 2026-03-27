from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from typing import Any, Sequence, cast

from dedupe import canonicalize_url, dedupe_items, normalize_title
from logging_utils import setup_logger
from policies.fetch_policy import (
    LOW_SIGNAL_KEYWORDS,
    LOW_SIGNAL_PATTERNS,
    TOPIC_KEYWORDS,
)
from policies.scoring_policy import (
    get_effective_limit,
    score_item_quality,
    summarize_item_scores,
)
from settings import load_settings
from state_utils import atomic_write_json, atomic_write_text

ROOT = Path(__file__).resolve().parent
DEFAULT_FEEDS_FILE = ROOT / "feeds.txt"
DEFAULT_OUTPUT_DIR = ROOT / "inputs"
DEFAULT_SCORES_FILE = ROOT / "feed_scores.json"
FEED_SCORES_SCHEMA = "feed_scores.v1"


@dataclass
class FeedItem:
    title: str
    source: str
    source_feed_url: str
    date: str
    link: str
    item_type: str
    summary: str
    canonical_url: str = ""
    normalized_title: str = ""
    dedupe_key: str = ""
    dedupe_group_id: str = ""
    duplicate_count: int = 0
    duplicate_sources: list[str] | None = None
    duplicate_reason: str = ""
    relevance_reason: str = ""
    recency_score: float = 0.0
    authority_score: float = 0.0
    relevance_score: float = 0.0
    convergence_score: float = 0.0
    novelty_score: float = 0.0
    item_quality_score: float = 0.0


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def load_feed_urls(path: Path) -> list[str]:
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def load_feed_scores(path: Path = DEFAULT_SCORES_FILE) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict) and payload.get("schema") == FEED_SCORES_SCHEMA:
        records = payload.get("records", {})
        return records if isinstance(records, dict) else {}
    if isinstance(payload, dict):
        return {
            str(feed_url): record
            for feed_url, record in payload.items()
            if isinstance(record, dict)
        }
    return {}


def save_feed_scores(scores: dict[str, dict], path: Path = DEFAULT_SCORES_FILE) -> None:
    atomic_write_json(
        path,
        {
            "schema": FEED_SCORES_SCHEMA,
            "updated_at": utc_now_iso(),
            "records": scores,
        },
    )


def get_feed_score(scores: dict[str, dict], feed_url: str) -> float:
    record = scores.get(feed_url, {})
    return float(record.get("score", 50.0))


def enrich_item_metadata(item: FeedItem) -> FeedItem:
    item.canonical_url = canonicalize_url(item.link)
    item.normalized_title = normalize_title(item.title)
    item.dedupe_key = (
        f"{item.canonical_url}::{item.normalized_title}"
        if item.canonical_url
        else item.normalized_title
    )
    if item.duplicate_sources is None:
        item.duplicate_sources = []
    return item


def apply_item_scores(
    items: Sequence[FeedItem],
    *,
    topic: str,
    scoring_weights: dict[str, float],
    authority_overrides: dict[str, float],
) -> list[FeedItem]:
    scored_items = list(items)
    for item in scored_items:
        result = score_item_quality(
            item,
            scored_items,
            topic,
            scoring_weights=scoring_weights,
            authority_overrides=authority_overrides,
        )
        item.recency_score = _safe_float(result["recency_score"])
        item.authority_score = _safe_float(result["authority_score"])
        item.relevance_score = _safe_float(result["relevance_score"])
        item.convergence_score = _safe_float(result["convergence_score"])
        item.novelty_score = _safe_float(result["novelty_score"])
        item.item_quality_score = _safe_float(result["item_quality_score"])
        item.relevance_reason = str(result["relevance_reason"])
    return scored_items


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def order_feed_urls(feed_urls: list[str], scores: dict[str, dict]) -> list[str]:
    ordered = sorted(feed_urls, key=lambda url: (-get_feed_score(scores, url), url))
    if len(ordered) <= 3:
        return ordered

    locked = ordered[:2]
    remainder = ordered[2:]
    remainder.sort(
        key=lambda url: (
            int(scores.get(url, {}).get("attempts", 0)),
            get_feed_score(scores, url),
            url,
        )
    )
    explore_pick = remainder.pop(0) if remainder else None
    return locked + ([explore_pick] if explore_pick else []) + remainder


def update_feed_record(
    existing: dict,
    *,
    source_name: str,
    fetched: int,
    kept: int,
    filtered: int,
    status: str,
    item_score_summary: dict[str, float] | None = None,
    duplicate_rate: float = 0.0,
) -> dict:
    record = dict(existing) if existing else {}
    attempts = int(record.get("attempts", 0)) + 1
    successes = int(record.get("successes", 0)) + (1 if status == "ok" else 0)
    total_fetched = int(record.get("total_fetched", 0)) + fetched
    total_kept = int(record.get("total_kept", 0)) + kept
    total_filtered = int(record.get("total_filtered", 0)) + filtered
    success_rate = successes / attempts if attempts else 0.0
    kept_rate = total_kept / total_fetched if total_fetched else 0.0
    volume_factor = min(total_kept / 20.0, 1.0)
    stability_score = round(
        100 * (0.45 * success_rate + 0.4 * kept_rate + 0.15 * volume_factor), 2
    )
    summary = item_score_summary or {}
    avg_item_score = _safe_float(
        summary.get("avg_item_score", record.get("avg_item_score", 0.0))
    )
    avg_relevance_score = _safe_float(
        summary.get("avg_relevance_score", record.get("avg_relevance_score", 0.0))
    )
    avg_authority_score = _safe_float(
        summary.get("avg_authority_score", record.get("avg_authority_score", 0.0))
    )
    avg_recency_score = _safe_float(
        summary.get("avg_recency_score", record.get("avg_recency_score", 0.0))
    )
    avg_convergence_score = _safe_float(
        summary.get("avg_convergence_score", record.get("avg_convergence_score", 0.0))
    )
    avg_novelty_score = _safe_float(
        summary.get("avg_novelty_score", record.get("avg_novelty_score", 0.0))
    )
    content_quality_score = avg_item_score if avg_item_score > 0 else stability_score
    quality_score = round(0.45 * stability_score + 0.55 * content_quality_score, 2)
    analysis_value_score = float(record.get("analysis_value_score", 50.0))
    score = round(0.7 * quality_score + 0.3 * analysis_value_score, 2)
    top_strengths: list[str] = []
    main_penalties: list[str] = []
    if avg_relevance_score >= 80:
        top_strengths.append("high_relevance")
    if avg_authority_score >= 80:
        top_strengths.append("high_authority")
    if avg_convergence_score >= 75:
        top_strengths.append("strong_convergence")
    if avg_novelty_score < 65:
        main_penalties.append("duplicate_pressure")
    if duplicate_rate >= 0.25:
        main_penalties.append("high_duplicate_rate")
    if kept_rate < 0.25:
        main_penalties.append("low_kept_rate")

    record.update(
        {
            "source": source_name,
            "attempts": attempts,
            "successes": successes,
            "total_fetched": total_fetched,
            "total_kept": total_kept,
            "total_filtered": total_filtered,
            "success_rate": round(success_rate, 4),
            "kept_rate": round(kept_rate, 4),
            "duplicate_rate": round(float(duplicate_rate), 4),
            "stability_score": stability_score,
            "avg_item_score": round(avg_item_score, 2),
            "avg_relevance_score": round(avg_relevance_score, 2),
            "avg_authority_score": round(avg_authority_score, 2),
            "avg_recency_score": round(avg_recency_score, 2),
            "avg_convergence_score": round(avg_convergence_score, 2),
            "avg_novelty_score": round(avg_novelty_score, 2),
            "quality_score": quality_score,
            "analysis_value_score": analysis_value_score,
            "score": score,
            "top_strengths": top_strengths,
            "main_penalties": main_penalties,
            "last_status": status,
            "last_updated": utc_now_iso(),
        }
    )
    return record


def fetch_feed(
    url: str, timeout: int = 20, retries: int = 2, retry_delay: float = 1.5
) -> bytes:
    last_error: Exception | None = None
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    }
    for attempt in range(retries + 1):
        try:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(retry_delay * (attempt + 1))
    if last_error is None:
        raise RuntimeError(f"Unknown fetch failure for {url}")
    raise last_error


def normalize_text(value: str | None, limit: int = 280) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(value))
    text = " ".join(text.split())
    return text[:limit].strip()


def is_relevant_item(item: FeedItem) -> tuple[bool, str]:
    haystack = f"{item.title} {item.summary}".lower()
    if any(re.search(pattern, haystack) for pattern in LOW_SIGNAL_PATTERNS):
        return False, "low_signal_pattern"
    if any(keyword in haystack for keyword in LOW_SIGNAL_KEYWORDS):
        return False, "low_signal_keyword"
    if any(keyword in haystack for keyword in TOPIC_KEYWORDS):
        return True, "topic_match"
    if item.source.lower() == "hacker news":
        return True, "hn_keep"
    return False, "no_topic_match"


def strip_tag(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def find_child_text(element: ET.Element, *names: str) -> str:
    wanted = set(names)
    for child in list(element):
        if strip_tag(child.tag) in wanted:
            raw = "".join(child.itertext()).strip() or (child.text or "").strip()
            return normalize_text(raw)
    return ""


def _rss_regex_tag_inner(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}\b[^>]*>([\s\S]*?)</{tag}\s*>", block, re.I)
    if not m:
        return ""
    inner = m.group(1).strip()
    if inner.startswith("<![CDATA[") and inner.endswith("]]>"):
        inner = inner[9:-3].strip()
    return inner.strip()


def _parse_feed_rss_regex(
    content: bytes, feed_url: str, limit: int
) -> tuple[str, list[FeedItem]]:
    """Last-resort RSS 2.0 parse when ElementTree rejects the XML (e.g. mismatched tags)."""
    text = content.decode("utf-8", errors="replace")
    if "<rss" not in text[:2000].lower():
        return feed_url, []

    src_m = re.search(
        r"<channel\b[^>]*>[\s\S]*?<title\b[^>]*>([\s\S]*?)</title\s*>", text, re.I
    )
    source = normalize_text(src_m.group(1)) if src_m else feed_url

    items: list[FeedItem] = []
    for m in re.finditer(r"<item\b[\s\S]*?</item\s*>", text, re.I):
        block = m.group(0)
        title_raw = _rss_regex_tag_inner(block, "title") or "(untitled)"
        link_raw = _rss_regex_tag_inner(block, "link")
        date_raw = (
            _rss_regex_tag_inner(block, "pubDate")
            or _rss_regex_tag_inner(block, "published")
            or "unknown"
        )
        desc_raw = _rss_regex_tag_inner(block, "description") or _rss_regex_tag_inner(
            block, "summary"
        )
        items.append(
            FeedItem(
                title=normalize_text(title_raw) or "(untitled)",
                source=source,
                source_feed_url=feed_url,
                date=normalize_text(date_raw) or "unknown",
                link=normalize_text(link_raw),
                item_type="RSS entry",
                summary=normalize_text(desc_raw) or normalize_text(title_raw),
            )
        )
        if len(items) >= limit:
            break
    return source, items


def _parse_feed_elementtree(
    content: bytes, feed_url: str, limit: int
) -> tuple[str, list[FeedItem]]:
    root = ET.fromstring(content)
    root_name = strip_tag(root.tag).lower()

    if root_name == "rss":
        channel = next(
            (child for child in list(root) if strip_tag(child.tag) == "channel"), None
        )
        if channel is None:
            return feed_url, []

        source = find_child_text(channel, "title") or feed_url
        items: list[FeedItem] = []
        for item in [
            child for child in list(channel) if strip_tag(child.tag) == "item"
        ][:limit]:
            items.append(
                FeedItem(
                    title=find_child_text(item, "title") or "(untitled)",
                    source=source,
                    source_feed_url=feed_url,
                    date=find_child_text(item, "pubDate", "published", "updated")
                    or "unknown",
                    link=find_child_text(item, "link"),
                    item_type="RSS entry",
                    summary=find_child_text(item, "description", "summary")
                    or find_child_text(item, "title"),
                )
            )
        return source, items

    if root_name == "feed":
        source = find_child_text(root, "title") or feed_url
        items: list[FeedItem] = []
        for entry in [child for child in list(root) if strip_tag(child.tag) == "entry"][
            :limit
        ]:
            link = ""
            for child in list(entry):
                if strip_tag(child.tag) != "link":
                    continue
                href = child.attrib.get("href")
                if href:
                    link = href
                    break
                if child.text:
                    link = normalize_text(child.text)
                    break
            items.append(
                FeedItem(
                    title=find_child_text(entry, "title") or "(untitled)",
                    source=source,
                    source_feed_url=feed_url,
                    date=find_child_text(entry, "published", "updated") or "unknown",
                    link=link,
                    item_type="Atom entry",
                    summary=find_child_text(entry, "summary", "content")
                    or find_child_text(entry, "title"),
                )
            )
        return source, items

    return feed_url, []


def parse_feed(content: bytes, feed_url: str, limit: int) -> tuple[str, list[FeedItem]]:
    try:
        return _parse_feed_elementtree(content, feed_url, limit)
    except ET.ParseError:
        return _parse_feed_rss_regex(content, feed_url, limit)


def _response_looks_like_html(content: bytes) -> bool:
    head = content.lstrip()[:800].lower()
    return head.startswith(b"<html") or head.startswith(b"<!doctype html")


def extract_items(
    feed_url: str,
    limit: int,
    timeout: int,
    retries: int,
    retry_delay: float,
) -> tuple[list[FeedItem], str | None]:
    try:
        content = fetch_feed(
            feed_url, timeout=timeout, retries=retries, retry_delay=retry_delay
        )
        _source, items = parse_feed(content, feed_url, limit)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return [], f"{feed_url} -> {type(exc).__name__}: {exc}"
    if not items:
        if _response_looks_like_html(content):
            return (
                [],
                f"{feed_url} -> HTML response (blocked/captcha/wrong URL), not RSS",
            )
        return [], f"{feed_url} -> no parsable entries found"

    for item in items:
        if item.summary.lower() == "comments":
            item.summary = item.title
    return items, None


def render_markdown(
    topic: str,
    items: Iterable[FeedItem],
    errors: list[str],
    source_stats: list[dict[str, str | int | float]],
    dedupe_groups: list[dict[str, object]] | None = None,
) -> str:
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# RSS Input Batch",
        "",
        "## Batch Metadata",
        f"- Topic: {topic}",
        f"- Collected At: {collected_at}",
        "- Collector: fetch_batch.py",
        "- Notes: Auto-generated from RSS feeds in the isolated experiment area.",
        "",
        "## Source Stats",
        "",
    ]

    for stat in source_stats:
        lines.append(
            f"- {stat['feed_url']} | source={stat['source']} | fetched={stat['fetched']} | kept={stat['kept']} | filtered={stat['filtered']} | status={stat['status']} | previous_score={stat['previous_score']} | current_score={stat['current_score']} | effective_limit={stat['effective_limit']} | duplicate_rate={stat.get('duplicate_rate', 0.0)} | avg_item_score={stat.get('avg_item_score', 0.0)}"
        )

    if dedupe_groups:
        lines.extend(["", "## Dedupe Summary", ""])
        for group in dedupe_groups:
            member_count = int(_safe_float(group.get("member_count", 1), 1.0))
            raw_sources = group.get("sources", [])
            sources = (
                [str(source) for source in raw_sources]
                if isinstance(raw_sources, list)
                else []
            )
            if member_count <= 1:
                continue
            lines.append(
                f"- group={group['group_id']} | members={member_count} | reason={group['reason']} | sources={', '.join(sources)} | title={group['representative_title']}"
            )

    lines.extend(["", "## Items", ""])

    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"### {index}. {item.title}",
                f"- Source: {item.source}",
                f"- Source Feed: {item.source_feed_url}",
                f"- Date: {item.date}",
                f"- Link: {item.link}",
                f"- Canonical URL: {item.canonical_url}",
                f"- Type: {item.item_type}",
                f"- Summary: {item.summary}",
                f"- Duplicate Count: {item.duplicate_count}",
                f"- Duplicate Sources: {', '.join(item.duplicate_sources or []) or '-'}",
                f"- Duplicate Reason: {item.duplicate_reason or '-'}",
                f"- Item Quality Score: {item.item_quality_score:.2f}",
                f"- Score Breakdown: recency={item.recency_score:.2f} authority={item.authority_score:.2f} relevance={item.relevance_score:.2f} convergence={item.convergence_score:.2f} novelty={item.novelty_score:.2f}",
                f"- Relevance Reason: {item.relevance_reason or '-'}",
                "",
            ]
        )

    if errors:
        lines.extend(["## Fetch Errors", ""])
        for error in errors:
            lines.append(f"- {error}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_batch_json(
    topic: str,
    output_path: Path,
    items: list[FeedItem],
    errors: list[str],
    source_stats: list[dict[str, str | int | float]],
    dedupe_groups: list[dict[str, object]] | None = None,
) -> dict:
    return {
        "schema": "rss_batch.json",
        "topic": topic,
        "generated_at": utc_now_iso(),
        "markdown_path": str(output_path),
        "item_count": len(items),
        "error_count": len(errors),
        "source_stats": source_stats,
        "dedupe_groups": dedupe_groups or [],
        "items": [asdict(item) for item in items],
        "errors": errors,
    }


def write_batch_outputs(
    output_path: Path,
    topic: str,
    items: list[FeedItem],
    errors: list[str],
    source_stats: list[dict[str, str | int | float]],
    dedupe_groups: list[dict[str, object]] | None = None,
) -> None:
    atomic_write_text(
        output_path,
        render_markdown(
            topic, items, errors, source_stats, dedupe_groups=dedupe_groups
        ),
    )
    atomic_write_json(
        output_path.with_suffix(".json"),
        build_batch_json(
            topic, output_path, items, errors, source_stats, dedupe_groups=dedupe_groups
        ),
    )


def run_fetch(
    feeds_file: Path = DEFAULT_FEEDS_FILE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    topic: str = "General RSS batch",
    per_feed_limit: int = 5,
    output_name: str | None = None,
    timeout: int = 20,
    retries: int = 2,
    retry_delay: float = 1.5,
    scores_file: Path = DEFAULT_SCORES_FILE,
    log_level: str | None = None,
) -> tuple[Path, int, list[str], list[dict[str, str | int | float]]]:
    settings = load_settings()
    logger = setup_logger(
        "rss_agent.fetch", log_level or str(settings.get("log_level", "INFO"))
    )
    scoring_weights = dict(settings.get("scoring_weights", {}))
    authority_overrides = dict(settings.get("source_authority_overrides", {}))
    dedupe_similarity_threshold = float(
        settings.get("dedupe_similarity_threshold", 0.82)
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    feed_urls = load_feed_urls(feeds_file)
    score_state = load_feed_scores(scores_file)
    ordered_feed_urls = order_feed_urls(feed_urls, score_state)
    all_items: list[FeedItem] = []
    errors: list[str] = []
    source_stats: list[dict[str, str | int | float]] = []
    all_dedupe_groups: list[dict[str, object]] = []

    for feed_url in ordered_feed_urls:
        previous_score = get_feed_score(score_state, feed_url)
        previous_record = score_state.get(feed_url, {})
        effective_limit = get_effective_limit(
            per_feed_limit, previous_score, int(previous_record.get("attempts", 0))
        )
        items, error = extract_items(
            feed_url,
            effective_limit,
            timeout=timeout,
            retries=retries,
            retry_delay=retry_delay,
        )

        if error:
            logger.warning("fetch_failed feed=%s error=%s", feed_url, error)
            errors.append(error)
            updated_record = update_feed_record(
                score_state.get(feed_url, {}),
                source_name=feed_url,
                fetched=0,
                kept=0,
                filtered=0,
                status="error",
            )
            score_state[feed_url] = updated_record
            source_stats.append(
                {
                    "feed_url": feed_url,
                    "source": feed_url,
                    "fetched": 0,
                    "kept": 0,
                    "filtered": 0,
                    "status": "error",
                    "previous_score": previous_score,
                    "current_score": updated_record["score"],
                    "effective_limit": effective_limit,
                }
            )
            continue

        kept_items: list[FeedItem] = []
        filtered_count = 0
        for item in items:
            enrich_item_metadata(item)
            keep, _reason = is_relevant_item(item)
            if keep:
                item.relevance_reason = _reason
                kept_items.append(item)
            else:
                filtered_count += 1

        feed_dedupe = dedupe_items(
            kept_items, similarity_threshold=dedupe_similarity_threshold
        )
        deduped_items = apply_item_scores(
            cast(list[FeedItem], list(feed_dedupe.kept_items)),
            topic=topic,
            scoring_weights=scoring_weights,
            authority_overrides=authority_overrides,
        )
        item_score_summary = summarize_item_scores(deduped_items)
        dedupe_filtered = int(feed_dedupe.stats.get("removed_count", 0))
        source_name = items[0].source if items else feed_url
        updated_record = update_feed_record(
            score_state.get(feed_url, {}),
            source_name=source_name,
            fetched=len(items),
            kept=len(deduped_items),
            filtered=filtered_count + dedupe_filtered,
            status="ok",
            item_score_summary=item_score_summary,
            duplicate_rate=float(feed_dedupe.stats.get("duplicate_rate", 0.0)),
        )
        score_state[feed_url] = updated_record
        source_stats.append(
            {
                "feed_url": feed_url,
                "source": source_name,
                "fetched": len(items),
                "kept": len(deduped_items),
                "filtered": filtered_count + dedupe_filtered,
                "status": "ok",
                "previous_score": previous_score,
                "current_score": updated_record["score"],
                "effective_limit": effective_limit,
                "duplicate_rate": updated_record["duplicate_rate"],
                "avg_item_score": updated_record["avg_item_score"],
                "avg_relevance_score": updated_record["avg_relevance_score"],
                "avg_authority_score": updated_record["avg_authority_score"],
                "avg_convergence_score": updated_record["avg_convergence_score"],
            }
        )
        all_items.extend(deduped_items)
        all_dedupe_groups.extend(feed_dedupe.groups)

    global_dedupe = dedupe_items(
        all_items, similarity_threshold=dedupe_similarity_threshold
    )
    all_items = apply_item_scores(
        cast(list[FeedItem], list(global_dedupe.kept_items)),
        topic=topic,
        scoring_weights=scoring_weights,
        authority_overrides=authority_overrides,
    )
    all_dedupe_groups.extend(global_dedupe.groups)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    output_name = output_name or f"{timestamp}-rss-batch.md"
    output_path = output_dir / output_name
    write_batch_outputs(
        output_path,
        topic,
        all_items,
        errors,
        source_stats,
        dedupe_groups=all_dedupe_groups,
    )
    save_feed_scores(score_state, scores_file)
    logger.info(
        "fetch_completed output=%s items=%s errors=%s",
        output_path,
        len(all_items),
        len(errors),
    )
    return output_path, len(all_items), errors, source_stats


def main() -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(
        description="Fetch RSS feeds into normalized Markdown and JSON batches."
    )
    parser.add_argument("--feeds-file", default=str(DEFAULT_FEEDS_FILE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--topic", default=str(settings["topic"]))
    parser.add_argument(
        "--per-feed-limit", type=int, default=int(settings["per_feed_limit"])
    )
    parser.add_argument("--output-name", default=None)
    parser.add_argument("--timeout", type=int, default=int(settings["timeout"]))
    parser.add_argument("--retries", type=int, default=int(settings["retries"]))
    parser.add_argument(
        "--retry-delay", type=float, default=float(settings["retry_delay"])
    )
    parser.add_argument("--scores-file", default=str(DEFAULT_SCORES_FILE))
    parser.add_argument("--log-level", default=str(settings["log_level"]))
    args = parser.parse_args()

    output_path, item_count, errors, source_stats = run_fetch(
        feeds_file=Path(args.feeds_file),
        output_dir=Path(args.output_dir),
        topic=args.topic,
        per_feed_limit=args.per_feed_limit,
        output_name=args.output_name,
        timeout=args.timeout,
        retries=args.retries,
        retry_delay=args.retry_delay,
        scores_file=Path(args.scores_file),
        log_level=args.log_level,
    )

    print(f"saved={output_path}")
    print(f"saved_json={output_path.with_suffix('.json')}")
    print(f"items={item_count}")
    if errors:
        print(f"errors={len(errors)}")
        for error in errors:
            print(error)
    for stat in source_stats:
        print(
            f"source={stat['source']} fetched={stat['fetched']} kept={stat['kept']} filtered={stat['filtered']} status={stat['status']} previous_score={stat['previous_score']} current_score={stat['current_score']} effective_limit={stat['effective_limit']}"
        )
    return 0 if item_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
