"""DMS 核心数据结构，对应论文3.2.1. MEMORY CONSTRUCTION。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Plan:
    """意图级子任务。"""

    precondition: str  # 前置条件
    goal: str  # 目标

    def key_text(self) -> str:
        return f"{self.precondition.strip()}||{self.goal.strip()}"


@dataclass
class TrajectoryStep:
    """原子交互一步。"""

    action: dict[str, Any]
    observation_ref: str | None = None  # 截图路径
    ui_hint: str | None = None


_SKIP_ACTION_TYPES = frozenset({"status", "wait", None, ""})


def action_step_count(trajectory: list[TrajectoryStep]) -> int:
    """有效动作步数（排除 status/wait），对齐官方 llm_io 含代码的步计数。"""
    return sum(
        1
        for s in trajectory
        if (s.action or {}).get("action_type") not in _SKIP_ACTION_TYPES
    )


def should_persist_trajectory(
    trajectory: list[TrajectoryStep], *, exploring: bool = False
) -> bool:
    """官方：step_count > 1；探索时 step_count >= 1 也可入库。"""
    n = action_step_count(trajectory)
    return n > 1 or (exploring and n >= 1)


@dataclass
class MemoryMeta:
    """记忆元数据。"""

    success: bool = True  # 是否成功
    created_step: int = 0  # 创建步数
    last_used_step: int = 0  # 最后使用步数
    reuse_count: int = 0  # 重用次数
    fail_verify_count: int = 0  # 验证失败次数
    description: str = ""  # 描述


@dataclass
class MemoryEntry:
    """记忆单元。"""

    id: str
    plan: Plan
    trajectory: list[TrajectoryStep] = field(default_factory=list)
    meta: MemoryMeta = field(default_factory=MemoryMeta)
    success_count: int = 0  # 成功次数
    fail_count: int = 0  # 失败次数

    @property
    def length(self) -> int:
        return len(self.trajectory)

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d
