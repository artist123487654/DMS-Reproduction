"""屏幕描述辅助（不强制依赖 android_world）。"""

from __future__ import annotations

from typing import Any


def describe_ui_elements(ui_elements: list[Any], max_items: int = 40) -> str:
    n = min(len(ui_elements), max_items)
    if n == 0:
        return "无 UI 元素（不可 click/index）"
    lines = [f"合法 index 范围: 0..{n - 1}（共 {n} 个；越界无效）"]
    for i, el in enumerate(ui_elements[:max_items]):
        text = getattr(el, "text", None) or ""
        desc = getattr(el, "content_description", None) or ""
        clickable = getattr(el, "is_clickable", False)
        editable = getattr(el, "is_editable", False)
        piece = f'UI[{i}] text="{text}" desc="{desc}" clickable={clickable} editable={editable}'
        lines.append(piece)
    return "\n".join(lines)
