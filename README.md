# Darwinian Memory System (DMS) 复现

基于论文 *Darwinian Memory: A Training-Free Self-Regulating Memory System for GUI Agent Evolution*，在 AndroidWorld 上复现训练免费的达尔文记忆系统（分层记忆、Survival Value、动态修剪），并与无记忆 / 静态记忆基线对比。

## 目录

```text
code/
├── android_world/   # AndroidWorld 评测环境
└── DMS/             # DMS 核心、Agent、评测脚本
    ├── runners/run_androidworld.py   # 评测入口（由 scripts 调用）
    └── scripts/                      # 一键 shell
```

## 环境（简述）

需已就绪：Linux + KVM、Android 模拟器（API 33 / `AndroidWorldAvd`，`-grpc 8554`）、Python 虚拟环境（已安装 `android_world` 与 `DMS` 依赖）。VLM 通过 HTTP API 调用（推荐 OpenRouter）；检索嵌入默认本地 `sentence-transformers`（见 `configs/default.yaml` 的 `embedding`）。

## 怎么跑（推荐用 shell）

脚本用相对路径定位仓库，**不绑用户名**；要求目录保持 `code/DMS` 与 `code/android_world` 同级。真正「一键」前仍需本机已具备：venv 激活、模拟器已起、API Key。

```bash
# 激活环境，保证模拟器已启动
source <你的venv>/bin/activate
adb devices   # 应看到 device

cd code/DMS
export OPENROUTER_API_KEY='sk-or-...'
# PYTHONPATH 由 scripts/_common.sh 自动设置，一般不用手写

# Minimum：默认 5 任务 × 5 rounds（考核底线）
bash scripts/run_min.sh
bash scripts/run_min_baselines.sh          # a → b → dms

# Preferred：覆盖全部真实 App，每 App 采 1–2 个任务
bash scripts/run_preferred.sh
bash scripts/run_preferred_baselines.sh

# Full Split：android_world 全集（约 116，很慢）
bash scripts/run_full_split.sh
bash scripts/run_full_split_baselines.sh

# 只看任务清单（不跑）
python scripts/list_suite_tasks.py --suite preferred --json
```

环境变量可覆盖：`BACKEND` / `TRIALS` / `PER_APP` / `SEED`。也可直接传参给脚本，例如：

```bash
BACKEND=a bash scripts/run_min.sh --model qwen/qwen2.5-vl-7b-instruct
```

正式评测输出在 `code/DMS/results/aw_{backend}_{suite}_{模型短名}_{时间戳}/`：

- `task_results.json`：每个任务原始日志  
- `round_metrics.json` / `round_metrics.csv`：每轮核心指标（SR / SRR / MRR / 步数 / Token / 记忆）  
- `summary.json`：与上同口径的精简汇总  
- `memory_banks/{a|b|dms}/`：各 baseline 独立记忆库  
- `evolution_curves.png`：若已安装 matplotlib 则每轮更新

指标逻辑在 `code/DMS/metrics/`（`RoundMetricsRecorder` / `MetricsPlotter`）。

### 嵌入模型（给师兄）

默认读 `configs/default.yaml`：

```yaml
embedding:
  model_name_or_path: BAAI/bge-small-en-v1.5   # HF ID 或本地目录
  device: cpu
```

若模型已下载到本地，用环境变量覆盖（无需改代码）：

```bash
export EMBEDDING_MODEL_PATH=/path/to/bge-small-en-v1.5
```
