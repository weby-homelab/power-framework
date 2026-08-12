#!/usr/bin/env python3
"""Validate the external Phase 8 evidence required for a stable release.

The repository can run synthetic technical benchmarks, but it must not promote
those receipts to real-vault or human-quality evidence.  This verifier accepts
only content-free, hash-bound receipts prepared outside the public checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from power_framework.phase8_contract import (
    CONTINUITY_INDEPENDENT_PROCESSES,
    HUMAN_EVIDENCE_THRESHOLD_PROFILE,
    PHASE8_CONTINUITY_SCHEMA_VERSION,
    PHASE8_OUTCOME_SCHEMA_VERSION,
    PLAIN_HANDOFF_PROCESSES,
    REAL_VAULT_COMPARATORS,
    REAL_VAULT_EXPERIMENTS,
    REAL_VAULT_METRICS,
    SYNTHETIC_WORKFLOW_COUNT,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
HUMAN_VALIDATOR = (
    REPO_ROOT / "benchmarks" / "human_retrieval" / "scripts" / "validate_human_evidence.py"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _object(value: object, label: str, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return None
    return value


def _sha256(value: object) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _canonical_file_sha256(path: Path) -> str:
    """Hash JSON evidence independently of checkout line-ending policy."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _candidate_manifest_hashes(
    path: Path, manifest_obj: dict[str, Any] | None = None
) -> set[str]:
    """Return all canonical/formatted SHA-256 representations of a human evidence manifest."""
    hashes = {_canonical_file_sha256(path)}
    if manifest_obj is None:
        try:
            manifest_obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return hashes
    if isinstance(manifest_obj, dict):
        for indent in (2, 4, None):
            for sort in (False, True):
                for trailing in (b"\n", b""):
                    if indent is None:
                        encoded = json.dumps(
                            manifest_obj,
                            ensure_ascii=False,
                            sort_keys=sort,
                            separators=(",", ":"),
                        ).encode("utf-8") + trailing
                    else:
                        encoded = json.dumps(
                            manifest_obj, ensure_ascii=False, sort_keys=sort, indent=indent
                        ).encode("utf-8") + trailing
                    hashes.add(hashlib.sha256(encoded).hexdigest())
    return hashes


def _finite_number(
    value: object, label: str, errors: list[str], *, maximum: float | None = None
) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        errors.append(f"{label} must be a finite number")
    elif maximum is not None and not 0 <= float(value) <= maximum:
        errors.append(f"{label} must be between 0 and {maximum}")


def _nonnegative_integer(value: object, label: str, errors: list[str]) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        errors.append(f"{label} must be a non-negative integer")


