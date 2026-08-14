"""三种记忆后端：A 无记忆 / B 静态追加 / DMS 达尔文。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from core.bank import MemoryBank
from core.regulate import DarwinianMemorySystem
from core.retrieval import DualFactorRetriever, Embedder, EmbeddingConfig, RetrievalConfig, build_embedder
from core.types import MemoryEntry, Plan, TrajectoryStep


@dataclass
class MemoryDecision:
    entry: MemoryEntry | None
    score: float
    mutate: bool


class MemoryBackend(Protocol):
    name: str

    def on_step_begin(self) -> None: ...
    def decide(self, plan: Plan) -> MemoryDecision: ...
    def suppress(self, plan: Plan) -> bool: ...
    def commit(
        self,
        plan: Plan,
        trajectory: list[TrajectoryStep],
        *,
        success: bool,
        decision: MemoryDecision,
    ) -> None: ...
    def size(self) -> int: ...


@dataclass
class ZeroShotMemory:
    """Baseline A：永不读写记忆。"""

    name: str = "baseline_a_zeroshot"

    def on_step_begin(self) -> None:
        return

    def decide(self, plan: Plan) -> MemoryDecision:
        return MemoryDecision(entry=None, score=0.0, mutate=True)

    def suppress(self, plan: Plan) -> bool:
        return False

    def commit(self, plan, trajectory, *, success, decision) -> None:
        return

    def size(self) -> int:
        return 0


@dataclass
class StaticAppendMemory:
    """Baseline B：只追加、不算 S、不修剪。"""

    bank: MemoryBank
    retriever: DualFactorRetriever | None = None
    embedder: Embedder | None = None
    name: str = "baseline_b_static"
    logical_step: int = 0
    _log: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.retriever is None:
            emb = self.embedder or build_embedder()
            self.retriever = DualFactorRetriever(
                self.bank, emb, RetrievalConfig(min_score=0.25)
            )

    def on_step_begin(self) -> None:
        self.logical_step += 1

    def decide(self, plan: Plan) -> MemoryDecision:
        hits = self.retriever.retrieve(plan)
        if not hits:
            return MemoryDecision(None, 0.0, True)
        entry, score = hits[0]
        # 静态记忆：命中则直接复放，无 mutation
        return MemoryDecision(entry, score, False)

    def suppress(self, plan: Plan) -> bool:
        return False

    def commit(self, plan, trajectory, *, success, decision) -> None:
        if not success or len(trajectory) <= 1:
            return
        emb_pre, emb_goal = self.retriever.embed_plan(plan)
        self.bank.add(
            plan,
            trajectory,
            logical_step=self.logical_step,
            success=True,
            emb_pre=emb_pre,
            emb_goal=emb_goal,
        )
        self._log.append(plan.goal)

    def size(self) -> int:
        return len(self.bank)


@dataclass
class DarwinianBackend:
    """DMS：完整自调节记忆。"""

    dms: DarwinianMemorySystem
    name: str = "dms"

    def on_step_begin(self) -> None:
        self.dms.tick()

    def decide(self, plan: Plan) -> MemoryDecision:
        entry, score, mutate = self.dms.query(plan)
        return MemoryDecision(entry=entry, score=score, mutate=mutate)

    def suppress(self, plan: Plan) -> bool:
        return self.dms.plan_suppressed(plan)

    def commit(self, plan, trajectory, *, success, decision) -> None:
        if success:
            self.dms.commit_success(
                plan,
                trajectory,
                from_memory=decision.entry,
                mutated=decision.mutate and decision.entry is not None,
            )
        else:
            self.dms.commit_failure(plan, from_memory=decision.entry)

    def size(self) -> int:
        return self.dms.memory_size()


def build_backend(
    kind: str,
    storage_root: str,
    dms: DarwinianMemorySystem | None = None,
    *,
    embedder: Embedder | None = None,
    embedding_cfg: EmbeddingConfig | None = None,
) -> MemoryBackend:
    """构建记忆后端。"""
    kind = kind.lower()
    if kind in {"a", "zero", "zeroshot", "baseline_a"}:
        return ZeroShotMemory()
    if kind in {"b", "static", "baseline_b"}:
        bank = MemoryBank(storage_root)
        emb = embedder or build_embedder(embedding_cfg)
        return StaticAppendMemory(bank=bank, embedder=emb)
    if kind in {"dms", "c", "darwinian"}:
        if dms is None:
            raise ValueError("DMS backend 需要传入 DarwinianMemorySystem")
        return DarwinianBackend(dms=dms)
    raise ValueError(f"未知 backend: {kind}")
