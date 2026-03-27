from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import cast
from pathlib import Path

from analyze_batch import run_analysis, run_skill_analysis
from archive_batches import run_archive
from errors import ConfigError, RSSAgentError, get_exit_code
from feed_report import DEFAULT_REPORT_PATH, generate_report
from fetch_batch import (
    DEFAULT_SCORES_FILE,
    load_feed_scores,
    run_fetch,
    save_feed_scores,
)
from i18n import (
    LOCALE_FILE,
    SUPPORTED_LANGS,
    get_ui_lang,
    read_stored_report_lang,
    read_stored_ui_lang,
    resolve_report_lang,
    resolve_ui_lang,
    set_active_lang,
    t,
    write_stored_report_lang,
    write_stored_ui_lang,
)
from interactive_cli import run_interactive_menu
from run_codex_pipeline import run_pipeline
from settings import load_settings
from skill_runtime import load_local_env
from watchlist import (
    DEFAULT_WATCHLIST_PATH,
    add_watch_topic,
    init_watchlist,
    load_watchlist,
    remove_watch_topic,
    reset_watchlist,
)

ROOT = Path(__file__).resolve().parent
DEFAULT_FEEDS_FILE = ROOT / "feeds.txt"
DEFAULT_INPUT_DIR = ROOT / "inputs"
DEFAULT_OUTPUT_DIR = ROOT / "outputs"
DEFAULT_ARCHIVE_DIR = ROOT / "archive"
HIDDEN_COMMAND_HELP = argparse.SUPPRESS


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
        raise ConfigError(t("errors.input_not_found", path=input_path))
    report_lang = resolve_report_lang(getattr(args, "report_lang", None))
    if args.mode == "skill":
        output_path, item_count = run_skill_analysis(
            input_path=input_path,
            output_dir=Path(args.output_dir),
            output_file=args.output_file,
            skill_name=args.skill_name,
            log_level=args.log_level,
            report_lang=report_lang,
        )
    else:
        output_path, item_count = run_analysis(
            input_path=input_path,
            output_dir=Path(args.output_dir),
            output_file=args.output_file,
            log_level=args.log_level,
            report_lang=report_lang,
        )
    print(f"saved={output_path}")
    print(f"saved_json={output_path.with_suffix('.json')}")
    print(f"items={item_count}")
    return 0 if item_count else 1


def cmd_run(args: argparse.Namespace) -> int:
    report_lang = resolve_report_lang(getattr(args, "report_lang", None))
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
        report_lang=report_lang,
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
    return 0 if int(cast(int, result["fetched_items"])) > 0 else 1


def cmd_report(args: argparse.Namespace) -> int:
    report_path = generate_report(
        scores_file=Path(args.scores_file), report_path=Path(args.report_file)
    )
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


def cmd_interactive(_args: argparse.Namespace) -> int:
    return run_interactive_menu()


def cmd_archive(args: argparse.Namespace) -> int:
    inputs_dir = Path(args.inputs_dir)
    outputs_dir = Path(args.outputs_dir)
    archive_dir = Path(args.archive_dir)
    interval = args.interval

    def run_once() -> tuple[int, int]:
        result = run_archive(
            inputs_dir=inputs_dir,
            outputs_dir=outputs_dir,
            archive_root=archive_dir,
            keep_batch_stem=args.keep_batch_stem,
            dry_run=args.dry_run,
        )
        n_in = len(result.moved_inputs)
        n_out = len(result.moved_outputs)
        if result.archive_dir is not None:
            print(f"archive_dir={result.archive_dir}")
        else:
            print(t("archive.none"))
        print(f"kept_batch_stem={result.kept_batch_stem}")
        print(f"kept_analysis_stem={result.kept_analysis_stem}")
        print(f"kept_skill_stem={result.kept_skill_stem}")
        print(f"moved_inputs={n_in}")
        print(f"moved_outputs={n_out}")
        if args.verbose:
            for p in result.moved_inputs:
                print(f"  in: {p.name}")
            for p in result.moved_outputs:
                print(f"  out: {p.name}")
        return n_in, n_out

    if interval is None:
        run_once()
        return 0

    if interval <= 0:
        raise ConfigError("--interval must be positive seconds")

    print(t("archive.watch", interval=interval))
    try:
        while True:
            run_once()
            time.sleep(float(interval))
    except KeyboardInterrupt:
        print(t("archive.stopped"))
        return 0


