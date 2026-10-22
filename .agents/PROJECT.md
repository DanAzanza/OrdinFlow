# OrdinFlow Project Architecture & Operational Knowledge Base

> **Rule**: Authoritative project memory for **architecture, operational contracts, verification commands, commit scopes, security boundaries, and domain invariants**.

---

## 1. Quality Gate & Commit Scopes
* **CI Verification**: `python scripts/verify_ci.py` (Ruff, Pyright across `core/` and `routes/`, full pytest suite).
* **Commit Scopes**: `[Core]`, `[Vision]`, `[RPA]`, `[Skills]`, `[API]`, `[UI]`, `[CI]`.
* **Subagent Roles**: `plan_critic` (Architecture sparring), `pre_commit_auditor` (Pre-commit diff audit).

---

## 2. Extraction & Vision Pipeline Invariants

### 📄 Single-Customer-Per-PDF Field Pooling Invariant
* In OrdinFlow, a single input PDF ALWAYS belongs to a single customer/patient/case, even when it contains multiple document types (e.g. Page 1 is `Arztbrief` and Page 2 is `Rezept` or `Laborbefund`).
* All extracted metadata fields across all pages of that PDF MUST be pooled and voted on together into a single shared PDF-wide consensus pool (via `ExtractionPipeline` / `_evaluate_round`), while only the `Document` type (`doc_type`) remains specific to each split document group when routing and saving sub-PDFs.
* Field schemas are unioned across all detected document types in the PDF so every relevant field is extracted and pooled across all non-empty pages, ensuring all split sub-documents inherit complete customer metadata (such as `Nachname`, `Vorname`, `Geburtsdatum`) and route into the exact same case folder.
* Do not isolate field voting per document type within the same PDF: cross-page pooling significantly improves statistical consensus and prevents split sub-documents from routing into separate or incomplete folders. Sub-document signature checks (`Signed`) remain isolated per split group.

### 📄 Empty-Page Multi-Document Split & Pre-Flight Coverage Trap
* **Strikter Pre-Flight Page Coverage Check**: `FileService.split_multi_page_pdf` erzwingt vor dem Zerschneiden eines PDFs, dass *alle* physischen Seiten des Eingabedokuments in `page_results` abgedeckt sind (`uncovered_pages = total_doc_pages - covered_pages`), um Datenverlust zu verhindern.
* **LEER-Seiten-Accounting**: Auch wenn `save_empty_pages=False` konfiguriert ist, müssen leere Seiten in `page_results` als `{"Document": "LEER", "pages": [...]}` aufgeführt bleiben. `split_multi_page_pdf` verwirft sie beim Erzeugen der Teil-PDFs automatisch. Fehlen sie jedoch in `page_results`, schlägt der Pre-Flight-Check fehl und das Dokument landet fälschlicherweise in der manuellen Prüfung.
* **Entkopplung von Split-Entscheidung und Filterung**: Der Multi-Document-Split darf erst ab mindestens zwei **nicht-leeren** Dokumentgruppen auslösen (`len([pr for pr in page_results if pr.get("Document") not in ("LEER", "BLANK")]) > 1`). Bei einem Einzeldokument mit zwischengehefteter Leerseite (z. B. Seite 1 `Vertrag`, Seite 2 `LEER`, Seite 3 `Vertrag`) verhindert dies das versehentliche Zerschneiden in zwei separate Verträge und leitet das PDF stattdessen an `save_filtered_pdf` weiter, um die Leerseite sauber zu entfernen.

### 📄 Sidecar `.meta` Lifecycle Trap
* `.meta` sidecars are NOT created for clean ingestions. They exist strictly for:
  1. **Quarantine / Review (`status: "review"`)**: Failed classification, broken validation, incomplete page splitting.
  2. **Downstream RPA Export**: Execution timestamps written by `core.skills.case_router.mark_file_skill_executed`.
* Never write tests or code expecting `.meta` files for clean, routed documents.

### ⏱️ Dependent Document Context Boundary (`last_context`)
* When routing multi-page or dependent medical records (e.g. lab annexes following a primary doctor letter), `last_context` inheritance is strictly bounded:
  1. Maximum age limit: **60 seconds** (1 minute).
  2. Spatial scope: Same parent directory.
* Context must never leak across separate folders, patient batches, or restart boundaries.
* Inherited fields are transparently tracked in `.meta` (`inherited_fields`, `inherited_from`). Config option `review_on_inheritance: true` routes documents to human review if fields were inherited.

