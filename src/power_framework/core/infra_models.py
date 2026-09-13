"""Strict, secret-free contracts for the INFRA-1 execution boundary."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from collections.abc import Mapping

_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HOST_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")
_FINGERPRINT_PATTERN = re.compile(r"^SHA256:[A-Za-z0-9+/]+={0,2}$")
_PATH_PATTERN = re.compile(r"^[^\x00\r\n\x00]+$")
_REMOTE_COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_FORBIDDEN_OUTPUT_KEYS = {
    "command",
    "commands",
    "environment",
    "private_key",
    "password",
    "raw_stderr",
    "raw_stdout",
    "stderr",
    "stdout",
    "token",
}


class InfraOperation(StrEnum):
    """The complete v1 operation allowlist exposed to agents."""

    STATUS = "status"
    PROBE = "probe"
    RSYNC_DRY_RUN = "rsync-dry-run"
    REPLICATE = "replicate"
    VERIFY = "verify"


class InfraResponseStatus(StrEnum):
    """Bounded broker outcomes used by Task/MCP/CLI adapters."""

    OK = "ok"
    BLOCKED = "blocked"
    AUTH_REQUIRED = "auth-required"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class InfraReasonCode(StrEnum):
    """Stable, content-free reasons for refusing or stopping an operation."""

    MISSING_EXECUTION_CAPABILITY = "MISSING_EXECUTION_CAPABILITY"
    CAPABILITY_DISABLED = "CAPABILITY_DISABLED"
    HOST_IDENTITY_UNTRUSTED = "HOST_IDENTITY_UNTRUSTED"
    HOST_IDENTITY_MISMATCH = "HOST_IDENTITY_MISMATCH"
    NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"
    BROKER_CREDENTIAL_UNAVAILABLE = "BROKER_CREDENTIAL_UNAVAILABLE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    REQUEST_INPUT_MISSING = "REQUEST_INPUT_MISSING"
    PROFILE_NOT_FOUND = "PROFILE_NOT_FOUND"
    TARGET_NOT_ALLOWED = "TARGET_NOT_ALLOWED"
    POLICY_INVALID = "POLICY_INVALID"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    OPERATION_IN_FLIGHT = "OPERATION_IN_FLIGHT"
    TIMEOUT = "TIMEOUT"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    PRINCIPAL_DENIED = "PRINCIPAL_DENIED"
    DRY_RUN_REQUIRED = "DRY_RUN_REQUIRED"
    OPERATION_FAILED = "OPERATION_FAILED"


class InfraExitCategory(StrEnum):
    """Secret-free categories for subprocess and verification outcomes."""

    SUCCESS = "success"
    REPLAY = "replay"
    HOST_IDENTITY_MISMATCH = "host-identity-mismatch"
    HOST_IDENTITY_UNTRUSTED = "host-identity-untrusted"
    NETWORK_UNAVAILABLE = "network-unavailable"
    TIMEOUT = "timeout"
    OUTPUT_LIMIT = "output-limit"
    PROCESS_UNAVAILABLE = "process-unavailable"
    REMOTE_REJECTED = "remote-rejected"
    FAILED = "failed"


class InfraBaseModel(BaseModel):
    """Base model that fails closed on fields not present in the contract."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


