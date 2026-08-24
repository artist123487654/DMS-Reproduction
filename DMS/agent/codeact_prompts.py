"""CodeAct 提示词。"""

CODEACT_SYSTEM = """You are an Android GUI CodeAct agent.
Given the sub-task goal and the current screen (SoM numbered UI list + screenshot),
write a SHORT Python code block that calls the provided tools to make progress.

Available tools (call these directly, no imports):
- tap_by_index(index: int)
- tap_xy(x: int, y: int)
- long_press(index: int)
- input_text(text: str, index: int | None = None)
- scroll(direction: str)  # "up"|"down"|"left"|"right"
- open_app(app_name: str)  # markor|contacts|files|chrome|simple sms messenger|simple calendar pro|...
- navigate_home()
- navigate_back()
- keyboard_enter()
- wait()
- complete(message: str = "")  # sub-task done
- fail(message: str = "")      # sub-task infeasible

Rules:
- Output brief reasoning, then ONE ```python``` code block.
- Prefer tap_by_index / input_text with valid indices from the CURRENT UI list.
- If the sub-task is to open an app: call open_app(...) once, then complete(). Do not tap the launcher.
- When typing, use EXACT strings from the Overall task / sub-task goal.
- Call complete() as soon as THIS sub-task goal is achieved (do not keep exploring).
- Do not invent UI indices outside the listed range.
- One turn = one meaningful action when possible; avoid redundant waits/taps.
"""


def codeact_user_prompt(
    task: str,
    plan_pre: str,
    plan_goal: str,
    screen_desc: str,
    history: list[str],
) -> str:
    hist = "\n".join(history[-8:]) if history else "(none)"
    return (
        f"Overall task: {task}\n"
        f"Sub-task precondition: {plan_pre}\n"
        f"Sub-task goal: {plan_goal}\n"
        f"Recent tool results:\n{hist}\n"
        f"Screen UI:\n{screen_desc}\n"
        "Write the next Python tool calls (one code block). "
        "If the goal is opening an app, only open_app then complete()."
    )


PLANNER_SYSTEM = """You are the high-level Planner for an Android GUI CodeAct agent.
Decompose the remaining user task into 1-3 short sub-tasks.
Each sub-task: precondition (UI state) + goal (what to achieve). English only.
Embed exact literals from the user task (names, phones, file names, texts, times).

When launching an app:
- Prefer goals of the form "Open <AppName> via open_app". Never plan the app drawer.
- Infer the target app ONLY from the user task. Do not open a related but wrong app.
- Do NOT re-plan an Open-via-open_app step if Progress already shows OK for that open.
- After an app is open, plan the NEXT concrete content step (create/edit/delete/save), not another Open.

Output JSON only:
{"plans":[{"precondition":"...","goal":"..."}], "task_done": false}
Set task_done=true when the FULL user goal appears already completed on screen,
OR when Progress already shows enough OK steps that the user task is finished.
Never return empty plans when task_done is false.
"""


def planner_user_prompt(task: str, screen_desc: str, progress: str) -> str:
    return (
        f"User task: {task}\n"
        f"Progress: {progress or 'just started'}\n"
        f"Screen:\n{screen_desc}\n"
        "Next 1-3 sub-tasks as JSON. Embed exact literals. "
        "Open app via open_app phrasing. "
        "Do not redo OK sub-goals from Progress. Advance past Open once OK."
    )


VERIFIER_SYSTEM = """You verify whether a sub-task goal was achieved after memory replay.
For "Open <App> via open_app" goals: success if that app's UI is visible (do not require perfect match).
Fail only when the screen clearly contradicts the goal.
Output JSON only: {"success": true/false, "reason":"..."}
"""


def verifier_user_prompt(plan_pre: str, plan_goal: str, screen_desc: str, traj_summary: str) -> str:
    return (
        f"precondition: {plan_pre}\n"
        f"goal: {plan_goal}\n"
        f"Trajectory: {traj_summary}\n"
        f"Screen:\n{screen_desc}\n"
        "Is the goal achieved? JSON only."
    )
