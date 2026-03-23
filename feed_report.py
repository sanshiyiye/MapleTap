from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fetch_batch import DEFAULT_SCORES_FILE, load_feed_scores
from state_utils import atomic_write_text


ROOT = Path(__file__).resolve().parent
DEFAULT_REPORT_PATH = ROOT / "outputs" / "feed_scores_report.md"


def render_report(scores: dict[str, dict]) -> str:
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
        "## Summary",
        "",
        "| Rank | Source | Score | Quality | Analysis | Attempts | Success Rate | Kept Rate | Last Status |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]

    for index, (feed_url, record) in enumerate(ordered, start=1):
        source = str(record.get("source", feed_url)).replace("|", "/")
        score = float(record.get("score", 0.0))
        quality = float(record.get("quality_score", score))
        analysis = float(record.get("analysis_value_score", 50.0))
        attempts = int(record.get("attempts", 0))
        success_rate = float(record.get("success_rate", 0.0))
        kept_rate = float(record.get("kept_rate", 0.0))
        last_status = str(record.get("last_status", "unknown"))
        lines.append(
            f"| {index} | {source} | {score:.2f} | {quality:.2f} | {analysis:.2f} | {attempts} | {success_rate:.2f} | {kept_rate:.2f} | {last_status} |"
        )

    lines.extend(["", "## Details", ""])

    for index, (feed_url, record) in enumerate(ordered, start=1):
        lines.extend(
            [
                f"### {index}. {record.get('source', feed_url)}",
                f"- Feed URL: {feed_url}",
                f"- Score: {float(record.get('score', 0.0)):.2f}",
                f"- Quality Score: {float(record.get('quality_score', record.get('score', 0.0))):.2f}",
                f"- Analysis Value Score: {float(record.get('analysis_value_score', 50.0)):.2f}",
                f"- Attempts: {int(record.get('attempts', 0))}",
                f"- Successes: {int(record.get('successes', 0))}",
                f"- Success Rate: {float(record.get('success_rate', 0.0)):.2f}",
                f"- Kept Rate: {float(record.get('kept_rate', 0.0)):.2f}",
                f"- Total Fetched: {int(record.get('total_fetched', 0))}",
                f"- Total Kept: {int(record.get('total_kept', 0))}",
                f"- Total Filtered: {int(record.get('total_filtered', 0))}",
                f"- Feedback Runs: {int(record.get('feedback_runs', 0))}",
                f"- Average Feedback Bonus: {float(record.get('average_feedback_bonus', 0.0)):.2f}",
                f"- Last Feedback Signal: {float(record.get('last_feedback_signal', 0.0)):.2f}",
                f"- Last Status: {record.get('last_status', 'unknown')}",
                f"- Last Updated: {record.get('last_updated', '-')}",
                f"- Last Feedback Updated: {record.get('last_feedback_updated', '-')}",
                "",
            ]
        )

    lines.extend(
        [
            "## Interpretation",
            "",
            "- `Score` is the current blended priority used by the pipeline.",
            "- `Quality Score` mainly reflects fetch stability and kept-vs-filtered ratio.",
            "- `Analysis Value Score` reflects how often a feed contributes to higher-ranked analysis output.",
            "- High score does not mean permanent lock-in. It should still be reviewed periodically.",
            "",
        ]
    )

    return "\n".join(lines)


def generate_report(
    scores_file: Path = DEFAULT_SCORES_FILE,
    report_path: Path = DEFAULT_REPORT_PATH,
) -> Path:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    scores = load_feed_scores(scores_file)
    atomic_write_text(report_path, render_report(scores))
    return report_path


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate a readable feed score report.")
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
