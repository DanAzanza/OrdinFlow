# OrdinFlow Domain & Runtime Knowledge Base

> **Rule**: Persistent memory strictly for **non-obvious runtime quirks, hardware/model constraints, and hidden system behaviors** that cannot be inferred from code, function signatures, or directory trees alone.

---

## 1. Quality Gate & Commit Scopes
* **CI Verification**: `python scripts/verify_ci.py` (Ruff, Pyright across `core/` and `routes/`, full pytest suite).
* **Commit Scopes**: `[Core]`, `[Vision]`, `[RPA]`, `[Skills]`, `[API]`, `[UI]`, `[CI]`.
* **Subagent Roles**: `plan_critic` (Architecture sparring), `pre_commit_auditor` (Pre-commit diff audit).

---

## 2. Hardware, Model & OS Constraints

### 🎯 Qwen Vision Model 28px Patch Alignment
* Vision transformers (Qwen2.5-VL / Qwen3-VL) use a $14\times14$ patch grid with $2\times2$ spatial pooling $\rightarrow$ unit size **$28\times28$ px**.
* Crops and bounding boxes in `SoMGrounder` must be floored to multiples of **28 px** (`(val // 28) * 28`) to eliminate padding tokens and interpolation blur.

### 🖥️ Windows Sandbox Subshell Isolation vs. Physical Desktop
* Subshells execute in an isolated window station (`exebox-...`), not the interactive user desktop (`WinSta0\Default`).
* Native OS GUI automation (`pynput`, `pyautogui`, `BitBlt`) in subshells targets the sandbox desktop and cannot touch the physical user screen. Use Chrome DevTools MCP for live browser inspection.

### 📐 Multi-Monitor Virtual Coordinate Space & DPI
* Secondary monitors left/above primary display have negative origins ($x_v < 0, y_v < 0$). Bounds require `SM_XVIRTUALSCREEN` (76) / `SM_YVIRTUALSCREEN` (77) offsets.
* Set Per-Monitor V2 DPI awareness (`-4`) before GDI `BitBlt` captures.

### 📋 Win64 Ctypes Pointer Truncation & Clipboard Yield Delay
* 64-bit Python defaults `ctypes` returns to 32-bit `c_int` (causes access violation `0xc0000005`). All memory handles must declare `restype = ctypes.c_void_p`.
* Pasting via `Ctrl+V` requires an **80ms yield delay** (`time.sleep(0.08)`) for target message pumps before restoring clipboard data.

### 🪟 Win32 GDI 10,000 Handle Quota
* Hard Windows quota: 10,000 GDI handles per process.
* Device Contexts and Bitmaps (`DeleteDC`, `ReleaseDC`, `DeleteObject`) must be deterministically released in `finally` blocks immediately after `BitBlt`. Leaks cause silent `ERROR_NO_MORE_USER_HANDLES`.

### ⚡ 4096 VRAM Budget on ~4GB APUs/GPUs
* Total prompt + vision token budget must stay $\le 4096$ to prevent `VK_ERROR_OUT_OF_DEVICE_MEMORY`.
* Vision scales in $+224\text{ px}$ steps. Layer offloading steps down `[-1, 20, 10, 5, 0]` to preserve $\approx 1\text{ GB}$ VRAM headroom for `mmproj`.

### 📂 Transient File Lock Resilience (.meta Sidecars & Renames)
* Windows Explorer, Defender, Google Drive, and OneDrive hold transient read/write locks (`PermissionError` [WinError 5 / 32]).
* File moves require exponential backoff retries. `.meta` updates must write to a unique temp file, flush, and atomically swap via `os.replace()`.

### 🪟 Windows COM `IUIAutomation` MTA Threading & 64-bit HWND
* UIA COM requires Multi-Threaded Apartment (`CoInitializeEx(0, 0x0)`).
* Window handles passed to COM methods must be explicitly wrapped in `ctypes.c_void_p(hwnd)`.

---

## 3. Repository & Domain Traps

### 📄 Sidecar `.meta` Lifecycle Trap
* `.meta` sidecars are NOT created for clean ingestions. They exist strictly for:
  1. **Quarantine / Review (`status: "review"`)**: Failed classification, broken validation, incomplete page splitting.
  2. **Downstream RPA Export**: Execution timestamps written by `CaseRouter.mark_file_skill_executed`.
* Never write tests or code expecting `.meta` files for clean, routed documents.

### 🧪 Test Isolation on Gitignored Local Skills
* `settings/skills/*.yaml` (except `*.example.yaml`) are gitignored practice configs. Automated tests in `tests/` must NEVER assert local disk skills; use in-memory fixtures or `temp_skills_dir`.

### 📄 0-Page Dummy PDF Trap in Test Fixtures
* `wait_until_unlocked` in `core/utils.py` retries 5 times with 1.0s sleep when `len(doc) == 0`. Dummy PDF test fixtures must always contain $\ge 1$ page (`MINIMAL_1PAGE_PDF_BYTES`) to avoid 5.0s CI delays per test.

### 🌐 German Domain & Terminology Exemption
* In OrdinFlow, German medical terms (Arztbriefe, Befunde, patient metadata) and runtime YAML configuration values in `settings/` (`"Privat"`, `"Kasse"`, `"Abgerechnet"`) are strictly exempt from English-only naming. Never translate domain concepts.

### 🔘 Frontend Button Type Trap (`<button type="button">`)
* HTML `<button>` defaults to `type="submit"`. In vanilla JS dialogs, unannotated buttons submit forms and reload pages. Non-submitting buttons must explicitly specify `type="button"`.
