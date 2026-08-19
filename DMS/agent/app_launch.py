"""开 App 捷径：借鉴官方 AppStarter「工具锁死」意图（非端口）。

不接 Droid/CodeAct。识别到打开已知 App 的子任务时，
短路为 open_app → complete，避免 VLM 翻 app drawer。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.actor import ActorStep
    from core.types import Plan

# AndroidWorld 常用 app_name（与 JSON ActionSpace 一致）
_APP_ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("markor", ("markor",)),
    ("contacts", ("contacts", "contact")),
    ("files", ("files", "file manager", "files app")),
    ("chrome", ("chrome",)),
    ("simple sms messenger", ("simple sms messenger", "sms messenger", "sms")),
    ("simple calendar pro", ("simple calendar pro", "calendar pro", "calendar")),
    ("simple gallery pro", ("simple gallery pro", "gallery pro", "gallery")),
    ("settings", ("settings",)),
    ("camera", ("camera",)),
    ("clock", ("clock",)),
]

_OPEN_INTENT = re.compile(
    r"\b(open|launch|start|open_app|via\s+open_app)\b|打开|启动",
    re.I,
)
# 同一子任务里还有后续编辑类工作 → 只强制第一步 open_app，不自动 complete
_FOLLOWUP_WORK = re.compile(
    r"\b(creat|write|type|input|sav|edit|delet|renam|send|compos|draft|"
    r"note\b|title|content|message|event|contact)\b|创建|写|输入|保存|编辑",
    re.I,
)


def match_app_name(text: str) -> str | None:
    low = (text or "").lower()
    # 长别名优先，避免 sms 抢到 calendar 等
    best: str | None = None
    best_len = -1
    for canonical, aliases in _APP_ALIASES:
        for a in aliases:
            if a in low and len(a) > best_len:
                best = canonical
                best_len = len(a)
    return best


def is_open_app_plan(plan: Plan) -> str | None:
    """若该 plan 主要是开某个已知 App，返回 canonical app_name。"""
    blob = f"{plan.precondition} {plan.goal}"
    app = match_app_name(blob)
    if not app:
        return None
    if not _OPEN_INTENT.search(blob):
        # 仅提到 app 名、无 open 语义 → 不劫持（可能是「在 Markor 里编辑」）
        return None
    return app


def _history_opened_ok(history: list[str], app: str) -> bool:
    needle = app.lower()
    for h in history:
        hl = h.lower()
        if "open_app" not in hl or needle not in hl:
            continue
        if "-> ok" in hl or "status=complete" in hl:
            return True
        # execute 报错时不要当成功
        if "->" in hl and "ok" not in hl.split("->", 1)[-1]:
            continue
    return False


def try_forced_open_app_step(plan: Plan, history: list[str]) -> ActorStep | None:
    """返回强制动作；None 表示走普通 Actor。"""
    from agent.actor import ActorStep

    app = is_open_app_plan(plan)
    if not app:
        return None

    followup = bool(_FOLLOWUP_WORK.search(plan.goal))
    if _history_opened_ok(history, app):
        if followup:
            # 已打开，后续编辑交给普通 Actor
            return None
        return ActorStep(
            action={"action_type": "status", "goal_status": "complete"},
            raw=f"[forced_open_app] already opened {app} -> complete",
            subtask_complete=True,
        )

    return ActorStep(
        action={"action_type": "open_app", "app_name": app},
        raw=f"[forced_open_app] open_app({app})",
        subtask_complete=False,
    )