def cmd_lang_show(_args: argparse.Namespace) -> int:
    print(t("lang.show.ui", value=get_ui_lang()))
    print(t("lang.show.report", value=read_stored_report_lang()))
    print(t("lang.show.file", path=str(LOCALE_FILE)))
    return 0


def cmd_lang_set(args: argparse.Namespace) -> int:
    write_stored_ui_lang(args.code)
    write_stored_report_lang(args.code)
    set_active_lang(args.code)
    print(t("lang.saved", code=args.code))
    return 0


def cmd_watch_show(args: argparse.Namespace) -> int:
    watchlist = load_watchlist(Path(args.watchlist_file))
    if getattr(args, "format", "table") == "json":
        print(json.dumps(watchlist, ensure_ascii=False, indent=2))
        return 0

    topics = watchlist.get("topics", [])
    if not isinstance(topics, list) or not topics:
        print("watchlist_topics=0")
        print("No watchlist topics configured.")
        return 0

    filtered_topics = []
    topic_filter = str(getattr(args, "topic", "") or "").strip().casefold()
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        if topic_filter and str(topic.get("name", "")).casefold() != topic_filter:
            continue
        filtered_topics.append(topic)

    if not filtered_topics:
        print("watchlist_topics=0")
        print("No matching watchlist topics.")
        return 0

    print(f"watchlist_topics={len(filtered_topics)}")
    for index, topic in enumerate(filtered_topics, start=1):
        if not isinstance(topic, dict):
            continue
        name = str(topic.get("name", "-"))
        hit_count = int(topic.get("hit_count", 0) or 0)
        last_run_hits = int(topic.get("last_run_hits", 0) or 0)
        last_hit_at = str(topic.get("last_hit_at", "-"))
        keywords = topic.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []
        matched_feeds = topic.get("matched_feeds", {})
        if not isinstance(matched_feeds, dict):
            matched_feeds = {}
        top_feeds = sorted(
            ((str(feed), int(count or 0)) for feed, count in matched_feeds.items()),
            key=lambda item: (-item[1], item[0]),
        )[:3]
        sample_items = topic.get("sample_items", [])
        if not isinstance(sample_items, list):
            sample_items = []
        limit = max(1, int(getattr(args, "limit", 1) or 1))

        print(f"[{index}] {name}")
        print(
            f"  total_hits={hit_count} last_run_hits={last_run_hits} last_hit_at={last_hit_at}"
        )
        print(f"  keywords={', '.join(str(x) for x in keywords) if keywords else '-'}")
        if top_feeds:
            print(
                "  top_feeds="
                + ", ".join(f"{feed} ({count})" for feed, count in top_feeds)
            )
        else:
            print("  top_feeds=-")
        if sample_items:
            for sample_index, recent in enumerate(sample_items[:limit], start=1):
                if isinstance(recent, dict):
                    label = (
                        "recent_sample"
                        if sample_index == 1
                        else f"sample_{sample_index}"
                    )
                    print(
                        f"  {label}="
                        f"{recent.get('title', '-')} | source={recent.get('source', '-')} | score={recent.get('score', '-')}"
                    )
        else:
            print("  recent_sample=-")
    return 0


def cmd_watch_init(args: argparse.Namespace) -> int:
    settings = load_settings()
    watchlist = init_watchlist(
        Path(args.watchlist_file), defaults=list(settings.get("watchlist_topics", []))
    )
    print(f"initialized={args.watchlist_file}")
    print(f"watchlist_topics={len(watchlist.get('topics', []))}")
    return 0


def cmd_watch_add(args: argparse.Namespace) -> int:
    settings = load_settings()
    keywords = [
        part.strip() for part in (args.keywords or "").split(",") if part.strip()
    ]
    watchlist = add_watch_topic(
        args.name,
        keywords=keywords or None,
        path=Path(args.watchlist_file),
        defaults=list(settings.get("watchlist_topics", [])),
    )
    print(f"added={args.name}")
    print(f"watchlist_topics={len(watchlist.get('topics', []))}")
    return 0


