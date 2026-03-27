from __future__ import annotations

import unittest
from dataclasses import dataclass, field

from dedupe import canonicalize_url, dedupe_items, normalize_title


@dataclass
class FakeItem:
    title: str
    source: str
    source_feed_url: str
    link: str
    canonical_url: str = ""
    normalized_title: str = ""
    dedupe_key: str = ""
    dedupe_group_id: str = ""
    duplicate_count: int = 0
    duplicate_sources: list[str] = field(default_factory=list)
    duplicate_reason: str = ""


class DedupeTests(unittest.TestCase):
    def test_normalize_title_removes_suffix_and_noise(self) -> None:
        self.assertEqual(
            normalize_title("Breaking: AI Coding Agent Launches | TechCrunch"),
            "ai coding agent launches",
        )

    def test_canonicalize_url_strips_tracking_params(self) -> None:
        self.assertEqual(
            canonicalize_url("https://example.com/post/?utm_source=x&ref=y&id=1#frag"),
            "https://example.com/post?id=1",
        )

    def test_dedupe_groups_same_url_items(self) -> None:
        items = [
            FakeItem(
                title="AI Coding Agent Raises Funding",
                source="Feed A",
                source_feed_url="feed-a",
                link="https://example.com/post?utm_source=feed",
            ),
            FakeItem(
                title="AI Coding Agent Raises Funding Today",
                source="Feed B",
                source_feed_url="feed-b",
                link="https://example.com/post?ref=hn",
            ),
        ]

        result = dedupe_items(items)

        self.assertEqual(result.stats["kept_count"], 1)
        self.assertEqual(result.stats["same_url_duplicates"], 1)
        kept = result.kept_items[0]
        self.assertEqual(kept.duplicate_count, 1)
        self.assertEqual(kept.duplicate_reason, "same_url")
        self.assertIn("Feed B", kept.duplicate_sources)

    def test_dedupe_detects_near_title_duplicates(self) -> None:
        items = [
            FakeItem(
                title="OpenAI launches coding agent for enterprise teams",
                source="Feed A",
                source_feed_url="feed-a",
                link="https://example.com/a",
            ),
            FakeItem(
                title="OpenAI launched coding agent for enterprise team workflows",
                source="Feed B",
                source_feed_url="feed-b",
                link="https://example.com/b",
            ),
        ]

        result = dedupe_items(items, similarity_threshold=0.5)

        self.assertEqual(result.stats["kept_count"], 1)
        self.assertEqual(result.stats["near_duplicates"], 1)


if __name__ == "__main__":
    unittest.main()
