@echo off
echo ====================================================
echo OrdinFlow - Smart Installation Script
echo ====================================================

REM Check if Python is installed
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not installed or not in PATH!
    echo Please download Python and check the "Add Python to PATH" box during installation.
    pause
    exit /b
)

echo [*] Creating virtual environment (venv)...
python -m venv venv

echo [*] Activating venv and installing dependencies...
call venv\Scripts\activate
python -m pip install --upgrade pip

REM Automatic GPU detection (NVIDIA vs. AMD/Intel vs. CPU) via PowerShell
set GPU_RES=0
powershell -NoProfile -Command "if ((Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -match 'NVIDIA') { exit 10 } else if ((Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -match 'AMD|Radeon|Intel') { exit 20 } else { exit 0 }"
set GPU_RES=%ERRORLEVEL%

if %GPU_RES% EQU 10 (
    echo [*] NVIDIA GPU detected! Installing llama-cpp-python with NVIDIA CUDA hardware acceleration...
    pip install --force-reinstall llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
    echo [*] Installing CUDA Runtime libraries...
    pip install nvidia-cublas nvidia-cuda-runtime
) else if %GPU_RES% EQU 20 (
    echo [*] AMD / Intel GPU detected! Installing llama-cpp-python with Vulkan hardware acceleration...
    pip install --force-reinstall "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.34-vulkan/llama_cpp_python-0.3.34-py3-none-win_amd64.whl"
) else (
    echo [*] No dedicated GPU found. Installing standard CPU variant...
    pip install llama-cpp-python
)

echo [*] Installing other dependencies from requirements.txt (incl. RapidOCR ONNX)...
pip install -r requirements.txt

echo [*] Checking AI Vision models...
python scripts/download_models.py

echo.
echo ====================================================
echo Installation successfully completed!
echo OrdinFlow is ready to use (Zero-Setup).
echo ====================================================
echo.
pause
