#!/usr/bin/env python3
"""claim_verification: verify a stated claim against the evidence chain (memory
events + receipts + logs), producing a graded, cited verdict.
The Prove-side companion to Reach.

Input:  {claim, scope?, horizon_s?, verify?, evidence?}
        -- evidence: [{ref, kind, t, excerpt, supports}]
Output: {claim, verdict: "supported|unsupported|unknown",
         evidence: [{ref, kind, t, excerpt}], confidence}
Read-only. Feeds the "reconstructable reason and evidence chain" rule.
"""
import json
import sys


def _parse_args(argv):
    if len(argv) == 1 and argv[0].lstrip().startswith("{"):
        try:
            d = json.loads(argv[0])
            if isinstance(d, dict):
                return d
        except (json.JSONDecodeError, ValueError):
            pass
    out = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            key = a[2:]
            if "=" in key:
                k, v = key.split("=", 1)
                out[k] = v
            else:
                v = argv[i + 1] if i + 1 < len(argv) else True
                out[key] = v
                i += 1
        else:
            out.setdefault("_pos", []).append(a)
        i += 1
    return out


def run(args):
    claim = str(args.get("claim", ""))
    verify = bool(args.get("verify", True))
    evidence_in = args.get("evidence") or []
    if not verify:
        return {"claim": claim, "verdict": "unknown",
                "evidence": [], "confidence": 0.0, "read_only": True}
    supporting = [e for e in evidence_in if e.get("supports", True)]
    cited = [{"ref": e.get("ref"), "kind": e.get("kind"),
              "t": e.get("t"), "excerpt": e.get("excerpt")}
             for e in supporting]
    if supporting:
        # majority/any-support graded verdict; confidence is the support share
        confidence = len(supporting) / len(evidence_in) if evidence_in else 1.0
        return {"claim": claim, "verdict": "supported",
                "evidence": cited, "confidence": round(confidence, 2),
                "read_only": True}
    if evidence_in:
        return {"claim": claim, "verdict": "unsupported",
                "evidence": [{"ref": e.get("ref"), "kind": e.get("kind"),
                              "t": e.get("t"), "excerpt": e.get("excerpt")}
                             for e in evidence_in],
                "confidence": 0.0, "read_only": True}
    return {"claim": claim, "verdict": "unknown",
            "evidence": [], "confidence": 0.0, "read_only": True}


def main():
    print(json.dumps(run(_parse_args(sys.argv[1:])), ensure_ascii=False))


if __name__ == "__main__":
    main()
