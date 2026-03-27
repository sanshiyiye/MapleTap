from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Generic, Protocol, Sequence, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TITLE_SITE_SUFFIX_RE = re.compile(r"\s+(?:[-|:])\s+[^-|:]{2,40}$")
TITLE_NOISE_WORDS = {
    "a",
    "an",
    "and",
    "breaking",
    "exclusive",
    "live",
    "news",
    "report",
    "the",
    "update",
}
DEFAULT_TRACKING_PARAMS = {
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
}


T = TypeVar("T", bound="DedupeItem")


class DedupeItem(Protocol):
    source: str
    source_feed_url: str
    link: str
    title: str


@dataclass
class DedupeResult(Generic[T]):
    kept_items: list[T]
    removed_items: list[T]
    groups: list[dict[str, Any]]
    stats: dict[str, int | float]


def normalize_title(title: str) -> str:
    value = " ".join((title or "").strip().lower().split())
    value = TITLE_SITE_SUFFIX_RE.sub("", value)
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    tokens = [
        token for token in value.split() if token and token not in TITLE_NOISE_WORDS
    ]
    return " ".join(tokens)


def canonicalize_url(url: str, tracking_params: set[str] | None = None) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    params_to_strip = tracking_params or DEFAULT_TRACKING_PARAMS
    split = urlsplit(raw)
    scheme = (split.scheme or "https").lower()
    netloc = split.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = split.path.rstrip("/") or "/"
    filtered_pairs = []
    for key, value in parse_qsl(split.query, keep_blank_values=False):
        if key.lower() in params_to_strip:
            continue
        filtered_pairs.append((key, value))
    filtered_pairs.sort()
    query = urlencode(filtered_pairs, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def tokenize_title(title: str) -> list[str]:
    normalized = normalize_title(title)
    return [token for token in normalized.split() if token]


def jaccard_similarity(tokens_a: list[str], tokens_b: list[str]) -> float:
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    if not set_a or not set_b:
        return 0.0
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def title_similarity(a: str, b: str) -> float:
    return jaccard_similarity(tokenize_title(a), tokenize_title(b))


def build_dedupe_key(item: DedupeItem) -> str:
    canonical_url = canonicalize_url(item.link)
    normalized_title = normalize_title(item.title)
    return f"{item.source_feed_url.strip()}::{canonical_url}::{normalized_title}"


def _set_item_field(item: DedupeItem, field_name: str, value: Any) -> None:
    try:
        setattr(item, field_name, value)
    except Exception:
        pass


def _build_group_id(seed: str) -> str:
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"dup-{digest}"


def dedupe_items(
    items: Sequence[T],
    similarity_threshold: float = 0.82,
) -> DedupeResult[T]:
    kept_items: list[T] = []
    removed_items: list[T] = []
    groups: list[dict[str, Any]] = []
    exact_duplicates = 0
    same_url_duplicates = 0
    near_duplicates = 0

    seen_exact: set[tuple[str, str, str]] = set()
    representatives: list[dict[str, Any]] = []

    for item in items:
        canonical_url = canonicalize_url(item.link)
        normalized_title = normalize_title(item.title)
        dedupe_key = (
            f"{canonical_url}::{normalized_title}"
            if canonical_url
            else normalized_title
        )
        _set_item_field(item, "canonical_url", canonical_url)
        _set_item_field(item, "normalized_title", normalized_title)
        _set_item_field(item, "dedupe_key", dedupe_key)
        _set_item_field(item, "duplicate_count", 0)
        _set_item_field(item, "duplicate_sources", [])
        _set_item_field(item, "duplicate_reason", "")

        exact_key = (item.source_feed_url.strip(), canonical_url, normalized_title)
        if exact_key in seen_exact:
            exact_duplicates += 1
            removed_items.append(item)
            _set_item_field(item, "duplicate_reason", "exact")
            continue
        seen_exact.add(exact_key)

        matched_group: dict[str, Any] | None = None
        for group in representatives:
            group_url = str(group["canonical_url"])
            group_title = str(group["normalized_title"])
            if canonical_url and group_url and canonical_url == group_url:
                matched_group = group
                reason = "same_url"
                same_url_duplicates += 1
                break
            if (
                normalized_title
                and group_title
                and title_similarity(normalized_title, group_title)
                >= similarity_threshold
            ):
                matched_group = group
                reason = "near_title"
                near_duplicates += 1
                break
        else:
            reason = ""

        if matched_group is None:
            group_id = _build_group_id(canonical_url or normalized_title or item.title)
            group = {
                "group_id": group_id,
                "representative_title": item.title,
                "normalized_title": normalized_title,
                "canonical_url": canonical_url,
                "reason": "primary",
                "member_count": 1,
                "sources": {item.source},
                "items": [item],
            }
            representatives.append(group)
            kept_items.append(item)
            _set_item_field(item, "dedupe_group_id", group_id)
            continue

        matched_group["member_count"] += 1
        matched_group["sources"].add(item.source)
        matched_group["items"].append(item)
        matched_group["reason"] = reason
        rep = matched_group["items"][0]
        rep_sources = sorted(matched_group["sources"])
        _set_item_field(rep, "duplicate_count", matched_group["member_count"] - 1)
        _set_item_field(rep, "duplicate_sources", rep_sources)
        _set_item_field(rep, "duplicate_reason", reason)
        _set_item_field(rep, "dedupe_group_id", matched_group["group_id"])
        _set_item_field(item, "dedupe_group_id", matched_group["group_id"])
        _set_item_field(item, "duplicate_reason", reason)
        removed_items.append(item)

    for group in representatives:
        groups.append(
            {
                "group_id": group["group_id"],
                "representative_title": group["representative_title"],
                "canonical_url": group["canonical_url"],
                "member_count": group["member_count"],
                "sources": sorted(group["sources"]),
                "reason": group["reason"],
            }
        )

    total_duplicates = exact_duplicates + same_url_duplicates + near_duplicates
    stats: dict[str, int | float] = {
        "input_count": len(items),
        "kept_count": len(kept_items),
        "removed_count": len(removed_items),
        "exact_duplicates": exact_duplicates,
        "same_url_duplicates": same_url_duplicates,
        "near_duplicates": near_duplicates,
        "duplicate_rate": round(total_duplicates / len(items), 4) if items else 0.0,
    }
    return DedupeResult(
        kept_items=kept_items,
        removed_items=removed_items,
        groups=groups,
        stats=stats,
    )
