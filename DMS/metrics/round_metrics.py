"""按轮次汇总指标并落盘。"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


# 默认任务难度（可用 complexity 覆盖）
_DEFAULT_DIFFICULTY: dict[str, str] = {
    "ContactsAddContact": "easy",
    "MarkorCreateNote": "medium",
    "FilesDeleteFile": "medium",
    "SimpleCalendarAddOneEvent": "hard",
    "MarkorCreateNoteAndSms": "hard",
}


class TaskDifficulty:
    """任务难度标注。"""

    @staticmethod
    def of(task_name: str, complexity: float | None = None) -> str:
        if task_name in _DEFAULT_DIFFICULTY:
            return _DEFAULT_DIFFICULTY[task_name]
        if complexity is None:
            return "medium"
        if complexity <= 1.0:
            return "easy"
        if complexity <= 2.0:
            return "medium"
        return "hard"


@dataclass
class RoundSnapshot:
    round: int
    total_tasks: int
    success_count: int
    sr: float
    sr_easy: float | None
    sr_medium: float | None
    sr_hard: float | None
    srr: float | None
    total_actions: int
    reused_actions: int
    mrr: float
    avg_steps_per_task: float
    avg_tokens_per_task: float
    avg_latency_seconds: float
    total_tokens: int
    final_memory_size: int
    peak_memory_size: int
    pruned_count: int
    memory_mb: float
    backend: str = ""


@dataclass
class RoundMetricsRecorder:
    """
    收集多轮任务结果，每轮结束写出核心指标。

    落盘：
      {out_dir}/round_metrics.json
      {out_dir}/round_metrics.csv
      {out_dir}/summary.json   # 与 CSV 同口径的精简汇总
    """

    out_dir: Path
    backend: str = ""
    model: str = ""
    memory_root: Path | None = None
    rounds: list[RoundSnapshot] = field(default_factory=list)
    # task_name -> [success_bool per round]
    _success_history: dict[str, list[bool]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.out_dir = Path(self.out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        if self.memory_root is not None:
            self.memory_root = Path(self.memory_root)

    @staticmethod
    def dir_size_mb(root: Path | None) -> float:
        if root is None or not Path(root).exists():
            return 0.0
        total = 0
        for p in Path(root).rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
        return total / (1024 * 1024)

    def _sr_by_difficulty(self, rows: list[dict[str, Any]], level: str) -> float | None:
        subset = [r for r in rows if r.get("difficulty") == level]
        if not subset:
            return None
        return sum(1 for r in subset if r.get("success")) / len(subset)

    def _compute_srr(self) -> float | None:
        """SRR = 连续成功对数 / 总成功次数（截至当前已记录的全部轮次）。"""
        pairs = 0
        successes = 0
        for seq in self._success_history.values():
            successes += sum(1 for x in seq if x)
            for i in range(len(seq) - 1):
                if seq[i] and seq[i + 1]:
                    pairs += 1
        if successes == 0:
            return None
        if all(len(seq) < 2 for seq in self._success_history.values()):
            return None
        return pairs / successes

    def record_round(
        self,
        *,
        round_idx: int,
        task_results: Iterable[dict[str, Any]],
        peak_memory_size: int,
        pruned_count: int,
        memory_root: Path | None = None,
    ) -> RoundSnapshot:
        rows = [r for r in task_results if "success" in r]
        n = len(rows)
        success_count = sum(1 for r in rows if r.get("success"))
        sr = success_count / n if n else 0.0

        for r in rows:
            name = str(r.get("task", ""))
            self._success_history.setdefault(name, []).append(bool(r.get("success")))

        total_actions = 0
        reused_actions = 0
        steps_sum = 0.0
        tokens_sum = 0
        latency_sum = 0.0
        for r in rows:
            m = r.get("metrics") or {}
            reused = int(m.get("reused_actions", 0))
            generated = int(m.get("generated_actions", 0))
            actor_steps = int(m.get("actor_steps", 0))
            # 优先用显式动作计数；否则回退 actor_steps
            if reused or generated:
                total_actions += reused + generated
                reused_actions += reused
            else:
                total_actions += actor_steps
                # replays 是 plan 级；无法精确还原动作，记 0 复用
            steps_sum += float(r.get("n_steps_logged") or m.get("actor_steps") or 0)
            tokens_sum += int(r.get("tokens") or 0)
            latency_sum += float(r.get("elapsed_sec") or 0.0)

        mrr = (reused_actions / total_actions) if total_actions else 0.0
        root = memory_root or self.memory_root
        final_mem = int(rows[-1].get("memory_size_after", 0)) if rows else 0
        peak = max(int(peak_memory_size), final_mem)

        snap = RoundSnapshot(
            round=round_idx + 1,  # 1-based
            total_tasks=n,
            success_count=success_count,
            sr=sr,
            sr_easy=self._sr_by_difficulty(rows, "easy"),
            sr_medium=self._sr_by_difficulty(rows, "medium"),
            sr_hard=self._sr_by_difficulty(rows, "hard"),
            srr=self._compute_srr(),
            total_actions=total_actions,
            reused_actions=reused_actions,
            mrr=mrr,
            avg_steps_per_task=(steps_sum / n) if n else 0.0,
            avg_tokens_per_task=(tokens_sum / n) if n else 0.0,
            avg_latency_seconds=(latency_sum / n) if n else 0.0,
            total_tokens=tokens_sum,
            final_memory_size=final_mem,
            peak_memory_size=peak,
            pruned_count=int(pruned_count),
            memory_mb=round(self.dir_size_mb(root), 4),
            backend=self.backend,
        )
        # 覆盖同 round 重跑；否则追加
        self.rounds = [x for x in self.rounds if x.round != snap.round]
        self.rounds.append(snap)
        self.rounds.sort(key=lambda x: x.round)
        self.flush()
        return snap

    def flush(self) -> None:
        payload = {
            "backend": self.backend,
            "model": self.model,
            "rounds": [asdict(r) for r in self.rounds],
        }
        json_path = self.out_dir / "round_metrics.json"
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        csv_path = self.out_dir / "round_metrics.csv"
        fieldnames = [
            "round",
            "total_tasks",
            "success_count",
            "sr",
            "sr_easy",
            "sr_medium",
            "sr_hard",
            "srr",
            "mrr",
            "total_actions",
            "reused_actions",
            "avg_steps_per_task",
            "avg_tokens_per_task",
            "avg_latency_seconds",
            "total_tokens",
            "final_memory_size",
            "peak_memory_size",
            "pruned_count",
            "memory_mb",
            "backend",
        ]
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in self.rounds:
                row = asdict(r)
                writer.writerow({k: row.get(k) for k in fieldnames})

        # 兼容旧 summary.json
        summary = {
            "backend": self.backend,
            "model": self.model,
            "summary": [
                {
                    "trial": r.round - 1,
                    "round": r.round,
                    "n": r.total_tasks,
                    "success_rate": r.sr,
                    "srr": r.srr,
                    "mrr": r.mrr,
                    "avg_steps": r.avg_steps_per_task,
                    "avg_tokens": r.avg_tokens_per_task,
                    "avg_latency_seconds": r.avg_latency_seconds,
                    "total_tokens": r.total_tokens,
                    "memory_size": r.final_memory_size,
                    "peak_memory_size": r.peak_memory_size,
                    "pruned_count": r.pruned_count,
                    "memory_mb": r.memory_mb,
                }
                for r in self.rounds
            ],
        }
        (self.out_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
