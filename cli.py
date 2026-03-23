from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from analyze_batch import run_analysis, run_skill_analysis
from errors import ConfigError, RSSAgentError, get_exit_code
from feed_report import DEFAULT_REPORT_PATH, generate_report
from fetch_batch import DEFAULT_SCORES_FILE, load_feed_scores, run_fetch, save_feed_scores
from run_codex_pipeline import run_pipeline
from settings import load_settings
from skill_runtime import load_local_env

ROOT = Path(__file__).resolve().parent
DEFAULT_FEEDS_FILE = ROOT / "feeds.txt"
DEFAULT_INPUT_DIR = ROOT / "inputs"
DEFAULT_OUTPUT_DIR = ROOT / "outputs"


def cmd_check(_args: argparse.Namespace) -> int:
    load_local_env()
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_MODEL")
    print(f"OPENAI_API_KEY={'set' if api_key else 'missing'}")
    print(f"OPENAI_BASE_URL={base_url or 'missing'}")
    print(f"OPENAI_MODEL={model or 'missing'}")
    ready = bool(api_key and base_url and model)
    print(f"skill_mode_ready={'true' if ready else 'false'}")
    return 0 if ready else 1


def cmd_fetch(args: argparse.Namespace) -> int:
    result = run_fetch(
        feeds_file=Path(args.feeds_file),
        output_dir=Path(args.output_dir),
        topic=args.topic,
        per_feed_limit=args.per_feed_limit,
        output_name=args.output_name,
        timeout=args.timeout,
        retries=args.retries,
        retry_delay=args.retry_delay,
        scores_file=Path(args.scores_file),
        log_level=args.log_level,
    )
    output_path, item_count, errors, source_stats = result
    print(f"saved={output_path}")
    print(f"saved_json={output_path.with_suffix('.json')}")
    print(f"items={item_count}")
    if errors:
        print(f"errors={len(errors)}")
    for stat in source_stats:
        print(
            f"source={stat['source']} fetched={stat['fetched']} kept={stat['kept']} filtered={stat['filtered']} status={stat['status']} current_score={stat['current_score']}"
        )
    return 0 if item_count else 1


def cmd_analyze(args: argparse.Namespace) -> int:
    input_path = Path(args.input_file)
    if not input_path.exists():
        raise ConfigError(f"Input file not found: {input_path}")
    if args.mode == "skill":
        output_path, item_count = run_skill_analysis(
            input_path=input_path,
            output_dir=Path(args.output_dir),
            output_file=args.output_file,
            skill_name=args.skill_name,
            log_level=args.log_level,
        )
    else:
        output_path, item_count = run_analysis(
            input_path=input_path,
            output_dir=Path(args.output_dir),
            output_file=args.output_file,
            log_level=args.log_level,
        )
    print(f"saved={output_path}")
    print(f"saved_json={output_path.with_suffix('.json')}")
    print(f"items={item_count}")
    return 0 if item_count else 1


def cmd_run(args: argparse.Namespace) -> int:
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
    )
    print(f"input={result['input']}")
    print(f"input_json={Path(str(result['input'])).with_suffix('.json')}")
    if result["output"]:
        print(f"output={result['output']}")
        print(f"output_json={Path(str(result['output'])).with_suffix('.json')}")
    print(f"report={result['report']}")
    print(f"fetched_items={result['fetched_items']}")
    print(f"analyzed_items={result['analyzed_items']}")
    print(f"analysis_mode={result['analysis_mode']}")
    return 0 if int(result["fetched_items"]) > 0 else 1


def cmd_report(args: argparse.Namespace) -> int:
    report_path = generate_report(scores_file=Path(args.scores_file), report_path=Path(args.report_file))
    print(f"report={report_path}")
    return 0


def cmd_score_show(args: argparse.Namespace) -> int:
    scores = load_feed_scores(Path(args.scores_file))
    print(json.dumps(scores, ensure_ascii=False, indent=2))
    return 0