def _validate_token(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _TOKEN_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a safe identifier")
    return value


def _validate_optional_path(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or not _PATH_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a bounded path without control characters")
    return value


class InfraRequest(InfraBaseModel):
    """LLM-facing request containing identifiers only, never infrastructure data."""

    operation: InfraOperation
    target: str | None = Field(default=None, max_length=128)
    profile: str | None = Field(default=None, max_length=128)
    dry_run: bool = False
    idempotency_key: str | None = Field(default=None, max_length=128)
    run_id: str | None = Field(default=None, max_length=128)
    approval_ref: str | None = Field(default=None, max_length=128)
    task_id: str | None = Field(default=None, max_length=128)
    expected_revision: int | None = Field(default=None, ge=1)

    _validate_target = field_validator("target")(lambda value: _validate_token(value, "target"))
    _validate_profile = field_validator("profile")(lambda value: _validate_token(value, "profile"))
    _validate_idempotency = field_validator("idempotency_key")(
        lambda value: _validate_token(value, "idempotency_key")
    )
    _validate_run = field_validator("run_id")(lambda value: _validate_token(value, "run_id"))
    _validate_approval = field_validator("approval_ref")(
        lambda value: _validate_token(value, "approval_ref")
    )
    _validate_task = field_validator("task_id")(lambda value: _validate_token(value, "task_id"))

    @model_validator(mode="after")
    def validate_operation_contract(self) -> InfraRequest:
        if self.operation == InfraOperation.REPLICATE and not self.idempotency_key:
            raise ValueError("replicate requires idempotency_key")
        if self.operation == InfraOperation.REPLICATE and self.dry_run:
            raise ValueError("replicate dry_run must use rsync-dry-run operation")
        if self.operation == InfraOperation.VERIFY and not self.run_id:
            raise ValueError("verify requires run_id")
        if self.operation != InfraOperation.VERIFY and self.run_id is not None:
            raise ValueError("run_id is valid only for verify")
        if self.operation != InfraOperation.REPLICATE and self.approval_ref is not None:
            raise ValueError("approval_ref is valid only for replicate")
        if self.task_id is None and self.expected_revision is not None:
            raise ValueError("expected_revision requires task_id")
        if self.task_id is not None:
            if self.operation == InfraOperation.STATUS:
                raise ValueError("status cannot mutate or bind a task")
            if not self.idempotency_key:
                raise ValueError("task-bound infrastructure action requires idempotency_key")
            if self.expected_revision is None:
                raise ValueError("task-bound infrastructure action requires expected_revision")
        return self


class InfraProfile(InfraBaseModel):
    """Operator-owned mapping from safe identifiers to infrastructure facts."""

    profile_id: str = Field(min_length=1, max_length=128)
    target_id: str = Field(min_length=1, max_length=128)
    hostname: str = Field(min_length=1, max_length=253)
    port: int = Field(default=22, ge=1, le=65535)
    remote_user: str = Field(min_length=1, max_length=64)
    remote_root: str = Field(min_length=1, max_length=512)
    allowed_operations: list[InfraOperation] = Field(min_length=1, max_length=5)
    source_roots: list[str] = Field(min_length=1, max_length=8)
    known_hosts_file: str = Field(min_length=1, max_length=512)
    host_key_fingerprint: str = Field(min_length=16, max_length=128)
    credential_id: str = Field(min_length=1, max_length=128)
    max_files: int = Field(default=10_000, ge=1, le=1_000_000)
    max_bytes: int = Field(default=10_000_000_000, ge=1, le=10_000_000_000)
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    max_output_bytes: int = Field(default=64_000, ge=1024, le=1_000_000)
    max_concurrent: int = Field(default=1, ge=1, le=2)
    max_retries: int = Field(default=0, ge=0, le=1)
    approval_policy: Literal["standing", "explicit"] = "explicit"
    standing_approval_ref: str | None = Field(default=None, max_length=128)
    standing_principal_ref: str | None = Field(default=None, max_length=128)
    dry_run_policy: Literal["required", "standing"] = "required"
    receiver_mode: Literal["rrsync-write-only"] = "rrsync-write-only"
    immutable_snapshot: bool = True
    no_delete: bool = True
    policy_revision: str = Field(min_length=1, max_length=128)

    @field_validator("profile_id", "target_id", "credential_id", "policy_revision")
    @classmethod
    def validate_identifiers(cls, value: str) -> str:
        return _validate_token(value, "identifier") or ""

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, value: str) -> str:
        if not _HOST_PATTERN.fullmatch(value) or ".." in value:
            raise ValueError("hostname must be a plain approved host identifier")
        return value

    @field_validator("remote_user")
    @classmethod
    def validate_remote_user(cls, value: str) -> str:
        if not _TOKEN_PATTERN.fullmatch(value) or "/" in value:
            raise ValueError("remote_user must be a safe non-root identifier")
        if value == "root":
            raise ValueError("root receiver accounts are not allowed")
        return value

    @field_validator("remote_root")
    @classmethod
    def validate_remote_root(cls, value: str) -> str:
        if not value.startswith("/") or not _PATH_PATTERN.fullmatch(value):
            raise ValueError("remote_root must be an absolute bounded path")
        if ".." in value.split("/"):
            raise ValueError("remote_root must not contain traversal")
        components = [component for component in value.split("/") if component]
        if any(not _REMOTE_COMPONENT_PATTERN.fullmatch(component) for component in components):
            raise ValueError("remote_root contains an unsafe path component")
        return value.rstrip("/") or "/"

    @field_validator("source_roots", "known_hosts_file")
    @classmethod
    def validate_configured_paths(cls, value: list[str] | str) -> list[str] | str:
        values = value if isinstance(value, list) else [value]
        for item in values:
            if (
                not item
                or not item.startswith("/")
                or not _PATH_PATTERN.fullmatch(item)
                or any(part in {".", ".."} for part in item.split("/")[1:])
            ):
                raise ValueError("configured paths must not contain control characters")
        return value

    @field_validator("host_key_fingerprint")
    @classmethod
    def validate_host_key_fingerprint(cls, value: str) -> str:
        if not _FINGERPRINT_PATTERN.fullmatch(value):
            raise ValueError("host_key_fingerprint must be an SSH SHA256 fingerprint")
        return value

    @field_validator("standing_approval_ref")
    @classmethod
    def validate_standing_approval(cls, value: str | None) -> str | None:
        return _validate_token(value, "standing_approval_ref")

    @field_validator("standing_principal_ref")
    @classmethod
    def validate_standing_principal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith("uid:") or len(value) > 128:
            raise ValueError("standing_principal_ref must be a server-derived uid reference")
        return value

    @model_validator(mode="after")
    def validate_policy_invariants(self) -> InfraProfile:
        if self.approval_policy == "standing" and not self.standing_approval_ref:
            raise ValueError("standing approval policy requires standing_approval_ref")
        if self.approval_policy == "standing" and not self.standing_principal_ref:
            raise ValueError("standing approval policy requires standing_principal_ref")
        if not self.immutable_snapshot or not self.no_delete:
            raise ValueError("INFRA-1 profiles require immutable_snapshot and no_delete")
        if (
            InfraOperation.REPLICATE not in self.allowed_operations
            and self.dry_run_policy == "standing"
        ):
            raise ValueError("dry_run_policy is meaningful only for replicate profiles")
        return self


class InfraPolicyFile(InfraBaseModel):
    """Strict root document for operator-managed broker profiles."""

    schema_version: Literal["power.infra-policy.v1"]
    profiles: list[InfraProfile] = Field(min_length=0, max_length=128)


class InfraApprovalRecord(InfraBaseModel):
    """Operator-installed approval; it is never minted by an agent request."""

    approval_ref: str = Field(min_length=1, max_length=128)
    operation: Literal[InfraOperation.REPLICATE] = InfraOperation.REPLICATE
    target_id: str = Field(min_length=1, max_length=128)
    profile_id: str = Field(min_length=1, max_length=128)
    policy_revision: str = Field(min_length=1, max_length=128)
    principal_ref: str = Field(min_length=1, max_length=128)
    expires_at: str = Field(min_length=1, max_length=64)

    @field_validator("approval_ref", "target_id", "profile_id", "policy_revision")
    @classmethod
    def validate_approval_tokens(cls, value: str) -> str:
        return _validate_token(value, "approval field") or ""

    @field_validator("principal_ref")
    @classmethod
    def validate_approval_principal(cls, value: str) -> str:
        if not value.startswith("uid:") or len(value) > 128:
            raise ValueError("approval principal_ref must be a server-derived uid reference")
        return value


class InfraCapabilityBlockReceipt(InfraBaseModel):
    """Content-free receipt for a blocked capability or policy admission."""

    schema_version: Literal["power.infra-block.v1"] = "power.infra-block.v1"
    receipt_id: str = Field(pattern=r"^ibr_[0-9a-f]{64}$")
    trace_id: str = Field(pattern=r"^tr_[A-Za-z0-9]{16,64}$")
    task_id: str | None = None
    operation: InfraOperation
    profile_id: str = Field(default="unknown", max_length=128)
    reason_code: InfraReasonCode
    required_capability: str = Field(min_length=1, max_length=128)
    policy_revision: str = Field(default="unknown", max_length=128)
    broker_status: str = Field(min_length=1, max_length=64)
    remediation_code: str = Field(min_length=1, max_length=128)
    recorded_at: str = Field(min_length=1, max_length=64)
    run_id: str | None = Field(default=None, max_length=128)
    source_manifest_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class InfraOperationReceipt(InfraBaseModel):
    """Bounded success/failure evidence returned by the broker."""

    schema_version: Literal["power.infra-receipt.v1"] = "power.infra-receipt.v1"
    receipt_id: str = Field(pattern=r"^ir_[0-9a-f]{64}$")
    trace_id: str = Field(pattern=r"^tr_[A-Za-z0-9]{16,64}$")
    task_id: str | None = None
    operation: InfraOperation
    target_id: str | None = None
    profile_id: str | None = None
    policy_revision: str = Field(min_length=1, max_length=128)
    principal_ref: str = Field(min_length=1, max_length=128)
    approval_ref: str | None = None
    source_manifest_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    host_key_fingerprint: str | None = None
    credential_id: str | None = None
    transport: Literal["unix", "ssh-rsync"]
    run_id: str | None = None
    dry_run: bool
    file_count: int = Field(default=0, ge=0)
    byte_count: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0, le=3_600_000)
    exit_category: InfraExitCategory
    verification_result: str | None = Field(default=None, max_length=128)
    idempotency_key_ref: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    recorded_at: str = Field(min_length=1, max_length=64)


