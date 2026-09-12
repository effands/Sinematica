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

:: Paksa tutup proses apa pun yang masih memakai port ini.
echo [Info] Memeriksa proses lama pada port %PORT%...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$listeners=Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; foreach ($pidValue in $listeners) { if ($pidValue) { Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue; Write-Host ('[Info] Proses lama ditutup: PID ' + $pidValue) } }; Start-Sleep -Milliseconds 500"

:: Otomatis buka tab browser di port yang dipilih
start "" "http://127.0.0.1:%PORT%"

:: Tanpa --reload agar job async tidak terputus saat file berubah.
python -m uvicorn backend.main:app --host 127.0.0.1 --port %PORT%

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Server terhenti. Tekan tombol apa saja untuk keluar.
    pause
)
