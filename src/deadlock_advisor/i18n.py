"""Translations. One JSON file per language in ``locales/`` serves both the Python messages
and the web page (``/api/i18n``). English is the source of truth and the fallback: a key
missing from another language falls back to the English text, so a half-done translation
never shows a raw key.

To add a language: copy ``locales/en.json`` to ``locales/<code>.json``, translate the values
(keep the ``{placeholders}``), and add the code to ``LANGUAGES`` below.
"""
from __future__ import annotations

import json
import locale
import os
import sys
from functools import lru_cache
from importlib import resources

DEFAULT = "en"
# code -> (name in its own language, deadlock-api asset language for hero/item names)
LANGUAGES = {
    "en": ("English", "english"),
    "pt-BR": ("Português (Brasil)", "brazilian"),
    "es": ("Español", "spanish"),
    "ru": ("Русский", "russian"),
    "zh-CN": ("简体中文", "schinese"),
}

_current = DEFAULT


@lru_cache(maxsize=None)
def _load(code: str) -> dict[str, str]:
    try:
        text = (resources.files("deadlock_advisor") / "locales" / f"{code}.json").read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, ValueError, FileNotFoundError):
        return {}
    return data if isinstance(data, dict) else {}


def _system_locale() -> str:
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, len(buf)):
                return buf.value
        except Exception:  # noqa: BLE001 - fall through to the portable way
            pass
    for var in ("LC_ALL", "LANG"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        return locale.getlocale()[0] or ""
    except ValueError:
        return ""


def resolve(code: str | None) -> str:
    """A supported language for a setting value: "" / None = follow the system language."""
    raw = (code or "").strip() or _system_locale()
    low = raw.replace("_", "-").lower()
    for known in LANGUAGES:
        if low == known.lower():
            return known
    base = low.split("-")[0]
    if base == "zh":
        return "zh-CN"
    for known in LANGUAGES:
        if known.lower().split("-")[0] == base:
            return known
    return DEFAULT


def set_language(code: str | None) -> str:
    global _current
    _current = resolve(code)
    return _current


def current() -> str:
    return _current


def api_language() -> str:
    """The deadlock-api `language` value, so hero and item names match the app language."""
    return LANGUAGES[_current][1]


def strings(code: str | None = None) -> dict[str, str]:
    """Every string for a language (English underneath), for the web page."""
    return _load(DEFAULT) | (_load(code or _current) if (code or _current) != DEFAULT else {})


def t(key: str, **params) -> str:
    text = _load(_current).get(key) or _load(DEFAULT).get(key) or key
    if not params:
        return text
    try:
        return text.format(**params)
    except (KeyError, IndexError, ValueError):
        return text
