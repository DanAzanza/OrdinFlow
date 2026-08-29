# OrdinFlow Domain & Runtime Knowledge Base

> **Rule**: This repository knowledge base serves strictly as persistent memory for **non-obvious runtime quirks, hardware/model constraints, and hidden system behaviors** that cannot be inferred from reading source code, function signatures, or docstrings alone. Do NOT document standard component mappings, obvious file listings, or generic code patterns here.

---

## 1. Hardware, Model & OS Constraints

### 🎯 Vision Model (Qwen2.5-VL / Qwen3-VL) 28px Patch Alignment
* **Constraint**: Vision transformers use a $14\times14$ patch grid with $2\times2$ spatial pooling $\rightarrow$ effective token unit is **$28\times28$ pixels**.
* **Rule**: All screen crops, quadrant slices, and region bounding boxes MUST be rounded down to exact multiples of **28 pixels** (`(val // 28) * 28`) to eliminate token padding waste and bilinear interpolation blur.

### 🖥️ Windows Sandbox Subshell Isolation vs. Physical Desktop
* **Constraint**: Subshells on Windows run in an isolated virtual desktop station (`exebox-...`), not in the interactive user desktop (`WinSta0\Default`).
* **Rule**: Native OS GUI automation (`pynput`, `pyautogui`, `BitBlt`) executed in subshells targets the sandbox desktop and is NOT visible on the user's screen. Never claim a physical window was interacted with unless using Chrome DevTools MCP on the live browser.

### 📐 Multi-Monitor Virtual Coordinate Space & DPI
* **Constraint**: Secondary monitors positioned left/above the primary display have negative coordinate origins ($x_v < 0, y_v < 0$).
* **Rule**: Screen bounds use `SM_XVIRTUALSCREEN` (76) / `SM_YVIRTUALSCREEN` (77). Target element clicks must add `origin_x` and `origin_y` offsets. Per-Monitor V2 DPI awareness (`-4`) must be set before GDI `BitBlt` captures.

### 📋 Win64 Ctypes Pointer Truncation & Clipboard Yield Delay
* **Constraint**: 64-bit Python defaults `ctypes` returns to 32-bit `c_int`, causing access violations (`0xc0000005`) on pointers.
* **Rule**: All memory handles/pointers (`GlobalAlloc`, `GetClipboardData`, etc.) MUST set `restype = ctypes.c_void_p`. When pasting via `Ctrl+V`, enforce an **80ms yield delay** (`time.sleep(0.08)`) to allow the target app message pump to process `WM_PASTE` before restoring clipboard data.

### ⚡ 4096 VRAM Context Budget on ~4GB APUs/GPUs
* **Constraint**: To run on 4GB consumer GPUs/APUs without `VK_ERROR_OUT_OF_DEVICE_MEMORY`, the combined prompt + vision token budget must not exceed 4096 (1,850 text + 2,052 image tokens max).
* **Rule**: Vision tier dimensions scale in $+140\text{ px}$ increments ($1232\text{ px} \to 1372\text{ px} \to 1512\text{ px}$). Offload layers step down `[-1, 20, 10, 5, 0]` to leave $\approx 1\text{ GB}$ VRAM headroom for the `mmproj` vision forward pass.

### 📂 Windows Explorer Transient Lock Resilience
* **Constraint**: Windows Explorer thumbnailers and antivirus scanners hold transient read locks on newly created/moved folders, raising `PermissionError` [WinError 5 / 32].
* **Rule**: Wrap directory renames/moves in `_safe_rename_dir` with exponential backoff retry.

---

## 2. Verification Commands & Quality Gates

* **Iterative Development (Code changes only)**:
  ```bash
  python -m pytest -q
  ```
  *(Run ONLY when `.py`/`.js` code changed. Never run Ruff or Pyright during iterative steps).*

* **Pre-Commit Quality Gate (Triggered strictly on explicit user commit request)**:
  ```bash
  python scripts/verify_ci.py
  ```
  *(Runs Ruff linter, Pyright type checker on `core/` and `routes/`, and full test suite).*

---

## 3. Specialized Multi-Agent Quality Subagents

* **`plan_critic` ("Grill Me" Sparring Panel)**: Multi-perspective architectural reviewer before writing implementation plans. Actively attacks assumptions, validates against real codebase APIs, and enforces KISS/YAGNI.
* **`pre_commit_auditor` ("Grill Me" Code & Goal Auditor)**: Adversarial auditor before commit approval. Scrutinizes `git diff` against Plan Fidelity (no cut corners) and `AGENTS.md` standards (zero placeholders, cross-platform guards, SRP limits).
