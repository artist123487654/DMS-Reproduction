"""这个脚本计算生存价值 S(m) = Utility × AdaptiveDecay × Reliability，对应论文3.2.3. SELF-REGULATION STRATEGY。"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SurvivalConfig:
    v_new: float = 1.0  # 新记忆的冷启动保护
    t_base: float = 30.0  # 基础半衰期
    mu: float = 15.0  # 半衰期调整因子
    beta: float = 0.5  # 衰减因子
    gamma: float = 1.0  # 可靠性因子

def marginal_utility(n_i: int, v_new: float, is_new: bool) -> float:
    """边际效用。U(n) = ln(1+n) + v_new（v_new是对新记忆的冷启动保护）"""
    bonus = v_new if is_new else 0.0
    return math.log1p(n_i) + bonus

def half_life(n_i: int, t_base: float, mu: float) -> float:
    """半衰期。t_half(n) = t_base + μ · ln(1+n)"""
    return t_base + mu * math.log1p(n_i)

def adaptive_decay(delta_t: float, n_i: int, beta: float, t_base: float, mu: float) -> float:
    """自适应衰减。D = 1 / (1 + exp(β(Δt - t_half)))"""
    th = half_life(n_i, t_base, mu)
    return 1.0 / (1.0 + math.exp(beta * (delta_t - th)))


def reliability(k_i: int, gamma: float) -> float:
    """可靠性。P(k) = 1 / (1 + γk)"""
    return 1.0 / (1.0 + gamma * k_i)


def survival_value(
    n_i: int,
    delta_t: float,
    k_i: int,
    cfg: SurvivalConfig,
    *,
    is_new: bool = False,
) -> float:
    """计算多因子生存价值 S。"""
    u = marginal_utility(n_i, cfg.v_new, is_new)
    d = adaptive_decay(delta_t, n_i, cfg.beta, cfg.t_base, cfg.mu)
    p = reliability(k_i, cfg.gamma)
    return u * d * p