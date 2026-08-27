"""Abstract LLM Backend layer supporting two implementations.

Both backends implement the same interface so core/vision.py does not need to change:
  - "llama_cpp" : Direct llama.cpp-python API (no separate server process)
  - "server"    : OpenAI-compatible API via a running llama-server with Instructor/Pydantic for structured extraction

Instructor + Pydantic enforce error-free data structure – invalid JSON tokens are blocked at the grammar level.
"""

from __future__ import annotations

import inspect
import logging
import os
import sys
import threading
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


def _filter_supported_kwargs(cls: type, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Filters kwargs against class constructor parameters to prevent TypeErrors."""
    try:
        sig = inspect.signature(cls.__init__)
        valid_keys = set(sig.parameters.keys())
        return {k: v for k, v in kwargs.items() if k in valid_keys}
    except (ValueError, TypeError):
        return kwargs


def _is_nvidia_cuda_available() -> bool:
    """Checks if NVIDIA CUDA acceleration is present on the current machine."""
    if sys.platform == "win32":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        nvcuda_path = os.path.join(system_root, "System32", "nvcuda.dll")
        if os.path.exists(nvcuda_path):
            try:
                import ctypes

                lib = ctypes.windll.LoadLibrary(nvcuda_path)
                if lib:
                    return True
            except Exception:
                pass
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
        except Exception:
            pass
    elif sys.platform == "linux":
        return os.path.exists("/proc/driver/nvidia/version") or os.path.exists("/usr/local/cuda")
    return False


class LLMBackend(ABC):
    """Interface for all LLM backends."""

    @abstractmethod
    def call_vision_api(self, payload: dict[str, object]) -> str: ...

    def preload(self) -> bool:
        """Preloads model weights ahead of time."""
        return True

    def unload(self) -> None:
        """Unloads model weights from memory."""
        pass


# Global module caching for the Llama instance
_GLOBAL_LLM_INSTANCE: object = None
_GLOBAL_LLM_KEY: tuple[Any, ...] | None = None
_LLM_LOCK = threading.RLock()


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
    # 8-bit (Recommended default)
    "8": 8,
    "q8_0": 8,
    "q8": 8,
    "8bit": 8,
    "int8": 8,
    "q8_1": 9,
    # 16-bit / unquantized
    "1": 1,
    "f16": 1,
    "fp16": 1,
    "16bit": 1,
    "half": 1,
    # 32-bit
    "0": 0,
    "f32": 0,
    "fp32": 0,
    "32bit": 0,
    "float": 0,
    # 4-bit / 5-bit
    "2": 2,
    "q4_0": 2,
    "q4": 2,
    "4bit": 2,
    "q4_1": 3,
    "6": 6,
    "q5_0": 6,
    "q5": 6,
    "5bit": 6,
    "q5_1": 7,
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
        # Intercept common user mistake: K-quants / IQ for KV cache
        if any(k in normalized for k in ["q4_k", "q5_k", "q6_k", "q8_k", "iq"]):
            logger.warning(
                "[-] KV cache does not support '%s' (K-quants/IQ). Using Q8_0 (8) fallback.", val
            )
            return default
    return default


def _generate_layer_candidates(requested: int) -> list[int]:
    """Generates a strictly decreasing layer ladder for dynamic VRAM fitting."""
    standard_steps = [36, 20, 10, 5, 0]
    if requested < 0:
        return [-1, 20, 10, 5, 0]
    if requested == 0:
        return [0]
    return [requested] + [s for s in standard_steps if s < requested]


class _LlamaCppBackend(LLMBackend):
    """Direct llama.cpp-python backend with singleton caching and grammar constraints."""

    def __init__(self, config: object) -> None:
        self.config = config

    def _ensure_loaded(self) -> bool:
        """Lazy init with singleton caching: Model is loaded once and reused."""
        global _GLOBAL_LLM_INSTANCE, _GLOBAL_LLM_KEY
        import gc
        import time

        config = self.config  # type: ignore[attr-defined]
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

        model_path = raw_path

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

        n_gpu_layers = getattr(config, "n_gpu_layers", -1)
        if n_gpu_layers is None:
            n_gpu_layers = -1

        n_ctx = getattr(config, "n_ctx", 4096) or 4096
        n_batch = getattr(config, "n_batch", 512) or 512
        n_ubatch = getattr(config, "n_ubatch", 512) or 512
        flash_attn = _is_nvidia_cuda_available()
        parsed_type_k = _parse_ggml_type(getattr(config, "type_k", 8))
        parsed_type_v = _parse_ggml_type(getattr(config, "type_v", 8))

        n_threads = getattr(config, "n_threads", 0)
        if not n_threads or n_threads <= 0:
            n_threads = max(4, (os.cpu_count() or 4) - 2)

        cache_key = (
            model_path,
            mmproj_raw,
            n_gpu_layers,
            n_ctx,
            n_batch,
            n_ubatch,
            flash_attn,
            parsed_type_k,
            parsed_type_v,
        )

        with _LLM_LOCK:
            # Check if global instance is already loaded (Double-checked locking)
            if _GLOBAL_LLM_INSTANCE is not None:
                if _GLOBAL_LLM_KEY == cache_key:
                    self._llm = _GLOBAL_LLM_INSTANCE
                    self._loaded = True
                    logger.debug("[+] Using LLM model instance already cached in VRAM.")
                    return True
                # Explicitly unload stale instance before allocating a new model with changed parameters
                logger.info("[*] LLM configuration changed. Unloading stale model from memory...")
                try:
                    if hasattr(_GLOBAL_LLM_INSTANCE, "close"):
                        _GLOBAL_LLM_INSTANCE.close()  # type: ignore[attr-defined]
                except Exception:
                    pass
                _GLOBAL_LLM_INSTANCE = None
                _GLOBAL_LLM_KEY = None
                gc.collect()

            if getattr(self, "_load_failed", False):
                return False

            if sys.platform == "win32":
                dll_dirs = []
                sys32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
                if os.path.exists(sys32):
                    dll_dirs.append(sys32)
                    try:
                        os.add_dll_directory(sys32)
                    except OSError:
                        pass

                for p in sys.path:
                    if "site-packages" in p and os.path.exists(p):
                        bin_dir = os.path.join(p, "bin")
                        if os.path.exists(bin_dir):
                            dll_dirs.append(bin_dir)
                            try:
                                os.add_dll_directory(bin_dir)
                            except OSError:
                                pass
                        for candidate in ["nvidia", "llama_cpp"]:
                            cand_dir = os.path.join(p, candidate)
                            if os.path.exists(cand_dir):
                                for root, dirs, files in os.walk(cand_dir):
                                    if any(f.endswith(".dll") for f in files):
                                        dll_dirs.append(root)
                                        try:
                                            os.add_dll_directory(root)
                                        except OSError:
                                            pass
                if dll_dirs:
                    os.environ["PATH"] = os.pathsep.join(dll_dirs) + os.pathsep + os.environ.get("PATH", "")

            try:
                from llama_cpp import Llama  # type: ignore[import-untyped]
                from llama_cpp.llama_chat_format import (  # type: ignore[import-untyped]
                    Qwen25VLChatHandler,  # type: ignore[import-untyped]
                )
            except (ImportError, RuntimeError) as _e:
                logger.error(
                    "[!] Could not load 'llama-cpp-python': %s\n    Please run Install_OrdinFlow.bat.",
                    _e,
                )
                self._load_failed = True
                return False

            try:
                if not os.path.isfile(model_path):
                    raise FileNotFoundError(f"Model file not found: {model_path}")

                if not _is_valid_gguf(model_path, min_mb=100):
                    raise ValueError(
                        f"Model file at '{model_path}' is corrupted or incomplete. "
                        "Please run 'python scripts/download_models.py --yes' to download a clean model copy."
                    )

                logger.info("[*] Initializing local VL model from '%s' ...", os.path.basename(model_path))

                chat_handler = None
                if mmproj_raw and os.path.isfile(mmproj_raw):
                    if _is_valid_gguf(mmproj_raw, min_mb=50):
                        logger.info(
                            "[*] Enabling Vision Projector (%s) via Qwen25VLChatHandler...",
                            os.path.basename(mmproj_raw),
                        )
                        chat_handler = Qwen25VLChatHandler(clip_model_path=mmproj_raw, verbose=False)
                    else:
                        logger.warning(
                            "[-] mmproj file at '%s' is corrupted or incomplete. Running without vision support.",
                            mmproj_raw,
                        )
                else:
                    logger.warning("[-] No valid mmproj path found. Model loading without vision support.")

                candidates = _generate_layer_candidates(n_gpu_layers)
                loaded_llm = None

                for cand in candidates:
                    flash_options = [flash_attn] if cand != 0 else [False]
                    if flash_attn and cand != 0:
                        flash_options.append(False)

                    for try_flash in flash_options:
                        logger.info(
                            "[*] Attempting to load LLM with n_gpu_layers=%s, flash_attn=%s...",
                            "ALL" if cand < 0 else str(cand),
                            try_flash,
                        )
                        kwargs: dict[str, Any] = {
                            "model_path": model_path,
                            "n_ctx": n_ctx,
                            "n_batch": n_batch,
                            "n_ubatch": n_ubatch,
                            "chat_handler": chat_handler,
                            "verbose": False,
                            "n_gpu_layers": cand,
                            "n_threads": n_threads,
                            "flash_attn": try_flash,
                            "offload_kqv": (cand != 0),
                            "no_perf": True,
                        }
                        if try_flash:
                            if parsed_type_k is not None:
                                kwargs["type_k"] = parsed_type_k
                            if parsed_type_v is not None:
                                kwargs["type_v"] = parsed_type_v
                        try:
                            gc.collect()
                            clean_kwargs = _filter_supported_kwargs(Llama, kwargs)
                            try:
                                loaded_llm = Llama(**clean_kwargs)  # type: ignore[assignment]
                            except TypeError:
                                clean_kwargs.pop("flash_attn", None)
                                clean_kwargs.pop("n_ubatch", None)
                                clean_kwargs.pop("type_k", None)
                                clean_kwargs.pop("type_v", None)
                                clean_kwargs.pop("offload_kqv", None)
                                clean_kwargs.pop("no_perf", None)
                                loaded_llm = Llama(**clean_kwargs)  # type: ignore[assignment]

                            logger.info(
                                "[+] Successfully fitted %s layer(s) into GPU/system memory (flash_attn=%s).",
                                "ALL" if cand < 0 else str(cand),
                                try_flash,
                            )
                            break
                        except Exception as alloc_err:
                            logger.warning(
                                "[-] Loading failed for n_gpu_layers=%s (flash_attn=%s): %s. Reclaiming memory...",
                                "ALL" if cand < 0 else str(cand),
                                try_flash,
                                alloc_err,
                            )
                            loaded_llm = None
                            gc.collect()
                            time.sleep(0.1)

                    if loaded_llm is not None:
                        break

                if loaded_llm is None:
                    raise RuntimeError(
                        "Could not load LLM even in CPU mode (n_gpu_layers=0). Check model integrity."
                    )

                self._llm = loaded_llm
                _GLOBAL_LLM_INSTANCE = self._llm
                _GLOBAL_LLM_KEY = cache_key
                logger.info("[+] Local VL model loaded successfully and cached in memory.")
            except Exception as _e:
                logger.error("[!] Error loading model: %s", _e)
                self._load_failed = True
                raise RuntimeError(
                    "Could not load LLM. Please run 'python scripts/download_models.py --yes' and verify GPU drivers."
                ) from _e

            self._loaded = True
            return True

    def preload(self) -> bool:
        """Preloads local VL model and executes a lightweight forward pass to compile graphs."""
        if not self._ensure_loaded():
            return False

        # Base64 56x56 solid white JPEG (multiple of 28 for Qwen2-VL patch grid) to warm up vision projector & KV cache
        dummy_b64_jpg = (
            "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAIBAQEBAQIBAQECAgICAgQDAgICAgUEBAMEBgUGBgYFBgYGBwkIBgcJBwYGCAsICQ"
            "oKCgoKBggLDAsKDAkKCgr/2wBDAQICAgICAgUDAwUKBwYHCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoK"
            "CgoKCgoKCgoKCgr/wAARCAA4ADgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAw"
            "IEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdI"
            "SUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1N"
            "XW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcF"
            "BAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1"
            "RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX"
            "2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD9/KKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK"
            "KKKACiiigAooooAKKKKACiiigAooooAKKKKAP/2Q=="
        )
        try:
            payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": "Warmup",
                        "images": [dummy_b64_jpg],
                    }
                ],
                "max_tokens": 1,
                "temperature": 0.0,
            }
            # Executes under _LLM_LOCK inside call_vision_api
            self.call_vision_api(payload)
            with _LLM_LOCK:
                reset_fn = getattr(self._llm, "reset", None)
                if callable(reset_fn):
                    try:
                        reset_fn()
                    except (AttributeError, RuntimeError, OSError):
                        pass
            logger.info("[+] Local VL model inference engine warmed up.")
            return True
        except Exception as e:
            logger.debug("Backend warmup pass skipped or failed: %s", e)
            return True

    def unload(self) -> None:
        """Explicitly unloads local VL model and releases memory/VRAM."""
        global _GLOBAL_LLM_INSTANCE, _GLOBAL_LLM_KEY
        import gc

        with _LLM_LOCK:
            if hasattr(self, "_llm") and self._llm is not None:
                try:
                    del self._llm
                except Exception as e:
                    logger.debug("Error deallocating local LLM: %s", e)
                self._llm = None
            _GLOBAL_LLM_INSTANCE = None
            _GLOBAL_LLM_KEY = None
            self._loaded = False
            gc.collect()
            logger.info("[+] Local VL model unloaded from memory.")

    def _convert_messages(self, raw_messages: list[dict[str, object]]) -> list[dict[str, object]]:
        """Converts legacy/custom message formats to standard OpenAI Multimodal format for llama-cpp-python."""
        formatted: list[dict[str, object]] = []
        for msg in raw_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            images = msg.get("images", [])

            if isinstance(content, list):
                formatted.append({"role": role, "content": content})
                continue

            content_parts: list[dict[str, object]] = []
            if isinstance(content, str) and content:
                content_parts.append({"type": "text", "text": content})

            if images:
                for img in images:  # type: ignore[union-attr]
                    if isinstance(img, str):
                        img_url = img if img.startswith("data:") else f"data:image/jpeg;base64,{img}"
                        content_parts.append({"type": "image_url", "image_url": {"url": img_url}})

            if not content_parts:
                content_parts.append({"type": "text", "text": ""})

            formatted.append({"role": role, "content": content_parts})
        return formatted

    def call_vision_api(self, payload: dict[str, object]) -> str:
        if not self._ensure_loaded():
            return ""
        with _LLM_LOCK:
            try:
                if hasattr(self._llm, "reset"):
                    try:
                        self._llm.reset()  # type: ignore[union-attr]
                    except (AttributeError, RuntimeError, OSError):
                        logger.debug("LLM reset failed", exc_info=True)
                raw_msgs = payload.get("messages") or []  # type: ignore[assignment]
                messages = self._convert_messages(raw_msgs)  # type: ignore[arg-type]

                options = payload.get("options")
                options_dict = options if isinstance(options, dict) else {}

                # Check both root payload and options dictionary
                temp_val = payload.get("temperature")
                if temp_val is None:
                    temp_val = options_dict.get("temperature", 0.0)
                temperature = float(temp_val) if isinstance(temp_val, (int, float)) else 0.0

                top_p_val = payload.get("top_p")
                if top_p_val is None:
                    top_p_val = options_dict.get("top_p", 0.1)
                top_p = float(top_p_val) if isinstance(top_p_val, (int, float)) else 0.1

                repeat_val = payload.get("repeat_penalty")
                if repeat_val is None:
                    repeat_val = options_dict.get("repeat_penalty", 1.0)
                repeat_penalty = float(repeat_val) if isinstance(repeat_val, (int, float)) else 1.0

                raw_max = payload.get("max_tokens") or options_dict.get("max_tokens") or getattr(self.config, "max_tokens", 2048) or 2048
                try:
                    max_tok = int(raw_max)  # type: ignore[arg-type]
                except (ValueError, TypeError):
                    max_tok = 2048

                grammar_str = payload.get("grammar")
                grammar_obj = None
                if grammar_str and isinstance(grammar_str, str):
                    try:
                        from llama_cpp import LlamaGrammar  # type: ignore[import-untyped]

                        grammar_obj = LlamaGrammar.from_string(grammar_str, verbose=False)
                    except Exception as e:
                        logger.warning("[-] Failed to compile LlamaGrammar (%s). Falling back unconstrained.", e)

                json_schema = payload.get("json_schema")
                kwargs: dict[str, object] = {
                    "messages": messages,
                    "temperature": temperature,
                    "top_p": top_p,
                    "repeat_penalty": repeat_penalty,
                    "max_tokens": max_tok,
                }
                if grammar_obj is not None:
                    kwargs["grammar"] = grammar_obj
                elif json_schema and isinstance(json_schema, dict):
                    kwargs["response_format"] = {
                        "type": "json_object",
                        "schema": json_schema,
                    }

                resp = self._llm.create_chat_completion(**kwargs)  # type: ignore[attr-defined]

                # Handle both streaming and non-streaming responses
                choices = resp.get("choices") if isinstance(resp, dict) else getattr(resp, "choices", None)
                if choices is None:
                    return ""

                first_choice = choices[0] if choices else None
                content: Any = ""
                if isinstance(first_choice, dict):
                    message = first_choice.get("message", {})
                    if isinstance(message, dict):
                        content = message.get("content", "")
                else:
                    message = getattr(first_choice, "message", None)
                    if isinstance(message, dict):
                        content = message.get("content", "")
                    else:
                        content = getattr(message, "content", "") if message is not None else ""

                result = str(content).strip() if isinstance(content, (str, list)) else ""
                return result
            except (AttributeError, RuntimeError, ValueError, TypeError) as e:
                logger.warning("[-] LLM call failed: %s", e)
                return ""


# ---- Server Backend with Instructor/Pydantic (optional) ----


class _ServerBackend(LLMBackend):
    """OpenAI-compatible API + Instructor for structured Pydantic extraction."""

    def __init__(self, config: object) -> None:
        self.config = config
        try:
            import instructor  # type: ignore[import-untyped]
            from openai import OpenAI  # type: ignore[import-untyped]

            self._client = instructor.from_openai(  # type: ignore[assignment]
                OpenAI(
                    base_url=config.server_url,  # type: ignore[attr-defined]
                    api_key=getattr(config, "server_api_key", "not-needed"),
                ),
                mode=instructor.Mode.JSON,
            )
        except (ImportError, AttributeError, RuntimeError, OSError, ValueError) as e:
            logger.error("[!] Instructor setup failed (openai/instructor not installed?): %s", e)
            self._client = None

    def call_vision_api(self, payload: dict[str, object]) -> str:
        if self._client is None:
            return ""
        msgs = []
        for m in payload.get("messages") or []:  # type: ignore[union-attr]
            role = m.get("role", "user")  # type: ignore[union-attr]
            content = m.get("content", "")  # type: ignore[union-attr]
            images = m.get("images") or []  # type: ignore[union-attr]

            content_parts: list[dict[str, Any]] = []
            if isinstance(content, str) and content:
                content_parts.append({"type": "text", "text": content})
            elif isinstance(content, list):
                content_parts.extend(content)

            if images:
                for img in images:
                    if isinstance(img, str):
                        img_url = img if img.startswith("data:") else f"data:image/jpeg;base64,{img}"
                        content_parts.append({"type": "image_url", "image_url": {"url": img_url}})

            if not content_parts:
                content_parts.append({"type": "text", "text": ""})

            msgs.append({"role": role, "content": content_parts})

        options = payload.get("options")
        options_dict = options if isinstance(options, dict) else {}
        temp_val = payload.get("temperature")
        if temp_val is None:
            temp_val = options_dict.get("temperature", 0.0)
        temperature = float(temp_val) if isinstance(temp_val, (int, float)) else 0.0

        raw_max = payload.get("max_tokens") or options_dict.get("max_tokens") or getattr(self.config, "max_tokens", 2048) or 2048
        try:
            max_tok = int(raw_max)  # type: ignore[arg-type]
        except (ValueError, TypeError):
            max_tok = 2048

        grammar_str = payload.get("grammar")
        extra_kwargs: dict[str, Any] = {}
        if grammar_str and isinstance(grammar_str, str):
            extra_kwargs["extra_body"] = {"grammar": grammar_str}

        try:
            resp = self._client.chat.completions.create(  # type: ignore[attr-defined]
                model=getattr(self.config, "server_model", "local-model"),
                messages=msgs,
                temperature=temperature,
                max_tokens=max_tok,
                **extra_kwargs,
            )
            return (resp.choices[0].message.content or "").strip()  # type: ignore[union-attr, attr-defined]
        except (AttributeError, RuntimeError, ValueError, TypeError, Exception) as e:
            if extra_kwargs and ("grammar" in str(e).lower() or "400" in str(e)):
                logger.warning("[-] Remote server rejected GBNF grammar (%s). Retrying unconstrained...", e)
                try:
                    resp = self._client.chat.completions.create(  # type: ignore[attr-defined]
                        model=getattr(self.config, "server_model", "local-model"),
                        messages=msgs,
                        temperature=temperature,
                        max_tokens=max_tok,
                    )
                    return (resp.choices[0].message.content or "").strip()  # type: ignore[union-attr, attr-defined]
                except Exception as retry_err:
                    logger.warning("[-] Server unconstrained retry call failed: %s", retry_err)
                    return ""
            logger.warning("[-] Server call failed: %s", e)
            return ""


def get_backend(config: object) -> LLMBackend:
    """Factory function: selects backend based on config.llm_backend."""
    backend = getattr(config, "llm_backend", "llama_cpp") or "llama_cpp"
    if backend == "server":
        return _ServerBackend(config)
    # Default: llama.cpp directly
    return _LlamaCppBackend(config)


__all__ = ["LLMBackend", "get_backend"]
