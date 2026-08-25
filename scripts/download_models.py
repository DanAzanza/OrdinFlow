from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

# Configure UTF-8 stdout if available, with safe fallback
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

MODEL_URLS = {
    "Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf": "https://huggingface.co/unsloth/Qwen3-VL-8B-Instruct-GGUF/resolve/main/Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf",
    "mmproj-BF16.gguf": "https://huggingface.co/unsloth/Qwen3-VL-8B-Instruct-GGUF/resolve/main/mmproj-BF16.gguf",
}

EXPECTED_MIN_SIZES: dict[str, int] = {
    "Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf": 4 * 1024 * 1024 * 1024,  # 4.0 GiB floor
    "mmproj-BF16.gguf": 1 * 1024 * 1024 * 1024,                     # 1.0 GiB floor
}
DEFAULT_MIN_GGUF_SIZE = 10 * 1024 * 1024  # 10 MiB generic floor


def validate_gguf_file(path: Path, expected_min_bytes: int | None = None) -> bool:
    """Verifies that a file exists, meets minimum size threshold, and starts with GGUF magic header."""
    if not path.is_file():
        return False

    min_size = (
        expected_min_bytes
        if expected_min_bytes is not None
        else EXPECTED_MIN_SIZES.get(path.name, DEFAULT_MIN_GGUF_SIZE)
    )

    try:
        if path.stat().st_size < min_size:
            return False
        with open(path, "rb") as f:
            magic = f.read(4)
            return magic == b"GGUF"
    except (OSError, PermissionError):
        return False


def resolve_download_url(url: str) -> str:
    """Converts HuggingFace web blob URLs to raw download resolve URLs if needed."""
    if "huggingface.co" in url and "/blob/" in url:
        return url.replace("/blob/", "/resolve/")
    return url


def download_file_atomic(url: str, dest_path: Path) -> bool:
    """Downloads a file to a .tmp extension and atomically moves it on completion."""
    url = resolve_download_url(url)
    tmp_path = dest_path.with_name(f"{dest_path.name}.tmp")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[*] Downloading {dest_path.name} from {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "OrdinFlow-Installer/1.0"})

    try:
        with urllib.request.urlopen(req) as response, open(tmp_path, "wb") as out_file:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            block_size = 1024 * 1024  # 1 MB

            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                out_file.write(buffer)
                downloaded += len(buffer)

                if total_size > 0:
                    percent = min(100.0, (downloaded / total_size) * 100)
                    mb_read = downloaded / (1024 * 1024)
                    mb_total = total_size / (1024 * 1024)
                    sys.stdout.write(f"\r progress: {percent:.1f}% ({mb_read:.1f} MB / {mb_total:.1f} MB)")
                    sys.stdout.flush()

        print("\n[OK] Download complete. Verifying file integrity...")
        if total_size > 0 and downloaded < total_size:
            raise IOError(f"Incomplete download: {downloaded}/{total_size} bytes received.")

        # GGUF header & size check on temporary file
        expected_min = EXPECTED_MIN_SIZES.get(dest_path.name, DEFAULT_MIN_GGUF_SIZE)
        if not validate_gguf_file(tmp_path, expected_min_bytes=expected_min):
            raise IOError(f"File failed GGUF integrity check (corrupted or missing GGUF header): {dest_path.name}")

        # Atomic replacement
        if dest_path.exists():
            dest_path.unlink()
        os.replace(tmp_path, dest_path)
        print(f"[OK] Successfully installed model: {dest_path.name}")
        return True

    except Exception as e:
        print(f"\n[ERROR] Failed to download {dest_path.name}: {e}")
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        return False


def main() -> None:
    root_dir = Path(__file__).resolve().parent.parent

    llm_path_str = "models/Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf"
    mmproj_path_str = "models/mmproj-BF16.gguf"

    config_path = root_dir / "settings" / "config.yaml"
    if not config_path.exists():
        config_path = root_dir / "config.yaml"

    if config_path.exists():
        try:
            import yaml

            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                llm_path_str = config.get("llm_model_path", llm_path_str)
                mmproj_path_str = config.get("mmproj_path", mmproj_path_str)
        except Exception:
            pass  # Fall back to defaults if PyYAML is unavailable or config has syntax error

    models_to_check = [Path(root_dir / llm_path_str), Path(root_dir / mmproj_path_str)]

    # Detect and remove corrupted stubs before prompting
    missing: list[Path] = []
    for p in models_to_check:
        if p.exists() and not validate_gguf_file(p):
            size_mb = p.stat().st_size / (1024 * 1024)
            print(f"[!] Corrupted or incomplete model file detected: {p.name} (Size: {size_mb:.1f} MB). Removing...")
            try:
                p.unlink()
            except OSError as err:
                print(f"[!] Could not remove corrupt file {p.name}: {err}")
        if not validate_gguf_file(p):
            missing.append(p)

    if not missing:
        print("[OK] All required vision GGUF model files exist and passed integrity checks in models/.")
        return

    print("====================================================")
    print("OrdinFlow Vision Model Setup")
    print("====================================================")

    auto_yes = "--yes" in sys.argv or "-y" in sys.argv

    for target_path in missing:
        filename = target_path.name
        print(f"\n[!] Missing model: {filename}")
        url = MODEL_URLS.get(filename)
        if url:
            if auto_yes:
                download_file_atomic(url, target_path)
            else:
                answer = input(f"Do you want to download {filename} now? (y/N): ").strip().lower()
                if answer in ["y", "yes"]:
                    download_file_atomic(url, target_path)
                else:
                    print(f"Skipped. Please place your GGUF model manually at: {target_path}")
        else:
            print(f"Please place your model manually at: {target_path}")


if __name__ == "__main__":
    main()
