from __future__ import annotations

import argparse
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from logging_utils import setup_logger
from settings import load_settings
from skill_runtime import build_skill_prompt, call_openai_compatible
from state_utils import atomic_write_json, atomic_write_text

ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = ROOT / "inputs"
DEFAULT_OUTPUT_DIR = ROOT / "outputs"


@dataclass
class NewsItem:
    title: str
    source: str
    source_feed: str
    date: str
    link: str
    item_type: str
    summary: str


HIGH_SIGNAL_RULES = [
    {
        "name": "developer_ai",
        "keywords": ["ai", "agent", "llm", "copilot", "coding model", "developer tool", "open source"],
        "opportunity_type": "developer_tools",
        "judgment": "high",
        "reason": "该条目直接体现了 AI 与开发工作流升级带来的真实需求，具备较强产品化信号。",
        "risk": "信号可能仍偏早期，且存在对单一平台或生态的依赖风险。",
        "action": "优先跟踪用户采用情况与集成路径，评估可切入的配套工具机会。",
        "score": 85,
    },
    {
        "name": "startup_signal",
        "keywords": ["startup", "founder", "saas", "automation", "launch", "funding"],
        "opportunity_type": "startup_signal",
        "judgment": "medium_high",
        "reason": "该条目可能对应新需求爆发、品类演进或采购紧迫度上升，具备市场窗口价值。",
        "risk": "创业新闻存在叙事放大和执行细节不足的问题，需防止被短期热度误导。",
        "action": "尽快验证真实用户痛点、付费意愿与可落地场景，再决定是否投入。",
        "score": 74,
    },
    {
        "name": "infra_signal",
        "keywords": ["security", "outage", "incident", "infrastructure", "observability", "supply chain"],
        "opportunity_type": "infrastructure",
        "judgment": "medium",
        "reason": "该条目指向稳定性、治理或运维刚需，通常具备可重复出现的长期需求。",
        "risk": "通用型方案赛道可能已拥挤，新进入者需要明确差异化定位。",
        "action": "优先寻找细分工作流切口，做垂直场景能力而非泛平台竞争。",
        "score": 66,
    },
]

LOW_SIGNAL_RULES = [
    {
        "keywords": ["newsletter", "podcast", "welcome back", "getting started", "beginner"],
        "reason": "该内容更偏入门或宣传信息，机会信号强度较弱。",
        "score": 24,
    },
    {
        "keywords": ["fashion", "snacks", "mobility", "transportation", "darts"],
        "reason": "该内容与 AI、开发工具、SaaS 创业等核心方向关联度偏低。",
        "score": 18,
    },
]

SOURCE_WEIGHTS = {
    "hacker news": 10,
    "the github blog": 14,
    "github blog": 14,
    "techcrunch": 6,
    "36kr": 4,
    "wired": 1,
    "mit technology review": 0,
}

ITEM_PATTERN = re.compile(
    r"### \d+\.\s+(?P<title>.+?)\n"
    r"- Source:\s+(?P<source>.+?)\n"
    r"- Source Feed:\s+(?P<source_feed>.+?)\n"
    r"- Date:\s+(?P<date>.+?)\n"
    r"- Link:\s+(?P<link>.+?)\n"
    r"- Type:\s+(?P<type>.+?)\n"
    r"- Summary:\s+(?P<summary>.+?)(?=\n### |\n## |\Z)",
    re.S,
)

HEADING_RE = re.compile(r"^###\s+\d+\.\s+(.+?)\s*$", re.M)


def parse_items(markdown: str) -> list[NewsItem]:
    items: list[NewsItem] = []
    for match in ITEM_PATTERN.finditer(markdown):
        items.append(
            NewsItem(
                title=match.group("title").strip(),
                source=match.group("source").strip(),
                source_feed=match.group("source_feed").strip(),
                date=match.group("date").strip(),
                link=match.group("link").strip(),
                item_type=match.group("type").strip(),
                summary=" ".join(match.group("summary").strip().split()),
            )
        )
    return items


