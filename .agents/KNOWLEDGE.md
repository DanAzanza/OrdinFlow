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

### 🪟 Windows 8.3 Short Path Trap (`RUNNER~1` vs. `runneradmin`)
* On Windows environments with usernames > 8 chars (e.g. GitHub Actions `runneradmin`), `tempfile.mkdtemp()` returns 8.3 short paths (`RUNNER~1`), whereas `Path(...).resolve()` expands to canonical long paths (`runneradmin`).
* Raw string comparisons (`p in set` or `p in list`) fail across short/long paths. Test fixtures must normalize tempdirs with `Path(tempfile.mkdtemp(...)).resolve()`, and path membership checks should resolve via `Path(p).resolve()`.

---

## 4. Multi-User & Runtime Security Contracts

### 🔒 Windows Terminal Server / Citrix Threat Model (`127.0.0.1:8080`)
* OrdinFlow target deployments include medical practices and legal offices on shared Windows Terminal Server / Citrix RDS hosts.
* On shared terminal servers, all concurrently logged-in users share `localhost` (`127.0.0.1`). Unauthenticated endpoints or fail-open token logic allow other local OS users to read patient files or inject skills.
* Every mutating endpoint and SSE event stream (`/api/events`) requires authentication via `X-OrdinFlow-Token` or `?token=...`. Test bypass headers (`X-OrdinFlow-Test-Bypass`) are strictly forbidden in production routes.

### 🛡️ Medical PII Logging Policy (§ 203 StGB, DSGVO / GDPR)
* Medical documentation requires strict minimization. `core/processor.py` and downstream routers must NEVER log raw extracted JSON payloads (patient names, dates of birth, diagnoses) at `INFO` level.
* Production logs at `INFO` or above are restricted to operational metadata (document IDs, classification labels, latency, destination folder). Raw extracted fields are only permissible in local developer `DEBUG` logs.

### ⏱️ Dependent Document Context Boundary (`last_context`)
* When routing multi-page or dependent medical records (e.g. lab annexes following a primary doctor letter), `last_context` inheritance is strictly bounded:
  1. Maximum age limit: **300 seconds** (5 minutes).
  2. Spatial scope: Same parent directory.
* Context must never leak across separate folders, patient batches, or restart boundaries.

### 📜 PowerShell Skill Execution Contract
* `core/skills/script_runner.py` passes extracted document values to PowerShell.
* Document values (names, case IDs) originate from untrusted OCR/VLM output and must NEVER be interpolated into command strings via string formatting/replace.
* Values are injected strictly via `$env:ORDINFLOW_<KEY>` process environment variables. PowerShell scripts consume `$env:ORDINFLOW_*` directly.

---

## 5. Medical PVS & RPA Integration Quirks

### 🏥 German PVS GDT 2.1 / 3.0 Parser Quirks & Watcher Races
* **Strict Byte Length vs. Char Length**: GDT lines follow `LLLLFFFFDDDD...\r\n`. `LLLL` is the byte count of the whole line including `LLLL` itself and `\r\n` (`len(data) + 10`). In CP437 byte count equals char count, but byte measurements must always occur *after* encoding to prevent buffer overflows in legacy PVS.
* **Deterministic Tag 8100 Fixed Width**: Tag 8100 (total file length in bytes) must be formatted as fixed 18 bytes (`00188100%08d\r\n`). Variable-width length formatting triggers iterative circular length recalculations.
* **70-Character Line Limit**: Legacy DOS/Windows PVS parsers (Medistar, TurboMed, Albis) truncate or crash if Tag 6220 (Befund) exceeds 70 characters. Free text must be word-wrapped into consecutive 6220 tags.
* **Directory Watcher Ingestion Race**: PVS directory watchers scan folders continuously and ingest incomplete files if written directly. Exports must write to `.gdt.tmp`, call `os.fsync()`, and atomically swap via `os.replace()`. Optional semaphore trigger files (`.sem` / `.ok`) must be written strictly *after* the `.gdt` rename.

### 🛡️ Win32 RPA Focus Guard, Modal Hierarchies & Lock Screens
* **Modal Child Hierarchy (`GA_ROOTOWNER`)**: Strict window title matching fails when target apps open modal file dialogs ("Speichern unter..."). The focus guard must inspect `GetAncestor(hwnd, GA_ROOTOWNER)` and match the target PID (`GetWindowThreadProcessId`) to permit legitimate modal child dialogs while blocking focus theft by unrelated foreground apps.
* **Detached Desktop / Lock Screen**: When Windows is locked (`LockApp.exe`, `LogonUI.exe`) or screen saver is active, `GetForegroundWindow()` returns 0 or the lock screen handle. Keystroke simulation must fail-closed immediately to avoid typing sensitive data into login screens or failing silently.
* **PII Clipboard Sanitization**: Pasting patient metadata via clipboard requires explicitly clearing the Win32 clipboard (`EmptyClipboard()`) in `finally` blocks to prevent sensitive patient data from leaking into Windows Clipboard History (`Win+V`).

