"""R6A.2 query-only execution, raw-output, and one-shot epoch contracts.

This module is deliberately retrieval-agnostic.  It owns the boundary between
verified query input and observed output persistence, but it never imports the
retrieval runtime and never accepts ground truth in the execution DTOs.
"""

from __future__ import annotations

import errno
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Callable

from pydantic import Field, StrictInt, ValidationError, model_validator

from .context_contracts import (
    AwareDateTime,
    Digest,
    OpaqueReference,
    RuntimeModel,
    ShortText,
    SourceReference,
)
from .evaluation_contracts import (
    EvaluationIntegrityError,
    EvaluationVerificationSnapshot,
    SealedRevisionSpec,
    load_bounded_json,
    validate_sealed_revision_spec,
    verify_evaluation_corpus,
)

MAX_RAW_OUTPUT_BYTES = 4 * 1024 * 1024
EPOCH_GUARD_FILENAME = "one-shot-epoch.json"
EPOCH_REGISTRY_DIRNAME = ".power-evaluation-epochs"
RAW_OUTPUT_FILENAME = "raw-retrieval-output.json"
FRESH_HOLDOUT_ONE_SHOT_INTENT = "fresh_holdout_one_shot"
_RAW_FORBIDDEN_MARKERS = (
    "github_release_token=",
    "aws_secret_access_key",
    "-----begin private key-----",
    "ghp_",
    "sk-or-",
    "sk-",
)


class QueryOnlyRecord(RuntimeModel):
    """The only query-side input exposed to a fresh holdout executor."""

    query_id: OpaqueReference
    query: ShortText = Field(max_length=2048)
    intent: OpaqueReference | None = None
    budget_class: Literal["FAST", "BALANCED", "DEEP"] = "FAST"


class ObservedCandidate(RuntimeModel):
    """Bounded candidate metadata observed from retrieval, without content."""

    source_id: OpaqueReference
    rank: Annotated[int, Field(ge=1, le=4096)]
    authority: OpaqueReference = "unknown"
    source_type: OpaqueReference = "unknown"
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_content_fields(self) -> ObservedCandidate:
        forbidden = {"content", "excerpt", "ground_truth", "query", "reason", "text"}

        def contains_forbidden(value: Any) -> bool:
            if isinstance(value, dict):
                return any(
                    str(key).casefold() in forbidden or contains_forbidden(item)
                    for key, item in value.items()
                )
            if isinstance(value, list):
                return any(contains_forbidden(item) for item in value)
            if isinstance(value, str):
                lowered = value.casefold()
                return any(marker in lowered for marker in _RAW_FORBIDDEN_MARKERS)
            return False

        if contains_forbidden(self.provenance):
            raise ValueError("raw candidate provenance must not contain content or ground truth")
        return self


