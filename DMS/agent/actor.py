"""底层 Actor Agent：逐步生成原子动作。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from agent import prompts
from agent.json_utils import extract_action_json
from core.types import Plan
from models.llm_protocol import MultimodalLLM


@dataclass
class ActorStep:
    action: dict[str, Any]
    raw: str
    subtask_complete: bool = False
    subtask_failed: bool = False


class Actor:
    def __init__(self, llm: MultimodalLLM):
        self.llm = llm

    def act(
        self,
        task: str,
        plan: Plan,
        screen_desc: str,
        image: np.ndarray | None,
        history: list[str],
    ) -> ActorStep:
        user = prompts.actor_user_prompt(
            task, plan.precondition, plan.goal, screen_desc, history
        )
        prompt = prompts.ACTOR_SYSTEM + "\n\n" + user
        images = [image] if image is not None else []
        text, _, _ = self.llm.predict_mm(prompt, images)
        action = extract_action_json(text or "") or {"action_type": "wait"}
        status = str(action.get("goal_status", "")).lower()
        complete = action.get("action_type") == "status" and status == "complete"
        failed = action.get("action_type") == "status" and status == "infeasible"
        return ActorStep(
            action=action,
            raw=text or "",
            subtask_complete=complete,
            subtask_failed=failed,
        )
