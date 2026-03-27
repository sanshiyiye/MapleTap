from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from analyze_batch import NewsItem, load_input_items, parse_items
from fetch_batch import load_feed_scores, save_feed_scores, utc_now_iso

HEADING_RE = re.compile(r"^###\s+\d+\.\s+(.+?)\s*$", re.M)

HIGH_PRIORITY_CUES = [
    "high",
    "high priority",
    "priority",
    "worth tracking",
    "recommend",
]


@dataclass
class FeedbackItemMeta:
    source_feed: str
    convergence_score: float = 0.0
    duplicate_count: int = 0
    novelty_score: float = 0.0
    item_quality_score: float = 0.0


def split_sections(markdown: str) -> list[tuple[str, str]]:
    matches = list(HEADING_RE.finditer(markdown))
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = markdown[start:end]
        sections.append((title, body))
    return sections


def build_title_to_item_map(input_path: Path) -> dict[str, FeedbackItemMeta]:
    items: list[NewsItem]
    try:
        items = load_input_items(input_path)
    except Exception:
        items = parse_items(input_path.read_text(encoding="utf-8"))
    mapped: dict[str, FeedbackItemMeta] = {}
    for item in items:
        mapped[item.title] = FeedbackItemMeta(
            source_feed=item.source_feed,
            convergence_score=float(item.convergence_score),
            duplicate_count=int(item.duplicate_count),
            novelty_score=float(item.novelty_score),
            item_quality_score=float(item.item_quality_score),
        )
    return mapped


def section_bonus(
    rank: int, body: str, item_meta: FeedbackItemMeta | None = None
) -> float:
    bonus = max(0.0, 18.0 - rank * 2.0)
    haystack = body.lower()
    if any(cue in haystack for cue in HIGH_PRIORITY_CUES):
        bonus += 6.0
    if item_meta is not None:
        if item_meta.convergence_score >= 75:
            bonus += 2.5
        if item_meta.item_quality_score >= 80:
            bonus += 2.0
        if item_meta.duplicate_count > 0:
            bonus -= min(5.0, item_meta.duplicate_count * 1.5)
        if item_meta.novelty_score < 60:
            bonus -= 2.0
    return bonus


def apply_analysis_feedback(
    input_path: Path, output_path: Path, scores_file: Path
) -> dict[str, dict]:
    input_markdown = input_path.read_text(encoding="utf-8")
    output_markdown = output_path.read_text(encoding="utf-8")

    title_to_item = build_title_to_item_map(input_path)

    score_state = load_feed_scores(scores_file)
    sections = split_sections(output_markdown)
    feed_bonus: dict[str, float] = {}

    for rank, (title, body) in enumerate(sections, start=1):
        item_meta = title_to_item.get(title)
        if not item_meta:
            continue
        feed_url = item_meta.source_feed
        feed_bonus[feed_url] = feed_bonus.get(feed_url, 0.0) + section_bonus(
            rank, body, item_meta=item_meta
        )

    for feed_url, bonus in feed_bonus.items():
        record = score_state.get(feed_url, {})
        feedback_runs = int(record.get("feedback_runs", 0)) + 1
        total_feedback_bonus = float(record.get("total_feedback_bonus", 0.0)) + bonus
        average_feedback_bonus = (
            total_feedback_bonus / feedback_runs if feedback_runs else 0.0
        )
        run_feedback_signal = min(100.0, round(40.0 + bonus * 1.2, 2))
        previous_analysis_value = float(record.get("analysis_value_score", 50.0))
        analysis_value_score = round(
            previous_analysis_value * 0.7 + run_feedback_signal * 0.3, 2
        )
        quality_score = float(record.get("quality_score", record.get("score", 50.0)))
        final_score = round(0.7 * quality_score + 0.3 * analysis_value_score, 2)

        record.update(
            {
                "feedback_runs": feedback_runs,
                "total_feedback_bonus": round(total_feedback_bonus, 2),
                "average_feedback_bonus": round(average_feedback_bonus, 2),
                "last_feedback_signal": run_feedback_signal,
                "analysis_value_score": analysis_value_score,
                "score": final_score,
                "last_feedback_updated": utc_now_iso(),
            }
        )
        score_state[feed_url] = record

    save_feed_scores(score_state, scores_file)
    return score_state


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Apply post-analysis feedback to feed scores."
    )
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--scores-file", required=True)
    args = parser.parse_args()

    score_state = apply_analysis_feedback(
        input_path=Path(args.input_file),
        output_path=Path(args.output_file),
        scores_file=Path(args.scores_file),
    )
    print(json.dumps(score_state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
