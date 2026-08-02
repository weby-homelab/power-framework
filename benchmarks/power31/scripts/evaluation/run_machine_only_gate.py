"""Run the bounded machine-only technical gate for POWER M2 through M5.

The gate is intentionally separate from the human-evidence protocol.  It uses
only committed synthetic benchmark data, a temporary vault, and the checked-in
release contract.  It cannot certify human retrieval quality, product demand,
or production envelopes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover - Windows does not expose resource
    resource = None  # type: ignore[assignment]

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_m2_auto import run as run_m2_auto  # noqa: E402
from run_release_evaluation import (  # noqa: E402
    DATASET_V1,
    MANIFEST_FILE,
    QRELS_FILE,
    QUERIES_FILE,
    REPO_ROOT,
    _db_path_for_vault,
    _get_git_info,
    _search_and_collect,
    _sync_vault,
    materialise_vault,
)
from verify_m2_auto import verify as verify_m2_auto  # noqa: E402

CONTRACT_DEFAULT = DATASET_V1.parent.parent / "configs" / "m2-m5-machine-only-contract.v1.json"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * percentile / 100)))
    return round(ordered[index], 3)


def _peak_rss_mb() -> float | None:
    if resource is None:
        return None
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return round(value / (1024 * 1024), 1)
    return round(value / 1024, 1)


def _validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != "power.machine-only-m2-m5/v1":
        raise ValueError("unsupported machine-only M2-M5 contract")
    if contract.get("scope") != "machine_only_technical":
        raise ValueError("scope must be machine_only_technical")
    if contract.get("human_evidence_used") is not False:
        raise ValueError("machine-only gate forbids human evidence")
    if contract.get("sealed_accessed") is not False:
        raise ValueError("machine-only gate forbids sealed access")

    m3 = contract.get("m3")
    if not isinstance(m3, dict) or m3.get("modes") != ["fts", "hybrid"]:
        raise ValueError("M3 must use the bounded fts/hybrid modes")
    for key in ("max_runtime_seconds", "max_query_p95_ms", "max_peak_rss_mb", "max_index_bytes"):
        if float(m3.get(key, 0)) <= 0:
            raise ValueError(f"M3 {key} must be positive")

    m4 = contract.get("m4")
    if not isinstance(m4, dict) or m4.get("scenario") != "transactional-memory-v1":
        raise ValueError("unsupported M4 machine-only scenario")
    if int(m4.get("required_history_entries", 0)) < 2:
        raise ValueError("M4 must verify at least two history entries")

    m5 = contract.get("m5")
    if not isinstance(m5, dict):
        raise ValueError("missing M5 contract")
    for key in ("require_clean_tree", "require_release_contract", "require_tag"):
        if m5.get(key) is not True:
            raise ValueError(f"M5 requires {key}=true")
    if m5.get("technical_release") is not True:
        raise ValueError("M5 must be a technical release gate")
    if m5.get("human_quality_certification") is not False:
        raise ValueError("M5 human-quality certification must remain false")
    if m5.get("production_quality_claim") is not False:
        raise ValueError("M5 production-quality claim must remain false")
    if m5.get("sealed_holdout") != "do_not_open":
        raise ValueError("M5 sealed holdout must remain closed")


def _run_m2(contract_path: Path, timestamp: str) -> dict[str, Any]:
    evidence = run_m2_auto(contract_path.parent / "m2-auto-contract.v1.json", None, timestamp)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as file:
        evidence_path = Path(file.name)
        json.dump(evidence, file, indent=2, ensure_ascii=False)
        file.write("\n")
    try:
        errors = verify_m2_auto(evidence_path)
    finally:
        evidence_path.unlink(missing_ok=True)
    return {
        "quality_gate": evidence.get("quality_gate"),
        "verifier_errors": errors,
        "human_evidence_used": evidence.get("human_evidence_used"),
        "sealed_accessed": evidence.get("sealed_accessed"),
        "source": evidence.get("source"),
        "dataset": evidence.get("dataset"),
        "metrics": evidence.get("metrics"),
        "runtime_seconds": evidence.get("runtime_seconds"),
        "runtime_budget_seconds": evidence.get("runtime_budget_seconds"),
        "failures": evidence.get("failures"),
    }


def _run_m3(contract: dict[str, Any]) -> dict[str, Any]:
    queries = _load_jsonl(QUERIES_FILE)
    vault_dir = Path(tempfile.mkdtemp(prefix="power-m3-machine-only-"))
    materialise_vault(vault_dir)
    started = time.monotonic()
    _sync_vault(vault_dir, sync_embeddings=False, force_rebuild=True)

    latency: dict[str, list[float]] = {mode: [] for mode in contract["m3"]["modes"]}
    for query in queries:
        for mode in latency:
            query_started = time.monotonic()
            _search_and_collect(vault_dir, query["query"], mode, top_k=10)
            latency[mode].append((time.monotonic() - query_started) * 1000)

    runtime_seconds = round(time.monotonic() - started, 3)
    db_path = _db_path_for_vault(vault_dir)
    index_bytes = db_path.stat().st_size
    peak_rss_mb = _peak_rss_mb()
    max_p95_ms = max(_percentile(values, 95) for values in latency.values())
    limits = contract["m3"]
    failures: list[str] = []
    if runtime_seconds > float(limits["max_runtime_seconds"]):
        failures.append("runtime_seconds exceeds max_runtime_seconds")
    if max_p95_ms > float(limits["max_query_p95_ms"]):
        failures.append("query p95 exceeds max_query_p95_ms")
    if peak_rss_mb is None or peak_rss_mb > float(limits["max_peak_rss_mb"]):
        failures.append("peak RSS is unavailable or exceeds max_peak_rss_mb")
    if index_bytes > int(limits["max_index_bytes"]):
        failures.append("index exceeds max_index_bytes")

    return {
        "scenario": "synthetic-power31-v1",
        "dataset": {
            "manifest_sha256": _sha256_file(MANIFEST_FILE),
            "queries_sha256": _sha256_file(QUERIES_FILE),
            "qrels_sha256": _sha256_file(QRELS_FILE),
            "query_count": len(queries),
        },
        "latency": {
            mode: {
                "p50_ms": _percentile(values, 50),
                "p95_ms": _percentile(values, 95),
            }
            for mode, values in latency.items()
        },
        "max_query_p95_ms": max_p95_ms,
        "runtime_seconds": runtime_seconds,
        "peak_rss_mb": peak_rss_mb,
        "index_bytes": index_bytes,
        "limits": {
            "max_runtime_seconds": limits["max_runtime_seconds"],
            "max_query_p95_ms": limits["max_query_p95_ms"],
            "max_peak_rss_mb": limits["max_peak_rss_mb"],
            "max_index_bytes": limits["max_index_bytes"],
        },
        "failures": failures,
        "quality_gate": "PASS" if not failures else "FAIL",
    }


def _transaction_note(title: str, body: str) -> str:
    return (
        "---\n"
        "type: Project\n"
        f'title: "{title}"\n'
        'description: "Machine-only transactional memory scenario"\n'
        "timestamp: 2026-08-03T00:00:00Z\n"
        "---\n\n"
        f"# {title}\n\n{body}\n"
    )


def _run_m4(contract: dict[str, Any]) -> dict[str, Any]:
    from power_framework.core.memory_api import (
        apply_change,
        propose_change,
        read_history,
        validate_state,
    )

    vault_dir = Path(tempfile.mkdtemp(prefix="power-m4-machine-only-"))
    (vault_dir / "01_Projects").mkdir()
    (vault_dir / "02_Areas").mkdir()
    (vault_dir / "01_Projects" / "Transaction.md").write_text(
        _transaction_note("Transaction", "Related context: [[Context]]."), encoding="utf-8"
    )
    (vault_dir / "02_Areas" / "Context.md").write_text(
        _transaction_note("Context", "Related transaction: [[Transaction]]."), encoding="utf-8"
    )

    first = propose_change(
        vault_dir,
        "01_Projects/Transaction.md",
        _transaction_note("Transaction", "First machine-approved update. Related: [[Context]]."),
    )
    approval_required = False
    try:
        apply_change(vault_dir, first, approved=False)
    except PermissionError:
        approval_required = True
    receipt_one = apply_change(vault_dir, first, approved=True)

    stale = propose_change(
        vault_dir,
        "01_Projects/Transaction.md",
        _transaction_note("Transaction", "Stale proposal. Related: [[Context]]."),
    )
    fresh = propose_change(
        vault_dir,
        "01_Projects/Transaction.md",
        _transaction_note("Transaction", "Fresh machine-approved update. Related: [[Context]]."),
    )
    receipt_two = apply_change(vault_dir, fresh, approved=True)
    stale_rejected = False
    try:
        apply_change(vault_dir, stale, approved=True)
    except RuntimeError:
        stale_rejected = True

    history = read_history(vault_dir)
    validated = validate_state(vault_dir)
    failures: list[str] = []
    if not approval_required:
        failures.append("unapproved proposal was accepted")
    if not stale_rejected:
        failures.append("stale proposal was accepted")
    if not validated and contract["m4"]["requires_validated_state"]:
        failures.append("transactional vault did not validate")
    if len(history) < int(contract["m4"]["required_history_entries"]):
        failures.append("transaction history is incomplete")

    return {
        "scenario": contract["m4"]["scenario"],
        "approval_boundary_enforced": approval_required,
        "stale_proposal_rejected": stale_rejected,
        "validated_state": validated,
        "history_entries": len(history),
        "receipt_paths": [receipt_one["path"], receipt_two["path"]],
        "failures": failures,
        "quality_gate": "PASS" if not failures else "FAIL",
    }


def _run_m5(contract: dict[str, Any]) -> dict[str, Any]:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise OSError("git executable is unavailable")
    diff_check = subprocess.run(  # noqa: S603
        [git_executable, "diff", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    status = subprocess.run(  # noqa: S603
        [git_executable, "status", "--porcelain"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    release = subprocess.run(
        [sys.executable, "scripts/verify_release_contract.py", "--require-tag"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    clean_tree = not status.stdout.strip()
    failures: list[str] = []
    if diff_check.returncode != 0:
        failures.append("git diff --check failed")
    if contract["m5"]["require_clean_tree"] and not clean_tree:
        failures.append("source tree is dirty")
    if contract["m5"]["require_release_contract"] and release.returncode != 0:
        failures.append("release contract failed")
    return {
        "clean_tree": clean_tree,
        "diff_check": "PASS" if diff_check.returncode == 0 else "FAIL",
        "release_contract": "PASS" if release.returncode == 0 else "FAIL",
        "release_returncode": release.returncode,
        "release_stdout": release.stdout.strip(),
        "release_stderr": release.stderr.strip(),
        "technical_release": contract["m5"]["technical_release"],
        "human_quality_certification": contract["m5"]["human_quality_certification"],
        "production_quality_claim": contract["m5"]["production_quality_claim"],
        "sealed_holdout": contract["m5"]["sealed_holdout"],
        "failures": failures,
        "quality_gate": "PASS" if not failures else "FAIL",
    }


def run(contract_path: Path, timestamp: str | None = None) -> dict[str, Any]:
    contract = _load_json(contract_path)
    _validate_contract(contract)
    cache_root = Path(tempfile.mkdtemp(prefix="power-machine-only-cache-"))
    previous_cache = os.environ.get("XDG_CACHE_HOME")
    os.environ["XDG_CACHE_HOME"] = str(cache_root)
    timestamp_value = timestamp or datetime.now(UTC).isoformat()
    try:
        m2 = _run_m2(contract_path, timestamp_value)
        m3 = _run_m3(contract)
        m4 = _run_m4(contract)
        m5 = _run_m5(contract)
    finally:
        if previous_cache is None:
            os.environ.pop("XDG_CACHE_HOME", None)
        else:
            os.environ["XDG_CACHE_HOME"] = previous_cache

    commit, dirty = _get_git_info()
    failures = [
        "machine-only milestone failed"
        for milestone in (m2, m3, m4, m5)
        if milestone.get("quality_gate") != "PASS"
    ]
    if dirty:
        failures.append("source tree became dirty")
    return {
        "schema_version": "power.machine-only-m2-m5-evidence/v1",
        "contract_sha256": _sha256_file(contract_path),
        "scope": contract["scope"],
        "human_evidence_used": False,
        "sealed_accessed": False,
        "source": {"commit": commit, "dirty_tree": dirty},
        "timestamp": timestamp_value,
        "m2": m2,
        "m3": m3,
        "m4": m4,
        "m5": m5,
        "failures": failures,
        "quality_gate": "PASS" if not failures else "FAIL",
        "limitations": [
            "Synthetic benchmark only; no private or sealed evaluation was opened",
            "Machine-only technical evidence is not human-quality certification",
            "No production latency, product adoption, or design-partner claim",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the machine-only POWER M2-M5 technical gate")
    parser.add_argument("--contract", type=Path, default=CONTRACT_DEFAULT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timestamp", default=None)
    args = parser.parse_args(argv)
    try:
        evidence = run(args.contract, args.timestamp)
    except (OSError, ValueError, subprocess.SubprocessError, TimeoutError) as exc:
        print(f"machine-only M2-M5 gate failed: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"machine-only M2-M5 {evidence['quality_gate']}")
    return 0 if evidence["quality_gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
