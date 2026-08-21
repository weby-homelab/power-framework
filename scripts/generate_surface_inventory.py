#!/usr/bin/env python3
"""Generate the content-free POWER public-surface compatibility inventory."""

from __future__ import annotations

import argparse
import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from power_framework.core.capabilities import manifest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "release" / "evidence" / "surface-inventory-v1.json"

LEGACY_COMMANDS = {
    "status": "doctor/control-plane",
    "cron": "maintenance plan",
    "heal": "maintenance plan/apply",
    "rot": "maintenance plan",
    "archive": "maintenance plan/apply with explicit approval",
    "synthesize": "explicit ingest workflow",
}

CORE_CAPABILITIES = [
    "vault-discovery",
    "lightweight-doctor",
    "okf-validation",
    "fts-retrieval",
    "safe-import",
    "application-service",
    "transactional-mutation",
    "durable-handoff",
    "provenance-record",
    "local-stdio-mcp",
]

OPTIONAL_TRACKS: dict[str, dict[str, str | None]] = {
    "fleet": {
        "description": "immutable artifact export/import and worker jobs",
        "status": "quarantined",
        "named_consumer": None,
        "owner": "release-maintainers",
        "slo": "none until the Phase 10 importer gate is green",
        "benchmark": "Phase 10 sealed fleet benchmark (not a 3.6.7 gate)",
        "threat_model": "docs/threat-model.md",
        "expiry": "revisit before the next minor release",
        "kill_criterion": "no manifest-bound rollback-safe consumer",
    },
    "bench": {
        "description": "benchmark runners and resource probes",
        "status": "optional",
        "named_consumer": "CI release-integrity jobs",
        "owner": "release-maintainers",
        "slo": "content-free receipts and reproducible runner commands",
        "benchmark": "benchmarks/power35 and benchmarks/power31",
        "threat_model": "docs/threat-model.md",
        "expiry": "review at every release",
        "kill_criterion": "receipt cannot reproduce the declared claim",
    },
    "remote": {
        "description": "authenticated remote MCP profile",
        "status": "quarantined",
        "named_consumer": None,
        "owner": "security-maintainers",
        "slo": "none until remote threat and compatibility gates are green",
        "benchmark": "remote MCP conformance (not a 3.6.7 gate)",
        "threat_model": "docs/threat-model.md",
        "expiry": "revisit before the next minor release",
        "kill_criterion": "no least-privilege, offline-safe consumer",
    },
    "experimental": {
        "description": "alternate models and experimental adapters",
        "status": "quarantined",
        "named_consumer": None,
        "owner": "retrieval-maintainers",
        "slo": "none until an experiment has a declared quality budget",
        "benchmark": "experiment-specific sealed benchmark",
        "threat_model": "docs/threat-model.md",
        "expiry": "revisit before the next minor release",
        "kill_criterion": "no owner, consumer, quality receipt, or budget",
    },
    "qwen3": {
        "description": "explicit experimental Qwen3 embedding profile",
        "status": "quarantined",
        "named_consumer": None,
        "owner": "retrieval-maintainers",
        "slo": "none until an explicit quality/resource comparison exists",
        "benchmark": "sealed retrieval quality comparison",
        "threat_model": "docs/threat-model.md",
        "expiry": "revisit before the next minor release",
        "kill_criterion": "no declared quality improvement over FTS",
    },
    "semantic": {
        "description": "dense retrieval accelerator",
        "status": "optional",
        "named_consumer": "explicit semantic retrieval profile",
        "owner": "retrieval-maintainers",
        "slo": "must fail closed and expose provider/generation/resource receipt",
        "benchmark": "benchmarks/power31 semantic quality comparison",
        "threat_model": "docs/threat-model.md",
        "expiry": "review at every release",
        "kill_criterion": "no quality improvement within the frozen resource budget",
    },
    "rerank": {
        "description": "cross-encoder reranking accelerator",
        "status": "optional",
        "named_consumer": "explicit reranked retrieval profile",
        "owner": "retrieval-maintainers",
        "slo": "must fail closed and preserve FTS baseline availability",
        "benchmark": "benchmarks/power31 reranking quality comparison",
        "threat_model": "docs/threat-model.md",
        "expiry": "review at every release",
        "kill_criterion": "no quality/resource improvement over the FTS baseline",
    },
    "gpu": {
        "description": "explicit provider runtime profile",
        "status": "optional",
        "named_consumer": "explicit GPU provider probe",
        "owner": "runtime-maintainers",
        "slo": "actual provider must be reported; silent CPU fallback is forbidden",
        "benchmark": "provider and resource receipt in the release benchmark",
        "threat_model": "docs/threat-model.md",
        "expiry": "review at every release",
        "kill_criterion": "provider identity or resource boundary is unverifiable",
    },
}


def _git(*args: str) -> str:
    result = subprocess.run(  # noqa: S603 -- fixed read-only repository query.
        ["git", "-C", str(REPO_ROOT), *args],  # noqa: S607 -- fixed executable name.
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def build_inventory() -> dict[str, Any]:
    """Return a deterministic interface and compatibility snapshot."""
    runtime = manifest()
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    extras = project.get("optional-dependencies", {})
    return {
        "schema_version": "power.surface-inventory.v1",
        "release": str(project["version"]),
        "source": {
            "commit": _git("rev-parse", "HEAD"),
            "tree": _git("show", "-s", "--format=%T", "HEAD"),
            "worktree_dirty": bool(_git("status", "--porcelain")),
        },
        "interfaces": {
            "cli_commands": runtime["interfaces"]["cli_commands"],
            "mcp_tools": runtime["interfaces"]["mcp_tools"],
        },
        "core_capabilities": CORE_CAPABILITIES,
        "optional_tracks": {
            name: {
                **metadata,
                "extra_declared": name in extras,
                "base_dependency": False,
            }
            for name, metadata in OPTIONAL_TRACKS.items()
        },
        "legacy_commands": LEGACY_COMMANDS,
        "deprecation_policy": "consumer inventory + replacement + compatibility window",
        "kill_policy": "missing consumer/owner/evidence/threat-model/expiry stays out of core",
    }


def main() -> int:
    """Write the inventory JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(build_inventory(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Surface inventory written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