class InfraResponse(InfraBaseModel):
    """Typed broker response; raw subprocess output is intentionally absent."""

    schema_version: Literal["power.infra-response.v1"] = "power.infra-response.v1"
    status: InfraResponseStatus
    operation: InfraOperation
    data: dict[str, Any] = Field(default_factory=dict)
    receipt: InfraOperationReceipt | InfraCapabilityBlockReceipt

    @field_validator("data")
    @classmethod
    def validate_bounded_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        if len(encoded) > 64_000:
            raise ValueError("broker response data exceeds the bounded response budget")
        if _contains_forbidden_output_key(value):
            raise ValueError("broker response data contains a forbidden sensitive field")
        return value

    @model_validator(mode="after")
    def validate_receipt_operation(self) -> InfraResponse:
        if self.receipt.operation != self.operation:
            raise ValueError("broker response receipt operation does not match response operation")
        return self


def _contains_forbidden_output_key(value: object) -> bool:
    if isinstance(value, dict):
        if any(str(key).casefold() in _FORBIDDEN_OUTPUT_KEYS for key in value):
            return True
        return any(_contains_forbidden_output_key(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_output_key(item) for item in value)
    return False


def utc_now() -> str:
    """Return a stable UTC timestamp for bounded receipts."""
    return datetime.now(UTC).isoformat()


def idempotency_key_reference(value: str | None) -> str | None:
    """Hash an idempotency key before it crosses the audit boundary."""
    if value is None:
        return None
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def derive_receipt_id(prefix: Literal["ir", "ibr"], payload: Mapping[str, object]) -> str:
    """Derive a content-addressed secret-free receipt identifier."""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(canonical).hexdigest()}"


def ssh_fingerprint_from_blob(blob: bytes) -> str:
    """Compute OpenSSH's SHA256 fingerprint representation for a key blob."""
    digest = hashlib.sha256(blob).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


__all__ = [
    "InfraApprovalRecord",
    "InfraBaseModel",
    "InfraCapabilityBlockReceipt",
    "InfraExitCategory",
    "InfraOperation",
    "InfraOperationReceipt",
    "InfraPolicyFile",
    "InfraProfile",
    "InfraReasonCode",
    "InfraRequest",
    "InfraResponse",
    "InfraResponseStatus",
    "derive_receipt_id",
    "idempotency_key_reference",
    "ssh_fingerprint_from_blob",
    "utc_now",
]