def score_item(item: NewsItem) -> tuple[int, dict[str, str] | None, str]:
    haystack = f"{item.title} {item.summary}".lower()
    best_rule: dict[str, str] | None = None
    best_score = 40

    for rule in HIGH_SIGNAL_RULES:
        if any(keyword in haystack for keyword in rule["keywords"]):
            if int(rule["score"]) > best_score:
                best_rule = rule
                best_score = int(rule["score"])

    low_signal_reason = ""
    for rule in LOW_SIGNAL_RULES:
        if any(keyword in haystack for keyword in rule["keywords"]):
            if int(rule["score"]) < best_score:
                best_rule = None
                best_score = int(rule["score"])
                low_signal_reason = str(rule["reason"])
    return best_score, best_rule, low_signal_reason


def analyze_item(item: NewsItem) -> dict[str, str | int]:
    score, rule, low_signal_reason = score_item(item)
    adjusted_score = score + int(SOURCE_WEIGHTS.get(item.source.lower(), 0))

    if rule is None:
        return {
            "title": item.title,
            "source": item.source,
            "source_feed": item.source_feed,
            "link": item.link,
            "summary": item.summary,
            "opportunity_type": "watch",
            "judgment": "low" if adjusted_score < 40 else "medium",
            "reason": low_signal_reason or "当前信号不够具体，暂不足以形成高置信机会判断。",
            "risk": "低信号条目如果权重过高，会分散注意力并影响整体机会排序。",
            "action": "先纳入观察清单，等待后续更多证据再决定是否提升优先级。",
            "score": adjusted_score,
        }

    return {
        "title": item.title,
        "source": item.source,
        "source_feed": item.source_feed,
        "link": item.link,
        "summary": item.summary,
        "opportunity_type": str(rule["opportunity_type"]),
        "judgment": str(rule["judgment"]),
        "reason": str(rule["reason"]),
        "risk": str(rule["risk"]),
        "action": str(rule["action"]),
        "score": adjusted_score,
    }


def score_to_rating(score: int) -> str:
    if score >= 90:
        return "5/5"
    if score >= 80:
        return "4/5"
    if score >= 70:
        return "3/5"
    if score >= 60:
        return "2/5"
    return "1/5"


def score_to_stars(score: int) -> str:
    filled = 5
    if score >= 90:
        filled = 5
    elif score >= 80:
        filled = 4
    elif score >= 70:
        filled = 3
    elif score >= 60:
        filled = 2
    else:
        filled = 1
    return "&#9733;" * filled + "&#9734;" * (5 - filled)


def score_band(score: int) -> str:
    if score >= 90:
        return "[TOP PICK]"
    if score >= 80:
        return "[HIGH]"
    if score >= 70:
        return "[MEDIUM]"
    if score >= 60:
        return "[WATCH]"
    return "[LOW]"


def judgment_label(judgment: str) -> str:
    mapping = {
        "high": "[HIGH CONVICTION]",
        "medium_high": "[STRONG SIGNAL]",
        "medium": "[WATCH CLOSELY]",
        "low": "[LOW PRIORITY]",
    }
    return mapping.get(judgment, f"[{judgment.upper()}]")


def render_chinese_overview(analyses: list[dict[str, str | int]]) -> list[str]:
    sources = sorted({str(item["source"]) for item in analyses})
    top_items = analyses[:3]
    top_titles = "；".join(str(item["title"]) for item in top_items)
    return [
        "本次 RSS 批次已完成重点机会筛选，输出优先级最高的内容以便先读先判断。",
        f"当前共纳入 {len(analyses)} 条结果，来源包括：{', '.join(sources)}。",
        f"优先关注的条目包括：{top_titles}。",
        "建议先阅读 Top Picks 区块，再根据 Link 打开原文做进一步判断。",
    ]


