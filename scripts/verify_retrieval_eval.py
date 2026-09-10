#!/usr/bin/env python3
"""Fail-closed offline verifier for the frozen POWER 3.8 eval corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from power_framework.core.evaluation_contracts import (
    EvaluationIntegrityError,
    load_development_for_tuning,
    reject_holdout_tuning,
    verify_evaluation_corpus,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="frozen retrieval-evaluation v1 directory")
    parser.add_argument(
        "--mode",
        choices=("integrity", "tuning"),
        default="integrity",
        help="integrity reads and verifies holdout; tuning reads development only",
    )
    parser.add_argument(
        "--split",
        choices=("development", "holdout"),
        default="development",
        help="split requested by tuning mode",
    )
    args = parser.parse_args(argv)

    try:
        if args.mode == "integrity":
            result = verify_evaluation_corpus(args.root)
        else:
            reject_holdout_tuning(args.split)
            records = load_development_for_tuning(args.root)
            result = {
                "status": "PASS",
                "mode": "tuning",
                "split": "development",
                "query_count": len(records),
                "holdout_used": False,
            }
    except EvaluationIntegrityError as exc:
        print(json.dumps({"status": "FAIL", "error_code": exc.code}, sort_keys=True))
        return 1
    except Exception:
        # Keep malformed/unexpected verifier failures bounded and content-free.
        print(json.dumps({"status": "FAIL", "error_code": "verifier_error"}, sort_keys=True))
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
