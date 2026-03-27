from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from watchlist import (
    add_watch_topic,
    init_watchlist,
    load_watchlist,
    remove_watch_topic,
    reset_watchlist,
    save_watchlist,
    update_watchlist_from_batch,
)


class WatchlistTests(unittest.TestCase):
    def test_init_add_remove_and_reset_watch_topics(self) -> None:
        with TemporaryDirectory() as tmp:
            watchlist_path = Path(tmp) / "watchlist.json"
            initialized = init_watchlist(
                watchlist_path,
                defaults=[{"name": "ai coding", "keywords": ["ai", "coding"]}],
            )
            self.assertEqual(len(initialized["topics"]), 1)

            updated = add_watch_topic(
                "infra signals",
                keywords=["incident", "outage"],
                path=watchlist_path,
            )
            self.assertEqual(len(updated["topics"]), 2)

            reset_state, changed = reset_watchlist(
                path=watchlist_path, topic_name="infra signals"
            )
            self.assertTrue(changed)
            infra = [
                topic
                for topic in reset_state["topics"]
                if topic["name"] == "infra signals"
            ][0]
            self.assertEqual(infra["hit_count"], 0)

            removed_state, removed = remove_watch_topic(
                "infra signals", path=watchlist_path
            )
            self.assertTrue(removed)
            self.assertEqual(len(removed_state["topics"]), 1)

    def test_load_watchlist_merges_defaults_into_schema(self) -> None:
        with TemporaryDirectory() as tmp:
            watchlist_path = Path(tmp) / "watchlist.json"
            data = load_watchlist(
                watchlist_path,
                defaults=[{"name": "ai coding", "keywords": ["ai", "coding"]}],
            )
            self.assertEqual(data["schema"], "watchlist.v1")
            self.assertEqual(len(data["topics"]), 1)

    def test_update_watchlist_from_batch_accumulates_hits(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch_path = root / "sample-rss-batch.md"
            batch_json = root / "sample-rss-batch.json"
            watchlist_path = root / "watchlist.json"
            batch_path.write_text("# placeholder\n", encoding="utf-8")
            batch_json.write_text(
                """
{
  "items": [
    {
      "title": "AI coding assistant improves team workflow",
      "source": "Hacker News",
      "source_feed_url": "https://news.ycombinator.com/rss",
      "date": "Fri, 27 Mar 2026 01:32:10 +0000",
      "link": "https://example.com/post",
      "item_type": "RSS entry",
      "summary": "A startup builds an AI coding assistant",
      "item_quality_score": 88.0
    }
  ]
}
                """.strip(),
                encoding="utf-8",
            )

            updated = update_watchlist_from_batch(
                batch_path,
                watchlist_path=watchlist_path,
                defaults=[{"name": "ai coding", "keywords": ["ai", "coding"]}],
                seen_at="2026-03-27T12:00:00Z",
            )
            save_watchlist(updated, watchlist_path)
            loaded = load_watchlist(watchlist_path)

            topic = loaded["topics"][0]
            self.assertEqual(topic["hit_count"], 1)
            self.assertEqual(topic["last_run_hits"], 1)
            self.assertEqual(topic["last_hit_at"], "2026-03-27T12:00:00Z")
            self.assertEqual(
                topic["sample_items"][0]["title"],
                "AI coding assistant improves team workflow",
            )


if __name__ == "__main__":
    unittest.main()
