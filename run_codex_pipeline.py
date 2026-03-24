from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from analyze_batch import run_analysis, run_skill_analysis
from feed_feedback import apply_analysis_feedback
from feed_report import DEFAULT_REPORT_PATH, generate_report
from fetch_batch import DEFAULT_SCORES_FILE, run_fetch
from i18n import resolve_report_lang
from logging_utils import setup_logger
from settings import load_settings

ROOT = Path(__file__).resolve().parent
DEFAULT_FEEDS_FILE = ROOT / "feeds.txt"
DEFAULT_INPUT_DIR = ROOT / "inputs"
DEFAULT_OUTPUT_DIR = ROOT / "outputs"


def run_pipeline(
    *,
    topic: str,
    feeds_file: Path,
    per_feed_limit: int,
    name_prefix: str | None,
    timeout: int,
    retries: int,
    retry_delay: float,
    scores_file: Path,
    analysis_mode: str,
    skill_name: str,
    log_level: str | None = None,
    report_lang: str = "en",
) -> dict[str, object]:
    logger = setup_logger("rss_agent.pipeline", log_level or str(load_settings().get("log_level", "INFO")))
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    prefix = name_prefix or timestamp
    input_name = f"{prefix}-rss-batch.md"
    output_name = f"{prefix}-rss-analysis.md"

    input_path, item_count, errors, source_stats = run_fetch(
        feeds_file=feeds_file,
        output_dir=DEFAULT_INPUT_DIR,
        topic=topic,
        per_feed_limit=per_feed_limit,
        output_name=input_name,
        timeout=timeout,
        retries=retries,
        retry_delay=retry_delay,
        scores_file=scores_file,
        log_level=log_level,
    )

    if item_count == 0:
        logger.warning("pipeline_no_items input=%s", input_path)
        report_path = generate_report(scores_file=scores_file)
        return {
            "input": input_path,
            "output": None,
            "report": report_path,
            "fetched_items": 0,
            "analyzed_items": 0,
            "analysis_mode": None,
            "errors": errors,
            "source_stats": source_stats,
        }

    used_mode = analysis_mode
    if analysis_mode == "auto":
        try:
            output_path, analyzed_count = run_skill_analysis(
                input_path=input_path,
                output_dir=DEFAULT_OUTPUT_DIR,
                output_file=output_name,
                skill_name=skill_name,
                log_level=log_level,
                report_lang=report_lang,
            )
            used_mode = "skill"
        except Exception as exc:
            logger.warning("skill_analysis_failed fallback=rules error=%s", exc)
            output_path, analyzed_count = run_analysis(
                input_path=input_path,
                output_dir=DEFAULT_OUTPUT_DIR,
                output_file=output_name,
                log_level=log_level,
                report_lang=report_lang,
            )
            used_mode = "rules"
    elif analysis_mode == "skill":
        output_path, analyzed_count = run_skill_analysis(
            input_path=input_path,
            output_dir=DEFAULT_OUTPUT_DIR,
            output_file=output_name,
            skill_name=skill_name,
            log_level=log_level,
            report_lang=report_lang,
        )
        used_mode = "skill"
    else:
        output_path, analyzed_count = run_analysis(
            input_path=input_path,
            output_dir=DEFAULT_OUTPUT_DIR,
            output_file=output_name,
            log_level=log_level,
            report_lang=report_lang,
        )
        used_mode = "rules"

    apply_analysis_feedback(input_path=input_path, output_path=output_path, scores_file=scores_file)
    report_path = generate_report(scores_file=scores_file, report_path=DEFAULT_REPORT_PATH)
    logger.info(
        "pipeline_completed input=%s output=%s report=%s fetched_items=%s analyzed_items=%s mode=%s",
        input_path,
        output_path,
        report_path,
        item_count,
        analyzed_count,
        used_mode,
    )
    return {
        "input": input_path,
        "output": output_path,
        "report": report_path,
        "fetched_items": item_count,
        "analyzed_items": analyzed_count,
        "analysis_mode": used_mode,
        "errors": errors,
        "source_stats": source_stats,
    }


def main() -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Run the isolated RSS pipeline end-to-end.")
    parser.add_argument("--topic", default=str(settings["topic"]))
    parser.add_argument("--feeds-file", default=str(DEFAULT_FEEDS_FILE))
    parser.add_argument("--per-feed-limit", type=int, default=int(settings["per_feed_limit"]))
    parser.add_argument("--name-prefix", default=None)
    parser.add_argument("--timeout", type=int, default=int(settings["timeout"]))
    parser.add_argument("--retries", type=int, default=int(settings["retries"]))
    parser.add_argument("--retry-delay", type=float, default=float(settings["retry_delay"]))
    parser.add_argument("--scores-file", default=str(DEFAULT_SCORES_FILE))
    parser.add_argument("--analysis-mode", choices=["rules", "skill", "auto"], default=str(settings["analysis_mode"]))
    parser.add_argument("--skill-name", default="tech-opportunity-skill")
    parser.add_argument("--log-level", default=str(settings["log_level"]))
    parser.add_argument(
        "--report-lang",
        choices=["en", "zh"],
        default=None,
        help="Analysis Markdown language (en|zh). Default: RSS_AGENT_REPORT_LANG, locale.json report_lang, or en.",
    )
    args = parser.parse_args()

    result = run_pipeline(
        topic=args.topic,
        feeds_file=Path(args.feeds_file),
        per_feed_limit=args.per_feed_limit,
        name_prefix=args.name_prefix,
        timeout=args.timeout,
        retries=args.retries,
        retry_delay=args.retry_delay,
        scores_file=Path(args.scores_file),
        analysis_mode=args.analysis_mode,
        skill_name=args.skill_name,
        log_level=args.log_level,
        report_lang=resolve_report_lang(args.report_lang),
    )

    print(f"input={result['input']}")
    if result["output"]:
        print(f"output={result['output']}")
        print(f"output_json={Path(str(result['output'])).with_suffix('.json')}")
    print(f"input_json={Path(str(result['input'])).with_suffix('.json')}")
    print(f"report={result['report']}")
    print(f"fetched_items={result['fetched_items']}")
    print(f"analyzed_items={result['analyzed_items']}")
    print(f"analysis_mode={result['analysis_mode']}")
    errors = list(result["errors"])
    if errors:
        print(f"errors={len(errors)}")
        for error in errors:
            print(error)
    for stat in result["source_stats"]:
        print(
            f"source={stat['source']} fetched={stat['fetched']} kept={stat['kept']} filtered={stat['filtered']} status={stat['status']} previous_score={stat['previous_score']} current_score={stat['current_score']} effective_limit={stat['effective_limit']}"
        )
    return 0 if int(result["fetched_items"]) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
