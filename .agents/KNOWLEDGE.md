# OrdinFlow Domain & Runtime Knowledge Base

> **Rule**: Persistent memory strictly for **non-obvious runtime quirks, hardware/model constraints, and hidden system behaviors** that cannot be inferred from code, function signatures, or directory trees alone.

---

## 1. Extraction & Vision Pipeline

### 📄 Single-Customer-Per-PDF Field Pooling Invariant
* In OrdinFlow, a single input PDF ALWAYS belongs to a single customer/patient/case, even when it contains multiple document types (e.g. Page 1 is `Arztbrief` and Page 2 is `Rezept` or `Laborbefund`).
* All extracted metadata fields across all pages of that PDF MUST be pooled and voted on together into a single shared PDF-wide consensus pool (via `ExtractionPipeline` / `_evaluate_round`), while only the `Document` type (`doc_type`) remains specific to each split document group when routing and saving sub-PDFs.
* Field schemas are unioned across all detected document types in the PDF so every relevant field is extracted and pooled across all non-empty pages, ensuring all split sub-documents inherit complete customer metadata (such as `Nachname`, `Vorname`, `Geburtsdatum`) and route into the exact same case folder.
* Do not isolate field voting per document type within the same PDF: cross-page pooling significantly improves statistical consensus and prevents split sub-documents from routing into separate or incomplete folders. Sub-document signature checks (`Signed`) remain isolated per split group.

---

## 2. Quality Gate & Commit Scopes
* **CI Verification**: `python scripts/verify_ci.py` (Ruff, Pyright across `core/` and `routes/`, full pytest suite).
* **Commit Scopes**: `[Core]`, `[Vision]`, `[RPA]`, `[Skills]`, `[API]`, `[UI]`, `[CI]`.
* **Subagent Roles**: `plan_critic` (Architecture sparring), `pre_commit_auditor` (Pre-commit diff audit).

---

## 3. Hardware, Model & OS Constraints

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

## 4. Repository & Domain Traps

### 📄 Sidecar `.meta` Lifecycle Trap
* `.meta` sidecars are NOT created for clean ingestions. They exist strictly for:
  1. **Quarantine / Review (`status: "review"`)**: Failed classification, broken validation, incomplete page splitting.
  2. **Downstream RPA Export**: Execution timestamps written by `core.skills.case_router.mark_file_skill_executed`.
* Never write tests or code expecting `.meta` files for clean, routed documents.

### 🧪 Test Isolation on Gitignored Local Skills
* `settings/skills/*.yaml` (except `*.example.yaml`) are gitignored practice configs. Automated tests in `tests/` must NEVER assert local disk skills; use in-memory fixtures or `temp_skills_dir`.

### 📄 0-Page Dummy PDF Trap in Test Fixtures
* `wait_until_unlocked` in `core/utils.py` checks `len(doc) > 0` and retries up to 6 times with 0.5s delay when `len(doc) == 0`. Dummy PDF test fixtures must always contain $\ge 1$ page (`MINIMAL_1PAGE_PDF_BYTES`) to avoid 2.5s CI delays per test.

### 🌐 German Domain & Terminology Exemption
* In OrdinFlow, German medical terms (Arztbriefe, Befunde, patient metadata) and runtime YAML configuration values in `settings/` (`"Privat"`, `"Kasse"`, `"Abgerechnet"`) are strictly exempt from English-only naming. Never translate domain concepts.

### 🪟 Windows 8.3 Short Path Trap (`RUNNER~1` vs. `runneradmin`)
* On Windows environments with usernames > 8 chars (e.g. GitHub Actions `runneradmin`), `tempfile.mkdtemp()` returns 8.3 short paths (`RUNNER~1`), whereas `Path(...).resolve()` expands to canonical long paths (`runneradmin`).
* Raw string comparisons (`p in set` or `p in list`) fail across short/long paths. Test fixtures must normalize tempdirs with `Path(tempfile.mkdtemp(...)).resolve()`, and path membership checks should resolve via `Path(p).resolve()`.

