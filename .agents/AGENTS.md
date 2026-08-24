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
* **Mandatory Architecture Sparring & "Grill Me" Gate (Zero-Exception Protocol)**:
  * **Strict Requirement**: Prior to writing or updating `implementation_plan.md` and requesting user feedback, the agent MUST ALWAYS execute an adversarial sparring loop with the `plan_critic` subagent.
  * **Automated Procedure (Never Wait for User Reminders)**:
    1. Define the `plan_critic` subagent via `define_subagent` (if not already defined in the conversation).
    2. Invoke `plan_critic` via `invoke_subagent` with a detailed architectural draft, explicit edge cases, platform considerations (Win32, Linux, macOS), and potential regression vectors.
    3. Evaluate the critique, address all high-risk findings, and synthesize the finalized, hardened design into `implementation_plan.md`.
    4. Only AFTER this subagent sparring is complete may the agent present the plan to the user for approval.
  * Presenting an `implementation_plan.md` or asking the user for plan approval without preceding `plan_critic` sparring is a direct protocol violation.
* **Incremental & Complete Edits**: Propose changes step-by-step.
* **Zero Placeholders**: Never use placeholders, summaries, or truncation comments (e.g., `// ... existing code ...`, `/* remaining code unchanged */`). Always output fully complete, runnable code files or intact, self-contained functional blocks.
* **Defensive & Dependency Hygiene**: Implement complete logic without unsolicited third-party packages. Rely on native capabilities and existing utilities first.
* **Non-Blocking Execution & Zero-Polling Protocol**: When initiating background processes or async timers, never poll for status in a loop. Update the user with a concise status message and yield control to await background notifications.
* **Task Verification Gate**: Run the automated test suite or repository CI verification script before presenting completed work or requesting user feedback.
* **Explicit User Authorization & Pre-Commit Protocol**: Never commit or push changes automatically or "on the side". Present results to the user and wait for their explicit request (e.g., "please push", "bitte committen"). Once authorized, execute the full Pre-Commit Quality Gate (Section 8: CI verification script and `pre_commit_auditor`) before creating the commit and pushing.

---

## 3. Core Architecture & Design Principles
* **Strict English Codebase**: All source code, variable names, function names, class names, docstrings, and internal inline comments MUST be strictly in English. (Domain settings and runtime configuration values are exempt).
* **Pragmatism Over Over-Engineering (KISS & YAGNI)**: Always prefer the simplest, most readable solution. Build strictly what is needed today. Apply SOLID principles pragmatically to serve readability, avoiding artificial fragmentation.
* **Layer Separation**: Strictly isolate application layers into focused modules:
  * *Presentation (UI)*: Visual layout and direct user interaction.
  * *Business Logic & State*: Data processing, state updates, and workflows.
  * *Data & API*: Network clients, database queries, and raw I/O.
  * *Types & Schemas*: Domain models and interface definitions.
  * *Utilities*: Pure helper functions without UI or state dependencies.
* **Centralized Configuration & State Access**: Never hardcode path lookups or read configuration files manually inside API handlers or subservices. Always access runtime settings through central state objects or dedicated configuration managers.
* **Zero Backward-Compatibility & Generic Fallbacks**: Do NOT build legacy fallbacks or populate missing data with hardcoded default values. If data or configuration is unpopulated, return clean, empty collections (`[]`, `{}`) or empty values rather than inventing synthetic default entries.
* **Modularization & File Size Limits**:
  * **Target Range**: Aim for files between **100 and 500 lines of code**.
  * **Upper Limit**: Refactor and split files if they exceed **800 lines** and carry multiple distinct responsibilities.
  * **Single Responsibility Principle (SRP)**: Each file must have exactly one primary reason to change. Separate frontend JS modules cleanly into API clients (`*_api.js`), view rendering (`*_views.js`), and event handlers (`*_events.js`).

---

## 4. Code Quality, Robustness & Security
* **Explicit Typing & Clean Interfaces**: Use strong typing (Type Hints, Pydantic schemas, TypeScript/JSDoc interfaces) throughout. Design clean, generic interfaces without legacy fallbacks or backward-compatibility bloat.
* **Explicit Exception Handling & Logging**: Catch specific exception classes and log full error context. Never use silent `try/except: pass` blocks. Prefer narrow exceptions over broad `except Exception` wherever practical.
* **Module-Level Logging**: Use module loggers such as `logger = logging.getLogger(__name__)` instead of the root logger for application code, and prefer structured logging with context over string interpolation.
* **Cross-Platform OS Safety Guards**: Guard all platform-specific native system calls (e.g. Win32 `ctypes.windll`, registry, GDI) with explicit runtime platform checks (`if sys.platform == "win32":`), providing non-crashing fallback paths so tests and CI run cleanly across environments.
* **Resource & Memory Hygiene**:
  * Always release resources (files, sockets, locks, database connections, native graphics buffers) using context managers (`with`) or `finally` blocks to prevent leaks.
  * In long-running batch pipelines, explicitly deallocate large native buffers and trigger periodic garbage collection (`gc.collect()`) after processing large files to prevent memory fragmentation and OS-level access violations.
