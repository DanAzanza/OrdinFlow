# 🚀 OrdinFlow

> ⚠️ Work in Progress (WIP): This project is actively under development and may change significantly over time.

OrdinFlow is a robust, rule-based AI Document Management System (DMS) and agentic orchestrator. It runs entirely locally to automatically classify, extract, and route documents (such as invoices, notes, reports, and drawings) with 100% data privacy.

By leveraging local **Vision-LLMs (via llama-cpp-python with Qwen3-VL)** and **Zero-Setup OCR (via RapidOCR & ONNX Runtime)**, OrdinFlow achieves high-precision extraction, fuzzy autocorrection, and signature detection without transmitting any data over the internet.

> **Author & Engineering:** Built & Engineered by **Daniel Azanza Hartmann** using Agentic AI Pair-Programming.

---

## ✨ Features

- **100% Local Processing:** Runs on your local hardware. Zero cloud APIs, zero subscription fees, and complete data privacy.
- **Multimodal AI Classification & Extraction:** Utilizes local Vision models to identify document types and pull structured metadata.
- **Hybrid Voting & Multi-Resolution Consistency:** Runs up to three vision passes at varying resolutions to resolve discrepancies, falling back to a democratic 2/3 voting system.
- **Zero-Setup ONNX OCR Autocorrection:** Uses embedded RapidOCR (ONNX Runtime) directly in Python to align AI extractions, correct typos/spaces, and reconstruct missing characters (like German umlaute) — without requiring external `.exe` installers!
- **Signature Detection:** Automatically detects whether a document has been signed at specific page locations.
- **Dynamic Routing & Templating:** Organizes files into custom folder structures based on user-defined templates (e.g., `{Year}--{DocumentType}--{LastName}`).
- **Premium Web Dashboard:** Real-time web UI to monitor incoming files, search processed documents, inspect metadata, and review files marked for manual verification.
- **Fully Domain-Agnostic:** Designed to handle any schema. Zero hardcoded fields; everything is defined dynamically via `config.yaml`.

---

## 📋 Prerequisites

Before running OrdinFlow, ensure you have the following components:

1. **Python 3.10+**
   - Download: [python.org](https://www.python.org/downloads/)
   - *Crucial:* Ensure you check **"Add Python to PATH"** during installation.
2. **Local Vision-LLM Model (GGUF)**
   - Loaded directly via `llama-cpp-python`, zero extra servers required.
   - Place your GGUF model in the `models/` directory (e.g., `qwen3-vl-8b-ud-q4_k_xl.gguf`).
   - Configured via `config.yaml` under `llm_model_path`.

---

## 🛠️ Installation

1. Clone or download this repository.
2. Double-click **`Install_OrdinFlow.bat`** (on Windows) or run the following in your terminal:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
   This will automatically create a virtual environment and install all dependencies (such as Flask, PyMuPDF, OpenCV, etc.).

---

## ▶️ Usage

### 1. Configure Paths & Schemas
Open `config.yaml` to define your incoming directory, archive directory, and custom document schemas. The default setup watches `./Eingang` and routes to `./Vorgaenge`:
```yaml
watch_dir: ./Eingang
target_base_dir: ./Vorgaenge
```

### 2. Start OrdinFlow
- **On Windows (Simple):** Double-click **`OrdinFlow.vbs`**. This launches both the routing orchestrator and the web dashboard in the background and opens the dashboard in your default browser.
- **Via Terminal:**
  ```bash
  # Start the background document routing worker and web server
  python main.py
  ```

### 3. Open the Dashboard
Navigate to [http://127.0.0.1:8080](http://127.0.0.1:8080) to view processed documents, manage pending verifications, and monitor execution statistics.

---

## 📁 Repository Structure

- `core/`: Contains the core routing logic, image preprocessors, OCR interface, and LLM orchestrator.
- `routes/` & `templates/`: Flask backend routes and HTML/CSS web dashboard.
- `licenses/`: Individual license files for open-source third-party dependencies.
- `THIRD_PARTY_LICENSES.md`: Comprehensive overview of third-party components and license terms.
- `docs/legal/`: Legal documentation, privacy policy (`PRIVACY_POLICY.md`), and compliance checklist (`COMPLIANCE_CHECKLIST.md`).
- `config.yaml`: The central configuration defining document schemas, extraction instructions, and routing rules.
- `tests/`: Extensive automated unit test suite covering extraction logic, path rendering, and routing rules.

---

## 🛡️ License

Copyright (c) 2026 **Daniel Azanza Hartmann**. This project is licensed under the **GNU Affero General Public License v3 (AGPL-3.0)**. See the [LICENSE](LICENSE) file for details.

*Note: This project utilizes PyMuPDF, which is licensed under GNU AGPL v3. Consequently, any distribution or network-hosted deployments of this codebase or derivative works must be open-sourced under the same license.*
