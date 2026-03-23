# Schemas

This folder documents the stable program-facing outputs for the local CLI tool.

## rss_batch.json

Top-level shape:

```json
{
  "topic": "string",
  "collected_at": "ISO datetime",
  "collector": "string",
  "source_stats": [],
  "items": [],
  "errors": []
}
```

Each item:

```json
{
  "title": "string",
  "source": "string",
  "source_feed_url": "string",
  "date": "string",
  "link": "string",
  "item_type": "string",
  "summary": "string"
}
```

## analysis_result.json

Top-level shape:

```json
{
  "input_file": "string",
  "mode": "rules|skill",
  "items": [],
  "output_markdown_file": "string"
}
```

## feed_scores.json

Top-level shape:

```json
{
  "feed_url": {
    "source": "string",
    "attempts": 0,
    "successes": 0,
    "total_fetched": 0,
    "total_kept": 0,
    "total_filtered": 0,
    "success_rate": 0.0,
    "kept_rate": 0.0,
    "quality_score": 0.0,
    "analysis_value_score": 0.0,
    "score": 0.0
  }
}
```
