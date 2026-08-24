"""AndroidWorld 评测任务套件：Minimum / Preferred / Full。"""

from __future__ import annotations

import random
from typing import Any


# Minimum 套件
MIN_TASKS = [
    "MarkorCreateNote",
    "ContactsAddContact",
    "FilesDeleteFile",
    "SimpleCalendarAddOneEvent",
    "MarkorCreateNoteAndSms",
]

# test单任务
TEST_TASKS = [
    "ContactsAddContact",
]


def _primary_app(task_cls: type) -> str:
    names = getattr(task_cls, "app_names", None) or ()
    if not names:
        return "unknown"
    first = names[0]
    return str(first).strip().lower()


def load_android_registry(family: str = "android"):
    """family: android | android_world"""
    from android_world import registry as aw_registry

    reg = aw_registry.TaskRegistry()
    if family in {"android_world", "full", "world"}:
        return reg.get_registry(reg.ANDROID_WORLD_FAMILY)
    return reg.get_registry(reg.ANDROID_FAMILY)


def build_preferred_tasks(
    *,
    seed: int = 30,
    per_app: int = 2,
    family: str = "android",
) -> list[str]:
    """
    Preferred：覆盖全部真实 App，每个 App 随机采样 1–2 个任务。
    默认用 ANDROID_FAMILY，不含 MiniWoB，用于跨应用泛化。
    """
    per_app = max(1, min(2, int(per_app)))
    aw = load_android_registry(family)
    by_app: dict[str, list[str]] = {}
    for name, cls in aw.items():
        app = _primary_app(cls)
        by_app.setdefault(app, []).append(name)

    rng = random.Random(seed)
    picked: list[str] = []
    for app in sorted(by_app.keys()):
        pool = sorted(by_app[app])
        k = min(per_app, len(pool))
        # 任务少时全取；多则固定种子抽样，保证可复现
        if len(pool) <= k:
            chosen = pool
        else:
            chosen = sorted(rng.sample(pool, k))
        picked.extend(chosen)
    return picked


def build_full_split_tasks(family: str = "android_world") -> list[str]:
    """完整 Split，android_world 全家桶约 116 个任务。"""
    aw = load_android_registry(family)
    return sorted(aw.keys())


def resolve_tasks(
    *,
    suite: str | None = None,
    tasks: str | None = None,
    tasks_file: str | None = None,
    seed: int = 30,
    per_app: int = 2,
) -> tuple[list[str], str]:
    """
    解析最终任务列表。
    优先级：--tasks > --tasks_file > --suite > 默认 min。
    返回 task_names 和 suite_label。
    """
    if tasks:
        parts = [x.strip() for x in tasks.replace(";", ",").split(",") if x.strip()]
        return parts, "custom"

    if tasks_file:
        from pathlib import Path

        text = Path(tasks_file).read_text(encoding="utf-8")
        parts: list[str] = []
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            if "," in line:
                parts.extend(x.strip() for x in line.split(",") if x.strip())
            else:
                parts.append(line)
        return parts, "file"

    suite = (suite or "min").strip().lower()
    if suite in {"test", "smoke"}:
        return list(TEST_TASKS), "test"
    if suite in {"min", "minimum", "default"}:
        return list(MIN_TASKS), "min"
    if suite in {"preferred", "pref", "apps20", "cross_app"}:
        return build_preferred_tasks(seed=seed, per_app=per_app), "preferred"
    if suite in {"full", "split", "android_world", "all"}:
        return build_full_split_tasks("android_world"), "full"
    if suite in {"android", "android_family"}:
        return build_full_split_tasks("android"), "android"
    raise ValueError(
        f"未知 suite={suite!r}，可选: test | min | preferred | full | android"
    )


def summarize_by_app(task_names: list[str], family: str = "android") -> dict[str, Any]:
    aw = load_android_registry(family if family != "full" else "android_world")
    # full suite may need world registry
    if any(n not in aw for n in task_names):
        aw = load_android_registry("android_world")
    by_app: dict[str, list[str]] = {}
    for name in task_names:
        cls = aw.get(name)
        app = _primary_app(cls) if cls else "unknown"
        by_app.setdefault(app, []).append(name)
    return {
        "n_tasks": len(task_names),
        "n_apps": len(by_app),
        "apps": {k: v for k, v in sorted(by_app.items())},
    }
