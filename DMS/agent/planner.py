"""高层 Planner，分解总任务为子任务。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from agent import codeact_prompts as prompts
from agent.json_utils import extract_json_obj
from core.types import Plan
from models.llm_protocol import MultimodalLLM


@dataclass
class PlannerResult:
    plans: list[Plan]
    task_done: bool
    raw: str


class Planner:
    def __init__(self, llm: MultimodalLLM, max_plans: int = 5):
        self.llm = llm
        self.max_plans = max_plans

    def plan(
        self,
        task: str,
        screen_desc: str,
        image: np.ndarray | None,
        progress: str = "",
    ) -> PlannerResult:
        user = prompts.planner_user_prompt(task, screen_desc, progress)
        prompt = prompts.PLANNER_SYSTEM + "\n\n" + user
        images = [image] if image is not None else []
        text, _, _ = self.llm.predict_mm(prompt, images)
        obj = extract_json_obj(text) or {}
        if not isinstance(obj, dict):
            obj = {}
        task_done = bool(obj.get("task_done", False))
        plans: list[Plan] = []
        for item in obj.get("plans", [])[: self.max_plans]:
            if not isinstance(item, dict):
                continue
            pre = str(item.get("precondition", "")).strip()
            goal = str(item.get("goal", "")).strip()
            if pre and goal:
                plans.append(Plan(precondition=pre, goal=goal))
        return PlannerResult(plans=plans, task_done=task_done, raw=text or "")
