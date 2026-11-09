@echo off
title SysSathi Companion
cd /d "%~dp0\.."
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\windows_launcher.py
) else (
    python scripts\windows_launcher.py
)
pause

