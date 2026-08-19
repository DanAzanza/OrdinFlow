import base64
import io
import logging
import os
from typing import Any

import numpy as np
from PIL import Image, ImageOps

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
        if longest_side != max_dim and (longest_side > max_dim or upscale):
            scale = max_dim / longest_side
            new_w = max(1, int(round(w * scale)))
            new_h = max(1, int(round(h * scale)))
            img = img.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)

    buffered = io.BytesIO()
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
        """Performs OpenCV-based preprocessing for the AI model (color with contrast prior to cropping). Returns unscaled image."""

        if not HAS_CV2 or cv2 is None:
            return pil_image.copy()

        try:
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")
            img = np.array(pil_image)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            # --- Auto-Crop (shadow exclusion via contour analysis) ---
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

    def scale_and_encode_image(
        self,
        pil_image: Image.Image,
        max_dim: int,
        upscale: bool = True,
    ) -> str:
        """Scales a prepared base image, adds a white border, and encodes it as Base64.

        If image dimension != max_dim:
        - Downscales with INTER_AREA for crisp sharpness
        - Upscales with INTER_LANCZOS4 to provide distinct ViT token grids and prevent voting collapse
        """
        if not HAS_CV2 or cv2 is None:
            return _encode_pil_fallback(
                pil_image,
                max_dim=max_dim,
                white_border=self.config.white_border,
                upscale=upscale,
            )

        try:
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")
            img = np.array(pil_image)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

            # --- White border ---
            bw = self.config.white_border
            if bw > 0:
                img = cv2.copyMakeBorder(img, bw, bw, bw, bw, cv2.BORDER_CONSTANT, value=[255, 255, 255])

            # --- Rescaling ---
            img_h, img_w = img.shape[:2]
            longest_side = max(img_h, img_w)
            if max_dim > 0 and longest_side != max_dim:
                scale = max_dim / longest_side
                new_w = max(1, int(round(img_w * scale)))
                new_h = max(1, int(round(img_h * scale)))
                if longest_side > max_dim:
                    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
                elif upscale:
                    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

            _, buffer = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), _JPEG_QUALITY])
            return base64.b64encode(buffer.tobytes()).decode("utf-8")
        except Exception:
            logger.exception("[!] Error during scaling and encoding")
            return _encode_pil_fallback(
                pil_image,
                max_dim=max_dim,
                white_border=self.config.white_border,
                upscale=upscale,
            )

    def extract_single_page_image(self, page: Any, doc: Any) -> Image.Image | None:
        """Extracts the raw full-page image from a PDF page if it contains exactly one dominant scan image."""
        try:
            image_list = page.get_images(full=True)
            if len(image_list) == 1:
                drawings = page.get_drawings() if hasattr(page, "get_drawings") else []
                # If page has non-trivial drawing paths (e.g. vector tables/lines), let it render as vector/hybrid
                if len(drawings) > 3:
                    return None

                # Check coverage: if image is placed on page, verify it covers most of the page (>= 60%)
                page_w = page.rect.width
                page_h = page.rect.height
                page_area = page_w * page_h
                if page_area > 0 and hasattr(page, "get_image_rects"):
                    try:
                        rects = page.get_image_rects(image_list[0][0])
                        if rects:
                            img_area = rects[0].width * rects[0].height
                            if (img_area / page_area) < 0.60:
                                # Small logo / header image on a digital page -> render full page instead
                                return None
                    except Exception as e:
                        logger.debug("Could not inspect image rects: %s", e)

                xref = image_list[0][0]
                base_img = doc.extract_image(xref)
                if base_img and "image" in base_img:
                    raw_bytes = base_img["image"]
                    img = Image.open(io.BytesIO(raw_bytes))
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    rot = getattr(page, "rotation", 0)
                    if rot != 0:
                        img = _apply_pdf_rotation(img, rot)
                    if img.width >= 200 and img.height >= 200:
                        return img
        except Exception as ex:
            logger.debug("Direct image extraction skipped: %s", ex)
        return None

    def create_source_images(
        self,
        pdf_path: str,
        return_raw: bool = False,
    ) -> list[Image.Image] | None:
        """Reads the document and creates prepared base images using the configured contrast settings.
        Uses PyMuPDF (fitz) for PDFs — with direct scan extraction for single-scan pages.
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
                    mat_300 = fitz.Matrix(300 / 72, 300 / 72)
                    for i in range(n_pages):
                        page = doc[i]
                        scan_img = self.extract_single_page_image(page, doc)
                        if scan_img is not None:
                            pil_images.append(scan_img)
                        else:
                            pix = page.get_pixmap(matrix=mat_300, colorspace=fitz.csRGB)
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
