"""Strict, secret-free contracts for the INFRA-1 execution boundary.

The request models in this module are deliberately smaller than the policy
models.  A caller chooses identifiers; only the broker resolves infrastructure
facts.  All response models are closed schemas so a compromised or fake local
endpoint cannot smuggle a command, environment, path inventory, or credential
material back into an agent context.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HOSTNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}[A-Za-z0-9]$")
_USER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,31}$")
_FINGERPRINT_PATTERN = re.compile(r"^SHA256:[A-Za-z0-9+/]+={0,2}$")
_ABSOLUTE_PATH_PATTERN = re.compile(r"^/[A-Za-z0-9._/+@=-]+$")
_RUN_PATTERN = re.compile(r"^run_[0-9a-f]{64}$")
_TRACE_PATTERN = re.compile(r"^tr_[0-9a-f]{32}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_IDEMPOTENCY_REF_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_FORBIDDEN_OUTPUT_KEYS = frozenset(
    {
        "argv",
        "command",
        "commands",
        "environment",
        "full_path",
        "private_key",
        "password",
        "raw_command",
        "raw_stderr",
        "raw_stdout",
        "stderr",
        "stdout",
        "token",
    }
)


class InfraOperation(StrEnum):
    """The only operations admitted by INFRA-1 v1."""

    STATUS = "status"
    PROBE = "probe"
    RSYNC_DRY_RUN = "rsync-dry-run"
    REPLICATE = "replicate"
    VERIFY = "verify"


InfraCapabilityId = Literal[
    "infra.broker.v1",
    "infra.ssh.probe.v1",
    "infra.rsync.dry-run.v1",
    "infra.rsync.replicate.v1",
    "infra.rsync.verify.v1",
]


CAPABILITY_BY_OPERATION: dict[InfraOperation, InfraCapabilityId] = {
    InfraOperation.STATUS: "infra.broker.v1",
    InfraOperation.PROBE: "infra.ssh.probe.v1",
    InfraOperation.RSYNC_DRY_RUN: "infra.rsync.dry-run.v1",
    InfraOperation.REPLICATE: "infra.rsync.replicate.v1",
    InfraOperation.VERIFY: "infra.rsync.verify.v1",
}


class InfraResponseStatus(StrEnum):
    """Bounded broker outcomes used by application adapters."""

    OK = "ok"
    BLOCKED = "blocked"
    AUTH_REQUIRED = "auth-required"
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
    OPERATION_IN_FLIGHT = "OPERATION_IN_FLIGHT"
    UNKNOWN_COMPLETION = "UNKNOWN_COMPLETION"
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    RUN_ALREADY_REPLICATED = "RUN_ALREADY_REPLICATED"
    APPROVAL_REPLAY = "APPROVAL_REPLAY"
    TIMEOUT = "TIMEOUT"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    PRINCIPAL_DENIED = "PRINCIPAL_DENIED"
    PRINCIPAL_UNAVAILABLE = "PRINCIPAL_UNAVAILABLE"
    DRY_RUN_REQUIRED = "DRY_RUN_REQUIRED"
    PROCESS_UNAVAILABLE = "PROCESS_UNAVAILABLE"
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
    UNKNOWN = "unknown"
    FAILED = "failed"


class InfraBaseModel(BaseModel):
    """Base model that fails closed on fields outside the contract."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


def _validate_token(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _TOKEN_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a safe identifier")
    return value


def _validate_safe_path(value: str, field_name: str, *, absolute: bool = True) -> str:
    if not isinstance(value, str) or not value or any(ord(char) < 32 for char in value):
        raise ValueError(f"{field_name} contains control characters")
    if "\\" in value or "~" in value or "$" in value or "%" in value:
        raise ValueError(f"{field_name} contains unsupported path syntax")
    if ".." in value.split("/"):
        raise ValueError(f"{field_name} must not contain traversal")
    if absolute and not value.startswith("/"):
        raise ValueError(f"{field_name} must be absolute")
    if absolute and not _ABSOLUTE_PATH_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} contains an unsafe path component")
    return value.rstrip("/") or "/"


def _validate_host(value: str) -> str:
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        raise ValueError("hostname must be a bounded host identifier")
    if any(char in value for char in "/\\[]*?!,$'\"`;"):
        raise ValueError("hostname contains unsupported syntax")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        if not _HOSTNAME_PATTERN.fullmatch(value) or ".." in value:
            raise ValueError("hostname must be a plain approved host identifier") from None
    return value


