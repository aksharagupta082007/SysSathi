# SysSathi ⚡

**SysSathi** is a multilingual, voice-and-text Windows diagnostic and tech-literacy companion. Built on Gnani AI speech models (Prisma STT, Timbre TTS) and the Evon reasoning LLM, SysSathi explains why your laptop is slow, teaches computer concepts with relatable everyday analogies, recommends verified software tools with download safety advice, and assists with Windows troubleshooting in any language you speak.

---

## 🎯 Core Principles

1. **Teach, don't just do:** Every answer explains *why* (RAM is like a desk surface; CPU like an engine) and surfaces actionable tips (e.g. `Ctrl + Shift + Esc` for Task Manager).
2. **Grounded or silent:** Factual claims cite local hardware measurements or verified curated sources (FMHY, Wikipedia, Microsoft Learn, EFF SSD). Hallucinated numbers and URLs are detected and rejected at runtime.
3. **Native language first:** Supports 12 Indic languages and English in both native script and Romanized code-mixed text (Hinglish, Tanglish, etc.).
4. **Safe by default:** Read-only diagnostics and knowledge tools are free. Any state-changing system action (such as closing apps) requires an explicit UI click on a 60-second expiring proposal. Voice cannot approve destructive actions.
5. **Works on weak hardware & weak internet:** Runs locally on `127.0.0.1`. The knowledge index uses an embedded sub-millisecond SQLite FTS5 database that works completely offline.

---

## 🚀 Quick Start (Windows-First)

### Prerequisites
- Windows 10/11
- Python 3.11 or 3.12 (`py -3.12 --version`)
- Modern browser (Edge, Chrome, or Firefox)

### 1. Setup Virtual Environment
Run in **PowerShell**:
```powershell
# Clone or navigate to the repository
cd C:\Users\<YourUser>\Desktop\gnani

# Create and activate virtual environment
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install in editable mode with development dependencies
pip install -e ".[dev]"
```

### 2. Configure API Keys
Copy the example environment file:
```powershell
cp .env.example .env
```
Edit `.env` with your Gnani API credentials:
```ini
GNANI_API_KEY=your_gnani_api_key_here
GNANI_PRISMA_TOKEN=your_prisma_stt_token_here
LLM_BACKEND=evon_remote # or 'mock' for offline testing
```

### 3. Launch the Application
- **Option A: Web PWA Companion**
  ```powershell
  python scripts/windows_launcher.py
  # Or simply double-click scripts/run_syssathi.bat
  ```
  Opens `http://127.0.0.1:8000` in your default browser.

- **Option B: Command Line Interface (CLI)**
  ```powershell
  # Interactive conversation mode
  syssathi chat

  # Instant hardware diagnostic report
  syssathi diagnose

  # Ask a tech question with citations
  syssathi ask "Mera laptop slow kyun hai?" --lang hi

  # Check knowledge database integrity
  syssathi index status
  ```

---

## 🛠️ CLI Subcommands

| Command | Description |
|---|---|
| `syssathi chat [--lang hi]` | Starts the interactive conversational companion. |
| `syssathi diagnose` | Measures CPU, RAM, Disk, Battery, and Startup apps in real time. |
| `syssathi ask "<query>" [--lang hi]` | One-shot grounded query with source citations and lesson cards. |
| `syssathi eval` | Runs the multi-step evaluation benchmark suite. |
| `syssathi index status` | Verifies the SQLite FTS5 knowledge base and displays SHA-256 signature. |

---

## 🛡️ Privacy & Data Redaction (§7.4)

SysSathi is built with strict privacy controls:
- **Local Application Only:** Binds strictly to `127.0.0.1`. No external cloud accounts or remote telemetry.
- **Automatic Path & Username Redaction:** Personal Windows file paths (e.g. `C:\Users\username\...`) and your local Windows username are automatically scrubbed locally (`<user>`) before any prompt is sent to external AI models.
- **Minimal Data Footprint:** Only the user's spoken audio (sent to Prisma STT) and redacted query text leave your machine. System diagnostics are computed entirely on your local PC via `psutil` and Windows APIs.

---

## 📚 Documentation

- [System Architecture](file:///docs/ARCHITECTURE.md)
- [Safety & Source Policy](file:///docs/SAFETY.md)
- [Contributing & Extension Guide](file:///docs/CONTRIBUTING.md)
- [Windows Native Development](file:///docs/WINDOWS_DEV.md)

---

## 🧪 Running Tests

SysSathi has a comprehensive test suite across 19 modules:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v
```
All 251 unit tests pass 100% green.
