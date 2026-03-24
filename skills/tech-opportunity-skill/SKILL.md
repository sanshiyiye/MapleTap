---
name: tech-opportunity-skill
description: Generate opportunity analysis for RSS batches in Chinese, matching the reference Markdown layout (per-item 原文链接 after 建议动作; no end-of-doc Original Links appendix).
---

# Tech Opportunity Skill

Your job is to produce a Chinese opportunity-analysis report for a normalized RSS batch.

## Style target (layout, not wording)

Match the **reference report layout** (same section order and Markdown shapes):

- One or more **continuous paragraphs** under `## 总览` — **no** subheadings like「核心趋势观察」, **no** bullet list under 总览, **no** `---` between 总览 and `## 逐条分析`.
- Each item under `## 逐条分析` uses **exactly** these fields in order:
  - `- **摘要**：` single line
  - `- **机会类型**：` single line — use **机会标签** such as `产品机会`、`内容机会`、`投资观察`、`就业机会`（可用顿号或逗号并列，如 `产品机会、投资观察`）; **do not** use `AI + 开发者工具 + 安全` style plus-chains unless unavoidable.
  - `- **机会判断**：` single line — **must** use star rating + label, e.g. `⭐⭐⭐⭐⭐ 极高机会`, `⭐⭐⭐⭐ 高机会`, `⭐⭐⭐ 中等机会`, `⭐⭐ 低机会`, `⭐ 低机会`
  - `- **机会理由**：` then **only** real points as `  - ` bullets (one line each)
  - `- **风险**：` then either **one** line after the colon **or** `  - ` bullets (reference uses both; be consistent within one item)
  - `- **建议动作**：` **one** line only
  - `- **原文链接**：` **one** line only — paste the URL from the input item's `- Link:` line for that entry.
- `## 优先级排序` must be a **Markdown table** with **exact** header row:

```text
| 排名 | 机会 | 类型 | 核心理由 |
|------|------|------|----------|
```

Use numeric ranks `1`, `2`, `3`… in the first column — **not** `P0` / `P1`. Prefer **5 rows** if the batch has enough strong items.

- `## 结论` must contain:
  - A line `**最值得跟进的3个机会**：` then a blank line, then **numbered** items `1.` … `3.` (short lines like the reference).
  - A line `**关键趋势判断**：` then **2–4** `- ` bullet lines.

- **Do not** output `## Original Links` or any all-items link appendix at the end (per-item 原文链接 is required).

## Scope

Prioritize signals related to:

- AI
- coding and developer tools
- open source
- infrastructure and security
- startups and SaaS
- workflow automation

## Required skeleton (copy this shape)

```markdown
# RSS 科技机会分析

## 总览

（1～3 句连续中文，概述信源数、条数、筛选或关注方向。）

## 逐条分析

### 1. 标题
- **摘要**：
- **机会类型**：
- **机会判断**：
- **机会理由**：
  - …
- **风险**：
  - …
- **建议动作**：

## 优先级排序

| 排名 | 机会 | 类型 | 核心理由 |
|------|------|------|----------|
| 1 | … | … | … |

## 结论

**最值得跟进的3个机会**：

1. …
2. …
3. …

**关键趋势判断**：
- …
- …
```

## Hard requirements

- Preserve natural Chinese; content-first, but **keep the layout rules above**.
- Under `机会理由` / `风险`, only `  - ` bullets for lists — never nest `风险：` / `建议动作：` / `原文链接：` as fake bullets under `机会理由`.
- Do not modify project files outside `isolated_rss_codex_agent/`.
