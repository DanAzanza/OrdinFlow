@echo off
echo ====================================================
echo OrdinFlow - Smart Installations-Skript
echo ====================================================

REM Pruefen ob Python installiert ist
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo FEHLER: Python ist nicht installiert oder nicht im PATH!
    echo Bitte lade Python herunter und setze beim Installieren den Haken bei "Add Python to PATH".
    pause
    exit /b
)

echo [*] Erstelle virtuelle Umgebung (venv)...
python -m venv venv

echo [*] Aktiviere venv und installiere Abhaengigkeiten...
call venv\Scripts\activate
python -m pip install --upgrade pip

REM Automatische GPU-Erkennung (NVIDIA vs. AMD/Intel vs. CPU) via PowerShell
set GPU_RES=0
powershell -NoProfile -Command "if ((Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -match 'NVIDIA') { exit 10 } else if ((Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -match 'AMD|Radeon|Intel') { exit 20 } else { exit 0 }"
set GPU_RES=%ERRORLEVEL%

if %GPU_RES% EQU 10 (
    echo [*] NVIDIA GPU erkannt! Installiere llama-cpp-python mit NVIDIA CUDA Hardwarebeschleunigung...
    pip install --force-reinstall llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
    echo [*] Installiere CUDA Runtime Bibliotheken...
    pip install nvidia-cublas nvidia-cuda-runtime
) else if %GPU_RES% EQU 20 (
    echo [*] AMD / Intel GPU erkannt! Installiere llama-cpp-python mit Vulkan-Hardwarebeschleunigung...
    pip install --force-reinstall "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.34-vulkan/llama_cpp_python-0.3.34-py3-none-win_amd64.whl"
) else (
    echo [*] Keine dedizierte GPU gefunden. Installiere Standard-CPU-Variante...
    pip install llama-cpp-python
)

echo [*] Installiere weitere Abhaengigkeiten aus requirements.txt (inkl. RapidOCR ONNX)...
pip install -r requirements.txt

echo [*] Pruefe KI-Vision-Modelle...
python scripts/download_models.py

echo.
echo ====================================================
echo Installation erfolgreich abgeschlossen!
echo OrdinFlow ist sofort einsatzbereit (Zero-Setup).
echo ====================================================
echo.
pause