def validate_real_vault_receipt(receipt: dict[str, Any], *, release: str) -> list[str]:
    """Return violations for the content-free real-vault Phase 8 receipt."""
    errors: list[str] = []
    if receipt.get("schema_version") != "power.phase8.real-vault-receipt.v1":
        errors.append("real-vault receipt has an unsupported schema")
    if receipt.get("release") != release:
        errors.append(f"real-vault receipt release must be {release}")
    if receipt.get("status") != "passed":
        errors.append("real-vault receipt status must be passed")
    if receipt.get("content_free") is not True or receipt.get("raw_content_present") is not False:
        errors.append("real-vault receipt must explicitly be content-free")

    source = _object(receipt.get("source"), "real-vault source", errors)
    if source is not None:
        if not isinstance(source.get("revision"), str) or not GIT_COMMIT_RE.fullmatch(
            source["revision"]
        ):
            errors.append("real-vault source.revision must be a Git commit")
        if source.get("clean") is not True:
            errors.append("real-vault source.clean must be true")

    vault = _object(receipt.get("vault"), "real-vault vault", errors)
    if vault is not None:
        if not isinstance(vault.get("opaque_id"), str) or len(vault["opaque_id"]) < 8:
            errors.append("real-vault vault.opaque_id must be an opaque identifier")
        if not _sha256(vault.get("snapshot_sha256")):
            errors.append("real-vault vault.snapshot_sha256 must be a SHA-256")
        _nonnegative_integer(vault.get("note_count"), "real-vault vault.note_count", errors)

    runtime = _object(receipt.get("runtime"), "real-vault runtime", errors)
    if runtime is not None:
        errors.extend(
            f"real-vault runtime.{field} must be non-empty"
            for field in ("executable", "provider", "generation")
            if not isinstance(runtime.get(field), str) or not runtime[field]
        )
        if not _sha256(runtime.get("config_sha256")):
            errors.append("real-vault runtime.config_sha256 must be a SHA-256")

    experiments = receipt.get("experiments")
    if not isinstance(experiments, list):
        errors.append("real-vault experiments must be a list")
    else:
        by_id: dict[str, dict[str, Any]] = {}
        for experiment in experiments:
            if not isinstance(experiment, dict) or not isinstance(experiment.get("id"), str):
                errors.append("each real-vault experiment must have an id")
                continue
            experiment_id = experiment["id"]
            if experiment_id in by_id:
                errors.append(f"duplicate real-vault experiment: {experiment_id}")
            by_id[experiment_id] = experiment
            if experiment.get("status") != "passed":
                errors.append(f"real-vault experiment {experiment_id} must be passed")
            if not _sha256(experiment.get("receipt_sha256")):
                errors.append(f"real-vault experiment {experiment_id} receipt must be a SHA-256")
        if set(by_id) != REAL_VAULT_EXPERIMENTS:
            errors.append("real-vault experiments must cover build, transfer, import and query")
        transfer = by_id.get("transfer")
        if transfer is not None:
            transfer_bytes = _object(transfer.get("bytes"), "transfer bytes", errors)
            if transfer_bytes is not None:
                for field in ("full", "wire", "delta"):
                    _nonnegative_integer(
                        transfer_bytes.get(field), f"transfer bytes.{field}", errors
                    )
                if (
                    not isinstance(transfer_bytes.get("compression"), str)
                    or not transfer_bytes["compression"]
                ):
                    errors.append("transfer bytes.compression must be non-empty")

    quality = _object(receipt.get("quality"), "real-vault quality", errors)
    if quality is not None:
        errors.extend(
            f"real-vault quality.{field} must be true"
            for field in ("sealed_dataset", "real_vault", "blind_scoring", "no_answer_scoring")
            if quality.get(field) is not True
        )
        if quality.get("outcome_gate") != "pass":
            errors.append("real-vault quality.outcome_gate must be pass")
        if quality.get("power_beats_no_power") is not True:
            errors.append("real-vault quality.power_beats_no_power must be true")
        comparators = quality.get("comparators")
        if (
            not isinstance(comparators, list)
            or not all(isinstance(comparator, str) for comparator in comparators)
            or not set(comparators) >= REAL_VAULT_COMPARATORS
        ):
            errors.append("real-vault quality must cover FTS, auto, semantic and no_power")
        metrics = _object(quality.get("metrics"), "real-vault quality.metrics", errors)
        if metrics is not None:
            if set(metrics) != REAL_VAULT_METRICS:
                errors.append("real-vault quality.metrics must contain the preregistered metrics")
            for metric in REAL_VAULT_METRICS - {"latency_p95_ms"}:
                _finite_number(
                    metrics.get(metric), f"real-vault quality.metrics.{metric}", errors, maximum=1
                )
            _finite_number(
                metrics.get("latency_p95_ms"), "real-vault quality.metrics.latency_p95_ms", errors
            )
        completion = quality.get("fresh_agent_completion_percent")
        _finite_number(
            completion,
            "real-vault quality.fresh_agent_completion_percent",
            errors,
            maximum=100,
        )
        if (
            isinstance(completion, (int, float))
            and not isinstance(completion, bool)
            and completion < 90
        ):
            errors.append("fresh-agent completion must be at least 90 percent")
        _finite_number(
            quality.get("safety_invariants_percent"),
            "real-vault quality.safety_invariants_percent",
            errors,
        )
        if quality.get("safety_invariants_percent") != 100:
            errors.append("safety invariants must be 100 percent")
        if quality.get("median_human_reminders") != 0:
            errors.append("median human reminders must be zero")

    human = _object(receipt.get("human_evidence"), "human evidence", errors)
    if human is not None:
        if human.get("status") != "passed" or human.get("sealed_holdout") is not True:
            errors.append("human evidence must be a passed sealed-holdout result")
        if not _sha256(human.get("manifest_sha256")):
            errors.append("human evidence manifest_sha256 must be a SHA-256")
    return errors


