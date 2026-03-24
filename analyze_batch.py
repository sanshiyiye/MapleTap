from __future__ import annotations

import argparse
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from i18n import resolve_report_lang, t
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

# Parallel English copy for low-signal rules (same order as LOW_SIGNAL_RULES).
LOW_SIGNAL_REASON_EN = [
    "This reads more like onboarding or promo content; the opportunity signal is weak.",
    "This is weakly aligned with AI, developer tools, SaaS startups, and related themes.",
]

HIGH_SIGNAL_RULE_EN: dict[str, dict[str, str]] = {
    "developer_ai": {
        "reason": "This item reflects real demand from AI and developer-workflow upgrades with strong productization signals.",
        "risk": "The signal may still be early, with dependency risk on a single platform or ecosystem.",
        "action": "Track adoption and integration paths first, then assess adjacent tooling opportunities.",
    },
    "startup_signal": {
        "reason": "This may indicate rising demand, category shifts, or tighter buying windows worth monitoring.",
        "risk": "Startup headlines can over-narrate; execution detail is often thin—avoid hype-only reads.",
        "action": "Validate pain, willingness to pay, and concrete use cases before committing effort.",
    },
    "infra_signal": {
        "reason": "This points to stability, governance, or ops needs that tend to recur over time.",
        "risk": "Generic solutions may be crowded; differentiation needs a sharp wedge.",
        "action": "Look for vertical workflow wedges rather than competing as a broad platform.",
    },
}

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


def score_item(item: NewsItem) -> tuple[int, dict[str, str] | None, dict[str, str] | None]:
    haystack = f"{item.title} {item.summary}".lower()
    best_rule: dict[str, str] | None = None
    best_score = 40
    matched_low: dict[str, str] | None = None

    for rule in HIGH_SIGNAL_RULES:
        if any(keyword in haystack for keyword in rule["keywords"]):
            if int(rule["score"]) > best_score:
                best_rule = rule
                best_score = int(rule["score"])

    for rule in LOW_SIGNAL_RULES:
        if any(keyword in haystack for keyword in rule["keywords"]):
            if int(rule["score"]) < best_score:
                best_rule = None
                best_score = int(rule["score"])
                matched_low = rule
    return best_score, best_rule, matched_low


def _low_reason_localized(low_rule: dict[str, str] | None, report_lang: str) -> str:
    if not low_rule:
        return ""
    try:
        idx = LOW_SIGNAL_RULES.index(low_rule)
    except ValueError:
        return str(low_rule["reason"])
    if report_lang == "en" and 0 <= idx < len(LOW_SIGNAL_REASON_EN):
        return LOW_SIGNAL_REASON_EN[idx]
    return str(low_rule["reason"])


def _high_fields_localized(rule: dict[str, str], report_lang: str) -> tuple[str, str, str]:
    if report_lang != "en":
        return str(rule["reason"]), str(rule["risk"]), str(rule["action"])
    name = str(rule.get("name", ""))
    en = HIGH_SIGNAL_RULE_EN.get(name)
    if en:
        return en["reason"], en["risk"], en["action"]
    return str(rule["reason"]), str(rule["risk"]), str(rule["action"])


