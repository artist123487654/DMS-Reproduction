"""三种记忆后端：A 无记忆 / B 静态追加 / DMS 达尔文。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from core.bank import MemoryBank
from core.regulate import DarwinianMemorySystem
from core.retrieval import DualFactorRetriever, Embedder, EmbeddingConfig, RetrievalConfig, build_embedder
from core.types import MemoryEntry, Plan, TrajectoryStep, should_persist_trajectory


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
    def on_episode_end(self, env_success: bool) -> None: ...
    def begin_episode(self) -> None: ...
    def size(self) -> int: ...


@dataclass
class ZeroShotMemory:
    name: str = "baseline_a_zeroshot"

    def on_step_begin(self) -> None:
        return

    def decide(self, plan: Plan) -> MemoryDecision:
        return MemoryDecision(entry=None, score=0.0, mutate=True)

    def suppress(self, plan: Plan) -> bool:
        return False

    def commit(self, plan, trajectory, *, success, decision) -> None:
        return

    def on_episode_end(self, env_success: bool) -> None:
        return

    def begin_episode(self) -> None:
        return

    def size(self) -> int:
        return 0


@dataclass
class StaticAppendMemory:
    """Baseline B：静态追加，只增不剪。"""

    bank: MemoryBank
    retriever: DualFactorRetriever | None = None
    embedder: Embedder | None = None
    retrieval_cfg: RetrievalConfig | None = None
    name: str = "baseline_b_static"
    logical_step: int = 0
    _log: list[str] = field(default_factory=list)
    _episode_added: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.retriever is None:
            emb = self.embedder or build_embedder()
            cfg = self.retrieval_cfg or RetrievalConfig()
            self.retriever = DualFactorRetriever(self.bank, emb, cfg)

    def on_step_begin(self) -> None:
        self.logical_step += 1

    def decide(self, plan: Plan) -> MemoryDecision:
        hits = self.retriever.retrieve(plan)
        if not hits:
            return MemoryDecision(None, 0.0, True)
        entry, score = hits[0]
        return MemoryDecision(entry, score, False)

    def suppress(self, plan: Plan) -> bool:
        return False

    def commit(self, plan, trajectory, *, success, decision) -> None:
        if not success or not should_persist_trajectory(trajectory):
            return
        if decision.entry is not None:
            return
        emb_pre, emb_goal = self.retriever.embed_plan(plan)
        entry = self.bank.add(
            plan,
            trajectory,
            logical_step=self.logical_step,
            success=True,
            emb_pre=emb_pre,
            emb_goal=emb_goal,
        )
        self._episode_added.append(entry.id)
        self._log.append(plan.goal)

    def on_episode_end(self, env_success: bool) -> None:
        self._episode_added.clear()

    def begin_episode(self) -> None:
        self._episode_added.clear()

    def size(self) -> int:
        return len(self.bank)


@dataclass
class DarwinianBackend:
    """DMS：完整自调节记忆。"""

    dms: DarwinianMemorySystem
    name: str = "dms"
    _episode_ids: list[str] = field(default_factory=list)
    _episode_added: list[str] = field(default_factory=list)

    def on_step_begin(self) -> None:
        self.dms.tick()

    def decide(self, plan: Plan) -> MemoryDecision:
        entry, score, mutate = self.dms.query(plan)
        return MemoryDecision(entry=entry, score=score, mutate=mutate)

    def suppress(self, plan: Plan) -> bool:
        return self.dms.plan_suppressed(plan)

    def commit(self, plan, trajectory, *, success, decision) -> None:
        if success:
            exploring = bool(decision.mutate)
            if not should_persist_trajectory(trajectory, exploring=exploring):
                return
            before = self.dms.memory_size()
            entry = self.dms.commit_success(
                plan,
                trajectory,
                from_memory=decision.entry,
                mutated=decision.mutate and decision.entry is not None,
            )
            mid = getattr(entry, "id", None) or getattr(decision.entry, "id", None)
            if mid:
                mid = str(mid)
                self._episode_ids.append(mid)
                if entry is not None and self.dms.memory_size() > before:
                    self._episode_added.append(mid)
        else:
            self.dms.commit_failure(plan, from_memory=decision.entry)
            if decision.entry is not None:
                self._episode_ids.append(decision.entry.id)

    def on_episode_end(self, env_success: bool) -> None:
        if not env_success:
            if self._episode_added:
                n = self.dms.bank.delete_many(self._episode_added)
                self.dms.stats["pruned"] = int(self.dms.stats.get("pruned", 0)) + n
            self.dms.risk_state.update_global(False, self.dms.cfg.risk)
        self._episode_ids.clear()
        self._episode_added.clear()

    def begin_episode(self) -> None:
        self._episode_ids.clear()
        self._episode_added.clear()

    def size(self) -> int:
        return self.dms.memory_size()


def build_backend(
    kind: str,
    storage_root: str,
    dms: DarwinianMemorySystem | None = None,
    *,
    embedder: Embedder | None = None,
    embedding_cfg: EmbeddingConfig | None = None,
    retrieval_cfg: RetrievalConfig | None = None,
) -> MemoryBackend:
    kind = kind.lower()
    if kind in {"a", "zero", "zeroshot", "baseline_a"}:
        return ZeroShotMemory()
    if kind in {"b", "static", "baseline_b"}:
        bank = MemoryBank(storage_root)
        emb = embedder or build_embedder(embedding_cfg)
        return StaticAppendMemory(
            bank=bank, embedder=emb, retrieval_cfg=retrieval_cfg
        )
    if kind in {"dms", "c", "darwinian"}:
        if dms is None:
            raise ValueError("DMS backend 需要传入 DarwinianMemorySystem")
        return DarwinianBackend(dms=dms)
    raise ValueError(f"未知 backend: {kind}")
