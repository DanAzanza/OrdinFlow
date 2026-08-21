# Security Policy

## Supported Versions

OrdinFlow is actively maintained and receives security updates for the latest versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.x / `main` | :white_check_mark: |
| < 1.0   | :x:                |

---

## 🔒 Privacy & On-Premise Security Model

OrdinFlow is engineered for **100% on-premise, air-gapped operation**:
- No document data, image data, or metadata is ever transmitted over the public internet.
- All AI inference executes locally via quantized GGUF weights through `llama-cpp-python`.
- OCR processing runs in-process via embedded ONNX runtime models.
- RPA keystroke injection is guarded by crash-safe Windows `BlockInput` shielding with registered `atexit` emergency releases.

---

## 🚨 Reporting a Vulnerability

Security and privacy in OrdinFlow are taken very seriously. If you discover a security vulnerability or sensitive data leak risk, please report it responsibly:

1. **Do NOT open a public GitHub issue** for undisclosed security vulnerabilities.
2. Instead, submit a private advisory through [GitHub Security Advisories](https://github.com/DanAzanza/OrdinFlow/security/advisories/new) or contact the maintainer via [LinkedIn](https://www.linkedin.com/in/daniel-azanza-hartmann-8a7b59384/).
3. Please include:
   - A detailed description of the vulnerability.
   - Steps or a minimal proof of concept to reproduce the issue.
   - Potential impact and affected components.

Reports will be acknowledged within 48 hours to release a patch promptly.