def _validate_public_token(value: str, field_name: str) -> str:
    return _validate_token(value, field_name) or ""


def _validate_optional_public_token(value: str | None, field_name: str) -> str | None:
    return _validate_token(value, field_name)


def _validate_public_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{field_name} must be bounded text")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{field_name} contains control characters")
    return value


class InfraRequest(InfraBaseModel):
    """LLM-facing request containing identifiers only, never infrastructure data."""

    operation: InfraOperation
    target: str | None = Field(default=None, max_length=128)
    profile: str | None = Field(default=None, max_length=128)
    dry_run: StrictBool = False
    idempotency_key: str | None = Field(default=None, max_length=128)
    run_id: str | None = Field(default=None, max_length=128)
    approval_ref: str | None = Field(default=None, max_length=128)
    # These fields only correlate a broker result with a pre-existing Task.  The
    # broker never treats them as authorization and never mutates TaskStore.
    task_id: str | None = Field(default=None, max_length=128)
    expected_revision: StrictInt | None = Field(default=None, ge=1)

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str | None) -> str | None:
        return _validate_token(value, "target")

    @field_validator("profile")
    @classmethod
    def validate_profile(cls, value: str | None) -> str | None:
        return _validate_token(value, "profile")

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, value: str | None) -> str | None:
        return _validate_token(value, "idempotency_key")

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str | None) -> str | None:
        if value is not None and not _RUN_PATTERN.fullmatch(value):
            raise ValueError("run_id must be a broker-derived run identifier")
        return value

    @field_validator("approval_ref")
    @classmethod
    def validate_approval_ref(cls, value: str | None) -> str | None:
        return _validate_token(value, "approval_ref")

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str | None) -> str | None:
        return _validate_token(value, "task_id")

    @model_validator(mode="after")
    def validate_operation_contract(self) -> InfraRequest:
        if self.operation is InfraOperation.STATUS and (
            self.target is not None
            or self.profile is not None
            or self.dry_run
            or self.idempotency_key is not None
            or self.run_id is not None
            or self.approval_ref is not None
            or self.task_id is not None
            or self.expected_revision is not None
        ):
            raise ValueError("status does not accept target, profile, or execution references")
        if self.operation is InfraOperation.REPLICATE and not self.idempotency_key:
            raise ValueError("replicate requires idempotency_key")
        if self.operation is InfraOperation.REPLICATE and self.dry_run:
            raise ValueError("replicate dry_run must use rsync-dry-run operation")
        if self.operation is InfraOperation.VERIFY and not self.run_id:
            raise ValueError("verify requires run_id")
        if self.operation is not InfraOperation.VERIFY and self.run_id is not None:
            raise ValueError("run_id is valid only for verify")
        if self.operation is not InfraOperation.REPLICATE and self.approval_ref is not None:
            raise ValueError("approval_ref is valid only for replicate")
        if self.task_id is None and self.expected_revision is not None:
            raise ValueError("expected_revision requires task_id")
        if self.task_id is not None:
            if self.operation is InfraOperation.STATUS:
                raise ValueError("status cannot bind a task")
            if not self.idempotency_key or self.expected_revision is None:
                raise ValueError("task-bound action requires idempotency_key and expected_revision")
        return self


