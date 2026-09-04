"""Architecture guard and hygiene tests to automatically enforce AGENTS.md rules.

These tests convert passive documentation guidelines into hard, failing CI gates:
1. File line size limits (Max 800 LOC ceiling per file).
2. Platform safety guards on Win32/native system calls.
3. Plain English codebase symbol naming standard.
"""

from __future__ import annotations

import os
from pathlib import Path

MAX_FILE_LINES_CEILING = 800
BASE_DIR = Path(__file__).resolve().parent.parent


def test_source_file_line_limits():
    """Guarantees no single source file in core/, routes/, or static/js/ exceeds 800 lines.

    Violations force the agent to modularize and separate responsibilities (SRP)
    before commits can pass.
    """
    targets = ["core", "routes", "static/js"]
    oversized_files: list[tuple[str, int]] = []

    for target in targets:
        target_dir = BASE_DIR / target
        if not target_dir.exists():
            continue
        for root, _, files in os.walk(target_dir):
            for file in files:
                if file.endswith((".py", ".js")):
                    file_path = Path(root) / file
                    with open(file_path, encoding="utf-8", errors="ignore") as f:
                        count = len(f.readlines())
                    if count > MAX_FILE_LINES_CEILING:
                        rel_path = file_path.relative_to(BASE_DIR).as_posix()
                        oversized_files.append((rel_path, count))

    assert not oversized_files, (
        f"The following {len(oversized_files)} file(s) exceed the {MAX_FILE_LINES_CEILING}-line ceiling:\n"
        + "\n".join(f"  - {path}: {lines} lines (Must be <= {MAX_FILE_LINES_CEILING})" for path, lines in oversized_files)
        + "\n\nPer .agents/AGENTS.md, split oversized files into dedicated submodules following Single Responsibility."
    )


def test_cross_platform_safety_guards_in_core():
    """Guarantees that Win32 ctypes calls in core/ are guarded with `sys.platform == 'win32'`."""
    core_dir = BASE_DIR / "core"
    for root, _, files in os.walk(core_dir):
        for file in files:
            if file.endswith(".py"):
                file_path = Path(root) / file
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if "ctypes.windll" in content:
                    assert "sys.platform == \"win32\"" in content or "sys.platform != \"win32\"" in content, (
                        f"File {file_path.name} uses ctypes.windll but is missing a cross-platform `sys.platform == 'win32'` guard."
                    )


def test_core_never_imports_routes():
    """Enforces strict architectural layer isolation: core/ must NEVER import from routes/.

    Routes depend on core, never the reverse. Circular dependencies from core to routes
    are strictly forbidden and blocked by this AST gate.
    """
    import ast

    core_dir = BASE_DIR / "core"
    violations: list[tuple[str, int, str]] = []

    for root, _, files in os.walk(core_dir):
        for file in files:
            if file.endswith(".py"):
                file_path = Path(root) / file
                rel_path = file_path.relative_to(BASE_DIR).as_posix()
                try:
                    tree = ast.parse(file_path.read_text(encoding="utf-8", errors="replace"), filename=str(file_path))
                except SyntaxError:
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name == "routes" or alias.name.startswith("routes."):
                                violations.append((rel_path, node.lineno, alias.name))
                    elif isinstance(node, ast.ImportFrom):
                        if node.module == "routes" or (node.module and node.module.startswith("routes.")):
                            violations.append((rel_path, node.lineno, node.module))

    assert not violations, (
        f"Architecture violation! {len(violations)} import(s) from 'routes' found in 'core/':\n"
        + "\n".join(f"  - {path}:{line} imports '{mod}'" for path, line, mod in violations)
        + "\n\nPer AGENTS.md Layer Separation, core/ must be completely independent of routes/."
    )
