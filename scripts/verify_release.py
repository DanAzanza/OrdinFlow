"""
OrdinFlow Release Verification Script.

Performs adversarial validation on a built release archive (.zip) and its SHA256 checksums:
1. SHA-256 Checksum Verification
2. Zip-Slip-safe Sandbox Extraction
3. Critical Manifest Completeness Check
4. Hygiene & Anti-Leakage Audit (Zero .git, venv, caches, logs, queue_state, or >10MB models)
5. Bytecode Compilation across all extracted Python files
6. Isolated Smoke Import Execution (without triggering _bootstrap_venv or background daemons)
"""

from __future__ import annotations

import argparse
import hashlib
import py_compile
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import yaml


def verify_sha256(archive_path: Path, checksum_path: Path | None = None) -> bool:
    """Verifies that the archive's SHA256 matches the companion checksum file."""
    if not archive_path.is_file():
        print(f"[FAIL] Archive file does not exist: {archive_path}")
        return False

    hasher = hashlib.sha256()
    with open(archive_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    actual_hash = hasher.hexdigest().lower()

    if checksum_path and checksum_path.is_file():
        checksum_content = checksum_path.read_text(encoding="utf-8").strip()
        expected_hash = checksum_content.split()[0].lower()
        if actual_hash != expected_hash:
            print(f"[FAIL] Checksum mismatch!\n  Expected: {expected_hash}\n  Actual:   {actual_hash}")
            return False
        print(f"[OK] SHA256 Checksum verified: {actual_hash}")
    else:
        print(f"[*] Calculated SHA256: {actual_hash} (no checksum file supplied)")

    return True


def safe_extract_archive(archive_path: Path, target_dir: Path) -> Path:
    """Safely extracts ZIP archive into target_dir with strict Zip-Slip protection."""
    target_dir_resolved = target_dir.resolve()

    with zipfile.ZipFile(archive_path, "r") as zf:
        for member in zf.infolist():
            # Check for zip-slip vectors
            norm_name = member.filename.replace("\\", "/")
            if ".." in norm_name.split("/"):
                raise ValueError(f"Zip-Slip vulnerability detected in member: {member.filename}")
            if norm_name.startswith("/") or (len(norm_name) > 1 and norm_name[1] == ":"):
                raise ValueError(f"Absolute path vulnerability detected in member: {member.filename}")

            dest_path = (target_dir_resolved / norm_name).resolve()
            if not str(dest_path).startswith(str(target_dir_resolved)):
                raise ValueError(f"Path traversal detected: {member.filename} escapes extraction sandbox")

        zf.extractall(target_dir_resolved)

    # Detect top-level bundle directory
    extracted_items = [p for p in target_dir_resolved.iterdir() if p.is_dir()]
    if len(extracted_items) == 1 and (extracted_items[0] / "main.py").is_file():
        return extracted_items[0]
    return target_dir_resolved


def check_manifest(bundle_dir: Path) -> bool:
    """Verifies that all required files and directories are present in the bundle."""
    required_files = [
        "main.py",
        "dashboard.py",
        "Install_OrdinFlow.bat",
        "Start_OrdinFlow.bat",
        "requirements.txt",
        "pyproject.toml",
        "LICENSE",
        "README.md",
        "THIRD_PARTY_LICENSES.md",
        "core/config.py",
        "core/processor.py",
        "core/voting.py",
        "core/extraction_pipeline.py",
        "routes/ui.py",
        "routes/api/__init__.py",
        "scripts/setup_environment.py",
        "scripts/download_models.py",
        "sample_data/cake_recipe_skill_example.yaml",
        "sample_data/recipes_pdf/Recipe__01_Black_Forest_Cake.pdf",
        "settings/config.yaml",
        "models/.gitkeep",
    ]

    missing = []
    for rf in required_files:
        if not (bundle_dir / rf).is_file():
            missing.append(rf)

    if missing:
        print(f"[FAIL] Missing required files in release bundle ({len(missing)}):")
        for m in missing:
            print(f"  - {m}")
        return False

    print(f"[OK] Manifest check passed ({len(required_files)} mandatory files verified).")
    return True


def check_hygiene(bundle_dir: Path) -> bool:
    """Audits extracted bundle to ensure zero secret/cache/model leaks or dirty dev states."""
    forbidden_patterns = [
        ".git",
        ".github",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "venv",
        ".venv",
        ".coverage",
        "crash.log",
        "main.log",
        "queue_state.json",
        ".cursorrules",
    ]

    violations = []
    max_file_size = 10 * 1024 * 1024  # 10 MB maximum allowed file in archive

    for path in bundle_dir.rglob("*"):
        rel_posix = path.relative_to(bundle_dir).as_posix()
        parts = rel_posix.split("/")

        # Check directory / filename forbidden patterns
        for forbidden in forbidden_patterns:
            if forbidden in parts or path.name == forbidden or path.name.endswith(".pyc"):
                violations.append(f"Forbidden asset found: {rel_posix}")

        # Check for heavy binary model files
        if path.is_file():
            size = path.stat().st_size
            if size > max_file_size:
                violations.append(f"File exceeds 10MB limit ({size / (1024*1024):.2f} MB): {rel_posix}")
            if path.suffix.lower() in {".gguf", ".safetensors", ".bin", ".pt"}:
                violations.append(f"Heavy model weight file included: {rel_posix}")

    # Check that settings/config.yaml is cleansed
    cfg_file = bundle_dir / "settings" / "config.yaml"
    if cfg_file.is_file():
        try:
            with open(cfg_file, encoding="utf-8") as f:
                cfg_data = yaml.safe_load(f) or {}
            watch_dir = cfg_data.get("watch_dir", "")
            target_dir = cfg_data.get("target_base_dir", "")
            if watch_dir != "" or target_dir != "":
                violations.append(f"settings/config.yaml contains dirty dev paths: watch='{watch_dir}', target='{target_dir}'")
        except Exception as e:
            violations.append(f"Could not parse settings/config.yaml: {e}")

    # Check that .bat files have Windows CRLF line endings
    for bat_name in ["Install_OrdinFlow.bat", "Start_OrdinFlow.bat"]:
        bat_file = bundle_dir / bat_name
        if bat_file.is_file():
            content = bat_file.read_bytes()
            if b"\n" in content and b"\r\n" not in content:
                violations.append(f"{bat_name} does not have CRLF line endings")

    if violations:
        print(f"[FAIL] Hygiene audit failed ({len(violations)} violations):")
        for v in violations:
            print(f"  - {v}")
        return False

    print("[OK] Hygiene audit passed (0 forbidden files, 0 leaks, clean config, CRLF verified).")
    return True


def check_python_compilation(bundle_dir: Path) -> bool:
    """Verifies that all Python files inside the bundle compile to valid bytecode without syntax errors."""
    py_files = list(bundle_dir.rglob("*.py"))
    if not py_files:
        print("[FAIL] No Python files found in bundle!")
        return False

    compile_errors = []
    for py_file in py_files:
        try:
            py_compile.compile(str(py_file), doraise=True)
        except py_compile.PyCompileError as e:
            compile_errors.append(f"{py_file.name}: {e}")

    if compile_errors:
        print(f"[FAIL] Bytecode compilation errors ({len(compile_errors)}):")
        for err in compile_errors:
            print(f"  - {err}")
        return False

    print(f"[OK] Python bytecode compilation passed ({len(py_files)} files syntax-checked).")
    return True


def check_smoke_import(bundle_dir: Path) -> bool:
    """Executes isolated module imports in a fresh subshell to verify decoupled core & route loading."""
    smoke_code = (
        "import sys, os\n"
        f"bundle_path = r'{bundle_dir.resolve()}'\n"
        "sys.path.insert(0, bundle_path)\n"
        "os.environ['_ORDINFLOW_REEXEC'] = '1'\n"  # Prevent bootstrap venv re-exec
        "from core.config import AppConfig\n"
        "cfg = AppConfig(base_dir=bundle_path)\n"
        "assert cfg.dashboard_port == 8080\n"
        "print('[SMOKE] AppConfig initialized successfully.')\n"
        "import dashboard\n"
        "assert hasattr(dashboard, 'app')\n"
        "print('[SMOKE] Flask dashboard app loaded successfully.')\n"
        "import routes.api\n"
        "print('[SMOKE] API routes module loaded successfully.')\n"
    )

    try:
        res = subprocess.run(
            [sys.executable, "-c", smoke_code],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if res.returncode != 0:
            print(f"[FAIL] Smoke import test failed (exit code {res.returncode}):\n{res.stderr}")
            return False

        print("[OK] Isolated smoke import tests passed successfully.")
        return True
    except subprocess.TimeoutExpired:
        print("[FAIL] Smoke import test timed out after 15 seconds.")
        return False
    except Exception as e:
        print(f"[FAIL] Smoke import test error: {e}")
        return False


def verify_bundle(archive_path: Path, checksum_path: Path | None = None) -> bool:
    """Runs the full release verification gate on the specified archive."""
    print("=" * 60)
    print(f" Verifying Release Bundle: {archive_path.name}")
    print("=" * 60)

    # 1. SHA256 Checksum
    if not verify_sha256(archive_path, checksum_path):
        return False

    # 2. Extract into temporary sandbox
    with tempfile.TemporaryDirectory(prefix="ordinflow_verify_") as tmp_dir:
        tmp_target = Path(tmp_dir)
        try:
            bundle_dir = safe_extract_archive(archive_path, tmp_target)
        except Exception as e:
            print(f"[FAIL] Failed to safely extract archive: {e}")
            return False

        # 3. Manifest Completeness Check
        if not check_manifest(bundle_dir):
            return False

        # 4. Hygiene Audit
        if not check_hygiene(bundle_dir):
            return False

        # 5. Bytecode Compilation
        if not check_python_compilation(bundle_dir):
            return False

        # 6. Isolated Smoke Imports
        if not check_smoke_import(bundle_dir):
            return False

    print("\n" + "=" * 60)
    print(" [OK] ALL RELEASE VERIFICATION GATES PASSED (0 defects) ")
    print("=" * 60)
    return True


def verify_installer(installer_path: Path, checksum_path: Path | None = None) -> bool:
    """Performs validation on a built Inno Setup installer executable (.exe)."""
    print("=" * 60)
    print(f"[*] Validating Inno Setup Installer: {installer_path.name}")
    print("=" * 60)

    # 1. Existence and size check
    if not installer_path.is_file():
        print(f"[FAIL] Installer executable does not exist: {installer_path}")
        return False

    size_bytes = installer_path.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    print(f"[*] Binary Size: {size_mb:.2f} MB ({size_bytes} bytes)")
    if size_bytes < 100 * 1024:
        print("[FAIL] Installer file is unexpectedly small (< 100 KB). Likely corrupt or empty.")
        return False

    # 2. Windows PE executable magic check
    try:
        with open(installer_path, "rb") as f:
            magic = f.read(2)
            if magic != b"MZ":
                print(f"[FAIL] Invalid executable header: expected b'MZ', found {magic!r}")
                return False
    except OSError as e:
        print(f"[FAIL] Could not read executable header: {e}")
        return False
    print("[OK] Valid Windows PE executable header (MZ) confirmed.")

    # 3. SHA256 Checksum Verification
    if not verify_sha256(installer_path, checksum_path):
        return False

    print("\n" + "=" * 60)
    print(" [OK] INSTALLER RELEASE VERIFICATION PASSED (0 defects) ")
    print("=" * 60)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify OrdinFlow Release Artifacts (Archive or Installer)")
    parser.add_argument("--archive", default=None, help="Path to release .zip archive")
    parser.add_argument("--installer", default=None, help="Path to release Inno Setup installer .exe")
    parser.add_argument("--checksum-file", default=None, help="Optional path to .sha256 checksum file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checksum_path = Path(args.checksum_file).resolve() if args.checksum_file else None

    if args.installer:
        installer_path = Path(args.installer).resolve()
        success = verify_installer(installer_path, checksum_path)
        return 0 if success else 1

    if args.archive:
        archive_path = Path(args.archive).resolve()
        if archive_path.suffix.lower() == ".exe":
            success = verify_installer(archive_path, checksum_path)
        else:
            success = verify_bundle(archive_path, checksum_path)
        return 0 if success else 1

    print("[ERROR] Please specify either --archive or --installer.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
