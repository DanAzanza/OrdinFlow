import base64
import io
import logging
import os
import threading
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from core.config import AppConfig

logger = logging.getLogger(__name__)

_JPEG_QUALITY = 90

_RAPID_OCR_ENGINE: Any = None
_OCR_LOCK = threading.RLock()


def get_rapid_ocr() -> Any:
    """Returns the globally cached RapidOCR engine instance or None if unavailable."""
    global _RAPID_OCR_ENGINE
    if _RAPID_OCR_ENGINE is None:
        with _OCR_LOCK:
            if _RAPID_OCR_ENGINE is None:
                try:
                    from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-untyped]

                    _RAPID_OCR_ENGINE = RapidOCR()
                except (ImportError, RuntimeError, OSError):
                    _RAPID_OCR_ENGINE = False
    return _RAPID_OCR_ENGINE if _RAPID_OCR_ENGINE is not False else None


def run_rapid_ocr(img: Any, engine: Any = None) -> list[Any] | None:
    """Thread-safely executes RapidOCR on an image input (numpy array or PIL image)."""
    ocr_engine = engine if engine is not None else get_rapid_ocr()
    if not ocr_engine:
        return None
    with _OCR_LOCK:
        try:
            res, _ = ocr_engine(img)
            return res
        except Exception as e:
            logger.debug("[run_rapid_ocr] OCR inference error: %s", e)
            return None


