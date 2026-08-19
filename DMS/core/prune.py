"""基于 Elbow 的容量调节与长尾修剪，对应 Adaptive Memory Regulation。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class CapacityConfig:
    C_min: int = 80  # 低于此规模不修剪；修剪后也至少保留这么多
    C_max: int = 300  # 容量上限
    delta_step: int = 20  # 高质量饱和时的扩容步长


def elbow_index(scores_desc: list[float]) -> int:
    """在降序生存价值曲线上找肘点 k* = argmax ∇²f(k)。"""
    n = len(scores_desc)
    if n < 3:
        return max(0, n - 1)
    f = np.asarray(scores_desc, dtype=np.float64)
    second = f[:-2] - 2.0 * f[1:-1] + f[2:]
    k_star = int(np.argmax(second)) + 1
    return k_star


def regulate_capacity(
    scores_desc: list[float],
    cfg: CapacityConfig,
) -> tuple[int, int, bool]:
    """
    返回 (keep_count, new_C_min, expanded)。
    肘点处价值仍不低于均值时扩容；否则按肘点剪长尾，保留数不低于 C_min。
    """
    n = len(scores_desc)
    if n <= cfg.C_min:
        return n, cfg.C_min, False

    k_star = elbow_index(scores_desc)
    mean_s = float(np.mean(scores_desc)) if scores_desc else 0.0
    elbow_score = scores_desc[k_star] if k_star < n else scores_desc[-1]

    if elbow_score >= mean_s:
        new_c = min(cfg.C_min + cfg.delta_step, cfg.C_max)
        keep = min(n, new_c)
        return keep, new_c, new_c > cfg.C_min

    keep = max(k_star + 1, cfg.C_min)
    keep = min(keep, n)
    return keep, cfg.C_min, False


def select_prune_ids(
    id_score_pairs: list[tuple[str, float]],
    cfg: CapacityConfig,
) -> tuple[list[str], int, bool]:
    """按 S 降序，返回应删除的 id，以及更新后的 C_min、是否扩容。"""
    if not id_score_pairs:
        return [], cfg.C_min, False
    ordered = sorted(id_score_pairs, key=lambda x: x[1], reverse=True)
    scores = [s for _, s in ordered]
    keep, new_c, expanded = regulate_capacity(scores, cfg)
    prune_ids = [mid for mid, _ in ordered[keep:]]
    return prune_ids, new_c, expanded
