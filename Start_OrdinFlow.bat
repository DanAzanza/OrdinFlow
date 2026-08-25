@echo off
cd /d "%~dp0"
title OrdinFlow Launcher

REM 1. Prefer pythonw.exe (windowless background execution)
if exist "%~dp0venv\Scripts\pythonw.exe" (
    start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0main.py" %*
    exit /b 0
)

REM 2. Fallback to python.exe if pythonw.exe is missing
if exist "%~dp0venv\Scripts\python.exe" (
    start "" "%~dp0venv\Scripts\python.exe" "%~dp0main.py" %*
    exit /b 0
)

REM 3. Virtual environment missing
echo ====================================================
echo [ERROR] OrdinFlow virtual environment not found!
echo ====================================================
echo.
echo Please run 'Install_OrdinFlow.bat' first to install
echo all required dependencies and AI models.
echo.
pause
exit /b 1
