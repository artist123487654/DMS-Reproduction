"""贝叶斯声誉与风险抑制（§3.2.4），对应论文3.2.4. RISK ASSESSMENT AND FEEDBACK REGULATION"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class RiskConfig:
    m: float = 4.0  # 先验强度
    t_global_init: float = 0.3  # 全局失败率初值
    lambda_pen: float = 0.3  # 动态阈值敏感度
    tau_base: float = 0.55  # 基础拒绝阈值


@dataclass
class RiskState:
    """维护全局失败率，供动态阈值使用。"""

    total_success: int = 0
    total_fail: int = 0
    t_global: float = 0.3

    def update_global(self, success: bool, cfg: RiskConfig) -> None:
        if success:
            self.total_success += 1
        else:
            self.total_fail += 1
        n = self.total_success + self.total_fail
        if n == 0:
            self.t_global = cfg.t_global_init
        else:
            # 观测失败率向 t_global_init 贝叶斯平滑
            self.t_global = (self.total_fail + cfg.m * cfg.t_global_init) / (n + cfg.m)


def expected_fail_prob(f_i: int, s_i: int, t_global: float, m: float) -> float:
    """期望失败概率。μ_i = (F + M·T_global) / (F + S + M)"""
    return (f_i + m * t_global) / (f_i + s_i + m)


def posterior_std(mu: float, f_i: int, s_i: int, m: float) -> float:
    """后验标准差。σ_i = sqrt( μ(1-μ) / (F+S+M+1) )"""
    return math.sqrt(max(mu * (1.0 - mu), 0.0) / (f_i + s_i + m + 1.0))


def risk_score(f_i: int, s_i: int, t_global: float, cfg: RiskConfig) -> float:
    """风险得分：t_i = μ_i - σ_i。"""
    mu = expected_fail_prob(f_i, s_i, t_global, cfg.m)
    sigma = posterior_std(mu, f_i, s_i, cfg.m)
    return mu - sigma


def reject_threshold(t_global: float, cfg: RiskConfig) -> float:
    """拒绝阈值。τ = τ_base · (1 - λ · T_global)"""
    return cfg.tau_base * (1.0 - cfg.lambda_pen * t_global)


def should_suppress_plan(
    f_i: int,
    s_i: int,
    state: RiskState,
    cfg: RiskConfig,
) -> tuple[bool, float, float]:
    """若 t_i > τ 则抑制该计划。返回 (suppress, t_i, τ)。"""
    ti = risk_score(f_i, s_i, state.t_global, cfg)
    tau = reject_threshold(state.t_global, cfg)
    return ti > tau, ti, tau
