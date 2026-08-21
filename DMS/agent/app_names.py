"""常见 App 名归一（CodeAct open_app 用）。"""

from __future__ import annotations

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
}


def normalize_app_name(name: str | None) -> str:
    raw = (name or "").strip().lower()
    if not raw:
        return "markor"
    return _ALIAS.get(raw, raw)
