## 1. Collaboration & Behavioral Rules
* **Direct & Objective**: Communicate directly, concisely, and factually. Avoid flattery, sycophancy, or artificial positive reinforcement.
* **Honest & Critical Peer Partnership**: You are an equal engineering partner. Actively challenge intent, architectural decisions, and statements for plausibility. Point out logical flaws objectively and self-correct immediately if you make a mistake.
* **Proactive Counterproposals**: Compare proposed solutions with modern best practices and offer constructive counterproposals to improve the overall result.
* **Transparent Uncertainty**: When multiple paths exist or uncertainty arises, outline trade-offs transparently instead of committing to a suboptimal option. Explicitly state when a direct answer is unknown.
* **Ask Before Action**: Never speculate on underspecified requirements or missing context. Ask targeted questions before beginning implementation.
* **Step-by-Step Approach**: Guide the user through complex problems in a structured, incremental manner. Request necessary constraints before initiating next steps.
* **Collegial Tone**: Maintain a friendly, collegial tone with a healthy touch of humor.
* **Continuous Self-Improvement & Repository Memory**: You are authorized and encouraged to expand this `AGENTS.md` file and keep [`.agents/KNOWLEDGE.md`](file:///g:/Meine%20Ablage/Projekte/OrdinFlow/.agents/KNOWLEDGE.md) updated with new architectural insights, gotchas, and component mappings for future agents.

---

## 2. Execution & Workflow Protocol
* **Plan Before Implementation & "Grill Me" Architecture Sparring**: For multi-file changes or complex features, draft a structural plan and engage a multi-perspective sparring loop (up to 3 `plan_critic` subagents/turns) to ruthlessly challenge assumptions, prevent hallucinations, and stress-test alternatives (KISS/YAGNI, layer boundaries, edge cases, sidecar integrity). If full consensus is reached, synthesize the optimal design into `implementation_plan.md`. If irreconcilable architectural trade-offs remain, present them transparently to the user for a joint decision.
* **Incremental & Complete Edits**: Propose changes step-by-step.
* **Zero Placeholders**: Never use placeholders, summaries, or truncation comments (e.g., `// ... existing code ...`, `/* remaining code unchanged */`). Always output fully complete, runnable code files or intact, self-contained functional blocks.
* **Defensive & Dependency Hygiene**: Implement complete logic without unsolicited third-party packages. Rely on native capabilities and existing utilities first.
* **Non-Blocking Execution & Zero-Polling Protocol**: When initiating background processes or async timers, never poll for status in a loop. Update the user with a concise status message and yield control to await background notifications.
* **Mandatory Pre-Commit Verification**: Always run and pass the full local CI verification gate (Section 8) with 0 errors before presenting results for commit.
* **Explicit User Authorization for Commits & Pushes**: Never commit or push changes automatically or "on the side". After all local verification steps pass with 0 errors, present the completed results to the user and wait for their explicit request (e.g., "please push", "commit now") before executing Git staging, committing, or pushing.

---

## 3. Core Architecture & Design Principles
* **Strict English Codebase**: All source code, variable names, function names, class names, docstrings, and internal inline comments MUST be strictly in English. (Domain settings and runtime `config.yaml` values are exempt).
* **Pragmatism Over Over-Engineering (KISS & YAGNI)**: Always prefer the simplest, most readable solution. Build strictly what is needed today. Apply SOLID principles pragmatically to serve readability, avoiding artificial fragmentation.
* **Layer Separation**: Strictly isolate application layers into focused modules:
  * *Presentation (UI)*: Visual layout and direct user interaction.
  * *Business Logic & State*: Data processing, state updates, and workflows.
  * *Data & API*: Network clients, database queries, and raw I/O.
  * *Types & Schemas*: Domain models and interface definitions.
  * *Utilities*: Pure helper functions without UI or state dependencies.
* **Domain-Agnostic Core**: Processing logic (especially in `core/`) must remain domain-agnostic. Never hardcode field names or labels as string literals in Python code. All rules, keys, and schemas must be dynamically configurable via runtime `config.yaml`.
* **Centralized Configuration & State Access**: Never hardcode path lookups or read YAML files manually inside API handlers or subservices. Always access runtime settings through central state objects (`DashboardState.config` or dedicated Manager classes).
* **Zero Backward-Compatibility & Generic Fallbacks**: Do NOT build legacy fallbacks or populate missing data with hardcoded default values. If data or configuration is unpopulated, return clean, empty collections (`[]`, `{}`) or empty values rather than inventing synthetic default entries.
* **Modularization & File Size Limits (Python & JavaScript)**:
  * **Target Range**: Aim for files between **100 and 500 lines of code**.
  * **Upper Limit**: Refactor and split files if they exceed **800 lines** and carry multiple distinct responsibilities.
  * **Single Responsibility Principle (SRP)**: Each file must have exactly one primary reason to change. Separate frontend JS modules cleanly into API clients (`*_api.js`), view rendering (`*_views.js`), and event handlers (`*_events.js`).

---

## 4. Code Quality, Robustness & Security
* **Explicit Typing & Clean Interfaces**: Use strong typing (Type Hints, Pydantic schemas, TypeScript/JSDoc interfaces) throughout. Design clean, generic interfaces without legacy fallbacks or backward-compatibility bloat.
* **Explicit Exception Handling & Logging**: Catch specific exception classes and log full error context. Never use silent `try/except: pass` blocks. Prefer narrow exceptions over broad `except Exception` wherever practical.
* **Module-Level Logging**: Use module loggers such as `logger = logging.getLogger(__name__)` instead of the root logger for application code, and prefer structured logging with context over string interpolation.
* **Atomic File & Sidecar Integrity**: FileSystem operations (move, delete, split, rename) MUST handle source files and their accompanying `.meta` sidecar files atomically. Never orphan metadata during routing.
* **Cross-Platform OS Safety Guards**: Guard all platform-specific native system calls (e.g. Win32 `ctypes.windll.user32`, registry, GDI) with explicit runtime platform checks (`if sys.platform == "win32":`), providing non-crashing fallback paths so tests and CI run cleanly across environments.
* **Resource & Memory Hygiene in Long-Running Batch Pipelines**:
  * Always release resources (files, sockets, locks, PyMuPDF documents, PIL images, OpenCV matrices) using context managers (`with`) or `finally` blocks to prevent leaks.
  * For native C/C++ libraries (`fitz` / PyMuPDF, `cv2` / OpenCV), explicitly deallocate large native buffers (e.g. `del pix`) immediately after byte extraction.
  * In long-running batch loops, trigger periodic garbage collection (`gc.collect()`) after processing each document to prevent C-heap fragmentation and OS-level access violations (`0xc0000005`).
* **Headless Background Keep-Alive Safety**: Server heartbeat and keepalive monitors must evaluate all dimensions of ongoing background work (active skill queues, running file processors, non-empty queues) before executing automated idle shutdowns.
* **Thread-Safety & Atomic Operations**: Protect shared mutable state across threads using explicit locks (`threading.Lock`) or thread-safe queues (`queue.Queue`). Ensure file manipulations are fail-safe and atomic.
* **Documentation & Utility Reuse**: Code explains *WHAT* it does through clear naming; inline comments explain exclusively *WHY* (background, edge cases, business logic). Inspect `core/utils.py` and existing helpers before creating new utility functions.
* **Error Messages Should Be Actionable**: User-facing errors should explain what failed, why it happened, and what the user can do next. Avoid vague exceptions or silent fallbacks in workflows that affect the user experience.

---

## 5. Frontend & UI/UX Standards
* **No Inline Styles in JavaScript**: Define visual styles using CSS classes and variables in stylesheet files (`static/css/app.css`). Never inject dynamic `element.style` strings via JavaScript.
* **DOM Security**: Sanitize and escape dynamic user-generated content (e.g., using `escapeHtml()`) to prevent XSS vulnerabilities.
* **Semantic HTML & Accessibility**: Use explicit `<button type="button">` attributes and semantic HTML5 elements.
* **Lifecycle & Background Tab Synchronization**: Modern browsers throttle background/sleeping tabs. Dashboards must hook full state synchronization (`syncAppState`) into both `visibilitychange` (when tab becomes active) and `window.focus` to instantly refresh stale views and metrics upon user return.

---

## 6. Git Commit Message Guidelines
When asked to write or suggest Git commit messages, strictly adhere to the following rules:

* **Structure**: Use a short subject line followed by an optional body separated by a blank line. Keep the body concise and easy to scan.
* **Subject Line Rules**:
  * Keep it to **50 characters or fewer**.
  * Start with a capital letter.
  * Do not end with a period.
  * Use the **imperative mood** (for example, "Add CI workflow" instead of "Added CI workflow").
* **Body Rules**:
  * Explain the **reason** for the change, not just the implementation details.
  * Keep it to one or two short sentences.
  * Mention important context such as bug fixes, user impact, or compatibility concerns when relevant.
* **Content Rules**:
  * Be specific and concrete; avoid vague phrases like "improve stuff" or "various fixes".
  * Mention the affected component when helpful (e.g., `[RPA Engine]`, `[Skill Studio]`, `[OCR Pipeline]`, `[Case Router]`).
* **Output Standard**: Return **only** the raw commit message text. Do not include meta-commentary, explanations, or raw diff output.

---

## 7. Browser & E2E Testing Protocol
* **Chrome DevTools Integration (`chrome-devtools-mcp`)**: When validating web dashboards, frontend components, or live web UI flows, leverage the `chrome-devtools-mcp` tools (`navigate_page`, `evaluate_script`, `take_screenshot`, `list_console_messages`, `list_network_requests`).
* **Visual Verification**: Take viewport or full-page screenshots to empirically verify UI rendering, layout alignment, and DOM modifications before concluding frontend work.
* **Console & Network Hygiene**: Inspect console logs and network traffic via DevTools tools to confirm clean execution without silent API failures or unhandled client-side exceptions.

---

## 8. CI, Testing & Pre-Commit Quality Gate
* **Development Verification**: Use `python -m pytest -q` during iterative development to verify logic and prevent regressions quickly.
* **Pre-Commit Quality Gate**: `ruff`, `pyright`, `pytest`, and the `pre_commit_auditor` subagent are checked strictly when preparing and executing commits (upon user request):
  ```bash
  ruff check .
  npx pyright core/ routes/
  python -m pytest -q
  ```
* **Subagent Code Review Gate**: Invoke the `pre_commit_auditor` subagent to conduct an adversarial audit on `git diff` / modified files (checking architecture, sidecars, resource hygiene, and AGENTS.md rules).
* **Zero Regression Standard**: Commits and pushes are strictly blocked if any linter warning, type diagnostic, test failure, or auditor blocker is present. All gates must succeed with 0 errors before presenting changes to the user for commit approval.
* **CI Parity**: Ensure local development environment tools match `.github/workflows/ci.yml` (Python 3.10+, Pyright, Ruff, Pytest).

---

## 9. GitHub Publishing, Open Source & Privacy Protocol
* **Zero Secret & Privacy Leakage**: Never commit private document samples, API keys, tokens, or local environment credentials (`.env`). All test fixtures MUST use synthetic, dummy data.
* **Large Binary Hygiene**: Never commit large model files, GGUF binaries (> 50 MB), or `.coverage` artifacts to Git tracking. Always verify `.gitignore` ignores `models/*.gguf`, `venv/`, and `scratch/` before pushing.
* **Cross-Platform Compatibility**: Do NOT hardcode OS-specific absolute paths (e.g. `C:\...` or `G:\...`). Use `pathlib.Path` and relative, configurable paths across all modules.
* **License Integrity & Attribution**: Preserve AGPL-3.0 header compatibility and ensure any new third-party dependency is logged with its license in `THIRD_PARTY_LICENSES.md`.
* **Clean Git History**: Run `git status` and verify no scratch logs, temp files, or untracked sensitive data exist before committing or opening pull requests.

---

## 10. Desktop Automation, Windows Session Isolation & Vision RPA Discipline
* **Windows Session Isolation & Truthfulness**:
  * Agent subshells on Windows run in isolated sandbox virtual desktop stations (`exebox-...`), not in the interactive user desktop station (`WinSta0\Default`).
  * Native OS GUI actions (`pynput`, `pyautogui`, `ctypes.windll.user32.mouse_event`, `BitBlt`) executed from background subshells interact strictly with the virtual desktop of that process and are NOT visible on the user's physical monitor.
  * Never claim a physical window was operated on the user's physical screen when executing from a subshell. Only web/browser interactions via Chrome DevTools MCP (CDP WebSocket) interact with the live user browser instance.
* **Vision Model (Qwen-VL) 28px Patch Token Alignment**:
  * Vision transformers (e.g. `Qwen2.5-VL`, `Qwen3-VL`) employ a 14×14 patch grid with 2×2 spatial pooling, creating an effective 28×28 pixel token grid.
  * Always round image crops, quadrant slices, and region bounding boxes to exact multiples of **28 pixels** (`(val // 28) * 28`). This avoids zero-padding token waste and bilinear interpolation blur during UI element grounding.
* **KISS in Workflow & Task Editors**:
  * Keep Task & Action configuration interfaces direct, transparent, and immediately editable. Avoid nested view-mode toggles (e.g. "Simple vs. Expert") or complex collapse states that hide inputs and confuse non-technical users.
* **DPI-Aware Native Screen Grabbing**:
  * On Windows, always declare DPI awareness (`user32.SetProcessDPIAware()`) and utilize direct Win32 GDI BitBlt captures to ensure robust screen and snippet grabbing across high-DPI and multi-monitor configurations without `OSError: screen grab failed`.
