"""DMS 闭环：检索 →（mutation）执行结果回流 → 更新 S → 修剪。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .bank import MemoryBank
from .mutation import MutationConfig, apply_inplace_evolution, should_mutate
from .prune import CapacityConfig, select_prune_ids
from .retrieval import (
    DualFactorRetriever,
    Embedder,
    EmbeddingConfig,
    RetrievalConfig,
    build_embedder,
)
from .risk import RiskConfig, RiskState, should_suppress_plan
from .survival import SurvivalConfig, survival_value
from .types import MemoryEntry, Plan, TrajectoryStep


@dataclass
class DMSConfig:
    survival: SurvivalConfig
    capacity: CapacityConfig
    retrieval: RetrievalConfig
    embedding: EmbeddingConfig
    mutation: MutationConfig
    risk: RiskConfig
    storage_root: str = "memory_banks/dms"


def load_config(path: str | Path) -> DMSConfig:
    raw: dict[str, Any] = {}
    p = Path(path)
    if p.exists():
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    s = raw.get("survival", {})
    c = raw.get("capacity", {})
    r = raw.get("retrieval", {})
    e = raw.get("embedding", {})
    m = raw.get("mutation", {})
    k = raw.get("risk", {})
    st = raw.get("storage", {})
    return DMSConfig(
        survival=SurvivalConfig(**{kk: s[kk] for kk in SurvivalConfig.__dataclass_fields__ if kk in s}),
        capacity=CapacityConfig(**{kk: c[kk] for kk in CapacityConfig.__dataclass_fields__ if kk in c}),
        retrieval=RetrievalConfig(**{kk: r[kk] for kk in RetrievalConfig.__dataclass_fields__ if kk in r}),
        embedding=EmbeddingConfig(**{kk: e[kk] for kk in EmbeddingConfig.__dataclass_fields__ if kk in e}),
        mutation=MutationConfig(**{kk: m[kk] for kk in MutationConfig.__dataclass_fields__ if kk in m}),
        risk=RiskConfig(**{kk: k[kk] for kk in RiskConfig.__dataclass_fields__ if kk in k}),
        storage_root=st.get("root", "memory_banks/dms"),
    )


class DarwinianMemorySystem:
    """训练免费的自调节记忆系统门面。"""

    def __init__(
        self,
        cfg: DMSConfig | None = None,
        *,
        embedder: Embedder | None = None,
        bank: MemoryBank | None = None,
    ):
        self.cfg = cfg or DMSConfig(
            survival=SurvivalConfig(),
            capacity=CapacityConfig(),
            retrieval=RetrievalConfig(),
            embedding=EmbeddingConfig(),
            mutation=MutationConfig(),
            risk=RiskConfig(),
        )
        self.bank = bank or MemoryBank(self.cfg.storage_root)
        self.retriever = DualFactorRetriever(
            self.bank,
            embedder=embedder or build_embedder(self.cfg.embedding),
            cfg=self.cfg.retrieval,
        )
        self.risk_state = RiskState(t_global=self.cfg.risk.t_global_init)
        self.logical_step = 0
        self.stats = {
            "added": 0,
            "reused": 0,
            "mutated": 0,
            "evolved": 0,
            "pruned": 0,
            "suppressed": 0,
        }

    def tick(self) -> None:
        self.logical_step += 1

    # ----- 风险门控（Planner 出 plan 后可调用）-----
    def plan_suppressed(self, plan: Plan) -> bool:
        """用历史同意图的失败统计做抑制；无历史则放行。"""
        hits = self.retriever.retrieve(plan)
        if not hits:
            return False
        entry, _ = hits[0]
        bad, _, _ = should_suppress_plan(
            entry.fail_count, entry.success_count, self.risk_state, self.cfg.risk
        )
        if bad:
            self.stats["suppressed"] += 1
        return bad

    # ----- 检索 / mutation 决策 -----
    def query(self, plan: Plan) -> tuple[MemoryEntry | None, float, bool]:
        """
        返回 (命中记忆, score, 是否 mutation)。
        mutation=True 时调用方应让 Actor 重跑而非 Replay。
        """
        hits = self.retriever.retrieve(plan)
        if not hits:
            return None, 0.0, True  # 未命中 → 必须生成
        entry, score = hits[0]
        mutate = should_mutate(self.cfg.mutation)
        if mutate:
            self.stats["mutated"] += 1
            return entry, score, True
        self.stats["reused"] += 1
        self.bank.touch_reuse(entry.id, self.logical_step)
        return entry, score, False

    # ----- 执行结果回流 -----
    def commit_success(
        self,
        plan: Plan,
        trajectory: list[TrajectoryStep],
        *,
        from_memory: MemoryEntry | None = None,
        mutated: bool = False,
        description: str = "",
    ) -> MemoryEntry | None:
        """成功轨迹写入或进化替换，然后尝试修剪。"""
        self.risk_state.update_global(True, self.cfg.risk)

        if mutated and from_memory is not None:
            evolved = apply_inplace_evolution(
                from_memory,
                trajectory,
                success=True,
                logical_step=self.logical_step,
            )
            # 本次成功执行计入 plan 级声誉（Si），与是否进化替换无关
            from_memory.success_count += 1
            from_memory.meta.last_used_step = self.logical_step
            emb_pre, emb_goal = self.retriever.embed_plan(plan)
            self.bank.update_entry(from_memory, emb_pre=emb_pre, emb_goal=emb_goal)
            if evolved:
                self.stats["evolved"] += 1
            self.maybe_prune()
            return from_memory

        if len(trajectory) <= 1:
            return None  # 碎片不入库

        emb_pre, emb_goal = self.retriever.embed_plan(plan)
        entry = self.bank.add(
            plan,
            trajectory,
            logical_step=self.logical_step,
            success=True,
            description=description,
            emb_pre=emb_pre,
            emb_goal=emb_goal,
        )
        self.stats["added"] += 1
        self.maybe_prune()
        return entry

    def commit_failure(
        self,
        plan: Plan,
        *,
        from_memory: MemoryEntry | None = None,
    ) -> None:
        """失败：抬高 K_i / F_i，推动 Survival 下降。"""
        self.risk_state.update_global(False, self.cfg.risk)
        if from_memory is None:
            return
        from_memory.fail_count += 1
        from_memory.meta.fail_verify_count += 1
        from_memory.meta.last_used_step = self.logical_step
        self.bank.update_entry(from_memory)
        self.maybe_prune()

    # ----- Survival + Prune -----
    def score_entry(self, entry: MemoryEntry) -> float:
        delta_t = max(0, self.logical_step - entry.meta.last_used_step)
        is_new = entry.meta.reuse_count == 0 and delta_t < self.cfg.survival.t_base
        return survival_value(
            entry.meta.reuse_count,
            float(delta_t),
            entry.meta.fail_verify_count,
            self.cfg.survival,
            is_new=is_new,
        )

    def maybe_prune(self) -> list[str]:
        size = len(self.bank)
        if size <= self.cfg.capacity.C_min:
            return []
        pairs = [(e.id, self.score_entry(e)) for e in self.bank.all_entries(load_traj=False)]
        prune_ids, new_c, _expanded = select_prune_ids(pairs, self.cfg.capacity)
        self.cfg.capacity.C_min = new_c
        n = self.bank.delete_many(prune_ids)
        self.stats["pruned"] += n
        return prune_ids

    def memory_size(self) -> int:
        return len(self.bank)