def render_output(analyses: list[dict[str, str | int]], source_name: str, mode: str) -> str:
    sorted_items = sorted(analyses, key=lambda item: int(item["score"]), reverse=True)
    top_items = sorted_items[:5]

    def cn_judgment(score: int) -> str:
        if score >= 90:
            return "⭐⭐⭐⭐⭐ 极高机会"
        if score >= 80:
            return "⭐⭐⭐⭐ 高机会"
        if score >= 70:
            return "⭐⭐⭐ 中等机会"
        if score >= 60:
            return "⭐⭐ 观察机会"
        return "⭐ 低机会"

    def cn_type(raw_type: str) -> str:
        mapping = {
            "developer_tools": "产品机会",
            "startup_signal": "产品机会、投资观察",
            "infrastructure": "产品机会",
            "watch": "观察机会",
        }
        return mapping.get(raw_type, "产品机会")

    def reason_points(item: dict[str, str | int]) -> list[str]:
        title = str(item["title"]).lower()
        source = str(item["source"]).lower()
        points = [str(item["reason"])]
        if any(k in title for k in ["ai", "agent", "llm", "copilot"]):
            points.append("AI 能力正从单点功能走向流程化协作，具备持续演进空间。")
        if any(k in title for k in ["startup", "raises", "funding", "series"]):
            points.append("资本与市场关注提升，说明该方向可能进入可验证商业化阶段。")
        if any(k in title for k in ["security", "outage", "incident", "supply chain"]):
            points.append("稳定性与安全问题属于高频刚需，付费与复购潜力通常更高。")
        if source in {"the github blog", "github blog", "hacker news", "techcrunch"}:
            points.append("信源在开发者与科技社区影响力较高，可作为趋势跟踪的先行指标。")
        return points[:3]

    def risk_points(item: dict[str, str | int]) -> list[str]:
        title = str(item["title"]).lower()
        points = [str(item["risk"])]
        if any(k in title for k in ["github", "copilot", "openai"]):
            points.append("若过度依赖头部平台生态，后续可能面临接口策略或定价变化风险。")
        if any(k in title for k in ["startup", "raises", "funding", "series"]):
            points.append("融资与曝光不等于长期留存，需关注真实使用频率和转化质量。")
        return points[:3]

    def action_text(item: dict[str, str | int]) -> str:
        title = str(item["title"]).lower()
        base = str(item["action"])
        if any(k in title for k in ["ai", "agent", "llm", "copilot"]):
            return base + "；可先做小范围 PoC，验证在现有流程中的提效幅度。"
        if any(k in title for k in ["security", "outage", "incident"]):
            return base + "；建议同步梳理可观测性与告警链路，明确可量化改进目标。"
        return base + "；建议先用 1-2 个真实场景做验证，再扩大投入。"

    top3 = sorted_items[:3]
    top_titles = "；".join(str(item["title"]) for item in top3)
    lines = [
        "# RSS 科技机会分析",
        "",
        "## 总览",
        "",
        f"本次批次来自 `{source_name}`，分析模式 `{mode}`，共处理 {len(sorted_items)} 条内容。优先关注：{top_titles}。",
        "",
        "## 逐条分析",
        "",
    ]

    for index, analysis in enumerate(sorted_items, start=1):
        score = int(analysis["score"])
        reasons = reason_points(analysis)
        risks = risk_points(analysis)
        lines.extend(
            [
                f"### {index}. {analysis['title']}",
                f"- **摘要**：{analysis['summary']}",
                f"- **机会类型**：{cn_type(str(analysis['opportunity_type']))}",
                f"- **机会判断**：{cn_judgment(score)}",
                "- **机会理由**：",
                *[f"  - {point}" for point in reasons],
                "- **风险**：",
                *[f"  - {point}" for point in risks],
                f"- **建议动作**：{action_text(analysis)}",
                f"- **原文链接**：{analysis['link']}",
                "",
                "---",
                "",
            ]
        )

    lines.extend(
        [
            "## 优先级排序",
            "",
            "| 排名 | 机会 | 类型 | 核心理由 |",
            "|------|------|------|----------|",
        ]
    )
    for index, item in enumerate(top_items, start=1):
        lines.append(
            f"| {index} | {item['title']} | {cn_type(str(item['opportunity_type']))} | {item['reason']} |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 结论",
            "",
            "**最值得跟进的3个机会**：",
            "",
        ]
    )
    for index, item in enumerate(top3, start=1):
        lines.append(f"{index}. **{item['title']}** - {item['action']}")

    lines.extend(
        [
            "",
            "**关键趋势判断**：",
            "- AI 与开发工具相关信号仍是当前批次主线，可优先跟进高分条目。",
            "- 评分用于信息分诊，正式决策前需回到原文链接做二次判断。",
            "",
        ]
    )
    return "\n".join(lines)


def render_original_links(items: list[NewsItem]) -> str:
    lines = ["## Original Links", ""]
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item.title}")
        lines.append(f"   - Source: {item.source}")
        lines.append(f"   - Link: {item.link}")
    lines.append("")
    return "\n".join(lines)


