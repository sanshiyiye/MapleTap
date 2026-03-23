---
name: rss-opportunity-pipeline-skill
description: 通过抓取、分析、整理三个步骤，完成隔离目录内的 RSS 机会挖掘流程
---

# RSS Opportunity Pipeline Skill

你的职责是在 `isolated_rss_codex_agent/` 目录内完成一条完整流程：

1. 获取信息
2. 分析信息
3. 整理结果

## 调用顺序

先执行抓取，再执行分析：

1. 读取 `feeds.txt`
2. 运行 `fetch_batch.py`
3. 确认生成新的 `inputs/*.md`
4. 优先使用 skill 驱动分析；如果本地未配置模型，则退回规则版分析
5. 运行 `analyze_batch.py` 或直接运行 `run_codex_pipeline.py`
5. 确认生成新的 `outputs/*.md`

## 推荐入口

优先使用单入口：

`isolated_rss_codex_agent/run_codex_pipeline.py`

推荐参数：

- `--analysis-mode auto`

含义：

- 如果本地已配置 OpenAI-compatible 模型接口，则读取 skill 并走真正的 skill 分析
- 否则自动退回规则版，保证流程不中断

## 目标信源

当前优先信源是：

- Hacker News
- TechCrunch
- GitHub Blog

其中 Hacker News 是科技、编程、创业、极客圈的核心必选源。

## 输出要求

输出必须至少包含：

- 新抓到的标准化输入文件路径
- 新生成的分析文件路径
- 本轮抓取条数
- 本轮分析条数
- 若有失败项，列出失败信息

## 边界

- 只在 `isolated_rss_codex_agent/` 内工作
- 不修改主项目 `src/`
- 不把中间结果写回主项目目录