def analyze_item(item: NewsItem, report_lang: str = "zh") -> dict[str, str | int]:
    lang = report_lang if report_lang in ("en", "zh") else "zh"
    score, rule, low_rule = score_item(item)
    adjusted_score = score + int(SOURCE_WEIGHTS.get(item.source.lower(), 0))

    if rule is None:
        low_reason = _low_reason_localized(low_rule, lang)
        return {
            "title": item.title,
            "source": item.source,
            "source_feed": item.source_feed,
            "link": item.link,
            "summary": item.summary,
            "opportunity_type": "watch",
            "judgment": "low" if adjusted_score < 40 else "medium",
            "reason": low_reason or t("report.no_rule.reason", lang=lang),
            "risk": t("report.no_rule.risk", lang=lang),
            "action": t("report.no_rule.action", lang=lang),
            "score": adjusted_score,
        }

    reason, risk, action = _high_fields_localized(rule, lang)
    return {
        "title": item.title,
        "source": item.source,
        "source_feed": item.source_feed,
        "link": item.link,
        "summary": item.summary,
        "opportunity_type": str(rule["opportunity_type"]),
        "judgment": str(rule["judgment"]),
        "reason": reason,
        "risk": risk,
        "action": action,
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


def render_output(
    analyses: list[dict[str, str | int]],
    _source_name: str,
    _mode: str,
    report_lang: str = "zh",
) -> str:
    lang = report_lang if report_lang in ("en", "zh") else "zh"
    colon = "：" if lang == "zh" else ": "

    def label_line(field_key: str, value: str) -> str:
        return f"- **{t(field_key, lang=lang)}**{colon}{value}"

    def label_open(field_key: str) -> str:
        return f"- **{t(field_key, lang=lang)}**{colon}"

    sorted_items = sorted(analyses, key=lambda item: int(item["score"]), reverse=True)
    top_items = sorted_items[:5]

    def judgment_stars(score: int) -> str:
        if score >= 90:
            return t("report.judgment.j90", lang=lang)
        if score >= 80:
            return t("report.judgment.j80", lang=lang)
        if score >= 70:
            return t("report.judgment.j70", lang=lang)
        if score >= 60:
            return t("report.judgment.j60", lang=lang)
        return t("report.judgment.j0", lang=lang)

    def type_label(raw_type: str) -> str:
        key = f"report.type.{raw_type}"
        mapped = t(key, lang=lang)
        return mapped if mapped != key else t("report.type.developer_tools", lang=lang)

    def reason_points(item: dict[str, str | int]) -> list[str]:
        title = str(item["title"]).lower()
        source = str(item["source"]).lower()
        points = [str(item["reason"])]
        if any(k in title for k in ["ai", "agent", "llm", "copilot"]):
            points.append(t("report.extra.reason_ai", lang=lang))
        if any(k in title for k in ["startup", "raises", "funding", "series"]):
            points.append(t("report.extra.reason_startup", lang=lang))
        if any(k in title for k in ["security", "outage", "incident", "supply chain"]):
            points.append(t("report.extra.reason_security", lang=lang))
        if source in {"the github blog", "github blog", "hacker news", "techcrunch"}:
            points.append(t("report.extra.reason_source", lang=lang))
        return points[:3]

    def risk_points(item: dict[str, str | int]) -> list[str]:
        title = str(item["title"]).lower()
        points = [str(item["risk"])]
        if any(k in title for k in ["github", "copilot", "openai"]):
            points.append(t("report.extra.risk_platform", lang=lang))
        if any(k in title for k in ["startup", "raises", "funding", "series"]):
            points.append(t("report.extra.risk_startup", lang=lang))
        return points[:3]

    sources = sorted({str(x["source"]) for x in sorted_items})
    n_sources = len(sources)
    n_items = len(sorted_items)
    overview_line = t("report.overview", lang=lang, sources=n_sources, items=n_items)

    top3 = sorted_items[:3]
    lines = [
        f"# {t('report.doc_title', lang=lang)}",
        "",
        f"## {t('report.section.overview', lang=lang)}",
        "",
        overview_line,
        "",
        f"## {t('report.section.items', lang=lang)}",
        "",
    ]

    for index, analysis in enumerate(sorted_items, start=1):
        score = int(analysis["score"])
        reasons = reason_points(analysis)
        risks = risk_points(analysis)
        lines.extend(
            [
                f"### {index}. {analysis['title']}",
                label_line("report.field.summary", str(analysis["summary"])),
                label_line("report.field.opportunity_type", type_label(str(analysis["opportunity_type"]))),
                label_line("report.field.judgment", judgment_stars(score)),
                label_open("report.field.reasons"),
                *[f"  - {point}" for point in reasons],
                label_open("report.field.risks"),
                *[f"  - {point}" for point in risks],
                label_line("report.field.action", str(analysis["action"])),
                label_line("report.field.link", str(analysis["link"])),
                "",
                "---",
                "",
            ]
        )

    th = t("report.table.rank", lang=lang)
    to = t("report.table.opportunity", lang=lang)
    tt = t("report.table.type", lang=lang)
    tr = t("report.table.core_reason", lang=lang)
    sep = "|------|------|------|----------|"
    lines.extend(
        [
            f"## {t('report.section.ranking', lang=lang)}",
            "",
            f"| {th} | {to} | {tt} | {tr} |",
            sep,
        ]
    )
    for index, item in enumerate(top_items, start=1):
        lines.append(
            f"| {index} | {item['title']} | {type_label(str(item['opportunity_type']))} | {item['reason']} |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            f"## {t('report.section.conclusion', lang=lang)}",
            "",
            t("report.conclusion.top3", lang=lang),
            "",
        ]
    )
    for index, item in enumerate(top3, start=1):
        lines.append(f"{index}. **{item['title']}** - {item['action']}")

    lines.extend(
        [
            "",
            t("report.trend.title", lang=lang),
            t("report.trend.1", lang=lang),
            t("report.trend.2", lang=lang),
            "",
        ]
    )
    return "\n".join(lines)


