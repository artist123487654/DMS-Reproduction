"""Screen description + lightweight Set-of-Marks overlay (independent of official DMS)."""

from __future__ import annotations

from typing import Any

import numpy as np


def _bbox_str(el: Any) -> str:
    bb = getattr(el, "bbox_pixels", None)
    if bb is None:
        return ""
    try:
        return f" bbox=[{int(bb.x_min)},{int(bb.y_min)},{int(bb.x_max)},{int(bb.y_max)}]"
    except Exception:
        return ""


def describe_ui_elements(ui_elements: list[Any], max_items: int = 40) -> str:
    n = min(len(ui_elements), max_items)
    if n == 0:
        return "No UI elements (click/index not available)."
    lines = [
        f"Valid index range: 0..{n - 1} ({n} elements; out-of-range is invalid).",
        "Screenshot marks match UI[i]. Prefer listed indices; optional click via x,y at bbox center.",
    ]
    for i, el in enumerate(ui_elements[:max_items]):
        text = getattr(el, "text", None) or ""
        desc = getattr(el, "content_description", None) or ""
        clickable = getattr(el, "is_clickable", False)
        editable = getattr(el, "is_editable", False)
        lines.append(
            f'UI[{i}] text="{text}" desc="{desc}" clickable={clickable} '
            f"editable={editable}{_bbox_str(el)}"
        )
    return "\n".join(lines)


def overlay_som(image: np.ndarray | None, ui_elements: list[Any], max_items: int = 40) -> np.ndarray | None:
    """Draw index marks on a copy of the screenshot; return original if drawing fails."""
    if image is None:
        return None
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return image

    img = Image.fromarray(image).convert("RGB")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    for i, el in enumerate(ui_elements[:max_items]):
        bb = getattr(el, "bbox_pixels", None)
        if bb is None:
            continue
        try:
            x0, y0, x1, y1 = int(bb.x_min), int(bb.y_min), int(bb.x_max), int(bb.y_max)
        except Exception:
            continue
        if x1 <= x0 or y1 <= y0:
            continue
        draw.rectangle([x0, y0, x1, y1], outline=(255, 64, 64), width=2)
        label = str(i)
        tx, ty = x0 + 2, max(0, y0 - 12)
        draw.rectangle([tx, ty, tx + 8 * len(label) + 4, ty + 12], fill=(255, 64, 64))
        draw.text((tx + 2, ty), label, fill=(255, 255, 255), font=font)

    return np.asarray(img, dtype=np.uint8)
