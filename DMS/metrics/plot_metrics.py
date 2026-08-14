"""从 round_metrics.csv / json 画论文风格曲线。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


class MetricsPlotter:
    """读取 RoundMetricsRecorder 落盘结果并出图（可选 matplotlib）。"""

    def __init__(self, results_dir: str | Path):
        self.results_dir = Path(results_dir)

    def load_rounds(self) -> list[dict[str, Any]]:
        json_path = self.results_dir / "round_metrics.json"
        if json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return list(data.get("rounds") or [])
        csv_path = self.results_dir / "round_metrics.csv"
        if not csv_path.exists():
            return []
        with csv_path.open(encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def plot_core_curves(self, out_name: str = "evolution_curves.png") -> Path | None:
        """
        一张图：SR / MRR / 平均步数 / 记忆条数随 round 变化。
        未安装 matplotlib 时返回 None。
        """
        rounds = self.load_rounds()
        if not rounds:
            return None
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("未安装 matplotlib，跳过绘图。pip install matplotlib")
            return None

        xs = [int(float(r["round"])) for r in rounds]
        sr = [float(r["sr"]) * 100 for r in rounds]
        mrr = [float(r["mrr"]) * 100 for r in rounds]
        steps = [float(r["avg_steps_per_task"]) for r in rounds]
        mem = [float(r["final_memory_size"]) for r in rounds]
        tokens = [float(r.get("avg_tokens_per_task") or 0) for r in rounds]

        fig, axes = plt.subplots(2, 2, figsize=(10, 7))
        ax = axes[0, 0]
        ax.plot(xs, sr, marker="o")
        ax.set_title("SR (Fig.5a)")
        ax.set_xlabel("Round")
        ax.set_ylabel("Success Rate (%)")
        ax.set_xticks(xs)

        ax = axes[0, 1]
        ax.plot(xs, mrr, marker="o", color="C1")
        ax.set_title("MRR (Fig.4)")
        ax.set_xlabel("Round")
        ax.set_ylabel("Memory Reuse (%)")
        ax.set_xticks(xs)

        ax = axes[1, 0]
        ax.plot(xs, steps, marker="o", color="C2", label="steps")
        ax.set_xlabel("Round")
        ax.set_ylabel("Avg steps")
        ax.set_xticks(xs)
        ax2 = ax.twinx()
        ax2.plot(xs, tokens, marker="s", color="C3", alpha=0.7, label="tokens")
        ax2.set_ylabel("Avg tokens")
        ax.set_title("Efficiency (Fig.7)")

        ax = axes[1, 1]
        ax.plot(xs, mem, marker="o", color="C4")
        ax.set_title("Memory size (Fig.6)")
        ax.set_xlabel("Round")
        ax.set_ylabel("#entries")
        ax.set_xticks(xs)

        fig.tight_layout()
        out = self.results_dir / out_name
        fig.savefig(out, dpi=150)
        plt.close(fig)
        return out
