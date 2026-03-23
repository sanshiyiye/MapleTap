from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path
from typing import Callable

from feed_report import DEFAULT_REPORT_PATH
from settings import load_settings

# Defaults mirror cli.py (avoid importing cli at module load — circular import).


def _root() -> Path:
    return Path(__file__).resolve().parent


def _require_tty() -> bool:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(
            "interactive 模式需要交互式终端（TTY）。"
            "请在终端中运行，或使用子命令：python cli.py run --help",
            file=sys.stderr,
        )
        return False
    return True


def _pause(message: str = "按 Enter 返回菜单…") -> None:
    try:
        input(message)
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
        print(f"\n完成（退出码 {code}）")
    except Exception as exc:
        print(f"\n错误: {exc}")
        print("提示: 检查路径、配置与网络；仍可用非交互命令重试。")
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

    # Lazy import after cli is fully loaded
    import cli as cli_mod

    while True:
        _clear_screen()
        _banner("RSS Agent 交互菜单")
        print(
            "\n请选择操作：\n"
            "  [1] 检查 Skill 环境 (check)\n"
            "  [2] 抓取 RSS → inputs (fetch)\n"
            "  [3] 分析已有批次 (analyze)\n"
            "  [4] 完整流程 fetch+analyze+反馈+报告 (run)\n"
            "  [5] 生成 feed 评分报告 (report)\n"
            "  [6] 查看 feed_scores (score show)\n"
            "  [7] 重置 feed_scores (score reset)\n"
            "  [8] 归档旧批次 (archive)\n"
            "  [9] 显示常用非交互命令示例\n"
            "  [0] 退出\n"
        )
        choice = input("请选择 [0-9]: ").strip()

        if choice == "0":
            print("再见。")
            return 0

        if choice == "1":
            _wrap_run("check", lambda: cli_mod.cmd_check(Namespace()))
            continue

        if choice == "2":
            def do_fetch() -> int:
                topic = _prompt(str(settings["topic"]), "topic")
                oname = _prompt("", "输出文件名 (留空则自动生成，如 2026-..-rss-batch.md)")
                lim = _prompt(str(settings["per_feed_limit"]), "每源条数 per_feed_limit")
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
                    raise RuntimeError(f"未找到 *-rss-batch.md，目录: {default_inputs}")
                print("\n可用批次：")
                for i, p in enumerate(batches, start=1):
                    print(f"  [{i}] {p.name}")
                idx_s = input("输入序号 (直接 Enter 选 1): ").strip() or "1"
                idx = int(idx_s)
                if idx < 1 or idx > len(batches):
                    raise RuntimeError("无效序号")
                path = batches[idx - 1]
                mode_s = (
                    input("模式 rules / skill [rules]: ").strip().lower() or "rules"
                )
                if mode_s not in {"rules", "skill"}:
                    raise RuntimeError("模式必须是 rules 或 skill")
                return cli_mod.cmd_analyze(
                    Namespace(
                        input_file=str(path),
                        output_dir=str(default_outputs),
                        output_file=None,
                        mode=mode_s,
                        skill_name="tech-opportunity-skill",
                        log_level=str(settings["log_level"]),
                    )
                )

            _wrap_run("analyze", do_analyze)
            continue

        if choice == "4":
            def do_run() -> int:
                topic = _prompt(str(settings["topic"]), "topic")
                mode = (
                    _prompt(str(settings["analysis_mode"]), "analysis_mode (rules/skill/auto)")
                )
                if mode not in {"rules", "skill", "auto"}:
                    raise RuntimeError("analysis_mode 必须是 rules / skill / auto")
                prefix = _prompt("", "name_prefix (留空=时间戳)")
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
                confirm = input("确认重置 feed_scores？输入大写 YES: ").strip()
                if confirm != "YES":
                    print("已取消。")
                    return 1
                return cli_mod.cmd_score_reset(Namespace(scores_file=str(scores_file)))

            _wrap_run("score reset", do_reset)
            continue

        if choice == "8":
            def do_archive_menu() -> int:
                print(
                    "\n归档子菜单：\n"
                    "  [1] 仅预览 (dry-run -v)\n"
                    "  [2] 执行归档一次\n"
                    "  [3] 定时归档 (每 N 秒，Ctrl+C 停止)\n"
                    "  [0] 返回\n"
                )
                sub = input("请选择: ").strip()
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
                    raw = _prompt("3600", "间隔秒数")
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
                print("无效选择。")
                return 1

            _wrap_run("archive", do_archive_menu)
            continue

        if choice == "9":
            print(
                "\n常用命令（可复制到脚本/CI）：\n"
                "  python cli.py check\n"
                "  python cli.py fetch --topic \"...\"\n"
                "  python cli.py analyze --input-file inputs/<batch>.md --mode rules\n"
                "  python cli.py run --analysis-mode auto\n"
                "  python cli.py report\n"
                "  python cli.py score show\n"
                "  python cli.py archive --dry-run -v\n"
            )
            _pause()
            continue

        print("无效输入，请输入 0-9。")
        _pause("按 Enter 继续…")
