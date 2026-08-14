# 运行指南

在 **Linux + KVM** 上：配好 Key → 启动模拟器 → 跑实验。  
需已装好 Android SDK（AVD：`AndroidWorldAvd`，API 33）、Python 虚拟环境与本仓库依赖。

```text
code/
├── android_world/
└── DMS/
```

---

## 1. 配置 API Key（先做这一步）

```bash
source /home/moxy/venvs/android_world/bin/activate
cd code/DMS

# OpenRouter（推荐）
export OPENROUTER_API_KEY='sk-or-...'

# 或 DashScope
# export DASHSCOPE_API_KEY='sk-...'
# export VLM_PROVIDER=dashscope
# export QWEN_BASE_URL='https://cn-hongkong.dashscope.aliyuncs.com/compatible-mode/v1'
```

---

## 2. 启动 Android 模拟器

```bash
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"

$ANDROID_HOME/emulator/emulator \
  -avd AndroidWorldAvd \
  -no-snapshot -no-window \
  -gpu swiftshader_indirect \
  -grpc 8554 \
  >/tmp/emulator.log 2>&1 &

adb wait-for-device
until [[ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]]; do sleep 2; done
adb devices   # 应看到 emulator-5554  device
```

首次装 App（只做一次）：

```bash
bash scripts/run_test.sh --perform_emulator_setup --model qwen/qwen3-vl-8b-instruct
```

之后不要再加 `--perform_emulator_setup`。

---

## 3. 跑实验

均在 `code/DMS` 下执行；默认模型：`qwen/qwen3-vl-8b-instruct`。

| 档位 | 命令 |
|------|------|
| Test（1 任务×5 轮，先跑） | `bash scripts/run_test.sh --model qwen/qwen3-vl-8b-instruct` |
| Minimum（5 任务×5 轮） | `bash scripts/run_min.sh --model qwen/qwen3-vl-8b-instruct` |
| Minimum 三组 a/b/dms | `bash scripts/run_min_baselines.sh --model qwen/qwen3-vl-8b-instruct` |
| Preferred | `bash scripts/run_preferred.sh --model qwen/qwen3-vl-8b-instruct` |
| Preferred 三组 | `bash scripts/run_preferred_baselines.sh --model qwen/qwen3-vl-8b-instruct` |
| Full（很慢） | `bash scripts/run_full_split.sh --model qwen/qwen3-vl-8b-instruct` |

可选：`BACKEND=a`、`TRIALS=1`（快速冒烟）、`TASK=MarkorCreateNote`（仅 test）。

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
