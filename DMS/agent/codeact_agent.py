"""CodeAct × DMS × AndroidWorld（独立实现，不 import 官方 DMS 包）。"""

from __future__ import annotations

from typing import Any

from agent.baselines import MemoryBackend
from agent.codeact_exec import extract_python_block, run_codeact
from agent import codeact_prompts as prompts
from agent.codeact_tools import CodeActToolkit
from agent.planner import Planner
from agent.ui_desc import describe_ui_elements, overlay_som
from agent.verifier import Verifier
from core.types import TrajectoryStep
from models.llm_protocol import MultimodalLLM

try:
    from android_world.agents import base_agent
    from android_world.env import json_action

    _HAS_AW = True
except Exception:
    _HAS_AW = False
    base_agent = None
    json_action = None


class CodeActAgentCore:
    """Planner 出子任务 → 检索/复放或 CodeAct 生成 → 回流 DMS。"""

    def __init__(
        self,
        llm: MultimodalLLM,
        memory: MemoryBackend,
        *,
        max_planner_steps: int = 8,
        max_codeact_turns: int = 12,
        use_verifier: bool = True,
    ):
        self.planner = Planner(llm)
        self.verifier = Verifier(llm)
        self.llm = llm
        self.memory = memory
        self.max_planner_steps = max_planner_steps
        self.max_codeact_turns = max_codeact_turns
        self.use_verifier = use_verifier

        self.plan_queue: list = []
        self.planner_steps = 0
        self.history: list[str] = []
        self._gen_traj: list[TrajectoryStep] = []
        self._gen_hist: list[str] = []
        self._gen_turns = 0
        self.metrics: dict[str, Any] = {
            "actor_steps": 0,
            "replays": 0,
            "generations": 0,
            "reused_actions": 0,
            "generated_actions": 0,
            "memory_size": [],
            "tokens_hint": 0,
        }

    def reset_episode(self) -> None:
        self.plan_queue = []
        self.planner_steps = 0
        self.history = []
        self._gen_traj = []
        self._gen_hist = []
        self._gen_turns = 0
        self.memory.begin_episode()

    def notify_env_success(self, env_success: bool) -> None:
        self.memory.on_episode_end(bool(env_success))

    def run_one_env_step(self, task: str, observe_fn, execute_fn) -> tuple[bool, dict[str, Any]]:
        self.memory.on_step_begin()
        image, ui_elements, screen_desc = observe_fn()

        if not self.plan_queue:
            if self.planner_steps >= self.max_planner_steps:
                return True, {"reason": "max_planner_steps"}
            progress = "; ".join(self.history[-5:])
            result = self.planner.plan(task, screen_desc, image, progress)
            self.planner_steps += 1
            if result.task_done and not result.plans:
                if self._can_accept_task_done():
                    return True, {"reason": "planner_task_done", "raw": result.raw}
                self.history.append("REJECT-task_done")
                return False, {"phase": "reject_task_done"}
            self.plan_queue = [p for p in result.plans if not self.memory.suppress(p)]
            if not self.plan_queue:
                self.history.append("empty_plan")
                return False, {"phase": "empty_plan"}
            self._reset_gen_state()
            return False, {"phase": "planned", "n_plans": len(self.plan_queue)}

        plan = self.plan_queue[0]
        decision = self.memory.decide(plan)

        # ---------- 记忆复放（整段轨迹）----------
        if decision.entry is not None and not decision.mutate:
            traj = decision.entry.trajectory
            self.metrics["replays"] += 1
            exec_errs = 0
            for step in traj:
                err = execute_fn(step.action)
                self.metrics["actor_steps"] += 1
                self.metrics["reused_actions"] += 1
                if err:
                    exec_errs += 1
            image2, _, screen2 = observe_fn()
            if exec_errs:
                ok = False
            elif image2 is None:
                ok = True
            else:
                ok = self._verify(plan, screen2, image2, traj)
            self.memory.commit(plan, list(traj), success=ok, decision=decision)
            self.plan_queue.pop(0)
            self._reset_gen_state()
            self.history.append(f"{'OK' if ok else 'FAIL'}-replay:{plan.goal}")
            self.metrics["memory_size"].append(self.memory.size())
            return False, {"phase": "replay", "success": ok, "goal": plan.goal}

        # ---------- CodeAct 生成（每 env step 一轮）----------
        self.metrics["generations"] += 1
        image_i, ui_i, screen_i = observe_fn()
        if not screen_i:
            screen_i = describe_ui_elements(ui_i)
        toolkit = CodeActToolkit(execute_fn, ui_count=len(ui_i or []))
        user = prompts.codeact_user_prompt(
            task, plan.precondition, plan.goal, screen_i, self._gen_hist
        )
        prompt = prompts.CODEACT_SYSTEM + "\n\n" + user
        images = [image_i] if image_i is not None else []
        text, _, _ = self.llm.predict_mm(prompt, images)
        code = extract_python_block(text or "") or ""
        result_log = run_codeact(code, toolkit.as_globals())
        for act in toolkit.actions:
            self._gen_traj.append(TrajectoryStep(action=act, ui_hint=screen_i[:200]))
            self.metrics["actor_steps"] += 1
            self.metrics["generated_actions"] += 1
        self._gen_hist.append(result_log[:500])
        self._gen_turns += 1

        sub_done = toolkit.finished and not toolkit.failed
        sub_fail = toolkit.failed
        budget_out = self._gen_turns >= self.max_codeact_turns

        if sub_done or sub_fail or budget_out:
            ok = bool(sub_done) and not sub_fail
            self.memory.commit(plan, list(self._gen_traj), success=ok, decision=decision)
            self.plan_queue.pop(0)
            self.history.append(f"{'OK' if ok else 'FAIL'}-gen:{plan.goal}")
            self.metrics["memory_size"].append(self.memory.size())
            info = {
                "phase": "codeact",
                "success": ok,
                "goal": plan.goal,
                "turns": self._gen_turns,
            }
            self._reset_gen_state()
            return False, info

        return False, {
            "phase": "codeact_continue",
            "goal": plan.goal,
            "turns": self._gen_turns,
        }

    def _reset_gen_state(self) -> None:
        self._gen_traj = []
        self._gen_hist = []
        self._gen_turns = 0

    def _verify(self, plan, screen: str, image, traj) -> bool:
        if not self.use_verifier:
            return True
        parts = [f"{i+1}:{s.action}" for i, s in enumerate(traj[:24])]
        summary = f"{len(traj)} steps | " + " | ".join(parts)
        return self.verifier.verify(plan, screen, image, summary).success

    def _can_accept_task_done(self) -> bool:
        if not any(h.startswith("OK") for h in self.history):
            return False
        if any(h.startswith("FAIL") for h in self.history[-5:]):
            return False
        return True


