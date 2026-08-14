"""DMS × AndroidWorld 评测入口（由 scripts/*.sh 调用）。

示例：
  bash scripts/run_min.sh
  bash scripts/run_preferred.sh
  bash scripts/run_full_split.sh
  python runners/run_androidworld.py --suite preferred --list-tasks
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Type

ROOT = Path(__file__).resolve().parents[1]
AW_ROOT = ROOT.parent / "android_world"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if AW_ROOT.exists() and str(AW_ROOT) not in sys.path:
    sys.path.insert(0, str(AW_ROOT))

os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
os.environ.setdefault("GRPC_TRACE", "none")


def find_adb_path(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    # Linux / macOS 优先；Windows 候选靠后。不依赖特定用户名。
    candidates = [
        Path(os.environ.get("ANDROID_HOME", "")) / "platform-tools" / "adb",
        Path(os.environ.get("ANDROID_SDK_ROOT", "")) / "platform-tools" / "adb",
        Path.home() / "Android" / "Sdk" / "platform-tools" / "adb",
        Path.home() / "android-sdk" / "platform-tools" / "adb",
        Path.home() / "Library" / "Android" / "sdk" / "platform-tools" / "adb",
        Path(os.environ.get("ANDROID_HOME", "")) / "platform-tools" / "adb.exe",
        Path(os.environ.get("ANDROID_SDK_ROOT", "")) / "platform-tools" / "adb.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools" / "adb.exe",
        Path.home() / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools" / "adb.exe",
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    from shutil import which

    hit = which("adb")
    if hit:
        return hit
    raise EnvironmentError(
        "找不到 adb。请安装 Android SDK，把 platform-tools 加入 PATH，"
        "或设置 ANDROID_HOME / ANDROID_SDK_ROOT，或用 --adb_path 指定。"
    )


def _has_api_key() -> bool:
    for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "QWEN_API_KEY", "DASHSCOPE_API_KEY"):
        if os.environ.get(name):
            return True
    return False


def build_llm(model: str | None, base_url: str | None, provider: str | None):
    """必须配置真实 VLM API；未配置则提示并退出。"""
    if not _has_api_key() and not base_url and not os.environ.get("QWEN_BASE_URL"):
        print("没有配置模型：请设置 OPENROUTER_API_KEY 或 OPENAI_API_KEY 后再运行。")
        print("  例: export OPENROUTER_API_KEY='sk-or-...'")
        sys.exit(1)

    from models.qwen_vl import QwenVLWrapper

    try:
        llm = QwenVLWrapper(model_name=model, base_url=base_url, provider=provider)
    except RuntimeError as e:
        print("没有配置模型：", e)
        sys.exit(1)

    if not llm.api_key or llm.api_key == "EMPTY":
        print("没有配置模型：API Key 为空，请设置 OPENROUTER_API_KEY 或 OPENAI_API_KEY。")
        sys.exit(1)

    key_hint = llm.api_key[:6] + "..."
    print(f"VLM HTTP: {llm.base_url}  model={llm.model}  key={key_hint}")
    health = llm.health_check()
    if not health.get("ok"):
        print("模型服务不可用：", health)
        print("请检查 API Key / 网络 / --provider。")
        sys.exit(1)
    print("VLM health: OK", health.get("url"))
    return llm


def sanitize_model_tag(model: str | None, max_len: int = 64) -> str:
    """把模型名压成可作目录名的短标签，便于对比不同模型结果。"""
    raw = (model or "unknown").strip() or "unknown"
    # openrouter: qwen/qwen3-vl-8b-instruct → qwen3-vl-8b-instruct
    if "/" in raw:
        raw = raw.split("/")[-1]
    out = []
    for ch in raw:
        if ch.isalnum() or ch in "._-+":
            out.append(ch)
        else:
            out.append("_")
    tag = "".join(out).strip("._-") or "unknown"
    return tag[:max_len]


def default_results_dir(backend: str, model: str | None, suite: str = "min") -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = sanitize_model_tag(model)
    suite_tag = sanitize_model_tag(suite, max_len=24)
    return ROOT / "results" / f"aw_{backend}_{suite_tag}_{tag}_{stamp}"


def build_memory(backend: str, run_dir: Path):
    from agent.baselines import build_backend
    from core.regulate import DarwinianMemorySystem, load_config

    cfg = load_config(ROOT / "configs" / "default.yaml")
    # 不同 baseline 分目录（即便复用同一 out_dir 也不会串库）
    storage = run_dir / "memory_banks" / backend
    storage.mkdir(parents=True, exist_ok=True)
    cfg.storage_root = str(storage)
    dms = None
    if backend == "dms":
        dms = DarwinianMemorySystem(cfg)
    return (
        build_backend(
            backend,
            str(storage),
            dms=dms,
            embedding_cfg=cfg.embedding,
        ),
        dms,
    )


def max_steps_for_task(task) -> int:
    # 与 minimal_task_runner 类似：complexity * 10，并设上下限
    complexity = float(getattr(task, "complexity", 1.0) or 1.0)
    return max(15, min(80, int(complexity * 12)))


def run_one_task(
    env,
    task_cls: Type,
    agent_factory,
    seed: int | None,
    *,
    llm: Any = None,
) -> dict[str, Any]:
    from android_world.agents import base_agent
    from metrics.round_metrics import TaskDifficulty

    if seed is not None:
        params = task_cls.generate_random_params()
        # 部分任务内部用随机；这里尽量固定外部可复现点
        try:
            import random

            random.seed(seed)
            params = task_cls.generate_random_params()
        except Exception:  # noqa: BLE001
            params = task_cls.generate_random_params()
    else:
        params = task_cls.generate_random_params()

    task = task_cls(params)
    task.initialize_task(env)
    agent = agent_factory(env)
    if hasattr(agent, "reset"):
        agent.reset(go_home=True)

    goal = str(task.goal)
    complexity = float(getattr(task, "complexity", 1.0) or 1.0)
    difficulty = TaskDifficulty.of(task_cls.__name__, complexity)
    print(f"\n=== Goal: {goal}  [{difficulty}]")
    max_steps = max_steps_for_task(task)
    is_done = False
    step_logs: list[dict[str, Any]] = []
    t0 = time.time()
    tokens_before = int(getattr(llm, "total_tokens", 0) or 0) if llm is not None else 0
    peak_mem = 0

    for step_i in range(max_steps):
        try:
            response: base_agent.AgentInteractionResult = agent.step(goal)
        except Exception as e:  # noqa: BLE001
            step_logs.append({"step": step_i, "error": repr(e)})
            print(f"  [step {step_i}] error: {e}")
            break
        info = {}
        if isinstance(response.data, dict):
            mem_sz = response.data.get("memory_size")
            if isinstance(mem_sz, int):
                peak_mem = max(peak_mem, mem_sz)
            info = {
                "info": response.data.get("info"),
                "memory_size": mem_sz,
                "metrics": response.data.get("metrics"),
            }
        step_logs.append({"step": step_i, "done": response.done, **info})
        if response.done:
            is_done = True
            break

    try:
        success_score = float(task.is_successful(env))
    except Exception as e:  # noqa: BLE001
        success_score = 0.0
        step_logs.append({"is_successful_error": repr(e)})

    agent_successful = bool(is_done and success_score == 1.0)
    elapsed = time.time() - t0
    metrics = {}
    if hasattr(agent, "core"):
        metrics = dict(getattr(agent.core, "metrics", {}) or {})
        if metrics.get("memory_size"):
            peak_mem = max(peak_mem, max(int(x) for x in metrics["memory_size"]))
    tokens_after = int(getattr(llm, "total_tokens", 0) or 0) if llm is not None else 0
    tokens_used = max(0, tokens_after - tokens_before)

    print(
        f"{'✅ SUCCESS' if agent_successful else '❌ FAIL'} | "
        f"done={is_done} score={success_score} | {elapsed:.1f}s | "
        f"tokens={tokens_used} | {task_cls.__name__}"
    )

    # 清理任务副作用
    try:
        task.tear_down(env)
    except Exception:  # noqa: BLE001
        pass

    return {
        "task": task_cls.__name__,
        "goal": goal,
        "difficulty": difficulty,
        "complexity": complexity,
        "success": agent_successful,
        "is_done": is_done,
        "success_score": success_score,
        "elapsed_sec": elapsed,
        "tokens": tokens_used,
        "max_steps": max_steps,
        "n_steps_logged": len(step_logs),
        "peak_memory_size": peak_mem,
        "metrics": metrics,
        "steps": step_logs,
        "params": params,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="DMS × AndroidWorld 评测")
    parser.add_argument(
        "--tasks",
        type=str,
        default=None,
        help="逗号分隔任务名；优先级高于 --tasks_file / --suite",
    )
    parser.add_argument(
        "--tasks_file",
        type=str,
        default=None,
        help="任务列表文件（每行一个，或逗号分隔）",
    )
    parser.add_argument(
        "--suite",
        type=str,
        default="min",
        choices=["test", "min", "preferred", "full", "android"],
        help="test=单任务冒烟；min=默认5任务；preferred=每App采1–2个；full=全集；android=ANDROID_FAMILY",
    )
    parser.add_argument(
        "--per_app",
        type=int,
        default=2,
        help="仅 preferred：每个 App 采样任务数（1 或 2）",
    )
    parser.add_argument("--backend", choices=["a", "b", "dms"], default="dms")
    parser.add_argument("--trials", type=int, default=5, help="每个任务重复轮数（对齐论文约 5 round）")
    parser.add_argument("--console_port", type=int, default=5554)
    parser.add_argument("--grpc_port", type=int, default=8554)
    parser.add_argument("--adb_path", type=str, default=None)
    parser.add_argument("--perform_emulator_setup", action="store_true")
    parser.add_argument("--model", type=str, default=None, help="默认读 QWEN_MODEL；OpenRouter 例 qwen/qwen3-vl-8b-instruct")
    parser.add_argument(
        "--base_url",
        type=str,
        default=None,
        help="VLM HTTP 地址；默认读 QWEN_BASE_URL",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        choices=["openrouter", "openai", "dashscope"],
        help="API 网关；默认：有 OPENROUTER_API_KEY 则 openrouter",
    )
    parser.add_argument("--seed", type=int, default=30)
    parser.add_argument("--list-tasks", action="store_true")
    parser.add_argument("--out_dir", type=str, default=None)
    args = parser.parse_args()

    from runners.task_suites import MIN_TASKS, resolve_tasks, summarize_by_app

    try:
        task_names, suite_label = resolve_tasks(
            suite=args.suite,
            tasks=args.tasks,
            tasks_file=args.tasks_file,
            seed=args.seed,
            per_app=args.per_app,
        )
    except Exception as e:  # noqa: BLE001
        # preferred/full 需要 android_world；min 可离线解析
        if args.suite == "min" and not args.tasks and not args.tasks_file:
            task_names, suite_label = list(MIN_TASKS), "min"
        else:
            print("解析任务套件失败：", e)
            traceback.print_exc()
            sys.exit(1)

    if args.list_tasks:
        print(f"suite={suite_label}  n={len(task_names)}")
        for n in task_names:
            print(" -", n)
        try:
            info = summarize_by_app(task_names)
            print(f"\n覆盖 App 数: {info['n_apps']}")
            for app, ts in info["apps"].items():
                print(f"  [{app}] {len(ts)}: {', '.join(ts)}")
        except Exception as e:  # noqa: BLE001
            print("无法按 App 汇总（需 android_world）：", e)
        return

    # 延迟导入真实依赖
    try:
        from android_world import registry
        from android_world.env import env_launcher
        from agent.pa_agent import DMSPlannerActorAgent
    except Exception as e:  # noqa: BLE001
        print("导入 AndroidWorld / DMS Agent 失败：", e)
        traceback.print_exc()
        sys.exit(1)

    # 先建 LLM，再用真实模型名命名结果目录（便于跨模型对比）
    model_name = args.model or os.environ.get("QWEN_MODEL")
    llm = build_llm(
        model_name,
        base_url=args.base_url,
        provider=args.provider or os.environ.get("VLM_PROVIDER"),
    )
    resolved_model = getattr(llm, "model", None) or model_name or "unknown"

    out_dir = (
        Path(args.out_dir)
        if args.out_dir
        else default_results_dir(args.backend, resolved_model, suite_label)
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    adb_path = find_adb_path(args.adb_path)
    print(f"adb: {adb_path}")
    print(f"suite={suite_label} tasks={len(task_names)}")
    print(f"tasks: {task_names[:8]}{'...' if len(task_names) > 8 else ''}")
    print(f"backend={args.backend} model={resolved_model} trials={args.trials}")
    print(f"out={out_dir}")

    env = env_launcher.load_and_setup_env(
        console_port=args.console_port,
        emulator_setup=args.perform_emulator_setup,
        adb_path=adb_path,
        grpc_port=args.grpc_port,
    )
    env.reset(go_home=True)

    task_registry = registry.TaskRegistry()
    aw_registry = task_registry.get_registry(task_registry.ANDROID_WORLD_FAMILY)
    for name in task_names:
        if name not in aw_registry:
            env.close()
            raise ValueError(f"任务不在 registry: {name}")

    # 同一 backend 记忆跨 trial 保留，才能看到「进化」
    memory, dms = build_memory(args.backend, out_dir)
    mem_root = out_dir / "memory_banks" / args.backend

    from metrics.plot_metrics import MetricsPlotter
    from metrics.round_metrics import RoundMetricsRecorder

    recorder = RoundMetricsRecorder(
        out_dir=out_dir,
        backend=args.backend,
        model=resolved_model,
        memory_root=mem_root,
    )

    def agent_factory(e):
        return DMSPlannerActorAgent(e, llm, memory, name=f"dms_pa_{args.backend}")

    def pruned_total() -> int:
        if dms is None:
            return 0
        return int(dms.stats.get("pruned", 0))

    all_results: list[dict[str, Any]] = []
    try:
        for trial in range(args.trials):
            print(f"\n######## ROUND {trial + 1}/{args.trials} ########")
            pruned_before = pruned_total()
            peak_mem = memory.size()
            round_rows: list[dict[str, Any]] = []

            for name in task_names:
                task_cls = aw_registry[name]
                seed = args.seed + trial * 1009 + (hash(name) % 97)
                try:
                    result = run_one_task(
                        env, task_cls, agent_factory, seed=seed, llm=llm
                    )
                except Exception as e:  # noqa: BLE001
                    result = {
                        "task": name,
                        "success": False,
                        "error": repr(e),
                        "traceback": traceback.format_exc(),
                        "metrics": {},
                        "tokens": 0,
                        "elapsed_sec": 0.0,
                        "peak_memory_size": memory.size(),
                    }
                    print(f"❌ 任务异常 {name}: {e}")
                result["trial"] = trial
                result["round"] = trial + 1
                result["backend"] = args.backend
                result["model"] = resolved_model
                result["memory_size_after"] = memory.size()
                peak_mem = max(
                    peak_mem,
                    int(result.get("peak_memory_size") or 0),
                    int(result.get("memory_size_after") or 0),
                )
                all_results.append(result)
                round_rows.append(result)
                # 每任务落盘，避免中断丢数据
                (out_dir / "task_results.json").write_text(
                    json.dumps(all_results, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )

            # 每轮结束：汇总核心指标 + 可选出图
            snap = recorder.record_round(
                round_idx=trial,
                task_results=round_rows,
                peak_memory_size=peak_mem,
                pruned_count=pruned_total() - pruned_before,
                memory_root=mem_root,
            )
            print(
                f"[Round {snap.round}] SR={snap.sr:.2%} MRR={snap.mrr:.2%} "
                f"SRR={snap.srr if snap.srr is not None else 'n/a'} "
                f"tokens={snap.total_tokens} mem={snap.final_memory_size} "
                f"({snap.memory_mb:.2f} MB) pruned={snap.pruned_count}"
            )
            plotter = MetricsPlotter(out_dir)
            fig = plotter.plot_core_curves()
            if fig:
                print("wrote", fig)
    finally:
        env.close()

    print("\n==== Round Metrics ====")
    print((out_dir / "round_metrics.json").read_text(encoding="utf-8"))
    print("wrote", out_dir / "task_results.json")
    print("wrote", out_dir / "round_metrics.json")
    print("wrote", out_dir / "round_metrics.csv")
    print("wrote", out_dir / "summary.json")


if __name__ == "__main__":
    main()