### 🗂️ Flask `<path:folder>` vs `<folder>` in Nested Case Routes
* Case directories can be organized into hierarchical subfolders (e.g. `2026/Dr_Mueller_Hans`).
* REST routes targeting cases (e.g. `/api/file/meta/cases/<path:folder>/<filename>`) must use Flask's `<path:folder>` converter rather than default `<folder>`, which breaks on `/` and causes silent 404s. Directory containment security is strictly enforced downstream via `_resolve_and_guard`.

### 🛡️ Allowed Roots Security Boundary in File Exports
* `export_case_to_gdt` and export actions enforce `is_within_allowed_roots(path)` to prevent rogue file writes across the filesystem.
* Test fixtures or export configurations must reside within configured target roots or temporary directories (`tempfile.TemporaryDirectory()`). Arbitrary paths fail closed with permission errors.

### 📄 Empty-Page Multi-Document Split & Pre-Flight Coverage Trap
* **Strikter Pre-Flight Page Coverage Check**: `FileService.split_multi_page_pdf` erzwingt vor dem Zerschneiden eines PDFs, dass *alle* physischen Seiten des Eingabedokuments in `page_results` abgedeckt sind (`uncovered_pages = total_doc_pages - covered_pages`), um Datenverlust zu verhindern.
* **LEER-Seiten-Accounting**: Auch wenn `save_empty_pages=False` konfiguriert ist, müssen leere Seiten in `page_results` als `{"Document": "LEER", "pages": [...]}` aufgeführt bleiben. `split_multi_page_pdf` verwirft sie beim Erzeugen der Teil-PDFs automatisch. Fehlen sie jedoch in `page_results`, schlägt der Pre-Flight-Check fehl und das Dokument landet fälschlicherweise in der manuellen Prüfung.
* **Entkopplung von Split-Entscheidung und Filterung**: Der Multi-Document-Split darf erst ab mindestens zwei **nicht-leeren** Dokumentgruppen auslösen (`len([pr for pr in page_results if pr.get("Document") not in ("LEER", "BLANK")]) > 1`). Bei einem Einzeldokument mit zwischengehefteter Leerseite (z. B. Seite 1 `Vertrag`, Seite 2 `LEER`, Seite 3 `Vertrag`) verhindert dies das versehentliche Zerschneiden in zwei separate Verträge und leitet das PDF stattdessen an `save_filtered_pdf` weiter, um die Leerseite sauber zu entfernen.

---

## 5. Multi-User & Runtime Security Contracts

### 🔒 Windows Terminal Server / Citrix Threat Model (`127.0.0.1:8080`)
* OrdinFlow target deployments include medical practices and legal offices on shared Windows Terminal Server / Citrix RDS hosts.
* On shared terminal servers, all concurrently logged-in users share `localhost` (`127.0.0.1`). Unauthenticated endpoints or fail-open token logic allow other local OS users to read patient files or inject skills.
* Every mutating endpoint and SSE event stream (`/api/events`) requires authentication via `X-OrdinFlow-Token` or `?token=...`. Test bypass headers (`X-OrdinFlow-Test-Bypass`) are strictly forbidden in production routes.

### 🛡️ Medical PII Logging Policy (§ 203 StGB, DSGVO / GDPR)
* Medical documentation requires strict minimization. `core/processor.py` and downstream routers must NEVER log raw extracted JSON payloads (patient names, dates of birth, diagnoses) at `INFO` level.
* Production logs at `INFO` or above are restricted to operational metadata (document IDs, classification labels, latency, destination folder). Raw extracted fields are only permissible in local developer `DEBUG` logs.

### ⏱️ Dependent Document Context Boundary (`last_context`)
* When routing multi-page or dependent medical records (e.g. lab annexes following a primary doctor letter), `last_context` inheritance is strictly bounded:
  1. Maximum age limit: **60 seconds** (1 minute).
  2. Spatial scope: Same parent directory.
* Context must never leak across separate folders, patient batches, or restart boundaries.
* Inherited fields are transparently tracked in `.meta` (`inherited_fields`, `inherited_from`). Config option `review_on_inheritance: true` routes documents to human review if fields were inherited.