if _HAS_AW:

    class DMSCodeActAgent(base_agent.EnvironmentInteractingAgent):
        def __init__(
            self,
            env,
            llm: MultimodalLLM,
            memory: MemoryBackend,
            name: str = "dms_codeact",
            **kwargs,
        ):
            super().__init__(env, name=name)
            # 兼容旧配置名 max_actor_steps
            if "max_actor_steps" in kwargs and "max_codeact_turns" not in kwargs:
                kwargs["max_codeact_turns"] = kwargs.pop("max_actor_steps")
            self.core = CodeActAgentCore(llm, memory, **kwargs)
            self._last_info: dict[str, Any] = {}

        def reset(self, go_home: bool = False) -> None:
            super().reset(go_home=go_home)
            self.core.reset_episode()

        def notify_env_success(self, env_success: bool) -> None:
            self.core.notify_env_success(env_success)

        def step(self, goal: str) -> base_agent.AgentInteractionResult:
            latest_ui: list[Any] = []

            def observe():
                nonlocal latest_ui
                state = self.get_post_transition_state()
                raw = state.pixels if hasattr(state, "pixels") else None
                ui = list(getattr(state, "ui_elements", []) or [])
                latest_ui = ui
                desc = describe_ui_elements(ui)
                image = overlay_som(raw, ui)
                return image, ui, desc

            def execute(action_dict: dict[str, Any]) -> str | None:
                if action_dict.get("action_type") == "status":
                    return None
                action_dict = dict(action_dict)
                atype = action_dict.get("action_type")
                if atype == "open_app":
                    from agent.app_names import normalize_app_name

                    action_dict["app_name"] = normalize_app_name(action_dict.get("app_name"))

                has_xy = action_dict.get("x") is not None and action_dict.get("y") is not None
                needs_index = atype in {"click", "long_press", "input_text"} and not has_xy
                if needs_index:
                    n = len(latest_ui)
                    try:
                        idx_i = int(action_dict.get("index"))
                    except (TypeError, ValueError):
                        return f"invalid index {action_dict.get('index')!r}; valid 0..{n - 1}"
                    if n <= 0 or idx_i < 0 or idx_i >= n:
                        return f"index {idx_i} out of range 0..{max(n - 1, 0)}"
                    action_dict["index"] = idx_i
                    if atype in {"click", "long_press"}:
                        bb = getattr(latest_ui[idx_i], "bbox_pixels", None)
                        if bb is not None:
                            try:
                                cx, cy = bb.center
                                action_dict = {
                                    "action_type": atype,
                                    "x": int(cx),
                                    "y": int(cy),
                                }
                            except Exception:
                                pass
                try:
                    keys = getattr(json_action, "ACTION_KEYS", action_dict.keys())
                    act = json_action.JSONAction(
                        **{k: v for k, v in action_dict.items() if k in keys}
                    )
                except Exception as e:
                    return f"bad action json: {e}"
                try:
                    self.env.execute_action(act)
                except Exception as e:
                    return f"execute failed: {e}"
                return None

            done, info = self.core.run_one_env_step(goal, observe, execute)
            self._last_info = info
            data = {
                "info": info,
                "metrics": dict(self.core.metrics),
                "memory_size": self.core.memory.size(),
                "history": list(self.core.history),
            }
            return base_agent.AgentInteractionResult(done=done, data=data)

else:

    class DMSCodeActAgent:  # type: ignore
        def __init__(self, *args, **kwargs):
            raise ImportError("未安装/不可导入 android_world，请使用 CodeActAgentCore。")
