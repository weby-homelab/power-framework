#!/usr/bin/env python3
"""Fail-closed offline verifier for the frozen POWER 3.8 eval corpus."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from power_framework.core.evaluation_contracts import (
    EvaluationCorpusManifest,
    EvaluationIntegrityError,
    build_holdout_access_receipt,
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
    parser.add_argument(
        "--receipt-out",
        type=Path,
        help="optional exact output path for a bounded integrity-read receipt",
    )
    args = parser.parse_args(argv)

    try:
        if args.receipt_out is not None and args.mode != "integrity":
            raise EvaluationIntegrityError(
                "receipt_mode", "receipt output is available only for integrity verification"
            )
        if args.mode == "integrity":
            result = verify_evaluation_corpus(args.root)
            if args.receipt_out is not None:
                root = args.root.resolve()
                manifest = EvaluationCorpusManifest.model_validate(
                    json.loads((root / "manifest.json").read_text(encoding="utf-8"))
                )
                holdout_path = root / "queries.holdout.jsonl"
                receipt = build_holdout_access_receipt(
                    manifest,
                    rows_read=int(result["holdout_query_count"]),
                    bytes_read=holdout_path.stat().st_size,
                )
                output = args.receipt_out
                if not output.parent.is_dir():
                    raise EvaluationIntegrityError(
                        "receipt_parent", "receipt output directory is missing"
                    )
                resolved_output = output.resolve()
                if resolved_output == root or root in resolved_output.parents:
                    raise EvaluationIntegrityError(
                        "receipt_output",
                        "receipt output must not overwrite frozen corpus artifacts",
                    )
                with tempfile.NamedTemporaryFile(
                    mode="wb", dir=output.parent, prefix=".phase5a-receipt-", delete=False
                ) as temporary:
                    temporary.write(receipt.to_canonical_bytes() + b"\n")
                    temporary_path = Path(temporary.name)
                os.replace(temporary_path, output)
                result = {**result, "receipt_generated": True, "receipt_digest": receipt.digest()}
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
