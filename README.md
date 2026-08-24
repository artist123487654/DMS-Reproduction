# Darwinian Memory System (DMS) 复现

本仓库是 **Darwinian Memory System (DMS)** 的非官方复现，在 [AndroidWorld](https://github.com/google-research/android_world) 上评测。

**论文：** [Darwinian Memory: A Training-Free Self-Regulating Memory System for GUI Agent Evolution](https://arxiv.org/abs/2601.22528)（arXiv:2601.22528）

DMS 将 Agent 记忆视为遵循「适者生存」的动态生态：分层意图/动作记忆、效用驱动的 Survival Value 选择，以及动态修剪。本实现以训练免费的 Planner–Actor 流水线落地上述机制，并在 AndroidWorld 上对比三套后端：

| Backend | 说明 |
|---------|------|
| `a` | 零记忆（≈ 论文 PA-Lite；考核 Baseline A） |
| `b` | 静态追加、不修剪（考核 Baseline B；与 DMS 共用双因子/`min_score`） |
| `dms` | 达尔文记忆：Survival + 动态修剪 + ε-mutation 等 |

默认推荐轻量开源多模态模型 **Qwen3-VL-8B-Instruct**（约 8B，符合考核 7B～8B 开源 VLM 要求）。论文使用更大骨干（如 72B），本复现侧重机制验证，报告中需做 Gap 分析。

## 仓库结构

```text
code/
├── android_world/          # AndroidWorld 评测环境
└── DMS/                    # 复现代码
    ├── core/               # 记忆库、Survival、修剪、检索
    ├── agent/              # Planner / Actor / Verifier / 基线
    ├── runners/            # run_androidworld.py
    └── scripts/            # 一键脚本
```

请保持 `DMS/` 与 `android_world/` **同级**。

## 评测套件

| Suite | 脚本 | 规模 |
|-------|------|------|
| `test` | `run_test.sh` | 1 任务 × 5 轮 |
| `min` | `run_min.sh` | 5 任务 × 5 轮 |
| `preferred` | `run_preferred.sh` | 每 App 1～2 任务 × 5 轮 |
| `full` | `run_full_split.sh` | 全集 × 5 轮 |

`*_baselines.sh` 顺序跑 `a → b`；`run_preferred_all.sh` 顺序跑 `dms → b → a`。

---

## 运行方法

整体流程：**配环境 → 启模拟器 →（首次）装 App 写快照 → 跑 sh 脚本**。实验在 Linux 上的 Android 模拟器里跑真实 App 任务，Agent 看图决策，DMS 负责记忆检索与演化。

### 1. 前置条件

跑脚本前，机器上需已具备：

- **Linux + KVM**：Android 模拟器依赖硬件虚拟化，需有 `/dev/kvm`（云服务器请选带 KVM 的机型）。
- **Android SDK + AVD**：用 Android Studio 装好 SDK，并创建名为 **AndroidWorldAvd** 的虚拟手机（Pixel 6、API 33），详见 [AndroidWorld 官方说明](https://github.com/google-research/android_world#installation)。
- **Python 3.11+**：跑 DMS 与 AndroidWorld 代码。
- **VLM API Key**：调用 Qwen3-VL 做多模态 Planner/Actor；考核共用 OpenRouter Key 如下（几天会过期，可直接复制）：

```bash
export ANDROID_HOME="$HOME/Android/Sdk"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"
export OPENROUTER_API_KEY='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'
```

### 2. 安装依赖

创建 Python 虚拟环境，把 **AndroidWorld**（评测环境、任务、adb 通信）和 **DMS**（记忆系统、Agent）装进同一个 venv：

```bash
python3.11 -m venv ~/venvs/android_world
source ~/venvs/android_world/bin/activate

cd code/android_world
pip install -r requirements.txt
python setup.py install

cd ../DMS
pip install -r requirements.txt
```

### 3. 启动模拟器

AndroidWorld 在 **Live 模拟器** 里评测。`start_emulator.sh` 会后台拉起 `AndroidWorldAvd` 并通过 adb 连上：

```bash
source ~/venvs/android_world/bin/activate
cd code/DMS
bash scripts/start_emulator.sh
adb devices   # 应看到 emulator-5554 device
```

### 4. 首次初始化（只需一次）

AndroidWorld 任务依赖 Markor、Contacts 等第三方 App，首次需在模拟器里**自动安装并保存快照**（否则任务无法 reset）。加 `--perform_emulator_setup`，可能跑较久：

```bash
export OPENROUTER_API_KEY='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'

bash scripts/run_test.sh \
  --perform_emulator_setup \
  --model qwen/qwen3-vl-8b-instruct

adb shell ls /data/data/android_world/snapshots/ | head   # 应看到 markor 等目录
```

之后正式实验**不要**再加 `--perform_emulator_setup`；模拟器数据被 wipe 后才需重做。

### 5. 跑实验

在 `code/DMS` 下执行各档脚本；脚本调用 `run_androidworld.py` 连模拟器跑任务，结果写入 `results/`。每次跑前激活 venv 并 export Key：

```bash
source ~/venvs/android_world/bin/activate
cd code/DMS
export OPENROUTER_API_KEY='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'
```

| 档位 | 命令 | 说明 |
|------|------|------|
| Test | `bash scripts/run_test.sh --model qwen/qwen3-vl-8b-instruct` | 1 任务 × 5 轮，先跑通 |
| Minimum | `bash scripts/run_min.sh --model qwen/qwen3-vl-8b-instruct` | 5 任务 × 5 轮，backend=dms |
| Minimum 基线 | `bash scripts/run_min_baselines.sh --model qwen/qwen3-vl-8b-instruct` | 顺序跑 a → b |
| Preferred | `bash scripts/run_preferred.sh --model qwen/qwen3-vl-8b-instruct` | 跨 App 采样 × 5 轮 |
| Preferred 基线 | `bash scripts/run_preferred_baselines.sh --model qwen/qwen3-vl-8b-instruct` | 顺序跑 a → b |
| Preferred 全套 | `bash scripts/run_preferred_all.sh --model qwen/qwen3-vl-8b-instruct` | 顺序跑 dms → b → a |
| Full | `bash scripts/run_full_split.sh --model qwen/qwen3-vl-8b-instruct` | ~116 任务，很慢 |
| Full 基线 | `bash scripts/run_full_split_baselines.sh --model qwen/qwen3-vl-8b-instruct` | Full 档 a → b |

可选：`BACKEND=a`、`TRIALS=1` 快速冒烟；`TASK=MarkorCreateNote` 指定 test 任务。  
长实验前缀加 `DETACH=1`，断开 SSH 不中断，日志在 `DMS/logs/`。

结果目录：`DMS/results/aw_{backend}_{suite}_{model}_{时间戳}/`，含 `task_results.json`、`round_metrics.json`、同目录下 `memory_banks/{a|b|dms}/`。

---

## 配置

超参见 `DMS/configs/default.yaml`。

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

本仓库为独立复现，用于研究 / 课程考核，**非论文作者官方发布**。
