"""judge(): the shared spine. One structured call, reasoning separated from
verdict, nothing accepted unvalidated, one bounded retry with the error named,
provenance on everything. Schema-validated work checks against the contract;
constructed work is confirmed by the caller's deterministic engine, passed in
as verify.
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from .contract import TaskContract
from .strip import extract_json, strip_think
from .validate import stamp_escalation, validate_artifact, validate_rows
from .view import ViewClient

HARNESS_VERSION = "0.1.1"
REASONING_TAIL = 6000  # chars of reasoning fed forward when content is empty

# Seat-aware completion budgets for contracts that do not carry their own
# (2026-07-23, the reasoning-depth session). Thinking seats starve at the
# downstream 4k default: a reasoning seat closes easy work under 1k tokens and
# medium work under an observed 8.2k tail, so 16384 covers the distribution.
# Budgets past 32k bought rumination, not closure, so proof-grade work rides
# two_pass structure, and this cap is a watchdog, not a memory guard.
#
# The mapping is deployment-specific, so it is supplied through the
# HARNESS_SEAT_BUDGETS environment variable (a JSON object mapping seat name to
# integer completion tokens) rather than baked into the code. Example:
#   HARNESS_SEAT_BUDGETS='{"reasoner": 16384}'
def seat_budget_defaults() -> dict:
    raw = os.environ.get("HARNESS_SEAT_BUDGETS", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out

PASS1_FOOTER = (
    "\n\nWork the task through carefully and completely. State your analysis "
    "and conclusions in plain text. Do NOT emit the final structured output "
    "yet, and do not invoke any tools; plain text only."
)
PASS2_TEMPLATE = (
    "Based on your analysis above, emit ONLY the final output now. {schema} "
    "Output raw JSON only: no prose, no explanation, no markdown fences."
)
RETRY_TEMPLATE = (
    "Your output failed validation. Errors: {errors}. "
    "Emit the corrected output now. {schema} Raw JSON only, nothing else."
)
SINGLE_TEMPLATE = "{body}\n\n{schema} Output raw JSON only: no prose, no fences."


@dataclass
class JudgeResult:
    task_id: str
    valid: bool = False
    shape: str = "rows"
    rows: list = field(default_factory=list)
    artifact: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id, "valid": self.valid, "shape": self.shape,
            "rows": self.rows, "artifact": self.artifact, "flags": self.flags,
            "errors": self.errors, "provenance": self.provenance,
        }

    def save(self, path: str | Path):
        Path(path).write_text(json.dumps(self.to_dict(), indent=1))


def _accumulate(usage_total: dict, usage: dict):
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        usage_total[k] = usage_total.get(k, 0) + int(usage.get(k, 0) or 0)


def _parse_and_validate(text: str, contract: TaskContract, verify):
    parsed = extract_json(text)  # raises ValueError on no-JSON
    defaulted = 0
    if (contract.output.shape != "artifact" and isinstance(parsed, dict)
            and contract.output.row_count == 1):
        # One row was asked for and one object came back. The wrapper is not
        # the judgment: a rubric that says "emit ONE object" and a schema that
        # says "a JSON array of exactly 1 objects" both describe this reply,
        # and failing it bought a full re-emission on a third of the wave-4
        # gate documents (2026-08-18, 11 of 33 retried at thousands of tokens
        # each). Coerce, and let validate_rows judge the row itself.
        parsed = [parsed]
    if contract.output.shape == "artifact":
        errors = validate_artifact(parsed, contract.output)
    else:
        # A missing flag key is an unraised flag, not a broken row; default it
        # to empty rather than failing good judgments over bookkeeping, and
        # count the defaults so the omission stays visible.
        if isinstance(parsed, list):
            for row in parsed:
                if isinstance(row, dict):
                    for f in contract.output.flag_fields:
                        if f not in row:
                            row[f] = ""
                            defaulted += 1
        errors = validate_rows(parsed, contract.output)
    if not errors and verify is not None:
        ok, verrors = verify(parsed)
        if not ok:
            errors = ["engine verification failed"] + list(verrors)
    if errors:
        raise ValueError("; ".join(errors[:12]))
    return parsed, defaulted


def judge(seat: str, contract: TaskContract, verify=None,
          view: ViewClient | None = None, label: str = "") -> JudgeResult:
    view = view or ViewClient()
    label = label or contract.task_id
    budget = contract.max_tokens
    if budget is None:
        budget = seat_budget_defaults().get(seat)
    t0 = time.time()
    result = JudgeResult(task_id=contract.task_id, shape=contract.output.shape)
    prov = view.seat_provenance(seat)
    prov.update({
        "task_id": contract.task_id, "prompt_hash": contract.prompt_hash(),
        "harness_version": HARNESS_VERSION, "two_pass": contract.two_pass,
        "temperature": contract.temperature,
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "retries": 0,
    })
    usage_total: dict = {}

    body = "\n\n".join(x for x in (contract.rubric, contract.anchors, contract.payload) if x)
    messages: list = []
    if contract.two_pass:
        messages.append({"role": "user", "content": body + PASS1_FOOTER})
        r1 = view.chat(seat, messages, label=f"{label}/pass1",
                       max_tokens=budget, temperature=contract.temperature)
        _accumulate(usage_total, r1.usage)
        analysis = strip_think(r1.content) or r1.reasoning[-REASONING_TAIL:]
        if not analysis.strip():
            analysis = "(no analysis emitted; proceed directly and carefully)"
        messages.append({"role": "assistant", "content": analysis})
        messages.append({"role": "user",
                         "content": PASS2_TEMPLATE.format(schema=contract.schema_summary())})
    else:
        messages.append({"role": "user",
                         "content": SINGLE_TEMPLATE.format(body=body,
                                                           schema=contract.schema_summary())})

    parsed = None
    defaulted = 0
    for attempt in (0, 1):  # the contract's one bounded retry
        reply = view.chat(seat, messages, label=f"{label}/verdict{attempt}",
                          max_tokens=budget, temperature=contract.temperature)
        _accumulate(usage_total, reply.usage)
        verdict_text = strip_think(reply.content)
        try:
            parsed, defaulted = _parse_and_validate(verdict_text, contract, verify)
            break
        except ValueError as e:
            result.errors = [str(e)]
            if attempt == 0:
                prov["retries"] = 1
                result.flags.append("retried")
                messages.append({"role": "assistant", "content": verdict_text or "(empty)"})
                messages.append({"role": "user", "content": RETRY_TEMPLATE.format(
                    errors=str(e)[:600], schema=contract.schema_summary())})

    prov.update({"usage": usage_total, "elapsed_s": round(time.time() - t0, 1),
                 "finished": time.strftime("%Y-%m-%dT%H:%M:%S")})
    result.provenance = prov

    if parsed is None:
        result.flags.append("incomplete")
        return result

    result.valid = True
    result.errors = []
    if defaulted:
        result.flags.append(f"flags_defaulted:{defaulted}")
    if contract.output.shape == "artifact":
        result.artifact = parsed
    else:
        result.rows = parsed
        n = stamp_escalation(result.rows, contract.escalation)
        if n:
            result.flags.append(f"escalations:{n}")
    return result
