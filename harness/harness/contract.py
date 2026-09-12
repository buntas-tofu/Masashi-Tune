"""Task contracts: the structured input a judgment call requires.

A contract carries the rubric, the calibration anchors, the batch payload, and
the output schema. The schema drives validation (emitted rows) or names the
artifact keys the caller's engine will verify (constructed artifacts).
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OutputSpec:
    shape: str = "rows"              # "rows" | "artifact"
    columns: list = field(default_factory=list)
    enums: dict = field(default_factory=dict)        # column -> allowed values
    row_count: int | None = None
    flag_fields: list = field(default_factory=list)  # must survive as fields
    artifact_keys: list = field(default_factory=list)


@dataclass
class TaskContract:
    task_id: str
    rubric: str
    payload: str
    anchors: str = ""
    output: OutputSpec = field(default_factory=OutputSpec)
    escalation: dict | None = None   # {"composite_fields": [], "composite_gte": n,
                                     #  "claim_fields": [], "claim_values": []}
    two_pass: bool = True
    max_tokens: int | None = None    # per-call completion budget override
    # Sampling posture, declared by the TASK rather than guessed by the
    # transport (2026-07-30). Greedy by default because a contract exists to
    # produce a verdict, and a verdict read twice should read the same. Every
    # vessel carries temperature 0.6 for conversation, and a body that omits
    # temperature inherits it: that is how the harness came to score at
    # conversational settings on every call it ever made.
    #
    # Set None to take the seat's own setting, and only for a task whose value
    # is variety rather than a stable answer. Say why in `notes` when you do.
    temperature: float | None = 0.0
    notes: str = ""

    def prompt_hash(self) -> str:
        blob = json.dumps(
            {"rubric": self.rubric, "anchors": self.anchors, "payload": self.payload},
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def schema_summary(self) -> str:
        o = self.output
        if o.shape == "artifact":
            keys = ", ".join(o.artifact_keys) or "as specified in the task"
            return (f"Emit ONE JSON object with exactly these keys: {keys}. "
                    "Values must be concrete (integers and lists, no formulas, no prose).")
        parts = [f"Emit a JSON array of exactly {o.row_count} objects."
                 if o.row_count else "Emit a JSON array of objects."]
        if o.columns:
            parts.append("Every object must carry exactly these keys: "
                         + ", ".join(o.columns) + ".")
        for col, allowed in o.enums.items():
            parts.append(f"'{col}' must be one of: " + ", ".join(str(a) for a in allowed) + ".")
        if o.flag_fields:
            parts.append("Flag fields " + ", ".join(o.flag_fields)
                         + " are mandatory keys; use empty string when not raised.")
        return " ".join(parts)


def load_contract(path: str | Path) -> TaskContract:
    raw = json.loads(Path(path).read_text())
    out = raw.pop("output", {})
    return TaskContract(output=OutputSpec(**out), **raw)
