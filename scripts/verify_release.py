#!/usr/bin/env python3
"""Verify a unified POWER release manifest and native-install plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from power_framework.core.integrations import _release_contract, build_native_install_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    args = parser.parse_args()

    wheel = args.wheel.expanduser().resolve()
    manifest = args.manifest.expanduser().resolve()
    contract = _release_contract(manifest, wheel)
    plan = build_native_install_plan(home=args.home, power_wheel=wheel, manifest=manifest)
    if plan["status"] not in {"ready", "update", "no_change"}:
        raise RuntimeError(f"unexpected native install plan status: {plan['status']}")
    report = {
        "status": "pass",
        "version": contract["version"],
        "commit": contract["commit"],
        "manifest_sha256": contract["manifest_sha256"],
        "wheel_sha256": plan["artifacts"]["power_wheel"]["sha256"],
        "native_plan_status": plan["status"],
        "launchers": plan["launchers"],
        "retired_launchers": plan["retired_launchers"],
        "web_entry_point": contract["web"]["entry_point"],
        "mcp_transport": contract["mcp"]["transport"],
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
