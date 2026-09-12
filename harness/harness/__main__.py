"""harness CLI.

  python -m harness selftest
  python -m harness judge --seat reasoner --contract task.json --out result.json
  python -m harness redteam --seat reviewer --artifact a.json --context ctx.txt --out r.json
"""

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(prog="harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")

    pj = sub.add_parser("judge")
    pj.add_argument("--seat", required=True)
    pj.add_argument("--contract", required=True, type=Path)
    pj.add_argument("--out", type=Path)
    pj.add_argument("--view", default=None)
    pj.add_argument("--one-pass", action="store_true")

    pr = sub.add_parser("redteam")
    pr.add_argument("--seat", default="")
    pr.add_argument("--artifact", required=True, type=Path)
    pr.add_argument("--context", required=True, type=Path)
    pr.add_argument("--out", type=Path)
    pr.add_argument("--view", default=None)

    args = ap.parse_args()

    if args.cmd == "selftest":
        from .selftest import run
        return run()

    from .view import ViewClient
    view = ViewClient(args.view) if args.view else ViewClient()

    if args.cmd == "judge":
        from .contract import load_contract
        from .judge import judge
        contract = load_contract(args.contract)
        if args.one_pass:
            contract.two_pass = False
        result = judge(args.seat, contract, view=view)
    else:
        from .redteam import redteam
        artifact = json.loads(args.artifact.read_text())
        result = redteam(artifact, args.context.read_text(), seat=args.seat, view=view)

    payload = result.to_dict()
    if args.out:
        args.out.write_text(json.dumps(payload, indent=1))
        print(f"result -> {args.out}")
    summary = {k: payload[k] for k in ("task_id", "valid", "flags", "errors")}
    summary["elapsed_s"] = payload["provenance"].get("elapsed_s")
    summary["usage"] = payload["provenance"].get("usage")
    print(json.dumps(summary, indent=1))
    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
