"""Planner-Actor 与 AndroidWorld 挂接。"""

from __future__ import annotations

from typing import Any

from agent.actor import Actor
from agent.app_launch import normalize_app_name
from agent.baselines import MemoryBackend
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


class PALiteAgentCore:
    """observe_fn -> (image, ui, desc); execute_fn(action) -> error_str|None。"""

    def __init__(
        self,
        llm: MultimodalLLM,
        memory: MemoryBackend,
        *,
        max_planner_steps: int = 8,
        max_actor_steps: int = 12,
        use_verifier: bool = True,
    ):
        self.planner = Planner(llm)
        self.actor = Actor(llm)
        self.verifier = Verifier(llm)
        self.memory = memory
        self.max_planner_steps = max_planner_steps
        self.max_actor_steps = max_actor_steps
        self.use_verifier = use_verifier

        self.plan_queue: list = []
        self.planner_steps = 0
        self.history: list[str] = []
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
        self.memory.begin_episode()

    def notify_env_success(self, env_success: bool) -> None:
        self.memory.on_episode_end(bool(env_success))

    def run_one_env_step(
        self,
        task: str,
        observe_fn,
        execute_fn,
    ) -> tuple[bool, dict[str, Any]]:
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
            # 空计划不结束 episode，继续规划
            if not self.plan_queue:
                self.history.append("empty_plan")
                return False, {"phase": "empty_plan"}
            return False, {"phase": "planned", "n_plans": len(self.plan_queue)}

        plan = self.plan_queue[0]
        decision = self.memory.decide(plan)

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
            self.history.append(f"{'OK' if ok else 'FAIL'}-replay:{plan.goal}")
            self.metrics["memory_size"].append(self.memory.size())
            return False, {"phase": "replay", "success": ok, "goal": plan.goal}

        self.metrics["generations"] += 1
        new_traj: list[TrajectoryStep] = []
        actor_hist: list[str] = []
        sub_done = False
        sub_fail = False
        for _ in range(self.max_actor_steps):
            image_i, ui_i, screen_i = observe_fn()
            if not screen_i:
                screen_i = describe_ui_elements(ui_i)
            step = self.actor.act(task, plan, screen_i, image_i, actor_hist)
            action = step.action
            new_traj.append(TrajectoryStep(action=action, ui_hint=screen_i[:200]))
            self.metrics["actor_steps"] += 1
            self.metrics["generated_actions"] += 1
            if step.subtask_complete:
                sub_done = True
                actor_hist.append(f"{action} -> status=complete")
                break
            if step.subtask_failed:
                sub_fail = True
                actor_hist.append(f"{action} -> status=infeasible")
                break
            err = execute_fn(action)
            actor_hist.append(f"{action} -> {err or 'ok'}")
            if err:
                continue
            if action.get("action_type") == "status":
                break

        ok = bool(sub_done) and not sub_fail
        self.memory.commit(plan, new_traj, success=ok, decision=decision)
        self.plan_queue.pop(0)
        self.history.append(f"{'OK' if ok else 'FAIL'}-gen:{plan.goal}")
        self.metrics["memory_size"].append(self.memory.size())
        return False, {"phase": "generate", "success": ok, "goal": plan.goal}

    def _verify(self, plan, screen: str, image, traj) -> bool:
        if not self.use_verifier:
            return True
        parts = [f"{i+1}:{s.action}" for i, s in enumerate(traj[:24])]
        summary = f"{len(traj)} steps | " + " | ".join(parts)
        return self.verifier.verify(plan, screen, image, summary).success

    def _can_accept_task_done(self) -> bool:
        """无 OK 或近期有 FAIL 时不接受 task_done。"""
        if not any(h.startswith("OK") for h in self.history):
            return False
        if any(h.startswith("FAIL") for h in self.history[-5:]):
            return False
        return True


if _HAS_AW:

    class DMSPlannerActorAgent(base_agent.EnvironmentInteractingAgent):
        def __init__(self, env, llm: MultimodalLLM, memory: MemoryBackend, name: str = "dms_pa", **kwargs):
            super().__init__(env, name=name)
            self.core = PALiteAgentCore(llm, memory, **kwargs)
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

    class DMSPlannerActorAgent:  # type: ignore
        def __init__(self, *args, **kwargs):
            raise ImportError("未安装/不可导入 android_world，请使用 PALiteAgentCore。")
