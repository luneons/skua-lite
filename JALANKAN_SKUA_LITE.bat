@echo off
setlocal
cd /d "%~dp0"

rem Pastikan package dari folder src dapat ditemukan.
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"

rem Jalankan memakai Python Launcher jika tersedia, lalu fallback ke python.
where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3 -m skua_lite %*
) else (
    python -m skua_lite %*
)

set "SKUA_EXIT=%errorlevel%"
if not "%SKUA_EXIT%"=="0" (
    echo.
    echo [ERROR] skua-lite berhenti dengan kode %SKUA_EXIT%.
    pause
)
exit /b %SKUA_EXIT%
