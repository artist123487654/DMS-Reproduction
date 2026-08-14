"""轻量 JSON 抽取，避免强依赖 android_world.agent_utils。"""

from __future__ import annotations

import ast
import json
import re
from typing import Any


def extract_json_obj(text: str) -> dict[str, Any] | list[Any] | None:
    if not text:
        return None
    # 优先代码块
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    candidates = []
    if fence:
        candidates.append(fence.group(1))
    # 再找第一个大括号/中括号块（非贪婪可能不够，用栈扫描）
    candidates.extend(_brace_slices(text))
    for c in candidates:
        obj = _try_parse(c)
        if obj is not None:
            return obj
    return None


def _try_parse(s: str) -> dict[str, Any] | list[Any] | None:
    try:
        return json.loads(s)
    except Exception:
        pass
    try:
        val = ast.literal_eval(s)
        if isinstance(val, (dict, list)):
            return val
    except Exception:
        pass
    return None


def _brace_slices(text: str) -> list[str]:
    out: list[str] = []
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        while start != -1:
            depth = 0
            for i in range(start, len(text)):
                ch = text[i]
                if ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        out.append(text[start : i + 1])
                        break
            start = text.find(opener, start + 1)
    # 较长的优先
    out.sort(key=len, reverse=True)
    return out[:5]


def extract_action_json(text: str) -> dict[str, Any] | None:
    """从 Actor 输出中提取动作 JSON。"""
    m = re.search(r"Action:\s*(\{.*\})", text, re.DOTALL | re.IGNORECASE)
    if m:
        obj = _try_parse(m.group(1).strip())
        if isinstance(obj, dict):
            return obj
    obj = extract_json_obj(text)
    return obj if isinstance(obj, dict) else None
