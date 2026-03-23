# Isolated RSS Codex Agent

This folder is a physically isolated local toolchain for:

- fetching RSS feeds
- normalizing them into standard batch files
- analyzing them with rules or skill-driven LLM calls
- feeding the result back into feed scoring
- generating a readable score report

It does not modify the main `src/` project path.

## Current entrypoint

Use the unified CLI:

```bash
python isolated_rss_codex_agent/cli.py --help
```

Available commands:

- `check`
- `fetch`
- `analyze`
- `run`
- `report`
- `score show`
- `score reset`

## Important files

- `cli.py`: unified local CLI
- `fetch_batch.py`: RSS fetch + filter + dedupe + score update
- `analyze_batch.py`: rules/skill analysis + JSON sidecar output
- `run_codex_pipeline.py`: end-to-end orchestration
- `feed_feedback.py`: analysis feedback into feed scores
- `feed_report.py`: readable score report generator
- `feed_scores.json`: persistent score state
- `settings.json`: runtime defaults
- `.env.local`: model credentials and endpoint
- `feeds.txt`: active RSS feed list
- `schemas/README.md`: JSON schema notes
- `policies/`: fetch / analysis / scoring rule modules

## Output model

Each batch now produces both:

- Markdown for human review
- JSON for programmatic reuse

Examples:

- `inputs/<name>.md`
- `inputs/<name>.json`
- `outputs/<name>.md`
- `outputs/<name>.json`

## Typical usage

Check skill mode:

```bash
python isolated_rss_codex_agent/cli.py check
```

Fetch only:

```bash
python isolated_rss_codex_agent/cli.py fetch --topic "AI, coding, startup opportunities"
```

Analyze only:

```bash
python isolated_rss_codex_agent/cli.py analyze --input-file isolated_rss_codex_agent/inputs/<batch>.md --mode rules
```

Run the full pipeline:

```bash
python isolated_rss_codex_agent/cli.py run --analysis-mode auto
```

Generate score report:

```bash
python isolated_rss_codex_agent/cli.py report
```

## Validation status

The refactored CLI flow has been validated locally with:

- `cli.py --help`
- `cli.py check`
- `cli.py fetch`
- `cli.py analyze --mode rules`
- `cli.py run --analysis-mode auto`
- `cli.py report`

The latest full validation produced:

- `inputs/cli-run-test-rss-batch.md`
- `inputs/cli-run-test-rss-batch.json`
- `outputs/cli-run-test-rss-analysis.md`
- `outputs/cli-run-test-rss-analysis.json`
- `outputs/feed_scores_report.md`
