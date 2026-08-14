"""MemoryBank：SQLite 索引 + 轨迹文件存储。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Iterable

import numpy as np

from .types import MemoryEntry, MemoryMeta, Plan, TrajectoryStep


class MemoryBank:
    """
    将Plan和Trajectory分开存储：
    - SQLite：存储Plan和Trajectory的关联关系
    - traj/*.json：存储Trajectory
    """

    def __init__(self, root: str | Path, db_name: str = "index.sqlite", traj_dirname: str = "traj"):
        self.root = Path(root)
        self.traj_dir = self.root / traj_dirname
        self.root.mkdir(parents=True, exist_ok=True)
        self.traj_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / db_name
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                precondition TEXT NOT NULL,
                goal TEXT NOT NULL,
                success INTEGER NOT NULL DEFAULT 1,
                created_step INTEGER NOT NULL,
                last_used_step INTEGER NOT NULL,
                reuse_count INTEGER NOT NULL DEFAULT 0,
                fail_verify_count INTEGER NOT NULL DEFAULT 0,
                success_count INTEGER NOT NULL DEFAULT 0,
                fail_count INTEGER NOT NULL DEFAULT 0,
                description TEXT NOT NULL DEFAULT '',
                traj_len INTEGER NOT NULL DEFAULT 0,
                emb_pre BLOB,
                emb_goal BLOB
            )
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "MemoryBank":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # ---------- 路径解码 ----------
    def traj_path(self, mem_id: str) -> Path:
        return self.traj_dir / f"{mem_id}.json"

    # ---------- 增加记忆 ----------
    def add(
        self,
        plan: Plan,
        trajectory: list[TrajectoryStep],
        *,
        logical_step: int,
        success: bool = True,
        description: str = "",
        emb_pre: np.ndarray | None = None,
        emb_goal: np.ndarray | None = None,
        mem_id: str | None = None,
    ) -> MemoryEntry:
        # 过滤单步原子轨迹，避免碎片化
        if len(trajectory) <= 1:
            raise ValueError("拒绝 |τ|=1 的碎片记忆")

        mem_id = mem_id or str(uuid.uuid4())
        entry = MemoryEntry(
            id=mem_id,
            plan=plan,
            trajectory=list(trajectory),
            meta=MemoryMeta(
                success=success,
                created_step=logical_step,
                last_used_step=logical_step,
                reuse_count=0,
                description=description,
            ),
            success_count=1 if success else 0,
            fail_count=0 if success else 1,
        )
        self._write_traj(entry)
        self._conn.execute(
            """
            INSERT INTO memories (
                id, precondition, goal, success, created_step, last_used_step,
                reuse_count, fail_verify_count, success_count, fail_count,
                description, traj_len, emb_pre, emb_goal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id,
                plan.precondition,
                plan.goal,
                int(success),
                logical_step,
                logical_step,
                0,
                0,
                entry.success_count,
                entry.fail_count,
                description,
                len(trajectory),
                _emb_to_blob(emb_pre),
                _emb_to_blob(emb_goal),
            ),
        )
        self._conn.commit()
        return entry

    # ---------- 查记忆 ----------
    def get(self, mem_id: str, load_traj: bool = True) -> MemoryEntry | None:
        row = self._conn.execute("SELECT * FROM memories WHERE id=?", (mem_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row, load_traj=load_traj)

    # ---------- 删记忆 ----------
    def delete(self, mem_id: str) -> None:
        self._conn.execute("DELETE FROM memories WHERE id=?", (mem_id,))
        self._conn.commit()
        p = self.traj_path(mem_id)
        if p.exists():
            p.unlink()

    def delete_many(self, mem_ids: Iterable[str]) -> int:
        ids = list(mem_ids)
        for mid in ids:
            self.delete(mid)
        return len(ids)

    # ---------- 查记忆数量 ----------
    def __len__(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0])

    # ---------- 查所有记忆 ----------
    def all_entries(self, load_traj: bool = False) -> list[MemoryEntry]:
        rows = self._conn.execute("SELECT * FROM memories").fetchall()
        return [self._row_to_entry(r, load_traj=load_traj) for r in rows]

    # ---------- 更新记忆 ----------
    def update_entry(self, entry: MemoryEntry, *, emb_pre: np.ndarray | None = None, emb_goal: np.ndarray | None = None) -> None:
        self._write_traj(entry)
        self._conn.execute(
            """
            UPDATE memories SET
                precondition=?, goal=?, success=?, created_step=?, last_used_step=?,
                reuse_count=?, fail_verify_count=?, success_count=?, fail_count=?,
                description=?, traj_len=?,
                emb_pre=COALESCE(?, emb_pre),
                emb_goal=COALESCE(?, emb_goal)
            WHERE id=?
            """,
            (
                entry.plan.precondition,
                entry.plan.goal,
                int(entry.meta.success),
                entry.meta.created_step,
                entry.meta.last_used_step,
                entry.meta.reuse_count,
                entry.meta.fail_verify_count,
                entry.success_count,
                entry.fail_count,
                entry.meta.description,
                entry.length,
                _emb_to_blob(emb_pre),
                _emb_to_blob(emb_goal),
                entry.id,
            ),
        )
        self._conn.commit()

    def touch_reuse(self, mem_id: str, logical_step: int) -> None:
        self._conn.execute(
            """
            UPDATE memories
            SET reuse_count = reuse_count + 1, last_used_step=?
            WHERE id=?
            """,
            (logical_step, mem_id),
        )
        self._conn.commit()

    def bump_verify_fail(self, mem_id: str) -> None:
        self._conn.execute(
            "UPDATE memories SET fail_verify_count = fail_verify_count + 1 WHERE id=?",
            (mem_id,),
        )
        self._conn.commit()

    # ---------- 设置嵌入 ----------
    def set_embeddings(self, mem_id: str, emb_pre: np.ndarray, emb_goal: np.ndarray) -> None:
        self._conn.execute(
            "UPDATE memories SET emb_pre=?, emb_goal=? WHERE id=?",
            (_emb_to_blob(emb_pre), _emb_to_blob(emb_goal), mem_id),
        )
        self._conn.commit()

    def iter_index_rows(self) -> list[sqlite3.Row]:
        return list(self._conn.execute("SELECT * FROM memories").fetchall())

    # ---------- 内部 ----------
    def _write_traj(self, entry: MemoryEntry) -> None:
        payload = [
            {
                "action": s.action,
                "observation_ref": s.observation_ref,
                "ui_hint": s.ui_hint,
            }
            for s in entry.trajectory
        ]
        self.traj_path(entry.id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _load_traj(self, mem_id: str) -> list[TrajectoryStep]:
        p = self.traj_path(mem_id)
        if not p.exists():
            return []
        raw = json.loads(p.read_text(encoding="utf-8"))
        return [
            TrajectoryStep(
                action=item.get("action", {}),
                observation_ref=item.get("observation_ref"),
                ui_hint=item.get("ui_hint"),
            )
            for item in raw
        ]

    def _row_to_entry(self, row: sqlite3.Row, load_traj: bool) -> MemoryEntry:
        traj = self._load_traj(row["id"]) if load_traj else []
        return MemoryEntry(
            id=row["id"],
            plan=Plan(precondition=row["precondition"], goal=row["goal"]),
            trajectory=traj,
            meta=MemoryMeta(
                success=bool(row["success"]),
                created_step=row["created_step"],
                last_used_step=row["last_used_step"],
                reuse_count=row["reuse_count"],
                fail_verify_count=row["fail_verify_count"],
                description=row["description"] or "",
            ),
            success_count=row["success_count"],
            fail_count=row["fail_count"],
        )


def _emb_to_blob(vec: np.ndarray | None) -> bytes | None:
    if vec is None:
        return None
    arr = np.asarray(vec, dtype=np.float32)
    return arr.tobytes()


def blob_to_emb(blob: bytes | None) -> np.ndarray | None:
    if blob is None:
        return None
    return np.frombuffer(blob, dtype=np.float32).copy()
