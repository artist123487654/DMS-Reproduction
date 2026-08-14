"""Planner-Actor Agent，挂接 AndroidWorld 与三种记忆后端。"""

from __future__ import annotations

from typing import Any

import numpy as np

from agent.actor import Actor
from agent.baselines import MemoryBackend, MemoryDecision
from agent.planner import Planner
from agent.ui_desc import describe_ui_elements
from agent.verifier import Verifier
from core.types import Plan, TrajectoryStep
from models.llm_protocol import MultimodalLLM

try:
    from android_world.agents import base_agent
    from android_world.env import json_action
    from android_world.env import interface as aw_interface

    _HAS_AW = True
except Exception:  
    _HAS_AW = False
    base_agent = None  
    json_action = None  
    aw_interface = None  


class PALiteAgentCore:
    """
    不绑定环境的 PA 循环核心，便于单测和独立运行。
    真正执行动作通过 execute_fn(action_dict) -> None。
    观察通过 observe_fn() -> (image, ui_elements, screen_desc)。
    """

    def __init__(
        self,
        llm: MultimodalLLM,
        memory: MemoryBackend,
        *,
        max_planner_steps: int = 12,
        max_actor_steps: int = 8,
        use_verifier: bool = True,
    ):
        self.planner = Planner(llm)
        self.actor = Actor(llm)
        self.verifier = Verifier(llm)
        self.memory = memory
        self.max_planner_steps = max_planner_steps
        self.max_actor_steps = max_actor_steps
        self.use_verifier = use_verifier

        self.plan_queue: list[Plan] = []
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

    def run_one_env_step(
        self,
        task: str,
        observe_fn,
        execute_fn,
    ) -> tuple[bool, dict[str, Any]]:
        """推进一个环境可感知步骤；done 表示整任务结束。"""
        self.memory.on_step_begin()
        image, ui_elements, screen_desc = observe_fn()

        # 需要规划
        if not self.plan_queue:
            if self.planner_steps >= self.max_planner_steps:
                return True, {"reason": "max_planner_steps"}
            progress = "; ".join(self.history[-5:])
            result = self.planner.plan(task, screen_desc, image, progress)
            self.planner_steps += 1
            if result.task_done and not result.plans:
                return True, {"reason": "planner_task_done", "raw": result.raw}
            # 风险抑制：跳过高风险 plan
            filtered = []
            for p in result.plans:
                if self.memory.suppress(p):
                    continue
                filtered.append(p)
            self.plan_queue = filtered or result.plans
            if not self.plan_queue:
                return True, {"reason": "empty_plan"}
            return False, {"phase": "planned", "n_plans": len(self.plan_queue)}

        plan = self.plan_queue[0]
        decision = self.memory.decide(plan)

        if decision.entry is not None and not decision.mutate:
            # 复放记忆轨迹
            traj = decision.entry.trajectory
            self.metrics["replays"] += 1
            for step in traj:
                execute_fn(step.action)
                self.metrics["actor_steps"] += 1
                self.metrics["reused_actions"] += 1
            image2, _, screen2 = observe_fn()
            ok = self._verify(plan, screen2, image2, traj)
            self.memory.commit(plan, list(traj), success=ok, decision=decision)
            self.plan_queue.pop(0)
            self.history.append(f"{'OK' if ok else 'FAIL'}-replay:{plan.goal}")
            self.metrics["memory_size"].append(self.memory.size())
            return False, {"phase": "replay", "success": ok, "goal": plan.goal}

        # 生成执行
        self.metrics["generations"] += 1
        new_traj: list[TrajectoryStep] = []
        actor_hist: list[str] = []
        sub_done = False
        sub_fail = False
        for _ in range(self.max_actor_steps):
            image_i, ui_i, screen_i = observe_fn()
            # 刷新描述
            if not screen_i:
                screen_i = describe_ui_elements(ui_i)
            step = self.actor.act(task, plan, screen_i, image_i, actor_hist)
            action = step.action
            new_traj.append(TrajectoryStep(action=action, ui_hint=screen_i[:200]))
            actor_hist.append(str(action))
            self.metrics["actor_steps"] += 1
            self.metrics["generated_actions"] += 1
            if step.subtask_complete:
                sub_done = True
                break
            if step.subtask_failed:
                sub_fail = True
                break
            execute_fn(action)
            if action.get("action_type") == "status":
                break

        image_f, _, screen_f = observe_fn()
        if sub_fail:
            ok = False
        elif sub_done and not self.use_verifier:
            ok = True
        else:
            ok = self._verify(plan, screen_f, image_f, new_traj) if new_traj else False

        self.memory.commit(plan, new_traj, success=ok, decision=decision)
        self.plan_queue.pop(0)
        self.history.append(f"{'OK' if ok else 'FAIL'}-gen:{plan.goal}")
        self.metrics["memory_size"].append(self.memory.size())
        # 失败则清空后续计划，迫使重规划
        if not ok:
            self.plan_queue = []
        return False, {"phase": "generate", "success": ok, "goal": plan.goal}

    def _verify(self, plan: Plan, screen: str, image, traj) -> bool:
        if not self.use_verifier:
            return True
        summary = f"{len(traj)} steps; last={traj[-1].action if traj else None}"
        return self.verifier.verify(plan, screen, image, summary).success


if _HAS_AW:

    class DMSPlannerActorAgent(base_agent.EnvironmentInteractingAgent):
        """AndroidWorld 可运行 Agent。"""

        def __init__(
            self,
            env,
            llm: MultimodalLLM,
            memory: MemoryBackend,
            name: str = "dms_pa",
            **kwargs,
        ):
            super().__init__(env, name=name)
            self.core = PALiteAgentCore(llm, memory, **kwargs)
            self._last_info: dict[str, Any] = {}

        def reset(self, go_home: bool = False) -> None:
            super().reset(go_home=go_home)
            self.core.reset_episode()

        def step(self, goal: str) -> base_agent.AgentInteractionResult:
            def observe():
                state = self.get_post_transition_state()
                image = state.pixels if hasattr(state, "pixels") else None
                ui = getattr(state, "ui_elements", []) or []
                desc = describe_ui_elements(ui)
                return image, ui, desc

            def execute(action_dict: dict[str, Any]) -> None:
                if action_dict.get("action_type") == "status":
                    return
                try:
                    act = json_action.JSONAction(**{
                        k: v for k, v in action_dict.items()
                        if k in getattr(json_action, "ACTION_KEYS", action_dict.keys())
                    })
                except Exception:
                    # 宽松构造
                    act = json_action.JSONAction(
                        action_type=action_dict.get("action_type", "wait"),
                        index=action_dict.get("index"),
                        text=action_dict.get("text"),
                        direction=action_dict.get("direction"),
                        app_name=action_dict.get("app_name"),
                        goal_status=action_dict.get("goal_status"),
                    )
                self.env.execute_action(act)

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
