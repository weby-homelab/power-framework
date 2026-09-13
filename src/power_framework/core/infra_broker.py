"""Constrained local INFRA-1 broker client and opt-in broker service.

The client is the only surface used by POWER CLI/MCP.  It accepts identifiers
only and speaks a bounded framed protocol over one configured Unix socket.  The
server owns profiles, credentials, host-key policy, fixed subprocess argv, and
all remote execution decisions.  Neither side accepts a shell command.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import selectors
import shlex
import signal
import socket
import stat
import struct
import subprocess
import time
import uuid
from base64 import b64decode
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from pydantic import ValidationError

from .infra_models import (
    InfraApprovalRecord,
    InfraCapabilityBlockReceipt,
    InfraExitCategory,
    InfraOperation,
    InfraOperationReceipt,
    InfraPolicyFile,
    InfraProfile,
    InfraReasonCode,
    InfraRequest,
    InfraResponse,
    InfraResponseStatus,
    derive_receipt_id,
    idempotency_key_reference,
    ssh_fingerprint_from_blob,
    utc_now,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

MAX_FRAME_BYTES = 64_000
SERVER_IO_TIMEOUT_SECONDS = 15.0
DEFAULT_SOCKET_PATH = Path("/run/power-infra/broker.sock")
DEFAULT_POLICY_PATH = Path("/etc/power/infra/profiles.d")
DEFAULT_STATE_DIR = Path("/var/lib/power-infra")
DEFAULT_APPROVAL_PATH = Path("/etc/power/infra/approvals.json")
SSH_BINARY = "/usr/bin/ssh"
RSYNC_BINARY = "/usr/bin/rsync"
_PEER_CREDENTIALS = getattr(socket, "SO_PEERCRED", 17)
_MAX_RECEIPT_LOG_BYTES = 10_000_000
_MAX_IDEMPOTENCY_RECORDS = 10_000
logger = logging.getLogger(__name__)


class InfraBrokerError(RuntimeError):
    """Internal error carrying only a bounded, public reason category."""

    def __init__(
        self,
        reason_code: InfraReasonCode,
        remediation_code: str,
        broker_status: str,
        message: str = "infrastructure operation blocked",
        *,
        policy_revision: str = "unknown",
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.remediation_code = remediation_code
        self.broker_status = broker_status
        self.policy_revision = policy_revision


class InfraBrokerClientProtocol(Protocol):
    """Small injectable boundary used by ApplicationService and tests."""

    def execute(self, request: InfraRequest) -> InfraResponse:
        """Execute one typed broker request."""


@dataclass(frozen=True)
class _ProcessResult:
    returncode: int | None
    stdout_bytes: int
    stderr_bytes: int
    category: InfraExitCategory
    duration_ms: int
    stdout_sample: bytes = b""


@dataclass(frozen=True)
class _Manifest:
    digest: str
    file_count: int
    byte_count: int


@dataclass(frozen=True)
class _Reservation:
    request_digest: str
    run_id: str
    source_manifest_digest: str
    policy_revision: str


def _safe_socket_path(path: Path) -> Path:
    path = Path(path).expanduser()
    if not path.is_absolute():
        raise ValueError("broker socket path must be absolute")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("broker socket path contains unsafe components")
    return path


def _assert_regular_operator_file(path: Path, *, max_bytes: int = 1_048_576) -> bytes:
    """Read a bounded, non-symlink, non-group/world-writable operator file."""
    _assert_no_symlink_components(path)
    _assert_secure_directory(path.parent)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError("operator configuration file is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError("operator configuration file must not be a symlink")
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("operator configuration file must be a regular file")
    if metadata.st_size > max_bytes:
        raise ValueError("operator configuration file exceeds its size limit")
    if metadata.st_mode & 0o022:
        raise ValueError("operator configuration file must not be group/world writable")
    if metadata.st_uid not in {0, os.geteuid()}:
        raise ValueError("operator configuration file has an unexpected owner")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValueError("operator configuration file is unreadable") from exc


def _assert_no_symlink_components(path: Path) -> None:
    """Reject symlinked ancestors before opening a configured path."""
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise ValueError("configured path components are unavailable") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("configured path must not contain symlink components")


def _assert_secure_directory(path: Path) -> None:
    """Require an existing policy/state directory to be private and operator-owned."""
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError("operator directory is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("operator path must be a regular directory")
    if metadata.st_mode & 0o022:
        raise ValueError("operator directory must not be group/world writable")
    if metadata.st_uid not in {0, os.geteuid()}:
        raise ValueError("operator directory has an unexpected owner")


def load_infra_policy(path: Path) -> InfraPolicyFile:
    """Load a strict policy file or a bounded directory of JSON profiles."""
    path = Path(path).expanduser()
    _assert_no_symlink_components(path)
    if path.is_symlink():
        raise ValueError("infrastructure policy path must not be a symlink")
    if path.is_dir():
        _assert_secure_directory(path)
        entries = sorted(
            entry for entry in path.glob("*.json") if not entry.name.endswith(".example.json")
        )
        if len(entries) > 128:
            raise ValueError("infrastructure policy has too many profile files")
        profiles: list[InfraProfile] = []
        for entry in entries:
            if entry.is_symlink():
                raise ValueError("infrastructure profile must not be a symlink")
            payload = json.loads(_assert_regular_operator_file(entry).decode("utf-8"))
            if isinstance(payload, dict) and "profiles" in payload:
                document = InfraPolicyFile.model_validate(payload)
                profiles.extend(document.profiles)
            else:
                profiles.append(InfraProfile.model_validate(payload))
        _validate_unique_profiles(profiles)
        return InfraPolicyFile(schema_version="power.infra-policy.v1", profiles=profiles)

    payload = json.loads(_assert_regular_operator_file(path).decode("utf-8"))
    try:
        document = InfraPolicyFile.model_validate(payload)
    except (TypeError, ValueError, ValidationError) as exc:
        raise ValueError("infrastructure policy schema is invalid") from exc
    _validate_unique_profiles(document.profiles)
    return document


def load_infra_approvals(path: Path) -> dict[str, dict[str, object]]:
    """Load operator-installed, exact-scope approvals from a strict file."""
    payload = json.loads(_assert_regular_operator_file(Path(path)).decode("utf-8"))
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "approvals"}
        or payload.get("schema_version") != "power.infra-approvals.v1"
    ):
        raise ValueError("infrastructure approval schema is invalid")
    raw_approvals = payload.get("approvals")
    if not isinstance(raw_approvals, list) or len(raw_approvals) > 10_000:
        raise ValueError("infrastructure approval list is invalid or unbounded")
    result: dict[str, dict[str, object]] = {}
    for raw in raw_approvals:
        record = InfraApprovalRecord.model_validate(raw)
        if record.approval_ref in result:
            raise ValueError("infrastructure approval_ref is duplicated")
        result[record.approval_ref] = record.model_dump(mode="json")
    return result


def _validate_unique_profiles(profiles: Iterable[InfraProfile]) -> None:
    seen_profiles: set[str] = set()
    seen_targets: set[tuple[str, str]] = set()
    for profile in profiles:
        if profile.profile_id in seen_profiles:
            raise ValueError("infrastructure policy contains duplicate profile_id")
        seen_profiles.add(profile.profile_id)
        target_key = (profile.target_id, profile.profile_id)
        if target_key in seen_targets:
            raise ValueError("infrastructure policy contains duplicate target/profile mapping")
        seen_targets.add(target_key)


def build_ssh_options(
    *,
    hostname: str,
    port: int,
    username: str,
    known_hosts_file: Path,
    credential_file: Path,
) -> list[str]:
    """Build the complete fixed SSH option vector used by the broker.

    ``hostname`` and ``username`` are accepted to keep this helper explicit at
    the policy boundary; the returned options never contain caller input.
    """
    del hostname, username
    return [
        "-o",
        "BatchMode=yes",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "PubkeyAuthentication=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "IdentityAgent=none",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts_file}",
        "-o",
        "RequestTTY=no",
        "-p",
        str(port),
        "-i",
        str(credential_file),
    ]


def _build_ssh_command(profile: InfraProfile, credential_file: Path) -> str:
    return shlex.join(
        [
            SSH_BINARY,
            *build_ssh_options(
                hostname=profile.hostname,
                port=profile.port,
                username=profile.remote_user,
                known_hosts_file=Path(profile.known_hosts_file),
                credential_file=credential_file,
            ),
        ]
    )


def _encode_frame(payload: Mapping[str, object]) -> bytes:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    if len(encoded) > MAX_FRAME_BYTES:
        raise ValueError("broker frame exceeds the maximum size")
    return struct.pack(">I", len(encoded)) + encoded


def _receive_exact(connection: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = connection.recv(min(remaining, 16_384))
        if not chunk:
            raise ConnectionError("broker socket closed before a complete frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _receive_frame(connection: socket.socket) -> dict[str, object]:
    header = _receive_exact(connection, 4)
    (size,) = struct.unpack(">I", header)
    if size < 2 or size > MAX_FRAME_BYTES:
        raise ValueError("broker frame length is outside the bounded protocol")
    payload = json.loads(_receive_exact(connection, size).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("broker frame must contain a JSON object")
    return payload


def _trace_id() -> str:
    return f"tr_{uuid.uuid4().hex}"


def _block_response(
    request: InfraRequest,
    reason_code: InfraReasonCode,
    *,
    required_capability: str | None = None,
    policy_revision: str = "unknown",
    broker_status: str = "unavailable",
    remediation_code: str = "INSPECT_BROKER_STATUS",
    task_id: str | None = None,
    run_id: str | None = None,
    source_manifest_digest: str | None = None,
) -> InfraResponse:
    required_capability = (
        required_capability
        or {
            InfraOperation.STATUS: "infra.broker.v1",
            InfraOperation.PROBE: "infra.ssh.probe.v1",
            InfraOperation.RSYNC_DRY_RUN: "infra.rsync.dry-run.v1",
            InfraOperation.REPLICATE: "infra.rsync.replicate.v1",
            InfraOperation.VERIFY: "infra.rsync.verify.v1",
        }[request.operation]
    )
    trace_id = _trace_id()
    payload = {
        "trace_id": trace_id,
        "operation": request.operation.value,
        "profile_id": request.profile or "unknown",
        "reason_code": reason_code.value,
        "required_capability": required_capability,
        "policy_revision": policy_revision,
        "broker_status": broker_status,
        "remediation_code": remediation_code,
        "task_id": task_id or request.task_id,
        "run_id": run_id,
        "source_manifest_digest": source_manifest_digest,
    }
    receipt = InfraCapabilityBlockReceipt(
        receipt_id=derive_receipt_id("ibr", payload),
        trace_id=trace_id,
        task_id=task_id or request.task_id,
        operation=request.operation,
        profile_id=request.profile or "unknown",
        reason_code=reason_code,
        required_capability=required_capability,
        policy_revision=policy_revision,
        broker_status=broker_status,
        remediation_code=remediation_code,
        recorded_at=utc_now(),
        run_id=run_id,
        source_manifest_digest=source_manifest_digest,
    )
    status = (
        InfraResponseStatus.AUTH_REQUIRED
        if reason_code == InfraReasonCode.APPROVAL_REQUIRED
        else InfraResponseStatus.BLOCKED
    )
    return InfraResponse(status=status, operation=request.operation, data={}, receipt=receipt)


class InfraBrokerClient:
    """Safe local client.  It never invokes SSH/rsync and never reads credentials."""

    def __init__(self, *, socket_path: Path | None = None, timeout_seconds: float = 10.0) -> None:
        self.socket_path = _safe_socket_path(
            socket_path or Path(os.getenv("POWER_INFRA_SOCKET", str(DEFAULT_SOCKET_PATH)))
        )
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("broker client timeout must be between 0 and 60 seconds")
        self.timeout_seconds = timeout_seconds

    def execute(self, request: InfraRequest) -> InfraResponse:
        """Send one bounded request over the configured Unix socket."""
        if not isinstance(request, InfraRequest):
            raise TypeError("broker client requires an InfraRequest")
        if request.operation != InfraOperation.STATUS and (
            not request.target or not request.profile
        ):
            return _block_response(
                request,
                InfraReasonCode.REQUEST_INPUT_MISSING,
                broker_status="input-required",
                remediation_code="PROVIDE_TARGET_AND_PROFILE",
            )
        if self.socket_path.is_symlink():
            return _block_response(
                request,
                InfraReasonCode.MISSING_EXECUTION_CAPABILITY,
                broker_status="broker-unavailable",
                remediation_code="REPAIR_SOCKET_BOUNDARY",
            )
        try:
            metadata = self.socket_path.lstat()
        except FileNotFoundError:
            return _block_response(
                request,
                InfraReasonCode.MISSING_EXECUTION_CAPABILITY,
                broker_status="broker-not-installed",
                remediation_code="INSTALL_ENABLE_BROKER",
            )
        except OSError:
            return _block_response(
                request,
                InfraReasonCode.MISSING_EXECUTION_CAPABILITY,
                broker_status="broker-unavailable",
                remediation_code="INSPECT_BROKER_STATUS",
            )
        if not stat.S_ISSOCK(metadata.st_mode):
            return _block_response(
                request,
                InfraReasonCode.MISSING_EXECUTION_CAPABILITY,
                broker_status="broker-unavailable",
                remediation_code="REPAIR_SOCKET_BOUNDARY",
            )

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout_seconds)
                connection.connect(str(self.socket_path))
                connection.sendall(_encode_frame(request.model_dump(mode="json")))
                response = InfraResponse.model_validate(_receive_frame(connection))
        except (ConnectionError, OSError, TimeoutError, ValueError, ValidationError):
            return _block_response(
                request,
                InfraReasonCode.PROTOCOL_ERROR,
                broker_status="broker-unavailable",
                remediation_code="INSPECT_BROKER_LOG",
            )
        return response

    def status(self) -> InfraResponse:
        """Return broker status without probing a remote target."""
        return self.execute(InfraRequest(operation=InfraOperation.STATUS))


class InfraBrokerServer:
    """Opt-in local broker that owns policy, credentials, and fixed execution."""

    def __init__(
        self,
        *,
        policy_path: Path = DEFAULT_POLICY_PATH,
        socket_path: Path = DEFAULT_SOCKET_PATH,
        state_dir: Path = DEFAULT_STATE_DIR,
        credential_dir: Path | None = None,
        approval_path: Path | None = None,
        authorized_uids: set[int] | None = None,
        authorized_gids: set[int] | None = None,
        command_runner: Callable[[list[str], int, int], _ProcessResult] | None = None,
        approval_registry: Mapping[str, Mapping[str, object]] | None = None,
    ) -> None:
        self.policy_path = Path(policy_path).expanduser()
        self.socket_path = _safe_socket_path(socket_path)
        self.state_dir = Path(state_dir).expanduser()
        configured_credential_dir = credential_dir or Path(
            os.getenv("CREDENTIALS_DIRECTORY") or "/run/credentials/power-infra-broker"
        )
        self.credential_dir = Path(configured_credential_dir).expanduser()
        _assert_no_symlink_components(self.credential_dir)
        if self.credential_dir.exists():
            _assert_secure_directory(self.credential_dir)
        self.authorized_uids = set(authorized_uids or set())
        self.authorized_gids = set(authorized_gids or set())
        self.command_runner = command_runner or _run_bounded_process
        self.approval_registry = dict(approval_registry or {})
        if approval_path is not None and Path(approval_path).exists():
            self.approval_registry.update(load_infra_approvals(Path(approval_path)))
        self._idempotency: dict[tuple[str, str], tuple[str, InfraResponse]] = {}
        self._reservations: dict[tuple[str, str], _Reservation] = {}
        self._known_runs: set[str] = set()
        self._dry_runs: set[tuple[str, str, str]] = set()
        self._load_idempotency()

    def peer_principal(self, connection: socket.socket) -> str:
        """Derive authorization identity from OS peer credentials, not JSON."""
        if hasattr(connection, "getsockopt") and hasattr(socket, "SO_PEERCRED"):
            raw = connection.getsockopt(socket.SOL_SOCKET, _PEER_CREDENTIALS, struct.calcsize("3i"))
            peer_pid, uid, gid = struct.unpack("3i", raw)
        elif hasattr(connection, "getpeereid"):  # pragma: no cover - BSD fallback
            peer_pid = 0
            uid, gid = connection.getpeereid()
        else:  # pragma: no cover - unsupported platform
            raise InfraBrokerError(
                InfraReasonCode.PRINCIPAL_DENIED,
                "UNSUPPORTED_PEER_CREDENTIALS",
                "principal-unavailable",
            )
        if self.authorized_uids and uid not in self.authorized_uids:
            raise InfraBrokerError(
                InfraReasonCode.PRINCIPAL_DENIED,
                "CALLER_UID_NOT_ALLOWED",
                "principal-denied",
            )
        peer_gids = {gid}
        if self.authorized_gids and peer_pid > 0:
            try:
                for line in (
                    Path(f"/proc/{peer_pid}/status")
                    .read_text(encoding="utf-8", errors="replace")
                    .splitlines()
                ):
                    if line.startswith("Groups:"):
                        peer_gids.update(int(value) for value in line.split()[1:])
                        break
            except (OSError, ValueError):
                pass
        if self.authorized_gids and not peer_gids.intersection(self.authorized_gids):
            raise InfraBrokerError(
                InfraReasonCode.PRINCIPAL_DENIED,
                "CALLER_GID_NOT_ALLOWED",
                "principal-denied",
            )
        if not self.authorized_uids and not self.authorized_gids:
            raise InfraBrokerError(
                InfraReasonCode.PRINCIPAL_DENIED,
                "CONFIGURE_CALLER_ALLOWLIST",
                "principal-denied",
            )
        return f"uid:{uid}"

    def handle_connection(self, connection: socket.socket) -> None:
        """Process one bounded connection and close it at the transport owner."""
        try:
            connection.settimeout(SERVER_IO_TIMEOUT_SECONDS)
            payload = _receive_frame(connection)
            try:
                request = InfraRequest.model_validate(payload)
            except (TypeError, ValueError, ValidationError):
                request = InfraRequest(operation=InfraOperation.STATUS)
                response = _block_response(
                    request,
                    InfraReasonCode.PROTOCOL_ERROR,
                    broker_status="invalid-request",
                    remediation_code="SEND_TYPED_REQUEST",
                )
            else:
                try:
                    principal_ref = self.peer_principal(connection)
                except InfraBrokerError as error:
                    response = _block_response(
                        request,
                        error.reason_code,
                        broker_status=error.broker_status,
                        remediation_code=error.remediation_code,
                        policy_revision=error.policy_revision,
                    )
                else:
                    response = self.handle_request(request, principal_ref=principal_ref)
            self._record_receipt(response)
            connection.sendall(_encode_frame(response.model_dump(mode="json")))
        except (ConnectionError, OSError, ValueError, ValidationError):
            return

    def _record_receipt(self, response: InfraResponse) -> None:
        """Append bounded secret-free receipt evidence when StateDirectory exists."""
        if not self.state_dir.exists():
            return
        try:
            if self.state_dir.is_symlink() or not self.state_dir.is_dir():
                return
            directory_mode = self.state_dir.stat().st_mode
            if directory_mode & 0o077:
                return
            receipt_path = self.state_dir / "receipts.jsonl"
            if receipt_path.exists():
                metadata = receipt_path.lstat()
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                    return
                if metadata.st_size >= _MAX_RECEIPT_LOG_BYTES:
                    return
            encoded = (
                json.dumps(response.receipt.model_dump(mode="json"), sort_keys=True) + "\n"
            ).encode("utf-8")
            if len(encoded) > MAX_FRAME_BYTES:
                return
            if (
                receipt_path.exists()
                and receipt_path.stat().st_size + len(encoded) > _MAX_RECEIPT_LOG_BYTES
            ):
                return
            flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(receipt_path, flags, 0o600)
            try:
                written = 0
                while written < len(encoded):
                    written += os.write(descriptor, encoded[written:])
            finally:
                os.close(descriptor)
        except OSError:
            logger.warning("INFRA-1 receipt persistence unavailable")

    def handle_request(self, request: InfraRequest, *, principal_ref: str) -> InfraResponse:
        """Execute one already-authenticated request without trusting payload identity."""
        if request.operation == InfraOperation.STATUS:
            return self._status_response(principal_ref)
        try:
            policy = load_infra_policy(self.policy_path)
        except (OSError, ValueError, json.JSONDecodeError):
            return _block_response(
                request,
                InfraReasonCode.POLICY_INVALID,
                broker_status="policy-invalid",
                remediation_code="REPAIR_OPERATOR_POLICY",
            )
        if not request.target or not request.profile:
            return _block_response(
                request,
                InfraReasonCode.REQUEST_INPUT_MISSING,
                policy_revision="unknown",
                broker_status="input-required",
                remediation_code="PROVIDE_TARGET_AND_PROFILE",
            )
        profile = next(
            (item for item in policy.profiles if item.profile_id == request.profile), None
        )
        if profile is None:
            return _block_response(
                request,
                InfraReasonCode.PROFILE_NOT_FOUND,
                policy_revision="unknown",
                broker_status="profile-missing",
                remediation_code="INSTALL_OPERATOR_PROFILE",
            )
        if profile.target_id != request.target:
            return _block_response(
                request,
                InfraReasonCode.TARGET_NOT_ALLOWED,
                policy_revision=profile.policy_revision,
                broker_status="target-not-allowed",
                remediation_code="SELECT_APPROVED_TARGET",
            )
        if request.operation == InfraOperation.REPLICATE and request.idempotency_key:
            key = (principal_ref, idempotency_key_reference(request.idempotency_key) or "")
            existing = self._idempotency.get(key)
            request_digest = self._request_digest(request, profile.policy_revision)
            if existing is not None:
                prior_digest, prior_response = existing
                if prior_digest != request_digest:
                    return _block_response(
                        request,
                        InfraReasonCode.IDEMPOTENCY_CONFLICT,
                        policy_revision=profile.policy_revision,
                        broker_status="idempotency-conflict",
                        remediation_code="ISSUE_NEW_IDEMPOTENCY_KEY",
                    )
                return prior_response.model_copy(
                    update={"data": {**prior_response.data, "replay": True}}
                )
            reservation = self._reservations.get(key)
            if reservation is not None:
                if reservation.request_digest != request_digest:
                    return _block_response(
                        request,
                        InfraReasonCode.IDEMPOTENCY_CONFLICT,
                        policy_revision=profile.policy_revision,
                        broker_status="idempotency-conflict",
                        remediation_code="ISSUE_NEW_IDEMPOTENCY_KEY",
                    )
                return _block_response(
                    request,
                    InfraReasonCode.OPERATION_IN_FLIGHT,
                    policy_revision=reservation.policy_revision,
                    broker_status="operation-in-flight",
                    remediation_code="VERIFY_EXISTING_RUN_BEFORE_RETRY",
                    run_id=reservation.run_id,
                    source_manifest_digest=reservation.source_manifest_digest,
                )
        if request.operation not in profile.allowed_operations:
            return _block_response(
                request,
                InfraReasonCode.CAPABILITY_DISABLED,
                policy_revision=profile.policy_revision,
                broker_status="profile-operation-disabled",
                remediation_code="REQUEST_OPERATOR_PROFILE_CHANGE",
            )
        if request.operation == InfraOperation.VERIFY and request.run_id not in self._known_runs:
            return _block_response(
                request,
                InfraReasonCode.RUN_NOT_FOUND,
                policy_revision=profile.policy_revision,
                broker_status="run-not-found",
                remediation_code="RESOLVE_OPERATOR_RUN_RECEIPT",
            )
        try:
            credential_file = self._credential_file(profile)
            self._assert_pinned_host_key(profile)
            approval_ref = self._validate_approval(request, profile, principal_ref)
            manifest = (
                self._build_manifest(profile) if request.operation != InfraOperation.PROBE else None
            )
            if request.operation == InfraOperation.REPLICATE:
                assert manifest is not None
                if (
                    profile.dry_run_policy == "required"
                    and (
                        profile.profile_id,
                        profile.policy_revision,
                        manifest.digest,
                    )
                    not in self._dry_runs
                ):
                    return _block_response(
                        request,
                        InfraReasonCode.DRY_RUN_REQUIRED,
                        policy_revision=profile.policy_revision,
                        broker_status="dry-run-required",
                        remediation_code="RUN_RSYNC_DRY_RUN",
                    )
                reservation = self._reserve_idempotency(
                    principal_ref,
                    request,
                    profile.policy_revision,
                    manifest,
                )
            else:
                reservation = None
            response = self._execute_operation(
                request,
                profile,
                principal_ref=principal_ref,
                credential_file=credential_file,
                manifest=manifest,
                approval_ref=approval_ref,
                run_id_override=reservation.run_id if reservation else None,
            )
            if request.operation == InfraOperation.REPLICATE and request.idempotency_key:
                self._remember_idempotency(
                    principal_ref,
                    request,
                    profile.policy_revision,
                    response,
                )
            return response
        except InfraBrokerError as error:
            return _block_response(
                request,
                error.reason_code,
                policy_revision=error.policy_revision or profile.policy_revision,
                broker_status=error.broker_status,
                remediation_code=error.remediation_code,
            )

    def _status_response(self, principal_ref: str) -> InfraResponse:
        try:
            policy = load_infra_policy(self.policy_path)
        except (OSError, ValueError, json.JSONDecodeError):
            request = InfraRequest(operation=InfraOperation.STATUS)
            return _block_response(
                request,
                InfraReasonCode.POLICY_INVALID,
                broker_status="policy-invalid",
                remediation_code="REPAIR_OPERATOR_POLICY",
            )
        ready_profiles: list[str] = []
        missing_credentials: list[str] = []
        for profile in policy.profiles:
            try:
                self._credential_file(profile)
                self._assert_pinned_host_key(profile)
            except InfraBrokerError:
                missing_credentials.append(profile.profile_id)
            else:
                ready_profiles.append(profile.profile_id)
        request = InfraRequest(operation=InfraOperation.STATUS)
        return self._operation_response(
            request,
            principal_ref=principal_ref,
            policy_revision="multi"
            if len(policy.profiles) != 1
            else policy.profiles[0].policy_revision,
            data={
                "broker_status": "active",
                "profiles": [profile.profile_id for profile in policy.profiles],
                "ready_profiles": ready_profiles,
                "profiles_needing_operator_attention": missing_credentials,
            },
            exit_category=InfraExitCategory.SUCCESS,
            transport="unix",
            dry_run=True,
        )

    def _credential_file(self, profile: InfraProfile) -> Path:
        if self.credential_dir.is_symlink():
            raise InfraBrokerError(
                InfraReasonCode.BROKER_CREDENTIAL_UNAVAILABLE,
                "REPAIR_CREDENTIAL_DIRECTORY",
                "credential-unavailable",
                policy_revision=profile.policy_revision,
            )
        candidate = self.credential_dir / profile.credential_id
        _assert_no_symlink_components(candidate)
        try:
            candidate.resolve().relative_to(self.credential_dir.resolve())
        except ValueError as exc:
            raise InfraBrokerError(
                InfraReasonCode.BROKER_CREDENTIAL_UNAVAILABLE,
                "REPAIR_CREDENTIAL_MAPPING",
                "credential-unavailable",
                policy_revision=profile.policy_revision,
            ) from exc
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise InfraBrokerError(
                InfraReasonCode.BROKER_CREDENTIAL_UNAVAILABLE,
                "INSTALL_BROKER_CREDENTIAL",
                "credential-unavailable",
                policy_revision=profile.policy_revision,
            ) from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise InfraBrokerError(
                InfraReasonCode.BROKER_CREDENTIAL_UNAVAILABLE,
                "REPAIR_CREDENTIAL_FILE",
                "credential-unavailable",
                policy_revision=profile.policy_revision,
            )
        if metadata.st_mode & 0o077:
            raise InfraBrokerError(
                InfraReasonCode.BROKER_CREDENTIAL_UNAVAILABLE,
                "REPAIR_CREDENTIAL_PERMISSIONS",
                "credential-unavailable",
                policy_revision=profile.policy_revision,
            )
        return candidate

    def _assert_pinned_host_key(self, profile: InfraProfile) -> None:
        path = Path(profile.known_hosts_file)
        try:
            content = _assert_regular_operator_file(path, max_bytes=1_000_000).decode("utf-8")
        except (OSError, UnicodeError, ValueError) as exc:
            raise InfraBrokerError(
                InfraReasonCode.HOST_IDENTITY_UNTRUSTED,
                "INSTALL_OPERATOR_HOST_KEY_PIN",
                "host-identity-untrusted",
                policy_revision=profile.policy_revision,
            ) from exc
        expected_hosts = {profile.hostname, f"[{profile.hostname}]:{profile.port}"}
        for line in content.splitlines():
            fields = line.strip().split()
            if len(fields) < 3 or fields[0].startswith(("#", "@", "|1|")):
                continue
            if not any(host in expected_hosts for host in fields[0].split(",")):
                continue
            try:
                blob = b64decode(fields[2], validate=True)
            except (ValueError, TypeError):
                continue
            if ssh_fingerprint_from_blob(blob) == profile.host_key_fingerprint:
                return
        raise InfraBrokerError(
            InfraReasonCode.HOST_IDENTITY_UNTRUSTED,
            "PIN_APPROVED_HOST_KEY",
            "host-identity-untrusted",
            policy_revision=profile.policy_revision,
        )

    def _validate_approval(
        self,
        request: InfraRequest,
        profile: InfraProfile,
        principal_ref: str,
    ) -> str | None:
        if request.operation != InfraOperation.REPLICATE:
            return None
        if profile.approval_policy == "standing":
            if profile.standing_principal_ref != principal_ref:
                raise InfraBrokerError(
                    InfraReasonCode.APPROVAL_REQUIRED,
                    "USE_OPERATOR_INSTALLED_APPROVAL_FOR_PRINCIPAL",
                    "auth-required",
                    policy_revision=profile.policy_revision,
                )
            if request.approval_ref and request.approval_ref != profile.standing_approval_ref:
                raise InfraBrokerError(
                    InfraReasonCode.APPROVAL_REQUIRED,
                    "USE_OPERATOR_INSTALLED_APPROVAL",
                    "auth-required",
                    policy_revision=profile.policy_revision,
                )
            return profile.standing_approval_ref
        if not request.approval_ref:
            raise InfraBrokerError(
                InfraReasonCode.APPROVAL_REQUIRED,
                "REQUEST_EXACT_PROFILE_APPROVAL",
                "auth-required",
                policy_revision=profile.policy_revision,
            )
        record = self.approval_registry.get(request.approval_ref)
        if record is None:
            raise InfraBrokerError(
                InfraReasonCode.APPROVAL_REQUIRED,
                "RESOLVE_OPERATOR_APPROVAL",
                "auth-required",
                policy_revision=profile.policy_revision,
            )
        expected = {
            "operation": request.operation.value,
            "target_id": profile.target_id,
            "profile_id": profile.profile_id,
            "policy_revision": profile.policy_revision,
            "principal_ref": principal_ref,
        }
        try:
            expires_at = datetime.fromisoformat(str(record.get("expires_at")))
            if expires_at.tzinfo is None or expires_at.astimezone(UTC) <= datetime.now(UTC):
                raise ValueError("approval expired")
        except (TypeError, ValueError, OverflowError):
            raise InfraBrokerError(
                InfraReasonCode.APPROVAL_REQUIRED,
                "REISSUE_EXPIRED_APPROVAL",
                "auth-required",
                policy_revision=profile.policy_revision,
            ) from None
        if any(record.get(key) != value for key, value in expected.items()):
            raise InfraBrokerError(
                InfraReasonCode.APPROVAL_REQUIRED,
                "REISSUE_EXACT_PROFILE_APPROVAL",
                "auth-required",
                policy_revision=profile.policy_revision,
            )
        return request.approval_ref

    def _build_manifest(self, profile: InfraProfile) -> _Manifest:
        entries: list[dict[str, object]] = []
        total_bytes = 0
        for root_index, root_text in enumerate(profile.source_roots):
            root = Path(root_text)
            try:
                _assert_no_symlink_components(root)
            except ValueError as exc:
                raise InfraBrokerError(
                    InfraReasonCode.POLICY_INVALID,
                    "REPAIR_SOURCE_ROOT",
                    "profile-invalid",
                    policy_revision=profile.policy_revision,
                ) from exc
            if root.is_symlink() or not root.is_dir():
                raise InfraBrokerError(
                    InfraReasonCode.POLICY_INVALID,
                    "REPAIR_SOURCE_ROOT",
                    "profile-invalid",
                    policy_revision=profile.policy_revision,
                )
            for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
                for dirname in list(dirnames):
                    if Path(current, dirname).is_symlink():
                        raise InfraBrokerError(
                            InfraReasonCode.RESOURCE_LIMIT,
                            "REMOVE_SOURCE_SYMLINK",
                            "source-invalid",
                            policy_revision=profile.policy_revision,
                        )
                for filename in sorted(filenames):
                    candidate = Path(current, filename)
                    metadata = candidate.lstat()
                    if (
                        stat.S_ISLNK(metadata.st_mode)
                        or not stat.S_ISREG(metadata.st_mode)
                        or metadata.st_nlink != 1
                    ):
                        raise InfraBrokerError(
                            InfraReasonCode.RESOURCE_LIMIT,
                            "REMOVE_SOURCE_SPECIAL_FILE",
                            "source-invalid",
                            policy_revision=profile.policy_revision,
                        )
                    relative = candidate.relative_to(root).as_posix()
                    if (
                        not relative
                        or relative.startswith("-")
                        or any(ord(char) < 32 for char in relative)
                    ):
                        raise InfraBrokerError(
                            InfraReasonCode.RESOURCE_LIMIT,
                            "RENAME_UNSAFE_SOURCE_PATH",
                            "source-invalid",
                            policy_revision=profile.policy_revision,
                        )
                    total_bytes += metadata.st_size
                    if total_bytes > profile.max_bytes:
                        raise InfraBrokerError(
                            InfraReasonCode.RESOURCE_LIMIT,
                            "LOWER_SOURCE_SIZE_OR_SPLIT_RUN",
                            "resource-limit",
                            policy_revision=profile.policy_revision,
                        )
                    if len(entries) >= profile.max_files:
                        raise InfraBrokerError(
                            InfraReasonCode.RESOURCE_LIMIT,
                            "LOWER_SOURCE_FILE_COUNT_OR_SPLIT_RUN",
                            "resource-limit",
                            policy_revision=profile.policy_revision,
                        )
                    digest = hashlib.sha256()
                    with candidate.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(64 * 1024), b""):
                            digest.update(chunk)
                    entries.append(
                        {
                            "root": root_index,
                            "path": relative,
                            "size": metadata.st_size,
                            "sha256": digest.hexdigest(),
                        }
                    )
        serialized = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return _Manifest(
            digest=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            file_count=len(entries),
            byte_count=total_bytes,
        )

    def _execute_operation(
        self,
        request: InfraRequest,
        profile: InfraProfile,
        *,
        principal_ref: str,
        credential_file: Path,
        manifest: _Manifest | None,
        approval_ref: str | None,
        run_id_override: str | None = None,
    ) -> InfraResponse:
        if request.operation == InfraOperation.PROBE:
            argv = [
                SSH_BINARY,
                *build_ssh_options(
                    hostname=profile.hostname,
                    port=profile.port,
                    username=profile.remote_user,
                    known_hosts_file=Path(profile.known_hosts_file),
                    credential_file=credential_file,
                ),
                f"{profile.remote_user}@{profile.hostname}",
            ]
            result = self.command_runner(argv, profile.timeout_seconds, profile.max_output_bytes)
            if result.category != InfraExitCategory.SUCCESS or result.returncode != 0:
                return self._failed_response(
                    request,
                    profile,
                    principal_ref=principal_ref,
                    approval_ref=approval_ref,
                    manifest=manifest,
                    result=result,
                )
            return self._operation_response(
                request,
                principal_ref=principal_ref,
                policy_revision=profile.policy_revision,
                target_id=profile.target_id,
                profile_id=profile.profile_id,
                approval_ref=approval_ref,
                host_key_fingerprint=profile.host_key_fingerprint,
                credential_id=profile.credential_id,
                data={"reachable": True},
                exit_category=result.category,
                transport="ssh-rsync",
                dry_run=True,
                duration_ms=result.duration_ms,
            )

        assert manifest is not None
        dry_run = request.operation == InfraOperation.RSYNC_DRY_RUN
        run_id = (
            run_id_override
            or request.run_id
            or (
                f"run_{uuid.uuid4().hex}"
                if request.operation in {InfraOperation.RSYNC_DRY_RUN, InfraOperation.REPLICATE}
                else None
            )
        )
        if run_id is None:
            raise InfraBrokerError(
                InfraReasonCode.REQUEST_INPUT_MISSING,
                "PROVIDE_RUN_ID",
                "input-required",
                policy_revision=profile.policy_revision,
            )
        aggregate_duration = 0
        aggregate_result: _ProcessResult | None = None
        for root_index, source_root in enumerate(profile.source_roots):
            destination = (
                f"{profile.remote_user}@{profile.hostname}:"
                f"{profile.remote_root}/runs/{run_id}/source-{root_index}/"
            )
            argv = [
                RSYNC_BINARY,
                "-rt",
                "--stats",
                "--no-links",
                "--no-devices",
                "--no-specials",
            ]
            if dry_run or request.operation == InfraOperation.VERIFY:
                argv.append("--dry-run")
            if request.operation == InfraOperation.VERIFY:
                argv.append("--checksum")
                argv.extend(["--itemize-changes", "--out-format=%i"])
            argv.extend(
                [
                    "--rsh",
                    _build_ssh_command(profile, credential_file),
                    f"{source_root.rstrip('/')}/",
                    destination,
                ]
            )
            result = self.command_runner(argv, profile.timeout_seconds, profile.max_output_bytes)
            aggregate_duration += result.duration_ms
            aggregate_result = result
            if result.category != InfraExitCategory.SUCCESS or result.returncode != 0:
                return self._failed_response(
                    request,
                    profile,
                    principal_ref=principal_ref,
                    approval_ref=approval_ref,
                    manifest=manifest,
                    result=result,
                    run_id=run_id,
                    duration_ms=aggregate_duration,
                )
        if request.operation == InfraOperation.RSYNC_DRY_RUN:
            self._dry_runs.add((profile.profile_id, profile.policy_revision, manifest.digest))
        assert aggregate_result is not None
        if request.operation == InfraOperation.VERIFY and not _rsync_verification_is_clean(
            aggregate_result
        ):
            return self._operation_response(
                request,
                principal_ref=principal_ref,
                policy_revision=profile.policy_revision,
                target_id=profile.target_id,
                profile_id=profile.profile_id,
                source_manifest_digest=manifest.digest,
                host_key_fingerprint=profile.host_key_fingerprint,
                credential_id=profile.credential_id,
                run_id=run_id,
                data={
                    "run_id": run_id,
                    "file_count": manifest.file_count,
                    "byte_count": manifest.byte_count,
                    "policy_revision": profile.policy_revision,
                    "dry_run": True,
                    "verification": "rsync-dry-run-mismatch",
                },
                exit_category=InfraExitCategory.FAILED,
                transport="ssh-rsync",
                dry_run=True,
                file_count=manifest.file_count,
                byte_count=manifest.byte_count,
                duration_ms=aggregate_duration,
                verification_result="rsync-dry-run-mismatch",
            )
        return self._operation_response(
            request,
            principal_ref=principal_ref,
            policy_revision=profile.policy_revision,
            target_id=profile.target_id,
            profile_id=profile.profile_id,
            approval_ref=approval_ref,
            source_manifest_digest=manifest.digest,
            host_key_fingerprint=profile.host_key_fingerprint,
            credential_id=profile.credential_id,
            run_id=run_id,
            data={
                "run_id": run_id,
                "file_count": manifest.file_count,
                "byte_count": manifest.byte_count,
                "policy_revision": profile.policy_revision,
                "dry_run": request.operation == InfraOperation.RSYNC_DRY_RUN
                or request.operation == InfraOperation.VERIFY,
                "verification": "rsync-dry-run-clean"
                if request.operation == InfraOperation.VERIFY
                else "dry-run-passed"
                if request.operation == InfraOperation.RSYNC_DRY_RUN
                else "replicated-to-immutable-run",
            },
            exit_category=InfraExitCategory.SUCCESS,
            transport="ssh-rsync",
            dry_run=request.operation in {InfraOperation.RSYNC_DRY_RUN, InfraOperation.VERIFY},
            file_count=manifest.file_count,
            byte_count=manifest.byte_count,
            duration_ms=aggregate_duration,
            verification_result=(
                "rsync-dry-run-clean" if request.operation == InfraOperation.VERIFY else None
            ),
        )

    def _failed_response(
        self,
        request: InfraRequest,
        profile: InfraProfile,
        *,
        principal_ref: str,
        approval_ref: str | None,
        manifest: _Manifest | None,
        result: _ProcessResult,
        run_id: str | None = None,
        duration_ms: int | None = None,
    ) -> InfraResponse:
        reason = {
            InfraExitCategory.HOST_IDENTITY_MISMATCH: InfraReasonCode.HOST_IDENTITY_MISMATCH,
            InfraExitCategory.HOST_IDENTITY_UNTRUSTED: InfraReasonCode.HOST_IDENTITY_UNTRUSTED,
            InfraExitCategory.NETWORK_UNAVAILABLE: InfraReasonCode.NETWORK_UNAVAILABLE,
            InfraExitCategory.TIMEOUT: InfraReasonCode.TIMEOUT,
        }.get(result.category, InfraReasonCode.OPERATION_FAILED)
        if reason in {
            InfraReasonCode.HOST_IDENTITY_MISMATCH,
            InfraReasonCode.HOST_IDENTITY_UNTRUSTED,
            InfraReasonCode.NETWORK_UNAVAILABLE,
            InfraReasonCode.TIMEOUT,
        }:
            return _block_response(
                request,
                reason,
                policy_revision=profile.policy_revision,
                broker_status=result.category.value,
                remediation_code={
                    InfraReasonCode.HOST_IDENTITY_MISMATCH: "OPERATOR_ROTATE_PIN",
                    InfraReasonCode.HOST_IDENTITY_UNTRUSTED: "OPERATOR_PIN_HOST_KEY",
                    InfraReasonCode.NETWORK_UNAVAILABLE: "CHECK_APPROVED_TARGET_NETWORK",
                    InfraReasonCode.TIMEOUT: "INSPECT_BROKER_LOG_AND_RESOLVE_RUN",
                }[reason],
                run_id=run_id,
                source_manifest_digest=manifest.digest if manifest else None,
            )
        return self._operation_response(
            request,
            principal_ref=principal_ref,
            policy_revision=profile.policy_revision,
            target_id=profile.target_id,
            profile_id=profile.profile_id,
            approval_ref=approval_ref,
            source_manifest_digest=manifest.digest if manifest else None,
            host_key_fingerprint=profile.host_key_fingerprint,
            credential_id=profile.credential_id,
            run_id=run_id,
            data={"file_count": manifest.file_count if manifest else 0},
            exit_category=result.category,
            transport="ssh-rsync",
            dry_run=request.operation != InfraOperation.REPLICATE,
            file_count=manifest.file_count if manifest else 0,
            byte_count=manifest.byte_count if manifest else 0,
            duration_ms=duration_ms if duration_ms is not None else result.duration_ms,
        )

    def _operation_response(
        self,
        request: InfraRequest,
        *,
        principal_ref: str,
        policy_revision: str,
        data: dict[str, Any],
        exit_category: InfraExitCategory,
        transport: str,
        dry_run: bool,
        target_id: str | None = None,
        profile_id: str | None = None,
        approval_ref: str | None = None,
        source_manifest_digest: str | None = None,
        host_key_fingerprint: str | None = None,
        credential_id: str | None = None,
        run_id: str | None = None,
        file_count: int = 0,
        byte_count: int = 0,
        duration_ms: int = 0,
        verification_result: str | None = None,
    ) -> InfraResponse:
        trace_id = _trace_id()
        payload = {
            "trace_id": trace_id,
            "operation": request.operation.value,
            "target_id": target_id,
            "profile_id": profile_id,
            "policy_revision": policy_revision,
            "principal_ref": principal_ref,
            "run_id": run_id,
            "source_manifest_digest": source_manifest_digest,
            "exit_category": exit_category.value,
        }
        receipt = InfraOperationReceipt(
            receipt_id=derive_receipt_id("ir", payload),
            trace_id=trace_id,
            task_id=request.task_id,
            operation=request.operation,
            target_id=target_id,
            profile_id=profile_id,
            policy_revision=policy_revision,
            principal_ref=principal_ref,
            approval_ref=approval_ref,
            source_manifest_digest=source_manifest_digest,
            host_key_fingerprint=host_key_fingerprint,
            credential_id=credential_id,
            transport=transport,  # type: ignore[arg-type]
            run_id=run_id,
            dry_run=dry_run,
            file_count=file_count,
            byte_count=byte_count,
            duration_ms=duration_ms,
            exit_category=exit_category,
            verification_result=verification_result,
            idempotency_key_ref=idempotency_key_reference(request.idempotency_key),
            recorded_at=utc_now(),
        )
        data = {
            **data,
            "receipt_id": receipt.receipt_id,
            "trace_id": trace_id,
            "policy_revision": policy_revision,
        }
        return InfraResponse(
            status=InfraResponseStatus.OK
            if exit_category in {InfraExitCategory.SUCCESS, InfraExitCategory.REPLAY}
            else InfraResponseStatus.FAILED,
            operation=request.operation,
            data=data,
            receipt=receipt,
        )

    @staticmethod
    def _request_digest(request: InfraRequest, policy_revision: str) -> str:
        canonical = json.dumps(
            {"request": request.model_dump(mode="json"), "policy_revision": policy_revision},
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _load_idempotency(self) -> None:
        """Load bounded secret-free replay records from the operator state dir."""
        if not self.state_dir.exists():
            return
        if self.state_dir.is_symlink() or not self.state_dir.is_dir():
            raise ValueError("broker state directory must be a regular directory")
        if self.state_dir.stat().st_mode & 0o077:
            raise ValueError("broker state directory must not be group/world accessible")
        path = self.state_dir / "idempotency.json"
        if not path.exists():
            return
        try:
            payload = json.loads(_assert_regular_operator_file(path).decode("utf-8"))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("broker idempotency state is invalid") from exc
        if not isinstance(payload, list) or len(payload) > _MAX_IDEMPOTENCY_RECORDS:
            raise ValueError("broker idempotency state exceeds its bound")
        for record in payload:
            if not isinstance(record, dict):
                raise ValueError("broker idempotency record is invalid")
            principal_ref = record.get("principal_ref")
            key_ref = record.get("idempotency_key_ref")
            digest = record.get("request_digest")
            response_payload = record.get("response")
            if (
                not isinstance(principal_ref, str)
                or not isinstance(key_ref, str)
                or not isinstance(digest, str)
            ):
                raise ValueError("broker idempotency record is incomplete")
            if record.get("status", "completed") == "in-flight":
                run_id = record.get("run_id")
                manifest_digest = record.get("source_manifest_digest")
                policy_revision = record.get("policy_revision")
                if not all(
                    isinstance(value, str) for value in (run_id, manifest_digest, policy_revision)
                ):
                    raise ValueError("broker reservation record is incomplete")
                self._reservations[(principal_ref, key_ref)] = _Reservation(
                    request_digest=digest,
                    run_id=cast("str", run_id),
                    source_manifest_digest=cast("str", manifest_digest),
                    policy_revision=cast("str", policy_revision),
                )
                continue
            if record.get("status", "completed") != "completed" or not isinstance(
                response_payload, dict
            ):
                raise ValueError("broker idempotency record has an unknown status")
            response = InfraResponse.model_validate(response_payload)
            self._idempotency[(principal_ref, key_ref)] = (
                digest,
                response,
            )
            if response.receipt.run_id:
                self._known_runs.add(response.receipt.run_id)

    def _remember_idempotency(
        self,
        principal_ref: str,
        request: InfraRequest,
        policy_revision: str,
        response: InfraResponse,
    ) -> None:
        key_ref = idempotency_key_reference(request.idempotency_key)
        if key_ref is None:
            return
        key = (principal_ref, key_ref)
        reservation = self._reservations.pop(key, None)
        self._idempotency[(principal_ref, key_ref)] = (
            self._request_digest(request, policy_revision),
            response,
        )
        if response.receipt.run_id:
            self._known_runs.add(response.receipt.run_id)
        try:
            self._persist_idempotency()
        except (OSError, ValueError):
            self._idempotency.pop(key, None)
            if reservation is not None:
                self._reservations[key] = reservation
            logger.warning("INFRA-1 idempotency completion persistence unavailable")

    def _reserve_idempotency(
        self,
        principal_ref: str,
        request: InfraRequest,
        policy_revision: str,
        manifest: _Manifest,
    ) -> _Reservation:
        key_ref = idempotency_key_reference(request.idempotency_key)
        if key_ref is None:
            raise InfraBrokerError(
                InfraReasonCode.IDEMPOTENCY_CONFLICT,
                "ISSUE_IDEMPOTENCY_KEY",
                "idempotency-unavailable",
                policy_revision=policy_revision,
            )
        if len(self._idempotency) + len(self._reservations) >= _MAX_IDEMPOTENCY_RECORDS:
            raise InfraBrokerError(
                InfraReasonCode.RESOURCE_LIMIT,
                "RESOLVE_OLD_IDEMPOTENCY_RECORDS",
                "idempotency-capacity-exhausted",
                policy_revision=policy_revision,
            )
        request_digest = self._request_digest(request, policy_revision)
        run_digest = hashlib.sha256(
            f"{principal_ref}:{key_ref}:{request_digest}".encode()
        ).hexdigest()
        reservation = _Reservation(
            request_digest=request_digest,
            run_id=f"run_{run_digest[:32]}",
            source_manifest_digest=manifest.digest,
            policy_revision=policy_revision,
        )
        key = (principal_ref, key_ref)
        self._reservations[key] = reservation
        try:
            self._persist_idempotency()
        except (OSError, ValueError) as exc:
            self._reservations.pop(key, None)
            raise InfraBrokerError(
                InfraReasonCode.OPERATION_FAILED,
                "REPAIR_IDEMPOTENCY_STATE",
                "idempotency-unavailable",
                policy_revision=policy_revision,
            ) from exc
        return reservation

    def _persist_idempotency(self) -> None:
        if not self.state_dir.exists():
            self.state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        _assert_secure_directory(self.state_dir)
        records: list[dict[str, object]] = []
        records.extend(
            {
                "status": "in-flight",
                "principal_ref": principal,
                "idempotency_key_ref": key_ref,
                "request_digest": reservation.request_digest,
                "run_id": reservation.run_id,
                "source_manifest_digest": reservation.source_manifest_digest,
                "policy_revision": reservation.policy_revision,
            }
            for (principal, key_ref), reservation in self._reservations.items()
        )
        records.extend(
            {
                "status": "completed",
                "principal_ref": principal,
                "idempotency_key_ref": key_ref,
                "request_digest": digest,
                "response": stored_response.model_dump(mode="json"),
            }
            for (principal, key_ref), (digest, stored_response) in self._idempotency.items()
        )
        if len(records) > _MAX_IDEMPOTENCY_RECORDS:
            raise ValueError("broker idempotency state exceeds its bound")
        payload = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        encoded = payload.encode("utf-8")
        if len(encoded) > _MAX_RECEIPT_LOG_BYTES:
            raise ValueError("broker idempotency state exceeds its byte bound")
        path = self.state_dir / "idempotency.json"
        temporary = self.state_dir / f"idempotency.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            written = 0
            while written < len(encoded):
                written += os.write(descriptor, encoded[written:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        directory_descriptor = os.open(self.state_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)


def _run_bounded_process(
    argv: list[str], timeout_seconds: int, max_output_bytes: int = 1_000_000
) -> _ProcessResult:
    """Run a fixed argv with bounded I/O, timeout, and no inherited credentials."""
    started = time.perf_counter()
    environment = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "HOME": "/nonexistent",
    }
    try:
        process = subprocess.Popen(  # noqa: S603 - argv is broker-generated and shell=False
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            shell=False,
            start_new_session=True,
        )
    except FileNotFoundError:
        return _ProcessResult(
            returncode=None,
            stdout_bytes=0,
            stderr_bytes=0,
            category=InfraExitCategory.PROCESS_UNAVAILABLE,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    except OSError:
        return _ProcessResult(
            returncode=None,
            stdout_bytes=0,
            stderr_bytes=0,
            category=InfraExitCategory.FAILED,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    selector = selectors.DefaultSelector()
    assert process.stdout is not None
    assert process.stderr is not None
    selector.register(process.stdout, selectors.EVENT_READ)
    selector.register(process.stderr, selectors.EVENT_READ)
    stdout_bytes = 0
    stderr_bytes = 0
    stdout_sample = bytearray()
    stderr_sample = bytearray()
    deadline = started + timeout_seconds
    timed_out = False
    output_limited = False
    try:
        while selector.get_map():
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                timed_out = True
                break
            for key, _ in selector.select(timeout=min(remaining, 0.25)):
                chunk = os.read(key.fd, 16_384)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if key.fileobj is process.stdout:
                    stdout_bytes += len(chunk)
                    if len(stdout_sample) < 65_536:
                        stdout_sample.extend(chunk[: 65_536 - len(stdout_sample)])
                else:
                    stderr_bytes += len(chunk)
                    if len(stderr_sample) < 4096:
                        stderr_sample.extend(chunk[: 4096 - len(stderr_sample)])
                if stdout_bytes + stderr_bytes > max_output_bytes:
                    output_limited = True
                    break
            if timed_out or output_limited:
                break
        if timed_out or output_limited:
            with suppress(OSError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                with suppress(OSError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=1)
        else:
            process.wait(timeout=max(0.1, deadline - time.perf_counter()))
    except subprocess.TimeoutExpired:
        timed_out = True
        with suppress(OSError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=1)
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()

    category = (
        InfraExitCategory.TIMEOUT
        if timed_out
        else InfraExitCategory.OUTPUT_LIMIT
        if output_limited
        else InfraExitCategory.SUCCESS
        if process.returncode == 0
        else InfraExitCategory.FAILED
    )
    if category == InfraExitCategory.FAILED:
        category = _classify_process_failure(bytes(stderr_sample))
    return _ProcessResult(
        returncode=process.returncode,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        category=category,
        duration_ms=int((time.perf_counter() - started) * 1000),
        stdout_sample=bytes(stdout_sample),
    )


def _classify_process_failure(stderr_sample: bytes) -> InfraExitCategory:
    """Map bounded SSH/rsync diagnostics to categories without exposing text."""
    message = stderr_sample.decode("utf-8", errors="replace").casefold()
    if (
        "host key verification failed" in message
        or "remote host identification has changed" in message
    ):
        return InfraExitCategory.HOST_IDENTITY_MISMATCH
    if "no matching host key type" in message or "known_hosts" in message:
        return InfraExitCategory.HOST_IDENTITY_UNTRUSTED
    if any(
        marker in message
        for marker in (
            "could not resolve hostname",
            "connection timed out",
            "connection refused",
            "no route to host",
            "network is unreachable",
            "connection reset",
        )
    ):
        return InfraExitCategory.NETWORK_UNAVAILABLE
    if "permission denied" in message or "access denied" in message:
        return InfraExitCategory.REMOTE_REJECTED
    return InfraExitCategory.FAILED


def _rsync_verification_is_clean(result: _ProcessResult) -> bool:
    """Interpret only bounded itemized rsync output, never return its paths."""
    ignored_prefixes = (
        "sending ",
        "receiving ",
        "sent ",
        "received ",
        "total size is ",
        "number of files:",
        "total file size:",
        "total transferred file size:",
        "created directory ",
    )
    for raw_line in result.stdout_sample.decode("utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.casefold().startswith(ignored_prefixes):
            continue
        if len(line) > 11 and line[0] in "<>ch*":
            return False
    return True


def broker_main(argv: list[str] | None = None) -> None:
    """Run the opt-in broker daemon; installation/enablement remains operator-owned."""
    import argparse

    parser = argparse.ArgumentParser(prog="power-infra-broker")
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve", help="Run the local Unix-socket broker")
    serve.add_argument("--policy", default=str(DEFAULT_POLICY_PATH))
    serve.add_argument("--socket", default=str(DEFAULT_SOCKET_PATH))
    serve.add_argument("--state", default=str(DEFAULT_STATE_DIR))
    serve.add_argument("--approvals", default=str(DEFAULT_APPROVAL_PATH))
    args = parser.parse_args(argv)
    if args.command != "serve":
        raise SystemExit(2)
    server = InfraBrokerServer(
        policy_path=Path(args.policy),
        socket_path=Path(args.socket),
        state_dir=Path(args.state),
        approval_path=Path(args.approvals) if Path(args.approvals).exists() else None,
        authorized_gids={os.getgid(), *os.getgroups()},
    )
    socket_path = _safe_socket_path(server.socket_path)
    if socket_path.exists():
        raise RuntimeError("refusing to replace an existing broker socket")
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(socket_path))
        os.chmod(socket_path, 0o660)
        listener.listen(8)
        while True:
            connection, _ = listener.accept()
            with connection:
                server.handle_connection(connection)


__all__ = [
    "DEFAULT_APPROVAL_PATH",
    "DEFAULT_POLICY_PATH",
    "DEFAULT_SOCKET_PATH",
    "DEFAULT_STATE_DIR",
    "InfraBrokerClient",
    "InfraBrokerClientProtocol",
    "InfraBrokerError",
    "InfraBrokerServer",
    "broker_main",
    "build_ssh_options",
    "load_infra_approvals",
    "load_infra_policy",
]
