"""子任务验证。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from agent import prompts
from agent.json_utils import extract_json_obj
from core.types import Plan
from models.llm_protocol import MultimodalLLM


@dataclass
class VerifyResult:
    success: bool
    reason: str
    raw: str


class Verifier:
    def __init__(self, llm: MultimodalLLM):
        self.llm = llm

    def verify(
        self,
        plan: Plan,
        screen_desc: str,
        image: np.ndarray | None,
        traj_summary: str,
    ) -> VerifyResult:
        user = prompts.verifier_user_prompt(
            plan.precondition, plan.goal, screen_desc, traj_summary
        )
        prompt = prompts.VERIFIER_SYSTEM + "\n\n" + user
        images = [image] if image is not None else []
        text, _, _ = self.llm.predict_mm(prompt, images)
        obj = extract_json_obj(text) or {}
        if not isinstance(obj, dict):
            obj = {}
        return VerifyResult(
            success=bool(obj.get("success", False)),
            reason=str(obj.get("reason", "")),
            raw=text or "",
        )