def align_to_vit_grid(dim: int, patch_size: int = 28) -> int:
    """Rounds a dimension down to an exact multiple of the ViT token patch size (default 28px)."""
    if dim <= 0:
        return patch_size
    return (dim // patch_size) * patch_size

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


def _apply_pdf_rotation(img: Image.Image, rotation: int) -> Image.Image:
    """Rotates a PIL image according to PyMuPDF clockwise page rotation degrees."""
    rot = rotation % 360
    if rot == 90:
        return img.transpose(Image.Transpose.ROTATE_270)
    if rot == 180:
        return img.transpose(Image.Transpose.ROTATE_180)
    if rot == 270:
        return img.transpose(Image.Transpose.ROTATE_90)
    return img


def _encode_pil_fallback(
    pil_image: Image.Image,
    max_dim: int | None = None,
    white_border: int = 0,
    upscale: bool = True,
) -> str:
    """Fallback PIL-based scaler with letterbox padding to multiples of 28."""
    img = pil_image.copy()
    if img.mode != "RGB":
        img = img.convert("RGB")

    if white_border > 0:
        w, h = img.size
        new_img = Image.new("RGB", (w + 2 * white_border, h + 2 * white_border), (255, 255, 255))
        new_img.paste(img, (white_border, white_border))
        img = new_img

    if max_dim is not None and max_dim > 0:
        w, h = img.size
        longest_side = max(w, h)
        target_max = (max_dim // 28) * 28 if max_dim >= 28 else 28
        if longest_side > 0 and (longest_side != target_max or (w % 28 != 0 or h % 28 != 0)) and (longest_side > target_max or upscale):
            scale = target_max / float(longest_side)
            scaled_w = max(1, int(round(w * scale)))
            scaled_h = max(1, int(round(h * scale)))
            img = img.resize((scaled_w, scaled_h), resample=Image.Resampling.LANCZOS)

            # Bottom-right letterbox padding to 28px grid
            pad_w = ((scaled_w + 27) // 28) * 28
            pad_h = ((scaled_h + 27) // 28) * 28
            pad_right = pad_w - scaled_w
            pad_bottom = pad_h - scaled_h
            if pad_right > 0 or pad_bottom > 0:
                padded = Image.new("RGB", (pad_w, pad_h), (255, 255, 255))
                padded.paste(img, (0, 0))
                img = padded

    with io.BytesIO() as buffered:
        img.save(buffered, format="JPEG", quality=_JPEG_QUALITY)
        return base64.b64encode(buffered.getvalue()).decode("utf-8")


class ImagePreprocessor:
    """Handles image preprocessing and manipulation (OpenCV, Pillow)."""

    def __init__(self, config: AppConfig):
        self.config = config

    def prepare_base_image(
        self,
        pil_image: Image.Image,
    ) -> Image.Image:
        """Performs OpenCV-based preprocessing for the AI model (adaptive background estimation,
        edge artifact filtering, auto-cropping, and 300 DPI white border). Returns unscaled image.
        """
        if not HAS_CV2 or cv2 is None:
            if isinstance(pil_image, np.ndarray):
                return Image.fromarray(pil_image)
            return pil_image.copy()

        try:
            if isinstance(pil_image, np.ndarray):
                pil_image = Image.fromarray(pil_image)
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")
            img = np.array(pil_image)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            img_h, img_w = img.shape[:2]

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            render_dpi = getattr(self.config, "render_dpi", 200) or 200
            dpi_scale = max(0.2, render_dpi / 300.0)

            # 1. Robust Background Estimation (Sample inset margin proportionally inside edge to avoid black scanner bed)
            if img_h > 120 and img_w > 120:
                m_min = max(5, int(15 * dpi_scale))
                m_max = max(m_min + 5, int(60 * dpi_scale))
                margin_top = gray[m_min : min(m_max, img_h // 4), :]
                margin_bottom = gray[max(0, img_h - m_max) : img_h - m_min, :]
                margin_left = gray[:, m_min : min(m_max, img_w // 4)]
                margin_right = gray[:, max(0, img_w - m_max) : img_w - m_min]
                margin_samples = np.concatenate([
                    margin_top.flatten(),
                    margin_bottom.flatten(),
                    margin_left.flatten(),
                    margin_right.flatten(),
                ])
                bg_val = (
                    int(np.percentile(np.asarray(margin_samples, dtype=np.float64), 85))
                    if len(margin_samples) > 0
                    else 255
                )  # type: ignore[call-overload, arg-type]
            else:
                bg_val = int(np.median(np.asarray(gray, dtype=np.float64))) if gray.size > 0 else 255  # type: ignore[call-overload, arg-type]

            # 2. Symmetric Absolute Difference & Gaussian Denoising
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            bg_arr = np.full_like(blurred, bg_val)
            diff = cv2.absdiff(blurred, bg_arr)

            thresh_val = getattr(self.config, "crop_edge_threshold", 30)
            _, thresh = cv2.threshold(diff, thresh_val, 255, cv2.THRESH_BINARY)

            # 3. Contour Extraction & Robust Border Artifact Filtering
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            valid_rects: list[tuple[int, int, int, int]] = []

            # DPI-aware border strip thresholds (ignore thin lines along edge, keep headers)
            max_edge_strip_w = max(int(20 * dpi_scale), int(img_w * 0.025))
            max_edge_strip_h = max(int(20 * dpi_scale), int(img_h * 0.025))
            touch_tol = max(2, int(5 * dpi_scale))
            dust_limit = max(10, int(25 * dpi_scale))

            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                if w < self.config.min_contour_area and h < self.config.min_contour_area:
                    continue

                touches_left = x <= touch_tol
                touches_top = y <= touch_tol
                touches_right = (x + w) >= (img_w - touch_tol)
                touches_bottom = (y + h) >= (img_h - touch_tol)
                touches_edge = touches_left or touches_top or touches_right or touches_bottom

                # Filter thin scanner shadows / roller lines along outer edges
                is_vert_strip = (touches_left or touches_right) and w <= max_edge_strip_w
                is_horiz_strip = (touches_top or touches_bottom) and h <= max_edge_strip_h
                is_corner_dust = touches_edge and w < dust_limit and h < dust_limit

                if is_vert_strip or is_horiz_strip or is_corner_dust:
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
                min_dim = int(50 * dpi_scale)
                if (x2 - x1) > min_dim and (y2 - y1) > min_dim:
                    img = img[y1:y2, x1:x2]

            # 4. Apply White Border ONCE at raw rendering stage
            bw = self.config.white_border
            if bw > 0:
                val = [255, 255, 255] if len(img.shape) == 3 else 255
                img = cv2.copyMakeBorder(img, bw, bw, bw, bw, cv2.BORDER_CONSTANT, value=val)

            return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

        except Exception:
            logger.exception("[!] Error in OpenCV preprocessing pipeline")
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")
            return pil_image.copy()

    def scale_and_encode_image(
        self,
        pil_image: Image.Image,
        max_dim: int,
        upscale: bool = True,
    ) -> str:
        """Scales a prepared base image with proportional letterboxing to 28px ViT patch tokens and encodes as Base64.

        - Downscales with INTER_AREA for crisp sharpness
        - Upscales with INTER_LANCZOS4 to provide distinct ViT token grids and prevent voting collapse
        - Pads to exact multiples of 28 with bottom-right white letterboxing
        """
        if not HAS_CV2 or cv2 is None:
            return _encode_pil_fallback(
                pil_image,
                max_dim=max_dim,
                white_border=0,
                upscale=upscale,
            )

        try:
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")
            img = np.array(pil_image)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            img_h, img_w = img.shape[:2]
            longest_side = max(img_h, img_w)
            target_max = (max_dim // 28) * 28 if max_dim >= 28 else 28

            if max_dim > 0 and longest_side > 0 and (longest_side != target_max or (img_w % 28 != 0 or img_h % 28 != 0)):
                scale = target_max / float(longest_side)
                scaled_w = max(1, int(round(img_w * scale)))
                scaled_h = max(1, int(round(img_h * scale)))

                interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LANCZOS4
                img = cv2.resize(img, (scaled_w, scaled_h), interpolation=interp)

                # Bottom-right letterbox padding to multiple of 28
                pad_w = ((scaled_w + 27) // 28) * 28
                pad_h = ((scaled_h + 27) // 28) * 28
                pad_right = pad_w - scaled_w
                pad_bottom = pad_h - scaled_h

                if pad_right > 0 or pad_bottom > 0:
                    val = [255, 255, 255] if len(img.shape) == 3 else 255
                    img = cv2.copyMakeBorder(
                        img, 0, pad_bottom, 0, pad_right, cv2.BORDER_CONSTANT, value=val
                    )

            _, buffer = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY])
            return base64.b64encode(buffer.tobytes()).decode("utf-8")
        except Exception:
            logger.exception("[!] Error during scaling and encoding")
            return _encode_pil_fallback(
                pil_image,
                max_dim=max_dim,
                white_border=0,
                upscale=upscale,
            )

    def get_prepared_page_image(
        self,
        page_dict: dict[str, Any],
        dimension: int,
    ) -> str:
        """Retrieves, crops, and scales a page image on-demand for multi-tier extraction."""
        # 1. If in-memory cropped image exists, use directly
        if page_dict.get("prep_img") is not None:
            return self.scale_and_encode_image(page_dict["prep_img"], dimension)

        # 2. Re-render on demand if pdf_path is available
        pdf_path = page_dict.get("pdf_path")
        idx = page_dict.get("idx", 0)

        if pdf_path and os.path.isfile(pdf_path) and pdf_path.lower().endswith(".pdf"):
            if HAS_FITZ and fitz is not None:
                with fitz.open(pdf_path) as doc:
                    if 0 <= idx < len(doc):
                        page = doc[idx]
                        dpi = getattr(self.config, "render_dpi", 200) or 200
                        mat = fitz.Matrix(dpi / 72, dpi / 72)
                        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
                        raw_img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                        del pix
                        prep_img = self.prepare_base_image(raw_img)
                        return self.scale_and_encode_image(prep_img, dimension)

        # 3. Fallback to cached base64 if no raw source available
        return page_dict.get("b64_img", "")

    def create_source_images(
        self,
        pdf_path: str,
        return_raw: bool = False,
    ) -> list[Image.Image] | None:
        """Reads the document and creates prepared base images using standardized DPI rendering.
        Uses PyMuPDF (fitz) for PDFs and Pillow for image files.
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
                    dpi = getattr(self.config, "render_dpi", 200) or 200
                    mat = fitz.Matrix(dpi / 72, dpi / 72)
                    for i in range(n_pages):
                        page = doc[i]
                        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
                        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                        pil_images.append(img)
                        del pix
            else:
                with Image.open(pdf_path) as img:
                    img = ImageOps.exif_transpose(img)
                    pil_images = [img.convert("RGB")]

            if return_raw:
                return pil_images
            return [self.prepare_base_image(img) for img in pil_images]
        except (OSError, RuntimeError, ValueError) as ex:
            logger.warning("[!] Error loading source images: %s", ex)
            return None
