"""Red team: adversarial review of a verified artifact, made mechanical.

After the engine confirms an artifact, a second, larger seat adversarially
reviews it: is it minimal, is the claim airtight, is there a hidden assumption.
Refute-first framing; a pass verdict must be earned. The verdict is data.
"""

import os

from .contract import OutputSpec, TaskContract
from .judge import JudgeResult, judge
from .view import ViewClient

REDTEAM_RUBRIC = (
    "You are the red team. An artifact below has already passed deterministic "
    "engine verification; your job is to try to REFUTE it anyway, on the axes "
    "the engine cannot check. Attack in order: (1) minimality, is there a "
    "strictly smaller or simpler object with the same claimed property; "
    "(2) airtightness, does the stated claim actually follow from the object, "
    "with no step asserted but unproven; (3) hidden assumptions, does the "
    "construction smuggle in a convention or a boundary condition the task "
    "statement does not grant. Default to refute when uncertain. A verdict of "
    "pass must be earned by failing to find any attack that lands."
)


def redteam(artifact: dict, context: str, seat: str = "",
            view: ViewClient | None = None, task_id: str = "redteam") -> JudgeResult:
    import json

    seat = seat or os.environ.get("HARNESS_REDTEAM_SEAT", "reviewer")
    contract = TaskContract(
        task_id=task_id,
        rubric=REDTEAM_RUBRIC,
        anchors="",
        payload=("TASK CONTEXT:\n" + context + "\n\nARTIFACT UNDER REVIEW:\n"
                 + json.dumps(artifact, indent=1)),
        output=OutputSpec(shape="artifact",
                          artifact_keys=["verdict", "attacks_tried", "reasons"]),
        two_pass=True,
    )
    result = judge(seat, contract, view=view, label=task_id)
    if result.valid:
        verdict = str(result.artifact.get("verdict", "")).lower()
        if verdict not in ("pass", "refute"):
            result.valid = False
            result.errors = [f"verdict {verdict!r} not in ['pass', 'refute']"]
            result.flags.append("incomplete")
    return result