def validate_technical_receipts(*, outcome_path: Path, continuity_path: Path) -> list[str]:
    """Validate public synthetic Phase 8 receipts without promoting them."""
    errors: list[str] = []
    outcome = _load_json(outcome_path)
    continuity = _load_json(continuity_path)
    if outcome is None:
        errors.append(f"outcome receipt is missing or invalid JSON: {outcome_path}")
    else:
        if outcome.get("schema_version") != PHASE8_OUTCOME_SCHEMA_VERSION:
            errors.append("outcome receipt has an unsupported schema")
        if outcome.get("synthetic") is not True or outcome.get("content_free") is not True:
            errors.append("outcome receipt must be synthetic and content-free")
        if outcome.get("workflow_count") != SYNTHETIC_WORKFLOW_COUNT:
            errors.append(f"outcome receipt must cover {SYNTHETIC_WORKFLOW_COUNT} workflows")
        gate = _object(outcome.get("gate"), "outcome gate", errors)
        if gate is not None:
            completion = gate.get("fresh_agent_completion")
            if (
                not isinstance(completion, (int, float))
                or isinstance(completion, bool)
                or completion < 0.9
            ):
                errors.append("outcome fresh-agent completion must be at least 0.9")
            errors.extend(
                f"outcome gate.{field} must be true"
                for field in (
                    "safety_invariants_100",
                    "false_premise_abstention",
                    "stale_state_filter",
                    "technical_continuity_20",
                    "blocked_workflow_abstention",
                )
                if gate.get(field) is not True
            )
            if gate.get("median_human_reminders") != 0:
                errors.append("outcome gate.median_human_reminders must be zero")
        comparison = _object(outcome.get("comparison"), "outcome comparison", errors)
        if comparison is not None:
            if comparison.get("practical_improvement") is not True:
                errors.append("outcome comparison must show practical improvement over no_power")
            for label in ("power_mean_score", "no_power_mean_score"):
                _finite_number(
                    comparison.get(label), f"outcome comparison.{label}", errors, maximum=1
                )
            evidence_recall = _object(
                comparison.get("evidence_recall"), "outcome evidence recall", errors
            )
            if evidence_recall is not None:
                for label in ("power", "no_power"):
                    _finite_number(
                        evidence_recall.get(label),
                        f"outcome evidence_recall.{label}",
                        errors,
                        maximum=1,
                    )
        profiles = _object(outcome.get("retrieval_profiles"), "outcome retrieval profiles", errors)
        if profiles is not None:
            for profile in ("fts", "auto", "semantic"):
                profile_data = _object(profiles.get(profile), f"outcome {profile} profile", errors)
                if profile_data is not None and profile_data.get("status") not in {
                    "executed",
                    "not_evaluated",
                }:
                    errors.append(f"outcome {profile} profile has an invalid status")
            semantic = profiles.get("semantic")
            if (
                isinstance(semantic, dict)
                and semantic.get("status") == "not_evaluated"
                and (not isinstance(semantic.get("reason"), str) or not semantic["reason"])
            ):
                errors.append("outcome semantic profile must explain non-evaluation")
        if outcome.get("blind_scoring") is not False:
            errors.append("outcome synthetic receipt must not claim blind scoring")
        feedback_reuse = _object(outcome.get("feedback_reuse"), "outcome feedback reuse", errors)
        if feedback_reuse is not None and feedback_reuse.get("measured") is not False:
            errors.append("outcome synthetic receipt must not claim feedback reuse")
        bootstrap = _object(
            outcome.get("bootstrap_context_tokens"), "outcome bootstrap/context tokens", errors
        )
        if bootstrap is not None and bootstrap.get("measured") is not False:
            errors.append("outcome synthetic receipt must not claim measured context tokens")
        if outcome.get("raw_content_in_report") is not False:
            errors.append("outcome receipt must be content-free")
        if outcome.get("human_quality_certification") is not False:
            errors.append("outcome receipt must not claim human-quality certification")
        if outcome.get("real_vault") is not False:
            errors.append("outcome receipt must not claim real-vault evidence")
        if outcome.get("sealed_holdout") != "not_opened":
            errors.append("outcome receipt must not open the sealed holdout")

    if continuity is None:
        errors.append(f"continuity receipt is missing or invalid JSON: {continuity_path}")
    else:
        if continuity.get("schema_version") != PHASE8_CONTINUITY_SCHEMA_VERSION:
            errors.append("continuity receipt has an unsupported schema")
        if continuity.get("synthetic") is not True or continuity.get("content_free") is not True:
            errors.append("continuity receipt must be synthetic and content-free")
        if continuity.get("workflow_count") != SYNTHETIC_WORKFLOW_COUNT:
            errors.append(f"continuity receipt must cover {SYNTHETIC_WORKFLOW_COUNT} workflows")
        if continuity.get("independent_processes") != CONTINUITY_INDEPENDENT_PROCESSES:
            errors.append(
                "continuity receipt must cover "
                f"{CONTINUITY_INDEPENDENT_PROCESSES} independent processes"
            )
        if continuity.get("plain_handoff_processes") != PLAIN_HANDOFF_PROCESSES:
            errors.append(
                f"continuity receipt must measure {PLAIN_HANDOFF_PROCESSES} plain-handoff processes"
            )
        gate = _object(continuity.get("gate"), "continuity gate", errors)
        if gate is not None:
            errors.extend(
                f"continuity gate.{field} must be true"
                for field in (
                    "correct_resume_20",
                    "proof_carrying_handoff",
                    "source_preserved",
                    "unsafe_actions_100_percent_safe",
                    "human_reminders_median_zero",
                    "power_beats_plain_handoff",
                )
                if gate.get(field) is not True
            )
        comparison = _object(continuity.get("comparison"), "continuity comparison", errors)
        if comparison is not None:
            if comparison.get("practical_improvement") is not True:
                errors.append("continuity comparison must show improvement over plain handoff")
            power_rate = comparison.get("power_continuity_rate")
            plain_rate = comparison.get("plain_handoff_continuity_rate")
            _finite_number(
                power_rate, "continuity comparison.power_continuity_rate", errors, maximum=1
            )
            _finite_number(
                plain_rate,
                "continuity comparison.plain_handoff_continuity_rate",
                errors,
                maximum=1,
            )
            if (
                isinstance(power_rate, (int, float))
                and not isinstance(power_rate, bool)
                and isinstance(plain_rate, (int, float))
                and not isinstance(plain_rate, bool)
                and power_rate <= plain_rate
            ):
                errors.append("continuity must beat the plain handoff baseline")
        metrics = _object(continuity.get("metrics"), "continuity metrics", errors)
        if metrics is not None:
            _finite_number(
                metrics.get("duplicate_work_rate"),
                "continuity metrics.duplicate_work_rate",
                errors,
                maximum=1,
            )
            if metrics.get("duplicate_work_rate") != 0:
                errors.append("continuity duplicate_work_rate must be zero")
        if continuity.get("raw_content_in_report") is not False:
            errors.append("continuity receipt must be content-free")
        if continuity.get("human_quality_certification") is not False:
            errors.append("continuity receipt must not claim human-quality certification")
        if continuity.get("real_vault") is not False:
            errors.append("continuity receipt must not claim real-vault evidence")
        if continuity.get("sealed_holdout") != "not_opened":
            errors.append("continuity receipt must not open the sealed holdout")
    return errors


