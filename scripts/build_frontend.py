"""Cross-platform frontend build runner with automatic local NTFS staging.

Handles building the React + TypeScript + Vite SPA cleanly both on native
filesystems (CI, Linux, macOS, local NTFS) and on virtual/cloud drives such as
Google Drive File Stream where `npm install` cannot write `node_modules/`.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
OUTPUT_DIR = ROOT_DIR / "static" / "app"

_SYNC_FILES = (
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    "vite.config.ts",
    "vitest.config.ts",
    "components.json",
    "index.html",
)


def _is_native_ntfs_drive(path: Path) -> bool:
    """Returns True when path resides on a local fixed NTFS drive (or non-Windows OS)."""
    if sys.platform != "win32":
        return True

    try:
        resolved = str(path.resolve())
        drive = os.path.splitdrive(resolved)[0]
        if not drive:
            return False
        root_path = drive.rstrip("\\/") + "\\"

        drive_type = ctypes.windll.kernel32.GetDriveTypeW(root_path)
        if drive_type != 3:  # DRIVE_FIXED
            return False

        fs_buf = ctypes.create_unicode_buffer(64)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            root_path,
            None,
            0,
            None,
            None,
            None,
            fs_buf,
            len(fs_buf),
        )
        if not ok:
            return False
        return fs_buf.value.upper() == "NTFS"
    except (OSError, AttributeError):
        return False


def _npm_executable() -> str:
    return "npm.cmd" if sys.platform == "win32" else "npm"


def _compute_deps_hash(frontend_dir: Path) -> str:
    hasher = hashlib.sha256()
    for fname in ("package.json", "package-lock.json"):
        fpath = frontend_dir / fname
        if fpath.is_file():
            hasher.update(fname.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(fpath.read_bytes())
    return hasher.hexdigest()


def _copy_if_changed(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_file() and src.stat().st_size == dst.stat().st_size:
        if src.read_bytes() == dst.read_bytes():
            return
    shutil.copy2(src, dst)


def _sync_dir_tree(src_dir: Path, dst_dir: Path) -> None:
    """Mirrors src_dir into dst_dir, pruning deleted files while minimizing writes."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    expected_rel: set[str] = set()

    if src_dir.is_dir():
        for item in src_dir.rglob("*"):
            if item.is_file():
                rel = item.relative_to(src_dir).as_posix()
                expected_rel.add(rel)
                _copy_if_changed(item, dst_dir / rel)

    for existing in list(dst_dir.rglob("*")):
        if existing.is_file():
            rel = existing.relative_to(dst_dir).as_posix()
            if rel not in expected_rel:
                existing.unlink()
    for existing_dir in sorted(
        (p for p in dst_dir.rglob("*") if p.is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,
    ):
        try:
            if not any(existing_dir.iterdir()):
                existing_dir.rmdir()
        except OSError:
            pass


def _sync_to_staging(frontend_dir: Path, staging_dir: Path) -> None:
    staging_dir.mkdir(parents=True, exist_ok=True)
    for fname in _SYNC_FILES:
        src = frontend_dir / fname
        dst = staging_dir / fname
        if src.is_file():
            _copy_if_changed(src, dst)
        elif dst.is_file():
            dst.unlink()
    _sync_dir_tree(frontend_dir / "src", staging_dir / "src")


def _run_npm(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> int:
    cmd = [_npm_executable(), *args]
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    print(f"[Frontend] Running in {cwd}: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(cwd), env=merged_env, check=False)
    return res.returncode


def _ensure_dependencies(work_dir: Path, frontend_dir: Path, staged: bool) -> int:
    node_modules = work_dir / "node_modules"
    hash_file = work_dir / ".deps.sha256"
    current_hash = _compute_deps_hash(frontend_dir)

    if node_modules.is_dir() and hash_file.is_file():
        if hash_file.read_text(encoding="utf-8").strip() == current_hash:
            return 0

    has_lockfile = (work_dir / "package-lock.json").is_file()
    subcmd = ["ci"] if has_lockfile else ["install"]
    code = _run_npm(subcmd, cwd=work_dir)
    if code != 0 and has_lockfile:
        print("[Frontend] npm ci failed; retrying with npm install...")
        code = _run_npm(["install"], cwd=work_dir)
    if code != 0:
        return code

    if staged:
        lock_src = work_dir / "package-lock.json"
        lock_dst = frontend_dir / "package-lock.json"
        if lock_src.is_file():
            _copy_if_changed(lock_src, lock_dst)

    hash_file.write_text(_compute_deps_hash(frontend_dir), encoding="utf-8")
    return 0


def run_frontend_tasks(
    install: bool = False,
    typecheck: bool = False,
    test: bool = False,
    build: bool = False,
) -> int:
    if not FRONTEND_DIR.is_dir() or not (FRONTEND_DIR / "package.json").is_file():
        print("[Frontend] frontend/package.json not found; skipping.", file=sys.stderr)
        return 1

    native_mode = _is_native_ntfs_drive(FRONTEND_DIR)
    if native_mode:
        work_dir = FRONTEND_DIR
        staged = False
        print(f"[Frontend] Using native workspace: {work_dir}")
    else:
        local_base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
        work_dir = local_base / "OrdinFlow" / "frontend-build"
        staged = True
        print(f"[Frontend] Non-NTFS workspace detected; staging build in: {work_dir}")
        _sync_to_staging(FRONTEND_DIR, work_dir)

    if install or not (work_dir / "node_modules").is_dir():
        code = _ensure_dependencies(work_dir, FRONTEND_DIR, staged=staged)
        if code != 0:
            return code
    elif staged:
        # Ensure dependencies stay fresh when package.json changes
        code = _ensure_dependencies(work_dir, FRONTEND_DIR, staged=True)
        if code != 0:
            return code

    if typecheck:
        code = _run_npm(["run", "typecheck"], cwd=work_dir)
        if code != 0:
            return code

    if test:
        code = _run_npm(["run", "test"], cwd=work_dir)
        if code != 0:
            return code

    if build:
        if staged:
            staged_out = work_dir / "out"
            code = _run_npm(
                ["run", "build"],
                cwd=work_dir,
                env={"ORDINFLOW_OUT_DIR": str(staged_out)},
            )
            if code != 0:
                return code
            _sync_dir_tree(staged_out, OUTPUT_DIR)
            print(f"[Frontend] Synced built bundle to: {OUTPUT_DIR}")
        else:
            code = _run_npm(["run", "build"], cwd=work_dir)
            if code != 0:
                return code

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and verify OrdinFlow React frontend")
    parser.add_argument("--install", action="store_true", help="Ensure npm dependencies are installed")
    parser.add_argument("--typecheck", action="store_true", help="Run TypeScript typecheck")
    parser.add_argument("--test", action="store_true", help="Run Vitest unit tests")
    parser.add_argument("--build", action="store_true", help="Build production bundle to static/app/")
    parser.add_argument("--all", action="store_true", help="Run install, typecheck, test, and build")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.all or not (args.install or args.typecheck or args.test or args.build):
        return run_frontend_tasks(install=True, typecheck=True, test=True, build=True)
    return run_frontend_tasks(
        install=args.install,
        typecheck=args.typecheck,
        test=args.test,
        build=args.build,
    )


if __name__ == "__main__":
    sys.exit(main())
