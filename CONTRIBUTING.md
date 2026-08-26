# Contributing to OrdinFlow

Thank you for your interest in contributing to **OrdinFlow**! Bug reports, feature suggestions, documentation enhancements, and code contributions are very welcome.

---

## 📜 Code of Conduct

This project and everyone participating in it is governed by the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

---

## 🛠️ Development Setup

1. **Fork and Clone the Repository:**
   ```bash
   git clone https://github.com/<your-username>/OrdinFlow.git
   cd OrdinFlow
   ```

2. **Create and Activate a Virtual Environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies and Development Tools:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   pip install ruff pyright pytest pytest-cov
   ```

4. **Download Local Vision Models (Optional for Unit Tests):**
   Place your GGUF models in `models/` (e.g. `Qwen3-VL-4B-Instruct-UD-Q4_K_XL.gguf` and `mmproj-BF16.gguf`). Note: The automated unit test suite uses synthetic fixtures and runs without downloading large model weights.

---

## 🚦 Local Quality Gates & CI Pre-Flight Checks

Before submitting a pull request, ensure all three local verification gates pass with **0 errors and 0 warnings**:

1. **Linting and Code Style:**
   ```bash
   ruff check .
   ```

2. **Static Type Analysis:**
   ```bash
   npx -y pyright@latest core/ routes/
   ```

3. **Automated Unit Tests:**
   ```bash
   python -m pytest -q
   ```

---

## 📐 Coding Standards & Guidelines

* **Strict English Codebase:** All Python code, variable names, functions, classes, docstrings, and inline comments must be written in English.
* **Type Hints:** Use explicit typing everywhere (`from typing import ...`, Type Annotations, Pydantic schemas).
* **Domain-Agnostic Core:** Core processing logic in `core/` must remain domain-agnostic. Avoid hardcoding document schemas or field names in Python files; use runtime YAML configurations (`settings/skills/`).
* **Zero Placeholders:** Never submit code containing placeholders, summaries, or truncation comments (`// TODO`, `...`).
* **Resource Hygiene:** Always close and clean up file handles, native image buffers, and PyMuPDF document handles within `with` context managers or `finally` blocks.

---

## 📝 Git Commit Guidelines

Commit messages must follow this concise format:

* **Subject Line:**
  * Maximum **50 characters**.
  * Start with a capital letter.
  * Do not end with a period.
  * Use the **imperative mood** (e.g. `Add multi-resolution consensus test` instead of `Added tests`).
* **Body:**
  * Explain the **reason** for the change and any key context.
  * Keep it to 1–2 short sentences.

Example:
```
Add multi-resolution consensus test

Introduce test cases verifying tier escalation when confidence falls below the 0.67 threshold.
```

---

## 🔄 Pull Request Workflow

1. Create a feature branch: `git checkout -b feature/my-new-feature`
2. Commit your changes following the commit message guidelines.
3. Run and verify all local CI checks (`ruff`, `pyright`, `pytest`).
4. Push your branch to GitHub: `git push origin feature/my-new-feature`
5. Open a Pull Request against the `main` branch with a clear description of your changes.

Thank you for helping make OrdinFlow better!
