"""Windows Native Launcher for SysSathi (Phase E §7.3).

Starts the local SysSathi Web UI bound to 127.0.0.1 and opens the browser.
Local-only, privacy-preserving desktop application.
"""

from __future__ import annotations

import os
import sys
import time
import webbrowser
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from syssathi.core.wsl import is_wsl
from syssathi.host.config import get_settings


def launch_windows_app() -> None:
    """Launch the local SysSathi web application and open in default browser."""
    print("=" * 60)
    print("           SysSathi — Windows Tech Companion")
    print("=" * 60)

    # 1. WSL Check (Decision 1 & §7.3)
    if is_wsl():
        print("\n[WARNING] Detected WSL environment.")
        print("For accurate hardware diagnostics (RAM, CPU, Battery, Startup),")
        print("run natively in Windows PowerShell: .\\.venv\\Scripts\\python.exe scripts\\windows_launcher.py\n")

    # 2. Settings & Keys Check
    settings = get_settings()
    if not settings.GNANI_API_KEY and settings.LLM_BACKEND != "mock":
        print("[NOTICE] GNANI_API_KEY is not set in environment or .env.")
        print("Defaulting to simulated/mock responses for testing.")

    # 3. Open browser after brief delay
    url = f"http://{settings.HOST}:{settings.PORT}"
    print(f"\nStarting SysSathi local desktop companion on {url} ...")
    print("Bound strictly to 127.0.0.1 (local app only, no telemetry).")
    print("Press Ctrl+C in this console window to exit.\n")

    import threading

    def _open_browser() -> None:
        time.sleep(1.2)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_open_browser, daemon=True).start()

    # 4. Run Uvicorn server
    import uvicorn
    uvicorn.run(
        "syssathi.web.app:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
    )


if __name__ == "__main__":
    launch_windows_app()