def ensure_output_appendices(raw_output: str, items: list[NewsItem]) -> str:
    """
    参考版式在「结论」处结束，不追加 Original Links（链接仍在 inputs JSON 中保留）。
    """
    _ = items  # 保留签名便于将来按需恢复附录
    return raw_output.rstrip() + "\n"


def _strip_tail_original_links(markdown: str) -> str:
    """Remove trailing ## Original Links … (aligned with reference report; no appendix)."""
    return re.sub(r"\n##\s+Original\s+Links\s*\n[\s\S]*\Z", "", markdown.rstrip(), flags=re.I).rstrip()


def _normalize_skill_overview(text: str) -> str:
    """Reference 总览为连续段落，去掉末尾多余分隔线。"""
    t = (text or "").strip()
    t = re.sub(r"\n+---\s*$", "", t)
    return t.strip()


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


# (header text variant, canonical field key in Chinese)
_CARD_HEADER_VARIANTS: list[tuple[str, str]] = [
    ("摘要", "摘要"),
    ("Summary", "摘要"),
    ("机会类型", "机会类型"),
    ("Opportunity Type", "机会类型"),
    ("机会判断", "机会判断"),
    ("Judgment", "机会判断"),
    ("机会理由", "机会理由"),
    ("Reason", "机会理由"),
    ("风险", "风险"),
    ("Risk", "风险"),
    ("建议动作", "建议动作"),
    ("Action", "建议动作"),
    ("原文链接", "原文链接"),
    ("Link", "原文链接"),
    ("Source link", "原文链接"),
]


def _card_field_header_key(line: str) -> str | None:
    """
    If line opens a standard card field, return canonical key (中文).

    Only lines with Markdown bold around the field name count as section headers,
    e.g. `- **风险**：`. Plain `- 风险：一段话` is treated as a bullet (so mis-nested
    `  - 风险：...` under 机会理由 does not end the section).
    """
    s = line.strip()
    for variant, canon in _CARD_HEADER_VARIANTS:
        pat_star = rf"^-\s*\*\*{re.escape(variant)}\*\*\s*[：:]\s*"
        if re.match(pat_star, s, re.I):
            return canon
    return None


def _bullet_inner_text(line: str) -> str | None:
    s = line.strip()
    if not s.startswith("- "):
        return None
    return s[2:].strip().replace("**", "")


def _is_misnested_field_bullet(inner: str) -> bool:
    """
    Model sometimes nests 风险/建议动作/原文链接 bullets under 机会理由 or 风险.
    Those should not appear as list items for that section.
    """
    low = inner.casefold()
    prefixes = (
        "风险：",
        "风险:",
        "建议动作：",
        "建议动作:",
        "原文链接：",
        "原文链接:",
        "link:",
        "source link:",
        "risk:",
        "action:",
    )
    return any(inner.startswith(p) or low.startswith(p.casefold()) for p in prefixes)


