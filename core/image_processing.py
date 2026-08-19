import base64
import io
import logging
import os

import numpy as np
from PIL import Image

from core.config import AppConfig

logger = logging.getLogger(__name__)

_JPEG_QUALITY = 90

HAS_FITZ = False
try:
    import fitz  # type: ignore[import-untyped]

    HAS_FITZ = True
except ImportError:
    fitz = None  # type: ignore[assignment]

HAS_CV2 = False
try:
    import cv2  # type: ignore[import-untyped]

    HAS_CV2 = True
except ImportError:
    cv2 = None  # type: ignore[assignment]


def _encode_pil_fallback(pil_image: Image.Image) -> str:
    buffered = io.BytesIO()
    pil_image.save(buffered, format="JPEG", quality=_JPEG_QUALITY)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


class ImagePreprocessor:
    """Handles image preprocessing and manipulation (OpenCV, Pillow)."""

    def __init__(self, config: AppConfig):
        self.config = config

    def prepare_base_image(
        self,
        pil_image: Image.Image,
    ) -> Image.Image:
        """Performs OpenCV-based preprocessing for the AI model (color with contrast prior to cropping). Returns unscaled image."""

        if not HAS_CV2 or cv2 is None:
            return pil_image.copy()

        try:
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")
            img = np.array(pil_image)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            # --- 2. Auto-Crop (shadow exclusion via contour analysis) ---
            gray_temp = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blurred_for_crop = cv2.GaussianBlur(gray_temp, (5, 5), 0)
            inv_crop = cv2.bitwise_not(blurred_for_crop)
            _, thresh_crop = cv2.threshold(inv_crop, self.config.crop_edge_threshold, 255, cv2.THRESH_BINARY)

            contours, _ = cv2.findContours(thresh_crop, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            img_h, img_w = img.shape[:2]
            valid_rects: list[tuple[int, int, int, int]] = []

            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                if w < self.config.min_contour_area and h < self.config.min_contour_area:
                    continue
                touches_left = x <= 5
                touches_top = y <= 5
                touches_right = (x + w) >= (img_w - 5)
                touches_bottom = (y + h) >= (img_h - 5)
                if touches_left or touches_top or touches_right or touches_bottom:
                    continue
                valid_rects.append((x, y, w, h))

            if valid_rects:
                x_min = min(r[0] for r in valid_rects)
                y_min = min(r[1] for r in valid_rects)
                x_max = max(r[0] + r[2] for r in valid_rects)
                y_max = max(r[1] + r[3] for r in valid_rects)
                pad = self.config.crop_padding
                x1 = max(0, x_min - pad)
                y1 = max(0, y_min - pad)
                x2 = min(img_w, x_max + pad)
                y2 = min(img_h, y_max + pad)
                if x2 > x1 and y2 > y1:
                    img = img[y1:y2, x1:x2]

            return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

        except Exception:
            logger.exception("[!] Error in OpenCV preprocessing pipeline")
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")
            return pil_image.copy()

    def scale_and_encode_image(self, pil_image: Image.Image, max_dim: int) -> str:
        """Scales a prepared base image, adds a white border, and encodes it as Base64."""
        if not HAS_CV2 or cv2 is None:
            return _encode_pil_fallback(pil_image)

        try:
            img = np.array(pil_image)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            # --- White border ---
            bw = self.config.white_border
            if bw > 0:
                img = cv2.copyMakeBorder(img, bw, bw, bw, bw, cv2.BORDER_CONSTANT, value=[255, 255, 255])

            # --- Rescaling ---
            img_h, img_w = img.shape[:2]
            longest_side = max(img_h, img_w)
            if longest_side > max_dim:
                scale = max_dim / longest_side
                new_w = int(img_w * scale)
                new_h = int(img_h * scale)
                img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

            _, buffer = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY])
            return base64.b64encode(buffer.tobytes()).decode("utf-8")
        except Exception:
            logger.exception("[!] Error during scaling and encoding")
            return _encode_pil_fallback(pil_image)

    def create_source_images(
        self,
        pdf_path: str,
        return_raw: bool = False,
    ) -> list[Image.Image] | None:
        """Reads the document and creates prepared base images using the configured contrast settings.
        Uses PyMuPDF (fitz) for PDFs — no Poppler dependency required.
        """
        _, ext = os.path.splitext(pdf_path.lower())

        try:
            if ext == ".pdf":
                if not HAS_FITZ or fitz is None:
                    logger.error("[!] PyMuPDF (fitz) not installed – PDF cannot be processed.")
                    return None
                pil_images: list[Image.Image] = []
                with fitz.open(pdf_path) as doc:
                    n_pages = len(doc)
                    # 300 DPI matrix for crisp OCR recognition
                    mat = fitz.Matrix(300 / 72, 300 / 72)
                    for i in range(n_pages):
                        page = doc[i]
                        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
                        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                        pil_images.append(img)
                        del pix
            else:
                with Image.open(pdf_path) as img:
                    pil_images = [img.convert("RGB")]

            if return_raw:
                return pil_images
            return [self.prepare_base_image(img) for img in pil_images]
        except (OSError, RuntimeError, ValueError) as ex:
            logger.warning("[!] Error loading source images: %s", ex)
            return None