### 🌐 Iframe Auth & URL Hash Fragment Security
* Endpoints like `/api/file/...` and `/api/preview/...` enforce strict token validation.
* In browser iframes, appending `?token=...` after a URL hash fragment (e.g. `/api/file/...#toolbar=0?token=...`) breaks RFC 3986 parsing: browsers interpret parameters after `#` as client-side fragments and strip them before HTTP transmission, causing 403 Forbidden responses.
* Frontend helper `withAuthToken(url)` must split URLs at `#`, append `?token=...` to the pathname/search query, and preserve the `#fragment` at the end.
* Backend authentication uses `secrets.compare_digest` with explicit `isinstance(token, str)` checking to prevent timing attacks and type confusion.

### 📜 PowerShell Skill Execution Contract
* `core/skills/script_runner.py` passes extracted document values to PowerShell.
* Document values (names, case IDs) originate from untrusted OCR/VLM output and must NEVER be interpolated into command strings via string formatting/replace or blocklist escaping.
* Values are injected strictly via `$env:ORDINFLOW_<KEY>` process environment variables (or `%ORDINFLOW_<KEY>%` for cmd.exe), bounded at 8192 characters. PowerShell scripts consume `$env:ORDINFLOW_*` directly.

---

## 6. Medical PVS & RPA Integration Quirks

### 🏥 German PVS GDT 2.1 Parser Quirks & Watcher Races
* **Strict 3-Digit Byte Length Prefix (`LLL`)**: Standard GDT 2.1 lines follow `LLLFFFFDDDD...\r\n`. `LLL` is a 3-digit ASCII length (`len(data_bytes) + 9`), bounded at 999 bytes max. In CP437/ISO-8859-1 byte count equals char count, but byte measurements must always occur *after* encoding to prevent buffer overflows in legacy PVS.
* **Deterministic Tag 8100 (5-Digit File Length)**: Tag 8100 (total file length in bytes) is formatted as fixed 14 bytes (`0148100%05d\r\n`).
* **Satzart 6310 (Untersuchungsdaten übermitteln)**: OrdinFlow exports findings to PVS using Satzart 6310. Tag 8315 is Receiver (PVS), Tag 8316 is Sender (ORDINFLOW, max 8 chars), Tag 9206 is Character Set (2 = CP437, 3 = ISO-8859-1).
* **Fail-Fast Integrity**: Tag 3000 (Patienten-ID) is strictly required; missing patient IDs fail fast with `ValueError` rather than guessing generic IDs. Tag 3103 (Geburtsdatum) must be omitted if unparseable or absent—never synthesize current date into patient master data.
* **70-Character Line Limit**: Legacy DOS/Windows PVS parsers (Medistar, TurboMed, Albis) truncate or crash if Tag 6220 (Befund) exceeds 70 characters. Free text must be word-wrapped into consecutive 6220 tags.
* **Directory Watcher Ingestion Race**: PVS directory watchers scan folders continuously and ingest incomplete files if written directly. Exports must write to `.gdt.tmp`, call `os.fsync()`, and atomically swap via `os.replace()`. Optional semaphore trigger files (`.sem` / `.ok`) must be written strictly *after* the `.gdt` rename.

### 🛡️ Win32 RPA Focus Guard, Modal Hierarchies & Lock Screens
* **Modal Child Hierarchy (`GA_ROOTOWNER`)**: Strict window title matching fails when target apps open modal file dialogs ("Speichern unter..."). The focus guard must inspect `GetAncestor(hwnd, GA_ROOTOWNER)` and match the target PID (`GetWindowThreadProcessId`) to permit legitimate modal child dialogs while blocking focus theft by unrelated foreground apps.
* **Detached Desktop / Lock Screen**: When Windows is locked (`LockApp.exe`, `LogonUI.exe`) or screen saver is active, `GetForegroundWindow()` returns 0 or the lock screen handle. Keystroke simulation must fail-closed immediately to avoid typing sensitive data into login screens or failing silently.
* **PII Clipboard Sanitization**: Pasting patient metadata via clipboard requires explicitly clearing the Win32 clipboard (`EmptyClipboard()`) in `finally` blocks to prevent sensitive patient data from leaking into Windows Clipboard History (`Win+V`).

