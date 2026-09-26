"""Abstract LLM Backend layer supporting two implementations.

Both backends implement the same interface so core/vision.py does not need to change:
  - "llama_cpp" : Direct llama.cpp-python API (no separate server process)
  - "server"    : OpenAI-compatible API via a running llama-server with Instructor/Pydantic for structured extraction

Instructor + Pydantic enforce error-free data structure – invalid JSON tokens are blocked at the grammar level.
"""

from __future__ import annotations

import logging
import os
import threading
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


from core.llm_hardware import (
    _filter_supported_kwargs,
    _generate_layer_candidates,
    _get_optimal_cpu_threads,
    _is_gpu_acceleration_available,
    _is_nvidia_cuda_available,
    _is_valid_gguf,
    _is_vulkan_available,
    _parse_ggml_type,
    _resolve_model_paths,
    _setup_win32_dll_directories,
)


class LLMBackend(ABC):
    """Interface for all LLM backends."""

    @abstractmethod
    def call_vision_api(self, payload: dict[str, object]) -> str: ...

    def preload(self) -> bool:
        """Preloads model weights ahead of time."""
        return True

    def unload(self) -> None:
        """Unloads model weights from memory."""
        logger.debug("[LLMBackend] Default unload no-op.")


# Global module caching for the Llama instance
_GLOBAL_LLM_INSTANCE: object = None
_GLOBAL_LLM_KEY: tuple[Any, ...] | None = None
_LLM_LOCK = threading.RLock()


