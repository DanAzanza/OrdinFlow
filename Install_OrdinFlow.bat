@echo off
setlocal enabledelayedexpansion
title OrdinFlow Setup Launcher

echo ====================================================
echo OrdinFlow - Smart Installation Launcher
echo ====================================================

REM 1. Check Python availability on PATH
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install 64-bit Python from https://www.python.org/downloads/
    echo Make sure to check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

REM 2. Create virtual environment if missing
if not exist "%~dp0venv\Scripts\python.exe" (
    echo [*] Creating virtual environment...
    python -m venv "%~dp0venv"
    if !ERRORLEVEL! NEQ 0 (
        echo.
        echo [ERROR] Failed to create virtual environment!
        echo Please ensure you have write permissions in this folder.
        echo.
        pause
        exit /b 1
    )
)

REM 3. Hand off full installation to the isolated Python orchestrator
echo [*] Launching OrdinFlow Environment Orchestrator...
"%~dp0venv\Scripts\python.exe" "%~dp0scripts\setup_environment.py"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ====================================================
    echo [ERROR] Installation did not complete successfully.
    echo Please review the error messages above.
    echo ====================================================
    echo.
    pause
    exit /b 1
)

echo.
pause
exit /b 0
