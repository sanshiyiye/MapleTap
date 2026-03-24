from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
SKILLS_DIR = ROOT / "skills"
ENV_FILES = [ROOT / ".env.local", ROOT / ".env"]


def load_local_env() -> None:
    for env_path in ENV_FILES:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_skill_text(skill_name: str) -> str:
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    content = skill_path.read_text(encoding="utf-8")
    if content.startswith("---"):
        match = re.match(r"^---\n.*?\n---\n", content, re.S)
        if match:
            content = content[match.end():]
    return content.strip()


def build_skill_prompt(skill_name: str, input_markdown: str, report_lang: str = "zh") -> tuple[str, str]:
    skill_text = load_skill_text(skill_name)
    if report_lang == "en":
        system_prompt = (
            "You are a local RSS opportunity analysis assistant. "
            "Follow the provided skill exactly. "
            "Return concise, structured Markdown entirely in English."
        )
        user_prompt = (
            f"# Active Skill\n\n{skill_text}\n\n"
            f"# Input Batch\n\n{input_markdown}\n\n"
            "# Task\n\n"
            "Follow the skill precisely, analyze the opportunities in the batch, "
            "and return structured Markdown entirely in English.\n\n"
            "Use these top-level section titles (##) in English exactly:\n"
            "## Overview\n"
            "## Item analysis\n"
            "## Priority ranking\n"
            "## Conclusion\n\n"
            "Under each item in Item analysis, use bullet fields in English with these labels:\n"
            "- **Summary**: …\n"
            "- **Opportunity Type**: …\n"
            "- **Judgment**: …\n"
            "- **Reason**: (then nested bullets)\n"
            "- **Risk**: (then nested bullets)\n"
            "- **Action**: …\n"
            "- **Source link**: the article URL copied from the input item's `- Link:` line.\n"
            "Do not add a trailing `## Original Links` section at the end of the document."
        )
    else:
        system_prompt = (
            "You are a local RSS opportunity analysis assistant. "
            "Follow the provided skill exactly. "
            "Return concise, structured Markdown in Chinese."
        )
        user_prompt = (
            f"# Active Skill\n\n{skill_text}\n\n"
            f"# Input Batch\n\n{input_markdown}\n\n"
            "# Task\n\n"
            "Please follow the skill precisely, analyze the opportunities in the batch, "
            "and return structured Markdown in Chinese.\n\n"
            "After `- **建议动作**：` on each item, include `- **原文链接**：` with the URL from that item's "
            "`- Link:` line in the input batch."
        )
    return system_prompt, user_prompt


def call_openai_compatible(system_prompt: str, user_prompt: str) -> str:
    load_local_env()
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=90) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTPError {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"URLError: {exc}") from exc

    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError(f"Invalid response: {body}")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content:
        raise RuntimeError(f"Empty model response: {body}")
    return content
