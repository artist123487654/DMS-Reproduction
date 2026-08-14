#!/usr/bin/env python3
"""列出 / 导出 Preferred 或 Full 任务清单（不跑评测）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AW = ROOT.parent / "android_world"
for p in (ROOT, AW):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from runners.task_suites import resolve_tasks, summarize_by_app  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--suite", default="preferred", choices=["test", "min", "preferred", "full", "android"])
    p.add_argument("--per_app", type=int, default=2)
    p.add_argument("--seed", type=int, default=30)
    p.add_argument("--out", type=str, default=None, help="写出任务列表（每行一个）")
    p.add_argument("--json", action="store_true", help="打印 App 汇总 JSON")
    args = p.parse_args()

    tasks, label = resolve_tasks(suite=args.suite, seed=args.seed, per_app=args.per_app)
    info = summarize_by_app(tasks)
    print(f"suite={label} n_tasks={info['n_tasks']} n_apps={info['n_apps']}")
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        for t in tasks:
            print(t)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(tasks) + "\n", encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
