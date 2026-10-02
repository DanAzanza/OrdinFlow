# OrdinFlow Domain & Runtime Knowledge Base

> **Rule**: This repository knowledge base serves strictly as persistent memory for **non-obvious runtime quirks, hardware/model constraints, and hidden system behaviors** that cannot be inferred from reading source code, function signatures, or docstrings alone. Do NOT document standard component mappings, obvious file listings, or generic code patterns here.

---

## 1. Central Pre-Commit Verification Gate

The central verification script required by `AGENTS.md` Section 8:
```bash
python scripts/verify_ci.py
```
*(Deterministically runs Ruff linter, Pyright static type checker across `core/` and `routes/`, and the complete test suite).*

---

## 2. Git Commit Scope Mapping

Repository-specific component scopes required by `AGENTS.md` Section 6:
* `[Core]`: Core document processor, triage engine, domain models, filesystem service (`core/`).
* `[Vision]`: Vision backends (Qwen3-VL), 28px patch scaling, image preprocessing (`core/vision.py`, `core/image_processing.py`, `models/`).
* `[RPA]`: Windows UI automation, Win32 UIA locators, GDI screen captures (`core/skills/engines/export_engine.py`, `core/skills/uia_locator.py`, `core/skills/grounder.py`).
* `[Skills]`: Skill recorder, queue dispatcher, models, loop execution (`core/skills/`).
* `[API]`: Flask REST endpoints, request/response validation schemas (`routes/api/`, `routes/schemas.py`).
* `[UI]`: Web dashboard, frontend JS modules, CSS styling (`templates/`, `static/`, `routes/ui.py`).
* `[CI]`: Quality gate scripts, build pipelines, release automation (`scripts/`, `.github/`).

---

## 3. Hardware, Model & OS Constraints

### 🎯 Qwen Vision Model 28px Patch Alignment
* **Constraint**: Vision transformers (Qwen2.5-VL / Qwen3-VL) use a $14\times14$ patch grid with $2\times2$ spatial pooling $\rightarrow$ effective token unit is **$28\times28$ pixels**.
* **Quirk**: Screen crops, quadrant slices, and region bounding boxes in `SoMGrounder` must be rounded down to exact multiples of **28 pixels** (`(val // 28) * 28`) to eliminate token padding waste and bilinear interpolation blur during model downscaling.

### 🖥️ Windows Sandbox Subshell Isolation vs. Physical Desktop
* **Constraint**: Subshells on Windows run in an isolated virtual desktop station (`exebox-...`), not in the interactive user desktop (`WinSta0\Default`).
* **Quirk**: Native OS GUI automation (`pynput`, `pyautogui`, `BitBlt`) executed in subshells targets the sandbox desktop and is NOT visible on the user's screen. Never claim a physical window was interacted with unless using Chrome DevTools MCP on the live browser.

### 📐 Multi-Monitor Virtual Coordinate Space & DPI
* **Constraint**: Secondary monitors positioned left/above the primary display have negative coordinate origins ($x_v < 0, y_v < 0$).
* **Quirk**: Screen bounds use `SM_XVIRTUALSCREEN` (76) / `SM_YVIRTUALSCREEN` (77). Target element clicks must add `origin_x` and `origin_y` offsets. Per-Monitor V2 DPI awareness (`-4`) must be set before GDI `BitBlt` captures.

### 📋 Win64 Ctypes Pointer Truncation & Clipboard Yield Delay
* **Constraint**: 64-bit Python defaults `ctypes` returns to 32-bit `c_int`, causing access violations (`0xc0000005`) on pointers.
* **Quirk**: All memory handles/pointers (`GlobalAlloc`, `GetClipboardData`, etc.) MUST set `restype = ctypes.c_void_p`. When pasting via `Ctrl+V`, enforce an **80ms yield delay** (`time.sleep(0.08)`) to allow the target app message pump to process `WM_PASTE` before restoring clipboard data.

### 🪟 Win32 GDI 10,000 Handle Quota
* **Constraint**: Windows enforces a hard quota of 10,000 GDI handles per process.
* **Quirk**: Device Contexts and Bitmaps (`DeleteDC`, `ReleaseDC`, `DeleteObject`) must be deterministically released in `finally` blocks immediately following `BitBlt` captures. Leaking GDI handles causes silent `BitBlt` failures (`ERROR_NO_MORE_USER_HANDLES`) during extended automation runs.

