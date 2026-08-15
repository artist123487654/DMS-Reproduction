# Darwinian Memory System (DMS) 复现

本仓库是 **Darwinian Memory System (DMS)** 的非官方复现，在 [AndroidWorld](https://github.com/google-research/android_world) 上评测。

**论文：** [Darwinian Memory: A Training-Free Self-Regulating Memory System for GUI Agent Evolution](https://arxiv.org/abs/2601.22528)（arXiv:2601.22528）

DMS 将 Agent 记忆视为遵循「适者生存」的动态生态：分层意图/动作记忆、效用驱动的 Survival Value 选择，以及动态修剪。本实现以训练免费的 Planner–Actor 流水线落地上述机制，并在 AndroidWorld 上对比三套后端：

| Backend | 说明 |
|---------|------|
| `a` | Zero-shot VLM（无记忆） |
| `b` | 静态追加记忆（只增不剪） |
| `dms` | 完整达尔文记忆系统 |

默认推荐轻量开源多模态模型 **Qwen3-VL-8B-Instruct**（约 8B，符合考核 7B～8B 开源 VLM 要求；原推荐的 Qwen2.5-VL-7B 多数平台已下架）。论文使用更大骨干（如 72B），本复现侧重机制验证，报告中需做 Gap 分析。

## 仓库结构

```text
code/
├── README.md               # 项目说明
├── RUN.md                  # 启动模拟器与跑实验（详细步骤）
├── android_world/          # AndroidWorld 评测环境
└── DMS/                    # 复现代码
    ├── core/               # 记忆库、Survival、修剪、检索、闭环调节
    ├── agent/              # Planner / Actor / Verifier / 基线
    ├── models/             # VLM HTTP 客户端
    ├── metrics/            # 轮次级 SR / MRR / Token / 记忆指标
    ├── runners/            # 评测入口（run_androidworld.py）
    ├── scripts/            # 一键启动脚本
    │   ├── run_test.sh     # Test：单任务冒烟
    │   ├── run_min.sh      # Minimum：5 任务
    │   ├── run_preferred.sh
    │   └── run_full_split.sh
    └── configs/default.yaml
```

请保持 `DMS/` 与 `android_world/` 同级。脚本按相对路径定位，不依赖固定用户名或绝对路径。  
**如何启动模拟器并跑各档实验：见 [RUN.md](./RUN.md)。**

## 评测套件

| Suite | 脚本 | 规模 | 用途 |
|-------|------|------|------|
| `test` | `scripts/run_test.sh` | 1 任务 × 1 轮 | 低成本验证全流程 |
| `min` | `scripts/run_min.sh` | 5 任务 × 5 轮 | 考核 Minimum |
| `preferred` | `scripts/run_preferred.sh` | 每 App 采 1～2 任务 × 5 轮 | 跨应用 Preferred |
| `full` | `scripts/run_full_split.sh` | AndroidWorld 全集 × 5 轮 | 完整 Split（耗时长） |

对应 `*_baselines.sh` 会依次跑 `a` → `b` → `dms`。

## 环境要求

- 推荐 Linux + KVM
- Android 模拟器（API 33 / `AndroidWorldAvd`，gRPC 常见端口 `8554`）
- 已安装 `android_world` 与 `DMS/requirements.txt` 的 Python 虚拟环境
- VLM API Key：`OPENROUTER_API_KEY` 或 `DASHSCOPE_API_KEY`（或 `OPENAI_API_KEY`）
- 检索嵌入：默认 `BAAI/bge-small-en-v1.5`，可用 `EMBEDDING_MODEL_PATH` 指向本地目录

运行前请激活虚拟环境、启动模拟器并导出 API Key。`scripts/_common.sh` 会做基本检查，但不会自动安装依赖或启动模拟器。

## 快速开始

```bash
source <venv>/bin/activate
adb devices   # 应看到就绪设备

cd code/DMS
export OPENROUTER_API_KEY='sk-or-...'
# 或: export DASHSCOPE_API_KEY='sk-...' && export VLM_PROVIDER=dashscope

# 1) Test：1 个短任务 × 1 轮
bash scripts/run_test.sh \
  --model qwen/qwen3-vl-8b-instruct

# 2) Minimum / Preferred / Full
bash scripts/run_min.sh --model qwen/qwen3-vl-8b-instruct
bash scripts/run_min_baselines.sh --model qwen/qwen3-vl-8b-instruct
bash scripts/run_preferred.sh --model qwen/qwen3-vl-8b-instruct
bash scripts/run_full_split.sh --model qwen/qwen3-vl-8b-instruct

# 仅列出套件任务（不跑评测）
python runners/run_androidworld.py --suite test --list-tasks
python runners/run_androidworld.py --suite preferred --list-tasks
```

常用环境变量：`BACKEND`、`TRIALS`、`PER_APP`、`SEED`、`TASK`（仅 `run_test.sh` 可覆盖任务名）。

```bash
BACKEND=a TASK=MarkorCreateNote bash scripts/run_test.sh --model qwen/qwen3-vl-8b-instruct
```

DashScope（例如 Azure 东亚，建议香港 endpoint）：

```bash
export DASHSCOPE_API_KEY='sk-...'
bash scripts/run_test.sh \
  --provider dashscope \
  --base_url https://cn-hongkong.dashscope.aliyuncs.com/compatible-mode/v1 \
  --model qwen3-vl-8b-instruct
```

等价 Python 入口：

```bash
python runners/run_androidworld.py --suite test --backend dms --trials 1 \
  --model qwen/qwen3-vl-8b-instruct
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

指标实现见 `DMS/metrics/`（`RoundMetricsRecorder`、`MetricsPlotter`）。`results/` 与记忆库默认已由 `.gitignore` 忽略。

## 配置

超参与嵌入见 `DMS/configs/default.yaml`：

```yaml
embedding:
  model_name_or_path: BAAI/bge-small-en-v1.5
  device: cpu
```

本地嵌入权重：

```bash
export EMBEDDING_MODEL_PATH=/path/to/bge-small-en-v1.5
```

## 引用

```bibtex
@misc{mi2026darwinianmemorytrainingfreeselfregulating,
      title={Darwinian Memory: A Training-Free Self-Regulating Memory System for GUI Agent Evolution},
      author={Hongze Mi and Yibo Feng and WenJie Lu and Song Cao and Jinyuan Li and Yanming Li and Xuelin Zhang and Haotian Luo and Songyang Peng and He Cui and Tengfei Tian and Jun Fang and Hua Chai and Naiqiang Tan},
      year={2026},
      eprint={2601.22528},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2601.22528},
}
```

## 声明

本仓库为独立复现，用于研究 / 课程考核，**非论文作者官方发布**。因模型规模、解码策略与任务子集不同，结果可能与原论文存在差异。
