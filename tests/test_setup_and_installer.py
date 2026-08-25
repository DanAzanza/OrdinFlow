"""Tests for OrdinFlow environment setup orchestrator and model downloader."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import scripts.download_models as dm
import scripts.setup_environment as se
from core.llm_backends import _is_valid_gguf
from main import _bootstrap_venv


def test_check_python_compatibility_valid(monkeypatch):
    monkeypatch.setattr(sys, "maxsize", 2**63 - 1)  # 64-bit
    monkeypatch.setattr(sys, "version_info", (3, 11, 5, "final", 0))
    assert se.check_python_compatibility() is True


def test_check_python_compatibility_32bit(monkeypatch):
    monkeypatch.setattr(sys, "maxsize", 2**31 - 1)  # 32-bit
    assert se.check_python_compatibility() is False


def test_check_python_compatibility_old_python(monkeypatch):
    monkeypatch.setattr(sys, "maxsize", 2**63 - 1)
    monkeypatch.setattr(sys, "version_info", (3, 9, 0, "final", 0))
    assert se.check_python_compatibility() is False


def test_detect_gpu_backend_nvidia(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    with patch("os.path.exists", return_value=True), patch("ctypes.windll.LoadLibrary", return_value=MagicMock()):
        assert se.detect_gpu_backend() == "cu124"


def test_detect_gpu_backend_cpu_fallback(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert se.detect_gpu_backend() == "cpu"


def test_install_llama_cpp_fallback_to_cpu():
    with patch("scripts.setup_environment.run_pip") as mock_pip:
        # First call (e.g. cu124) fails, second call (cpu) succeeds
        mock_pip.side_effect = [False, True]
        res = se.install_llama_cpp("cu124")
        assert res is True
        assert mock_pip.call_count == 2


def test_resolve_download_url():
    hf_blob = "https://huggingface.co/unsloth/Qwen3-VL-8B-Instruct-GGUF/blob/main/model.gguf"
    resolved = dm.resolve_download_url(hf_blob)
    assert resolved == "https://huggingface.co/unsloth/Qwen3-VL-8B-Instruct-GGUF/resolve/main/model.gguf"


def test_validate_gguf_file_valid(tmp_path: Path):
    model_file = tmp_path / "valid_model.gguf"
    # Write GGUF magic + padding to 20MB
    content = b"GGUF" + b"\x00" * (20 * 1024 * 1024)
    model_file.write_bytes(content)

    assert dm.validate_gguf_file(model_file, expected_min_bytes=10 * 1024 * 1024) is True
    assert _is_valid_gguf(str(model_file), min_mb=10) is True


def test_validate_gguf_file_corrupt_magic(tmp_path: Path):
    model_file = tmp_path / "corrupt_magic.gguf"
    content = b"<!DO" + b"\x00" * (20 * 1024 * 1024)  # HTML stub
    model_file.write_bytes(content)

    assert dm.validate_gguf_file(model_file, expected_min_bytes=10 * 1024 * 1024) is False
    assert _is_valid_gguf(str(model_file), min_mb=10) is False


def test_validate_gguf_file_too_small(tmp_path: Path):
    model_file = tmp_path / "too_small.gguf"
    model_file.write_bytes(b"GGUF" + b"\x00" * 1000)  # Only ~1 KB

    assert dm.validate_gguf_file(model_file, expected_min_bytes=10 * 1024 * 1024) is False
    assert _is_valid_gguf(str(model_file), min_mb=10) is False


def test_validate_gguf_file_nonexistent(tmp_path: Path):
    missing_file = tmp_path / "nonexistent.gguf"
    assert dm.validate_gguf_file(missing_file) is False
    assert _is_valid_gguf(str(missing_file)) is False


def test_download_file_atomic_success(tmp_path: Path):
    dest = tmp_path / "custom_model.gguf"
    # Create fake GGUF payload exceeding 10MB default floor
    fake_content = b"GGUF" + b"\x00" * (12 * 1024 * 1024)

    mock_response = MagicMock()
    mock_response.headers = {"Content-Length": str(len(fake_content))}
    mock_response.read.side_effect = [fake_content, b""]
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_response):
        success = dm.download_file_atomic("https://example.com/custom_model.gguf", dest)
        assert success is True
        assert dest.exists()
        assert dest.read_bytes() == fake_content
        # Temporary file should not exist
        assert not dest.with_name("custom_model.gguf.tmp").exists()


def test_download_file_atomic_failure_cleans_up(tmp_path: Path):
    dest = tmp_path / "failed_model.gguf"

    mock_response = MagicMock()
    mock_response.headers = {"Content-Length": "100"}
    # Return fewer bytes than Content-Length to trigger failure
    mock_response.read.side_effect = [b"short", b""]
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_response):
        success = dm.download_file_atomic("https://example.com/fail.gguf", dest)
        assert success is False
        assert not dest.exists()
        assert not dest.with_name("failed_model.gguf.tmp").exists()


def test_bootstrap_venv_reexec_sentinel(monkeypatch):
    monkeypatch.setenv("_ORDINFLOW_REEXEC", "1")
    # Should return cleanly without calling subprocess or sys.exit
    _bootstrap_venv()


def test_generate_layer_candidates_auto():
    from core.llm_backends import _generate_layer_candidates

    # -1 (auto) should produce full ladder
    assert _generate_layer_candidates(-1) == [-1, 20, 10, 5, 0]


def test_generate_layer_candidates_explicit():
    from core.llm_backends import _generate_layer_candidates

    # Explicit 22 should step down without jumping higher
    assert _generate_layer_candidates(22) == [22, 20, 10, 5, 0]
    # Explicit 0 should only try CPU
    assert _generate_layer_candidates(0) == [0]
    # Explicit 12 should start with 12 and step down
    assert _generate_layer_candidates(12) == [12, 10, 5, 0]


def test_parse_ggml_type():
    from core.llm_backends import _parse_ggml_type

    # Standard valid integers
    assert _parse_ggml_type(8) == 8
    assert _parse_ggml_type(1) == 1
    assert _parse_ggml_type(0) == 0
    assert _parse_ggml_type(2) == 2

    # String aliases
    assert _parse_ggml_type("q8_0") == 8
    assert _parse_ggml_type("Q8_0") == 8
    assert _parse_ggml_type("f16") == 1
    assert _parse_ggml_type("8bit") == 8
    assert _parse_ggml_type("  q4_0  ") == 2

    # Python bool trap: True should NOT resolve to 1
    assert _parse_ggml_type(True) == 8
    assert _parse_ggml_type(False) == 8

    # Unsupported / invalid / K-quants fallback
    assert _parse_ggml_type("q4_k_m") == 8
    assert _parse_ggml_type("q8_k") == 8
    assert _parse_ggml_type("iq3_s") == 8
    assert _parse_ggml_type(99) == 8
    assert _parse_ggml_type(None) == 8
    assert _parse_ggml_type("garbage", default=1) == 1


def test_filter_supported_kwargs():
    from core.llm_backends import _filter_supported_kwargs

    class DummyClass:
        def __init__(self, model_path: str, n_ctx: int = 2048, flash_attn: bool = True):
            self.model_path = model_path
            self.n_ctx = n_ctx
            self.flash_attn = flash_attn

    input_kwargs = {
        "model_path": "test.gguf",
        "n_ctx": 4096,
        "flash_attn": True,
        "unsupported_param": "foo",
        "another_extra": 123,
    }

    filtered = _filter_supported_kwargs(DummyClass, input_kwargs)
    assert "model_path" in filtered
    assert "n_ctx" in filtered
    assert "flash_attn" in filtered
    assert "unsupported_param" not in filtered
    assert "another_extra" not in filtered
