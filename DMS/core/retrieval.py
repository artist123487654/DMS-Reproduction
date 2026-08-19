"""双因子检索：Score = sim(pre)·sim(goal), 对应论文3.2.2. MEMORY UTILIZATION MECHANISM的Dual-Factor Retrieval。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .bank import MemoryBank, blob_to_emb
from .types import MemoryEntry, Plan


class Embedder(Protocol):
    def encode(self, text: str) -> np.ndarray: ...


@dataclass
class RetrievalConfig:
    top_k: int = 1
    min_score: float = 0.55


@dataclass
class EmbeddingConfig:
    """本地词向量嵌入模型。"""

    model_name_or_path: str = "BAAI/bge-small-en-v1.5"
    device: str = "cpu"
    normalize: bool = True


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float32).ravel()
    b = np.asarray(b, dtype=np.float32).ravel()
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < 1e-8 or nb < 1e-8:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class SentenceTransformerEmbedder:
    """本地词向量嵌入模型，使用 sentence-transformers 库。"""

    def __init__(
        self,
        model_name_or_path: str,
        device: str = "cpu",
        normalize: bool = True,
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError("需要安装 sentence-transformers，pip install sentence-transformers") from e
        self.normalize = normalize
        self.model_name_or_path = model_name_or_path
        self.model = SentenceTransformer(model_name_or_path, device=device)

    def encode(self, text: str) -> np.ndarray:
        vec = self.model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=self.normalize,
        )
        return np.asarray(vec, dtype=np.float32).ravel()


def resolve_embedding_source(cfg: EmbeddingConfig) -> str:
    """优先环境变量，便于指向已下载目录。"""
    for key in ("EMBEDDING_MODEL_PATH", "EMBEDDING_MODEL"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return cfg.model_name_or_path


def build_embedder(cfg: EmbeddingConfig | None = None) -> Embedder:
    cfg = cfg or EmbeddingConfig()
    source = resolve_embedding_source(cfg)
    print(f"Embedding: source={source}  device={cfg.device}")
    return SentenceTransformerEmbedder(
        model_name_or_path=source,
        device=cfg.device,
        normalize=cfg.normalize,
    )


class DualFactorRetriever:
    def __init__(
        self,
        bank: MemoryBank,
        embedder: Embedder | None = None,
        cfg: RetrievalConfig | None = None,
    ):
        self.bank = bank
        self.embedder = embedder or build_embedder()
        self.cfg = cfg or RetrievalConfig()

    def embed_plan(self, plan: Plan) -> tuple[np.ndarray, np.ndarray]:
        return self.embedder.encode(plan.precondition), self.embedder.encode(plan.goal)

    def score(self, query: Plan, emb_pre: np.ndarray, emb_goal: np.ndarray) -> float:
        q_pre, q_goal = self.embed_plan(query)
        return cosine(q_pre, emb_pre) * cosine(q_goal, emb_goal)

    def retrieve(self, query: Plan) -> list[tuple[MemoryEntry, float]]:
        hits: list[tuple[MemoryEntry, float]] = []
        for row in self.bank.iter_index_rows():
            emb_pre = blob_to_emb(row["emb_pre"])
            emb_goal = blob_to_emb(row["emb_goal"])
            if emb_pre is None or emb_goal is None:
                plan = Plan(row["precondition"], row["goal"])
                emb_pre, emb_goal = self.embed_plan(plan)
                self.bank.set_embeddings(row["id"], emb_pre, emb_goal)
            s = self.score(query, emb_pre, emb_goal)
            if s >= self.cfg.min_score:
                entry = self.bank.get(row["id"], load_traj=True)
                if entry is not None:
                    hits.append((entry, s))
        hits.sort(key=lambda x: x[1], reverse=True)
        return hits[: self.cfg.top_k]
