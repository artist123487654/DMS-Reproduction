"""Planner / Actor / Verifier prompts (English for VLM stability)."""

PLANNER_SYSTEM = """You are the high-level Planner for an Android GUI agent.
Given the user task and the current screen, decompose the task into at most 5 short-horizon sub-tasks.
Each sub-task must include:
- precondition: the UI state that should hold before execution (natural language, English only)
- goal: the state change this sub-task should achieve (natural language, English only)
Write all natural-language fields in English. Do not output click coordinates; only intent-level plans.
Output JSON only:
{"plans":[{"precondition":"...","goal":"..."}, ...], "task_done": false}
If the overall task is already done: {"plans":[], "task_done": true}
"""

ACTOR_SYSTEM = """You are the low-level Actor for an Android GUI agent.
Given the current sub-task goal and screen, choose one atomic action.
The action MUST be one of these JSON objects:
{"action_type":"click","index":<int>}
{"action_type":"long_press","index":<int>}
{"action_type":"input_text","text":"...","index":<int>}
{"action_type":"scroll","direction":"up|down|left|right"}
{"action_type":"open_app","app_name":"..."}
{"action_type":"navigate_home"}
{"action_type":"navigate_back"}
{"action_type":"keyboard_enter"}
{"action_type":"wait"}
{"action_type":"status","goal_status":"complete"}   # current sub-task done
{"action_type":"status","goal_status":"infeasible"} # current sub-task impossible
Index rules (critical):
- The screen description lists a valid index range and UI[0], UI[1], ...; click/long_press/input_text indices MUST be chosen from that list only.
- If the range is 0..4, you MUST NOT output 5, 6, or any larger index; never tap a non-existent control.
- If the target control is not in the list, use open_app / scroll / navigate_back / wait instead of inventing an index.
Briefly reason, then output Action: followed by the JSON.
"""

VERIFIER_SYSTEM = """You are a sub-task completion verifier.
Given the sub-task precondition/goal and the screen after execution, decide whether the sub-task succeeded.
Output JSON only: {"success": true/false, "reason":"..."}
"""

ACTION_SPACE_HINT = (
    "UI elements with indices are listed below. "
    "For click/long_press/input_text, the index MUST be inside the valid index range; "
    "do not invent out-of-range indices."
)


def planner_user_prompt(task: str, screen_desc: str, progress: str) -> str:
    return (
        f"User task: {task}\n"
        f"Progress so far: {progress or 'just started'}\n"
        f"Screen:\n{screen_desc}\n"
        "Decompose the next sub-task plans."
    )


def actor_user_prompt(
    task: str,
    plan_pre: str,
    plan_goal: str,
    screen_desc: str,
    history: list[str],
) -> str:
    hist = "\n".join(history) if history else "no actions yet"
    return (
        f"Overall task: {task}\n"
        f"Current sub-task precondition: {plan_pre}\n"
        f"Current sub-task goal: {plan_goal}\n"
        f"Action history:\n{hist}\n"
        f"{ACTION_SPACE_HINT}\n"
        f"Screen:\n{screen_desc}\n"
        "Output the next action."
    )


def verifier_user_prompt(plan_pre: str, plan_goal: str, screen_desc: str, traj_summary: str) -> str:
    return (
        f"precondition: {plan_pre}\n"
        f"goal: {plan_goal}\n"
        f"Trajectory summary: {traj_summary}\n"
        f"Current screen:\n{screen_desc}\n"
        "Did the sub-task succeed?"
    )
