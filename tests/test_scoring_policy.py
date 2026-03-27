from __future__ import annotations

import unittest
from dataclasses import dataclass

from policies.scoring_policy import score_item_quality, score_recency


@dataclass
class FakeItem:
    title: str
    source: str
    source_feed_url: str
    date: str
    summary: str
    dedupe_group_id: str = ""
    duplicate_count: int = 0


class ScoringPolicyTests(unittest.TestCase):
    def test_recent_items_score_higher_than_old_items(self) -> None:
        fresh = score_recency("Fri, 27 Mar 2026 01:32:10 +0000")
        stale = score_recency("Fri, 27 Feb 2026 01:32:10 +0000")
        self.assertGreater(fresh, stale)

    def test_duplicate_items_get_lower_novelty(self) -> None:
        item = FakeItem(
            title="AI coding workflow updates",
            source="Hacker News",
            source_feed_url="https://news.ycombinator.com/rss",
            date="Fri, 27 Mar 2026 01:32:10 +0000",
            summary="AI coding workflow updates for developers",
            dedupe_group_id="dup-1",
            duplicate_count=2,
        )
        peer = FakeItem(
            title="AI coding workflow updates for developers",
            source="TechCrunch",
            source_feed_url="https://techcrunch.com/feed/",
            date="Fri, 27 Mar 2026 01:35:10 +0000",
            summary="Coverage of AI coding workflow updates",
            dedupe_group_id="dup-1",
            duplicate_count=0,
        )

        scored = score_item_quality(
            item, [item, peer], "AI coding startup opportunities"
        )

        self.assertLess(float(scored["novelty_score"]), 80.0)
        self.assertGreaterEqual(float(scored["convergence_score"]), 72.0)
        self.assertGreater(float(scored["item_quality_score"]), 0.0)


if __name__ == "__main__":
    unittest.main()
