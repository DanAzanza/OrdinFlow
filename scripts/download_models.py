import sys
import urllib.request
from pathlib import Path

import yaml

MODEL_URLS = {
    "Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf": "https://huggingface.co/unsloth/Qwen3-VL-8B-Instruct-GGUF/resolve/main/Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf",
    "mmproj-BF16.gguf": "https://huggingface.co/unsloth/Qwen3-VL-8B-Instruct-GGUF/resolve/main/mmproj-BF16.gguf",
}


def resolve_download_url(url: str) -> str:
    """Converts HuggingFace web blob URLs to raw download resolve URLs if needed."""
    if "huggingface.co" in url and "/blob/" in url:
        return url.replace("/blob/", "/resolve/")
    return url


def download_file(url: str, dest_path: Path):
    url = resolve_download_url(url)
    print(f"[*] Downloading {dest_path.name} from {url}...")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    def report_progress(block_num, block_size, total_size):
        read_bytes = block_num * block_size
        if total_size > 0:
            percent = min(100.0, (read_bytes / total_size) * 100)
            mb_read = read_bytes / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            sys.stdout.write(f"\r progress: {percent:.1f}% ({mb_read:.1f} MB / {mb_total:.1f} MB)")
            sys.stdout.flush()

    try:
        urllib.request.urlretrieve(url, dest_path, reporthook=report_progress)
        print("\n[✓] Download complete!")
    except Exception as e:
        print(f"\n[✗] Failed to download {dest_path.name}: {e}")


def main():
    root_dir = Path(__file__).resolve().parent.parent
    config_path = root_dir / "settings" / "config.yaml"
    if not config_path.exists():
        config_path = root_dir / "config.yaml"

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    llm_path_str = config.get("llm_model_path", "models/Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf")
    mmproj_path_str = config.get("mmproj_path", "models/mmproj-BF16.gguf")

    models_to_check = [Path(root_dir / llm_path_str), Path(root_dir / mmproj_path_str)]

    missing = [p for p in models_to_check if not p.exists()]

    if not missing:
        print("[✓] All required vision GGUF model files exist in models/.")
        return

    print("====================================================")
    print("OrdinFlow Model Setup")
    print("====================================================")
    for target_path in missing:
        filename = target_path.name
        print(f"\n[!] Missing model: {filename}")
        url = MODEL_URLS.get(filename)
        if url:
            answer = input(f"Do you want to download {filename} now? (y/N): ").strip().lower()
            if answer in ["y", "yes"]:
                download_file(url, target_path)
            else:
                print(f"Skipped. Please place your GGUF model manually at: {target_path}")
        else:
            print(f"Please place your model manually at: {target_path}")


if __name__ == "__main__":
    main()
