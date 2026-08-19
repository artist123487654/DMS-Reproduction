#!/usr/bin/env bash
# 启动模拟器：先杀旧进程，再后台拉起。
#   bash scripts/start_emulator.sh

set -euo pipefail

ANDROID_HOME="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}}"
export ANDROID_HOME
export PATH="${ANDROID_HOME}/platform-tools:${ANDROID_HOME}/emulator:${PATH}"

AVD_NAME="${AVD_NAME:-AndroidWorldAvd}"
LOG="${EMU_LOG:-/tmp/emulator.log}"

echo "[emu] kill old..."
pkill -f "qemu-system-x86" 2>/dev/null || true
pkill -f "emulator.*${AVD_NAME}" 2>/dev/null || true
sleep 2
adb kill-server >/dev/null 2>&1 || true
adb start-server >/dev/null 2>&1 || true

echo "[emu] start ${AVD_NAME} -> ${LOG}"
rm -f "${LOG}"
nohup emulator \
  -avd "${AVD_NAME}" \
  -no-snapshot -no-window \
  -gpu swiftshader_indirect \
  -no-metrics \
  -grpc 8554 \
  >"${LOG}" 2>&1 </dev/null &
disown $! 2>/dev/null || true

echo "[emu] waiting boot..."
adb wait-for-device
until [[ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]]; do
  sleep 2
done
adb devices
echo "[emu] ready. 若失败看: tail -n 40 ${LOG}"
