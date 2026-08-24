"""AndroidWorld 工具集：供 CodeAct 代码调用，并记录可复放动作。"""

from __future__ import annotations

from typing import Any, Callable

from agent.app_names import normalize_app_name


class CodeActToolkit:
    """工具副作用经 execute_fn 落到真机。"""

    def __init__(
        self,
        execute_fn: Callable[[dict[str, Any]], str | None],
        *,
        ui_count: int = 0,
    ):
        self.execute_fn = execute_fn
        self.ui_count = ui_count
        self.actions: list[dict[str, Any]] = []
        self.finished = False
        self.failed = False
        self.message = ""

    def _run(self, action: dict[str, Any]) -> str:
        self.actions.append(dict(action))
        err = self.execute_fn(action)
        return err or "ok"

    def tap_by_index(self, index: int) -> str:
        idx = int(index)
        if self.ui_count > 0 and (idx < 0 or idx >= self.ui_count):
            return f"bad index {idx}; valid 0..{self.ui_count - 1}"
        return self._run({"action_type": "click", "index": idx})

    def tap_xy(self, x: int, y: int) -> str:
        return self._run({"action_type": "click", "x": int(x), "y": int(y)})

    def long_press(self, index: int) -> str:
        idx = int(index)
        if self.ui_count > 0 and (idx < 0 or idx >= self.ui_count):
            return f"bad index {idx}; valid 0..{self.ui_count - 1}"
        return self._run({"action_type": "long_press", "index": idx})

    def input_text(self, text: str, index: int | None = None) -> str:
        action: dict[str, Any] = {"action_type": "input_text", "text": str(text)}
        if index is not None:
            idx = int(index)
            if self.ui_count > 0 and (idx < 0 or idx >= self.ui_count):
                return f"bad index {idx}; valid 0..{self.ui_count - 1}"
            action["index"] = idx
        return self._run(action)

    def scroll(self, direction: str = "down") -> str:
        d = str(direction).lower().strip()
        if d not in {"up", "down", "left", "right"}:
            d = "down"
        return self._run({"action_type": "scroll", "direction": d})

    def open_app(self, app_name: str) -> str:
        name = normalize_app_name(app_name)
        return self._run({"action_type": "open_app", "app_name": name})

    def navigate_home(self) -> str:
        return self._run({"action_type": "navigate_home"})

    def navigate_back(self) -> str:
        return self._run({"action_type": "navigate_back"})

    def keyboard_enter(self) -> str:
        return self._run({"action_type": "keyboard_enter"})

    def wait(self) -> str:
        return self._run({"action_type": "wait"})

    def complete(self, message: str = "") -> str:
        self.finished = True
        self.message = str(message or "complete")
        return "completed"

    def fail(self, message: str = "") -> str:
        self.failed = True
        self.finished = True
        self.message = str(message or "infeasible")
        return "failed"

    def as_globals(self) -> dict[str, Any]:
        return {
            "tap_by_index": self.tap_by_index,
            "tap_xy": self.tap_xy,
            "long_press": self.long_press,
            "input_text": self.input_text,
            "scroll": self.scroll,
            "open_app": self.open_app,
            "navigate_home": self.navigate_home,
            "navigate_back": self.navigate_back,
            "keyboard_enter": self.keyboard_enter,
            "wait": self.wait,
            "complete": self.complete,
            "fail": self.fail,
        }
