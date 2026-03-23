# Local CLI Runbook

## Goal

Run the isolated RSS tool as a stable local CLI without touching the main NewsPilot codepath.

## Required files

- `feeds.txt`
- `.env.local` for skill mode
- `settings.json`

## Quick start

1. Check configuration:

```bash
python isolated_rss_codex_agent/cli.py check
```

Optional interactive menu (TTY only):

```bash
python isolated_rss_codex_agent/cli.py interactive
```

2. Run a full batch:

```bash
python isolated_rss_codex_agent/cli.py run --analysis-mode auto
```

3. Open outputs:

- `isolated_rss_codex_agent/inputs/`
- `isolated_rss_codex_agent/outputs/`

## Command reference

Fetch:

```bash
python isolated_rss_codex_agent/cli.py fetch --topic "AI, coding, startup opportunities"
```

Analyze an existing batch:

```bash
python isolated_rss_codex_agent/cli.py analyze --input-file isolated_rss_codex_agent/inputs/<batch>.md --mode rules
```

Generate score report:

```bash
python isolated_rss_codex_agent/cli.py report
```

Show score state:

```bash
python isolated_rss_codex_agent/cli.py score show
```

Reset score state:

```bash
python isolated_rss_codex_agent/cli.py score reset
```

Archive older batch files (keeps newest batch by mtime; use `--keep-batch-stem` to pin):

```bash
python isolated_rss_codex_agent/cli.py archive --dry-run -v
python isolated_rss_codex_agent/cli.py archive
```

Watch mode (repeat every N seconds; Ctrl+C to stop):

```bash
python isolated_rss_codex_agent/cli.py archive --interval 3600
```

## Runtime behavior

- `fetch` writes Markdown and JSON batch files.
- `analyze` writes Markdown and JSON analysis files.
- `run` executes fetch, analyze, feedback, and report in one command.
- `auto` analysis mode prefers `skill` and falls back to `rules` on failure.
- feed priority is updated over time through `feed_scores.json`.

## Validated commands

The current refactor was validated with:

```bash
python isolated_rss_codex_agent/cli.py --help
python isolated_rss_codex_agent/cli.py check
python isolated_rss_codex_agent/cli.py fetch --topic "CLI validation for AI, coding, startup opportunities" --output-name "cli-fetch-test.md"
python isolated_rss_codex_agent/cli.py analyze --input-file isolated_rss_codex_agent/inputs/cli-fetch-test.md --mode rules --output-file "cli-fetch-test-analysis.md"
python isolated_rss_codex_agent/cli.py run --topic "CLI full pipeline validation for AI, coding, startup opportunities" --name-prefix "cli-run-test" --analysis-mode auto
python isolated_rss_codex_agent/cli.py report
```
