---
name: rss-fetch-skill
description: 抓取 RSS 或网页更新，并整理成可供机会分析的标准输入材料
---

# RSS Fetch Skill

你的职责是把分散的 RSS 源、网页更新或搜索结果，整理成 `tech-opportunity-skill` 可直接消费的输入文件。

## 目标

生成一个放在 `isolated_rss_codex_agent/inputs/` 下的 Markdown 文件，供后续机会分析使用。

## 适用输入

- 直接给定的 RSS feed URL
- 网页文章列表页
- 用户手工提供的若干链接
- 已有的搜索结果摘要

## 工作步骤

1. 明确本次抓取范围：
   - 主题
   - 时间范围
   - 信息源
2. 尽量从 RSS feed 获取最近条目
3. 如果无法直接读取 RSS：
   - 退化为读取文章页或搜索结果页
   - 提取标题、日期、来源、链接、摘要
4. 去掉明显无关、重复、营销噪音内容
5. 整理为标准 Markdown 输入文件
6. 保存到 `isolated_rss_codex_agent/inputs/`

## 标准输出格式

输出文件必须使用以下结构：

```markdown
# RSS Input Batch

## Batch Metadata
- Topic:
- Collected At:
- Collector:
- Notes:

## Items

### 1. Title
- Source:
- Date:
- Link:
- Type:
- Summary:

### 2. Title
- Source:
- Date:
- Link:
- Type:
- Summary:
```

## 数据质量要求

- 优先保留一手来源
- 摘要尽量短，保留事实，不写长篇改写
- 如果日期不确定，要写明
- 如果某条内容只是推测或二手总结，要写明来源性质

## 与后续 skill 的关系

这个 skill 只负责整理输入，不负责机会判断。

整理完成后，交给：

- `isolated_rss_codex_agent/skills/tech-opportunity-skill/SKILL.md`

## 文件边界

只在以下目录内工作：

- `isolated_rss_codex_agent/inputs/`
- `isolated_rss_codex_agent/outputs/`

不要修改主项目目录下的内容。