class InfraProfile(InfraBaseModel):
    """Operator-owned mapping from identifiers to fixed infrastructure facts."""

    profile_id: StrictStr = Field(min_length=1, max_length=128)
    target_id: StrictStr = Field(min_length=1, max_length=128)
    hostname: StrictStr = Field(min_length=1, max_length=253)
    port: StrictInt = Field(default=22, ge=1, le=65535)
    remote_user: StrictStr = Field(min_length=1, max_length=32)
    remote_root: StrictStr = Field(min_length=1, max_length=512)
    allowed_operations: list[InfraOperation] = Field(min_length=1, max_length=5)
    source_roots: list[StrictStr] = Field(min_length=1, max_length=8)
    known_hosts_file: StrictStr = Field(min_length=1, max_length=512)
    host_key_fingerprint: StrictStr = Field(min_length=16, max_length=128)
    credential_id: StrictStr = Field(min_length=1, max_length=128)
    verify_credential_id: StrictStr | None = Field(default=None, max_length=128)
    allow_plaintext_credential_fallback: StrictBool = False
    allowed_principal_refs: list[StrictStr] = Field(default_factory=list, max_length=32)
    max_files: StrictInt = Field(default=10_000, ge=1, le=1_000_000)
    max_bytes: StrictInt = Field(default=10_000_000_000, ge=1, le=10_000_000_000)
    timeout_seconds: StrictInt = Field(default=300, ge=1, le=3600)
    max_output_bytes: StrictInt = Field(default=64_000, ge=1024, le=1_000_000)
    max_concurrent: StrictInt = Field(default=1, ge=1, le=2)
    max_retries: StrictInt = Field(default=0, ge=0, le=0)
    approval_policy: Literal["standing", "explicit"] = "explicit"
    standing_approval_ref: StrictStr | None = Field(default=None, max_length=128)
    standing_principal_ref: StrictStr | None = Field(default=None, max_length=128)
    dry_run_policy: Literal["required", "standing"] = "required"
    receiver_mode: Literal["rrsync-write-only", "rrsync-immutable"] = "rrsync-immutable"
    immutable_snapshot: StrictBool = True
    no_delete: StrictBool = True
    policy_revision: StrictStr = Field(min_length=1, max_length=128)

    @field_validator("profile_id", "target_id", "credential_id", "policy_revision")
    @classmethod
    def validate_identifiers(cls, value: str) -> str:
        return _validate_token(value, "identifier") or ""

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, value: str) -> str:
        return _validate_host(value)

    @field_validator("remote_user")
    @classmethod
    def validate_remote_user(cls, value: str) -> str:
        if not _USER_PATTERN.fullmatch(value) or value == "root":
            raise ValueError("remote_user must be a safe non-root identifier")
        return value

    @field_validator("remote_root")
    @classmethod
    def validate_remote_root(cls, value: str) -> str:
        return _validate_safe_path(value, "remote_root")

    @field_validator("source_roots")
    @classmethod
    def validate_source_roots(cls, values: list[str]) -> list[str]:
        for value in values:
            normalized = _validate_safe_path(value, "source_root")
            if normalized == "/" or normalized.startswith(("/proc", "/sys", "/dev", "/run")):
                raise ValueError("source_root is outside the approved data staging class")
        if len(set(values)) != len(values):
            raise ValueError("source_roots must be unique")
        return values

    @field_validator("known_hosts_file")
    @classmethod
    def validate_known_hosts_file(cls, value: str) -> str:
        return _validate_safe_path(value, "known_hosts_file")

    @field_validator("host_key_fingerprint")
    @classmethod
    def validate_host_key_fingerprint(cls, value: str) -> str:
        if not _FINGERPRINT_PATTERN.fullmatch(value):
            raise ValueError("host_key_fingerprint must be an SSH SHA256 fingerprint")
        return value

    @field_validator("allowed_principal_refs", "standing_principal_ref")
    @classmethod
    def validate_principal_refs(cls, value: list[str] | str | None) -> list[str] | str | None:
        values = value if isinstance(value, list) else [value] if value is not None else []
        for principal in values:
            if not isinstance(principal, str) or not re.fullmatch(r"uid:[0-9]+", principal):
                raise ValueError("principal references must be server-derived uid identifiers")
        return value

    @field_validator("standing_approval_ref")
    @classmethod
    def validate_standing_approval_ref(cls, value: str | None) -> str | None:
        return _validate_token(value, "standing_approval_ref")

    @field_validator("verify_credential_id")
    @classmethod
    def validate_verify_credential_id(cls, value: str | None) -> str | None:
        return _validate_token(value, "verify_credential_id")

    @model_validator(mode="after")
    def validate_policy_invariants(self) -> InfraProfile:
        if len(set(self.allowed_operations)) != len(self.allowed_operations):
            raise ValueError("allowed_operations must be unique")
        if self.approval_policy == "standing" and not self.standing_approval_ref:
            raise ValueError("standing approval policy requires standing_approval_ref")
        if self.approval_policy == "standing" and not self.standing_principal_ref:
            raise ValueError("standing approval policy requires standing_principal_ref")
        if self.approval_policy == "explicit" and self.standing_approval_ref is not None:
            raise ValueError("explicit approval policy cannot carry a standing approval")
        if self.verify_credential_id == self.credential_id:
            raise ValueError("verify_credential_id must use a separate receiver identity")
        if not self.immutable_snapshot or not self.no_delete:
            raise ValueError("INFRA-1 profiles require immutable_snapshot and no_delete")
        if self.immutable_snapshot and self.receiver_mode != "rrsync-immutable":
            raise ValueError("immutable_snapshot requires the immutable rrsync receiver mode")
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
    """Operator-installed exact approval; an agent cannot mint this record."""

    approval_ref: StrictStr = Field(min_length=1, max_length=128)
    operation: Literal[InfraOperation.REPLICATE] = InfraOperation.REPLICATE
    target_id: StrictStr = Field(min_length=1, max_length=128)
    profile_id: StrictStr = Field(min_length=1, max_length=128)
    policy_revision: StrictStr = Field(min_length=1, max_length=128)
    profile_digest: StrictStr = Field(pattern=_SHA256_PATTERN.pattern)
    principal_ref: StrictStr = Field(min_length=1, max_length=128)
    expires_at: StrictStr = Field(min_length=1, max_length=64)
    one_time: StrictBool = True

    @field_validator("approval_ref", "target_id", "profile_id", "policy_revision")
    @classmethod
    def validate_approval_tokens(cls, value: str) -> str:
        return _validate_token(value, "approval field") or ""

    @field_validator("principal_ref")
    @classmethod
    def validate_approval_principal(cls, value: str) -> str:
        if not re.fullmatch(r"uid:[0-9]+", value):
            raise ValueError("approval principal_ref must be a server-derived uid reference")
        return value

    @model_validator(mode="after")
    def require_one_time_use(self) -> InfraApprovalRecord:
        if not self.one_time:
            raise ValueError("INFRA-1 approvals must be one-time")
        return self