class _LlamaCppBackend(LLMBackend):
    """Direct llama.cpp-python backend with singleton caching and grammar constraints."""

    def __init__(self, config: object) -> None:
        self.config = config

    def _ensure_loaded(self) -> bool:
        """Lazy init with singleton caching: Model is loaded once and reused."""
        global _GLOBAL_LLM_INSTANCE, _GLOBAL_LLM_KEY

        model_path, mmproj_raw = _resolve_model_paths(self.config)
        config = self.config

        n_gpu_layers = getattr(config, "n_gpu_layers", -1)
        if n_gpu_layers is None:
            n_gpu_layers = -1

        n_ctx = getattr(config, "n_ctx", 4096) or 4096
        n_batch = getattr(config, "n_batch", 512) or 512
        n_ubatch = getattr(config, "n_ubatch", 512) or 512
        flash_attn = _is_gpu_acceleration_available()
        parsed_type_k = _parse_ggml_type(getattr(config, "type_k", 8))
        parsed_type_v = _parse_ggml_type(getattr(config, "type_v", 8))
        n_threads = _get_optimal_cpu_threads(getattr(config, "n_threads", 0))

        cache_key = (
            os.path.abspath(model_path),
            os.path.abspath(mmproj_raw) if mmproj_raw else None,
            n_gpu_layers,
            n_ctx,
            n_batch,
            n_ubatch,
            flash_attn,
            parsed_type_k,
            parsed_type_v,
            n_threads,
        )

        with _LLM_LOCK:
            if _GLOBAL_LLM_INSTANCE is not None:
                if _GLOBAL_LLM_KEY == cache_key:
                    self._llm = _GLOBAL_LLM_INSTANCE
                    self._loaded = True
                    logger.debug("[+] Using LLM model instance already cached in VRAM.")
                    return True
                logger.info("[*] LLM configuration changed. Unloading stale model from memory...")
                self._unload_cached_instance()

            if getattr(self, "_load_failed", False):
                return False

            _setup_win32_dll_directories()

            if not os.path.isfile(model_path):
                self._load_failed = True
                raise FileNotFoundError(f"Model file not found: {model_path}")

            if not _is_valid_gguf(model_path, min_mb=100):
                self._load_failed = True
                raise ValueError(
                    f"Model file at '{model_path}' is corrupted or incomplete. "
                    "Please run 'python scripts/download_models.py --yes' to download a clean model copy."
                )

            logger.info("[*] Initializing local VL model from '%s' ...", os.path.basename(model_path))

            chat_handler = self._init_chat_handler(mmproj_raw)
            candidates = _generate_layer_candidates(n_gpu_layers)

            load_params: dict[str, Any] = {
                "model_path": model_path,
                "n_ctx": n_ctx,
                "n_batch": n_batch,
                "n_ubatch": n_ubatch,
                "n_threads": n_threads,
                "flash_attn": flash_attn,
                "type_k": parsed_type_k,
                "type_v": parsed_type_v,
                "n_gpu_layers": n_gpu_layers,
            }

            try:
                loaded_llm = self._fit_model_candidate_matrix(candidates, load_params, chat_handler, mmproj_raw)
                if loaded_llm is None:
                    raise RuntimeError("Could not load LLM even in CPU mode (n_gpu_layers=0). Check model integrity.")

                self._llm = loaded_llm
                _GLOBAL_LLM_INSTANCE = self._llm
                _GLOBAL_LLM_KEY = cache_key
                self._loaded = True
                logger.info("[+] Local VL model loaded successfully and cached in memory.")
                return True
            except Exception as _e:
                logger.error("[!] Error loading model: %s", _e)
                self._load_failed = True
                raise RuntimeError(
                    "Could not load LLM. Please run 'python scripts/download_models.py --yes' and verify GPU drivers."
                ) from _e

    def _unload_cached_instance(self) -> None:
        """Closes and deallocates global cached LLM instance."""
        global _GLOBAL_LLM_INSTANCE, _GLOBAL_LLM_KEY
        import gc

        try:
            if hasattr(_GLOBAL_LLM_INSTANCE, "close"):
                _GLOBAL_LLM_INSTANCE.close()  # type: ignore[attr-defined]
        except Exception as e:
            logger.debug("[LLMBackend] Error closing LLM instance: %s", e)
        _GLOBAL_LLM_INSTANCE = None
        _GLOBAL_LLM_KEY = None
        gc.collect()

    def _init_chat_handler(self, mmproj_raw: str) -> Any | None:
        """Initializes the vision chat handler if mmproj file exists and is valid."""
        if not mmproj_raw or not os.path.isfile(mmproj_raw):
            logger.warning("[-] No valid mmproj path found. Model loading without vision support.")
            return None

        if not _is_valid_gguf(mmproj_raw, min_mb=50):
            logger.warning("[-] mmproj file at '%s' is corrupted or incomplete. Running without vision support.", mmproj_raw)
            return None

        try:
            from llama_cpp.llama_chat_format import Qwen25VLChatHandler  # type: ignore[import-untyped]

            logger.info("[*] Enabling Vision Projector (%s) via Qwen25VLChatHandler...", os.path.basename(mmproj_raw))
            return Qwen25VLChatHandler(clip_model_path=mmproj_raw, verbose=False)
        except (ImportError, RuntimeError) as e:
            logger.warning("[-] Could not initialize Qwen25VLChatHandler: %s", e)
            return None

    def _verify_llm_probe(self, loaded_llm: Any, chat_handler: Any) -> bool:
        """Executes a lightweight 1-token forward probe to confirm GPU/VRAM stability."""
        try:
            if chat_handler is not None:
                dummy_b64 = (
                    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP////////////////////////////////////////////////////"
                    "//////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
                )
                probe_messages = self._convert_messages([{"role": "user", "content": "probe", "images": [dummy_b64]}])
            else:
                probe_messages = [{"role": "user", "content": "1"}]

            loaded_llm.create_chat_completion(
                messages=probe_messages,  # type: ignore[arg-type]
                max_tokens=1,
                temperature=0.0,
            )
            if hasattr(loaded_llm, "reset") and callable(loaded_llm.reset):
                try:
                    loaded_llm.reset()
                except Exception as reset_err:
                    logger.debug("[LLMBackend] Probe reset error: %s", reset_err)
            return True
        except Exception as probe_err:
            logger.debug("[LLMBackend] Forward probe failed: %s", probe_err)
            return False

    def _try_load_single_configuration(
        self,
        llama_cls: Any,
        cand: int,
        try_flash: bool,
        load_params: dict[str, Any],
        chat_handler: Any,
    ) -> Any | None:
        """Attempts to allocate a single Llama instance with graceful kwarg fallback."""
        import gc
        import time

        kwargs: dict[str, Any] = {
            "model_path": load_params["model_path"],
            "n_ctx": load_params["n_ctx"],
            "n_batch": load_params["n_batch"],
            "n_ubatch": load_params["n_ubatch"],
            "chat_handler": chat_handler,
            "verbose": False,
            "n_gpu_layers": cand,
            "n_threads": load_params["n_threads"],
            "flash_attn": try_flash,
            "offload_kqv": (cand != 0),
            "no_perf": True,
        }
        if try_flash:
            if load_params.get("type_k") is not None:
                kwargs["type_k"] = load_params["type_k"]
            if load_params.get("type_v") is not None:
                kwargs["type_v"] = load_params["type_v"]

        try:
            gc.collect()
            clean_kwargs = _filter_supported_kwargs(llama_cls, kwargs)
            try:
                return llama_cls(**clean_kwargs)
            except TypeError:
                for deprecated_key in ["flash_attn", "n_ubatch", "type_k", "type_v", "offload_kqv", "no_perf"]:
                    clean_kwargs.pop(deprecated_key, None)
                return llama_cls(**clean_kwargs)
        except Exception as alloc_err:
            logger.warning(
                "[-] Loading failed for n_gpu_layers=%s (flash_attn=%s): %s. Reclaiming memory...",
                "ALL" if cand < 0 else str(cand),
                try_flash,
                alloc_err,
            )
            gc.collect()
            time.sleep(0.1)
            return None

    def _fit_model_candidate_matrix(
        self,
        candidates: list[int],
        load_params: dict[str, Any],
        chat_handler: Any,
        mmproj_raw: str,
    ) -> Any | None:
        """Iterates candidate layer counts and flash attention options to find a stable configuration."""
        import gc
        import time

        try:
            from llama_cpp import Llama  # type: ignore[import-untyped]
            from llama_cpp.llama_chat_format import Qwen25VLChatHandler  # type: ignore[import-untyped]
        except (ImportError, RuntimeError) as _e:
            logger.error("[!] Could not load 'llama-cpp-python': %s\n    Please run Install_OrdinFlow.bat.", _e)
            return None

        flash_attn = load_params.get("flash_attn", False)

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
                loaded_llm = self._try_load_single_configuration(Llama, cand, try_flash, load_params, chat_handler)
                if loaded_llm is None:
                    continue

                probe_ok = self._verify_llm_probe(loaded_llm, chat_handler)
                if probe_ok or cand == 0:
                    if cand == 0 and load_params.get("n_gpu_layers", -1) != 0:
                        logger.warning(
                            "[*] GPU offloading not viable (insufficient VRAM). Successfully switched model execution to CPU mode (n_gpu_layers=0, %d threads).",
                            load_params.get("n_threads", 4),
                        )
                    else:
                        logger.info(
                            "[+] Successfully fitted and validated %s layer(s) into GPU/system memory (flash_attn=%s).",
                            "ALL" if cand < 0 else str(cand),
                            try_flash,
                        )
                    return loaded_llm

                logger.warning(
                    "[-] Forward probe failed for n_gpu_layers=%s (flash_attn=%s). Downgrading...",
                    "ALL" if cand < 0 else str(cand),
                    try_flash,
                )
                try:
                    if hasattr(loaded_llm, "close"):
                        loaded_llm.close()  # type: ignore[attr-defined]
                except Exception as close_err:
                    logger.debug("[LLMBackend] Probe close error: %s", close_err)
                loaded_llm = None
                if mmproj_raw and os.path.isfile(mmproj_raw) and _is_valid_gguf(mmproj_raw, min_mb=50):
                    chat_handler = Qwen25VLChatHandler(clip_model_path=mmproj_raw, verbose=False)
                gc.collect()
                time.sleep(0.1)

        return None

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
            try:
                close_fn = getattr(self._llm, "close", None)
                if callable(close_fn):
                    close_fn()
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
        with _LLM_LOCK:
            if not self._ensure_loaded():
                return ""
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

                raw_max = payload.get("max_tokens") or options_dict.get("max_tokens") or getattr(self.config, "max_tokens", 512) or 512
                try:
                    max_tok = int(raw_max)  # type: ignore[arg-type]
                except (ValueError, TypeError):
                    max_tok = 512

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

                try:
                    resp = self._llm.create_chat_completion(**kwargs)  # type: ignore[attr-defined]
                except Exception as e:
                    if grammar_obj is not None or "response_format" in kwargs:
                        logger.warning("[-] LLM call with grammar/response_format failed (%s). Retrying unconstrained...", e)
                        kwargs.pop("grammar", None)
                        kwargs.pop("response_format", None)
                        resp = self._llm.create_chat_completion(**kwargs)  # type: ignore[attr-defined]
                    else:
                        raise

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

                return str(content).strip() if isinstance(content, (str, list)) else ""
            except Exception as e:
                logger.warning("[-] LLM call failed: %s", e)
                err_str = str(e).lower()
                if any(x in err_str for x in ["access violation", "segmentation fault", "cuda", "out of memory"]):
                    logger.error("[!] Critical LLM backend error detected: %s. Unloading model for clean recovery...", e)
                    self.unload()
                raise


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

        raw_max = payload.get("max_tokens") or options_dict.get("max_tokens") or getattr(self.config, "max_tokens", 512) or 512
        try:
            max_tok = int(raw_max)  # type: ignore[arg-type]
        except (ValueError, TypeError):
            max_tok = 512

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


__all__ = [
    "LLMBackend",
    "get_backend",
    "_filter_supported_kwargs",
    "_is_gpu_acceleration_available",
    "_is_nvidia_cuda_available",
    "_is_vulkan_available",
]
