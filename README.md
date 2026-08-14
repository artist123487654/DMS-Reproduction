# Darwinian Memory System (DMS) 复现

本仓库是 **Darwinian Memory System (DMS)** 的非官方复现，在 [AndroidWorld](https://github.com/google-research/android_world) 上评测。

**论文：** [Darwinian Memory: A Training-Free Self-Regulating Memory System for GUI Agent Evolution](https://arxiv.org/abs/2601.22528)（arXiv:2601.22528）

DMS 将 Agent 记忆视为遵循「适者生存」的动态生态：分层意图/动作记忆、效用驱动的 Survival Value 选择，以及动态修剪。本实现以训练免费的 Planner–Actor 流水线落地上述机制，并在 AndroidWorld 上对比三套后端：

| Backend | 说明 |
|---------|------|
| `a` | Zero-shot VLM（无记忆） |
| `b` | 静态追加记忆（只增不剪） |
| `dms` | 完整达尔文记忆系统 |

默认使用轻量开源多模态模型（如经 OpenRouter / OpenAI 兼容接口调用的 Qwen2.5-VL-7B），适配算力受限的复现设置；与论文中的大参数骨干可能存在性能差距。

## 仓库结构

```text
code/
├── android_world/          # AndroidWorld 评测环境
└── DMS/                    # 复现代码
    ├── core/               # 记忆库、Survival、修剪、检索、闭环调节
    ├── agent/              # Planner / Actor / Verifier / 基线
    ├── models/             # VLM HTTP 客户端
    ├── metrics/            # 轮次级 SR / MRR / Token / 记忆指标
    ├── runners/            # 评测入口（run_androidworld.py）
    ├── scripts/            # 一键启动脚本
    └── configs/default.yaml
```

脚本按相对路径定位仓库，请保持 `DMS/` 与 `android_world/` 同级，位于 `code/` 下。

## 环境要求

- 推荐 Linux + KVM
- Android 模拟器（API 33 / `AndroidWorldAvd`，gRPC 常见端口 `8554`）
- 已安装 `android_world` 与 `DMS/requirements.txt` 依赖的 Python 虚拟环境
- VLM API Key（`OPENROUTER_API_KEY` 或 `OPENAI_API_KEY`）
- 检索用嵌入模型（默认 `BAAI/bge-small-en-v1.5`，或设置 `EMBEDDING_MODEL_PATH`）

运行前请：激活虚拟环境、启动模拟器、导出 API Key。脚本会做基本检查，但不会自动完成上述准备。

## 快速开始

```bash
source <venv>/bin/activate
adb devices   # 应看到就绪设备

cd code/DMS
export OPENROUTER_API_KEY='sk-or-...'

# Minimum：默认 5 个代表性任务 × 5 轮
bash scripts/run_min.sh
bash scripts/run_min_baselines.sh          # a → b → dms

# Preferred：每个真实 App 采样 1–2 个任务（跨应用覆盖）
bash scripts/run_preferred.sh
bash scripts/run_preferred_baselines.sh

# Full Split：AndroidWorld 全集（约 116 任务，耗时长）
bash scripts/run_full_split.sh
bash scripts/run_full_split_baselines.sh

# 仅列出套件任务，不跑评测
python scripts/list_suite_tasks.py --suite preferred --json
```

可用环境变量覆盖：`BACKEND`、`TRIALS`、`PER_APP`、`SEED`。也可向脚本追加参数，例如：

```bash
BACKEND=a bash scripts/run_min.sh --model qwen/qwen2.5-vl-7b-instruct
```

等价 Python 入口：

```bash
python runners/run_androidworld.py --suite preferred --backend dms --trials 5
```

## 输出说明

每次运行写入：

`DMS/results/aw_{backend}_{suite}_{model}_{timestamp}/`

| 文件 | 内容 |
|------|------|
| `task_results.json` | 逐任务日志 |
| `round_metrics.json` / `.csv` | 每轮 SR、SRR、MRR、步数、Token、记忆规模 |
| `summary.json` | 轮次精简汇总 |
| `memory_banks/{a\|b\|dms}/` | 各 baseline 独立记忆库 |
| `evolution_curves.png` | 若已安装 matplotlib 则生成曲线图 |

指标汇总实现见 `DMS/metrics/`（`RoundMetricsRecorder`、`MetricsPlotter`）。

## 配置

超参与嵌入配置见 `DMS/configs/default.yaml`：

```yaml
embedding:
  model_name_or_path: BAAI/bge-small-en-v1.5
  device: cpu
```

使用本地嵌入权重时，无需改 YAML：

```bash
export EMBEDDING_MODEL_PATH=/path/to/bge-small-en-v1.5
```

## 引用

若使用本复现或原方法，请引用原论文：

```bibtex
@article{mi2026darwinian,
  title={Darwinian Memory: A Training-Free Self-Regulating Memory System for GUI Agent Evolution},
  author={Mi, Hongze and Feng, Yibo and Lu, WenJie and Cao, Song and Li, Jinyuan and Li, Yanming and Zhang, Xuelin and Luo, Haotian and Peng, Songyang and Cui, He and Tian, Tengfei and Fang, Jun and Chai, Hua and Tan, Naiqiang},
  journal={arXiv preprint arXiv:2601.22528},
  year={2026}
}
```

## 声明

本仓库为独立复现，用于研究 / 课程考核，**非论文作者官方发布**。因模型规模、解码策略与任务子集不同，结果可能与原论文存在差异。
