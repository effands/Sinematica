@echo off
title Sinematica AI Studio - Automated E2E Scene Generation Test Runner
cd /d "%~dp0"
chcp 65001 >nul

echo =====================================================================
echo   SINEMATICA AI STUDIO - AUTOMATED E2E SCENE GENERATION TEST RUNNER
echo =====================================================================
echo.

IF EXIST ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python scripts/test_e2e_generation.py %*

set EXIT_CODE=%ERRORLEVEL%
echo.
echo =====================================================================
if %EXIT_CODE% EQU 0 (
    echo [SELESAI] Pengujian E2E Scene Generation Berhasil! (Exit Code: 0)
) else (
    echo [GAGAL] Pengujian E2E Scene Generation Mengalami Kendala (Exit Code: %EXIT_CODE%)
)
echo =====================================================================
echo.
pause
