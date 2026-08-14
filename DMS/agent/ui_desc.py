"""屏幕描述辅助（不强制依赖 android_world）。"""

from __future__ import annotations

from typing import Any


def describe_ui_elements(ui_elements: list[Any], max_items: int = 40) -> str:
    lines: list[str] = []
    for i, el in enumerate(ui_elements[:max_items]):
        text = getattr(el, "text", None) or ""
        desc = getattr(el, "content_description", None) or ""
        clickable = getattr(el, "is_clickable", False)
        editable = getattr(el, "is_editable", False)
        piece = f'UI[{i}] text="{text}" desc="{desc}" clickable={clickable} editable={editable}'
        lines.append(piece)
    return "\n".join(lines) if lines else "无 UI 元素"
