"""OrdinFlow Environment & Hardware Setup Orchestrator.

Resilient, hardware-tailored dependency and binary wheel resolver.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path

# Configure UTF-8 stdout if available, with safe fallback
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def check_python_compatibility() -> bool:
    """Verifies 64-bit architecture and warns/checks supported Python versions."""
    is_64bit = sys.maxsize > 2**32
    major, minor = sys.version_info[0], sys.version_info[1]

    version_str = getattr(sys, "version", f"{major}.{minor}").split()[0]
    print(f"[*] Python Version: {version_str} ({'64-bit' if is_64bit else '32-bit'})")

    if not is_64bit:
        print("\n[ERROR] 32-bit Python detected!")
        print("OrdinFlow AI and OCR backends require 64-bit Python (win_amd64).")
        print("Please install 64-bit Python from https://www.python.org/downloads/\n")
        return False

    if major != 3 or minor < 10:
        print(f"\n[ERROR] Python 3.10 or higher is required (found {major}.{minor}).")
        print("Please install Python 3.11 or 3.12 (64-bit) from https://www.python.org/downloads/\n")
        return False

    if minor > 12:
        print(f"\n[!] Notice: Python {major}.{minor} detected.")
        print("    If any native binary wheels fail, Python 3.11 or 3.12 (64-bit) is recommended for maximum compatibility.")

    return True


def detect_gpu_backend() -> str:
    """Detects GPU acceleration backend with strict priority.

    1. NVIDIA CUDA (nvcuda.dll / Registry scan) -> 'cu124'
    2. AMD / Intel Vulkan (vulkan-1.dll + Registry scan) -> 'vulkan'
    3. Fallback -> 'cpu'
    """
    print("[*] Detecting hardware acceleration capabilities...")

    system_root = os.environ.get("SystemRoot", r"C:\Windows")

    # 1. Test for NVIDIA CUDA Driver DLL
    nvcuda_path = os.path.join(system_root, "System32", "nvcuda.dll")
    if sys.platform == "win32" and os.path.exists(nvcuda_path):
        try:
            cuda_lib = ctypes.windll.LoadLibrary(nvcuda_path)
            if cuda_lib:
                print("    [OK] NVIDIA CUDA driver detected (nvcuda.dll). Using CUDA 12.4 backend.")
                return "cu124"
        except Exception:
            pass

    # 2. Registry Display Adapter inspection (handles hybrid dual-GPU laptops)
    has_nvidia = False
    has_vulkan_vendor = False

    if sys.platform == "win32":
        try:
            import winreg

            key_path = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as root_key:
                subkeys_count, _, _ = winreg.QueryInfoKey(root_key)
                for i in range(subkeys_count):
                    try:
                        subkey_name = winreg.EnumKey(root_key, i)
                        if subkey_name.isdigit():
                            with winreg.OpenKey(root_key, subkey_name) as subkey:
                                desc, _ = winreg.QueryValueEx(subkey, "DriverDesc")
                                desc_lower = str(desc).lower()
                                if "nvidia" in desc_lower:
                                    has_nvidia = True
                                elif any(v in desc_lower for v in ["amd", "radeon", "intel", "arc"]):
                                    has_vulkan_vendor = True
                    except OSError:
                        continue
        except Exception:
            pass

    if has_nvidia:
        print("    [OK] NVIDIA GPU detected via Registry. Using CUDA 12.4 backend.")
        return "cu124"

    # 3. Check Vulkan runtime DLL for AMD/Intel
    vulkan_path = os.path.join(system_root, "System32", "vulkan-1.dll")
    if sys.platform == "win32" and os.path.exists(vulkan_path) and has_vulkan_vendor:
        print("    [OK] AMD/Intel GPU with Vulkan runtime detected. Using Vulkan backend.")
        return "vulkan"

    print("    [-] No dedicated GPU acceleration detected. Using CPU backend.")
    return "cpu"


def run_pip(args: list[str]) -> bool:
    """Runs pip in the current Python environment and returns success status."""
    cmd = [sys.executable, "-m", "pip"] + args
    res = subprocess.run(cmd)
    return res.returncode == 0


def install_llama_cpp(backend: str) -> bool:
    """Installs llama-cpp-python strictly from pre-built binary wheels (pinned to stable v0.3.34)."""
    index_url = f"https://abetlen.github.io/llama-cpp-python/whl/{backend}"
    print(f"\n[*] Installing llama-cpp-python v0.3.34 ({backend.upper()}) from {index_url}...")

    cmd = [
        "install",
        "--only-binary",
        "llama-cpp-python",
        "--upgrade",
        "--force-reinstall",
        "llama-cpp-python==0.3.34",
        "--extra-index-url",
        index_url,
    ]

    success = run_pip(cmd)
    if not success and backend != "cpu":
        print(f"[!] Failed to install {backend} wheel. Falling back to CPU prebuilt binary wheel...")
        return install_llama_cpp("cpu")

    if backend == "cu124" and success:
        print("[*] Installing CUDA 12 runtime packages...")
        run_pip(["install", "nvidia-cublas-cu12", "nvidia-cuda-runtime-cu12"])

    return success


def main() -> int:
    root_dir = Path(__file__).resolve().parent.parent
    os.chdir(root_dir)

    print("====================================================")
    print("OrdinFlow Setup & Dependency Orchestrator")
    print("====================================================")

    if not check_python_compatibility():
        return 1

    # 1. Upgrade packaging tools
    print("\n[*] Upgrading pip packaging tools...")
    run_pip(["install", "--upgrade", "pip", "setuptools", "wheel"])

    # 2. Hardware backend detection & llama-cpp-python binary installation
    backend = detect_gpu_backend()
    if not install_llama_cpp(backend):
        print("\n[ERROR] Failed to install pre-built llama-cpp-python binary wheel.")
        return 1

    # 3. Install core dependencies from requirements.txt
    req_file = root_dir / "requirements.txt"
    if req_file.exists():
        print(f"\n[*] Installing core dependencies from {req_file.name}...")
        if not run_pip(["install", "-r", str(req_file), "--prefer-binary"]):
            print("\n[ERROR] Failed to install core dependencies from requirements.txt.")
            return 1

    # 4. Check / Download Models
    models_script = root_dir / "scripts" / "download_models.py"
    if models_script.exists():
        print("\n[*] Checking Vision & LLM Models...")
        res = subprocess.run([sys.executable, str(models_script)])
        if res.returncode != 0:
            print("\n[!] Notice: Model download was skipped or interrupted. You can run scripts/download_models.py anytime.")

    print("\n====================================================")
    print("[OK] OrdinFlow installation successfully completed!")
    print("OrdinFlow is ready to use (Zero-Setup).")
    print("====================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
