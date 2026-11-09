# Contributing to SysSathi 🤝

We welcome contributions to SysSathi! This guide explains how to set up your development environment, add languages, extend skills, and add curated knowledge sources.

---

## 1. Development Setup (Windows-First)

SysSathi inspects native Windows hardware metrics (CPU, RAM, WMI, registry, battery). Development should be done natively in **Windows PowerShell**:

```powershell
# 1. Clone repository
git clone https://github.com/gnani/syssathi.git
cd syssathi

# 2. Create virtual environment with Python 3.11 or 3.12
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install in editable mode with development dependencies
pip install -e ".[dev]"

# 4. Copy environment configuration
cp .env.example .env

# 5. Run test suite to verify installation
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

> **Note on WSL:** Developing inside WSL is supported for LLM prompt engineering, but psutil will see the Linux VM, not the host Windows laptop. System diagnostic tools must be tested in Windows PowerShell.

---

## 2. Adding a New Language

SysSathi supports any language supported by Gnani AI models (Prisma STT and Timbre TTS).

### Step 1: Add to `src/syssathi/core/languages.yaml`
```yaml
fr:
  code: fr
  name: French
  native_name: Français
  script: latin
  prisma_code: fr-FR
  timbre_lang: fr
  default_voice: standard
  sentence_delimiters: [".", "!", "?"]
  digits: "0123456789"
```

### Step 2: Add Translations in `src/syssathi/core/i18n.py`
Add key entries to the catalog:
```python
"fr": {
    "greeting": "Bonjour ! Je suis SysSathi, votre compagnon informatique.",
    "ready": "Prêt",
    "thinking": "Réflexion en cours...",
    "laptop_healthy": "Votre ordinateur semble en parfait état.",
}
```

### Step 3: Add a Test in `tests/test_skills_and_languages.py`
Ensure the language detector and registry properly recognize the new language code.

---

## 3. Adding a New Knowledge Source

All knowledge sources must adhere to open and permissive licensing.

### Step 1: Register in `src/syssathi/knowledge/sources.yaml`
```yaml
  archwiki:
    id: archwiki
    name: ArchWiki
    homepage: https://wiki.archlinux.org
    ingest: api
    license: GNU-FDL-1.3
    trust: encyclopedic
    description: Comprehensive community documentation for Linux system configuration.
```

### Step 2: Seed or Ingest Entries
- To add curated seeds, edit `src/syssathi/knowledge/seeds.py`.
- To ingest a markdown repository, run:
  ```python
  from syssathi.knowledge.ingest import ingest_file
  ingest_file("path/to/docs.md", source_id="archwiki", default_category="system")
  ```

### Step 3: Run Integrity Check
```powershell
syssathi index status
```

---

## 4. Authoring a New Skill

Skills encapsulate a specific domain or user need adhering to Principle 1: **"Teach, don't just do."**

### Step 1: Create `src/syssathi/skills/<your_skill>.py`
```python
from typing import Any
from syssathi.skills.base import BaseSkill, LessonCard

class NetworkDiagnosticSkill(BaseSkill):
    name = "network"
    description = "Diagnoses Wi-Fi and network connectivity issues."

    def can_handle(self, text: str, intent: str | None = None) -> bool:
        return any(k in text.lower() for k in ("wifi", "internet", "ping", "dns"))

    def get_tools(self) -> list[str]:
        return ["search_sources", "explain_term"]

    def get_system_prompt(self, language: str = "hi", script: str = "latin") -> str:
        return "You are SysSathi. Diagnose network connectivity and suggest simple router or DNS checks."

    def build_lesson_card(self, tool_output: dict[str, Any]) -> LessonCard | None:
        return LessonCard(
            title="Understanding DNS",
            summary="DNS translates website names into numbers.",
            actionable_tip="Try flushing your DNS cache: ipconfig /flushdns in Command Prompt.",
        )

    def format_deterministic_fallback(self, tool_output: dict[str, Any], language: str = "hi") -> str:
        return "Network router restart karke dekhein."
```

### Step 2: Register in `src/syssathi/skills/__init__.py`
Add the new skill instance to `ALL_SKILLS`:
```python
ALL_SKILLS: list[BaseSkill] = [
    DiagnoseSkill(),
    ExplainSkill(),
    ToolFinderSkill(),
    HowToSkill(),
    ErrorExplainerSkill(),
    NetworkDiagnosticSkill(),  # new skill
]
```

---

## 5. Testing & Code Quality

Before submitting a pull request:
1. Ensure all unit tests pass:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/ -v
   ```
2. Run smoke tests:
   ```powershell
   .\.venv\Scripts\python.exe scripts/mcp_smoke.py
   ```
3. Never bypass runtime grounding or safety checks. All new tools modifying system state must go through the proposal approval lifecycle.

