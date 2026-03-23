---
name: tech-opportunity-skill
description: Generate opportunity analysis for RSS batches in the style of the existing Chinese report, while preserving original links.
---

# Tech Opportunity Skill

Your job is to produce a Chinese opportunity-analysis report for a normalized RSS batch.

## Style target

Match the style of the existing strong reference report:

- concise Chinese summary first
- then item-by-item analysis
- then a priority ranking section
- then a conclusion

Do not force a new visual template. Keep the answer natural and content-first.

## Scope

Prioritize signals related to:

- AI
- coding and developer tools
- open source
- infrastructure and security
- startups and SaaS
- workflow automation

## Required output format

Return Markdown with these sections:

```markdown
# RSS 科技机会分析

## 总览

## 逐条分析

### 1. 标题
- **摘要**：
- **机会类型**：
- **机会判断**：
- **机会理由**：
- **风险**：
- **建议动作**：
- **原文链接**：

## 优先级排序

## 结论

## Original Links
1. 标题
   - Source:
   - Link:
```

## Hard requirements

- Preserve the natural Chinese summary style.
- Each analyzed item must include its original `原文链接`.
- The final output must include an `Original Links` section.
- Do not remove useful reasoning content just to fit a template.
- Do not modify project files outside `isolated_rss_codex_agent/`.
