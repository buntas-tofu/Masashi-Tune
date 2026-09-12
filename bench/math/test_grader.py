#!/usr/bin/env python3
"""test_grader.py: the grader graded before any contestant is.

The July lesson institutionalized: the first grader demanded ANSWER: format
and falsely zeroed the boxed-emitting OpenMath family. This suite feeds the
grader every format a seat has actually produced and requires 100 percent
before a heat counts. Plain asserts, stdlib only, exit 1 on any failure.
"""

import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from math_bench import extract_answer, grade, parse_value  # noqa: E402


def check(name, cond):
    status = "ok" if cond else "FAIL"
    print(f"  {status}  {name}")
    return cond


def main() -> int:
    results = []
    item_frac = {"answer": "3/4"}
    item_int = {"answer": "96"}
    item_neg = {"answer": "-21"}
    item_tol = {"answer": "13/18", "tol": 0.002}
    item_pct = {"answer": "5.53", "tol": 0.02}

    g = grade(item_frac, "Reasoning here.\nANSWER: 3/4")
    results.append(check("answer-line fraction", g["correct"] and g["method"] == "answer-line" and g["format_adherent"]))

    g = grade(item_frac, "Reasoning.\nANSWER: 0.75")
    results.append(check("decimal equals fraction exactly", g["correct"]))

    g = grade(item_frac, "So the sum is \\boxed{\\frac{3}{4}}.")
    results.append(check("boxed tex fraction, adherence false", g["correct"] and g["method"] == "boxed" and not g["format_adherent"]))

    g = grade(item_int, "<think>long budget spend 5148 not it</think>The count is 96.\nANSWER: 96")
    results.append(check("think block stripped", g["correct"]))

    g = grade(item_int, "After all that, the total number of strings is 96.")
    results.append(check("fallback last-line number", g["correct"] and g["method"] == "fallback"))

    g = grade(item_neg, "ANSWER: -21")
    results.append(check("negative integer", g["correct"]))

    g = grade(item_tol, "final answer: 0.722")
    results.append(check("tolerance decimal for repeating rational", g["correct"]))

    g = grade(item_pct, "ANSWER: 5.53%")
    results.append(check("percent sign stripped", g["correct"]))

    g = grade(item_int, "ANSWER: 5,148")
    results.append(check("comma number wrong value stays wrong", not g["correct"]))

    g = grade({"answer": "5148"}, "ANSWER: 5,148")
    results.append(check("comma number parses", g["correct"]))

    g = grade(item_int, "I cannot determine the answer.")
    results.append(check("no answer graded incorrect", not g["correct"] and g["method"] == "none"))

    g = grade(item_frac, "**Answer:** 3/4")
    results.append(check("markdown bold answer line", g["correct"]))

    raw, method = extract_answer("ANSWER: 10\nwait no\nANSWER: 12")
    results.append(check("last answer line wins", raw == "12"))

    results.append(check("tex frac parses", parse_value("\\frac{13}{18}") == Fraction(13, 18)))
    results.append(check("plain frac parses", parse_value("28/3") == Fraction(28, 3)))
    results.append(check("decimal parses exact", parse_value("14.7") == Fraction(147, 10)))

    n_bad = sum(1 for r in results if not r)
    print(f"{len(results) - n_bad}/{len(results)} grader checks passed")
    return 1 if n_bad else 0


if __name__ == "__main__":
    sys.exit(main())
