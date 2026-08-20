"""Set-of-Mark (SoM) Preprocessor for Visual Language Model (VLM) Grounding."""

import ctypes
import logging
import sys
import time

from PIL import Image, ImageDraw, ImageFont, ImageGrab

logger = logging.getLogger(__name__)

try:
    import cv2  # type: ignore[import-untyped]
    import numpy as np
except ImportError:
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]


class SoMGrounder:
    """Generates Set-of-Mark overlays for screen captures to enable precise VLM clicking."""

    @staticmethod
    def capture_screen(window_title: str | None = None) -> Image.Image | None:
        """Captures a screenshot of the entire screen or focuses the target window title."""
        if window_title and sys.platform == "win32":
            try:
                hwnd = ctypes.windll.user32.FindWindowW(None, window_title)  # type: ignore[union-attr]
                if not hwnd:
                    found: list[int] = []

                    def enum_windows_proc(h: int, _lparam: int) -> bool:
                        length = ctypes.windll.user32.GetWindowTextLengthW(h)  # type: ignore[union-attr]
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            ctypes.windll.user32.GetWindowTextW(h, buff, length + 1)  # type: ignore[union-attr]
                            if window_title.lower().replace("*", "") in buff.value.lower():
                                found.append(h)
                        return True

                    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(enum_windows_proc)
                    ctypes.windll.user32.EnumWindows(cb, 0)
                    if found:
                        hwnd = found[0]

                if hwnd:
                    ctypes.windll.user32.SetForegroundWindow(hwnd)  # type: ignore[union-attr]
                    time.sleep(0.2)
            except OSError as e:
                logger.warning("[SoMGrounder] Error focusing window '%s': %s", window_title, e)

        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                gdi32 = ctypes.windll.gdi32
                user32.SetProcessDPIAware()
                w_s = user32.GetSystemMetrics(0)
                h_s = user32.GetSystemMetrics(1)
                hdc = user32.GetDC(0)
                memdc = gdi32.CreateCompatibleDC(hdc)
                hbmp = gdi32.CreateCompatibleBitmap(hdc, w_s, h_s)
                gdi32.SelectObject(memdc, hbmp)
                gdi32.BitBlt(memdc, 0, 0, w_s, h_s, hdc, 0, 0, 0x00CC0020)
                buf = (ctypes.c_char * (w_s * h_s * 4))()
                gdi32.GetBitmapBits(hbmp, len(buf), buf)
                img = Image.frombuffer("RGBA", (w_s, h_s), buf, "raw", "BGRA", 0, 1)
                user32.ReleaseDC(0, hdc)
                gdi32.DeleteDC(memdc)
                gdi32.DeleteObject(hbmp)
                return img
            except Exception as e:
                logger.debug("[SoMGrounder] Win32 BitBlt capture failed, trying ImageGrab: %s", e)

        if ImageGrab is not None:
            try:
                return ImageGrab.grab()  # type: ignore[attr-defined]
            except OSError as e:
                logger.error("[SoMGrounder] Screenshot via ImageGrab failed: %s", e)
        return None

    @staticmethod
    def generate_som_overlay(
        img: Image.Image,
    ) -> tuple[Image.Image, dict[int, dict[str, int | list[int]]]]:
        """Segments the image into candidate UI bounding boxes and draws numbered badges [1], [2], ...

        Returns: (som_image, candidates_map)
        candidates_map[id] = {"center_x": int, "center_y": int, "bbox": [x1, y1, x2, y2]}
        """
        candidates_map: dict[int, dict[str, int | list[int]]] = {}
        som_img = img.copy()
        draw = ImageDraw.Draw(som_img, "RGBA")

        boxes: list[tuple[int, int, int, int]] = []

        # 1. RapidOCR Bounding Boxes (ONNX Engine)
        from core.extraction_pipeline import _get_rapid_ocr

        engine = _get_rapid_ocr()
        if engine is not None:
            try:
                img_np = np.array(img) if np is not None else None
                if img_np is not None:
                    res, _ = engine(img_np)
                    if res:
                        for line in res:
                            box = line[0]
                            xs = [float(p[0]) for p in box]
                            ys = [float(p[1]) for p in box]
                            w = max(xs) - min(xs)
                            h = max(ys) - min(ys)
                            if w > 15 and h > 8:
                                boxes.append(
                                    (
                                        int(min(xs)),
                                        int(min(ys)),
                                        int(max(xs)),
                                        int(max(ys)),
                                    )
                                )
            except (AttributeError, RuntimeError, OSError, ValueError) as e:
                logger.debug("[SoMGrounder] RapidOCR box extraction skipped: %s", e)

        # 2. Contour detection via OpenCV (for textless buttons & icons)
        if cv2 is not None and np is not None:
            try:
                open_cv_image = np.array(img.convert("RGB"))
                gray = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2GRAY)
                blur = cv2.GaussianBlur(gray, (3, 3), 0)
                thresh = cv2.adaptiveThreshold(
                    blur,
                    255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY_INV,
                    11,
                    2,
                )
                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                for cnt in contours:
                    x, y, w, h = cv2.boundingRect(cnt)
                    if 15 < w < img.width * 0.8 and 12 < h < img.height * 0.8:
                        boxes.append((x, y, x + w, y + h))
            except (AttributeError, RuntimeError, OSError, ValueError) as e:
                logger.debug("[SoMGrounder] Contour extraction skipped: %s", e)

        # Non-Maximum Suppression / Overlap Filtering
        filtered_boxes: list[tuple[int, int, int, int]] = []
        for box in boxes:
            x1, y1, x2, y2 = box
            overlap = False
            for fb in filtered_boxes:
                fx1, fy1, _fx2, _fy2 = fb
                if abs(x1 - fx1) < 20 and abs(y1 - fy1) < 15:
                    overlap = True
                    break
            if not overlap:
                filtered_boxes.append(box)

        # Max 80 elements per screenshot to avoid overloading the VLM
        filtered_boxes = filtered_boxes[:80]

        # Draw Numbered Badges
        try:
            font = ImageFont.load_default()
        except OSError:
            font = None

        for idx, (x1, y1, x2, y2) in enumerate(filtered_boxes, start=1):
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            candidates_map[idx] = {
                "center_x": cx,
                "center_y": cy,
                "bbox": [x1, y1, x2, y2],
            }

            draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0, 180), width=2)
            badge_text = f"[{idx}]"
            badge_w = len(badge_text) * 7 + 4
            badge_h = 14
            draw.rectangle([x1, max(0, y1 - badge_h), x1 + badge_w, y1], fill=(255, 0, 0, 220))
            draw.text(
                (x1 + 2, max(0, y1 - badge_h) + 1),
                badge_text,
                fill=(255, 255, 255, 255),
                font=font,
            )

        return som_img, candidates_map
