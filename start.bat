@echo off
title Sinematica AI Studio - Google Flow Video Generator
cd /d "%~dp0"

echo ===================================================
echo   SINEMATICA AI STUDIO - GOOGLE FLOW AUTO GENERATOR
echo ===================================================
echo.

IF NOT EXIST ".env" (
    echo [Info] Membuat file .env...
    copy .env.example .env
)

SET PORT=8888
IF NOT "%~1"=="" (
    echo %~1| findstr /r "^[0-9][0-9]*$" >nul
    if not errorlevel 1 SET PORT=%~1
)

echo [1/2] Memeriksa Environment...
IF EXIST ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

echo.
echo ===================================================
echo  Menjalankan Server Sinematica AI di Port %PORT%
echo  Membuka tab browser otomatis ke: http://127.0.0.1:%PORT%
echo ===================================================
echo.

:: Otomatis buka tab browser di Port 8888
start "" "http://127.0.0.1:%PORT%"

python -m uvicorn backend.main:app --host 127.0.0.1 --port %PORT% --reload --reload-dir backend --reload-dir engine

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Server terhenti. Tekan tombol apa saja untuk keluar.
    pause
)
