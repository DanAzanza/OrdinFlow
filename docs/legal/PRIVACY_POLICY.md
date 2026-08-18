# Data Privacy & Security Policy – OrdinFlow

**Author / Maintainer:** Daniel Azanza Hartmann  
**Version:** 1.0  
**Status:** Open Source Release  

---

## 1. Overview and Scope

OrdinFlow is an open-source, rule-based AI Document Management System (DMS) designed with a **100% Local-First & Privacy-First** architecture. This document outlines the privacy principles, data handling practices, and security technical measures implemented in the OrdinFlow codebase.

---

## 2. Core Privacy Principles

| Principle | Implementation in OrdinFlow |
|-----------|-----------------------------|
| **100% Offline & On-Premise** | All document parsing, OCR text extraction, and Vision-LLM inferences run locally on the host machine. Zero external API calls, zero telemetry, zero cloud dependencies. |
| **Data Sovereignty** | Processed documents never leave the local environment or internal network. |
| **No External Trackers** | The Flask web dashboard operates completely locally (`http://127.0.0.1:8080`) without third-party tracking scripts or external CDN dependencies. |

---

## 3. Data Processing Architecture

```
[ Incoming File ] ──> [ Local Skill Queue Engine ]
                             │
                             ▼
                    [ Local ONNX OCR ] (RapidOCR)
                             │
                             ▼
                [ Local Vision LLM ] (Qwen3-VL via llama-cpp-python)
                             │
                             ▼
          [ Local Target Folder & Sidecar .meta File ]
```

1. **Ingestion:** Local files placed in `watch_dir` are processed by a local background worker.
2. **OCR & Image Extraction:** Page rendering is handled locally via PyMuPDF and processed by embedded RapidOCR / OpenCV.
3. **Multimodal LLM Inference:** Document classification and structured metadata extraction run strictly offline via `llama-cpp-python` loading GGUF model files stored in `./models`.
4. **Storage:** Extracted metadata is saved to local JSON sidecar (`.meta`) files next to routed documents.

---

## 4. GDPR & Regulatory Compliance Considerations

For users deploying OrdinFlow in environments subject to the **EU General Data Protection Regulation (GDPR)**:

* **Article 5(1)(f) GDPR (Integrity and Confidentiality):** By eliminating cloud transmission, OrdinFlow provides technical safeguards against unauthorized remote interception.
* **Article 30 GDPR (Records of Processing Activities):** Organizations using OrdinFlow can reference this architecture document to demonstrate local processing boundaries.
* **Article 32 GDPR (Security of Processing):** Local execution ensures that personal and sensitive data (e.g., medical records, financial invoices) remain strictly contained within the user's infrastructure.

---

## 5. Security Recommendations for Deployment

1. **File System Permissions:** Restrict access to the `./Eingang` (incoming) and `./Vorgaenge` (archive) directories to authorized system users.
2. **Dashboard Binding:** Ensure the Flask dashboard is bound to `127.0.0.1` unless network authentication is configured.
3. **Model Verification:** Always verify GGUF model checksums when downloading weights from HuggingFace repositories.