def cmd_watch_remove(args: argparse.Namespace) -> int:
    settings = load_settings()
    watchlist, removed = remove_watch_topic(
        args.name,
        path=Path(args.watchlist_file),
        defaults=list(settings.get("watchlist_topics", [])),
    )
    print(f"removed={'true' if removed else 'false'}")
    print(f"watchlist_topics={len(watchlist.get('topics', []))}")
    return 0 if removed else 1


def cmd_watch_reset(args: argparse.Namespace) -> int:
    settings = load_settings()
    watchlist, changed = reset_watchlist(
        path=Path(args.watchlist_file),
        defaults=list(settings.get("watchlist_topics", [])),
        topic_name=args.topic,
    )
    print(f"reset={'true' if changed else 'false'}")
    print(f"watchlist_topics={len(watchlist.get('topics', []))}")
    return 0 if changed else 1


def make_global_parser() -> argparse.ArgumentParser:
    gp = argparse.ArgumentParser(add_help=False)
    gp.add_argument(
        "--lang",
        choices=sorted(SUPPORTED_LANGS),
        default=None,
        metavar="CODE",
        help="en|zh for this run; default: RSS_AGENT_LANG, else locale.json, else en.",
    )
    gp.add_argument(
        "--save-lang",
        action="store_true",
        default=False,
        help="Persist --lang to locale.json (requires --lang).",
    )
    gp.add_argument(
        "--report-lang",
        choices=sorted(SUPPORTED_LANGS),
        default=None,
        metavar="CODE",
        help="Analysis output language en|zh for analyze/run; default: RSS_AGENT_REPORT_LANG, else locale.json report_lang, else en.",
    )
    gp.add_argument(
        "--save-report-lang",
        action="store_true",
        default=False,
        help="Persist --report-lang to locale.json (requires --report-lang).",
    )
    return gp


