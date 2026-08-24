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
    """一轮 CodeAct LLM IO，存 prompt / thought / code。"""

    prompt: str = ""
    response_thought: str = ""
    response_code: str = ""
    response_raw: str = ""


def io_step_count(trajectory: list[TrajectoryStep]) -> int:
    """有效 CodeAct 轮数，统计含可执行代码的步。"""
    return sum(1 for s in trajectory if (s.response_code or "").strip())


def should_persist_trajectory(
    trajectory: list[TrajectoryStep], *, exploring: bool = False
) -> bool:
    """成功轨迹入库：默认多轮，探索时允许单轮。"""
    n = io_step_count(trajectory)
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
