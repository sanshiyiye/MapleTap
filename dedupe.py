from __future__ import annotations

from typing import Protocol


class DedupeItem(Protocol):
    source_feed_url: str
    link: str
    title: str


def dedupe_items(items: list[DedupeItem]) -> list[DedupeItem]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[DedupeItem] = []
    for item in items:
        key = (
            item.source_feed_url.strip(),
            item.link.strip(),
            item.title.strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