def _load_human_validator() -> Any:
    spec = importlib.util.spec_from_file_location("power_m2_human_evidence", HUMAN_VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the M2 human evidence validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_phase8_evidence(
    *, real_vault_receipt_path: Path, human_manifest_path: Path, release: str
) -> list[str]:
    """Validate both receipts and their cross-binding without printing content."""
    errors: list[str] = []
    real_receipt = _load_json(real_vault_receipt_path)
    if real_receipt is None:
        errors.append(f"real-vault receipt is missing or invalid JSON: {real_vault_receipt_path}")
    else:
        errors.extend(validate_real_vault_receipt(real_receipt, release=release))

    human_manifest = _load_json(human_manifest_path)
    if human_manifest is None:
        errors.append(f"human manifest is missing or invalid JSON: {human_manifest_path}")
    else:
        validator = _load_human_validator()
        errors.extend(validator.validate_evidence_file(human_manifest_path, allow_sealed=True))
        if human_manifest.get("status") != "adjudicated":
            errors.append("human manifest status must be adjudicated")
        if human_manifest.get("split") != "sealed_holdout":
            errors.append("human manifest split must be sealed_holdout")
        if human_manifest.get("threshold_profile") != HUMAN_EVIDENCE_THRESHOLD_PROFILE:
            errors.append(
                f"human manifest must use the {HUMAN_EVIDENCE_THRESHOLD_PROFILE} threshold profile"
            )

    if real_receipt is not None and human_manifest is not None:
        human_evidence = real_receipt.get("human_evidence")
        expected_hash = (
            human_evidence.get("manifest_sha256") if isinstance(human_evidence, dict) else None
        )
        if expected_hash not in _candidate_manifest_hashes(human_manifest_path, human_manifest):
            errors.append("real-vault receipt human manifest hash does not match the manifest")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    parser.add_argument("--real-vault-receipt", type=Path, required=True)
    parser.add_argument("--human-manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        errors = validate_phase8_evidence(
            real_vault_receipt_path=args.real_vault_receipt,
            human_manifest_path=args.human_manifest,
            release=args.release,
        )
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        print(f"Phase 8 evidence validation failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("Phase 8 evidence validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("Phase 8 real-vault and sealed human evidence are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
