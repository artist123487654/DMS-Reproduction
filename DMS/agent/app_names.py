"""常见 App 名归一，供 CodeAct open_app 使用。"""

from __future__ import annotations

import re

_ALIAS = {
    "markor": "markor",
    "contacts": "contacts",
    "contact": "contacts",
    "files": "files",
    "file": "files",
    "documents": "files",
    "chrome": "chrome",
    "sms": "simple sms messenger",
    "simple sms messenger": "simple sms messenger",
    "simple sms": "simple sms messenger",
    "calendar": "simple calendar pro",
    "simple calendar pro": "simple calendar pro",
    "simple calendar": "simple calendar pro",
    "gallery": "simple gallery pro",
    "simple gallery pro": "simple gallery pro",
    "phone": "contacts",
}

_OPEN_VIA = re.compile(
    r"open\s+(?:the\s+)?(.+?)(?:\s+app)?\s+via\s+open_app",
    re.IGNORECASE,
)


def normalize_app_name(name: str | None) -> str:
    raw = (name or "").strip().lower()
    if not raw:
        return "markor"
    return _ALIAS.get(raw, raw)


def infer_app_from_text(text: str | None) -> str | None:
    """从 goal / task 文本推断应 open_app 的应用名。"""
    raw = (text or "").strip()
    if not raw:
        return None
    m = _OPEN_VIA.search(raw)
    if m:
        return normalize_app_name(m.group(1).strip(" \"'"))
    low = raw.lower()
    for alias in sorted(_ALIAS.keys(), key=len, reverse=True):
        if alias in low:
            return _ALIAS[alias]
    return None


def is_open_app_goal(goal: str | None) -> bool:
    g = (goal or "").lower()
    if "via open_app" in g or "open_app" in g:
        return True
    if g.strip().startswith("open ") and " via " not in g:
        # "Open Markor" 一类短目标
        return infer_app_from_text(goal) is not None and len(g) < 80
    return False
