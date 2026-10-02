"""Unit tests for core/llm_backends.py: Message formatting, GPU layer ladders, grammar fallbacks, and backend lifecycle."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from core.llm_backends import _LlamaCppBackend, _ServerBackend, get_backend


def test_get_backend_factory():
    """Verifies that get_backend selects the appropriate backend according to config."""

    class ConfigServer:
        llm_backend = "server"
        server_url = "http://localhost:8080/v1"

    class ConfigLlamaCpp:
        llm_backend = "llama_cpp"

    class ConfigDefault:
        llm_backend = None

    with patch("core.llm_backends._ServerBackend.__init__", return_value=None):
        b_server = get_backend(ConfigServer())
        assert isinstance(b_server, _ServerBackend)

    b_llamacpp = get_backend(ConfigLlamaCpp())
    assert isinstance(b_llamacpp, _LlamaCppBackend)

    b_default = get_backend(ConfigDefault())
    assert isinstance(b_default, _LlamaCppBackend)


def test_convert_messages_text_and_data_uris():
    """Verifies OpenAI multimodal message formatting with plain text, data URIs, and raw base64."""
    backend = _LlamaCppBackend(config=object())
    raw = [
        {"role": "user", "content": "Hello world", "images": []},
        {"role": "user", "content": "Analyze", "images": ["abc123rawb64"]},
        {"role": "user", "content": "Analyze prefixed", "images": ["data:image/png;base64,xyz789"]},
        {"role": "user", "content": [{"type": "text", "text": "preformatted"}]},
        {"role": "system", "content": "", "images": []},
    ]
    formatted = backend._convert_messages(raw)
    assert len(formatted) == 5

    # 1. Plain text converted to content part
    assert formatted[0]["role"] == "user"
    assert formatted[0]["content"] == [{"type": "text", "text": "Hello world"}]

    # 2. Raw base64 converted to data:image/jpeg;base64, URI
    assert formatted[1]["content"][0] == {"type": "text", "text": "Analyze"}
    assert formatted[1]["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/jpeg;base64,abc123rawb64"},
    }

    # 3. Already prefixed data URI preserved as-is
    assert formatted[2]["content"][1]["image_url"]["url"] == "data:image/png;base64,xyz789"

    # 4. List content passed through directly
    assert formatted[3]["content"] == [{"type": "text", "text": "preformatted"}]

    # 5. Empty content fallback
    assert formatted[4]["content"] == [{"type": "text", "text": ""}]


def test_fit_model_candidate_matrix_gpu_fallback():
    """Verifies candidate layer ladder: fallback on OOM to lower layer count."""
    backend = _LlamaCppBackend(config=object())
    mock_llama_mod = MagicMock()
    mock_chat_mod = MagicMock()

    instance_success = MagicMock()
    instance_success.create_chat_completion.return_value = {"choices": [{"message": {"content": "ok"}}]}

    def mock_try_load(llama_cls, cand, try_flash, load_params, chat_handler):
        if cand == -1:
            return None  # Simulate OOM on ALL layers
        return instance_success

    with (
        patch.dict(sys.modules, {"llama_cpp": mock_llama_mod, "llama_cpp.llama_chat_format": mock_chat_mod}),
        patch.object(backend, "_try_load_single_configuration", side_effect=mock_try_load),
        patch.object(backend, "_verify_llm_probe", return_value=True),
    ):
        result = backend._fit_model_candidate_matrix(
            candidates=[-1, 20, 10, 0],
            load_params={"flash_attn": False},
            chat_handler=None,
            mmproj_raw="",
        )
        assert result is instance_success


def test_fit_model_candidate_matrix_probe_failure_downgrades_to_cpu():
    """Verifies that forward probe failures deallocate GPU instance and switch to CPU mode (cand=0)."""
    backend = _LlamaCppBackend(config=object())
    mock_llama_mod = MagicMock()
    mock_chat_mod = MagicMock()

    mock_gpu_instance = MagicMock()
    mock_cpu_instance = MagicMock()

    def mock_try_load(llama_cls, cand, try_flash, load_params, chat_handler):
        if cand > 0 or cand == -1:
            return mock_gpu_instance
        return mock_cpu_instance

    def mock_verify_probe(loaded_llm, chat_handler):
        # GPU probe fails, CPU probe succeeds
        return loaded_llm is mock_cpu_instance

    with (
        patch.dict(sys.modules, {"llama_cpp": mock_llama_mod, "llama_cpp.llama_chat_format": mock_chat_mod}),
        patch.object(backend, "_try_load_single_configuration", side_effect=mock_try_load),
        patch.object(backend, "_verify_llm_probe", side_effect=mock_verify_probe),
    ):
        result = backend._fit_model_candidate_matrix(
            candidates=[-1, 20, 0],
            load_params={"flash_attn": False, "n_threads": 4},
            chat_handler=None,
            mmproj_raw="",
        )
        assert result is mock_cpu_instance
        mock_gpu_instance.close.assert_called()


def test_call_vision_api_grammar_fallback_on_failure():
    """Verifies that grammar/schema compilation or token rejection triggers unconstrained retry."""
    backend = _LlamaCppBackend(config=object())
    backend._ensure_loaded = MagicMock(return_value=True)
    mock_llm = MagicMock()

    # First call with grammar raises Exception, second call unconstrained succeeds
    mock_llm.create_chat_completion.side_effect = [
        RuntimeError("Grammar rejected token"),
        {"choices": [{"message": {"content": "{\"status\": \"ok\"}"}}]},
    ]
    backend._llm = mock_llm

    payload = {
        "messages": [{"role": "user", "content": "extract"}],
        "grammar": "root ::= [0-9]+",
    }

    mock_grammar_cls = MagicMock()
    mock_grammar_cls.from_string.return_value = MagicMock()
    mock_llama_mod = MagicMock(LlamaGrammar=mock_grammar_cls)

    with patch.dict(sys.modules, {"llama_cpp": mock_llama_mod}):
        res = backend.call_vision_api(payload)
        assert res == '{"status": "ok"}'
        assert mock_llm.create_chat_completion.call_count == 2
        second_call_kwargs = mock_llm.create_chat_completion.call_args_list[1][1]
        assert "grammar" not in second_call_kwargs


def test_call_vision_api_critical_error_triggers_unload():
    """Verifies that critical fault strings (CUDA, access violation, segfault) trigger backend unload."""
    backend = _LlamaCppBackend(config=object())
    backend._ensure_loaded = MagicMock(return_value=True)
    backend.unload = MagicMock()
    mock_llm = MagicMock()
    mock_llm.create_chat_completion.side_effect = RuntimeError("CUDA driver out of memory error")
    backend._llm = mock_llm

    payload = {"messages": [{"role": "user", "content": "query"}]}

    with pytest.raises(RuntimeError, match="CUDA"):
        backend.call_vision_api(payload)

    backend.unload.assert_called_once()


def test_server_backend_client_and_grammar_fallback():
    """Verifies _ServerBackend handles remote server calls and falls back on grammar rejection."""

    class DummyConfig:
        server_url = "http://localhost:8080/v1"
        server_api_key = "test"
        server_model = "test-model"

    backend = _ServerBackend.__new__(_ServerBackend)
    backend.config = DummyConfig()
    mock_client = MagicMock()

    resp_ok = MagicMock()
    resp_ok.choices = [MagicMock(message=MagicMock(content='{"extracted": true}'))]
    mock_client.chat.completions.create.side_effect = [
        RuntimeError("400 Bad Request: grammar not supported"),
        resp_ok,
    ]
    backend._client = mock_client

    payload = {
        "messages": [{"role": "user", "content": "Extract data"}],
        "grammar": "root ::= .*",
    }
    result = backend.call_vision_api(payload)
    assert result == '{"extracted": true}'
    assert mock_client.chat.completions.create.call_count == 2


def test_server_backend_none_client_returns_empty():
    """Verifies _ServerBackend returns empty string when client is None."""
    backend = _ServerBackend.__new__(_ServerBackend)
    backend.config = object()
    backend._client = None
    assert backend.call_vision_api({"messages": []}) == ""
