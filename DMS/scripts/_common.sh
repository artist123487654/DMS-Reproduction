#!/usr/bin/env bash
# 被各 run_*.sh source：解析仓库路径、设置 PYTHONPATH、做最小前置检查。
# 不绑定任何用户名 / 绝对路径；假定目录结构为：
#   <repo>/code/DMS/scripts/this
#   <repo>/code/android_world/
#
# 后台保活，关掉 VSCode 或 SSH 也不停：
#   DETACH=1 bash scripts/run_preferred.sh --model qwen/qwen3-vl-8b-instruct
# 日志在 DMS/logs/；用 tail -f 查看，kill $(cat ...pid) 停止。

_dms_common_init() {
  local here root aw
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  root="$(cd "${here}/.." && pwd)"
  aw="$(cd "${root}/../android_world" && pwd)"

  if [[ ! -f "${root}/runners/run_androidworld.py" ]]; then
    echo "[错误] 找不到 runners/run_androidworld.py, ROOT=${root}" >&2
    exit 1
  fi
  if [[ ! -d "${aw}/android_world" ]]; then
    echo "[错误] 找不到并列的 android_world 工程：${aw}" >&2
    echo "      请保持 code/DMS 与 code/android_world 同级。" >&2
    exit 1
  fi

  cd "${root}"
  export DMS_ROOT="${root}"
  export ANDROID_WORLD_ROOT="${aw}"
  export PYTHONPATH="${root}:${aw}:${PYTHONPATH:-}"

  # 优先当前环境的 python；没有再试 python3
  if command -v python >/dev/null 2>&1; then
    export DMS_PYTHON="${DMS_PYTHON:-python}"
  elif command -v python3 >/dev/null 2>&1; then
    export DMS_PYTHON="${DMS_PYTHON:-python3}"
  else
    echo "[错误] 找不到 python / python3，请先激活虚拟环境。" >&2
    exit 1
  fi

  if ! "${DMS_PYTHON}" -c "import android_world" >/dev/null 2>&1; then
    echo "[错误] 当前解释器无法 import android_world: ${DMS_PYTHON}" >&2
    echo "      请先: source <venv>/bin/activate 并确保已安装 android_world。" >&2
    exit 1
  fi

  if [[ -z "${OPENROUTER_API_KEY:-}${OPENAI_API_KEY:-}${QWEN_API_KEY:-}${DASHSCOPE_API_KEY:-}" \
        && -z "${QWEN_BASE_URL:-}" ]]; then
    echo "[错误] 未设置 VLM API Key，需 OPENROUTER_API_KEY / OPENAI_API_KEY 等。" >&2
    exit 1
  fi

  if ! command -v adb >/dev/null 2>&1; then
    echo "[警告] PATH 中没有 adb；将尝试 ANDROID_HOME / ANDROID_SDK_ROOT。" >&2
  else
    if ! adb devices 2>/dev/null | grep -qE $'device$'; then
      echo "[警告] adb devices 未见就绪设备。请先启动模拟器，如 emulator-5554。" >&2
    fi
  fi

  echo "[env] DMS_ROOT=${DMS_ROOT}"
  echo "[env] ANDROID_WORLD_ROOT=${ANDROID_WORLD_ROOT}"
  echo "[env] PYTHON=${DMS_PYTHON} ($("${DMS_PYTHON}" -c 'import sys; print(sys.executable)'))"
}

# 前台直接跑；DETACH=1 时 nohup 后台跑，断开远程会话不中断。
dms_exec() {
  if [[ "${DETACH:-0}" != "1" && "${DETACH:-}" != "true" && "${DETACH:-}" != "yes" ]]; then
    "$@"
    return $?
  fi

  mkdir -p "${DMS_ROOT}/logs"
  local stamp base log pidf
  stamp="$(date +%Y%m%d_%H%M%S)"
  base="run_${stamp}"
  log="${DMS_ROOT}/logs/${base}.log"
  pidf="${DMS_ROOT}/logs/${base}.pid"

  {
    echo "========== DMS detach =========="
    echo "time: $(date -Is)"
    echo "cmd:  $*"
    echo "================================"
  } >"${log}"

  nohup "$@" >>"${log}" 2>&1 </dev/null &
  echo $! >"${pidf}"
  disown $! 2>/dev/null || true

  echo "[detach] pid=$(cat "${pidf}")"
  echo "[detach] log=${log}"
  echo "[detach] 查看: tail -f ${log}"
  echo "[detach] 停止: kill \$(cat ${pidf})"
}

_dms_common_init
