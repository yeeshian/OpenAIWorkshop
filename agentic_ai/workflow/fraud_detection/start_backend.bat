@echo off
REM Startup script for Fraud Detection Workflow Backend
REM Sets UTF-8 encoding to prevent Unicode errors on Windows

echo Starting Fraud Detection Workflow Backend...

REM Set UTF-8 encoding for Python
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

REM Change to the script directory
cd /d "%~dp0"

REM Run with uv
uv run --prerelease allow backend.py

pause