def build_parser(*, global_parent: argparse.ArgumentParser) -> argparse.ArgumentParser:
    settings = load_settings()
    parser = argparse.ArgumentParser(
        parents=[global_parent],
        description=t("cli.description"),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=t("cli.epilog"),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser(
        "check",
        help=t("cmd.check.help"),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=t("cmd.check.epilog"),
    )
    check_parser.set_defaults(func=cmd_check)

    interactive_parser = subparsers.add_parser(
        "interactive",
        help=HIDDEN_COMMAND_HELP,
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=t("cmd.interactive.epilog"),
    )
    interactive_parser.set_defaults(func=cmd_interactive)

    fetch_parser = subparsers.add_parser(
        "fetch",
        help=t("cmd.fetch.help"),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=t("cmd.fetch.epilog"),
    )
    fetch_parser.add_argument("--feeds-file", default=str(DEFAULT_FEEDS_FILE))
    fetch_parser.add_argument("--output-dir", default=str(DEFAULT_INPUT_DIR))
    fetch_parser.add_argument("--topic", default=str(settings["topic"]))
    fetch_parser.add_argument(
        "--per-feed-limit", type=int, default=int(settings["per_feed_limit"])
    )
    fetch_parser.add_argument("--output-name", default=None)
    fetch_parser.add_argument("--timeout", type=int, default=int(settings["timeout"]))
    fetch_parser.add_argument("--retries", type=int, default=int(settings["retries"]))
    fetch_parser.add_argument(
        "--retry-delay", type=float, default=float(settings["retry_delay"])
    )
    fetch_parser.add_argument("--scores-file", default=str(DEFAULT_SCORES_FILE))
    fetch_parser.add_argument("--log-level", default=str(settings["log_level"]))
    fetch_parser.set_defaults(func=cmd_fetch)

    analyze_parser = subparsers.add_parser(
        "analyze",
        help=t("cmd.analyze.help"),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=t("cmd.analyze.epilog"),
    )
    analyze_parser.add_argument("--input-file", required=True)
    analyze_parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    analyze_parser.add_argument("--output-file", default=None)
    analyze_parser.add_argument("--mode", choices=["rules", "skill"], default="rules")
    analyze_parser.add_argument("--skill-name", default="tech-opportunity-skill")
    analyze_parser.add_argument("--log-level", default=str(settings["log_level"]))
    analyze_parser.set_defaults(func=cmd_analyze)

    run_parser = subparsers.add_parser(
        "run",
        help=t("cmd.run.help"),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=t("cmd.run.epilog"),
    )
    run_parser.add_argument("--topic", default=str(settings["topic"]))
    run_parser.add_argument("--feeds-file", default=str(DEFAULT_FEEDS_FILE))
    run_parser.add_argument(
        "--per-feed-limit", type=int, default=int(settings["per_feed_limit"])
    )
    run_parser.add_argument("--name-prefix", default=None)
    run_parser.add_argument("--timeout", type=int, default=int(settings["timeout"]))
    run_parser.add_argument("--retries", type=int, default=int(settings["retries"]))
    run_parser.add_argument(
        "--retry-delay", type=float, default=float(settings["retry_delay"])
    )
    run_parser.add_argument("--scores-file", default=str(DEFAULT_SCORES_FILE))
    run_parser.add_argument(
        "--analysis-mode",
        choices=["rules", "skill", "auto"],
        default=str(settings["analysis_mode"]),
    )
    run_parser.add_argument("--skill-name", default="tech-opportunity-skill")
    run_parser.add_argument("--log-level", default=str(settings["log_level"]))
    run_parser.set_defaults(func=cmd_run)

    report_parser = subparsers.add_parser(
        "report",
        help=t("cmd.report.help"),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=t("cmd.report.epilog"),
    )
    report_parser.add_argument("--scores-file", default=str(DEFAULT_SCORES_FILE))
    report_parser.add_argument("--report-file", default=str(DEFAULT_REPORT_PATH))
    report_parser.set_defaults(func=cmd_report)

    score_parser = subparsers.add_parser(
        "score",
        help=HIDDEN_COMMAND_HELP,
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=t("cmd.score.epilog"),
    )
    score_subparsers = score_parser.add_subparsers(dest="score_command", required=True)

    score_show_parser = score_subparsers.add_parser(
        "show", help=t("cmd.score.show.help")
    )
    score_show_parser.add_argument("--scores-file", default=str(DEFAULT_SCORES_FILE))
    score_show_parser.set_defaults(func=cmd_score_show)

    score_reset_parser = score_subparsers.add_parser(
        "reset", help=t("cmd.score.reset.help")
    )
    score_reset_parser.add_argument("--scores-file", default=str(DEFAULT_SCORES_FILE))
    score_reset_parser.set_defaults(func=cmd_score_reset)

    archive_parser = subparsers.add_parser(
        "archive",
        help=HIDDEN_COMMAND_HELP,
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=t("cmd.archive.epilog"),
    )
    archive_parser.add_argument("--inputs-dir", default=str(DEFAULT_INPUT_DIR))
    archive_parser.add_argument("--outputs-dir", default=str(DEFAULT_OUTPUT_DIR))
    archive_parser.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE_DIR))
    archive_parser.add_argument(
        "--keep-batch-stem",
        default=None,
        help=t("cmd.archive.keep_stem"),
    )
    archive_parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help=t("cmd.archive.interval"),
    )
    archive_parser.add_argument(
        "--dry-run",
        action="store_true",
        help=t("cmd.archive.dry_run"),
    )
    archive_parser.add_argument("--verbose", "-v", action="store_true")
    archive_parser.set_defaults(func=cmd_archive)

    lang_parser = subparsers.add_parser(
        "lang",
        help=HIDDEN_COMMAND_HELP,
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=t("cmd.lang.epilog"),
    )
    lang_subparsers = lang_parser.add_subparsers(dest="lang_action", required=True)
    lang_show_parser = lang_subparsers.add_parser("show", help=t("cmd.lang.show.help"))
    lang_show_parser.set_defaults(func=cmd_lang_show)
    lang_set_parser = lang_subparsers.add_parser("set", help=t("cmd.lang.set.help"))
    lang_set_parser.add_argument(
        "code", choices=sorted(SUPPORTED_LANGS), help=t("cmd.lang.set.arg")
    )
    lang_set_parser.set_defaults(func=cmd_lang_set)

    watch_parser = subparsers.add_parser(
        "watch",
        help="Inspect accumulated watchlist topics.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Example:\n  python cli.py watch show",
    )
    watch_subparsers = watch_parser.add_subparsers(dest="watch_action", required=True)
    watch_show_parser = watch_subparsers.add_parser(
        "show",
        help="Show current watchlist data.",
    )
    watch_show_parser.add_argument(
        "--watchlist-file", default=str(DEFAULT_WATCHLIST_PATH)
    )
    watch_show_parser.add_argument(
        "--format", choices=["table", "json"], default="table"
    )
    watch_show_parser.add_argument("--topic", default=None)
    watch_show_parser.add_argument("--limit", type=int, default=1)
    watch_show_parser.set_defaults(func=cmd_watch_show)

    watch_init_parser = watch_subparsers.add_parser(
        "init", help="Initialize watchlist from default topics."
    )
    watch_init_parser.add_argument(
        "--watchlist-file", default=str(DEFAULT_WATCHLIST_PATH)
    )
    watch_init_parser.set_defaults(func=cmd_watch_init)

    watch_add_parser = watch_subparsers.add_parser(
        "add", help="Add or update a watch topic."
    )
    watch_add_parser.add_argument("name")
    watch_add_parser.add_argument("--keywords", default="")
    watch_add_parser.add_argument(
        "--watchlist-file", default=str(DEFAULT_WATCHLIST_PATH)
    )
    watch_add_parser.set_defaults(func=cmd_watch_add)

    watch_remove_parser = watch_subparsers.add_parser(
        "remove", help="Remove a watch topic."
    )
    watch_remove_parser.add_argument("name")
    watch_remove_parser.add_argument(
        "--watchlist-file", default=str(DEFAULT_WATCHLIST_PATH)
    )
    watch_remove_parser.set_defaults(func=cmd_watch_remove)

    watch_reset_parser = watch_subparsers.add_parser(
        "reset", help="Reset watch hit counts and samples."
    )
    watch_reset_parser.add_argument("--topic", default=None)
    watch_reset_parser.add_argument(
        "--watchlist-file", default=str(DEFAULT_WATCHLIST_PATH)
    )
    watch_reset_parser.set_defaults(func=cmd_watch_reset)

    return parser


