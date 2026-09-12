"""harness: the fabric's solve/judgment layer.

One spine, two verifiers: judge() carries a structured task contract to a seat,
separates reasoning from verdict (two-pass protocol plus channel handling),
validates before accepting (contract schema for emitted-row work; the caller's
deterministic engine for constructed-artifact work), retries once with the error
named, and tags everything with provenance. Raw seat chat is the documented
degraded mode; this package is the fix.
"""

from .batch import judge_rows
from .contract import TaskContract, load_contract
from .judge import JudgeResult, judge
from .redteam import redteam
from .view import ViewClient

__version__ = "0.1.0"
__all__ = ["TaskContract", "load_contract", "JudgeResult", "judge", "judge_rows",
           "redteam", "ViewClient"]
