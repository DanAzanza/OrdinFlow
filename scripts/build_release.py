"""
OrdinFlow Release Packaging Script.

Packages a clean, self-contained, sanitized release archive (ZIP) and SHA256 checksums
for GitHub Releases and on-premise deployments.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

import yaml

# Root directory of the repository
ROOT_DIR = Path(__file__).resolve().parent.parent


def get_pyproject_version() -> str:
    """Reads the current project version from pyproject.toml."""
    pyproject_path = ROOT_DIR / "pyproject.toml"
    if not pyproject_path.is_file():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")

    content = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
    if not match:
        raise ValueError("Could not parse version from pyproject.toml")
    return match.group(1).strip()


def sanitize_config_yaml(src_path: Path) -> bytes:
    """Cleanses config.yaml by clearing developer-specific watch and target directories."""
    if not src_path.is_file():
        return b""

    with open(src_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # Ensure empty string defaults so AppConfig.setup_paths() creates ./Inbox and ./Cases locally
    data["watch_dir"] = ""
    data["target_base_dir"] = ""

    cleaned_str = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return cleaned_str.encode("utf-8")


def normalize_crlf(content: bytes) -> bytes:
    """Normalizes line endings to Windows CRLF (\r\n) for batch scripts."""
    # Replace \r\n with \n first, then \n with \r\n
    text = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return text.replace(b"\n", b"\r\n")


def is_excluded_path(rel_path: str) -> bool:
    """Determines whether a relative path inside the repo should be excluded from release."""
    posix_path = rel_path.replace("\\", "/")
    parts = posix_path.split("/")

    # Excluded directories anywhere in tree
    denied_dir_names = {
        ".git",
        ".github",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "venv",
        ".venv",
        "scratch",
        "tests",
        ".vscode",
        ".idea",
        "htmlcov",
        "dist",
        "build",
    }
    if any(p in denied_dir_names for p in parts[:-1]):
        return True

    # Excluded filenames and patterns
    filename = parts[-1].lower()
    if filename.startswith(".git") or filename.startswith(".coverage"):
        return True

    # Deny log files, temporary and debug files
    if filename.endswith(".log") or filename.endswith(".tmp") or filename.endswith(".flag") or filename.endswith(".bak"):
        return True

    # Deny compiled bytecode
    if filename.endswith(".pyc") or filename.endswith(".pyo") or filename.endswith(".pyd"):
        return True

    # Deny active queue state or developer cursor/IDE rules
    if filename in {"queue_state.json", ".cursorrules", "crash.log", "main.log"}:
        return True

    # Deny binary model weights in models/ directory (must be downloaded via download_models.py)
    if "models/" in posix_path:
        if filename.endswith((".gguf", ".bin", ".pt", ".safetensors", ".part")):
            return True

    return False


def build_release_archive(
    version: str,
    output_dir: Path,
    root_dir: Path = ROOT_DIR,
    allow_version_mismatch: bool = False,
) -> tuple[Path, Path]:
    """Builds the release zip archive and companion SHA256 checksum file."""
    # 1. Version validation
    normalized_version = version.lstrip("v")
    toml_version = get_pyproject_version()

    if normalized_version != toml_version and not allow_version_mismatch:
        raise ValueError(
            f"Version mismatch: Specified version is '{version}' (normalized '{normalized_version}') "
            f"but pyproject.toml defines version '{toml_version}'. "
            f"Please update pyproject.toml or use the correct version tag."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    zip_filename = f"OrdinFlow-v{normalized_version}.zip"
    zip_path = output_dir / zip_filename
    checksum_filename = f"OrdinFlow-v{normalized_version}-checksums.sha256"
    checksum_path = output_dir / checksum_filename

    bundle_prefix = f"OrdinFlow-v{normalized_version}"
    print(f"[*] Packaging release bundle: {zip_filename}")
    print(f"[*] Root bundle directory: {bundle_prefix}/")

    # 2. Collect files to include
    files_to_pack: list[tuple[Path, str]] = []

    # Mandatory root files
    root_files = [
        "main.py",
        "dashboard.py",
        "Install_OrdinFlow.bat",
        "Start_OrdinFlow.bat",
        "requirements.txt",
        "pyproject.toml",
        "LICENSE",
        "README.md",
        "THIRD_PARTY_LICENSES.md",
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
    ]
    for rf in root_files:
        p = root_dir / rf
        if p.is_file():
            files_to_pack.append((p, f"{bundle_prefix}/{rf}"))

    # Directories to pack recursively
    include_dirs = [
        "core",
        "routes",
        "scripts",
        "sample_data",
        "settings",
        "static",
        "templates",
        "docs",
    ]
    for d in include_dirs:
        dir_path = root_dir / d
        if not dir_path.is_dir():
            continue
        for child in dir_path.rglob("*"):
            if not child.is_file():
                continue
            rel_to_root = child.relative_to(root_dir).as_posix()
            if is_excluded_path(rel_to_root):
                continue
            arc_name = f"{bundle_prefix}/{rel_to_root}"
            files_to_pack.append((child, arc_name))

    # Add placeholder and guide for models directory
    models_readme = (
        "OrdinFlow Models Directory\n"
        "=========================\n\n"
        "Quantized Vision-LLM models are not bundled directly inside the release zip.\n"
        "Run 'Install_OrdinFlow.bat' (Windows) or 'python scripts/download_models.py' (Linux/macOS)\n"
        "to automatically download and verify the official models from HuggingFace.\n"
    ).encode("utf-8")

    # 3. Write ZIP archive
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        # Write models/.gitkeep and models/README.txt
        zf.writestr(f"{bundle_prefix}/models/.gitkeep", b"")
        zf.writestr(f"{bundle_prefix}/models/README.txt", models_readme)

        # Write collected files
        for src_path, arc_name in files_to_pack:
            rel_path = src_path.relative_to(root_dir).as_posix()

            # Special handling: Sanitize settings/config.yaml
            if rel_path == "settings/config.yaml":
                cleansed_bytes = sanitize_config_yaml(src_path)
                zf.writestr(arc_name, cleansed_bytes)
                continue

            # Special handling: Enforce CRLF on .bat files
            if src_path.suffix.lower() == ".bat":
                raw_bytes = src_path.read_bytes()
                crlf_bytes = normalize_crlf(raw_bytes)
                zf.writestr(arc_name, crlf_bytes)
                continue

            # Default: stream file into zip
            zf.write(src_path, arcname=arc_name)

    # 4. Generate SHA256 Checksum
    hasher = hashlib.sha256()
    with open(zip_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    sha256_hex = hasher.hexdigest()

    checksum_line = f"{sha256_hex}  {zip_filename}\n"
    checksum_path.write_text(checksum_line, encoding="utf-8")

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"[OK] Release archive created: {zip_path} ({size_mb:.2f} MB)")
    print(f"[OK] Checksum created: {checksum_path} (SHA256: {sha256_hex})")

    return zip_path, checksum_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build OrdinFlow Release Archive")
    parser.add_argument(
        "--version",
        default="",
        help="Release version tag (e.g. 'v1.0.0' or '1.0.0'). Defaults to version in pyproject.toml.",
    )
    parser.add_argument(
        "--output-dir",
        default="dist",
        help="Output directory for the generated release zip and checksum file.",
    )
    parser.add_argument(
        "--allow-version-mismatch",
        action="store_true",
        help="Allow building even if version does not match pyproject.toml (for dev testing).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    version = args.version or get_pyproject_version()
    output_dir = Path(args.output_dir).resolve()

    try:
        build_release_archive(
            version=version,
            output_dir=output_dir,
            allow_version_mismatch=args.allow_version_mismatch,
        )
        return 0
    except Exception as e:
        print(f"\n[ERROR] Failed to build release: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
