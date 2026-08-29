"""Local CI Quality Gate runner for OrdinFlow.

Executes the exact checks as `.github/workflows/ci.yml`:
1. Ruff linter (full repo)
2. Pyright static type analysis (`core/` and `routes/`)
3. Pytest suite
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _resolve_pyright_cmd() -> tuple[list[str], bool]:
    """Determines the most reliable pyright invocation across Python venv, PATH binary, and npx."""
    try:
        import pyright  # noqa: F401

        return [sys.executable, "-m", "pyright", "core/", "routes/"], False
    except ImportError:
        pass

    if shutil.which("pyright"):
        return ["pyright", "core/", "routes/"], (sys.platform == "win32")

    if shutil.which("npx"):
        return ["npx", "pyright", "core/", "routes/"], (sys.platform == "win32")

    return [sys.executable, "-m", "pyright", "core/", "routes/"], False


def run_gate(name: str, cmd: list[str], use_shell: bool = False) -> bool:
    """Executes a single quality gate command, printing clean diagnostics."""
    print(f"\n[CI Gate] Running {name}...")
    print(f"Command: {' '.join(cmd)}")
    start_t = time.time()
    try:
        cmd_input = subprocess.list2cmdline(cmd) if use_shell else cmd
        res = subprocess.run(
            cmd_input,
            shell=use_shell,
            cwd=str(ROOT_DIR),
            text=True,
            capture_output=False,
        )
        elapsed = time.time() - start_t
        if res.returncode == 0:
            print(f"[CI Gate] \033[92mPASS\033[0m: {name} completed successfully in {elapsed:.2f}s")
            return True
        else:
            print(f"[CI Gate] \033[91mFAIL\033[0m: {name} failed with exit code {res.returncode} ({elapsed:.2f}s)")
            return False
    except FileNotFoundError as e:
        print(f"[CI Gate] \033[91mERROR\033[0m: Executable not found for {name}: {e}")
        return False
    except Exception as e:
        print(f"[CI Gate] \033[91mERROR\033[0m: Unexpected error running {name}: {e}")
        return False


def main() -> int:
    """Executes full CI verification pipeline."""
    print("=" * 60)
    print(" OrdinFlow Local CI Pre-Commit Quality Gate ")
    print("=" * 60)

    # 1. Ruff Linter
    ruff_ok = run_gate("Ruff Linter", [sys.executable, "-m", "ruff", "check", "."])
    if not ruff_ok:
        print("\n\033[91m[!] CI Gate Blocked by Ruff Linter errors.\033[0m")
        return 1

    # 2. Pyright Static Type Checker (Full scope: core/ and routes/)
    pyright_cmd, use_shell = _resolve_pyright_cmd()
    pyright_ok = run_gate("Pyright Static Type Checker", pyright_cmd, use_shell=use_shell)
    if not pyright_ok:
        print("\n\033[91m[!] CI Gate Blocked by Pyright Type Diagnostics.\033[0m")
        return 1

    # 3. Pytest Suite
    pytest_ok = run_gate("Pytest Test Suite", [sys.executable, "-m", "pytest", "-q"])
    if not pytest_ok:
        print("\n\033[91m[!] CI Gate Blocked by Pytest Failures.\033[0m")
        return 1

    print("\n" + "=" * 60)
    print(" \033[92mALL CI GATES PASSED (0 errors, 0 warnings)\033[0m ")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