def main() -> int:
    global_parser = make_global_parser()
    pre_args, rest = global_parser.parse_known_args()
    if not rest:
        resolve_ui_lang(cli_lang=pre_args.lang, save=pre_args.save_lang)
        if pre_args.save_report_lang and pre_args.report_lang is not None:
            write_stored_report_lang(pre_args.report_lang)
        if sys.stdin.isatty() and sys.stdout.isatty():
            return int(cmd_interactive(argparse.Namespace()))
        parser = build_parser(global_parent=global_parser)
        parser.print_help()
        return 0
    if pre_args.save_lang and pre_args.lang is None:
        set_active_lang(read_stored_ui_lang())
        print("error=--save-lang requires --lang (en|zh)", file=sys.stderr)
        return 2
    if pre_args.save_report_lang and pre_args.report_lang is None:
        set_active_lang(read_stored_ui_lang())
        print(
            "error=--save-report-lang requires --report-lang (en|zh)", file=sys.stderr
        )
        return 2
    resolve_ui_lang(cli_lang=pre_args.lang, save=pre_args.save_lang)
    if pre_args.save_report_lang:
        write_stored_report_lang(pre_args.report_lang)
    parser = build_parser(global_parent=global_parser)
    args = parser.parse_args(rest)
    # Global flags were consumed by parse_known_args above and are not re-parsed from `rest`.
    args.lang = pre_args.lang
    args.save_lang = pre_args.save_lang
    args.report_lang = pre_args.report_lang
    args.save_report_lang = pre_args.save_report_lang
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
