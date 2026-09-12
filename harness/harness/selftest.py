"""Offline golden checks: the harness's own board, no network, no seats.

Mirrors the engine selftest culture: wired to real failure modes observed
2026-07-08 (think-block leaks, reasoning-only replies, enum drift, silent row
loss) so a regression prints as a failed board line, not a surprise in a run.
"""

from .contract import OutputSpec, TaskContract
from .strip import extract_json, strip_think
from .validate import stamp_escalation, validate_rows

SPEC = OutputSpec(shape="rows", columns=["field", "cef_map"],
                  enums={"cef_map": ["Direct", "Proxy", "Inferable", "None"]},
                  row_count=2, flag_fields=["needs_review"])


def _goldens():
    yield ("strip closed think-block",
           lambda: strip_think("<think>secret deliberation</think>The answer is 4."),
           "The answer is 4.")
    yield ("strip unclosed think (reasoning-only signature)",
           lambda: strip_think("<think>ran to the token limit"), "")
    yield ("extract fenced json",
           lambda: extract_json('prose\n```json\n{"a": 1}\n```\nmore'), {"a": 1})
    yield ("extract balanced json inside prose",
           lambda: extract_json('Sure! Here you go: [{"x": 2}] hope that helps'),
           [{"x": 2}])
    yield ("reasoning-only raises",
           lambda: _raises(lambda: extract_json("")), True)
    yield ("row count mismatch caught",
           lambda: bool(validate_rows([{"field": "a", "cef_map": "Direct",
                                        "needs_review": ""}], SPEC)), True)
    yield ("enum violation caught",
           lambda: any("cef_map" in e for e in validate_rows(
               [{"field": "a", "cef_map": "Direct", "needs_review": ""},
                {"field": "b", "cef_map": "Sorta", "needs_review": ""}], SPEC)), True)
    yield ("clean rows pass",
           lambda: validate_rows(
               [{"field": "a", "cef_map": "Direct", "needs_review": ""},
                {"field": "b", "cef_map": "None", "needs_review": "LOW CONFIDENCE"}],
               SPEC), [])
    yield ("escalation composite >= 30",
           lambda: stamp_escalation([{"s1": 20, "s2": 15}, {"s1": 5, "s2": 5}],
                                    {"composite_fields": ["s1", "s2"],
                                     "composite_gte": 30}), 1)
    yield ("escalation on SSN claim",
           lambda: stamp_escalation([{"claims": "SSN"}, {"claims": "none"}],
                                    {"claim_fields": ["claims"],
                                     "claim_values": ["SSN", "NAME_FULL"]}), 1)
    yield ("prompt hash stable",
           lambda: TaskContract("t", "r", "p").prompt_hash()
           == TaskContract("t2", "r", "p").prompt_hash(), True)
    yield ("schema summary carries enums",
           lambda: "Direct" in TaskContract("t", "r", "p",
                                            output=SPEC).schema_summary(), True)
    yield ("chunk split preserves order and count",
           lambda: _chunk_check(), True)
    yield ("missing flag key defaults to unraised",
           lambda: _flag_default_check(), True)


def _flag_default_check() -> bool:
    from .contract import TaskContract
    from .judge import _parse_and_validate
    c = TaskContract("t", "r", "p", output=SPEC)
    text = ('[{"field": "a", "cef_map": "Direct"},'
            ' {"field": "b", "cef_map": "None", "needs_review": "check me"}]')
    rows, defaulted = _parse_and_validate(text, c, None)
    return defaulted == 1 and rows[0]["needs_review"] == "" \
        and rows[1]["needs_review"] == "check me"


def _chunk_check() -> bool:
    from .batch import split_chunks
    rows = list(range(80))
    chunks = split_chunks(rows, 12)
    flat = [x for c in chunks for x in c]
    return len(chunks) == 7 and flat == rows and len(chunks[-1]) == 8


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except ValueError:
        return True


def run() -> int:
    failed = 0
    for name, fn, want in _goldens():
        got = fn()
        ok = got == want
        failed += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name}"
              + ("" if ok else f"  got={got!r} want={want!r}"))
    total = sum(1 for _ in _goldens())
    print(f"\nselftest: {total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run())