def extract_block_values(body: str, labels: list[str]) -> list[str]:
    """
    Collect bullet lines under the first matching section header in `labels`.

    Stops at the next *top-level* card field (another - **xx**： header).
    Skips bullets that look like wrongly nested 风险/建议动作/原文链接 lines.
    """
    lowered = {str(l).casefold() for l in labels}
    if "机会理由" in labels or "reason" in lowered:
        primary = "机会理由"
    elif "风险" in labels or "risk" in lowered:
        primary = "风险"
    else:
        primary = labels[0]

    lines = body.splitlines()
    collecting = False
    values: list[str] = []
    for raw_line in lines:
        key = _card_field_header_key(raw_line)
        if not collecting:
            if key == primary:
                collecting = True
            continue
        if key is not None and key != primary:
            break
        inner = _bullet_inner_text(raw_line)
        if inner is None:
            continue
        if _is_misnested_field_bullet(inner):
            continue
        values.append(inner)
    return values


def _skill_extract_section(
    raw_output: str,
    *,
    zh_title: str,
    zh_next: list[str],
    en_title: str,
    en_next: list[str],
    prefer_zh: bool,
) -> str:
    tail = ["Original Links"]
    if prefer_zh:
        first = extract_section(raw_output, zh_title, zh_next + tail)
        if first.strip():
            return first
        return extract_section(raw_output, en_title, en_next + tail)
    first = extract_section(raw_output, en_title, en_next + tail)
    if first.strip():
        return first
    return extract_section(raw_output, zh_title, zh_next + tail)


