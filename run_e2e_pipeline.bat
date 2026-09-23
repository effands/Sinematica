@echo off
title Sinematica AI Studio - Full Automated E2E Pipeline Runner
cd /d "%~dp0"
chcp 65001 >nul

echo ===============================================================================
echo   SINEMATICA AI STUDIO - FULL AUTOMATED E2E PIPELINE RUNNER
echo   Alur: Katalog Genre/Preset -^> AI Storyboard -^> Fleet Execution -^> Video
echo ===============================================================================
echo.

IF EXIST ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python run_e2e_pipeline.py --scenes 2 --duration 10 --country Indonesia --lang Indonesia --aspect-ratio portrait %*

set EXIT_CODE=%ERRORLEVEL%
echo.
echo ===============================================================================
if %EXIT_CODE% EQU 0 (
    echo [SELESAI] Pipeline E2E Storyboard to Video Berhasil! - Exit Code: 0
) else (
    echo [PERINGATAN] Pipeline Selesai dengan Kode: %EXIT_CODE%
)
echo ===============================================================================
echo.
pause
