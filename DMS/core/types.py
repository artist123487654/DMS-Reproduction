"""DMS 核心数据结构。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Plan:
    """意图级子任务。"""

    precondition: str
    goal: str

    def key_text(self) -> str:
        return f"{self.precondition.strip()}||{self.goal.strip()}"


@dataclass
class TrajectoryStep:
    """原子交互一步。"""

    action: dict[str, Any]
    observation_ref: str | None = None
    ui_hint: str | None = None


_SKIP_ACTION_TYPES = frozenset({"status", "wait", None, ""})


def action_step_count(trajectory: list[TrajectoryStep]) -> int:
    """有效动作步数，不含 status/wait。"""
    return sum(
        1
        for s in trajectory
        if (s.action or {}).get("action_type") not in _SKIP_ACTION_TYPES
    )


def should_persist_trajectory(
    trajectory: list[TrajectoryStep], *, exploring: bool = False
) -> bool:
    """成功轨迹入库：默认 n>1；探索允许 n>=1。含 input_text 的完整轨迹可入库（对齐常用 CodeAct+DMS）。"""
    n = action_step_count(trajectory)
    if n > 1:
        return True
    if n >= 1 and exploring:
        return True
    return False


@dataclass
class MemoryMeta:
    success: bool = True
    created_step: int = 0
    last_used_step: int = 0
    reuse_count: int = 0
    fail_verify_count: int = 0
    description: str = ""


@dataclass
class MemoryEntry:
    id: str
    plan: Plan
    trajectory: list[TrajectoryStep] = field(default_factory=list)
    meta: MemoryMeta = field(default_factory=MemoryMeta)
    success_count: int = 0
    fail_count: int = 0

    @property
    def length(self) -> int:
        return len(self.trajectory)

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)