def cmd_score_reset(args: argparse.Namespace) -> int:
    save_feed_scores({}, Path(args.scores_file))
    print(f"reset={args.scores_file}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Local RSS agent CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Check skill-mode environment readiness.")
    check_parser.set_defaults(func=cmd_check)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch RSS feeds into inputs.")
    fetch_parser.add_argument("--feeds-file", default=str(DEFAULT_FEEDS_FILE))
    fetch_parser.add_argument("--output-dir", default=str(DEFAULT_INPUT_DIR))
    fetch_parser.add_argument("--topic", default=str(settings["topic"]))
    fetch_parser.add_argument("--per-feed-limit", type=int, default=int(settings["per_feed_limit"]))
    fetch_parser.add_argument("--output-name", default=None)
    fetch_parser.add_argument("--timeout", type=int, default=int(settings["timeout"]))
    fetch_parser.add_argument("--retries", type=int, default=int(settings["retries"]))
    fetch_parser.add_argument("--retry-delay", type=float, default=float(settings["retry_delay"]))
    fetch_parser.add_argument("--scores-file", default=str(DEFAULT_SCORES_FILE))
    fetch_parser.add_argument("--log-level", default=str(settings["log_level"]))
    fetch_parser.set_defaults(func=cmd_fetch)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze a normalized input batch.")
    analyze_parser.add_argument("--input-file", required=True)
    analyze_parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    analyze_parser.add_argument("--output-file", default=None)
    analyze_parser.add_argument("--mode", choices=["rules", "skill"], default="rules")
    analyze_parser.add_argument("--skill-name", default="tech-opportunity-skill")
    analyze_parser.add_argument("--log-level", default=str(settings["log_level"]))
    analyze_parser.set_defaults(func=cmd_analyze)

    run_parser = subparsers.add_parser("run", help="Run fetch + analyze + feedback + report.")
    run_parser.add_argument("--topic", default=str(settings["topic"]))
    run_parser.add_argument("--feeds-file", default=str(DEFAULT_FEEDS_FILE))
    run_parser.add_argument("--per-feed-limit", type=int, default=int(settings["per_feed_limit"]))
    run_parser.add_argument("--name-prefix", default=None)
    run_parser.add_argument("--timeout", type=int, default=int(settings["timeout"]))
    run_parser.add_argument("--retries", type=int, default=int(settings["retries"]))
    run_parser.add_argument("--retry-delay", type=float, default=float(settings["retry_delay"]))
    run_parser.add_argument("--scores-file", default=str(DEFAULT_SCORES_FILE))
    run_parser.add_argument("--analysis-mode", choices=["rules", "skill", "auto"], default=str(settings["analysis_mode"]))
    run_parser.add_argument("--skill-name", default="tech-opportunity-skill")
    run_parser.add_argument("--log-level", default=str(settings["log_level"]))
    run_parser.set_defaults(func=cmd_run)

    report_parser = subparsers.add_parser("report", help="Generate feed score report.")
    report_parser.add_argument("--scores-file", default=str(DEFAULT_SCORES_FILE))
    report_parser.add_argument("--report-file", default=str(DEFAULT_REPORT_PATH))
    report_parser.set_defaults(func=cmd_report)

    score_parser = subparsers.add_parser("score", help="Inspect or reset feed scores.")
    score_subparsers = score_parser.add_subparsers(dest="score_command", required=True)

    score_show_parser = score_subparsers.add_parser("show", help="Show current feed scores.")
    score_show_parser.add_argument("--scores-file", default=str(DEFAULT_SCORES_FILE))
    score_show_parser.set_defaults(func=cmd_score_show)

    score_reset_parser = score_subparsers.add_parser("reset", help="Reset feed scores.")
    score_reset_parser.add_argument("--scores-file", default=str(DEFAULT_SCORES_FILE))
    score_reset_parser.set_defaults(func=cmd_score_reset)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except RSSAgentError as exc:
        print(f"error={exc}")
        return get_exit_code(exc)
    except Exception as exc:
        print(f"error={exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
