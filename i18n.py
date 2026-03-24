from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from state_utils import atomic_write_json

ROOT = Path(__file__).resolve().parent
LOCALES_DIR = ROOT / "locales"
LOCALE_FILE = ROOT / "locale.json"

SUPPORTED_LANGS = frozenset({"en", "zh"})

_active_lang: str = "en"


def get_ui_lang() -> str:
    return _active_lang


def set_active_lang(lang: str) -> None:
    global _active_lang
    if lang in SUPPORTED_LANGS:
        _active_lang = lang
    else:
        _active_lang = "en"


def read_stored_ui_lang() -> str:
    if not LOCALE_FILE.is_file():
        return "en"
    try:
        data = json.loads(LOCALE_FILE.read_text(encoding="utf-8"))
        v = str(data.get("ui_lang", "en")).strip().lower()
        return v if v in SUPPORTED_LANGS else "en"
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return "en"


def read_stored_report_lang() -> str:
    """Persisted analysis/report language from locale.json; default en."""
    if not LOCALE_FILE.is_file():
        return "en"
    try:
        data = json.loads(LOCALE_FILE.read_text(encoding="utf-8"))
        v = str(data.get("report_lang", "en")).strip().lower()
        return v if v in SUPPORTED_LANGS else "en"
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return "en"


def write_stored_ui_lang(lang: str) -> None:
    if lang not in SUPPORTED_LANGS:
        lang = "en"
    data: dict = {}
    if LOCALE_FILE.is_file():
        try:
            data = json.loads(LOCALE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            data = {}
    data["ui_lang"] = lang
    if "report_lang" not in data:
        data["report_lang"] = "en"
    atomic_write_json(LOCALE_FILE, data)


def write_stored_report_lang(lang: str) -> None:
    if lang not in SUPPORTED_LANGS:
        lang = "en"
    data: dict = {}
    if LOCALE_FILE.is_file():
        try:
            data = json.loads(LOCALE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            data = {}
    data["report_lang"] = lang
    atomic_write_json(LOCALE_FILE, data)


def resolve_report_lang(cli_override: str | None) -> str:
    """
    Priority: CLI --report-lang > env RSS_AGENT_REPORT_LANG > locale.json report_lang > en.
    """
    env_raw = os.environ.get("RSS_AGENT_REPORT_LANG", "").strip().lower()
    env_lang = env_raw if env_raw in SUPPORTED_LANGS else None
    if cli_override and cli_override in SUPPORTED_LANGS:
        return cli_override
    if env_lang:
        return env_lang
    return read_stored_report_lang()


def resolve_ui_lang(*, cli_lang: str | None, save: bool) -> str:
    """
    Priority: CLI --lang > env RSS_AGENT_LANG > locale.json > en.
    If save and cli_lang is set, persist to locale.json.
    """
    env_raw = os.environ.get("RSS_AGENT_LANG", "").strip().lower()
    env_lang = env_raw if env_raw in SUPPORTED_LANGS else None
    stored = read_stored_ui_lang()

    if cli_lang and cli_lang in SUPPORTED_LANGS:
        resolved = cli_lang
        if save:
            write_stored_ui_lang(cli_lang)
            write_stored_report_lang(cli_lang)
    elif env_lang:
        resolved = env_lang
    else:
        resolved = stored

    set_active_lang(resolved)
    return resolved


@lru_cache(maxsize=len(SUPPORTED_LANGS))
def _load_bundle(lang: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{lang}.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in raw.items()}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def t(key: str, *, lang: str | None = None, **kwargs: object) -> str:
    code = lang if (lang is not None and lang in SUPPORTED_LANGS) else get_ui_lang()
    bundle = _load_bundle(code)
    s = bundle.get(key)
    if s is None and code != "en":
        s = _load_bundle("en").get(key)
    if s is None:
        s = key
    if kwargs:
        try:
            return s.format(**kwargs)
        except (KeyError, ValueError):
            return s
    return s


def clear_strings_cache() -> None:
    _load_bundle.cache_clear()
