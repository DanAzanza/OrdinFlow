"""Platform-specific helpers for drive listing and native GUI dialogs."""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
import string
import subprocess
import sys

from core.utils import sanitize_safe_path

logger = logging.getLogger(__name__)


def get_system_drives() -> list[str]:
    """Returns available drive letters on Windows or root directory on POSIX."""
    drives: list[str] = []
    if sys.platform == "win32" or os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                drives.append(drive)
    else:
        drives.append("/")
    return drives


def pick_path_dialog(
    picker_type: str = "folder",
    initial_dir: str = "",
    title: str = "",
) -> str | None:
    """Opens a native GUI picker dialog to choose a folder or file."""
    selected_path: str | None = None
    init_dir = os.getcwd()
    if initial_dir and isinstance(initial_dir, str):
        is_safe, clean_init = sanitize_safe_path(initial_dir)
        if is_safe and clean_init:
            p = Path(clean_init).resolve()
            if p.is_dir():
                init_dir = str(p)
            elif p.is_file():
                init_dir = str(p.parent)

    # 1. Try tkinter dialog
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        if picker_type == "file":
            filetypes = (
                [("GGUF Models (*.gguf)", "*.gguf"), ("All Files (*.*)", "*.*")]
                if any(x in title.lower() for x in ("model", "gguf", "projector", "mmproj"))
                else [("All Files (*.*)", "*.*")]
            )
            selected = filedialog.askopenfilename(
                initialdir=init_dir,
                title=title or "Select File",
                filetypes=filetypes,
            )
        else:
            selected = filedialog.askdirectory(
                initialdir=init_dir,
                title=title or "Select Folder",
            )
        root.destroy()
        if selected:
            selected_path = os.path.normpath(selected)
    except Exception as e:
        logger.debug("[PlatformUtils] Native tkinter dialog failed: %s", e)

    # 2. PowerShell fallback on Windows if tkinter didn't produce a path
    if not selected_path and (sys.platform == "win32" or os.name == "nt"):
        try:
            fallback_title = "Select File" if picker_type == "file" else "Select Folder"
            diag_title = title if title else fallback_title

            clean_dir = os.path.abspath(init_dir).replace("'", "''")
            clean_title = diag_title.replace("'", "''").replace("\r", "").replace("\n", " ")

            if picker_type == "file":
                ps_script = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "$f = New-Object System.Windows.Forms.OpenFileDialog; "
                    f"$f.InitialDirectory = '{clean_dir}'; "
                    f"$f.Title = '{clean_title}'; "
                    "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.Write($f.FileName) }"
                )
            else:
                ps_script = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                    f"$f.SelectedPath = '{clean_dir}'; "
                    f"$f.Description = '{clean_title}'; "
                    "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.Write($f.SelectedPath) }"
                )

            encoded_cmd = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_cmd],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if res.returncode == 0 and res.stdout.strip():
                selected_path = os.path.normpath(res.stdout.strip())
        except Exception as e:
            logger.debug("[PlatformUtils] PowerShell picker fallback failed: %s", e)

    return selected_path
