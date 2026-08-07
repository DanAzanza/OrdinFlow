# Third-Party Licenses – OrdinFlow

**Last Updated:** July 2026  
**Project Author / Rights Holder:** Daniel Azanza Hartmann  

---

## Overview of Used Open-Source Components

| Component | Version | License | Type / Purpose |
|-----------|---------|--------|----------------|
| Flask | Latest available (via requirements.txt) | BSD 3-Clause | Web Dashboard Framework |
| PyMuPDF (fitz) | Latest available (via requirements.txt) | GNU AGPL v3.0 | PDF Processing & Rendering |
| RapidOCR (rapidocr-onnxruntime) | Latest available (via requirements.txt) | Apache License 2.0 | Zero-Setup Local OCR |
| ONNX Runtime | Dependency of RapidOCR | MIT License | Inferenz Engine for OCR |
| Pillow (PIL) | Latest available (via requirements.txt) | HPND | Image Processing & Manipulation |
| llama-cpp-python | Latest available (via requirements.txt) | MIT License | Local Vision-LLM Inference (GGUF) |
| Qwen3-VL-8B | GGUF Quantization Q4_K_M | Tongyi Qianwen / Apache 2.0 | Local Multimodal Vision Model |
| watchdog | Latest available (via requirements.txt) | Apache License 2.0 | Filesystem Monitoring |
| PyYAML | Latest available (via requirements.txt) | MIT License | YAML Configuration Parsing |
| opencv-python | Latest available (via requirements.txt) | Apache License 2.0 | Computer Vision & Preprocessing |
| numpy | Latest available (via requirements.txt) | BSD 3-Clause | Numerical Array Computing |
| pytest | Latest available (via requirements.txt) | MIT License | Testing Framework |
| pytest-mock | Latest available (via requirements.txt) | MIT License | Test Mocking Utility |

---

## License Terms by Component

### 1. Flask – BSD 3-Clause License

**Purpose:** Web dashboard interface for OrdinFlow.  
**Summary:** Free to use, modify, and distribute. Requires copyright notice and license text retention.

The full license text is available in `licenses/FLASK_LICENSE.txt`.

### 2. PyMuPDF (fitz) – GNU Affero General Public License v3.0 (AGPL-3.0)

**Purpose:** Extraction and conversion of PDF pages to image tensors.  
**Summary:** AGPL v3.0 Open-Source License. Because OrdinFlow itself is open-sourced under the GNU AGPL v3.0 on GitHub, all copyleft requirements of PyMuPDF are fully satisfied.

The full license text is available in `licenses/GPL-AGPL-3.0.txt` and the root `LICENSE` file.

### 3. RapidOCR (rapidocr-onnxruntime) & ONNX Runtime – Apache License 2.0 / MIT License

**Purpose:** Zero-setup embedded OCR processing directly in Python without external binaries.  
**Summary:** Free to use, modify, and distribute.

The full license texts are available in `licenses/APACHE-2.0.txt` and `licenses/MIT_LICENSE.txt`.

### 5. Pillow – HPND License (Historic Permission Notice and Disclaimer)

**Purpose:** Image loading and color channel manipulation.  
**Summary:** Free to use without restrictions. Attribution recommended.

The full license text is available in `licenses/HPND.txt`.

### 6. llama-cpp-python – MIT License

**Purpose:** Local execution of Vision GGUF models (including Qwen3-VL) as a native Python binding.  
**Summary:** Permissive license. Free to use, modify, and distribute with attribution.

The full license text is available in `licenses/MIT_LICENSE.txt`.

### 7. Qwen3-VL-8B-Instruct – Tongyi Qianwen License & Apache 2.0

**Purpose:** Local multimodal AI model for document classification and schema extraction.  
**Summary:** Permitted for open-source research and application usage. Output data must not be used to train competing commercial base models.

The full license text is available in `licenses/TONGYI_QIANWEN_LICENSE.txt`.

### 8. watchdog – Apache License 2.0

**Purpose:** Monitoring directory events for incoming document detection.  
**Summary:** Permissive license. Free to use with attribution.

The full license text is available in `licenses/APACHE-2.0.txt`.

### 9. PyYAML – MIT License

**Purpose:** Parsing configuration files (`config.yaml`).  
**Summary:** Permissive license. Free to use and modify.

The full license text is available in `licenses/MIT_PYYAML.txt` / `licenses/MIT_LICENSE.txt`.

### 10. opencv-python – Apache License 2.0

**Purpose:** Computer vision operations (image enhancement, cropping, edge detection).  
**Summary:** Permissive license. Free to use with attribution.

The full license text is available in `licenses/APACHE-2.0.txt`.

### 11. numpy – BSD 3-Clause License

**Purpose:** Numerical computation and array manipulations.  
**Summary:** Permissive license. Requires attribution notice.

The full license text is available in `licenses/BSD-3NUMPY.txt`.

### 12. pytest & pytest-mock – MIT License

**Purpose:** Automated test runner and mock library for development and CI.  
**Summary:** Permissive license. Free to use and distribute.

The full license text is available in `licenses/MIT_PYTEST.txt`.

---

## Compliance Statement for GitHub Open-Source Release

All third-party dependencies are properly acknowledged, documented, and distributed under their respective open-source licenses. OrdinFlow is licensed under the **GNU AGPL v3.0**, ensuring full compatibility across the entire dependency graph.
