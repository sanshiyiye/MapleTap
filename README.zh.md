# Isolated RSS Codex Agent

**语言 / Language:** 中文（本页）· [English README](README.md)

本目录是一套**独立**的本地工具链，用于：

- 抓取 RSS 并标准化为批次文件  
- 使用**规则**或 **Skill + LLM** 分析批次  
- 将分析结果回写进订阅源评分  
- 生成可读的评分报告  

不会改动上级工程中的 `src/` 目录树。

## 入口

统一 CLI（在本目录下执行；若在仓库根目录，请加上路径前缀）：

```bash
python cli.py --help
```

在 monorepo 根目录：

```bash
python isolated_rss_codex_agent/cli.py --help
```

### 子命令

| 命令 | 说明 |
|------|------|
| `check` | 检查 Skill 模式环境（`OPENAI_*`） |
| `interactive` | 交互式数字菜单（逻辑与非交互子命令一致） |
| `fetch` | 抓取 RSS → `inputs/` |
| `analyze` | 分析单个批次（`rules` / `skill`） |
| `run` | 抓取 + 分析 + 反馈 + 报告 |
| `report` | 生成 `feed_scores_report.md` |
| `score show` / `score reset` | 查看或清空 feed 分数 |
| `archive` | 归档较早的输入/输出（可选 `--interval`） |
| `lang show` / `lang set en\|zh` | 查看或写入 `locale.json`（界面与报告语言默认） |

### 全局参数（必须写在**子命令之前**）

| 参数 | 说明 |
|------|------|
| `--lang en\|zh` | 本次进程的界面文案语言 |
| `--save-lang` | 将 `--lang` 写入 `locale.json`（须同时提供 `--lang`） |
| `--report-lang en\|zh` | 分析报告 Markdown 的语言 |
| `--save-report-lang` | 将 `--report-lang` 写入 `locale.json`（须同时提供 `--report-lang`） |

**优先级**

- **界面**：`--lang` → 环境变量 `RSS_AGENT_LANG` → `locale.json` 的 `ui_lang` → `en`  
- **报告**：`--report-lang` → `RSS_AGENT_REPORT_LANG` → `locale.json` 的 `report_lang` → `en`  

示例：

```bash
python cli.py --lang zh --report-lang zh run --analysis-mode auto
```

文案在 `locales/en.json`、`locales/zh.json`，逻辑在 `i18n.py`。`locale.json` 默认被 git 忽略。

## 重要文件

| 路径 | 作用 |
|------|------|
| `cli.py` | 主命令行入口 |
| `i18n.py`、`locales/*.json` | 界面与报告文案 |
| `fetch_batch.py` | 抓取、过滤、去重、更新分数 |
| `analyze_batch.py` | 规则/Skill 分析与 JSON 副产物 |
| `run_codex_pipeline.py` | 端到端流水线 |
| `feed_feedback.py` | 分析结果写回评分 |
| `feed_report.py` | 评分报告 Markdown |
| `feed_scores.json` | 持久化评分状态 |
| `settings.json` | 运行默认项 |
| `.env.local` | API Key、Base URL、模型名 |
| `feeds.txt` | RSS 地址列表 |
| `schemas/README.md` | JSON Schema 说明 |
| `policies/` | 抓取 / 分析 / 评分策略模块 |

## 输出形态

每个批次会生成：

- **Markdown** — 给人阅读的分析报告；每条在「建议动作」后包含 **原文链接**；文末**不**附整篇 `## Original Links` 附录  
- **JSON** — 同一次运行的结构化数据  

常见路径：

- `inputs/<name>.md`、`inputs/<name>.json`  
- `outputs/<name>.md`、`outputs/<name>.json`  

## 常用操作

检查 Skill 环境：

```bash
python cli.py check
```

交互菜单（需在真实终端中运行）：

```bash
python cli.py interactive
```

仅抓取：

```bash
python cli.py fetch --topic "AI, coding, startup opportunities"
```

仅分析：

```bash
python cli.py analyze --input-file inputs/<batch>.md --mode rules
python cli.py --report-lang zh analyze --input-file inputs/<batch>.md --mode skill
```

完整流水线：

```bash
python cli.py run --analysis-mode auto
```

生成评分报告：

```bash
python cli.py report
```

归档旧批次（保留最新的 `*-rss-batch` 及配对的分析文件）：

```bash
python cli.py archive
python cli.py archive --dry-run -v
python cli.py archive --interval 3600
```

## 校验说明

已在本地跑通：`check`、`fetch`、`analyze`（rules/skill）、`run`、`report`、`archive`、`interactive` 等路径。

更多运维说明见 **`RUNBOOK.md`**。

## 安全

请勿提交 **`.env.local`** 或真实 API 密钥。凭证与自检说明见 **[SECURITY.md](SECURITY.md)**。
