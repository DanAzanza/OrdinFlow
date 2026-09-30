"""Tests for OrdinFlow environment setup orchestrator and model downloader."""

from __future__ import annotations

import os
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
    hf_blob = "https://huggingface.co/unsloth/Qwen3-VL-4B-Instruct-GGUF/blob/main/model.gguf"
    resolved = dm.resolve_download_url(hf_blob)
    assert resolved == "https://huggingface.co/unsloth/Qwen3-VL-4B-Instruct-GGUF/resolve/main/model.gguf"


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


def test_is_nvidia_cuda_available():
    from core.llm_backends import _is_nvidia_cuda_available

    res = _is_nvidia_cuda_available()
    assert isinstance(res, bool)


def test_is_vulkan_available():
    from core.llm_backends import _is_vulkan_available

    res = _is_vulkan_available()
    assert isinstance(res, bool)


def test_is_gpu_acceleration_available(monkeypatch):
    from core.llm_backends import _is_gpu_acceleration_available

    res = _is_gpu_acceleration_available()
    assert isinstance(res, bool)

    # Test darwin override
    monkeypatch.setattr("sys.platform", "darwin")
    assert _is_gpu_acceleration_available() is True


def test_inno_setup_script_directives():
    """Validates that ordinflow.iss contains critical safety directives."""
    iss_path = Path(__file__).resolve().parent.parent / "installer" / "ordinflow.iss"
    assert iss_path.is_file(), "installer/ordinflow.iss must exist"
    content = iss_path.read_text(encoding="utf-8")

    assert "PrivilegesRequired=lowest" in content
    assert "PrivilegesRequiredOverridesAllowed=dialog" in content
    assert "runasoriginaluser" in content  # Prevents UAC postinstall poisoning
    assert "ArchitecturesInstallIn64BitMode=x64compatible" in content
    assert "InitializeUninstall" in content  # Patient record protection guard
    assert "InitializeSetup" in content  # Python pre-flight check


def test_find_iscc_compiler_from_path(monkeypatch):
    from scripts.build_release import find_iscc_compiler

    monkeypatch.setattr("shutil.which", lambda cmd: r"C:\Tools\Inno\iscc.exe" if cmd == "iscc" else None)
    res = find_iscc_compiler()
    assert res == Path(r"C:\Tools\Inno\iscc.exe")


def test_find_iscc_compiler_missing(monkeypatch):
    from scripts.build_release import find_iscc_compiler

    monkeypatch.setattr("shutil.which", lambda cmd: None)
    with patch("pathlib.Path.is_file", return_value=False):
        assert find_iscc_compiler() is None


def test_build_inno_installer_mocked(tmp_path: Path):
    from scripts.build_release import build_inno_installer

    dist_dir = tmp_path / "dist"
    fake_exe = dist_dir / "OrdinFlow-Setup-v0.9.0.exe"

    def fake_subprocess_run(cmd, check=False):
        # Create fake exe payload (>100KB with MZ header)
        dist_dir.mkdir(parents=True, exist_ok=True)
        fake_exe.write_bytes(b"MZ" + b"\x00" * (120 * 1024))
        mock_res = MagicMock()
        mock_res.returncode = 0
        return mock_res

    with (
        patch("scripts.build_release.find_iscc_compiler", return_value=Path(r"C:\fake\iscc.exe")),
        patch("subprocess.run", side_effect=fake_subprocess_run),
    ):
        exe_path, checksum_path = build_inno_installer(
            version="0.9.0",
            output_dir=dist_dir,
            allow_version_mismatch=True,
        )
        assert exe_path.is_file()
        assert checksum_path.is_file()
        assert "OrdinFlow-Setup-v0.9.0.exe" in checksum_path.read_text(encoding="utf-8")


def test_verify_installer_valid(tmp_path: Path):
    from scripts.verify_release import verify_installer

    fake_exe = tmp_path / "OrdinFlow-Setup-v0.9.0.exe"
    payload = b"MZ" + b"\x00" * (200 * 1024)
    fake_exe.write_bytes(payload)

    import hashlib

    hasher = hashlib.sha256(payload)
    sha_file = tmp_path / "checksums.sha256"
    sha_file.write_text(f"{hasher.hexdigest()}  {fake_exe.name}\n", encoding="utf-8")

    assert verify_installer(fake_exe, sha_file) is True


def test_verify_installer_corrupt_header(tmp_path: Path):
    from scripts.verify_release import verify_installer

    fake_exe = tmp_path / "OrdinFlow-Setup-v0.9.0.exe"
    fake_exe.write_bytes(b"PK" + b"\x00" * (200 * 1024))  # ZIP header instead of MZ

    assert verify_installer(fake_exe) is False


def test_verify_installer_too_small(tmp_path: Path):
    from scripts.verify_release import verify_installer

    fake_exe = tmp_path / "OrdinFlow-Setup-v0.9.0.exe"
    fake_exe.write_bytes(b"MZ" + b"\x00" * 100)  # Only ~100 bytes

    assert verify_installer(fake_exe) is False


def test_config_setup_paths_write_fallback(tmp_path: Path, monkeypatch):
    from core.config import AppConfig

    read_only_dir = tmp_path / "protected_app"
    read_only_dir.mkdir()
    fake_appdata = tmp_path / "user_appdata"
    fake_appdata.mkdir()

    monkeypatch.setenv("LOCALAPPDATA", str(fake_appdata))
    monkeypatch.setattr(sys, "platform", "win32")

    cfg = AppConfig(base_dir=str(read_only_dir))

    # Mock os.access to report base_dir is NOT writable
    orig_access = os.access

    def mock_access(path, mode):
        if str(path) == str(read_only_dir.resolve()):
            return False
        return orig_access(path, mode)

    monkeypatch.setattr(os, "access", mock_access)

    cfg.setup_paths()

    # watch_dir and target_base_dir should be inside fake_appdata
    assert str(fake_appdata) in cfg.watch_dir
    assert str(fake_appdata) in cfg.target_base_dir


