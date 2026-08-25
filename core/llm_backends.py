"""Abstract LLM Backend layer supporting two implementations.

Both backends implement the same interface so core/vision.py does not need to change:
  - "llama_cpp" : Direct llama.cpp-python API (no separate server process)
  - "server"    : OpenAI-compatible API via a running llama-server with Instructor/Pydantic for structured extraction

Instructor + Pydantic enforce error-free data structure – invalid JSON tokens are blocked at the grammar level.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


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
        flash_attn = bool(getattr(config, "flash_attn", True))

        n_threads = getattr(config, "n_threads", 0)
        if not n_threads or n_threads <= 0:
            n_threads = max(4, (os.cpu_count() or 4) - 2)

        cache_key = (model_path, mmproj_raw, n_gpu_layers, n_ctx, n_batch, n_ubatch, flash_attn)

        with _LLM_LOCK:
            # Check if global instance is already loaded (Double-checked locking)
            if _GLOBAL_LLM_INSTANCE is not None and _GLOBAL_LLM_KEY == cache_key:
                self._llm = _GLOBAL_LLM_INSTANCE
                self._loaded = True
                logger.debug("[+] Using LLM model instance already cached in VRAM.")
                return True

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
                        }
                        try:
                            gc.collect()
                            try:
                                loaded_llm = Llama(**kwargs)  # type: ignore[assignment]
                            except TypeError:
                                kwargs.pop("flash_attn", None)
                                kwargs.pop("n_ubatch", None)
                                loaded_llm = Llama(**kwargs)  # type: ignore[assignment]

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
        """Preloads local VL model into memory ahead of time."""
        return self._ensure_loaded()

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

                max_tok = getattr(self.config, "max_tokens", 2048) or 2048
                json_schema = payload.get("json_schema")
                options = payload.get("options")
                options_dict = options if isinstance(options, dict) else {}
                kwargs: dict[str, object] = {
                    "messages": messages,
                    "temperature": options_dict.get("temperature", 0.0),
                    "top_p": options_dict.get("top_p", 0.1),
                    "max_tokens": max_tok,
                }
                if json_schema and isinstance(json_schema, dict):
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
        try:
            resp = self._client.chat.completions.create(  # type: ignore[attr-defined]
                model=getattr(self.config, "server_model", "local-model"),
                messages=msgs,
                temperature=(payload.get("options") or {}).get("temperature", 0.0),  # type: ignore[union-attr]
            )
            return (resp.choices[0].message.content or "").strip()  # type: ignore[union-attr, attr-defined]
        except (AttributeError, RuntimeError, ValueError, TypeError) as e:
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
