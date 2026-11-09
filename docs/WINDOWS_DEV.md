# Windows Native Development Guide for SysSathi

## 1. Why Native Windows?

SysSathi ("system companion") is designed to inspect, diagnose, and optimize real personal computers.

When executed inside **WSL (Windows Subsystem for Linux)**:
- `psutil` monitors the Linux VM kernel rather than the host Windows operating system.
- Registry Run keys (`winreg`) and `StartupApproved\Run` are unavailable.
- Windows power management (`powercfg.exe`) and battery health counters cannot read physical hardware.
- Process actions (`terminate`, `kill`) only target Linux VM tasks.

Therefore, **system diagnostics and process management must be run and tested natively on Windows**.

---

## 2. Environment Setup

### Prerequisites
- Windows 10 (version 1903+) or Windows 11 (64-bit).
- Python 3.12 (recommended) installed and added to PATH.
- PowerShell 5.1+ or PowerShell 7+.

### Setup Virtual Environment
In the repository root in PowerShell:
```powershell
# Create virtual environment with Python 3.12
py -3.12 -m venv .venv

# Activate environment in PowerShell
.\.venv\Scripts\activate

# Install dependencies in editable mode
pip install -e ".[dev]"
```

---

## 3. Configuration (.env)

Copy the configuration template:
```powershell
Copy-Item .env.example .env
```

Configure your environment variables:
- `SYSSATHI_LLM_BACKEND`: `evon_remote` (production) or `mock` (offline testing).
- `EVON_BASE_URL`: Evon vLLM endpoint URL.
- `HF_TOKEN`: Hugging Face authorization token.
- `GNANI_API_KEY`: Gnani Vachana platform API key for Prisma STT and Timbre TTS.

---

## 4. Running SysSathi on Windows

### Run Full Test Suite
```powershell
& ".\.venv\Scripts\python.exe" -m pytest tests/ -v
```

### Live MCP Server Smoke Test
Validates all 6 MCP tools directly against the Windows OS:
```powershell
& ".\.venv\Scripts\python.exe" scripts/mcp_smoke.py
```

### Start the Interactive Web UI
```powershell
& ".\.venv\Scripts\python.exe" -m uvicorn syssathi.web.app:app --host 127.0.0.1 --port 8000
```
Open your browser to `http://127.0.0.1:8000`.

### Run CLI in Terminal
```powershell
& ".\.venv\Scripts\python.exe" -m syssathi.host.cli
```

---

## 5. Windows Hardware and System Features

- **Battery Health**: SysSathi queries WMI `BatteryStaticData` and falls back automatically to unprivileged `powercfg /batteryreport /xml /output <tmp>` without requiring administrative privileges.
- **Startup App Intelligence**: Reads `HKCU` and `HKLM` `Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run` binary flags to accurately filter out disabled applications.
- **Process Memory & CPU**: Two-pass sampling measures true active process CPU percentages and sums working set memory across process trees.

