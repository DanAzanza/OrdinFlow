import base64
import ctypes
from io import BytesIO
import logging
import re
import sys
import time
from typing import Any, cast

from PIL import Image, ImageDraw, ImageFont, ImageGrab

logger = logging.getLogger(__name__)

try:
    import cv2  # type: ignore[import-untyped]
    import numpy as np
except ImportError:
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]


_DPI_INITIALIZED = False


def _init_dpi_awareness() -> None:
    """Sets Per-Monitor V2 DPI awareness once with progressive fallbacks."""
    global _DPI_INITIALIZED
    if _DPI_INITIALIZED or sys.platform != "win32":
        return
    _DPI_INITIALIZED = True
    u32 = getattr(ctypes.windll, "user32", None)
    shcore = getattr(ctypes.windll, "shcore", None)
    try:
        if u32 and hasattr(u32, "SetProcessDpiAwarenessContext"):
            u32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            return
    except Exception:
        pass
    try:
        if shcore and hasattr(shcore, "SetProcessDpiAwareness"):
            shcore.SetProcessDpiAwareness(2)
            return
    except Exception:
        pass
    try:
        if u32 and hasattr(u32, "SetProcessDPIAware"):
            u32.SetProcessDPIAware()
    except Exception:
        pass


_init_dpi_awareness()


