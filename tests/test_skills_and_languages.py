"""Unit tests for Phase C multilingual architecture, skills registry, and language detection."""

from __future__ import annotations

import pytest

from syssathi.core.i18n import t
from syssathi.core.languages import get_language_registry
from syssathi.core.wsl import get_environment_info, is_wsl
from syssathi.host.router import classify_intent, route
from syssathi.skills import ALL_SKILLS, DiagnoseSkill, resolve_skill
from syssathi.skills.base import LessonCard


class TestLanguageRegistry:
    def test_loads_12_languages(self):
        reg = get_language_registry()
        langs = reg.list_languages()
        assert len(langs) == 12
        codes = {lang.code for lang in langs}
        assert "hi" in codes
        assert "en" in codes
        assert "bn" in codes
        assert "ta" in codes
        assert "te" in codes
        assert "mr" in codes
        assert "gu" in codes
        assert "kn" in codes
        assert "ml" in codes
        assert "pa" in codes
        assert "or" in codes
        assert "ur" in codes

    def test_detects_devanagari_hindi(self):
        reg = get_language_registry()
        detected = reg.detect_language("मेरा लैपटॉप धीमा है")
        assert detected.code in ("hi", "mr")
        assert detected.default_script == "devanagari"

    def test_detects_bengali(self):
        reg = get_language_registry()
        detected = reg.detect_language("আমার ল্যাপটপ ধীর")
        assert detected.code == "bn"
        assert detected.default_script == "bengali"

    def test_detects_tamil(self):
        reg = get_language_registry()
        detected = reg.detect_language("என் மடிக்கணினி மெதுவாக உள்ளது")
        assert detected.code == "ta"
        assert detected.default_script == "tamil"

    def test_detects_telugu(self):
        reg = get_language_registry()
        detected = reg.detect_language("నా ల్యాప్‌టాప్ నెమ్మదిగా ఉంది")
        assert detected.code == "te"
        assert detected.default_script == "telugu"

    def test_detects_latin_fallback(self):
        reg = get_language_registry()
        detected = reg.detect_language("My PC is lagging", default="en")
        assert detected.code == "en"


class TestMultilingualRouter:
    def test_routes_multilingual_slowness_to_fast(self):
        assert route("मेरा लैपटॉप बहुत धीमा चल रहा है") == "fast"
        assert route("আমার ল্যাপটপ ধীর") == "fast"
        assert route("என் மடிக்கணினி மெதுவாக உள்ளது") == "fast"
        assert route("mera laptop slow hai") == "fast"

    def test_classifies_intents(self):
        assert classify_intent("mera laptop slow hai") == "diagnose"
        assert classify_intent("battery kitni bachi hai?") == "battery"
        assert classify_intent("list all startup applications") == "startup"
        assert classify_intent("VPN kya hota hai?") == "explain"
        assert classify_intent("free video editing software batao") == "toolfinder"
        assert classify_intent("wifi password kaise badlu?") == "howto"
        assert classify_intent("error 0x80070005 aa raha hai") == "errors"
        assert classify_intent("namaste, aap kaise ho?") == "general"


class TestSkillsRegistry:
    def test_all_skills_registered(self):
        skill_names = {s.name for s in ALL_SKILLS}
        assert "diagnose" in skill_names
        assert "explain" in skill_names
        assert "toolfinder" in skill_names
        assert "howto" in skill_names
        assert "errors" in skill_names

    def test_resolve_skill_routes_query(self):
        skill = resolve_skill("laptop bohot slow ho gaya hai")
        assert isinstance(skill, DiagnoseSkill)

    def test_diagnose_skill_lesson_card_generation(self):
        skill = DiagnoseSkill()
        # High RAM teachable moment
        card_ram = skill.build_lesson_card({
            "findings": [{"code": "RAM_HIGH", "message": "RAM 92%"}]
        })
        assert card_ram is not None
        assert isinstance(card_ram, LessonCard)
        assert "RAM" in card_ram.title
        assert "Ctrl + Shift + Esc" in card_ram.actionable_tip

        # High CPU teachable moment
        card_cpu = skill.build_lesson_card({
            "findings": [{"code": "CPU_HIGH", "message": "CPU 88%"}]
        })
        assert card_cpu is not None
        assert "CPU" in card_cpu.title

        # Startup teachable moment
        card_startup = skill.build_lesson_card({
            "findings": [{"code": "STARTUP_HIGH", "message": "10 apps"}]
        })
        assert card_startup is not None
        assert "Startup" in card_startup.title


class TestLocalizationAndWSL:
    def test_i18n_translation(self):
        hi_latn = t("greeting", lang="hi", script="latin")
        assert "SysSathi" in hi_latn

        hi_dev = t("greeting", lang="hi", script="devanagari")
        assert "सिस्सार्थी" in hi_dev

        en = t("greeting", lang="en")
        assert "Windows system companion" in en

    def test_wsl_detection_info(self):
        info = get_environment_info()
        assert "os" in info
        assert "is_wsl" in info
        assert isinstance(info["is_wsl"], bool)
        assert "python_version" in info