* **Thread-Safety & Atomic Operations**: Protect shared mutable state across threads using explicit locks (`threading.Lock` / `threading.RLock`) or thread-safe queues. Ensure file manipulations are fail-safe and atomic.
* **Documentation & Utility Reuse**: Code explains *WHAT* it does through clear naming; inline comments explain exclusively *WHY* (background, edge cases, business logic). Inspect existing utilities and helpers before creating new utility functions.
* **Actionable Error Messages**: User-facing errors must explain what failed, why it happened, and what the user can do next. Avoid vague exceptions or silent fallbacks in workflows that affect user experience.

---

## 5. Frontend & UI/UX Standards
* **No Inline Styles in JavaScript**: Define visual styles using CSS classes and variables in stylesheet files. Never inject dynamic `element.style` strings via JavaScript.
* **DOM Security**: Sanitize and escape dynamic user-generated content (e.g., using `escapeHtml()`) to prevent XSS vulnerabilities.
* **Semantic HTML & Accessibility**: Use explicit `<button type="button">` attributes and semantic HTML5 elements.
* **Lifecycle & Background Tab Synchronization**: Modern browsers throttle background/sleeping tabs. Dashboards must hook full state synchronization into both `visibilitychange` (when tab becomes active) and `window.focus` to instantly refresh stale views and metrics upon user return.

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
  * Mention the affected component in brackets when helpful (e.g., `[Core Engine]`, `[API]`, `[UI]`).
* **Output Standard**: Return **only** the raw commit message text. Do not include meta-commentary, explanations, or raw diff output.

---

## 7. Browser & E2E Testing Protocol
* **Browser Automation & DevTools Integration**: When validating web dashboards, frontend components, or live web UI flows, leverage browser automation tools (e.g. Chrome DevTools MCP: `navigate_page`, `evaluate_script`, `take_screenshot`, `list_console_messages`, `list_network_requests`).
* **Visual Verification**: Take viewport or full-page screenshots to empirically verify UI rendering, layout alignment, and DOM modifications before concluding frontend work.
* **Console & Network Hygiene**: Inspect console logs and network traffic via DevTools tools to confirm clean execution without silent API failures or unhandled client-side exceptions.

---

## 8. CI, Testing & Pre-Commit Quality Gate
* **Development & Task Completion Gate**: Run the repository's fast automated test suite during iterative development and before presenting completed work to the user.
* **Mandatory Pre-Commit Quality Gate (Triggered Upon Explicit Commit Request)**:
  * When the user explicitly authorizes a commit/push, the agent MUST run the central verification script documented in [`.agents/KNOWLEDGE.md`](file:///g:/Meine%20Ablage/Projekte/OrdinFlow/.agents/KNOWLEDGE.md).
  * Deterministically execute CI parity: Linter, Static Type Checker, and Full Test Suite.
* **Subagent Code & Goal Audit Gate**: For non-trivial refactorings and features, invoke the `pre_commit_auditor` subagent to conduct an adversarial audit on `git diff` against:
  1. **Plan-to-Code Fidelity**: Does the code genuinely solve the root problem and deliver all commitments from `implementation_plan.md`, or were corners cut and edge cases dropped?
  2. **Code & Architecture Standards**: Adherence to `AGENTS.md` rules (no placeholders, resource hygiene, cross-platform guards, SRP limits, zero secret leaks).
  3. **Verification Completeness**: Confirm that the verification script ran over the entire codebase with 0 errors.
* **Zero Regression Standard**: Commits and pushes are strictly blocked if any linter warning, type diagnostic, test failure, or auditor blocker is present. All gates must succeed with 0 errors before executing the git commit.

---

## 9. Security, Open Source & Privacy Protocol
* **Zero Secret & Privacy Leakage**: Never commit private document samples, API keys, tokens, or local environment credentials (`.env`). All test fixtures MUST use synthetic, dummy data.
* **Large Binary Hygiene**: Never commit large model files, binary weights (> 50 MB), or `.coverage` artifacts to Git tracking. Always verify `.gitignore` ignores large binaries, virtual environments, and temporary scratch directories.
* **Cross-Platform Compatibility**: Do NOT hardcode OS-specific absolute paths. Use standard path libraries (`pathlib.Path`) and relative, configurable paths across all modules.
* **License Integrity & Attribution**: Preserve software license headers and ensure any new third-party dependency is recorded with its license.
* **Clean Git History**: Run `git status` and verify no scratch logs, temp files, or untracked sensitive data exist before committing or opening pull requests.