class InfraProfileStatus(InfraBaseModel):
    """Content-free dynamic profile readiness facts."""

    profile_id: StrictStr = Field(max_length=128)
    target_id: StrictStr = Field(max_length=128)
    policy_revision: StrictStr = Field(max_length=128)
    allowed_operations: list[InfraOperation]
    credential_status: Literal["available", "missing", "invalid"]
    credential_source: Literal[
        "systemd-loadcredential", "configured", "plaintext-fallback", "missing"
    ]
    verify_credential_status: Literal["available", "missing", "invalid", "not-configured"]
    host_identity_status: Literal["pinned", "missing", "mismatch", "invalid"]
    profile_status: Literal["ready", "credential-missing", "host-key-missing", "invalid"]
    approval_policy: Literal["standing", "explicit"]

    @field_validator("profile_id", "target_id", "policy_revision")
    @classmethod
    def validate_status_identifiers(cls, value: str) -> str:
        return _validate_public_token(value, "profile status identifier")


class InfraResponseData(InfraBaseModel):
    """Closed bounded data payload shared by all broker operations."""

    broker_status: StrictStr | None = Field(default=None, max_length=64)
    client_supported: StrictBool | None = None
    transport: Literal["unix", "ssh-rsync"] | None = None
    principal_source: Literal["SO_PEERCRED", "getpeereid"] | None = None
    profiles: list[InfraProfileStatus] = Field(default_factory=list, max_length=128)
    ready: StrictBool | None = None
    run_id: str | None = None
    file_count: StrictInt = Field(default=0, ge=0, le=1_000_000)
    byte_count: StrictInt = Field(default=0, ge=0, le=10_000_000_000)
    dry_run: StrictBool | None = None
    reachable: StrictBool | None = None
    verification: (
        Literal[
            "status",
            "not-requested",
            "dry-run-passed",
            "replicated-awaiting-verify",
            "passed",
            "inventory-matched",
            "mismatch",
            "unknown",
        ]
        | None
    ) = None
    replay: StrictBool = False

    def __getitem__(self, key: str) -> object:
        """Preserve read-only mapping compatibility without permitting new fields."""

        if key not in type(self).model_fields:
            raise KeyError(key)
        return getattr(self, key)

    @field_validator("run_id")
    @classmethod
    def validate_response_run_id(cls, value: str | None) -> str | None:
        if value is not None and not _RUN_PATTERN.fullmatch(value):
            raise ValueError("response run_id is invalid")
        return value

    @field_validator("broker_status")
    @classmethod
    def validate_broker_status(cls, value: str | None) -> str | None:
        return _validate_optional_public_token(value, "broker_status")


