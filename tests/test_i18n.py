import json
import re
from importlib import resources

import pytest

from deadlock_advisor import i18n

CODES = list(i18n.LANGUAGES)


def _strings(code):
    return json.loads((resources.files("deadlock_advisor") / "locales" / f"{code}.json").read_text(encoding="utf-8"))


def _placeholders(text):
    return sorted(re.findall(r"\{(\w+)\}", text))


@pytest.mark.parametrize("code", CODES)
def test_every_language_has_the_same_keys_and_placeholders(code):
    en, other = _strings("en"), _strings(code)
    assert set(other) == set(en), (set(en) ^ set(other))
    for key, text in other.items():
        assert _placeholders(text) == _placeholders(en[key]), key


@pytest.mark.parametrize("code", CODES)
def test_no_developer_words_in_the_texts(code):
    banned = re.compile(r"\bgit\b|config\.json|account_id|match_id|game_dir|\bSHA|checksum|traceback", re.I)
    for key, text in _strings(code).items():
        assert not banned.search(text), (code, key, text)


def test_resolve_system_and_saved_languages():
    assert i18n.resolve("pt-BR") == "pt-BR"
    assert i18n.resolve("pt_PT") == "pt-BR"      # nearest language we have
    assert i18n.resolve("es-MX") == "es"
    assert i18n.resolve("zh-TW") == "zh-CN"
    assert i18n.resolve("de-DE") == "en"         # unknown -> English
    assert i18n.resolve("RU") == "ru"


def test_missing_key_falls_back_to_english_then_to_the_key():
    i18n.set_language("pt-BR")
    try:
        assert i18n.t("msg.ready", hero="Rem") == "Build pronta para Rem."
        assert i18n.t("no.such.key") == "no.such.key"
        assert i18n.strings()["status.waiting"] == "Aguardando partida…"
    finally:
        i18n.set_language("en")


def test_api_language_follows_the_ui_language():
    i18n.set_language("pt-BR")
    try:
        assert i18n.api_language() == "brazilian"
    finally:
        i18n.set_language("en")
    assert i18n.api_language() == "english"
