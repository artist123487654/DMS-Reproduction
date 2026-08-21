# 运行指南

在 **Linux + KVM** 上：配好 Key → 启动模拟器 → 跑实验。  
需已装好 Android SDK（AVD：`AndroidWorldAvd`，API 33）、Python 虚拟环境与本仓库依赖。

```text
code/
├── android_world/
└── DMS/
```

---

## 1. 配置 API Key 以及启动 Android 模拟器

```bash
source /home/moxy/venvs/android_world/bin/activate
cd DMS

export OPENROUTER_API_KEY='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'

bash scripts/start_emulator.sh

```bash
# 可能要跑较久（装包+快照）。成功后 snapshots 在模拟器内：
#   /data/data/android_world/snapshots/
bash scripts/run_test.sh --perform_emulator_setup --model qwen/qwen3-vl-8b-instruct
```

确认快照（应能看到 markor / contacts 等包名目录）：

```bash
adb shell ls /data/data/android_world/snapshots/ | head
```

之后正式实验**不要**再加 `--perform_emulator_setup`。
若模拟器数据被清掉，需重新 setup。

---

## 3. 跑实验

均在 `code/DMS` 下执行；默认模型：`qwen/qwen3-vl-8b-instruct`。  
执行器为独立 **CodeAct**（Planner → 写 Python 调工具 / 命中则复放轨迹），挂自研 DMS；**不**从官方 DMS 仓库 import。

正式评测前确认快照：`adb shell ls /data/data/android_world/snapshots/`；旧 `memory_banks` 建议清空后空库重跑。

| 档位 | 命令 |
|------|------|
| Test（1 任务×5 轮，先跑） | `bash scripts/run_test.sh --model qwen/qwen3-vl-8b-instruct` |
| Minimum（5 任务×5 轮，默认 dms） | `bash scripts/run_min.sh --model qwen/qwen3-vl-8b-instruct` |
| Minimum 基线 a/b | `bash scripts/run_min_baselines.sh --model qwen/qwen3-vl-8b-instruct` |
| Preferred（默认 dms） | `bash scripts/run_preferred.sh --model qwen/qwen3-vl-8b-instruct` |
| Preferred 基线 a/b | `bash scripts/run_preferred_baselines.sh --model qwen/qwen3-vl-8b-instruct` |
| Full（很慢，默认 dms） | `bash scripts/run_full_split.sh --model qwen/qwen3-vl-8b-instruct` |

可选：`BACKEND=a`、`TRIALS=1`（快速冒烟）、`TASK=MarkorCreateNote`（仅 test）。

### 关掉 VSCode 也不中断（推荐长实验）

前缀加 `DETACH=1`，用 `nohup` 脱离远程会话：

```bash
DETACH=1 bash scripts/run_min_baselines.sh --model qwen/qwen3-vl-8b-instruct
DETACH=1 bash scripts/run_min.sh --model qwen/qwen3-vl-8b-instruct

DETACH=1 bash scripts/run_full_split_baselines.sh --model qwen/qwen3-vl-8b-instruct
DETACH=1 bash scripts/run_full_split.sh --model qwen/qwen3-vl-8b-instruct

DETACH=1 bash scripts/run_preferred_baselines.sh --model qwen/qwen3-vl-8b-instruct
DETACH=1 bash scripts/run_preferred.sh --model qwen/qwen3-vl-8b-instruct
```

日志与 PID 在 `DMS/logs/`。查看 / 停止：

```bash
tail -f logs/run_*.log          # 或脚本打印的具体路径
kill $(cat logs/run_xxx.pid)
```

模拟器请用 `bash scripts/start_emulator.sh`（内部已 nohup，关掉 VSCode 一般不会停）。

结果在：`DMS/results/aw_{backend}_{suite}_{model}_{时间戳}/`  
记忆在同目录：`memory_banks/{a|b|dms}/`（`index.sqlite` + `traj/*.json`），**不是** `DMS/memory_banks/`。

---

## 排障

| 问题 | 处理 |
|------|------|
| 无 `/dev/kvm` | 换带虚拟化的机器 |
| Qt/xcb 报错 | 确认有 `-no-window` |
| adb 无设备 | 看 `/tmp/emulator.log`，等 boot 完成 |
| 提示没有配置模型 | 回到第 1 步检查 Key 是否已 `export` |