class InfraCapabilityBlockReceipt(InfraBaseModel):
    """Content-free receipt for a blocked capability or policy admission."""

    schema_version: Literal["power.infra-block.v1"] = "power.infra-block.v1"
    receipt_id: str = Field(pattern=r"^ibr_[0-9a-f]{64}$")
    trace_id: str = Field(pattern=_TRACE_PATTERN.pattern)
    task_id: str | None = None
    principal_ref: str | None = None
    operation: InfraOperation
    target_id: str | None = None
    profile_id: str = Field(default="unknown", max_length=128)
    reason_code: InfraReasonCode
    required_capability: InfraCapabilityId
    policy_revision: str = Field(default="unknown", max_length=128)
    broker_status: str = Field(min_length=1, max_length=64)
    remediation_code: str = Field(min_length=1, max_length=128)
    recorded_at: str = Field(min_length=1, max_length=64)
    run_id: str | None = None
    source_manifest_digest: str | None = Field(default=None, pattern=_SHA256_PATTERN.pattern)

    @field_validator("task_id", "target_id")
    @classmethod
    def validate_block_tokens(cls, value: str | None) -> str | None:
        return _validate_optional_public_token(value, "block identifier")

    @field_validator("principal_ref")
    @classmethod
    def validate_block_principal(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"uid:[0-9]+", value):
            raise ValueError("block receipt principal_ref must be server-derived")
        return value

    @field_validator("run_id")
    @classmethod
    def validate_block_run_id(cls, value: str | None) -> str | None:
        if value is not None and not _RUN_PATTERN.fullmatch(value):
            raise ValueError("block run_id is invalid")
        return value

    @field_validator("profile_id", "policy_revision", "broker_status", "remediation_code")
    @classmethod
    def validate_block_text(cls, value: str) -> str:
        return _validate_public_token(value, "block receipt field")

    @field_validator("recorded_at")
    @classmethod
    def validate_block_timestamp(cls, value: str) -> str:
        return _validate_public_text(value, "block recorded_at")


class InfraOperationReceipt(InfraBaseModel):
    """Bounded success/failure evidence returned by the broker."""

    schema_version: Literal["power.infra-receipt.v1"] = "power.infra-receipt.v1"
    receipt_id: str = Field(pattern=r"^ir_[0-9a-f]{64}$")
    trace_id: str = Field(pattern=_TRACE_PATTERN.pattern)
    task_id: str | None = None
    operation: InfraOperation
    target_id: str | None = None
    profile_id: str | None = None
    policy_revision: str = Field(min_length=1, max_length=128)
    principal_ref: str = Field(min_length=1, max_length=128)
    approval_ref: str | None = None
    source_manifest_digest: str | None = Field(default=None, pattern=_SHA256_PATTERN.pattern)
    host_key_fingerprint: str | None = None
    credential_id: str | None = None
    transport: Literal["unix", "ssh-rsync"]
    run_id: str | None = None
    dry_run: StrictBool
    file_count: StrictInt = Field(default=0, ge=0, le=1_000_000)
    byte_count: StrictInt = Field(default=0, ge=0, le=10_000_000_000)
    duration_ms: StrictInt = Field(default=0, ge=0, le=3_600_000)
    exit_category: InfraExitCategory
    verification_result: (
        Literal[
            "status",
            "not-requested",
            "dry-run-passed",
            "replicated-awaiting-verify",
            "passed",
            "inventory-matched",
            "mismatch",
            "unknown",
        ]
        | None
    ) = None
    idempotency_key_ref: str | None = Field(default=None, pattern=_IDEMPOTENCY_REF_PATTERN.pattern)
    recorded_at: str = Field(min_length=1, max_length=64)

    @field_validator("task_id", "target_id", "profile_id", "approval_ref", "credential_id")
    @classmethod
    def validate_receipt_tokens(cls, value: str | None) -> str | None:
        return _validate_optional_public_token(value, "receipt identifier")

    @field_validator("policy_revision", "principal_ref")
    @classmethod
    def validate_receipt_required_tokens(cls, value: str) -> str:
        return _validate_public_token(value, "receipt identifier")

    @field_validator("principal_ref")
    @classmethod
    def validate_receipt_principal(cls, value: str) -> str:
        if not re.fullmatch(r"uid:[0-9]+", value):
            raise ValueError("receipt principal_ref must be a server-derived uid identifier")
        return value

    @field_validator("host_key_fingerprint")
    @classmethod
    def validate_receipt_fingerprint(cls, value: str | None) -> str | None:
        if value is not None and not _FINGERPRINT_PATTERN.fullmatch(value):
            raise ValueError("receipt host key fingerprint is invalid")
        return value

    @field_validator("run_id")
    @classmethod
    def validate_receipt_run_id(cls, value: str | None) -> str | None:
        if value is not None and not _RUN_PATTERN.fullmatch(value):
            raise ValueError("receipt run_id is invalid")
        return value

    @field_validator("recorded_at")
    @classmethod
    def validate_receipt_timestamp(cls, value: str) -> str:
        return _validate_public_text(value, "receipt recorded_at")


