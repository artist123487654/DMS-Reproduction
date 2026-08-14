"""基于 Elbow 的容量调节与长尾修剪，这个脚本用于根据生存价值选择需要修剪的记忆。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class CapacityConfig:
    C_min: int = 80  # 触发修剪的容量下界
    C_max: int = 300  # 最大容量
    delta_step: int = 20  # 扩张步长


def elbow_index(scores_desc: list[float]) -> int:
    """
    在降序生存价值曲线上找肘点：
    k* = argmax_k ∇²f(k)
    """
    n = len(scores_desc)
    if n < 3:
        return max(0, n - 1)
    f = np.asarray(scores_desc, dtype=np.float64)
    # 离散二阶差分：f[k-1] - 2f[k] + f[k+1]
    second = f[:-2] - 2.0 * f[1:-1] + f[2:]
    k_star = int(np.argmax(second)) + 1  # 对齐到原序列下标
    return k_star


def regulate_capacity(
    scores_desc: list[float],
    cfg: CapacityConfig,
) -> tuple[int, int, bool]:
    """
    返回 (keep_count, new_C_min, expanded)。
    若肘点处仍高于均值，视为高质量饱和 → 扩张 C_min 而非狠剪。
    """
    n = len(scores_desc)
    if n <= cfg.C_min:
        return n, cfg.C_min, False

    k_star = elbow_index(scores_desc)
    mean_s = float(np.mean(scores_desc)) if scores_desc else 0.0
    elbow_score = scores_desc[k_star] if k_star < n else scores_desc[-1]

    # f(k*) >= mean_s（群体均值）⇒ 扩容
    if elbow_score >= mean_s:
        new_c = min(cfg.C_min + cfg.delta_step, cfg.C_max)
        keep = min(n, new_c)
        return keep, new_c, new_c > cfg.C_min

    keep = max(1, min(k_star + 1, cfg.C_min))
    return keep, cfg.C_min, False


def select_prune_ids(
    id_score_pairs: list[tuple[str, float]],
    cfg: CapacityConfig,
) -> tuple[list[str], int, bool]:
    """按 S 降序，返回应删除的 id 列表，以及更新后的 C_min、是否扩容。"""
    if not id_score_pairs:
        return [], cfg.C_min, False
    ordered = sorted(id_score_pairs, key=lambda x: x[1], reverse=True)
    scores = [s for _, s in ordered]
    keep, new_c, expanded = regulate_capacity(scores, cfg)
    prune_ids = [mid for mid, _ in ordered[keep:]]
    return prune_ids, new_c, expanded