def ensure_output_appendices(raw_output: str, items: list[NewsItem]) -> str:
    parts: list[str] = [raw_output.rstrip()]
    if "## Original Links" not in raw_output:
        parts.append(render_original_links(items).rstrip())
    return "\n\n".join(parts) + "\n"


def extract_section(markdown: str, heading: str, next_headings: list[str]) -> str:
    start_match = re.search(rf"^##\s+{re.escape(heading)}\s*$", markdown, re.M)
    if not start_match:
        return ""
    start = start_match.end()
    end = len(markdown)
    for next_heading in next_headings:
        next_match = re.search(rf"^##\s+{re.escape(next_heading)}\s*$", markdown[start:], re.M)
        if next_match:
            end = min(end, start + next_match.start())
    return markdown[start:end].strip()


def split_card_sections(markdown: str) -> list[tuple[str, str]]:
    matches = list(HEADING_RE.finditer(markdown))
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections.append((title, markdown[start:end].strip()))
    return sections


def extract_single_value(body: str, labels: list[str]) -> str:
    for raw_line in body.splitlines():
        line = raw_line.strip()
        normalized = line.replace("**", "")
        for label in labels:
            prefix = f"- {label}："
            if normalized.startswith(prefix):
                return normalized[len(prefix):].strip()
            prefix_ascii = f"- {label}:"
            if normalized.startswith(prefix_ascii):
                return normalized[len(prefix_ascii):].strip()
    return ""


def extract_block_values(body: str, labels: list[str]) -> list[str]:
    lines = body.splitlines()
    collecting = False
    values: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip()
        normalized = line.strip().replace("**", "")
        if any(normalized.startswith(f"- {label}：") or normalized.startswith(f"- {label}:") for label in labels):
            collecting = True
            continue
        if collecting:
            if normalized.startswith("- ") and not normalized.startswith("- " + "") and "：" in normalized:
                break
            stripped = normalized.lstrip("-").strip()
            if not stripped:
                continue
            if stripped.startswith("- "):
                stripped = stripped[2:].strip()
            values.append(stripped)
    return values


