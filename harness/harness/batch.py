"""Batched row judgment: the token-aperture fix.

The view caps completion tokens per call (4,096 observed 2026-07-09, finish
reason 'length'), so a large form's fields can never return as one JSON breath.
judge_rows splits the payload rows into chunks sized to the aperture, runs the
judge spine per chunk with per-chunk row-count validation, and merges rows,
flags, errors, and usage into one result. Chunk failures are named per chunk,
never silent. This is also simply how Pass 2 scales: the 1040 carries 189
logical fields.
"""

import time
from dataclasses import replace

from .contract import TaskContract
from .judge import JudgeResult, judge
from .view import ViewClient


def split_chunks(rows: list, size: int) -> list:
    if size < 1:
        raise ValueError("chunk size must be >= 1")
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def judge_rows(seat: str, contract: TaskContract, payload_rows: list,
               chunk_size: int = 16, payload_header: str = "",
               two_pass: bool = False, verify=None,
               view: ViewClient | None = None) -> JudgeResult:
    import json

    view = view or ViewClient()
    t0 = time.time()
    merged = JudgeResult(task_id=contract.task_id, shape="rows")
    usage_total: dict = {}
    retries = 0
    chunks = split_chunks(payload_rows, chunk_size)

    for n, chunk in enumerate(chunks):
        sub = replace(
            contract,
            task_id=f"{contract.task_id}/chunk{n}",
            payload=(payload_header + "\n" if payload_header else "")
            + json.dumps(chunk, indent=0),
            output=replace(contract.output, row_count=len(chunk)),
            two_pass=two_pass,
        )
        r = judge(seat, sub, verify=verify, view=view, label=sub.task_id)
        merged.rows.extend(r.rows)
        retries += r.provenance.get("retries", 0)
        for k, v in (r.provenance.get("usage") or {}).items():
            usage_total[k] = usage_total.get(k, 0) + v
        if not r.valid:
            merged.errors.append(f"chunk {n} ({len(chunk)} rows): "
                                 + "; ".join(r.errors))
        for f in r.flags:
            if f.startswith("escalations:"):
                continue
            if f"chunk{n}:{f}" not in merged.flags:
                merged.flags.append(f"chunk{n}:{f}")

    merged.valid = not merged.errors and len(merged.rows) == len(payload_rows)
    if not merged.valid and "incomplete" not in merged.flags:
        merged.flags.append("incomplete")
    esc = sum(1 for r in merged.rows if r.get("escalate"))
    if esc:
        merged.flags.append(f"escalations:{esc}")
    merged.provenance = view.seat_provenance(seat)
    merged.provenance.update({
        "task_id": contract.task_id, "prompt_hash": contract.prompt_hash(),
        "chunks": len(chunks), "chunk_size": chunk_size, "two_pass": two_pass,
        "retries": retries, "usage": usage_total,
        "elapsed_s": round(time.time() - t0, 1),
        "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    return merged
