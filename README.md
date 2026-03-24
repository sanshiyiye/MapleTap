# Isolated RSS Codex Agent

**Language / 语言:** English (this file) · [中文 README](README.zh.md)

This folder is a self-contained local toolchain for:

- Fetching RSS feeds and normalizing them into batch files  
- Analyzing batches with **rules** or **skill-driven** LLM calls  
- Writing analysis feedback into feed scoring  
- Generating a readable score report  

It does not modify the parent project’s `src/` tree.

## Entrypoint

Unified CLI (run from this directory, or prefix paths from the repo root):

```bash
python cli.py --help
```

From the monorepo root:

```bash
python isolated_rss_codex_agent/cli.py --help
```

### Commands

| Command | Purpose |
|--------|---------|
| `check` | Verify skill mode env (`OPENAI_*`) |
| `interactive` | TTY menu (same actions as CLI subcommands) |
| `fetch` | Pull RSS → `inputs/` |
| `analyze` | Analyze one batch (`rules` / `skill`) |
| `run` | Fetch + analyze + feedback + report |
| `report` | Generate `feed_scores_report.md` |
| `score show` / `score reset` | Inspect or clear feed scores |
| `archive` | Archive old inputs/outputs (`--interval` optional) |
| `lang show` / `lang set en\|zh` | Persist UI + report language defaults in `locale.json` |

### Global flags (must appear **before** the subcommand)

| Flag | Purpose |
|------|---------|
| `--lang en\|zh` | UI strings for this process |
| `--save-lang` | Save `--lang` to `locale.json` (requires `--lang`) |
| `--report-lang en\|zh` | Language of analysis Markdown |
| `--save-report-lang` | Save `--report-lang` to `locale.json` (requires `--report-lang`) |

**Precedence**

- **UI**: `--lang` → `RSS_AGENT_LANG` → `locale.json` `ui_lang` → `en`  
- **Report**: `--report-lang` → `RSS_AGENT_REPORT_LANG` → `locale.json` `report_lang` → `en`  

Example:

```bash
python cli.py --lang zh --report-lang zh run --analysis-mode auto
```

Strings live in `locales/en.json` and `locales/zh.json`; logic in `i18n.py`. `locale.json` is gitignored.

## Important files

| Path | Role |
|------|------|
| `cli.py` | Main CLI |
| `i18n.py`, `locales/*.json` | UI + report copy |
| `fetch_batch.py` | Fetch, filter, dedupe, score updates |
| `analyze_batch.py` | Rules/skill analysis + JSON sidecar |
| `run_codex_pipeline.py` | End-to-end pipeline |
| `feed_feedback.py` | Apply analysis outcome to scores |
| `feed_report.py` | Score report Markdown |
| `feed_scores.json` | Persistent scores (gitignored in some setups) |
| `settings.json` | Defaults |
| `.env.local` | API key / base URL / model |
| `feeds.txt` | RSS URL list |
| `schemas/README.md` | JSON schema notes |
| `policies/` | Fetch / analysis / scoring rules |

## Output model

Each batch produces:

- **Markdown** — human-readable analysis; each item includes **Source link** / **原文链接** after Action; no trailing `## Original Links` appendix  
- **JSON** — same run, machine-friendly  

Typical paths:

- `inputs/<name>.md`, `inputs/<name>.json`  
- `outputs/<name>.md`, `outputs/<name>.json`  

## Typical usage

Check skill mode:

```bash
python cli.py check
```

Interactive menu (real terminal required):

```bash
python cli.py interactive
```

Fetch only:

```bash
python cli.py fetch --topic "AI, coding, startup opportunities"
```

Analyze only:

```bash
python cli.py analyze --input-file inputs/<batch>.md --mode rules
python cli.py --report-lang zh analyze --input-file inputs/<batch>.md --mode skill
```

Full pipeline:

```bash
python cli.py run --analysis-mode auto
```

Score report:

```bash
python cli.py report
```

Archive old batches (keeps newest `*-rss-batch` and paired analyses):

```bash
python cli.py archive
python cli.py archive --dry-run -v
python cli.py archive --interval 3600
```

## Validation

The CLI flow has been exercised with: `check`, `fetch`, `analyze` (rules/skill), `run`, `report`, `archive`, and `interactive`.

See also **`RUNBOOK.md`** for operational notes.