### ⚡ 4096 VRAM Context Budget on ~4GB APUs/GPUs
* **Constraint**: To run on 4GB consumer GPUs/APUs without `VK_ERROR_OUT_OF_DEVICE_MEMORY`, the combined prompt + vision token budget must stay $\le 4096$.
* **Quirk**: Vision dimensions scale in $+224\text{ px}$ increments ($896\text{ px} \to 1120\text{ px} \to 1344\text{ px} \to 1568\text{ px}$). Dynamic layer offloading steps down `[-1, 20, 10, 5, 0]` to leave $\approx 1\text{ GB}$ VRAM headroom for the `mmproj` vision forward pass.

### 📂 Transient File Lock Resilience (.meta Sidecars & Renames)
* **Constraint**: Windows Explorer thumbnailers, Windows Defender, Google Drive Desktop, and OneDrive hold transient read/write locks on newly created/moved files and sidecars, raising `PermissionError` [WinError 5 / 32].
* **Quirk**: File and directory moves must implement exponential backoff retry loops. Sidecar metadata updates (`.meta`) MUST write to a unique temporary file (`<path>.tmp_<pid>_<uuid>`), flush & close, and atomically swap using `os.replace()`.

### 🪟 Windows COM `IUIAutomation` MTA Threading & 64-bit HWND Wrapping
* **Constraint**: UI Automation COM interface (`UIAutomationCore.dll`) requires Multi-Threaded Apartment (MTA) initialization. Passing raw `int` handles to 64-bit COM methods causes pointer truncation and access violations. Passing invalid/hidden HWNDs (e.g. 0) raises `0x80040201` (`EVENT_E_ALL_SUBSCRIBERS_FAILED`).
* **Quirk**: Always initialize MTA COM (`CoInitializeEx(0, 0x0)`) before UIA tree traversal. Window handles passed to COM methods (e.g. `ElementFromHandle`) MUST be explicitly wrapped in `ctypes.c_void_p(hwnd)`.

---

## 4. Repository & Test Environment Contracts

### 📄 Sidecar `.meta` Lifecycle Contract
* **Constraint**: `.meta` sidecars are NOT created for successfully ingested and cleanly routed documents. Intuitively expecting `.meta` files on every document in `Cases/` causes false-positive test assertions and broken assumptions.
* **Contract**: In OrdinFlow, `.meta` sidecars exist strictly in two scenarios:
  1. **Quarantine / Review (`status: "review"`)**: Created by `FileService.mark_for_review` when classification fails, validation rules fail, or multi-page PDF splitting aborts due to incomplete page coverage.
  2. **Downstream RPA Export**: Updated by `CaseRouter.mark_file_skill_executed` during export tasks to track executed skills and timestamps.
  Never write tests or logic expecting `.meta` files alongside successfully ingested, cleanly routed documents.

### 🧪 Test Isolation on Gitignored Local Skills
* **Constraint**: `settings/skills/*.yaml` (except `*.example.yaml`) are user/environment-specific configuration files and are excluded from Git tracking via `.gitignore`.
* **Contract**: Automated test suites in `tests/` MUST NEVER assert the presence of local disk skill files (e.g. CorelDRAW or local practice workflows). All engine and UI tests must operate purely on in-memory fixtures or isolated temporary test directories (`temp_skills_dir`).

### 📄 0-Page Dummy PDF Trap in Test Fixtures
* **Constraint**: In `core/utils.py`, `wait_until_unlocked` checks structural readiness using `len(doc) > 0` via PyMuPDF (`fitz.open`).
* **Quirk**: Plain text strings (`"dummy content"`) or empty PDF headers (`b"%PDF-1.4\n%EOF\n"`) parse with `len(doc) == 0`. `wait_until_unlocked` assumes an external scanner is still streaming pages, retrying 5 times with a 1.0s sleep (5.0s per test!). Tests creating dummy PDFs must always use `tests.conftest.MINIMAL_1PAGE_PDF_BYTES` or the `create_test_pdf` fixture (`len(doc) >= 1`) to avoid false multi-second CI delays.

