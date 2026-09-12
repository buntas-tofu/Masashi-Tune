"""pytest twin of the selftest board; same goldens, one assert per line."""

from harness.selftest import _goldens


def test_goldens():
    for name, fn, want in _goldens():
        assert fn() == want, name


def test_single_object_is_one_row():
    """A rows contract asking for exactly one row accepts a bare object as
    that row (2026-08-18); the wrapper is not the judgment."""
    from harness.contract import OutputSpec, TaskContract
    from harness.judge import _parse_and_validate
    c = TaskContract(task_id="t", rubric="r", payload="p",
                     output=OutputSpec(shape="rows", columns=["doc", "proposals"], row_count=1))
    parsed, defaulted = _parse_and_validate('{"doc": "x", "proposals": "[]"}', c, None)
    assert parsed == [{"doc": "x", "proposals": "[]"}]
    # two rows asked, one object given: still a mismatch, still an error
    c2 = TaskContract(task_id="t", rubric="r", payload="p",
                      output=OutputSpec(shape="rows", columns=["doc"], row_count=2))
    try:
        _parse_and_validate('{"doc": "x"}', c2, None)
    except ValueError:
        pass
    else:
        raise AssertionError("a bare object must not satisfy a two-row contract")
