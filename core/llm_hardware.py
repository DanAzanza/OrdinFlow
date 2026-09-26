"""Hardware acceleration, GPU/Vulkan detection, and GGUF quantization utilities."""

from __future__ import annotations

import inspect
import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)


def _is_nvidia_cuda_available() -> bool:
    """Checks if an NVIDIA GPU with display drivers is installed on the host."""
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
                                if "nvidia" in str(desc).lower():
                                    return True
                    except OSError:
                        continue
        except Exception as e:
            logger.debug("[LLMHardware] Registry display adapter check failed: %s", e)
    elif sys.platform == "linux":
        return os.path.exists("/proc/driver/nvidia/version") or os.path.exists("/usr/local/cuda")
    return False


def _is_vulkan_available() -> bool:
    """Checks if Vulkan runtime and GPU support are present on the current machine."""
    if sys.platform == "win32":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        vulkan_path = os.path.join(system_root, "System32", "vulkan-1.dll")
        if os.path.exists(vulkan_path):
            try:
                import ctypes

                lib = ctypes.windll.LoadLibrary(vulkan_path)
                if lib:
                    return True
            except Exception as e:
                logger.debug("[LLMHardware] Vulkan LoadLibrary check failed: %s", e)
    elif sys.platform == "linux":
        return os.path.exists("/usr/lib/libvulkan.so.1") or os.path.exists("/usr/lib/x86_64-linux-gnu/libvulkan.so.1")
    return False


def _is_gpu_acceleration_available() -> bool:
    """Checks if GPU acceleration (CUDA, Vulkan, or Metal) is available."""
    if sys.platform == "darwin":
        return True  # Metal is universally available on modern macOS
    return _is_nvidia_cuda_available() or _is_vulkan_available()


def _is_valid_gguf(path_str: str, min_mb: int = 10) -> bool:
    """Verifies file exists, meets minimum size floor, and starts with b'GGUF'."""
    if not path_str or not os.path.isfile(path_str):
        return False
    try:
        if os.path.getsize(path_str) < min_mb * 1024 * 1024:
            return False
        with open(path_str, "rb") as f:
            return f.read(4) == b"GGUF"
    except (OSError, PermissionError):
        return False


_KV_QUANT_MAP: dict[str, int] = {
    "8": 8, "q8_0": 8, "q8": 8, "8bit": 8, "int8": 8, "q8_1": 9,
    "1": 1, "f16": 1, "fp16": 1, "16bit": 1, "half": 1,
    "0": 0, "f32": 0, "fp32": 0, "32bit": 0, "float": 0,
    "2": 2, "q4_0": 2, "q4": 2, "4bit": 2, "q4_1": 3,
    "6": 6, "q5_0": 6, "q5": 6, "5bit": 6, "q5_1": 7,
}

_SUPPORTED_KV_TYPES = {0, 1, 2, 3, 6, 7, 8, 9}


def _parse_ggml_type(val: Any, default: int = 8) -> int:
    """Parses and sanitizes GGML KV cache quantization types, preventing C-level aborts."""
    if val is None or isinstance(val, bool):
        return default
    if isinstance(val, int):
        if val in _SUPPORTED_KV_TYPES:
            return val
        logger.warning("[-] Unsupported GGML KV type integer '%s'. Falling back to %s.", val, default)
        return default
    if isinstance(val, str):
        normalized = val.strip().lower()
        if normalized in _KV_QUANT_MAP:
            return _KV_QUANT_MAP[normalized]
        if any(k in normalized for k in ["q4_k", "q5_k", "q6_k", "q8_k", "iq"]):
            logger.warning(
                "[-] KV cache does not support '%s' (K-quants/IQ). Using Q8_0 (8) fallback.", val
            )
            return default
    return default


def _get_optimal_cpu_threads(configured_threads: int = 0) -> int:
    """Returns configured thread count, or all available CPU cores when <= 0."""
    if configured_threads and configured_threads > 0:
        return configured_threads
    return max(1, os.cpu_count() or 4)


def _generate_layer_candidates(requested: int) -> list[int]:
    """Generates a strictly decreasing layer ladder for dynamic VRAM fitting."""
    standard_steps = [36, 20, 10, 5, 0]
    if requested < 0:
        return [-1, 20, 10, 5, 0]
    if requested == 0:
        return [0]
    return [requested] + [s for s in standard_steps if s < requested]


def _filter_supported_kwargs(cls_or_func: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Filters a dictionary of keyword arguments against the target callable signature."""
    try:
        sig = inspect.signature(cls_or_func)
        has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        if has_varkw:
            return kwargs
        return {k: v for k, v in kwargs.items() if k in sig.parameters}
    except (ValueError, TypeError):
        return kwargs


def _setup_win32_dll_directories() -> None:
    """Configures Windows DLL search paths for CUDA, Vulkan, and llama.cpp runtimes."""
    if sys.platform != "win32":
        return

    dll_dirs: list[str] = []
    sys32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    if os.path.exists(sys32):
        dll_dirs.append(sys32)
        try:
            os.add_dll_directory(sys32)
        except OSError:
            pass

    for p in sys.path:
        if "site-packages" not in p or not os.path.exists(p):
            continue
        bin_dir = os.path.join(p, "bin")
        if os.path.exists(bin_dir):
            dll_dirs.append(bin_dir)
            try:
                os.add_dll_directory(bin_dir)
            except OSError:
                pass
        for candidate in ["nvidia", "llama_cpp"]:
            cand_dir = os.path.join(p, candidate)
            if not os.path.exists(cand_dir):
                continue
            for root, _dirs, files in os.walk(cand_dir):
                if any(f.endswith(".dll") for f in files):
                    dll_dirs.append(root)
                    try:
                        os.add_dll_directory(root)
                    except OSError:
                        pass
    if dll_dirs:
        os.environ["PATH"] = os.pathsep.join(dll_dirs) + os.pathsep + os.environ.get("PATH", "")


def _resolve_model_paths(config: object) -> tuple[str, str]:
    """Resolves absolute paths for the GGUF model and mmproj vision projector."""
    base_dir = os.path.abspath(str(getattr(config, "base_dir", ".")))

    raw_path = getattr(config, "llm_model_path", None) or ""
    if raw_path and not os.path.isabs(raw_path):
        raw_path = os.path.normpath(os.path.join(base_dir, raw_path))

    if not raw_path or not os.path.isfile(raw_path):
        models_dir = os.path.join(base_dir, "models")
        if os.path.isdir(models_dir):
            candidates = [
                os.path.join(models_dir, f)
                for f in os.listdir(models_dir)
                if f.endswith(".gguf") and not f.startswith("mmproj")
            ]
            if candidates:
                raw_path = candidates[0]

    mmproj_raw = getattr(config, "mmproj_path", None) or ""
    if mmproj_raw and not os.path.isabs(mmproj_raw):
        mmproj_raw = os.path.normpath(os.path.join(base_dir, mmproj_raw))

    if not mmproj_raw or not os.path.isfile(mmproj_raw):
        models_dir = os.path.join(base_dir, "models")
        if os.path.isdir(models_dir):
            candidates = [
                os.path.join(models_dir, f)
                for f in os.listdir(models_dir)
                if f.endswith(".gguf") and f.startswith("mmproj")
            ]
            if candidates:
                mmproj_raw = candidates[0]

    return raw_path, mmproj_raw
