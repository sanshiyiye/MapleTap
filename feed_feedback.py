from __future__ import annotations

import json
import re
from pathlib import Path

from analyze_batch import parse_items
from fetch_batch import load_feed_scores, save_feed_scores, utc_now_iso

HEADING_RE = re.compile(r"^###\s+\d+\.\s+(.+?)\s*$", re.M)

HIGH_PRIORITY_CUES = [
    "high",
    "high priority",
    "priority",
    "worth tracking",
    "recommend",
]


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


def section_bonus(rank: int, body: str) -> float:
    bonus = max(0.0, 18.0 - rank * 2.0)
    haystack = body.lower()
    if any(cue in haystack for cue in HIGH_PRIORITY_CUES):
        bonus += 6.0
    return bonus


def apply_analysis_feedback(input_path: Path, output_path: Path, scores_file: Path) -> dict[str, dict]:
    input_markdown = input_path.read_text(encoding="utf-8")
    output_markdown = output_path.read_text(encoding="utf-8")

    items = parse_items(input_markdown)
    title_to_feed: dict[str, str] = {item.title: item.source_feed for item in items}

    score_state = load_feed_scores(scores_file)
    sections = split_sections(output_markdown)
    feed_bonus: dict[str, float] = {}

    for rank, (title, body) in enumerate(sections, start=1):
        feed_url = title_to_feed.get(title)
        if not feed_url:
            continue
        feed_bonus[feed_url] = feed_bonus.get(feed_url, 0.0) + section_bonus(rank, body)

    for feed_url, bonus in feed_bonus.items():
        record = score_state.get(feed_url, {})
        feedback_runs = int(record.get("feedback_runs", 0)) + 1
        total_feedback_bonus = float(record.get("total_feedback_bonus", 0.0)) + bonus
        average_feedback_bonus = total_feedback_bonus / feedback_runs if feedback_runs else 0.0
        run_feedback_signal = min(100.0, round(40.0 + bonus * 1.2, 2))
        previous_analysis_value = float(record.get("analysis_value_score", 50.0))
        analysis_value_score = round(previous_analysis_value * 0.7 + run_feedback_signal * 0.3, 2)
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

    parser = argparse.ArgumentParser(description="Apply post-analysis feedback to feed scores.")
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