class InfraResponse(InfraBaseModel):
    """Typed broker response; raw subprocess output is intentionally absent."""

    schema_version: Literal["power.infra-response.v1"] = "power.infra-response.v1"
    status: InfraResponseStatus
    operation: InfraOperation
    target: str | None = None
    profile: str | None = None
    task_id: str | None = None
    request_digest: str = Field(pattern=_SHA256_PATTERN.pattern)
    data: InfraResponseData = Field(default_factory=InfraResponseData)
    receipt: InfraOperationReceipt | InfraCapabilityBlockReceipt

    @field_validator("target", "profile", "task_id")
    @classmethod
    def validate_response_identifiers(cls, value: str | None) -> str | None:
        return _validate_optional_public_token(value, "response identifier")

    @model_validator(mode="after")
    def validate_response_binding(self) -> InfraResponse:
        if self.receipt.operation is not self.operation:
            raise ValueError("broker response receipt operation does not match response operation")
        if (
            self.operation is not InfraOperation.STATUS
            and (not self.target or not self.profile)
            and not (
                isinstance(self.receipt, InfraCapabilityBlockReceipt)
                and self.receipt.reason_code is InfraReasonCode.REQUEST_INPUT_MISSING
            )
        ):
            raise ValueError("non-status response must identify target and profile")
        if (
            self.operation is not InfraOperation.STATUS
            and isinstance(self.receipt, InfraOperationReceipt)
            and (self.receipt.target_id != self.target or self.receipt.profile_id != self.profile)
        ):
            raise ValueError("broker response receipt target/profile does not match request")
        if self.receipt.task_id != self.task_id:
            raise ValueError("broker response receipt task binding does not match response")
        if isinstance(self.receipt, InfraCapabilityBlockReceipt) and (
            (self.target is not None and self.receipt.target_id != self.target)
            or (self.profile is not None and self.receipt.profile_id != self.profile)
        ):
            raise ValueError("broker block receipt target/profile does not match response")
        if isinstance(self.receipt, InfraOperationReceipt):
            expected_status = (
                InfraResponseStatus.OK
                if self.receipt.exit_category
                in {InfraExitCategory.SUCCESS, InfraExitCategory.REPLAY}
                else InfraResponseStatus.FAILED
            )
            if self.status is not expected_status:
                raise ValueError("operation receipt status does not match its exit category")
        if isinstance(self.receipt, InfraCapabilityBlockReceipt):
            expected_status = (
                InfraResponseStatus.AUTH_REQUIRED
                if self.receipt.reason_code is InfraReasonCode.APPROVAL_REQUIRED
                else InfraResponseStatus.BLOCKED
            )
            if self.status is not expected_status:
                raise ValueError("block response status does not match its reason")
        elif self.receipt.exit_category in {InfraExitCategory.SUCCESS, InfraExitCategory.REPLAY}:
            if self.status is not InfraResponseStatus.OK:
                raise ValueError("successful receipt requires status=ok")
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

    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(canonical).hexdigest()}"


def ssh_fingerprint_from_blob(blob: bytes) -> str:
    """Compute OpenSSH's SHA256 fingerprint representation for a key blob."""

    digest = hashlib.sha256(blob).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def canonical_profile_digest(profile: InfraProfile) -> str:
    """Hash every profile fact that can affect an external operation."""

    payload = profile.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


__all__ = [
    "CAPABILITY_BY_OPERATION",
    "InfraApprovalRecord",
    "InfraBaseModel",
    "InfraCapabilityBlockReceipt",
    "InfraCapabilityId",
    "InfraExitCategory",
    "InfraOperation",
    "InfraOperationReceipt",
    "InfraPolicyFile",
    "InfraProfile",
    "InfraProfileStatus",
    "InfraReasonCode",
    "InfraRequest",
    "InfraResponse",
    "InfraResponseData",
    "InfraResponseStatus",
    "canonical_profile_digest",
    "derive_receipt_id",
    "idempotency_key_reference",
    "ssh_fingerprint_from_blob",
    "utc_now",
]
