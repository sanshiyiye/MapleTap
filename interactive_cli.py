from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path
from typing import Callable

from feed_report import DEFAULT_REPORT_PATH
from i18n import resolve_report_lang, set_active_lang, t, write_stored_report_lang, write_stored_ui_lang
from settings import load_settings


def _root() -> Path:
    return Path(__file__).resolve().parent


def _require_tty() -> bool:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(t("interactive.tty"), file=sys.stderr)
        return False
    return True


def _pause(message: str | None = None) -> None:
    msg = message if message is not None else t("interactive.pause")
    try:
        input(msg)
    except EOFError:
        pass


def _prompt(default: str | None, label: str) -> str:
    hint = f" [{default}]" if default else ""
    raw = input(f"{label}{hint}: ").strip()
    if not raw and default is not None:
        return default
    return raw


def _clear_screen() -> None:
    try:
        import os

        os.system("cls" if os.name == "nt" else "clear")
    except OSError:
        print("\n" * 2)


def _banner(title: str) -> None:
    line = "═" * (len(title) + 4)
    print(f"╔{line}╗")
    print(f"║  {title}  ║")
    print(f"╚{line}╝")


def _list_batch_md(inputs_dir: Path) -> list[Path]:
    if not inputs_dir.is_dir():
        return []
    return sorted(
        (p for p in inputs_dir.glob("*-rss-batch.md") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _wrap_run(label: str, fn: Callable[[], int]) -> None:
    print(f"\n── {label} ──")
    try:
        code = fn()
        print("\n" + t("interactive.wrap.done", code=code))
    except Exception as exc:
        print("\n" + t("interactive.wrap.error", exc=str(exc)))
        print(t("interactive.hint"))
    _pause()


def run_interactive_menu() -> int:
    if not _require_tty():
        return 1

    root = _root()
    default_feeds = root / "feeds.txt"
    default_inputs = root / "inputs"
    default_outputs = root / "outputs"
    default_archive = root / "archive"
    scores_file = root / "feed_scores.json"

    settings = load_settings()

    import cli as cli_mod

    while True:
        _clear_screen()
        _banner(t("interactive.banner"))
        print(
            "\n"
            + t("interactive.menu.header")
            + "\n"
            + t("interactive.menu.1")
            + "\n"
            + t("interactive.menu.2")
            + "\n"
            + t("interactive.menu.3")
            + "\n"
            + t("interactive.menu.4")
            + "\n"
            + t("interactive.menu.5")
            + "\n"
            + t("interactive.menu.6")
            + "\n"
            + t("interactive.menu.7")
            + "\n"
            + t("interactive.menu.8")
            + "\n"
            + t("interactive.menu.9")
            + "\n"
            + t("interactive.menu.10")
            + "\n"
            + t("interactive.menu.0")
            + "\n"
        )
        choice = input(t("interactive.menu.prompt")).strip()

        if choice == "0":
            print(t("interactive.goodbye"))
            return 0

        if choice == "10":
            print("\n── " + t("interactive.lang.title") + " ──")
            pick = input(t("interactive.lang.prompt")).strip()
            if pick == "2" or pick.lower() == "zh":
                write_stored_ui_lang("zh")
                write_stored_report_lang("zh")
                set_active_lang("zh")
                print(t("interactive.lang.saved", code="zh"))
            elif pick == "1" or pick.lower() == "en":
                write_stored_ui_lang("en")
                write_stored_report_lang("en")
                set_active_lang("en")
                print(t("interactive.lang.saved", code="en"))
            else:
                print(t("interactive.lang.cancel"))
            _pause()
            continue

        if choice == "1":
            _wrap_run("check", lambda: cli_mod.cmd_check(Namespace()))
            continue

        if choice == "2":
            def do_fetch() -> int:
                topic = _prompt(str(settings["topic"]), t("interactive.topic"))
                oname = _prompt("", t("interactive.fetch.out_name"))
                lim = _prompt(str(settings["per_feed_limit"]), t("interactive.fetch.per_limit"))
                return cli_mod.cmd_fetch(
                    Namespace(
                        feeds_file=str(default_feeds),
                        output_dir=str(default_inputs),
                        topic=topic,
                        per_feed_limit=int(lim),
                        output_name=oname or None,
                        timeout=int(settings["timeout"]),
                        retries=int(settings["retries"]),
                        retry_delay=float(settings["retry_delay"]),
                        scores_file=str(scores_file),
                        log_level=str(settings["log_level"]),
                    )
                )

            _wrap_run("fetch", do_fetch)
            continue

        if choice == "3":
            def do_analyze() -> int:
                batches = _list_batch_md(default_inputs)
                if not batches:
                    raise RuntimeError(t("interactive.analyze.none", path=str(default_inputs)))
                print("\n" + t("interactive.analyze.list"))
                for i, p in enumerate(batches, start=1):
                    print(f"  [{i}] {p.name}")
                idx_s = input(t("interactive.analyze.pick")).strip() or "1"
                idx = int(idx_s)
                if idx < 1 or idx > len(batches):
                    raise RuntimeError(t("interactive.analyze.bad_idx"))
                path = batches[idx - 1]
                mode_s = input(t("interactive.analyze.mode")).strip().lower() or "rules"
                if mode_s not in {"rules", "skill"}:
                    raise RuntimeError(t("interactive.analyze.bad_mode"))
                return cli_mod.cmd_analyze(
                    Namespace(
                        input_file=str(path),
                        output_dir=str(default_outputs),
                        output_file=None,
                        mode=mode_s,
                        skill_name="tech-opportunity-skill",
                        log_level=str(settings["log_level"]),
                        report_lang=resolve_report_lang(None),
                    )
                )

            _wrap_run("analyze", do_analyze)
            continue

        if choice == "4":
            def do_run() -> int:
                topic = _prompt(str(settings["topic"]), t("interactive.topic"))
                mode = _prompt(str(settings["analysis_mode"]), t("interactive.run.mode"))
                if mode not in {"rules", "skill", "auto"}:
                    raise RuntimeError(t("interactive.run.bad_mode"))
                prefix = _prompt("", t("interactive.run.prefix"))
                return cli_mod.cmd_run(
                    Namespace(
                        topic=topic,
                        feeds_file=str(default_feeds),
                        per_feed_limit=int(settings["per_feed_limit"]),
                        name_prefix=prefix or None,
                        timeout=int(settings["timeout"]),
                        retries=int(settings["retries"]),
                        retry_delay=float(settings["retry_delay"]),
                        scores_file=str(scores_file),
                        analysis_mode=mode,
                        skill_name="tech-opportunity-skill",
                        log_level=str(settings["log_level"]),
                        report_lang=resolve_report_lang(None),
                    )
                )

            _wrap_run("run", do_run)
            continue

        if choice == "5":
            _wrap_run(
                "report",
                lambda: cli_mod.cmd_report(
                    Namespace(
                        scores_file=str(scores_file),
                        report_file=str(DEFAULT_REPORT_PATH),
                    )
                ),
            )
            continue

        if choice == "6":
            _wrap_run(
                "score show",
                lambda: cli_mod.cmd_score_show(Namespace(scores_file=str(scores_file))),
            )
            continue

        if choice == "7":
            def do_reset() -> int:
                confirm = input(t("interactive.reset.confirm")).strip()
                if confirm != "YES":
                    print(t("interactive.reset.cancel"))
                    return 1
                return cli_mod.cmd_score_reset(Namespace(scores_file=str(scores_file)))

            _wrap_run("score reset", do_reset)
            continue

        if choice == "8":
            def do_archive_menu() -> int:
                print(
                    "\n"
                    + t("interactive.archive.sub")
                    + "\n"
                    + t("interactive.archive.1")
                    + "\n"
                    + t("interactive.archive.2")
                    + "\n"
                    + t("interactive.archive.3")
                    + "\n"
                    + t("interactive.archive.0")
                    + "\n"
                )
                sub = input(t("interactive.archive.pick")).strip()
                if sub == "0":
                    return 0
                if sub == "1":
                    return cli_mod.cmd_archive(
                        Namespace(
                            inputs_dir=str(default_inputs),
                            outputs_dir=str(default_outputs),
                            archive_dir=str(default_archive),
                            keep_batch_stem=None,
                            interval=None,
                            dry_run=True,
                            verbose=True,
                        )
                    )
                if sub == "2":
                    return cli_mod.cmd_archive(
                        Namespace(
                            inputs_dir=str(default_inputs),
                            outputs_dir=str(default_outputs),
                            archive_dir=str(default_archive),
                            keep_batch_stem=None,
                            interval=None,
                            dry_run=False,
                            verbose=True,
                        )
                    )
                if sub == "3":
                    raw = _prompt("3600", t("interactive.archive.interval"))
                    return cli_mod.cmd_archive(
                        Namespace(
                            inputs_dir=str(default_inputs),
                            outputs_dir=str(default_outputs),
                            archive_dir=str(default_archive),
                            keep_batch_stem=None,
                            interval=float(raw),
                            dry_run=False,
                            verbose=False,
                        )
                    )
                print(t("interactive.archive.bad"))
                return 1

            _wrap_run("archive", do_archive_menu)
            continue

        if choice == "9":
            print(
                "\n"
                + t("interactive.examples.title")
                + "\n"
                "  python cli.py check\n"
                "  python cli.py fetch --topic \"...\"\n"
                "  python cli.py analyze --input-file inputs/<batch>.md --mode rules\n"
                "  python cli.py run --analysis-mode auto\n"
                "  python cli.py report\n"
                "  python cli.py score show\n"
                "  python cli.py archive --dry-run -v\n"
                "  python cli.py lang set zh\n"
            )
            _pause()
            continue

        print(t("interactive.invalid"))
        _pause(t("interactive.pause_short"))