def render_skill_cards_exact(items: list[NewsItem], raw_output: str, report_lang: str = "zh") -> str:
    lang = report_lang if report_lang in ("en", "zh") else "zh"
    colon = "：" if lang == "zh" else ": "
    prefer_zh = lang == "zh"

    def label_line(field_key: str, value: str) -> str:
        return f"- **{t(field_key, lang=lang)}**{colon}{value}"

    def label_open(field_key: str) -> str:
        return f"- **{t(field_key, lang=lang)}**{colon}"

    raw_output = _strip_tail_original_links(raw_output)
    overview = _skill_extract_section(
        raw_output,
        zh_title="总览",
        zh_next=["逐条分析", "优先级排序", "结论"],
        en_title="Overview",
        en_next=["Item analysis", "Priority ranking", "Conclusion"],
        prefer_zh=prefer_zh,
    )
    overview = _normalize_skill_overview(overview)
    cards_block = _skill_extract_section(
        raw_output,
        zh_title="逐条分析",
        zh_next=["优先级排序", "结论"],
        en_title="Item analysis",
        en_next=["Priority ranking", "Conclusion"],
        prefer_zh=prefer_zh,
    )
    ranking = _skill_extract_section(
        raw_output,
        zh_title="优先级排序",
        zh_next=["结论"],
        en_title="Priority ranking",
        en_next=["Conclusion"],
        prefer_zh=prefer_zh,
    )
    conclusion = _skill_extract_section(
        raw_output,
        zh_title="结论",
        zh_next=[],
        en_title="Conclusion",
        en_next=[],
        prefer_zh=prefer_zh,
    )

    item_map = {item.title: item for item in items}
    lines = [
        f"# {t('report.doc_title', lang=lang)}",
        "",
        f"## {t('report.section.overview', lang=lang)}",
        "",
        overview or t("report.skill.fallback_overview", lang=lang),
        "",
        f"## {t('report.section.items', lang=lang)}",
        "",
    ]

    for index, (title, body) in enumerate(split_card_sections(cards_block), start=1):
        item = item_map.get(title)
        summary = extract_single_value(body, ["摘要", "Summary"]) or (item.summary if item else "")
        opportunity_type = extract_single_value(body, ["机会类型", "Opportunity Type"])
        judgment = extract_single_value(body, ["机会判断", "Judgment"])
        action = extract_single_value(body, ["建议动作", "Action"])
        link = extract_single_value(body, ["原文链接", "Link", "Source link"]) or (item.link if item else "")
        reasons = extract_block_values(body, ["机会理由", "Reason"])
        risks = extract_block_values(body, ["风险", "Risk"])

        lines.extend(
            [
                f"### {index}. {title}",
                label_line("report.field.summary", summary),
                label_line("report.field.opportunity_type", opportunity_type),
                label_line("report.field.judgment", judgment),
                label_open("report.field.reasons"),
            ]
        )
        if reasons:
            for reason in reasons:
                lines.append(f"  - {reason}")
        else:
            lines.append(f"  - {t('report.insufficient', lang=lang)}")
        lines.append(label_open("report.field.risks"))
        if risks:
            for risk in risks:
                lines.append(f"  - {risk}")
        else:
            lines.append(f"  - {t('report.insufficient', lang=lang)}")
        lines.extend(
            [
                label_line("report.field.action", action),
                label_line("report.field.link", link),
                "",
                "---",
                "",
            ]
        )

    th = t("report.table.rank", lang=lang)
    to = t("report.table.opportunity", lang=lang)
    tt = t("report.table.type", lang=lang)
    tr = t("report.table.core_reason", lang=lang)
    rank_fallback = (
        f"| {th} | {to} | {tt} | {tr} |\n|------|------|------|----------|\n"
        + t("report.skill.rank_placeholder_row", lang=lang)
    )
    lines.extend(
        [
            f"## {t('report.section.ranking', lang=lang)}",
            "",
            ranking or rank_fallback,
            "",
            f"## {t('report.section.conclusion', lang=lang)}",
            "",
            conclusion or t("report.skill.conclusion_fallback", lang=lang),
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
    report_lang: str = "zh",
) -> tuple[Path, int]:
    logger = setup_logger("rss_agent.analyze", log_level or str(load_settings().get("log_level", "INFO")))
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown = input_path.read_text(encoding="utf-8")
    items = parse_items(markdown)
    rl = report_lang if report_lang in ("en", "zh") else "zh"
    system_prompt, user_prompt = build_skill_prompt(skill_name, markdown, report_lang=rl)
    raw_output = call_openai_compatible(system_prompt, user_prompt)
    raw_output = render_skill_cards_exact(items, raw_output, report_lang=rl)
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
    report_lang: str = "zh",
) -> tuple[Path, int]:
    logger = setup_logger("rss_agent.analyze", log_level or str(load_settings().get("log_level", "INFO")))
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown = input_path.read_text(encoding="utf-8")
    items = parse_items(markdown)
    rl = report_lang if report_lang in ("en", "zh") else "zh"
    analyses = [analyze_item(item, report_lang=rl) for item in items]

    output_name = output_file or f"{input_path.stem}-analysis.md"
    output_path = output_dir / output_name
    raw_output = render_output(analyses, input_path.name, "rules", report_lang=rl)
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
    parser.add_argument(
        "--report-lang",
        choices=["en", "zh"],
        default=None,
        help="Output language for Markdown (en|zh). Default: RSS_AGENT_REPORT_LANG, locale.json, or en.",
    )
    args = parser.parse_args()
    rl = resolve_report_lang(args.report_lang)

    if args.mode == "skill":
        output_path, item_count = run_skill_analysis(
            input_path=Path(args.input_file),
            output_dir=DEFAULT_OUTPUT_DIR,
            output_file=args.output_file,
            skill_name=args.skill_name,
            log_level=args.log_level,
            report_lang=rl,
        )
    else:
        output_path, item_count = run_analysis(
            input_path=Path(args.input_file),
            output_dir=DEFAULT_OUTPUT_DIR,
            output_file=args.output_file,
            log_level=args.log_level,
            report_lang=rl,
        )

    print(f"saved={output_path}")
    print(f"saved_json={output_path.with_suffix('.json')}")
    print(f"items={item_count}")
    return 0 if item_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
