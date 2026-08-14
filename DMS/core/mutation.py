"""ε-mutation 与更优轨迹原地替换。"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .types import MemoryEntry, TrajectoryStep


@dataclass
class MutationConfig:
    epsilon: float = 0.1


def should_mutate(cfg: MutationConfig, rng: random.Random | None = None) -> bool:
    """检索命中后，以 ε 概率放弃复放、改为 Actor 重跑。"""
    r = rng or random
    return r.random() < cfg.epsilon


def is_better_trajectory(
    new_traj: list[TrajectoryStep],
    old_traj: list[TrajectoryStep],
    *,
    new_success: bool,
) -> bool:
    """成功且步数更短 → 触发进化替换。"""
    if not new_success or not new_traj:
        return False
    if not old_traj:
        return True
    return len(new_traj) < len(old_traj)


def apply_inplace_evolution(
    entry: MemoryEntry,
    new_traj: list[TrajectoryStep],
    *,
    success: bool,
    logical_step: int,
) -> bool:
    """
    原地覆盖 τ（成功且更短）。
    - 保留 reuse_count / success_count / fail_count：索引仍是同一 plan 谱系
    - 仅清零 fail_verify_count(K)：校验债属于旧轨迹表型
    """
    if not is_better_trajectory(new_traj, entry.trajectory, new_success=success):
        return False
    entry.trajectory = list(new_traj)
    entry.meta.success = True
    entry.meta.last_used_step = logical_step
    entry.meta.fail_verify_count = 0
    return True