---

## 3. Security, Multi-User & Compliance Contracts

### 🔒 Windows Terminal Server / Citrix Threat Model (`127.0.0.1:8080`)
* OrdinFlow target deployments include medical practices and legal offices on shared Windows Terminal Server / Citrix RDS hosts.
* On shared terminal servers, all concurrently logged-in users share `localhost` (`127.0.0.1`). Unauthenticated endpoints or fail-open token logic allow other local OS users to read patient files or inject skills.
* Every mutating endpoint and SSE event stream (`/api/events`) requires authentication via `X-OrdinFlow-Token` or `?token=...`. Test bypass headers (`X-OrdinFlow-Test-Bypass`) are strictly forbidden in production routes.

### 🛡️ Medical PII Logging Policy (§ 203 StGB, DSGVO / GDPR)
* Medical documentation requires strict minimization. `core/processor.py` and downstream routers must NEVER log raw extracted JSON payloads (patient names, dates of birth, diagnoses) at `INFO` level.
* Production logs at `INFO` or above are restricted to operational metadata (document IDs, classification labels, latency, destination folder). Raw extracted fields are only permissible in local developer `DEBUG` logs.

### 📜 PowerShell Skill Execution Contract
* `core/skills/script_runner.py` passes extracted document values to PowerShell.
* Document values (names, case IDs) originate from untrusted OCR/VLM output and must NEVER be interpolated into command strings via string formatting/replace or blocklist escaping.
* Values are injected strictly via `$env:ORDINFLOW_<KEY>` process environment variables (or `%ORDINFLOW_<KEY>%` for cmd.exe), bounded at 8192 characters. PowerShell scripts consume `$env:ORDINFLOW_*` directly.

### 🛡️ Allowed Roots Security Boundary in File Exports
* `export_case_to_gdt` and export actions enforce `is_within_allowed_roots(path)` to prevent rogue file writes across the filesystem.
* Test fixtures or export configurations must reside within configured target roots or temporary directories (`tempfile.TemporaryDirectory()`). Arbitrary paths fail closed with permission errors.

### 🌐 Iframe Auth & URL Hash Fragment Security
* Endpoints like `/api/file/...` and `/api/preview/...` enforce strict token validation.
* In browser iframes, appending `?token=...` after a URL hash fragment (e.g. `/api/file/...#toolbar=0?token=...`) breaks RFC 3986 parsing: browsers interpret parameters after `#` as client-side fragments and strip them before HTTP transmission, causing 403 Forbidden responses.
* Frontend helper `withAuthToken(url)` must split URLs at `#`, append `?token=...` to the pathname/search query, and preserve the `#fragment` at the end.
* Backend authentication uses `secrets.compare_digest` with explicit `isinstance(token, str)` checking to prevent timing attacks and type confusion.

### 🗂️ Flask `<path:folder>` vs `<folder>` in Nested Case Routes
* Case directories can be organized into hierarchical subfolders (e.g. `2026/Dr_Mueller_Hans`).
* REST routes targeting cases (e.g. `/api/file/meta/cases/<path:folder>/<filename>`) must use Flask's `<path:folder>` converter rather than default `<folder>`, which breaks on `/` and causes silent 404s. Directory containment security is strictly enforced downstream via `_resolve_and_guard`.

---

## 4. Repository & Testing Conventions

### 🌐 German Domain & Terminology Exemption
* In OrdinFlow, German medical terms (Arztbriefe, Befunde, patient metadata) and runtime YAML configuration values in `settings/` (`"Privat"`, `"Kasse"`, `"Abgerechnet"`) are strictly exempt from English-only naming. Never translate domain concepts.

### 🧪 Test Isolation on Gitignored Local Skills
* `settings/skills/*.yaml` (except `*.example.yaml`) are gitignored practice configs. Automated tests in `tests/` must NEVER assert local disk skills; use in-memory fixtures or `temp_skills_dir`.

### 📄 0-Page Dummy PDF Trap in Test Fixtures
* `wait_until_unlocked` in `core/utils.py` checks `len(doc) > 0` and retries up to 6 times with 0.5s delay when `len(doc) == 0`. Dummy PDF test fixtures must always contain $\ge 1$ page (`MINIMAL_1PAGE_PDF_BYTES`) to avoid 2.5s CI delays per test.