class RawRetrievalOutputRecord(RuntimeModel):
    """One immutable observation produced by query-only execution."""

    query_id: OpaqueReference
    legacy_candidate_ids: list[OpaqueReference] = Field(max_length=4096)
    shadow_candidate_ids: list[OpaqueReference] = Field(max_length=4096)
    shadow_candidates: list[ObservedCandidate] = Field(max_length=4096)
    latency_ms: float = Field(ge=0)
    token_cost: StrictInt = Field(ge=0)
    pack_bytes: StrictInt = Field(ge=0)
    security_observations: dict[str, int | bool | str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_observation_bounds(self) -> RawRetrievalOutputRecord:
        encoded = json.dumps(self.security_observations, ensure_ascii=False, sort_keys=True)
        if len(encoded.encode("utf-8")) > 64 * 1024:
            raise ValueError("raw security observations exceed the byte bound")
        lowered = encoded.casefold()
        if any(marker in lowered for marker in _RAW_FORBIDDEN_MARKERS):
            raise ValueError("raw security observations contain a forbidden marker")
        return self


class RawRetrievalOutputArtifact(RuntimeModel):
    """Content-addressed output that can be scored after execution is frozen."""

    schema_version: Literal["power.retrieval-raw-output.v1"]
    evaluation_revision: Annotated[str, Field(pattern=r"^v1(?:\.[0-9]+)?$")]
    revision_spec_digest: Digest
    query_set_digest: Digest
    source_corpus_digest: Digest
    runtime_digest: Digest
    execution_runner_digest: Digest
    fixture_digest: Digest
    records: list[RawRetrievalOutputRecord] = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def validate_record_ids(self) -> RawRetrievalOutputArtifact:
        query_ids = [record.query_id for record in self.records]
        if len(query_ids) != len(set(query_ids)):
            raise ValueError("raw retrieval output query IDs must be unique")
        return self


class EpochBinding(RuntimeModel):
    """Immutable identity tuple copied into a one-shot epoch receipt."""

    evaluation_revision: Annotated[str, Field(pattern=r"^v1(?:\.[0-9]+)?$")]
    revision_spec_digest: Digest
    dataset_digest: Digest
    query_set_digest: Digest
    holdout_digest: Digest
    source_corpus_digest: Digest
    r6a2_freeze_digest: Digest
    r6a2_freeze_ref: SourceReference
    runtime_digest: Digest
    execution_runner_digest: Digest
    fixture_digest: Digest
    ownership_contract_digest: Digest
    fast_capability_contract_digest: Digest
    metric_contract_digest: Digest

    def assert_matches_descriptor(self, descriptor: HoldoutExecutionDescriptor) -> None:
        """Reject a binding that is not the verified corpus identity."""

        checks = (
            (self.evaluation_revision, descriptor.evaluation_revision, "revision"),
            (self.revision_spec_digest, descriptor.revision_spec_digest, "revision spec"),
            (self.dataset_digest, descriptor.dataset_digest, "dataset"),
            (self.query_set_digest, descriptor.query_set_digest, "query set"),
            (self.holdout_digest, descriptor.holdout_digest, "holdout"),
            (self.source_corpus_digest, descriptor.source_corpus_digest, "source corpus"),
        )
        for actual, expected, label in checks:
            if actual != expected:
                raise EvaluationIntegrityError(
                    "epoch_binding", f"epoch {label} binding does not match verified descriptor"
                )


class OneShotEvaluationEpochReceipt(RuntimeModel):
    """Distinct one-shot execution receipt; not an integrity-read receipt."""

    schema_version: Literal["power.retrieval-one-shot-epoch.v1"]
    evaluation_revision: Annotated[str, Field(pattern=r"^v1(?:\.[0-9]+)?$")]
    revision_spec_digest: Digest
    dataset_digest: Digest
    query_set_digest: Digest
    holdout_digest: Digest
    source_corpus_digest: Digest
    r6a2_freeze_digest: Digest
    r6a2_freeze_ref: SourceReference
    runtime_digest: Digest
    execution_runner_digest: Digest
    fixture_digest: Digest
    ownership_contract_digest: Digest
    fast_capability_contract_digest: Digest
    metric_contract_digest: Digest
    started_at: AwareDateTime
    status: Literal["STARTED", "COMPLETED_PASS", "COMPLETED_FAIL", "INTERRUPTED"]
    raw_output_digest: Digest | None = None
    raw_output_ref: OpaqueReference | None = None
    completed_at: AwareDateTime | None = None

    @classmethod
    def start(cls, *, binding: EpochBinding) -> OneShotEvaluationEpochReceipt:
        return cls(
            schema_version="power.retrieval-one-shot-epoch.v1",
            **binding.model_dump(mode="python"),
            started_at=datetime.now(UTC),
            status="STARTED",
        )

    @model_validator(mode="after")
    def validate_completion_binding(self) -> OneShotEvaluationEpochReceipt:
        if self.status == "COMPLETED_PASS" and (
            self.raw_output_digest is None or self.raw_output_ref is None
        ):
            raise ValueError("completed epoch must bind a raw output artifact")
        if self.status == "STARTED" and self.completed_at is not None:
            raise ValueError("started epoch cannot have a completion timestamp")
        return self


@dataclass(frozen=True)
class HoldoutExecutionDescriptor:
    """Safe descriptor returned to Stage A; it contains no ground truth."""

    evaluation_revision: str
    revision_spec_digest: str
    dataset_digest: str
    query_set_digest: str
    holdout_digest: str
    source_corpus_digest: str
    query_count: int


@dataclass(frozen=True)
class VerifiedHoldoutExecution:
    """Verified query-only source and descriptor for Stage A."""

    queries: tuple[QueryOnlyRecord, ...]
    descriptor: HoldoutExecutionDescriptor


def _bounded_root(output_root: Path, allowed_root: Path, *, allow_guard: bool = False) -> Path:
    root = Path(output_root)
    allowed = Path(allowed_root)
    if root.is_symlink() or allowed.is_symlink():
        raise EvaluationIntegrityError("output_root", "one-shot output roots must not be symlinks")
    if not root.is_dir() or not allowed.is_dir():
        raise EvaluationIntegrityError(
            "output_root", "one-shot output root must be an existing directory"
        )
    try:
        resolved_root = root.resolve()
        resolved_allowed = allowed.resolve()
        resolved_root.relative_to(resolved_allowed)
    except ValueError as exc:
        raise EvaluationIntegrityError(
            "output_root", "one-shot output root escapes its explicit bounded work root"
        ) from exc
    children = list(root.iterdir())
    if allow_guard:
        unexpected = [
            child
            for child in children
            if child.name not in {EPOCH_GUARD_FILENAME, EPOCH_REGISTRY_DIRNAME}
        ]
        if unexpected:
            raise EvaluationIntegrityError(
                "output_root", "one-shot output root contains unexpected files"
            )
    elif children:
        raise EvaluationIntegrityError(
            "output_root", "one-shot output root contains unexpected files"
        )
    return resolved_root


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd: int | None = None
    try:
        fd = os.open(path, flags, 0o600)
        written = 0
        while written < len(payload):
            written += os.write(fd, payload[written:])
        os.fsync(fd)
    except OSError as exc:
        if exc.errno in {errno.EEXIST, errno.ELOOP}:
            raise EvaluationIntegrityError(
                "epoch_already_consumed", "one-shot epoch already exists"
            ) from exc
        raise EvaluationIntegrityError(
            "epoch_guard", "one-shot epoch guard could not be created"
        ) from exc
    finally:
        if fd is not None:
            os.close(fd)
    _fsync_directory(path.parent)


@dataclass
class OneShotEpochGuard:
    """Atomic exclusive-create guard that cannot be acquired twice."""

    root: Path
    receipt: OneShotEvaluationEpochReceipt
    global_guard_path: Path
    guard_identity: tuple[int, int]
    global_guard_identity: tuple[int, int]
    _closed: bool = False

    @classmethod
    def acquire(
        cls,
        output_root: Path,
        receipt: OneShotEvaluationEpochReceipt,
        *,
        allowed_root: Path,
    ) -> OneShotEpochGuard:
        if receipt.status != "STARTED":
            raise EvaluationIntegrityError(
                "epoch_already_consumed", "epoch is not in STARTED state"
            )
        root = _bounded_root(Path(output_root), Path(allowed_root), allow_guard=True)
        guard_path = root / EPOCH_GUARD_FILENAME
        if guard_path.exists() or guard_path.is_symlink():
            raise EvaluationIntegrityError(
                "epoch_already_consumed", "one-shot epoch already exists"
            )
        registry_root = Path(allowed_root).resolve() / EPOCH_REGISTRY_DIRNAME
        if registry_root.is_symlink():
            raise EvaluationIntegrityError("epoch_guard", "epoch registry must not be a symlink")
        if registry_root.exists() and not registry_root.is_dir():
            raise EvaluationIntegrityError("epoch_guard", "epoch registry is not a directory")
        registry_root.mkdir(mode=0o700, exist_ok=True)
        global_guard_path = registry_root / f"{receipt.revision_spec_digest}.json"
        if global_guard_path.exists() or global_guard_path.is_symlink():
            raise EvaluationIntegrityError("epoch_already_consumed", "epoch binding already exists")
        payload = receipt.to_canonical_bytes() + b"\n"
        _write_exclusive(global_guard_path, payload)
        _write_exclusive(guard_path, payload)
        local_stat = os.stat(guard_path, follow_symlinks=False)
        global_stat = os.stat(global_guard_path, follow_symlinks=False)
        return cls(
            root=root,
            receipt=receipt,
            global_guard_path=global_guard_path,
            guard_identity=(local_stat.st_dev, local_stat.st_ino),
            global_guard_identity=(global_stat.st_dev, global_stat.st_ino),
        )

    @property
    def guard_path(self) -> Path:
        return self.root / EPOCH_GUARD_FILENAME

    def _set_status(
        self,
        status: Literal["COMPLETED_PASS", "COMPLETED_FAIL", "INTERRUPTED"],
        *,
        raw_output_digest: str | None = None,
        raw_output_ref: str | None = None,
    ) -> OneShotEvaluationEpochReceipt:
        if self._closed:
            raise EvaluationIntegrityError(
                "epoch_already_closed", "one-shot epoch is already closed"
            )
        updates: dict[str, Any] = {
            "status": status,
            "completed_at": datetime.now(UTC),
        }
        if raw_output_digest is not None:
            updates["raw_output_digest"] = raw_output_digest
        if raw_output_ref is not None:
            updates["raw_output_ref"] = raw_output_ref
        updated = self.receipt.model_copy(update=updates)
        temporary = self.root / f".{EPOCH_GUARD_FILENAME}.{os.getpid()}.{time_ns()}"
        _write_exclusive(temporary, updated.to_canonical_bytes() + b"\n")
        if self.guard_path.is_symlink() or self.global_guard_path.is_symlink():
            raise EvaluationIntegrityError("epoch_guard", "epoch guard target became a symlink")
        local_stat = os.stat(self.guard_path, follow_symlinks=False)
        global_stat = os.stat(self.global_guard_path, follow_symlinks=False)
        if (local_stat.st_dev, local_stat.st_ino) != self.guard_identity or (
            global_stat.st_dev,
            global_stat.st_ino,
        ) != self.global_guard_identity:
            raise EvaluationIntegrityError("epoch_guard", "epoch guard identity changed")
        os.replace(temporary, self.guard_path)
        global_temporary = self.global_guard_path.with_name(
            f".{self.global_guard_path.name}.{os.getpid()}.{time_ns()}"
        )
        _write_exclusive(global_temporary, updated.to_canonical_bytes() + b"\n")
        os.replace(global_temporary, self.global_guard_path)
        _fsync_directory(self.root)
        _fsync_directory(self.global_guard_path.parent)
        self.receipt = updated
        self._closed = True
        return updated

    def complete(
        self, *, raw_output_digest: str, raw_output_ref: str
    ) -> OneShotEvaluationEpochReceipt:
        return self._set_status(
            "COMPLETED_PASS",
            raw_output_digest=raw_output_digest,
            raw_output_ref=raw_output_ref,
        )

    def fail(self) -> OneShotEvaluationEpochReceipt:
        return self._set_status("COMPLETED_FAIL")

    def interrupt(self) -> OneShotEvaluationEpochReceipt:
        if self._closed:
            return self.receipt
        return self._set_status("INTERRUPTED")

    def __enter__(self) -> OneShotEpochGuard:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if exc_type is not None and not self._closed:
            self.interrupt()


def time_ns() -> int:
    """Small indirection that makes exclusive-update names easy to test."""

    return time.time_ns()


def _deep_validate_raw_output_artifact(
    artifact: RawRetrievalOutputArtifact,
) -> RawRetrievalOutputArtifact:
    try:
        return RawRetrievalOutputArtifact.model_validate(artifact.model_dump(mode="python"))
    except (TypeError, ValueError, ValidationError) as exc:
        raise EvaluationIntegrityError(
            "raw_output_schema", "raw output failed deep canonical validation"
        ) from exc


def write_raw_output_artifact(
    artifact: RawRetrievalOutputArtifact,
    *,
    output_root: Path,
    allowed_root: Path,
) -> Path:
    """Persist raw output exactly once inside a bounded work root."""

    validated_artifact = _deep_validate_raw_output_artifact(artifact)
    root = _bounded_root(Path(output_root), Path(allowed_root), allow_guard=True)
    output = root / RAW_OUTPUT_FILENAME
    if output.exists() or output.is_symlink():
        raise EvaluationIntegrityError("raw_output_exists", "raw output artifact already exists")
    payload = validated_artifact.to_canonical_bytes() + b"\n"
    if len(payload) > MAX_RAW_OUTPUT_BYTES:
        raise EvaluationIntegrityError("raw_output_too_large", "raw output exceeds the byte bound")
    _write_exclusive(output, payload)
    return output


def read_epoch_receipt(path: Path) -> OneShotEvaluationEpochReceipt:
    """Read one bounded epoch receipt without exposing query/GT content."""

    try:
        return OneShotEvaluationEpochReceipt.model_validate(load_bounded_json(path))
    except ValidationError as exc:
        raise EvaluationIntegrityError("epoch_receipt", "epoch receipt failed validation") from exc


def prepare_verified_holdout_execution(
    root: Path,
    *,
    expected_revision: str,
    revision_spec: SealedRevisionSpec | dict[str, Any],
    budget_class: Literal["FAST", "BALANCED", "DEEP"] = "FAST",
) -> VerifiedHoldoutExecution:
    """Verify a future corpus and return only query-side holdout records."""

    if not expected_revision:
        raise EvaluationIntegrityError(
            "revision_required", "holdout execution requires an explicit revision"
        )
    spec = validate_sealed_revision_spec(revision_spec)
    if spec.revision != expected_revision:
        raise EvaluationIntegrityError(
            "revision_mismatch", "revision spec does not match expected revision"
        )
    verified = verify_evaluation_corpus(
        Path(root),
        expected_revision=expected_revision,
        revision_spec=spec,
        return_snapshot=True,
    )
    if not isinstance(verified, EvaluationVerificationSnapshot):
        raise EvaluationIntegrityError(
            "verifier_state", "holdout verifier did not return a snapshot"
        )
    query_records: list[QueryOnlyRecord] = []
    for query in verified.holdout_queries:
        data: dict[str, Any] = {
            "query_id": query.query_id,
            "query": query.query,
            "budget_class": budget_class,
        }
        if query.intent is not None:
            data["intent"] = query.intent.value
        query_records.append(QueryOnlyRecord.model_validate(data))
    return VerifiedHoldoutExecution(
        queries=tuple(query_records),
        descriptor=HoldoutExecutionDescriptor(
            evaluation_revision=verified.manifest.evaluation_revision,
            revision_spec_digest=spec.digest(),
            dataset_digest=verified.manifest.dataset_digest,
            query_set_digest=verified.manifest.query_set_digest,
            holdout_digest=verified.manifest.holdout_split.digest,
            source_corpus_digest=verified.manifest.source_corpus_digest or "",
            query_count=len(query_records),
        ),
    )


def execute_query_only_once(
    *,
    queries: tuple[QueryOnlyRecord, ...],
    binding: EpochBinding,
    output_root: Path,
    allowed_root: Path,
    one_shot_intent: str,
    executor: Callable[[QueryOnlyRecord], RawRetrievalOutputRecord],
    verified_descriptor: HoldoutExecutionDescriptor | None = None,
) -> tuple[RawRetrievalOutputArtifact, OneShotEvaluationEpochReceipt]:
    """Acquire the guard, execute query-only input, and freeze raw output."""

    if one_shot_intent != FRESH_HOLDOUT_ONE_SHOT_INTENT:
        raise EvaluationIntegrityError(
            "one_shot_required", "fresh holdout execution requires explicit one-shot intent"
        )
    if not queries:
        raise EvaluationIntegrityError(
            "query_scope", "one-shot execution requires at least one query"
        )
    if not isinstance(verified_descriptor, HoldoutExecutionDescriptor):
        raise EvaluationIntegrityError(
            "descriptor_required", "one-shot execution requires a verified descriptor"
        )
    binding.assert_matches_descriptor(verified_descriptor)
    if len(queries) != verified_descriptor.query_count:
        raise EvaluationIntegrityError(
            "descriptor_query_count", "query count does not match the verified descriptor"
        )
    receipt = OneShotEvaluationEpochReceipt.start(binding=binding)
    guard = OneShotEpochGuard.acquire(output_root, receipt, allowed_root=allowed_root)
    try:
        records: list[RawRetrievalOutputRecord] = []
        for query in queries:
            record = executor(query)
            if record.query_id != query.query_id:
                raise EvaluationIntegrityError(
                    "raw_output_query_id", "executor returned an unexpected query ID"
                )
            records.append(record)
        artifact = RawRetrievalOutputArtifact(
            schema_version="power.retrieval-raw-output.v1",
            evaluation_revision=binding.evaluation_revision,
            revision_spec_digest=binding.revision_spec_digest,
            query_set_digest=binding.query_set_digest,
            source_corpus_digest=binding.source_corpus_digest,
            runtime_digest=binding.runtime_digest,
            execution_runner_digest=binding.execution_runner_digest,
            fixture_digest=binding.fixture_digest,
            records=records,
        )
        validated_artifact = _deep_validate_raw_output_artifact(artifact)
        output_path = write_raw_output_artifact(
            validated_artifact,
            output_root=output_root,
            allowed_root=allowed_root,
        )
        completed = guard.complete(
            raw_output_digest=validated_artifact.digest(),
            raw_output_ref=output_path.relative_to(Path(output_root).resolve()).as_posix(),
        )
        return validated_artifact, completed
    except Exception:
        guard.interrupt()
        raise


__all__ = [
    "EPOCH_GUARD_FILENAME",
    "EPOCH_REGISTRY_DIRNAME",
    "FRESH_HOLDOUT_ONE_SHOT_INTENT",
    "RAW_OUTPUT_FILENAME",
    "EpochBinding",
    "HoldoutExecutionDescriptor",
    "ObservedCandidate",
    "OneShotEpochGuard",
    "OneShotEvaluationEpochReceipt",
    "QueryOnlyRecord",
    "RawRetrievalOutputArtifact",
    "RawRetrievalOutputRecord",
    "VerifiedHoldoutExecution",
    "execute_query_only_once",
    "prepare_verified_holdout_execution",
    "read_epoch_receipt",
    "write_raw_output_artifact",
]
