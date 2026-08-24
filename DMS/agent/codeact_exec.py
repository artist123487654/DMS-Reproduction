"""受限 CodeAct 执行：从模型输出抽 Python，在工具命名空间中 exec。"""

from __future__ import annotations

import re
from typing import Any, Callable


def extract_python_block(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # 无 fence 时：尝试从首个工具调用起截取
    for name in (
        "tap_by_index",
        "tap_xy",
        "input_text",
        "open_app",
        "complete",
        "fail",
        "scroll",
    ):
        i = text.find(name + "(")
        if i >= 0:
            return text[i:].strip()
    return None


def split_thought_and_code(text: str) -> tuple[str, str]:
    """从模型回复拆出 thought 和 python 代码。"""
    if not text:
        return "", ""
    code = extract_python_block(text) or ""
    # 去掉所有 ```python ... ``` 块，剩余当 thought
    thought = re.sub(
        r"```(?:python)?\s*.*?```", "", text, flags=re.DOTALL | re.IGNORECASE
    ).strip()
    if not code:
        return thought or text.strip(), ""
    return thought, code


def run_codeact(
    code: str,
    tools: dict[str, Callable[..., Any]],
) -> str:
    """执行代码；返回工具侧累计日志。禁止 import / 打开文件等。"""
    if not code or not code.strip():
        return "empty code"
    banned = ("import ", "__", "open(", "exec(", "eval(", "os.", "sys.", "subprocess")
    low = code.lower()
    for b in banned:
        if b in low or b in code:
            return f"rejected: contains `{b.strip()}`"

    log: list[str] = []

    def _wrap(fn: Callable[..., Any], name: str) -> Callable[..., Any]:
        def inner(*args, **kwargs):
            try:
                out = fn(*args, **kwargs)
            except Exception as e:  # noqa: BLE001
                msg = f"{name}{args} {kwargs} -> ERROR {e}"
                log.append(msg)
                return msg
            msg = f"{name}{args} {kwargs} -> {out}"
            log.append(msg)
            return out

        return inner

    g = {"__builtins__": {}}
    for k, fn in tools.items():
        g[k] = _wrap(fn, k)
    try:
        exec(code, g, g)  # noqa: S102  — 故意受限的 CodeAct 沙箱
    except Exception as e:  # noqa: BLE001
        log.append(f"exec error: {e}")
    return "\n".join(log) if log else "ok (no tool calls)"