def render_skill_cards_exact(items: list[NewsItem], raw_output: str) -> str:
    overview = extract_section(raw_output, "总览", ["逐条分析", "优先级排序", "结论", "Original Links"])
    cards_block = extract_section(raw_output, "逐条分析", ["优先级排序", "结论", "Original Links"])
    ranking = extract_section(raw_output, "优先级排序", ["结论", "Original Links"])
    conclusion = extract_section(raw_output, "结论", ["Original Links"])

    item_map = {item.title: item for item in items}
    lines = [
        "# RSS 科技机会分析",
        "",
        "## 总览",
        "",
        overview or "本次批次已完成机会筛选，以下为按优先级整理的重点内容。",
        "",
        "## 逐条分析",
        "",
    ]

    for index, (title, body) in enumerate(split_card_sections(cards_block), start=1):
        item = item_map.get(title)
        summary = extract_single_value(body, ["摘要", "Summary"]) or (item.summary if item else "")
        opportunity_type = extract_single_value(body, ["机会类型", "Opportunity Type"])
        judgment = extract_single_value(body, ["机会判断", "Judgment"])
        action = extract_single_value(body, ["建议动作", "Action"])
        link = extract_single_value(body, ["原文链接", "Link"]) or (item.link if item else "")
        reasons = extract_block_values(body, ["机会理由", "Reason"])
        risks = extract_block_values(body, ["风险", "Risk"])

        lines.extend(
            [
                f"### {index}. {title}",
                f"- **摘要**：{summary}",
                f"- **机会类型**：{opportunity_type}",
                f"- **机会判断**：{judgment}",
                "- **机会理由**：",
            ]
        )
        if reasons:
            for reason in reasons:
                lines.append(f"  - {reason}")
        else:
            lines.append("  - 信息不足，需结合原文进一步判断")
        lines.append("- **风险**：")
        if risks:
            for risk in risks:
                lines.append(f"  - {risk}")
        else:
            lines.append("  - 信息不足，需结合原文进一步判断")
        lines.extend(
            [
                f"- **建议动作**：{action}",
                f"- **原文链接**：{link}",
                "",
                "---",
                "",
            ]
        )

    lines.extend(
        [
            "## 优先级排序",
            "",
            ranking or "可优先查看逐条分析中的前几项高优先级机会。",
            "",
            "## 结论",
            "",
            conclusion or "建议结合原文链接进一步确认重点机会后再做后续动作。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def parse_analysis_headings(markdown: str) -> list[str]:
    return [match.group(1).strip() for match in HEADING_RE.finditer(markdown)]


def build_analysis_json(
    *,
    input_path: Path,
    output_path: Path,
    mode: str,
    items: list[NewsItem],
    analyses: list[dict[str, str | int]] | None,
    raw_output: str,
) -> dict:
    return {
        "schema": "analysis_result.json",
        "mode": mode,
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "input_markdown_path": str(input_path),
        "output_markdown_path": str(output_path),
        "item_count": len(items),
        "items": [asdict(item) for item in items],
        "analyses": analyses or [],
        "output_headings": parse_analysis_headings(raw_output),
        "raw_output": raw_output,
    }


def write_analysis_outputs(
    *,
    input_path: Path,
    output_path: Path,
    mode: str,
    items: list[NewsItem],
    analyses: list[dict[str, str | int]] | None,
    raw_output: str,
) -> None:
    atomic_write_text(output_path, raw_output)
    atomic_write_json(
        output_path.with_suffix(".json"),
        build_analysis_json(
            input_path=input_path,
            output_path=output_path,
            mode=mode,
            items=items,
            analyses=analyses,
            raw_output=raw_output,
        ),
    )


def run_skill_analysis(
    input_path: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    output_file: str | None = None,
    skill_name: str = "tech-opportunity-skill",
    log_level: str | None = None,
) -> tuple[Path, int]:
    logger = setup_logger("rss_agent.analyze", log_level or str(load_settings().get("log_level", "INFO")))
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown = input_path.read_text(encoding="utf-8")
    items = parse_items(markdown)
    system_prompt, user_prompt = build_skill_prompt(skill_name, markdown)
    raw_output = call_openai_compatible(system_prompt, user_prompt)
    raw_output = render_skill_cards_exact(items, raw_output)
    raw_output = ensure_output_appendices(raw_output, items)

    output_name = output_file or f"{input_path.stem}-skill-analysis.md"
    output_path = output_dir / output_name
    write_analysis_outputs(
        input_path=input_path,
        output_path=output_path,
        mode="skill",
        items=items,
        analyses=None,
        raw_output=raw_output,
    )
    logger.info("analysis_completed mode=skill output=%s items=%s", output_path, len(items))
    return output_path, len(items)


def run_analysis(
    input_path: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    output_file: str | None = None,
    log_level: str | None = None,
) -> tuple[Path, int]:
    logger = setup_logger("rss_agent.analyze", log_level or str(load_settings().get("log_level", "INFO")))
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown = input_path.read_text(encoding="utf-8")
    items = parse_items(markdown)
    analyses = [analyze_item(item) for item in items]

    output_name = output_file or f"{input_path.stem}-analysis.md"
    output_path = output_dir / output_name
    raw_output = render_output(analyses, input_path.name, "rules")
    raw_output = ensure_output_appendices(raw_output, items)
    write_analysis_outputs(
        input_path=input_path,
        output_path=output_path,
        mode="rules",
        items=items,
        analyses=analyses,
        raw_output=raw_output,
    )
    logger.info("analysis_completed mode=rules output=%s items=%s", output_path, len(items))
    return output_path, len(items)


def main() -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Analyze a normalized RSS input batch.")
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--output-file", default=None)
    parser.add_argument("--mode", choices=["rules", "skill"], default=str(settings["analysis_mode"]).replace("auto", "rules"))
    parser.add_argument("--skill-name", default="tech-opportunity-skill")
    parser.add_argument("--log-level", default=str(settings["log_level"]))
    args = parser.parse_args()

    if args.mode == "skill":
        output_path, item_count = run_skill_analysis(
            input_path=Path(args.input_file),
            output_dir=DEFAULT_OUTPUT_DIR,
            output_file=args.output_file,
            skill_name=args.skill_name,
            log_level=args.log_level,
        )
    else:
        output_path, item_count = run_analysis(
            input_path=Path(args.input_file),
            output_dir=DEFAULT_OUTPUT_DIR,
            output_file=args.output_file,
            log_level=args.log_level,
        )

    print(f"saved={output_path}")
    print(f"saved_json={output_path.with_suffix('.json')}")
    print(f"items={item_count}")
    return 0 if item_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