class SoMGrounder:
    """Generates Set-of-Mark overlays for screen captures to enable precise VLM clicking."""

    @staticmethod
    def locate_target(
        locator: dict[str, Any],
        window_title: str | None = None,
        vision_extractor: Any = None,
    ) -> tuple[int, int] | None:
        """Determines the (x, y) pixel coordinates for a locator with auto-adaptive OCR & VLM fallback."""
        loc_type = str(locator.get("type", "auto"))
        loc_val = str(locator.get("value", "") or locator.get("prompt", "") or locator.get("target", ""))
        prompt = str(locator.get("prompt", "") or locator.get("value", "") or locator.get("target", ""))
        search_term = prompt or loc_val

        screen = SoMGrounder.capture_screen(window_title)
        if not screen:
            logger.error("[SoMGrounder] Screenshot could not be captured.")
            return None

        origin_x, origin_y = getattr(screen, "_screen_origin", (0, 0))

        # 1. Fast OCR Exact/Contains Match (RapidOCR)
        if loc_type in ("auto", "smart", "ocr_exact", "ocr_contains") and search_term:
            from core.extraction_pipeline import _get_rapid_ocr

            engine = _get_rapid_ocr()
            if engine is not None:
                try:
                    img_np = np.array(screen) if np is not None else None
                    if img_np is not None:
                        res, _ = engine(img_np)
                        if res:
                            # Pass 1: Exact match
                            for line in res:
                                box, text, _ = line
                                t = text.strip()
                                if not t:
                                    continue
                                if search_term.lower() == t.lower():
                                    xs = [float(p[0]) for p in box]
                                    ys = [float(p[1]) for p in box]
                                    cx = int(sum(xs) / len(xs))
                                    cy = int(sum(ys) / len(ys))
                                    offset = cast(list[int], locator.get("offset", [0, 0]))
                                    return origin_x + cx + offset[0], origin_y + cy + offset[1]

                            # Pass 2: Contains match (only for non-exact locator types)
                            if loc_type != "ocr_exact":
                                for line in res:
                                    box, text, _ = line
                                    t = text.strip()
                                    if not t:
                                        continue
                                    if search_term.lower() in t.lower():
                                        xs = [float(p[0]) for p in box]
                                        ys = [float(p[1]) for p in box]
                                        cx = int(sum(xs) / len(xs))
                                        cy = int(sum(ys) / len(ys))
                                        offset = cast(list[int], locator.get("offset", [0, 0]))
                                        return origin_x + cx + offset[0], origin_y + cy + offset[1]
                except Exception as e:
                    logger.warning("[SoMGrounder] RapidOCR Locator error: %s", e)

        # 2. Set-of-Mark (SoM) Grounding via VLM with High-Res Quadrant Tiling
        if (loc_type in ("auto", "smart", "som_vlm")) and vision_extractor and search_term:
            tiles = SoMGrounder.generate_quadrant_tiles(screen)
            for tile_img, off_x, off_y in tiles:
                som_img, candidates = SoMGrounder.generate_som_overlay(tile_img)
                if not candidates:
                    continue

                buf = BytesIO()
                som_img.save(buf, format="JPEG", quality=85)
                b64_som = base64.b64encode(buf.getvalue()).decode("utf-8")

                ground_prompt = (
                    f"Interactive UI elements are marked with red badges `[1]`, `[2]`, ... in this image.\n"
                    f"Which element number best matches: '{search_term}'?\n"
                    f"Reply ONLY with the exact number in square brackets, e.g. `[14]`. If no element matches, reply `NONE`."
                )
                payload = {"messages": [{"role": "user", "content": ground_prompt, "images": [b64_som]}]}

                resp = vision_extractor.call_vision_api(payload)
                if resp and "NONE" not in resp:
                    match = re.search(r"\[(\d+)\]", resp)
                    if match:
                        elem_id = int(match.group(1))
                        if elem_id in candidates:
                            target = candidates[elem_id]
                            offset_raw = locator.get("offset")
                            offset_x, offset_y = 0, 0
                            if isinstance(offset_raw, (list, tuple)) and len(offset_raw) >= 2:
                                ox, oy = offset_raw[0], offset_raw[1]
                                if isinstance(ox, (int, float)):
                                    offset_x = int(ox)
                                if isinstance(oy, (int, float)):
                                    offset_y = int(oy)
                            raw_cx = target.get("center_x")
                            raw_cy = target.get("center_y")
                            local_cx = int(raw_cx) if isinstance(raw_cx, (int, float)) else 0
                            local_cy = int(raw_cy) if isinstance(raw_cy, (int, float)) else 0
                            return origin_x + off_x + local_cx + offset_x, origin_y + off_y + local_cy + offset_y

        logger.warning("[SoMGrounder] Locator could not be resolved: %s", locator)
        return None

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
                    user32 = ctypes.windll.user32  # type: ignore[union-attr]
                    kernel32 = ctypes.windll.kernel32  # type: ignore[union-attr]
                    current_tid = kernel32.GetCurrentThreadId()
                    target_tid = user32.GetWindowThreadProcessId(hwnd, None)
                    if current_tid != target_tid:
                        user32.AttachThreadInput(current_tid, target_tid, True)
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    user32.SetForegroundWindow(hwnd)
                    user32.BringWindowToTop(hwnd)
                    user32.SetFocus(hwnd)
                    if current_tid != target_tid:
                        user32.AttachThreadInput(current_tid, target_tid, False)
                    time.sleep(0.2)
            except OSError as e:
                logger.warning("[SoMGrounder] Error focusing window '%s': %s", window_title, e)

        if sys.platform == "win32":
            hdc = 0
            memdc = 0
            hbmp = 0
            user32 = getattr(ctypes.windll, "user32", None)
            gdi32 = getattr(ctypes.windll, "gdi32", None)
            try:
                if user32 and gdi32:
                    _init_dpi_awareness()
                    x_v = user32.GetSystemMetrics(76)
                    y_v = user32.GetSystemMetrics(77)
                    w_s = user32.GetSystemMetrics(78)
                    h_s = user32.GetSystemMetrics(79)
                    if w_s <= 0 or h_s <= 0:
                        x_v, y_v = 0, 0
                        w_s = user32.GetSystemMetrics(0)
                        h_s = user32.GetSystemMetrics(1)

                    hdc = user32.GetDC(0)
                    if hdc:
                        memdc = gdi32.CreateCompatibleDC(hdc)
                        hbmp = gdi32.CreateCompatibleBitmap(hdc, w_s, h_s)
                        gdi32.SelectObject(memdc, hbmp)
                        gdi32.BitBlt(memdc, 0, 0, w_s, h_s, hdc, x_v, y_v, 0x00CC0020)
                        buf = (ctypes.c_char * (w_s * h_s * 4))()
                        gdi32.GetBitmapBits(hbmp, len(buf), buf)
                        img = Image.frombuffer("RGBA", (w_s, h_s), buf, "raw", "BGRA", 0, 1)
                        img._screen_origin = (x_v, y_v)  # type: ignore[attr-defined]
                        return img
            except Exception as e:
                logger.debug("[SoMGrounder] Win32 BitBlt capture failed, trying ImageGrab: %s", e)
            finally:
                if gdi32 and hbmp:
                    gdi32.DeleteObject(hbmp)
                if gdi32 and memdc:
                    gdi32.DeleteDC(memdc)
                if user32 and hdc:
                    user32.ReleaseDC(0, hdc)

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
            if y1 < badge_h + 2:
                badge_top = y1
                badge_bottom = min(y2, y1 + badge_h)
            else:
                badge_top = y1 - badge_h
                badge_bottom = y1

            draw.rectangle([x1, badge_top, x1 + badge_w, badge_bottom], fill=(255, 0, 0, 220))
            draw.text(
                (x1 + 2, badge_top + 1),
                badge_text,
                fill=(255, 255, 255, 255),
                font=font,
            )

        return som_img, candidates_map

    @staticmethod
    def generate_quadrant_tiles(
        img: Image.Image,
        patch_multiple: int = 28,
    ) -> list[tuple[Image.Image, int, int]]:
        """Splits large images (e.g. 4K/Ultrawide) into overlapping 28px-aligned quadrants + center crop.

        Dimensions are aligned to multiples of 28px for optimal Qwen-VL patch tokenization without padding.
        Returns: list of (cropped_image, offset_x, offset_y).
        """
        w, h = img.width, img.height
        if w <= 1920 and h <= 1080:
            return [(img, 0, 0)]

        # Target quadrant width and height with 10% overlap
        half_w = int(w * 0.55)
        half_h = int(h * 0.55)

        # Align tile sizes to multiples of 28 for zero-padding Qwen visual patch tokenization
        tile_w = max(28, (half_w // patch_multiple) * patch_multiple)
        tile_h = max(28, (half_h // patch_multiple) * patch_multiple)

        tiles: list[tuple[Image.Image, int, int]] = []

        # 1. Top-Left (Main Menus, Toolbars, File / Edit)
        crop_tl = img.crop((0, 0, min(w, tile_w), min(h, tile_h)))
        tiles.append((crop_tl, 0, 0))

        # 2. Top-Right (Window Controls, Right Toolbars, Layer Panels)
        x_tr = max(0, w - tile_w)
        crop_tr = img.crop((x_tr, 0, w, min(h, tile_h)))
        tiles.append((crop_tr, x_tr, 0))

        # 3. Center (Modal Dialogs, Popups, Confirmations)
        x_c = max(0, (w - tile_w) // 2)
        y_c = max(0, (h - tile_h) // 2)
        crop_c = img.crop((x_c, y_c, min(w, x_c + tile_w), min(h, y_c + tile_h)))
        tiles.append((crop_c, x_c, y_c))

        # 4. Bottom-Left (Status bars, Bottom panels)
        y_bl = max(0, h - tile_h)
        crop_bl = img.crop((0, y_bl, min(w, tile_w), h))
        tiles.append((crop_bl, 0, y_bl))

        # 5. Bottom-Right (Save/Cancel/OK buttons in dialogs, zoom sliders)
        x_br = max(0, w - tile_w)
        y_br = max(0, h - tile_h)
        crop_br = img.crop((x_br, y_br, w, h))
        tiles.append((crop_br, x_br, y_br))

        return tiles
