"""Abstract LLM Backend layer supporting two implementations.

Both backends implement the same interface so core/vision.py does not need to change:
  - "llama_cpp" : Direct llama.cpp-python API (no separate server process)
  - "server"    : OpenAI-compatible API via a running llama-server with Instructor/Pydantic for structured extraction

Instructor + Pydantic enforce error-free data structure – invalid JSON tokens are blocked at the grammar level.
"""

from __future__ import annotations

import json
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
_LLM_LOCK = threading.Lock()


class _LlamaCppBackend(LLMBackend):
    """Direct llama.cpp-python backend with singleton caching and grammar constraints."""

    def __init__(self, config: object) -> None:
        self.config = config

    def _ensure_loaded(self) -> bool:
        """Lazy init with singleton caching: Model is loaded once and reused."""
        global _GLOBAL_LLM_INSTANCE, _GLOBAL_LLM_KEY

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

        n_ctx = getattr(config, "n_ctx", 16384) or 16384
        n_batch = getattr(config, "n_batch", 2048) or 2048
        n_ubatch = getattr(config, "n_ubatch", 512) or 512
        flash_attn = bool(getattr(config, "flash_attn", True))

        n_threads = getattr(config, "n_threads", 0)
        if not n_threads or n_threads <= 0:
            n_threads = max(4, (os.cpu_count() or 4) - 2)

        cache_key = (model_path, mmproj_raw, n_gpu_layers, n_ctx, n_batch, n_ubatch, flash_attn)

        # Check if global instance is already loaded
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
                raise FileNotFoundError(f"Model not found: {model_path}")

            logger.info("[*] Loading local VL model from '%s' ...", os.path.basename(model_path))
            logger.info(
                "[*] GPU acceleration: %s Layer(s) on GPU, n_batch=%d, n_ubatch=%d, flash_attn=%s",
                "ALL" if n_gpu_layers < 0 else str(n_gpu_layers),
                n_batch,
                n_ubatch,
                flash_attn,
            )

            chat_handler = None
            if mmproj_raw and os.path.isfile(mmproj_raw):
                logger.info(
                    "[*] Enabling Vision Projector (%s) via Qwen25VLChatHandler...",
                    os.path.basename(mmproj_raw),
                )
                chat_handler = Qwen25VLChatHandler(clip_model_path=mmproj_raw, verbose=False)
            else:
                logger.warning("[-] No valid mmproj path found. Model loading without vision support.")

            kwargs: dict[str, Any] = {
                "model_path": model_path,
                "n_ctx": n_ctx,
                "n_batch": n_batch,
                "n_ubatch": n_ubatch,
                "chat_handler": chat_handler,
                "verbose": False,
                "n_gpu_layers": n_gpu_layers,
                "n_threads": n_threads,
                "flash_attn": flash_attn,
            }
            try:
                self._llm = Llama(**kwargs)  # type: ignore[assignment]
            except TypeError:
                # Fallback if older llama-cpp wheel doesn't support flash_attn / n_ubatch
                kwargs.pop("flash_attn", None)
                kwargs.pop("n_ubatch", None)
                self._llm = Llama(**kwargs)  # type: ignore[assignment]

            _GLOBAL_LLM_INSTANCE = self._llm
            _GLOBAL_LLM_KEY = cache_key
            logger.info("[+] Local VL model loaded successfully and cached in memory.")
        except Exception as _e:
            logger.error("[!] Error loading model: %s", _e)
            raise RuntimeError(
                "Could not load LLM. Please run 'Install_OrdinFlow.bat' and enable GPU acceleration (Vulkan/CUDA)."
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

    def call_vision_api(self, payload: dict[str, object], force_json: bool = False) -> str:
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
                elif force_json:
                    kwargs["response_format"] = {"type": "json_object"}

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

    def call_vision_api_json(self, payload: dict[str, object]) -> dict[str, object] | None:
        raw = self.call_vision_api(payload, force_json=True)
        if not raw:
            return None
        try:
            return json.loads(raw)  # type: ignore[arg-type]
        except json.JSONDecodeError as e:
            logger.warning(
                "[-] JSONDecodeError parsing Vision response: %s. Raw response: %r",
                e,
                raw,
            )
            return None


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
            # Convert to OpenAI format (list of dicts if str)
            if isinstance(content, str):
                msgs.append({"role": role, "content": [{"type": "text", "text": content}]})
            elif isinstance(content, list):
                msgs.append({"role": role, "content": content})
        try:
            resp = self._client.chat.completions.create(  # type: ignore[attr-defined]
                model="local-model",
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
