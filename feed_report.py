from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, cast

from fetch_batch import DEFAULT_SCORES_FILE, load_feed_scores
from history import DEFAULT_HISTORY_DIR, load_latest_snapshots
from state_utils import atomic_write_text
from watchlist import DEFAULT_WATCHLIST_PATH, load_watchlist


ROOT = Path(__file__).resolve().parent
DEFAULT_REPORT_PATH = ROOT / "outputs" / "feed_scores_report.md"


def _feed_map(snapshot: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not snapshot:
        return {}
    feeds = snapshot.get("feeds", [])
    if not isinstance(feeds, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in feeds:
        if isinstance(row, dict):
            result[str(row.get("feed_url", ""))] = row
    return result


def render_change_summary(
    latest: dict[str, Any] | None, previous: dict[str, Any] | None
) -> list[str]:
    lines = ["## Changes Since Last Run", ""]
    if latest is None:
        lines.extend(["- No run history yet.", ""])
        return lines
    if previous is None:
        lines.extend(
            [f"- First recorded snapshot: {latest.get('generated_at', '-')}", ""]
        )
        return lines

    latest_feeds = _feed_map(latest)
    previous_feeds = _feed_map(previous)
    deltas: list[tuple[float, str, str]] = []
    for feed_url, record in latest_feeds.items():
        current_score = float(record.get("score", 0.0))
        previous_score = float(previous_feeds.get(feed_url, {}).get("score", 0.0))
        source = str(record.get("source", feed_url))
        deltas.append((round(current_score - previous_score, 2), source, feed_url))
    deltas.sort(key=lambda item: (-item[0], item[1]))
    risers = [item for item in deltas if item[0] > 0][:3]
    fallers = sorted(
        (item for item in deltas if item[0] < 0), key=lambda item: (item[0], item[1])
    )[:3]

    latest_topics = (
        latest.get("watchlist", {}).get("topics", [])
        if isinstance(latest.get("watchlist", {}), dict)
        else []
    )
    previous_topics = (
        previous.get("watchlist", {}).get("topics", [])
        if isinstance(previous.get("watchlist", {}), dict)
        else []
    )
    latest_topic_map = {
        str(topic.get("name", "")): topic
        for topic in latest_topics
        if isinstance(topic, dict)
    }
    previous_topic_map = {
        str(topic.get("name", "")): topic
        for topic in previous_topics
        if isinstance(topic, dict)
    }

    if risers:
        lines.append("- Rising feeds:")
        for delta, source, _feed_url in risers:
            lines.append(f"  - {source}: +{delta:.2f}")
    if fallers:
        lines.append("- Falling feeds:")
        for delta, source, _feed_url in fallers:
            lines.append(f"  - {source}: {delta:.2f}")

    topic_changes = []
    for name, topic in latest_topic_map.items():
        latest_hits = int(topic.get("last_run_hits", 0) or 0)
        previous_hits = int(
            previous_topic_map.get(name, {}).get("last_run_hits", 0) or 0
        )
        delta = latest_hits - previous_hits
        topic_changes.append((delta, name, latest_hits))
    topic_changes.sort(key=lambda item: (-item[0], item[1]))
    if topic_changes:
        lines.append("- Watch topics:")
        for delta, name, latest_hits in topic_changes[:3]:
            prefix = "+" if delta >= 0 else ""
            lines.append(f"  - {name}: last_run_hits={latest_hits} ({prefix}{delta})")

    latest_top_items = (
        latest.get("top_items", [])
        if isinstance(latest.get("top_items", []), list)
        else []
    )
    if latest_top_items:
        best = latest_top_items[0]
        if isinstance(best, dict):
            lines.append(
                f"- Strongest current item: {best.get('title', '-')} | source={best.get('source', '-')} | score={best.get('item_quality_score', '-')}"
            )
    lines.append("")
    return lines


def render_watchlist_section(watchlist: dict[str, object]) -> list[str]:
    raw_topics = watchlist.get("topics", [])
    topics = cast(list[object], raw_topics) if isinstance(raw_topics, list) else []
    lines = ["## Watchlist Hits", ""]
    if not topics:
        lines.extend(["- No watchlist topics configured.", ""])
        return lines
    lines.extend(
        [
            "| Topic | Last Run Hits | Total Hits | Last Hit At | Top Feeds | Recent Sample |",
            "|---|---:|---:|---|---|---|",
        ]
    )
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        matched_feeds = topic.get("matched_feeds", {})
        top_feeds = "-"
        if isinstance(matched_feeds, dict) and matched_feeds:
            ordered_feeds = sorted(
                matched_feeds.items(), key=lambda item: (-int(item[1]), str(item[0]))
            )[:2]
            top_feeds = ", ".join(f"{feed} ({count})" for feed, count in ordered_feeds)
        sample_items = topic.get("sample_items", [])
        recent_sample = "-"
        if isinstance(sample_items, list) and sample_items:
            sample = sample_items[0]
            if isinstance(sample, dict):
                recent_sample = str(sample.get("title", "-"))
        lines.append(
            f"| {topic.get('name', '-')} | {int(topic.get('last_run_hits', 0) or 0)} | {int(topic.get('hit_count', 0) or 0)} | {topic.get('last_hit_at', '-')} | {top_feeds} | {recent_sample} |"
        )
    lines.append("")
    return lines


def render_report(
    scores: dict[str, dict],
    watchlist: dict[str, object] | None = None,
    latest_snapshot: dict[str, Any] | None = None,
    previous_snapshot: dict[str, Any] | None = None,
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ordered = sorted(
        scores.items(),
        key=lambda item: (-float(item[1].get("score", 0.0)), item[0]),
    )

    lines = [
        "# Feed Scores Report",
        "",
        f"- Generated At: {generated_at}",
        f"- Feed Count: {len(ordered)}",
        "",
    ]

    lines.extend(render_change_summary(latest_snapshot, previous_snapshot))

    lines.extend(
        [
            "## Summary",
            "",
            "| Rank | Source | Score | Quality | Avg Item | Duplicate Rate | Relevance | Authority | Convergence | Last Status |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )

    for index, (feed_url, record) in enumerate(ordered, start=1):
        source = str(record.get("source", feed_url)).replace("|", "/")
        score = float(record.get("score", 0.0))
        quality = float(record.get("quality_score", score))
        analysis = float(record.get("analysis_value_score", 50.0))
        avg_item = float(record.get("avg_item_score", 0.0))
        duplicate_rate = float(record.get("duplicate_rate", 0.0))
        relevance = float(record.get("avg_relevance_score", 0.0))
        authority = float(record.get("avg_authority_score", 0.0))
        convergence = float(record.get("avg_convergence_score", 0.0))
        last_status = str(record.get("last_status", "unknown"))
        lines.append(
            f"| {index} | {source} | {score:.2f} | {quality:.2f} | {avg_item:.2f} | {duplicate_rate:.2f} | {relevance:.2f} | {authority:.2f} | {convergence:.2f} | {last_status} |"
        )

    lines.extend(["", "## Details", ""])

    for index, (feed_url, record) in enumerate(ordered, start=1):
        lines.extend(
            [
                f"### {index}. {record.get('source', feed_url)}",
                f"- Feed URL: {feed_url}",
                f"- Score: {float(record.get('score', 0.0)):.2f}",
                f"- Quality Score: {float(record.get('quality_score', record.get('score', 0.0))):.2f}",
                f"- Stability Score: {float(record.get('stability_score', 0.0)):.2f}",
                f"- Analysis Value Score: {float(record.get('analysis_value_score', 50.0)):.2f}",
                f"- Average Item Score: {float(record.get('avg_item_score', 0.0)):.2f}",
                f"- Average Relevance Score: {float(record.get('avg_relevance_score', 0.0)):.2f}",
                f"- Average Authority Score: {float(record.get('avg_authority_score', 0.0)):.2f}",
                f"- Average Recency Score: {float(record.get('avg_recency_score', 0.0)):.2f}",
                f"- Average Convergence Score: {float(record.get('avg_convergence_score', 0.0)):.2f}",
                f"- Average Novelty Score: {float(record.get('avg_novelty_score', 0.0)):.2f}",
                f"- Attempts: {int(record.get('attempts', 0))}",
                f"- Successes: {int(record.get('successes', 0))}",
                f"- Success Rate: {float(record.get('success_rate', 0.0)):.2f}",
                f"- Kept Rate: {float(record.get('kept_rate', 0.0)):.2f}",
                f"- Duplicate Rate: {float(record.get('duplicate_rate', 0.0)):.2f}",
                f"- Total Fetched: {int(record.get('total_fetched', 0))}",
                f"- Total Kept: {int(record.get('total_kept', 0))}",
                f"- Total Filtered: {int(record.get('total_filtered', 0))}",
                f"- Feedback Runs: {int(record.get('feedback_runs', 0))}",
                f"- Average Feedback Bonus: {float(record.get('average_feedback_bonus', 0.0)):.2f}",
                f"- Last Feedback Signal: {float(record.get('last_feedback_signal', 0.0)):.2f}",
                f"- Last Status: {record.get('last_status', 'unknown')}",
                f"- Top Strengths: {', '.join(record.get('top_strengths', [])) or '-'}",
                f"- Main Penalties: {', '.join(record.get('main_penalties', [])) or '-'}",
                f"- Last Updated: {record.get('last_updated', '-')}",
                f"- Last Feedback Updated: {record.get('last_feedback_updated', '-')}",
                "",
            ]
        )

    if watchlist is not None:
        lines.extend(render_watchlist_section(watchlist))

    lines.extend(
        [
            "## Interpretation",
            "",
            "- `Score` is the current blended priority used by the pipeline.",
            "- `Quality Score` blends fetch stability with average item quality.",
            "- `Duplicate Rate` estimates how much repeated coverage a feed contributes.",
            "- `Average Item Score` blends relevance, authority, recency, convergence, and novelty.",
            "- `Analysis Value Score` reflects how often a feed contributes to higher-ranked analysis output.",
            "- High score does not mean permanent lock-in. It should still be reviewed periodically.",
            "",
        ]
    )

    return "\n".join(lines)


def generate_report(
    scores_file: Path = DEFAULT_SCORES_FILE,
    report_path: Path = DEFAULT_REPORT_PATH,
    watchlist_path: Path = DEFAULT_WATCHLIST_PATH,
    history_dir: Path = DEFAULT_HISTORY_DIR,
) -> Path:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    scores = load_feed_scores(scores_file)
    watchlist = load_watchlist(watchlist_path)
    latest_snapshot, previous_snapshot = load_latest_snapshots(history_dir)
    atomic_write_text(
        report_path,
        render_report(
            scores,
            watchlist=watchlist,
            latest_snapshot=latest_snapshot,
            previous_snapshot=previous_snapshot,
        ),
    )
    return report_path


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate a readable feed score report."
    )
    parser.add_argument("--scores-file", default=str(DEFAULT_SCORES_FILE))
    parser.add_argument("--report-file", default=str(DEFAULT_REPORT_PATH))
    args = parser.parse_args()

    report_path = generate_report(
        scores_file=Path(args.scores_file),
        report_path=Path(args.report_file),
    )
    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
