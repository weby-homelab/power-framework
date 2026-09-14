"""Constrained local INFRA-1 broker client and opt-in broker service.

The client is the only surface used by POWER CLI/MCP.  It accepts identifiers
only and speaks a one-request-per-connection framed protocol over a filesystem
Unix socket.  The server derives the caller from ``SO_PEERCRED``, reloads
operator policy at admission, snapshots trust material and source bytes, and
executes only a fixed rsync-over-SSH template.  There is intentionally no
direct SSH fallback and no remote shell primitive.

The Linux systemd profile in ``deploy/systemd`` is the production boundary. A
direct in-process ``handle_request`` call is useful for hermetic unit tests but
does not replace the socket principal and service sandbox.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import os
import re
import selectors
import shlex
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast

import yaml
from pydantic import ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping

from .infra_models import (
    CAPABILITY_BY_OPERATION,
    InfraApprovalRecord,
    InfraCapabilityBlockReceipt,
    InfraExitCategory,
    InfraOperation,
    InfraOperationReceipt,
    InfraPolicyFile,
    InfraProfile,
    InfraProfileStatus,
    InfraReasonCode,
    InfraRequest,
    InfraResponse,
    InfraResponseData,
    InfraResponseStatus,
    canonical_profile_digest,
    derive_receipt_id,
    idempotency_key_reference,
    ssh_fingerprint_from_blob,
    utc_now,
)

MAX_FRAME_BYTES = 64_000
SERVER_IO_TIMEOUT_SECONDS = 15.0
DEFAULT_SOCKET_PATH = Path("/run/power-infra/broker.sock")
DEFAULT_POLICY_PATH = Path("/etc/power/infra/profiles.d")
DEFAULT_STATE_DIR = Path("/var/lib/power-infra")
DEFAULT_RUNTIME_DIR = Path("/run/power-infra-broker")
DEFAULT_APPROVAL_PATH = Path("/etc/power/infra/approvals.json")
DEFAULT_FALLBACK_CREDENTIAL_DIR = Path("/etc/power/infra/credentials")
SSH_BINARY = "/usr/bin/ssh"
RSYNC_BINARY = "/usr/bin/rsync"
MAX_POLICY_BYTES = 1_048_576
MAX_KNOWN_HOSTS_BYTES = 1_000_000
MAX_CREDENTIAL_BYTES = 128_000
MAX_RECEIPT_BYTES = 64_000
MAX_STATE_RECORDS = 10_000
MAX_STATE_BYTES = 10_000_000
MAX_ACTIVE_CONNECTIONS = 8
MAX_PREPARED_ADMISSION_AGE_SECONDS = 3600
MAX_SNAPSHOT_STATE_BYTES = 50 * 1024 * 1024 * 1024
MIN_SNAPSHOT_FREE_BYTES = 64 * 1024 * 1024
_PEER_CREDENTIALS = getattr(socket, "SO_PEERCRED", None)
_UID_PATTERN = r"^uid:[0-9]+$"
_ADMISSION_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_WIRE_NONCE_PATTERN = r"^[0-9a-f]{32}$"
type InfraVerificationResult = Literal[
    "status",
    "not-requested",
    "dry-run-passed",
    "replicated-awaiting-verify",
    "passed",
    "inventory-matched",
    "mismatch",
    "unknown",
]
type InfraInventoryType = Literal["file", "directory"]
logger = logging.getLogger(__name__)


class InfraBrokerError(RuntimeError):
    """Internal error carrying only a bounded public reason category."""

    def __init__(
        self,
        reason_code: InfraReasonCode,
        remediation_code: str,
        broker_status: str,
        message: str = "infrastructure operation blocked",
        *,
        policy_revision: str = "unknown",
        run_id: str | None = None,
        source_manifest_digest: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.remediation_code = remediation_code
        self.broker_status = broker_status
        self.policy_revision = policy_revision
        self.run_id = run_id
        self.source_manifest_digest = source_manifest_digest


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
    stderr_sample: bytes = b""
    output_truncated: bool = False


@dataclass(frozen=True)
class _Manifest:
    digest: str
    file_count: int
    byte_count: int
    snapshot_dir: Path
    source_dirs: tuple[Path, ...]

    def digest_to_run_id(self) -> str:
        """Return the immutable run identifier derived from this manifest."""

        return f"run_{self.digest}"


@dataclass(frozen=True)
class _RunRecord:
    run_id: str
    target_id: str
    profile_id: str
    policy_revision: str
    profile_digest: str
    manifest_digest: str
    file_count: int
    byte_count: int
    dry_run_passed: bool
    write_in_progress: bool
    reservation_ref: str | None
    reservation_principal_ref: str | None
    reservation_owner_token: str | None
    replicated: bool
    receipt_id: str | None
    dry_run_receipt_id: str | None


@dataclass(frozen=True)
class _CredentialMaterial:
    path: Path
    source: Literal["systemd-loadcredential", "configured", "plaintext-fallback"]


def _safe_socket_path(path: Path) -> Path:
    """Validate a local filesystem socket path without resolving symlinks."""

    candidate = Path(path).expanduser()
    if not candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("broker socket path must be an absolute safe path")
    return candidate


def _assert_no_symlink_components(path: Path) -> None:
    """Reject symlinked ancestors before opening a configured path."""

    absolute = Path(path).absolute()
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


def _assert_secure_ancestors(path: Path, *, allowed_owners: set[int] | None = None) -> None:
    """Require non-writable ancestors, allowing only the normal sticky /tmp."""

    owners = allowed_owners or {0, os.geteuid()}
    absolute = Path(path).absolute()
    current = Path(absolute.anchor)
    for component in absolute.parts[1:-1]:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("configured path ancestor is not a directory")
        if metadata.st_uid not in owners:
            raise ValueError("configured path ancestor has an unexpected owner")
        mode = stat.S_IMODE(metadata.st_mode)
        sticky_tmp = mode & 0o1000 and mode & 0o002 and metadata.st_uid == 0
        if mode & 0o022 and not sticky_tmp:
            raise ValueError("configured path ancestor is writable by another principal")


def _assert_secure_directory(
    path: Path,
    *,
    create: bool = False,
    private: bool = False,
) -> None:
    """Validate a policy/state directory and optionally create its final node."""

    candidate = Path(path).expanduser()
    _assert_no_symlink_components(candidate)
    _assert_secure_ancestors(candidate)
    if not candidate.exists():
        if not create:
            raise FileNotFoundError("operator directory is unavailable")
        candidate.mkdir(parents=True, mode=0o700, exist_ok=False)
    metadata = candidate.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("operator path must be a regular directory")
    if metadata.st_uid not in {0, os.geteuid()}:
        raise ValueError("operator directory has an unexpected owner")
    mode = stat.S_IMODE(metadata.st_mode)
    if mode & 0o022:
        raise ValueError("operator directory must not be group/world writable")
    if private and mode & 0o077:
        raise ValueError("private broker directory must not be group/world accessible")


def _read_secure_file(
    path: Path,
    *,
    max_bytes: int,
    private: bool = False,
) -> bytes:
    """Read one stable regular file through an O_NOFOLLOW descriptor."""

    candidate = Path(path).expanduser()
    _assert_no_symlink_components(candidate)
    _assert_secure_ancestors(candidate)
    try:
        before = candidate.lstat()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise ValueError("operator file is unavailable") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ValueError("operator file must be a regular file")
    if before.st_nlink != 1:
        raise ValueError("operator file must not be hard-linked")
    if before.st_uid not in {0, os.geteuid()}:
        raise ValueError("operator file has an unexpected owner")
    mode = stat.S_IMODE(before.st_mode)
    if private and mode & 0o077:
        raise ValueError("private operator file permissions are too broad")
    if not private and mode & 0o022:
        raise ValueError("operator file must not be group/world writable")
    if before.st_size > max_bytes:
        raise ValueError("operator file exceeds its size limit")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(candidate, flags)
    try:
        after_open = os.fstat(descriptor)
        if (
            after_open.st_dev != before.st_dev
            or after_open.st_ino != before.st_ino
            or not stat.S_ISREG(after_open.st_mode)
            or after_open.st_nlink != 1
        ):
            raise ValueError("operator file changed during admission")
        chunks: list[bytes] = []
        total = 0
        while total <= max_bytes:
            chunk = os.read(descriptor, min(64 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("operator file exceeds its size limit")
        after_read = os.fstat(descriptor)
        if (
            after_read.st_dev != before.st_dev
            or after_read.st_ino != before.st_ino
            or after_read.st_mtime_ns != before.st_mtime_ns
            or after_read.st_ctime_ns != before.st_ctime_ns
        ):
            raise ValueError("operator file changed while it was read")
        if after_read.st_size != before.st_size:
            raise ValueError("operator file size changed while it was read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


class _UniqueYamlLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mappings before Pydantic sees them."""


def _construct_unique_mapping(loader: _UniqueYamlLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in mapping:
            raise ValueError("duplicate policy key")
        mapping[key] = loader.construct_object(value_node, deep=True)
    return mapping


_UniqueYamlLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate policy key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"JSON constant {value} is not allowed")


def _parse_document(raw: bytes, suffix: str) -> object:
    text = raw.decode("utf-8")
    if suffix in {".yaml", ".yml"}:
        return yaml.load(text, Loader=_UniqueYamlLoader)  # noqa: S506 - SafeLoader subclass only
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_json_keys,
        parse_constant=_reject_json_constant,
    )


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


def load_infra_policy(path: Path) -> InfraPolicyFile:
    """Load one strict policy file or a bounded operator-owned profile directory."""

    candidate = Path(path).expanduser()
    _assert_no_symlink_components(candidate)
    if candidate.is_dir():
        _assert_secure_directory(candidate)
        entries = sorted(
            entry
            for entry in candidate.iterdir()
            if entry.suffix in {".json", ".yaml", ".yml"}
            and not entry.name.startswith(".")
            and ".example." not in entry.name
        )
        if len(entries) > 128:
            raise ValueError("infrastructure policy has too many profile files")
        profiles: list[InfraProfile] = []
        for entry in entries:
            raw = _read_secure_file(entry, max_bytes=MAX_POLICY_BYTES)
            try:
                payload = _parse_document(raw, entry.suffix)
                if isinstance(payload, dict) and "profiles" in payload:
                    document = InfraPolicyFile.model_validate(payload)
                    profiles.extend(document.profiles)
                else:
                    profiles.append(InfraProfile.model_validate(payload))
            except (TypeError, ValueError, ValidationError, yaml.YAMLError) as exc:
                raise ValueError("infrastructure policy schema is invalid") from exc
        _validate_unique_profiles(profiles)
        return InfraPolicyFile(schema_version="power.infra-policy.v1", profiles=profiles)

    raw = _read_secure_file(candidate, max_bytes=MAX_POLICY_BYTES)
    try:
        payload = _parse_document(raw, candidate.suffix)
        document = InfraPolicyFile.model_validate(payload)
    except (TypeError, ValueError, ValidationError, yaml.YAMLError) as exc:
        raise ValueError("infrastructure policy schema is invalid") from exc
    _validate_unique_profiles(document.profiles)
    return document


def load_infra_approvals(path: Path) -> dict[str, InfraApprovalRecord]:
    """Reload exact approval records from the operator boundary."""

    raw = _read_secure_file(Path(path), max_bytes=MAX_POLICY_BYTES, private=False)
    try:
        payload = _parse_document(raw, ".json")
        if (
            not isinstance(payload, dict)
            or set(payload) != {"schema_version", "approvals"}
            or payload.get("schema_version") != "power.infra-approvals.v1"
            or not isinstance(payload.get("approvals"), list)
        ):
            raise ValueError("invalid approval document")
        values = cast("list[object]", payload["approvals"])
        if len(values) > MAX_STATE_RECORDS:
            raise ValueError("approval list exceeds its bound")
        records: dict[str, InfraApprovalRecord] = {}
        for value in values:
            record = InfraApprovalRecord.model_validate(value)
            if record.approval_ref in records:
                raise ValueError("approval_ref is duplicated")
            records[record.approval_ref] = record
        return records
    except (TypeError, ValueError, ValidationError, yaml.YAMLError) as exc:
        raise ValueError("infrastructure approval schema is invalid") from exc


def _atomic_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    """Publish a bounded state file atomically inside its private directory."""

    parent = path.parent
    _assert_secure_directory(parent, private=True)
    if len(payload) > MAX_STATE_BYTES:
        raise ValueError("broker state record exceeds its byte bound")
    if path.exists() and path.is_symlink():
        raise ValueError("broker state target must not be a symlink")
    temporary = parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, mode)
    published = False
    try:
        written = 0
        while written < len(payload):
            written += os.write(descriptor, payload[written:])
        os.fsync(descriptor)
        os.close(descriptor)
        os.replace(temporary, path)
        published = True
    finally:
        with suppress(OSError):
            os.close(descriptor)
        if not published:
            with suppress(OSError):
                temporary.unlink()
    _fsync_directory(parent)


def _fsync_directory(path: Path) -> None:
    """Durably publish directory-entry changes on local broker state."""

    _assert_no_symlink_components(path)
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _unlink_and_fsync(path: Path) -> None:
    """Remove one broker state entry and durably publish the deletion."""

    try:
        path.unlink()
    except FileNotFoundError:
        return
    _fsync_directory(path.parent)


def _remove_tree_and_fsync(path: Path) -> None:
    """Remove a broker-generated orphan and durably publish its parent change."""

    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError("generated broker state must not be a symlink")
    if stat.S_ISDIR(metadata.st_mode):
        shutil.rmtree(path)
    else:
        path.unlink()
    _fsync_directory(path.parent)


def _fsync_directory_tree(root: Path) -> None:
    """Durably publish every generated directory before snapshot promotion."""

    for current_text, dirnames, _filenames in os.walk(
        root,
        topdown=False,
        onerror=_raise_walk_error,
        followlinks=False,
    ):
        current = Path(current_text)
        if any((current / dirname).is_symlink() for dirname in dirnames):
            raise ValueError("generated snapshot contains a symlink directory")
        _fsync_directory(current)


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _write_bounded_file(path: Path, payload: bytes, *, mode: int) -> None:
    """Create one generated file without following a destination symlink."""

    parent = path.parent
    _assert_secure_directory(parent, private=True)
    if len(payload) > MAX_STATE_BYTES:
        raise ValueError("generated broker file exceeds its size limit")
    if path.exists():
        raise FileExistsError("generated broker file already exists")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, mode)
    try:
        written = 0
        while written < len(payload):
            written += os.write(descriptor, payload[written:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(parent)


def _safe_environment() -> dict[str, str]:
    """Return the only environment inherited by SSH/rsync children."""

    return {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": "/nonexistent"}


def _peer_identity(connection: socket.socket) -> tuple[int, int, int, str]:
    """Read kernel-provided local peer credentials; never trust JSON attribution."""

    if _PEER_CREDENTIALS is not None:
        raw = connection.getsockopt(socket.SOL_SOCKET, _PEER_CREDENTIALS, struct.calcsize("3i"))
        if len(raw) != struct.calcsize("3i"):
            raise InfraBrokerError(
                InfraReasonCode.PRINCIPAL_UNAVAILABLE,
                "UNSUPPORTED_PEER_CREDENTIALS",
                "principal-unavailable",
            )
        peer_pid, uid, gid = struct.unpack("3i", raw)
        return peer_pid, uid, gid, f"uid:{uid}"
    getpeereid = getattr(connection, "getpeereid", None)
    if callable(getpeereid):  # pragma: no cover - BSD fallback
        uid, gid = getpeereid()
        return 0, uid, gid, f"uid:{uid}"
    raise InfraBrokerError(
        InfraReasonCode.PRINCIPAL_UNAVAILABLE,
        "UNSUPPORTED_PEER_CREDENTIALS",
        "principal-unavailable",
    )


def peer_principal(connection: socket.socket) -> str:
    """Public read-only helper exposing the server-derived principal reference."""

    return _peer_identity(connection)[3]


def build_ssh_options(
    *,
    hostname: str,
    port: int,
    username: str,
    known_hosts_file: Path,
    credential_file: Path,
) -> list[str]:
    """Build the complete hermetic SSH option vector used by the broker.

    ``hostname`` and ``username`` are accepted as an explicit policy boundary;
    they are not inserted into options.  The remote target is supplied by the
    fixed rsync destination after policy validation.
    """

    del hostname, username
    return [
        "-F",
        "/dev/null",
        "-o",
        "BatchMode=yes",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "PubkeyAuthentication=yes",
        "-o",
        "PreferredAuthentications=publickey",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "IdentityAgent=none",
        "-o",
        "IdentityFile=" + str(credential_file),
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=" + str(known_hosts_file),
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        "KnownHostsCommand=none",
        "-o",
        "HashKnownHosts=no",
        "-o",
        "UpdateHostkeys=no",
        "-o",
        "CheckHostIP=no",
        "-o",
        "ProxyCommand=none",
        "-o",
        "ProxyJump=none",
        "-o",
        "PermitLocalCommand=no",
        "-o",
        "LocalCommand=none",
        "-o",
        "RemoteCommand=none",
        "-o",
        "RequestTTY=no",
        "-o",
        "ForwardAgent=no",
        "-o",
        "ForwardX11=no",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "ControlMaster=no",
        "-o",
        "ControlPath=none",
        "-o",
        "GSSAPIAuthentication=no",
        "-o",
        "GSSAPIDelegateCredentials=no",
        "-o",
        "HostbasedAuthentication=no",
        "-o",
        "PKCS11Provider=none",
        "-o",
        "SecurityKeyProvider=none",
        "-o",
        "AddKeysToAgent=no",
        "-o",
        "EnableEscapeCommandline=no",
        "-o",
        "CanonicalizeHostname=no",
        "-p",
        str(port),
    ]


def _build_ssh_command(profile: InfraProfile, known_hosts_file: Path, credential_file: Path) -> str:
    """Build rsync's fixed ``-e`` value from already validated policy material."""

    return shlex.join(
        [
            SSH_BINARY,
            *build_ssh_options(
                hostname=profile.hostname,
                port=profile.port,
                username=profile.remote_user,
                known_hosts_file=known_hosts_file,
                credential_file=credential_file,
            ),
        ]
    )


def _encode_frame(payload: Mapping[str, object]) -> bytes:
    encoded = _json_bytes(payload)
    if len(encoded) > MAX_FRAME_BYTES:
        raise ValueError("broker frame exceeds the maximum size")
    return struct.pack(">I", len(encoded)) + encoded


def _receive_exact(connection: socket.socket, size: int, *, deadline: float | None = None) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        if deadline is not None:
            wait_seconds = deadline - time.monotonic()
            if wait_seconds <= 0:
                raise TimeoutError("broker frame deadline elapsed")
            connection.settimeout(wait_seconds)
        chunk = connection.recv(min(remaining, 16_384))
        if not chunk:
            raise ConnectionError("broker socket closed before a complete frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _receive_frame(
    connection: socket.socket, *, deadline_seconds: float | None = None
) -> dict[str, object]:
    deadline = time.monotonic() + deadline_seconds if deadline_seconds is not None else None
    header = _receive_exact(connection, 4, deadline=deadline)
    (size,) = struct.unpack(">I", header)
    if size < 2 or size > MAX_FRAME_BYTES:
        raise ValueError("broker frame length is outside the bounded protocol")
    payload = json.loads(
        _receive_exact(connection, size, deadline=deadline).decode("utf-8"),
        object_pairs_hook=_reject_duplicate_json_keys,
        parse_constant=_reject_json_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError("broker frame must contain a JSON object")
    return cast("dict[str, object]", payload)


def _trace_id() -> str:
    return f"tr_{uuid.uuid4().hex}"


def _request_digest(request: InfraRequest, profile_digest: str | None = None) -> str:
    request_payload = request.model_dump(mode="json")
    if request.operation is InfraOperation.RSYNC_DRY_RUN:
        # The operation itself is the dry-run intent; adapters may omit the
        # redundant boolean while constructing the typed request.
        request_payload["dry_run"] = True
        request_payload["idempotency_key"] = None
    # Task identity and CAS revision are checked by ApplicationService; they
    # must not turn one external intent into a different broker side effect.
    request_payload.pop("task_id", None)
    request_payload.pop("expected_revision", None)
    payload: dict[str, object] = {"request": request_payload}
    if profile_digest is not None:
        payload["profile_digest"] = profile_digest
    return hashlib_sha256(_json_bytes(payload))


def hashlib_sha256(payload: bytes) -> str:
    """Small named helper keeps digest construction auditable and deterministic."""

    return hashlib.sha256(payload).hexdigest()


def _block_response(
    request: InfraRequest,
    reason_code: InfraReasonCode,
    *,
    policy_revision: str = "unknown",
    broker_status: str = "unavailable",
    remediation_code: str = "INSPECT_BROKER_STATUS",
    task_id: str | None = None,
    principal_ref: str | None = None,
    run_id: str | None = None,
    source_manifest_digest: str | None = None,
    request_digest: str | None = None,
) -> InfraResponse:
    """Create one bounded block receipt without copying exception content."""

    capability = CAPABILITY_BY_OPERATION[request.operation]
    trace_id = _trace_id()
    payload = {
        "trace_id": trace_id,
        "request_digest": request_digest or _request_digest(request),
        "operation": request.operation.value,
        "target_id": request.target,
        "profile_id": request.profile or "unknown",
        "reason_code": reason_code.value,
        "required_capability": capability,
        "policy_revision": policy_revision,
        "broker_status": broker_status,
        "remediation_code": remediation_code,
        "task_id": task_id or request.task_id,
        "principal_ref": principal_ref,
        "run_id": run_id,
        "source_manifest_digest": source_manifest_digest,
    }
    receipt = InfraCapabilityBlockReceipt(
        receipt_id=derive_receipt_id("ibr", payload),
        trace_id=trace_id,
        task_id=task_id or request.task_id,
        principal_ref=principal_ref,
        operation=request.operation,
        target_id=request.target,
        profile_id=request.profile or "unknown",
        reason_code=reason_code,
        required_capability=capability,
        policy_revision=policy_revision,
        broker_status=broker_status,
        remediation_code=remediation_code,
        recorded_at=utc_now(),
        run_id=run_id,
        source_manifest_digest=source_manifest_digest,
    )
    status = (
        InfraResponseStatus.AUTH_REQUIRED
        if reason_code is InfraReasonCode.APPROVAL_REQUIRED
        else InfraResponseStatus.BLOCKED
    )
    return InfraResponse(
        status=status,
        operation=request.operation,
        target=request.target,
        profile=request.profile,
        task_id=request.task_id,
        request_digest=request_digest or _request_digest(request),
        data=InfraResponseData(),
        receipt=receipt,
    )


class InfraBrokerClient:
    """Safe local client; it never invokes SSH/rsync and never reads credentials."""

    def __init__(
        self,
        *,
        socket_path: Path | None = None,
        timeout_seconds: float = 10.0,
        expected_broker_uid: int | None = None,
    ) -> None:
        self.socket_path = _safe_socket_path(
            socket_path or Path(os.getenv("POWER_INFRA_SOCKET", str(DEFAULT_SOCKET_PATH)))
        )
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("broker client timeout must be between 0 and 60 seconds")
        self.timeout_seconds = timeout_seconds
        self.expected_broker_uid = (
            expected_broker_uid if expected_broker_uid is not None else _default_broker_uid()
        )

    def execute(self, request: InfraRequest) -> InfraResponse:
        """Send one typed request over one authenticated local socket connection."""

        if not isinstance(request, InfraRequest):
            raise TypeError("broker client requires an InfraRequest")
        if request.operation is not InfraOperation.STATUS and (
            not request.target or not request.profile
        ):
            return _block_response(
                request,
                InfraReasonCode.REQUEST_INPUT_MISSING,
                broker_status="input-required",
                remediation_code="PROVIDE_TARGET_AND_PROFILE",
            )
        endpoint_state = _inspect_socket_endpoint(
            self.socket_path, expected_broker_uid=self.expected_broker_uid
        )
        if endpoint_state != "ready":
            return _block_response(
                request,
                InfraReasonCode.MISSING_EXECUTION_CAPABILITY,
                broker_status=endpoint_state,
                remediation_code=(
                    "INSTALL_ENABLE_BROKER"
                    if endpoint_state == "broker-not-installed"
                    else "ENABLE_BROKER_SERVICE"
                    if endpoint_state == "broker-disabled"
                    else "INSPECT_BROKER_STATUS"
                ),
            )
        if self.expected_broker_uid is None:
            return _block_response(
                request,
                InfraReasonCode.MISSING_EXECUTION_CAPABILITY,
                broker_status="broker-identity-unconfigured",
                remediation_code="INSTALL_DEDICATED_BROKER_ACCOUNT",
            )

        nonce = uuid.uuid4().hex
        sent = False
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout_seconds)
                connection.connect(str(self.socket_path))
                _, uid, _, _ = _peer_identity(connection)
                if self.expected_broker_uid is not None and uid != self.expected_broker_uid:
                    return _block_response(
                        request,
                        InfraReasonCode.PRINCIPAL_DENIED,
                        broker_status="broker-identity-mismatch",
                        remediation_code="REPAIR_BROKER_SOCKET_OWNER",
                    )
                wire_request = {
                    "schema_version": "power.infra-wire.v1",
                    "nonce": nonce,
                    "request": request.model_dump(mode="json"),
                }
                encoded_request = _encode_frame(wire_request)
                sent = True
                connection.sendall(encoded_request)
                frame = _receive_frame(connection, deadline_seconds=self.timeout_seconds)
            if (
                frame.get("schema_version") != "power.infra-wire-response.v1"
                or frame.get("nonce") != nonce
                or not isinstance(frame.get("response"), dict)
            ):
                raise ValueError("broker response binding is invalid")
            response = InfraResponse.model_validate(frame["response"])
            if (
                response.operation is not request.operation
                or response.target != request.target
                or response.profile != request.profile
                or response.task_id != request.task_id
                or response.request_digest != _request_digest(request)
            ):
                raise ValueError("broker response does not match the request")
            return response
        except InfraBrokerError as error:
            return _block_response(
                request,
                error.reason_code,
                broker_status=error.broker_status,
                remediation_code=error.remediation_code,
            )
        except ConnectionRefusedError:
            return _block_response(
                request,
                InfraReasonCode.MISSING_EXECUTION_CAPABILITY,
                broker_status="broker-disabled",
                remediation_code="ENABLE_BROKER_SERVICE",
            )
        except TimeoutError:
            if sent and request.operation is InfraOperation.REPLICATE:
                return _block_response(
                    request,
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    broker_status="broker-response-unknown",
                    remediation_code="RESOLVE_BROKER_RUN_BEFORE_RETRY",
                )
            return _block_response(
                request,
                InfraReasonCode.TIMEOUT,
                broker_status="broker-timeout",
                remediation_code="INSPECT_BROKER_STATUS",
            )
        except (
            ConnectionError,
            OSError,
            RecursionError,
            ValueError,
            ValidationError,
        ):
            if sent and request.operation is InfraOperation.REPLICATE:
                return _block_response(
                    request,
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    broker_status="broker-response-unknown",
                    remediation_code="RESOLVE_BROKER_RUN_BEFORE_RETRY",
                )
            return _block_response(
                request,
                InfraReasonCode.PROTOCOL_ERROR,
                broker_status="broker-unavailable",
                remediation_code="INSPECT_BROKER_STATUS",
            )

    def status(self) -> InfraResponse:
        """Return broker status without probing a remote target."""

        request = InfraRequest(operation=InfraOperation.STATUS)
        response = self.execute(request)
        broker_status = response.data.broker_status
        if isinstance(response.receipt, InfraCapabilityBlockReceipt):
            broker_status = response.receipt.broker_status
        return response.model_copy(
            update={
                "data": response.data.model_copy(
                    update={
                        "client_supported": os.name == "posix" and hasattr(socket, "AF_UNIX"),
                        "transport": "unix",
                        "broker_status": broker_status,
                    }
                )
            }
        )


def _default_broker_uid() -> int | None:
    """Resolve the expected service UID without making a network or secret read."""

    try:
        import pwd

        return pwd.getpwnam("power-infra").pw_uid
    except (KeyError, ImportError):
        return None


def _broker_binary_available() -> bool:
    """Check only fixed launcher locations for a truthful local status label."""

    candidates = (
        Path(sys.executable).with_name("power-infra-broker"),
        Path("/usr/bin/power-infra-broker"),
        Path("/etc/systemd/system/power-infra-broker.service"),
        Path("/usr/lib/systemd/system/power-infra-broker.service"),
    )
    return any(
        candidate.is_file()
        and not candidate.is_symlink()
        and (os.access(candidate, os.X_OK) or candidate.name == "power-infra-broker.service")
        for candidate in candidates
    )


def _inspect_socket_endpoint(
    path: Path,
    *,
    expected_broker_uid: int | None,
) -> Literal[
    "ready", "broker-not-installed", "broker-disabled", "unsafe-socket", "broker-unavailable"
]:
    try:
        _assert_no_symlink_components(path)
        _assert_secure_ancestors(
            path,
            allowed_owners={0, expected_broker_uid} if expected_broker_uid is not None else None,
        )
        metadata = path.lstat()
    except FileNotFoundError:
        return "broker-disabled" if _broker_binary_available() else "broker-not-installed"
    except (OSError, ValueError):
        return "unsafe-socket"
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISSOCK(metadata.st_mode):
        return "unsafe-socket"
    if expected_broker_uid is not None and metadata.st_uid != expected_broker_uid:
        return "unsafe-socket"
    if stat.S_IMODE(metadata.st_mode) & 0o002:
        return "unsafe-socket"
    return "ready"


class InfraBrokerServer:
    """Opt-in local broker owning policy, credentials, trust, and fixed execution."""

    def __init__(
        self,
        *,
        policy_path: Path = DEFAULT_POLICY_PATH,
        socket_path: Path = DEFAULT_SOCKET_PATH,
        state_dir: Path = DEFAULT_STATE_DIR,
        runtime_dir: Path | None = None,
        credential_dir: Path | None = None,
        approval_path: Path | None = None,
        authorized_uids: set[int] | None = None,
        authorized_gids: set[int] | None = None,
        command_runner: Callable[[list[str], float, int], _ProcessResult] | None = None,
    ) -> None:
        self.policy_path = Path(policy_path).expanduser()
        self.socket_path = _safe_socket_path(socket_path)
        self.state_dir = Path(state_dir).expanduser()
        configured_runtime_dir = (
            runtime_dir or os.getenv("POWER_INFRA_RUNTIME_DIR") or os.getenv("RUNTIME_DIRECTORY")
        )
        default_runtime_dir = (
            DEFAULT_RUNTIME_DIR
            if self.state_dir == DEFAULT_STATE_DIR
            else self.state_dir / "runtime"
        )
        self.runtime_dir = Path(configured_runtime_dir or default_runtime_dir).expanduser()
        environment_credential_dir = os.getenv("CREDENTIALS_DIRECTORY")
        if credential_dir is not None:
            self.credential_dir = Path(credential_dir).expanduser()
            self.credential_source: Literal[
                "systemd-loadcredential", "configured", "plaintext-fallback"
            ] = "plaintext-fallback"
        elif environment_credential_dir:
            self.credential_dir = Path(environment_credential_dir).expanduser()
            self.credential_source = "systemd-loadcredential"
        else:
            self.credential_dir = DEFAULT_FALLBACK_CREDENTIAL_DIR
            self.credential_source = "plaintext-fallback"
        self.approval_path = Path(approval_path or DEFAULT_APPROVAL_PATH).expanduser()
        self.authorized_uids = set(authorized_uids or set())
        self.authorized_gids = set(authorized_gids or set())
        self.command_runner = command_runner or _run_bounded_process
        self._state_lock = threading.RLock()
        self._semaphore_lock = threading.Lock()
        self._semaphores: dict[str, tuple[int, threading.BoundedSemaphore]] = {}
        self._profile_active: dict[str, int] = {}
        self._served_socket: socket.socket | None = None

    def peer_principal(self, connection: socket.socket) -> str:
        """Derive and authorize a principal using only kernel peer credentials."""

        peer_pid, uid, gid, principal_ref = _peer_identity(connection)
        del peer_pid
        if self.authorized_uids and uid not in self.authorized_uids:
            raise InfraBrokerError(
                InfraReasonCode.PRINCIPAL_DENIED,
                "CALLER_UID_NOT_ALLOWED",
                "principal-denied",
            )
        if self.authorized_gids and gid not in self.authorized_gids:
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
        return principal_ref

    def handle_connection(self, connection: socket.socket) -> None:
        """Process exactly one bounded request and close the connection."""

        connection.settimeout(SERVER_IO_TIMEOUT_SECONDS)
        request = InfraRequest(operation=InfraOperation.STATUS)
        nonce = "0" * 32
        try:
            principal_ref = self.peer_principal(connection)
        except (InfraBrokerError, OSError):
            return
        try:
            frame = _receive_frame(connection, deadline_seconds=SERVER_IO_TIMEOUT_SECONDS)
            if (
                frame.get("schema_version") != "power.infra-wire.v1"
                or not isinstance(frame.get("nonce"), str)
                or not __import__("re").fullmatch(_WIRE_NONCE_PATTERN, cast("str", frame["nonce"]))
                or not isinstance(frame.get("request"), dict)
            ):
                raise ValueError("invalid broker wire request")
            nonce = cast("str", frame["nonce"])
            request = InfraRequest.model_validate(frame["request"])
            response = self._handle_authenticated_request(request, principal_ref=principal_ref)
        except InfraBrokerError as error:
            response = _block_response(
                request,
                error.reason_code,
                policy_revision=error.policy_revision,
                broker_status=error.broker_status,
                remediation_code=error.remediation_code,
                run_id=error.run_id,
                source_manifest_digest=error.source_manifest_digest,
            )
        except (
            ConnectionError,
            OSError,
            RecursionError,
            RuntimeError,
            ValueError,
            ValidationError,
            UnicodeError,
        ):
            response = _block_response(
                request,
                InfraReasonCode.PROTOCOL_ERROR,
                broker_status="invalid-request",
                remediation_code="SEND_TYPED_REQUEST",
            )
        response = self._bind_block_principal(response, principal_ref)
        response = self._persist_receipt_or_degrade(request, response, principal_ref=principal_ref)
        response = self._bind_block_principal(response, principal_ref)
        with suppress(ConnectionError, OSError, ValueError):
            connection.sendall(
                _encode_frame(
                    {
                        "schema_version": "power.infra-wire-response.v1",
                        "nonce": nonce,
                        "response": response.model_dump(mode="json"),
                    }
                )
            )

    def handle_request(self, request: InfraRequest, *, principal_ref: str) -> InfraResponse:
        """Test/library seam restricted to the current local process identity."""

        if (
            principal_ref != f"uid:{os.getuid()}"
            or (not self.authorized_uids and not self.authorized_gids)
            or (self.authorized_uids and os.getuid() not in self.authorized_uids)
            or (self.authorized_gids and os.getgid() not in self.authorized_gids)
        ):
            raise ValueError(
                "in-process broker calls require the current authorized local identity"
            )
        response = self._process_request(request, principal_ref=principal_ref)
        response = self._bind_block_principal(response, principal_ref)
        response = self._persist_receipt_or_degrade(request, response, principal_ref=principal_ref)
        return self._bind_block_principal(response, principal_ref)

    @staticmethod
    def _bind_block_principal(response: InfraResponse, principal_ref: str) -> InfraResponse:
        """Bind server-derived identity to every block receipt before persistence."""

        receipt = response.receipt
        if not isinstance(receipt, InfraCapabilityBlockReceipt):
            return response
        payload = {
            "trace_id": receipt.trace_id,
            "request_digest": response.request_digest,
            "operation": receipt.operation.value,
            "target_id": response.target,
            "profile_id": response.profile or "unknown",
            "reason_code": receipt.reason_code.value,
            "required_capability": receipt.required_capability,
            "policy_revision": receipt.policy_revision,
            "broker_status": receipt.broker_status,
            "remediation_code": receipt.remediation_code,
            "task_id": response.task_id,
            "principal_ref": principal_ref,
            "run_id": receipt.run_id,
            "source_manifest_digest": receipt.source_manifest_digest,
        }
        bound = receipt.model_copy(
            update={
                "principal_ref": principal_ref,
                "receipt_id": derive_receipt_id("ibr", payload),
            }
        )
        return response.model_copy(update={"receipt": bound})

    def _handle_authenticated_request(
        self, request: InfraRequest, *, principal_ref: str
    ) -> InfraResponse:
        """Process a request only after ``handle_connection`` authenticated its peer."""

        return self._process_request(request, principal_ref=principal_ref)

    def _process_request(self, request: InfraRequest, *, principal_ref: str) -> InfraResponse:
        """Execute a request for an already validated broker principal."""

        if not isinstance(request, InfraRequest) or not re.fullmatch(_UID_PATTERN, principal_ref):
            raise ValueError("broker request requires a server-derived principal")
        if request.operation is InfraOperation.STATUS:
            return self._status_response(principal_ref)
        try:
            policy = load_infra_policy(self.policy_path)
        except FileNotFoundError:
            return _block_response(
                request,
                InfraReasonCode.MISSING_EXECUTION_CAPABILITY,
                broker_status="broker-profile-directory-missing",
                remediation_code="INSTALL_OPERATOR_PROFILE",
            )
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
        if profile.allowed_principal_refs and principal_ref not in profile.allowed_principal_refs:
            return _block_response(
                request,
                InfraReasonCode.PRINCIPAL_DENIED,
                policy_revision=profile.policy_revision,
                broker_status="profile-principal-denied",
                remediation_code="REQUEST_OPERATOR_PRINCIPAL_ADMISSION",
            )
        if request.operation not in profile.allowed_operations:
            return _block_response(
                request,
                InfraReasonCode.CAPABILITY_DISABLED,
                policy_revision=profile.policy_revision,
                broker_status="profile-operation-disabled",
                remediation_code="REQUEST_OPERATOR_PROFILE_CHANGE",
            )

        acquired = self._acquire_profile_slot(profile)
        if not acquired:
            return _block_response(
                request,
                InfraReasonCode.RESOURCE_LIMIT,
                policy_revision=profile.policy_revision,
                broker_status="concurrency-limit",
                remediation_code="RETRY_AFTER_OPERATOR_BOUNDED_INTERVAL",
            )
        try:
            self._ensure_state_capacity()
            return self._admit_and_execute(request, profile, principal_ref)
        except InfraBrokerError as error:
            return _block_response(
                request,
                error.reason_code,
                policy_revision=error.policy_revision or profile.policy_revision,
                broker_status=error.broker_status,
                remediation_code=error.remediation_code,
                run_id=error.run_id,
                source_manifest_digest=error.source_manifest_digest,
            )
        except TimeoutError:
            return _block_response(
                request,
                InfraReasonCode.TIMEOUT,
                policy_revision=profile.policy_revision,
                broker_status="broker-timeout",
                remediation_code="LOWER_PROFILE_TIMEOUT_OR_SNAPSHOT_SIZE",
            )
        except (OSError, ValueError, ValidationError):
            return _block_response(
                request,
                InfraReasonCode.MISSING_EXECUTION_CAPABILITY,
                policy_revision=profile.policy_revision,
                broker_status="broker-state-unavailable",
                remediation_code="REPAIR_BROKER_STATE_BOUNDARY",
            )
        finally:
            self._release_profile_slot(profile)

    def _acquire_profile_slot(self, profile: InfraProfile) -> bool:
        with self._semaphore_lock:
            current = self._semaphores.get(profile.profile_id)
            active = self._profile_active.get(profile.profile_id, 0)
            if current is not None and current[0] != profile.max_concurrent and active:
                return False
            if current is None or current[0] != profile.max_concurrent:
                semaphore = threading.BoundedSemaphore(profile.max_concurrent)
                self._semaphores[profile.profile_id] = (profile.max_concurrent, semaphore)
            else:
                semaphore = current[1]
            acquired = semaphore.acquire(blocking=False)
            if acquired:
                self._profile_active[profile.profile_id] = active + 1
            return acquired

    def _release_profile_slot(self, profile: InfraProfile) -> None:
        with self._semaphore_lock:
            current = self._semaphores.get(profile.profile_id)
            active = self._profile_active.get(profile.profile_id, 0)
            if current is None or active <= 0:
                return
            self._profile_active[profile.profile_id] = active - 1
            current[1].release()

    def _admit_and_execute(
        self,
        request: InfraRequest,
        profile: InfraProfile,
        principal_ref: str,
    ) -> InfraResponse:
        profile_digest = canonical_profile_digest(profile)
        request_digest = _request_digest(request, profile_digest)
        key_ref = idempotency_key_reference(request.idempotency_key)
        admission_record: dict[str, object] | None = None
        recovering_prepared_admission = False
        admission_owner_token = uuid.uuid4().hex
        idempotency_claimed_by_attempt = False
        if request.operation is InfraOperation.REPLICATE and key_ref is not None:
            admission_record = self._read_admission(key_ref, principal_ref)

        if request.operation is InfraOperation.REPLICATE and key_ref is not None:
            existing = self._read_idempotency(key_ref, principal_ref)
            if existing is not None:
                stored_digest = str(existing.get("request_digest", ""))
                if stored_digest != request_digest:
                    return _block_response(
                        request,
                        InfraReasonCode.IDEMPOTENCY_CONFLICT,
                        policy_revision=profile.policy_revision,
                        broker_status="idempotency-conflict",
                        remediation_code="ISSUE_NEW_IDEMPOTENCY_KEY",
                        request_digest=_request_digest(request),
                    )
                if existing.get("status") == "completed" and isinstance(
                    existing.get("response"), dict
                ):
                    try:
                        stored_response = InfraResponse.model_validate(existing["response"])
                    except ValidationError as exc:
                        raise InfraBrokerError(
                            InfraReasonCode.UNKNOWN_COMPLETION,
                            "RESOLVE_CORRUPT_IDEMPOTENCY_RECORD",
                            "idempotency-record-invalid",
                            policy_revision=profile.policy_revision,
                        ) from exc
                    stored_run_id = existing.get("run_id")
                    stored_source_digest = existing.get("source_manifest_digest")
                    stored_receipt = stored_response.receipt
                    if (
                        stored_response.operation is not InfraOperation.REPLICATE
                        or stored_response.status is not InfraResponseStatus.OK
                        or not isinstance(stored_run_id, str)
                        or not isinstance(stored_source_digest, str)
                        or not isinstance(stored_receipt, InfraOperationReceipt)
                    ):
                        raise InfraBrokerError(
                            InfraReasonCode.UNKNOWN_COMPLETION,
                            "RESOLVE_CORRUPT_IDEMPOTENCY_RECORD",
                            "idempotency-record-invalid",
                            policy_revision=profile.policy_revision,
                            run_id=stored_run_id if isinstance(stored_run_id, str) else None,
                            source_manifest_digest=(
                                stored_source_digest
                                if isinstance(stored_source_digest, str)
                                else None
                            ),
                        )
                    try:
                        stored_run = self._load_run_record(stored_run_id)
                    except InfraBrokerError as exc:
                        raise InfraBrokerError(
                            InfraReasonCode.UNKNOWN_COMPLETION,
                            "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                            "completion-record-unavailable",
                            policy_revision=profile.policy_revision,
                            run_id=stored_run_id,
                            source_manifest_digest=stored_source_digest,
                        ) from exc
                    if (
                        not stored_run.replicated
                        or stored_run.write_in_progress
                        or stored_run.reservation_ref is not None
                        or stored_run.receipt_id != stored_receipt.receipt_id
                        or not self._has_durable_replicate_receipt(
                            stored_run.receipt_id,
                            run_id=stored_run_id,
                            manifest_digest=stored_source_digest,
                            profile=profile,
                            principal_ref=principal_ref,
                            key_ref=key_ref,
                            response_request_digest=stored_response.request_digest,
                            task_id=stored_response.task_id,
                        )
                    ):
                        raise InfraBrokerError(
                            InfraReasonCode.UNKNOWN_COMPLETION,
                            "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                            "completion-record-unavailable",
                            policy_revision=profile.policy_revision,
                            run_id=stored_run_id,
                            source_manifest_digest=stored_source_digest,
                        )
                    self._delete_admission(key_ref, principal_ref)
                    return self._replay_response(request, stored_response, principal_ref, profile)
                if existing.get("status") == "in-progress":
                    if (
                        admission_record is not None
                        and admission_record.get("status") == "prepared"
                        and admission_record.get("request_digest") == request_digest
                        and admission_record.get("run_id") == existing.get("run_id")
                        and admission_record.get("source_manifest_digest")
                        == existing.get("source_manifest_digest")
                    ):
                        recovering_prepared_admission = True
                    else:
                        run_id = existing.get("run_id")
                        manifest_digest = existing.get("source_manifest_digest")
                        raise InfraBrokerError(
                            InfraReasonCode.UNKNOWN_COMPLETION,
                            "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                            "operation-in-flight",
                            policy_revision=profile.policy_revision,
                            run_id=run_id if isinstance(run_id, str) else None,
                            source_manifest_digest=(
                                manifest_digest if isinstance(manifest_digest, str) else None
                            ),
                        )

                if existing.get("status") != "in-progress":
                    raise InfraBrokerError(
                        InfraReasonCode.UNKNOWN_COMPLETION,
                        "RESOLVE_CORRUPT_IDEMPOTENCY_RECORD",
                        "idempotency-record-invalid",
                        policy_revision=profile.policy_revision,
                    )

        if admission_record is not None and admission_record.get("status") == "started":
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                "admission-started",
                policy_revision=profile.policy_revision,
                run_id=cast("str | None", admission_record.get("run_id")),
                source_manifest_digest=cast(
                    "str | None", admission_record.get("source_manifest_digest")
                ),
            )

        approval_ref = self._validate_approval(request, profile, principal_ref)
        deadline = time.monotonic() + profile.timeout_seconds
        # Do not read source data when the broker cannot first establish its
        # credential and host-identity boundary.  The execution path repeats
        # the checks against stable private snapshots immediately before SSH.
        if request.operation is not InfraOperation.VERIFY:
            self._credential_candidate(profile)
        self._require_host_key(profile)
        if request.operation is InfraOperation.VERIFY:
            if profile.verify_credential_id is None:
                raise InfraBrokerError(
                    InfraReasonCode.CAPABILITY_DISABLED,
                    "INSTALL_DEDICATED_READ_ONLY_VERIFY_CREDENTIAL",
                    "verify-credential-not-configured",
                    policy_revision=profile.policy_revision,
                )
            self._credential_candidate(profile, credential_id=profile.verify_credential_id)
        if request.operation is InfraOperation.VERIFY:
            record = self._load_run_record(request.run_id or "")
            self._validate_run_binding(record, request, profile, profile_digest)
            manifest = self._load_snapshot(record, profile)
        elif (
            request.operation is InfraOperation.REPLICATE
            and admission_record is not None
            and admission_record.get("status") == "prepared"
        ):
            prepared_run_id = cast("str", admission_record["run_id"])
            record = self._load_run_record(prepared_run_id)
            if (
                admission_record.get("request_digest") != request_digest
                or record.run_id != prepared_run_id
                or record.target_id != profile.target_id
                or record.profile_id != profile.profile_id
                or record.policy_revision != profile.policy_revision
                or record.profile_digest != profile_digest
            ):
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_PREPARED_ADMISSION_BINDING",
                    "prepared-admission-mismatch",
                    policy_revision=profile.policy_revision,
                    run_id=prepared_run_id,
                    source_manifest_digest=record.manifest_digest,
                )
            manifest = self._load_snapshot(record, profile)
        else:
            manifest = self._build_snapshot(profile, deadline)
            self._write_or_validate_run_record(
                manifest,
                profile,
                profile_digest,
                dry_run_passed=False,
                write_in_progress=False,
                reservation_ref=None,
                replicated=False,
                receipt_id=None,
            )

        if request.operation is InfraOperation.REPLICATE:
            self._revalidate_profile_before_write(
                request,
                profile,
                profile_digest=profile_digest,
                principal_ref=principal_ref,
                approval_ref=approval_ref,
            )
            record = self._load_run_record(manifest.digest_to_run_id())
            if record.replicated:
                raise InfraBrokerError(
                    InfraReasonCode.RUN_ALREADY_REPLICATED,
                    "VERIFY_EXISTING_RUN_BEFORE_NEW_WRITE",
                    "run-already-replicated",
                    policy_revision=profile.policy_revision,
                    run_id=record.run_id,
                    source_manifest_digest=record.manifest_digest,
                )
            if record.write_in_progress and not (
                admission_record is not None
                and admission_record.get("status") == "prepared"
                and admission_record.get("idempotency_key_ref") == key_ref
                and admission_record.get("run_id") == record.run_id
                and admission_record.get("source_manifest_digest") == record.manifest_digest
            ):
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                    "run-write-in-progress",
                    policy_revision=profile.policy_revision,
                    run_id=record.run_id,
                    source_manifest_digest=record.manifest_digest,
                )
            if profile.dry_run_policy == "required" and (
                not record.dry_run_passed
                or not self._has_durable_receipt(
                    record.dry_run_receipt_id or record.receipt_id,
                    request=request,
                    operation=InfraOperation.RSYNC_DRY_RUN,
                    run_id=record.run_id,
                )
            ):
                raise InfraBrokerError(
                    InfraReasonCode.DRY_RUN_REQUIRED,
                    "RUN_RSYNC_DRY_RUN",
                    "dry-run-required",
                    policy_revision=profile.policy_revision,
                    run_id=record.run_id,
                    source_manifest_digest=record.manifest_digest,
                )
            if key_ref is None:
                raise InfraBrokerError(
                    InfraReasonCode.IDEMPOTENCY_CONFLICT,
                    "ISSUE_IDEMPOTENCY_KEY",
                    "idempotency-unavailable",
                    policy_revision=profile.policy_revision,
                )
            admission_record = self._prepare_admission(
                request_digest=request_digest,
                record=record,
                profile=profile,
                profile_digest=profile_digest,
                key_ref=key_ref,
                principal_ref=principal_ref,
                approval_ref=approval_ref,
                owner_token=admission_owner_token,
            )
            if admission_record.get("status") != "prepared":
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_CORRUPT_ADMISSION_RECORD",
                    "admission-record-invalid",
                    policy_revision=profile.policy_revision,
                    run_id=record.run_id,
                    source_manifest_digest=record.manifest_digest,
                )
            if not recovering_prepared_admission:
                self._claim_idempotency(
                    key_ref,
                    principal_ref,
                    request_digest,
                    record,
                    owner_token=admission_owner_token,
                )
                idempotency_claimed_by_attempt = True
            else:
                self._claim_idempotency(
                    key_ref,
                    principal_ref,
                    request_digest,
                    record,
                    owner_token=admission_owner_token,
                    allow_existing_in_progress=True,
                )
            approval_claimed = False
            run_reserved = record.write_in_progress
            try:
                if profile.approval_policy == "explicit":
                    approval_ref = self._validate_approval(request, profile, principal_ref)
                    if approval_ref is None:
                        raise InfraBrokerError(
                            InfraReasonCode.APPROVAL_REQUIRED,
                            "RESOLVE_OPERATOR_APPROVAL",
                            "auth-required",
                            policy_revision=profile.policy_revision,
                        )
                if profile.approval_policy == "explicit" and approval_ref is not None:
                    self._claim_one_time_approval(
                        approval_ref,
                        profile.policy_revision,
                        reservation_ref=key_ref,
                        owner_token=admission_owner_token,
                    )
                    approval_claimed = True
                self._revalidate_profile_before_write(
                    request,
                    profile,
                    profile_digest=profile_digest,
                    principal_ref=principal_ref,
                    approval_ref=approval_ref,
                )
                if not record.write_in_progress:
                    self._reserve_run_for_write(
                        manifest,
                        profile,
                        profile_digest,
                        key_ref,
                        principal_ref=principal_ref,
                        owner_token=admission_owner_token,
                    )
                    run_reserved = True
                else:
                    self._rebind_run_reservation(
                        manifest,
                        profile,
                        profile_digest,
                        key_ref,
                        principal_ref=principal_ref,
                        owner_token=admission_owner_token,
                    )
                self._mark_admission_started(
                    key_ref, principal_ref, owner_token=admission_owner_token
                )
            except InfraBrokerError:
                if run_reserved:
                    self._release_pre_execution_reservation(
                        manifest,
                        profile,
                        profile_digest,
                        key_ref,
                        principal_ref,
                        approval_ref=approval_ref,
                        owner_token=admission_owner_token,
                    )
                elif idempotency_claimed_by_attempt:
                    self._discard_idempotency_reservation(
                        key_ref, principal_ref, owner_token=admission_owner_token
                    )
                    if (
                        approval_claimed
                        and approval_ref is not None
                        and self._admission_owned(key_ref, principal_ref, admission_owner_token)
                    ):
                        self._release_one_time_approval(
                            approval_ref,
                            profile.policy_revision,
                            reservation_ref=key_ref,
                            owner_token=admission_owner_token,
                        )
                    self._delete_admission(
                        key_ref, principal_ref, owner_token=admission_owner_token
                    )
                raise

        execution_started = False
        execution_effect_started = False

        def mark_execution_started() -> None:
            nonlocal execution_started
            execution_started = True

        def mark_execution_effect_started() -> None:
            nonlocal execution_effect_started
            execution_effect_started = True

        try:
            response = self._execute_operation(
                request,
                profile,
                principal_ref=principal_ref,
                approval_ref=approval_ref,
                manifest=manifest,
                deadline=deadline,
                execution_started=mark_execution_started,
                execution_effect_started=mark_execution_effect_started,
            )
        except Exception:
            if (
                request.operation is InfraOperation.REPLICATE
                and key_ref is not None
                and not execution_effect_started
            ):
                self._release_pre_execution_reservation(
                    manifest,
                    profile,
                    profile_digest,
                    key_ref,
                    principal_ref,
                    approval_ref=approval_ref,
                    owner_token=admission_owner_token,
                )
            raise

        if (
            request.operation is InfraOperation.REPLICATE
            and response.status is InfraResponseStatus.OK
            and time.monotonic() >= deadline
        ):
            raise self._timeout_error(profile, manifest)

        if request.operation is InfraOperation.RSYNC_DRY_RUN:
            self._write_or_validate_run_record(
                manifest,
                profile,
                profile_digest,
                dry_run_passed=response.status is InfraResponseStatus.OK,
                write_in_progress=False,
                reservation_ref=None,
                replicated=False,
                receipt_id=response.receipt.receipt_id,
                dry_run_receipt_id=response.receipt.receipt_id,
            )
        elif (
            request.operation is InfraOperation.REPLICATE
            and isinstance(response.receipt, InfraCapabilityBlockReceipt)
            and response.receipt.reason_code is InfraReasonCode.MISSING_EXECUTION_CAPABILITY
            and key_ref is not None
            and not execution_effect_started
        ):
            # No subprocess was started for PROCESS_UNAVAILABLE, so this
            # pre-effect reservation may be released and retried after the
            # fixed runtime is repaired. Unknown/partial outcomes never enter
            # this branch.
            self._release_pre_execution_reservation(
                manifest,
                profile,
                profile_digest,
                key_ref,
                principal_ref,
                approval_ref=approval_ref,
                owner_token=admission_owner_token,
            )
        elif (
            request.operation is InfraOperation.REPLICATE
            and response.status is InfraResponseStatus.OK
            and key_ref is not None
        ):
            try:
                if not self._record_receipt(response):
                    raise InfraBrokerError(
                        InfraReasonCode.UNKNOWN_COMPLETION,
                        "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                        "completion-record-unavailable",
                        policy_revision=profile.policy_revision,
                        run_id=manifest.digest_to_run_id(),
                        source_manifest_digest=manifest.digest,
                    )
                self._write_or_validate_run_record(
                    manifest,
                    profile,
                    profile_digest,
                    dry_run_passed=True,
                    write_in_progress=False,
                    reservation_ref=key_ref,
                    reservation_principal_ref=principal_ref,
                    reservation_owner_token=admission_owner_token,
                    replicated=True,
                    receipt_id=response.receipt.receipt_id,
                )
                self._complete_idempotency(
                    key_ref, principal_ref, response, owner_token=admission_owner_token
                )
                self._delete_admission(key_ref, principal_ref, owner_token=admission_owner_token)
            except (OSError, ValueError, ValidationError) as exc:
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                    "completion-record-unavailable",
                    policy_revision=profile.policy_revision,
                    run_id=manifest.digest_to_run_id(),
                    source_manifest_digest=manifest.digest,
                ) from exc
        elif (
            request.operation is InfraOperation.VERIFY
            and response.status is InfraResponseStatus.OK
            and isinstance(response.receipt, InfraOperationReceipt)
            and response.receipt.verification_result == "inventory-matched"
        ):
            self._resolve_verified_run(
                manifest,
                profile,
                profile_digest=profile_digest,
                principal_ref=principal_ref,
                response=response,
            )
        return response

    def _status_response(self, principal_ref: str) -> InfraResponse:
        request = InfraRequest(operation=InfraOperation.STATUS)
        try:
            policy = load_infra_policy(self.policy_path)
        except FileNotFoundError:
            return self._operation_response(
                request,
                principal_ref=principal_ref,
                policy_revision="none",
                data={
                    "broker_status": "active-profile-missing",
                    "transport": "unix",
                    "principal_source": "SO_PEERCRED"
                    if _PEER_CREDENTIALS is not None
                    else "getpeereid",
                    "profiles": [],
                    "ready": False,
                },
                exit_category=InfraExitCategory.SUCCESS,
                transport="unix",
                dry_run=True,
                verification_result="status",
            )
        except (OSError, ValueError, json.JSONDecodeError):
            return _block_response(
                request,
                InfraReasonCode.POLICY_INVALID,
                broker_status="policy-invalid",
                remediation_code="REPAIR_OPERATOR_POLICY",
            )

        profiles: list[InfraProfileStatus] = []
        for profile in policy.profiles:
            credential_status, credential_source = self._credential_status(profile)
            verify_credential_status = (
                "not-configured"
                if profile.verify_credential_id is None
                else self._credential_status(profile, credential_id=profile.verify_credential_id)[0]
            )
            host_status = self._host_key_status(profile)
            verify_ready = (
                InfraOperation.VERIFY not in profile.allowed_operations
                or verify_credential_status == "available"
            )
            if credential_status == "available" and host_status == "pinned" and verify_ready:
                profile_status: Literal[
                    "ready", "credential-missing", "host-key-missing", "invalid"
                ] = "ready"
            elif credential_status != "available":
                profile_status = "credential-missing"
            elif host_status == "missing":
                profile_status = "host-key-missing"
            else:
                profile_status = "invalid"
            profiles.append(
                InfraProfileStatus(
                    profile_id=profile.profile_id,
                    target_id=profile.target_id,
                    policy_revision=profile.policy_revision,
                    allowed_operations=list(profile.allowed_operations),
                    credential_status=credential_status,
                    credential_source=credential_source,
                    verify_credential_status=verify_credential_status,
                    host_identity_status=host_status,
                    profile_status=profile_status,
                    approval_policy=profile.approval_policy,
                )
            )
        ready = bool(profiles) and all(item.profile_status == "ready" for item in profiles)
        broker_status = "fully-ready" if ready else "active-profile-incomplete"
        return self._operation_response(
            request,
            principal_ref=principal_ref,
            policy_revision="multi" if len(profiles) != 1 else profiles[0].policy_revision,
            data={
                "broker_status": broker_status,
                "transport": "unix",
                "principal_source": "SO_PEERCRED"
                if _PEER_CREDENTIALS is not None
                else "getpeereid",
                "profiles": [item.model_dump(mode="json") for item in profiles],
                "ready": ready,
            },
            exit_category=InfraExitCategory.SUCCESS,
            transport="unix",
            dry_run=True,
            verification_result="status",
        )

    def _credential_candidate(
        self, profile: InfraProfile, *, credential_id: str | None = None
    ) -> tuple[Path, _CredentialMaterial]:
        directory = self.credential_dir
        try:
            _assert_secure_directory(directory)
        except FileNotFoundError as exc:
            raise InfraBrokerError(
                InfraReasonCode.BROKER_CREDENTIAL_UNAVAILABLE,
                "INSTALL_BROKER_CREDENTIAL",
                "credential-unavailable",
                policy_revision=profile.policy_revision,
            ) from exc
        except ValueError as exc:
            raise InfraBrokerError(
                InfraReasonCode.BROKER_CREDENTIAL_UNAVAILABLE,
                "REPAIR_CREDENTIAL_DIRECTORY",
                "credential-unavailable",
                policy_revision=profile.policy_revision,
            ) from exc
        selected_credential_id = credential_id or profile.credential_id
        candidate = directory / selected_credential_id
        try:
            _assert_no_symlink_components(candidate)
            candidate.resolve(strict=True).relative_to(directory.resolve(strict=True))
            _read_secure_file(candidate, max_bytes=MAX_CREDENTIAL_BYTES, private=True)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise InfraBrokerError(
                InfraReasonCode.BROKER_CREDENTIAL_UNAVAILABLE,
                "INSTALL_OR_REPAIR_BROKER_CREDENTIAL",
                "credential-unavailable",
                policy_revision=profile.policy_revision,
            ) from exc
        source = self.credential_source
        if source == "plaintext-fallback" and not profile.allow_plaintext_credential_fallback:
            raise InfraBrokerError(
                InfraReasonCode.BROKER_CREDENTIAL_UNAVAILABLE,
                "ENABLE_ONLY_OPERATOR_APPROVED_CREDENTIAL_FALLBACK",
                "plaintext-credential-fallback-disabled",
                policy_revision=profile.policy_revision,
            )
        return candidate, _CredentialMaterial(path=candidate, source=source)

    def _credential_status(
        self, profile: InfraProfile, *, credential_id: str | None = None
    ) -> tuple[
        Literal["available", "missing", "invalid"],
        Literal["systemd-loadcredential", "configured", "plaintext-fallback", "missing"],
    ]:
        try:
            _, material = self._credential_candidate(profile, credential_id=credential_id)
            return "available", material.source
        except InfraBrokerError:
            return "missing", "missing"

    def _host_key_status(
        self, profile: InfraProfile
    ) -> Literal["pinned", "missing", "mismatch", "invalid"]:
        try:
            self._read_and_validate_known_hosts(profile)
        except FileNotFoundError:
            return "missing"
        except InfraBrokerError as error:
            if error.reason_code is InfraReasonCode.HOST_IDENTITY_MISMATCH:
                return "mismatch"
            return "invalid"
        except (OSError, ValueError, UnicodeError):
            return "invalid"
        return "pinned"

    def _require_host_key(self, profile: InfraProfile) -> bytes:
        """Convert trust-file failures into a typed capability block."""

        try:
            return self._read_and_validate_known_hosts(profile)
        except InfraBrokerError:
            raise
        except FileNotFoundError as exc:
            raise InfraBrokerError(
                InfraReasonCode.HOST_IDENTITY_UNTRUSTED,
                "INSTALL_OPERATOR_HOST_KEY_PIN",
                "host-identity-untrusted",
                policy_revision=profile.policy_revision,
            ) from exc
        except (OSError, ValueError, UnicodeError) as exc:
            raise InfraBrokerError(
                InfraReasonCode.HOST_IDENTITY_UNTRUSTED,
                "REPAIR_DEDICATED_HOST_KEY_FILE",
                "host-identity-untrusted",
                policy_revision=profile.policy_revision,
            ) from exc

    def _read_and_validate_known_hosts(self, profile: InfraProfile) -> bytes:
        """Require one exact host/port entry and one exact pinned key."""

        raw = _read_secure_file(
            Path(profile.known_hosts_file),
            max_bytes=MAX_KNOWN_HOSTS_BYTES,
            private=False,
        )
        if b"\r" in raw or any(byte < 32 and byte not in {9, 10} for byte in raw):
            raise InfraBrokerError(
                InfraReasonCode.HOST_IDENTITY_UNTRUSTED,
                "REPAIR_DEDICATED_HOST_KEY_FILE",
                "host-identity-untrusted",
                policy_revision=profile.policy_revision,
            )
        text = raw.decode("utf-8")
        expected_host = (
            profile.hostname if profile.port == 22 else f"[{profile.hostname}]:{profile.port}"
        )
        entries: list[bytes] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            fields = stripped.split()
            if len(fields) < 3 or fields[0].startswith(("@", "|")):
                raise InfraBrokerError(
                    InfraReasonCode.HOST_IDENTITY_UNTRUSTED,
                    "REPAIR_DEDICATED_HOST_KEY_FILE",
                    "host-identity-untrusted",
                    policy_revision=profile.policy_revision,
                )
            hosts = fields[0].split(",")
            if len(hosts) != 1 or hosts[0] != expected_host:
                raise InfraBrokerError(
                    InfraReasonCode.HOST_IDENTITY_MISMATCH,
                    "OPERATOR_REPLACE_HOST_KEY_PIN",
                    "host-identity-mismatch",
                    policy_revision=profile.policy_revision,
                )
            if any(char in fields[0] for char in "*!?"):
                raise InfraBrokerError(
                    InfraReasonCode.HOST_IDENTITY_UNTRUSTED,
                    "REMOVE_HOST_KEY_PATTERNS",
                    "host-identity-untrusted",
                    policy_revision=profile.policy_revision,
                )
            if not fields[1].startswith(
                ("ssh-ed25519", "ssh-rsa", "rsa-sha2-", "ecdsa-sha2-", "sk-")
            ):
                raise InfraBrokerError(
                    InfraReasonCode.HOST_IDENTITY_UNTRUSTED,
                    "REPAIR_DEDICATED_HOST_KEY_FILE",
                    "host-identity-untrusted",
                    policy_revision=profile.policy_revision,
                )
            try:
                key_blob = base64.b64decode(fields[2], validate=True)
            except (ValueError, TypeError) as exc:
                raise InfraBrokerError(
                    InfraReasonCode.HOST_IDENTITY_UNTRUSTED,
                    "REPAIR_DEDICATED_HOST_KEY_FILE",
                    "host-identity-untrusted",
                    policy_revision=profile.policy_revision,
                ) from exc
            if ssh_fingerprint_from_blob(key_blob) != profile.host_key_fingerprint:
                raise InfraBrokerError(
                    InfraReasonCode.HOST_IDENTITY_MISMATCH,
                    "OPERATOR_REPLACE_HOST_KEY_PIN",
                    "host-identity-mismatch",
                    policy_revision=profile.policy_revision,
                )
            entries.append(key_blob)
        if len(entries) != 1:
            raise InfraBrokerError(
                InfraReasonCode.HOST_IDENTITY_UNTRUSTED,
                "INSTALL_ONE_EXACT_HOST_KEY_PIN",
                "host-identity-untrusted",
                policy_revision=profile.policy_revision,
            )
        return raw

    def _validate_approval(
        self,
        request: InfraRequest,
        profile: InfraProfile,
        principal_ref: str,
    ) -> str | None:
        if request.operation is not InfraOperation.REPLICATE:
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
        try:
            approvals = load_infra_approvals(self.approval_path)
        except FileNotFoundError:
            approvals = {}
        except (OSError, ValueError, ValidationError):
            raise InfraBrokerError(
                InfraReasonCode.APPROVAL_REQUIRED,
                "REPAIR_OPERATOR_APPROVAL_REGISTRY",
                "approval-registry-invalid",
                policy_revision=profile.policy_revision,
            ) from None
        record = approvals.get(request.approval_ref)
        if record is None:
            raise InfraBrokerError(
                InfraReasonCode.APPROVAL_REQUIRED,
                "RESOLVE_OPERATOR_APPROVAL",
                "auth-required",
                policy_revision=profile.policy_revision,
            )
        try:
            expires_at = datetime_from_iso(record.expires_at)
        except ValueError:
            raise InfraBrokerError(
                InfraReasonCode.APPROVAL_REQUIRED,
                "REISSUE_INVALID_APPROVAL",
                "auth-required",
                policy_revision=profile.policy_revision,
            ) from None
        if expires_at <= datetime_now_utc():
            raise InfraBrokerError(
                InfraReasonCode.APPROVAL_REQUIRED,
                "REISSUE_EXPIRED_APPROVAL",
                "auth-required",
                policy_revision=profile.policy_revision,
            )
        expected = {
            "operation": request.operation,
            "target_id": profile.target_id,
            "profile_id": profile.profile_id,
            "policy_revision": profile.policy_revision,
            "profile_digest": canonical_profile_digest(profile),
            "principal_ref": principal_ref,
        }
        if any(getattr(record, key) != value for key, value in expected.items()):
            raise InfraBrokerError(
                InfraReasonCode.APPROVAL_REQUIRED,
                "REISSUE_EXACT_PROFILE_APPROVAL",
                "auth-required",
                policy_revision=profile.policy_revision,
            )
        return record.approval_ref

    def _revalidate_profile_before_write(
        self,
        request: InfraRequest,
        profile: InfraProfile,
        *,
        profile_digest: str,
        principal_ref: str,
        approval_ref: str | None,
    ) -> None:
        """Re-read operator policy immediately before a write-side admission."""

        try:
            policy = load_infra_policy(self.policy_path)
        except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
            raise InfraBrokerError(
                InfraReasonCode.POLICY_INVALID,
                "REPAIR_OPERATOR_POLICY",
                "policy-invalid",
                policy_revision=profile.policy_revision,
            ) from exc
        current = next(
            (item for item in policy.profiles if item.profile_id == profile.profile_id), None
        )
        if current is None or canonical_profile_digest(current) != profile_digest:
            raise InfraBrokerError(
                InfraReasonCode.POLICY_INVALID,
                "RELOAD_PROFILE_AND_REBUILD_SNAPSHOT",
                "profile-changed-during-admission",
                policy_revision=profile.policy_revision,
            )
        if self._validate_approval(request, current, principal_ref) != approval_ref:
            raise InfraBrokerError(
                InfraReasonCode.APPROVAL_REQUIRED,
                "REISSUE_EXACT_PROFILE_APPROVAL",
                "approval-changed-during-admission",
                policy_revision=profile.policy_revision,
            )

    def _claim_one_time_approval(
        self,
        approval_ref: str,
        policy_revision: str,
        *,
        reservation_ref: str,
        owner_token: str | None = None,
    ) -> None:
        self._ensure_state_layout()
        marker = self.state_dir / "approval-uses" / hashlib_sha256(approval_ref.encode("utf-8"))
        with self._state_lock, self._state_file_lock():
            marker_data: dict[str, object] = {
                "approval_ref": approval_ref,
                "policy_revision": policy_revision,
                "reservation_ref": reservation_ref,
            }
            if owner_token is not None:
                if not _ADMISSION_TOKEN_PATTERN.fullmatch(owner_token):
                    raise ValueError("admission owner token is invalid")
                marker_data["owner_token"] = owner_token
            marker_payload = _json_bytes(marker_data)
            try:
                _write_bounded_file(marker, marker_payload, mode=0o600)
            except FileExistsError:
                try:
                    existing = json.loads(
                        _read_secure_file(marker, max_bytes=MAX_RECEIPT_BYTES, private=True).decode(
                            "utf-8"
                        ),
                        object_pairs_hook=_reject_duplicate_json_keys,
                    )
                except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise InfraBrokerError(
                        InfraReasonCode.APPROVAL_REPLAY,
                        "ISSUE_NEW_EXACT_APPROVAL",
                        "approval-replayed",
                        policy_revision=policy_revision,
                    ) from exc
                expected_existing = json.loads(marker_payload.decode("utf-8"))
                if existing == expected_existing:
                    return
                if (
                    owner_token is not None
                    and isinstance(existing, dict)
                    and existing.get("approval_ref") == approval_ref
                    and existing.get("policy_revision") == policy_revision
                    and existing.get("reservation_ref") == reservation_ref
                ):
                    _atomic_write(marker, marker_payload)
                    return
                raise InfraBrokerError(
                    InfraReasonCode.APPROVAL_REPLAY,
                    "ISSUE_NEW_EXACT_APPROVAL",
                    "approval-replayed",
                    policy_revision=policy_revision,
                ) from None
            except (OSError, ValueError) as exc:
                raise InfraBrokerError(
                    InfraReasonCode.APPROVAL_REQUIRED,
                    "REPAIR_APPROVAL_USAGE_STATE",
                    "approval-state-unavailable",
                    policy_revision=policy_revision,
                ) from exc

    def _build_snapshot(self, profile: InfraProfile, deadline: float) -> _Manifest:
        self._ensure_state_layout()
        self._ensure_snapshot_capacity(profile)
        self._validate_source_roots(profile)
        snapshots = self.state_dir / "snapshots"
        staging = snapshots / f".staging-{uuid.uuid4().hex}"
        staging.mkdir(mode=0o700)
        entries: list[dict[str, object]] = []
        directories: list[dict[str, object]] = []
        source_dirs: list[Path] = []
        total_bytes = 0
        total_entries = 0
        try:
            for root_index, root_text in enumerate(profile.source_roots):
                if time.monotonic() >= deadline:
                    raise self._timeout_error(profile)
                root = Path(root_text)
                destination_root = staging / f"source-{root_index:03d}"
                destination_root.mkdir(mode=0o700)
                source_dirs.append(destination_root)
                root_entries, root_bytes, root_entry_count, root_directories = (
                    _snapshot_source_root(
                        root,
                        destination_root,
                        root_index=root_index,
                        max_entries=profile.max_files - total_entries,
                        remaining_bytes=profile.max_bytes - total_bytes,
                        deadline=deadline,
                    )
                )
                entries.extend(root_entries)
                directories.extend(
                    {"root": root_index, "path": relative} for relative in root_directories
                )
                total_bytes += root_bytes
                total_entries += root_entry_count
            profile_digest = canonical_profile_digest(profile)
            manifest_payload = {
                "profile_digest": profile_digest,
                "target_id": profile.target_id,
                "policy_revision": profile.policy_revision,
                "control_files": ["source-000/.power-infra-run.json"],
                "entries": entries,
                "directories": directories,
            }
            digest = hashlib_sha256(_json_bytes(manifest_payload))
            run_id = f"run_{digest}"
            marker = {
                "schema_version": "power.infra-run.v1",
                "run_id": run_id,
                "profile_digest": profile_digest,
                "target_id": profile.target_id,
                "policy_revision": profile.policy_revision,
                "manifest_digest": digest,
                "file_count": len(entries),
                "byte_count": total_bytes,
            }
            _write_bounded_file(
                staging / "source-000" / ".power-infra-run.json",
                _json_bytes(marker),
                mode=0o600,
            )
            manifest_file = staging / "manifest.json"
            _write_bounded_file(manifest_file, _json_bytes(manifest_payload), mode=0o600)
            _fsync_directory_tree(staging)
            final_dir = snapshots / run_id
            if final_dir.exists():
                if final_dir.is_symlink():
                    raise ValueError("snapshot destination must not be a symlink")
                _remove_tree_and_fsync(staging)
                existing = self._load_snapshot_manifest(final_dir, profile)
                if existing.digest != digest:
                    raise InfraBrokerError(
                        InfraReasonCode.UNKNOWN_COMPLETION,
                        "RESOLVE_SNAPSHOT_COLLISION",
                        "snapshot-collision",
                        policy_revision=profile.policy_revision,
                        run_id=run_id,
                        source_manifest_digest=digest,
                    )
                return existing
            os.replace(staging, final_dir)
            _fsync_directory(snapshots)
            return _Manifest(
                digest=digest,
                file_count=len(entries),
                byte_count=total_bytes,
                snapshot_dir=final_dir,
                source_dirs=tuple(
                    final_dir / f"source-{index:03d}" for index in range(len(source_dirs))
                ),
            )
        except InfraBrokerError:
            with suppress(OSError):
                _remove_tree_and_fsync(staging)
            raise
        except TimeoutError as exc:
            with suppress(OSError):
                _remove_tree_and_fsync(staging)
            raise InfraBrokerError(
                InfraReasonCode.TIMEOUT,
                "LOWER_PROFILE_TIMEOUT",
                "snapshot-timeout",
                policy_revision=profile.policy_revision,
            ) from exc
        except (OSError, ValueError, UnicodeError) as exc:
            with suppress(OSError):
                _remove_tree_and_fsync(staging)
            raise InfraBrokerError(
                InfraReasonCode.RESOURCE_LIMIT,
                "REMOVE_UNSAFE_SOURCE_ENTRY_OR_REPAIR_SOURCE_ROOT",
                "source-invalid",
                policy_revision=profile.policy_revision,
            ) from exc

    def _validate_source_roots(self, profile: InfraProfile) -> None:
        sensitive = [
            self.credential_dir,
            self.state_dir,
            self.policy_path,
            self.approval_path,
            Path(profile.known_hosts_file),
        ]
        resolved_sensitive: list[Path] = []
        for path in sensitive:
            with suppress(OSError, ValueError):
                _assert_no_symlink_components(path)
                resolved_sensitive.append(path.resolve(strict=False))
        for source_text in profile.source_roots:
            source = Path(source_text)
            try:
                _assert_no_symlink_components(source)
            except (OSError, ValueError) as exc:
                raise InfraBrokerError(
                    InfraReasonCode.POLICY_INVALID,
                    "REMOVE_SYMLINKED_SOURCE_ROOT",
                    "source-root-invalid",
                    policy_revision=profile.policy_revision,
                ) from exc
            source = source.absolute()
            for forbidden in resolved_sensitive:
                if (
                    source == forbidden
                    or source.is_relative_to(forbidden)
                    or forbidden.is_relative_to(source)
                ):
                    raise InfraBrokerError(
                        InfraReasonCode.POLICY_INVALID,
                        "SEPARATE_SOURCE_FROM_BROKER_TRUST_PATHS",
                        "source-overlaps-trust-path",
                        policy_revision=profile.policy_revision,
                    )

    def _ensure_snapshot_capacity(self, profile: InfraProfile) -> None:
        """Apply aggregate snapshot and filesystem-free-space ceilings."""

        snapshots = self.state_dir / "snapshots"
        used = 0
        for path in snapshots.rglob("*"):
            if path.is_symlink():
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "REPAIR_BROKER_SNAPSHOT_STATE",
                    "snapshot-state-invalid",
                    policy_revision=profile.policy_revision,
                )
            if path.is_file():
                try:
                    used += path.stat().st_size
                except OSError as exc:
                    raise InfraBrokerError(
                        InfraReasonCode.RESOURCE_LIMIT,
                        "REPAIR_BROKER_SNAPSHOT_STATE",
                        "snapshot-state-unavailable",
                        policy_revision=profile.policy_revision,
                    ) from exc
                if used > MAX_SNAPSHOT_STATE_BYTES:
                    raise InfraBrokerError(
                        InfraReasonCode.RESOURCE_LIMIT,
                        "RESOLVE_OLD_BROKER_SNAPSHOTS",
                        "snapshot-capacity-exhausted",
                        policy_revision=profile.policy_revision,
                    )
        try:
            free_bytes = shutil.disk_usage(snapshots).free
        except OSError as exc:
            raise InfraBrokerError(
                InfraReasonCode.RESOURCE_LIMIT,
                "INSPECT_BROKER_FILESYSTEM_CAPACITY",
                "snapshot-capacity-unavailable",
                policy_revision=profile.policy_revision,
            ) from exc
        if free_bytes < min(profile.max_bytes, MAX_SNAPSHOT_STATE_BYTES) + MIN_SNAPSHOT_FREE_BYTES:
            raise InfraBrokerError(
                InfraReasonCode.RESOURCE_LIMIT,
                "LOWER_PROFILE_SIZE_OR_FREE_BROKER_STORAGE",
                "snapshot-free-space-limit",
                policy_revision=profile.policy_revision,
            )

    def _load_snapshot_manifest(self, snapshot_dir: Path, profile: InfraProfile) -> _Manifest:
        try:
            _assert_secure_directory(snapshot_dir, private=True)
            raw = _read_secure_file(
                snapshot_dir / "manifest.json", max_bytes=MAX_STATE_BYTES, private=True
            )
            payload = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_json_keys,
                parse_constant=_reject_json_constant,
            )
            if (
                not isinstance(payload, dict)
                or set(payload)
                != {
                    "profile_digest",
                    "target_id",
                    "policy_revision",
                    "control_files",
                    "entries",
                    "directories",
                }
                or not isinstance(payload.get("entries"), list)
                or not isinstance(payload.get("directories"), list)
                or payload.get("control_files") != ["source-000/.power-infra-run.json"]
            ):
                raise ValueError("invalid snapshot manifest")
            entries = cast("list[object]", payload["entries"])
            profile_digest = payload.get("profile_digest")
            target_id = payload.get("target_id")
            revision = payload.get("policy_revision")
            if (
                profile_digest != canonical_profile_digest(profile)
                or target_id != profile.target_id
                or revision != profile.policy_revision
            ):
                raise ValueError("snapshot profile binding changed")
            for entry in cast("list[object]", payload["entries"]):
                if not isinstance(entry, dict) or set(entry) != {"root", "path", "size", "sha256"}:
                    raise ValueError("snapshot manifest entry is invalid")
                if (
                    type(entry.get("root")) is not int
                    or not 0 <= cast("int", entry["root"]) < len(profile.source_roots)
                    or not isinstance(entry.get("path"), str)
                    or not isinstance(entry.get("sha256"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", cast("str", entry["sha256"]))
                ):
                    raise ValueError("snapshot manifest entry is invalid")
                _validate_relative_source_path(cast("str", entry["path"]))
            directories = cast("list[object]", payload["directories"])
            observed_directories: set[tuple[int, str]] = set()
            for directory in directories:
                if not isinstance(directory, dict) or set(directory) != {"root", "path"}:
                    raise ValueError("snapshot directory entry is invalid")
                root_index = directory.get("root")
                relative = directory.get("path")
                if (
                    type(root_index) is not int
                    or not 0 <= root_index < len(profile.source_roots)
                    or not isinstance(relative, str)
                ):
                    raise ValueError("snapshot directory entry is invalid")
                _validate_relative_source_path(relative)
                key = (root_index, relative)
                if key in observed_directories:
                    raise ValueError("snapshot manifest contains duplicate directories")
                observed_directories.add(key)
            if any(
                (entry.get("root"), entry.get("path")) in observed_directories
                for entry in entries
                if isinstance(entry, dict)
            ):
                raise ValueError("snapshot manifest file/directory collision")
            digest = hashlib_sha256(_json_bytes(payload))
            sizes: list[int] = []
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("size"), int):
                    raise ValueError("snapshot manifest entry size is invalid")
                sizes.append(cast("int", entry["size"]))
            total = sum(sizes)
            if len(entries) + len(directories) > profile.max_files or total > profile.max_bytes:
                raise ValueError("snapshot exceeds profile bounds")
            source_dirs = tuple(
                snapshot_dir / f"source-{index:03d}" for index in range(len(profile.source_roots))
            )
            if any(not directory.is_dir() or directory.is_symlink() for directory in source_dirs):
                raise ValueError("snapshot source directory is incomplete")
            marker_raw = _read_secure_file(
                source_dirs[0] / ".power-infra-run.json",
                max_bytes=MAX_RECEIPT_BYTES,
                private=True,
            )
            marker = json.loads(
                marker_raw.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_json_keys,
                parse_constant=_reject_json_constant,
            )
            if (
                not isinstance(marker, dict)
                or set(marker)
                != {
                    "schema_version",
                    "run_id",
                    "profile_digest",
                    "target_id",
                    "policy_revision",
                    "manifest_digest",
                    "file_count",
                    "byte_count",
                }
                or marker.get("schema_version") != "power.infra-run.v1"
                or marker.get("run_id") != f"run_{digest}"
                or marker.get("profile_digest") != profile_digest
                or marker.get("target_id") != target_id
                or marker.get("policy_revision") != revision
                or marker.get("manifest_digest") != digest
                or marker.get("file_count") != len(entries)
                or marker.get("byte_count") != total
            ):
                raise ValueError("snapshot run marker binding changed")
            return _Manifest(
                digest=digest,
                file_count=len(entries),
                byte_count=total,
                snapshot_dir=snapshot_dir,
                source_dirs=source_dirs,
            )
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_INCOMPLETE_BROKER_SNAPSHOT",
                "snapshot-invalid",
                policy_revision=profile.policy_revision,
            ) from exc

    def _load_run_record(self, run_id: str) -> _RunRecord:
        if not run_id:
            raise InfraBrokerError(
                InfraReasonCode.RUN_NOT_FOUND,
                "RESOLVE_OPERATOR_RUN_RECEIPT",
                "run-not-found",
            )
        self._ensure_state_layout()
        path = self.state_dir / "runs" / f"{run_id}.json"
        try:
            raw = _read_secure_file(path, max_bytes=MAX_RECEIPT_BYTES, private=True)
            payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
            if not isinstance(payload, dict):
                raise ValueError("run record is not an object")
            string_fields = (
                "run_id",
                "target_id",
                "profile_id",
                "policy_revision",
                "profile_digest",
                "manifest_digest",
            )
            if any(not isinstance(payload.get(field), str) for field in string_fields):
                raise ValueError("run record has invalid identifiers")
            if payload["run_id"] != run_id or not re.fullmatch(
                r"run_[0-9a-f]{64}", payload["run_id"]
            ):
                raise ValueError("run record has an invalid run identifier")
            if any(
                not re.fullmatch(r"[0-9a-f]{64}", cast("str", payload[field]))
                for field in ("profile_digest", "manifest_digest")
            ):
                raise ValueError("run record has an invalid digest")
            if any(
                not isinstance(payload.get(field), int) or isinstance(payload.get(field), bool)
                for field in ("file_count", "byte_count")
            ):
                raise ValueError("run record has invalid resource counts")
            if any(
                type(payload.get(field)) is not bool
                for field in ("dry_run_passed", "write_in_progress", "replicated")
            ):
                raise ValueError("run record has invalid state flags")
            reservation_ref = payload.get("reservation_ref")
            if reservation_ref is not None and not isinstance(reservation_ref, str):
                raise ValueError("run record has an invalid reservation reference")
            receipt_id = payload.get("receipt_id")
            dry_run_receipt_id = payload.get("dry_run_receipt_id")
            if receipt_id is not None and (
                not isinstance(receipt_id, str) or not re.fullmatch(r"ir_[0-9a-f]{64}", receipt_id)
            ):
                raise ValueError("run record has an invalid receipt reference")
            if dry_run_receipt_id is not None and (
                not isinstance(dry_run_receipt_id, str)
                or not re.fullmatch(r"ir_[0-9a-f]{64}", dry_run_receipt_id)
            ):
                raise ValueError("run record has an invalid dry-run receipt reference")
            if dry_run_receipt_id is None and not payload["replicated"]:
                dry_run_receipt_id = receipt_id
            reservation_principal_ref = payload.get("reservation_principal_ref")
            reservation_owner_token = payload.get("reservation_owner_token")
            if reservation_ref is None:
                if reservation_principal_ref is not None or reservation_owner_token is not None:
                    raise ValueError("run record has an unbound reservation identity")
            elif (
                not isinstance(reservation_principal_ref, str)
                or not re.fullmatch(_UID_PATTERN, reservation_principal_ref)
                or not isinstance(reservation_owner_token, str)
                or not _ADMISSION_TOKEN_PATTERN.fullmatch(reservation_owner_token)
            ):
                raise ValueError("run record has an invalid reservation identity")
            return _RunRecord(
                run_id=str(payload["run_id"]),
                target_id=str(payload["target_id"]),
                profile_id=str(payload["profile_id"]),
                policy_revision=str(payload["policy_revision"]),
                profile_digest=str(payload["profile_digest"]),
                manifest_digest=str(payload["manifest_digest"]),
                file_count=int(payload["file_count"]),
                byte_count=int(payload["byte_count"]),
                dry_run_passed=bool(payload["dry_run_passed"]),
                write_in_progress=bool(payload.get("write_in_progress", False)),
                reservation_ref=cast("str | None", payload.get("reservation_ref")),
                reservation_principal_ref=cast(
                    "str | None", payload.get("reservation_principal_ref")
                ),
                reservation_owner_token=cast("str | None", payload.get("reservation_owner_token")),
                replicated=bool(payload["replicated"]),
                receipt_id=receipt_id,
                dry_run_receipt_id=dry_run_receipt_id,
            )
        except (
            FileNotFoundError,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
        ) as exc:
            raise InfraBrokerError(
                InfraReasonCode.RUN_NOT_FOUND,
                "RESOLVE_OPERATOR_RUN_RECEIPT",
                "run-not-found",
            ) from exc

    def _validate_run_binding(
        self,
        record: _RunRecord,
        request: InfraRequest,
        profile: InfraProfile,
        profile_digest: str,
    ) -> None:
        if (
            record.run_id != request.run_id
            or record.target_id != profile.target_id
            or record.profile_id != profile.profile_id
            or record.policy_revision != profile.policy_revision
            or record.profile_digest != profile_digest
        ):
            raise InfraBrokerError(
                InfraReasonCode.RUN_NOT_FOUND,
                "RESOLVE_EXACT_PROFILE_RUN",
                "run-binding-mismatch",
                policy_revision=profile.policy_revision,
            )

    def _load_snapshot(self, record: _RunRecord, profile: InfraProfile) -> _Manifest:
        snapshot_dir = self.state_dir / "snapshots" / record.run_id
        manifest = self._load_snapshot_manifest(snapshot_dir, profile)
        if manifest.digest != record.manifest_digest:
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_SNAPSHOT_MANIFEST_DRIFT",
                "snapshot-digest-mismatch",
                policy_revision=profile.policy_revision,
                run_id=record.run_id,
                source_manifest_digest=record.manifest_digest,
            )
        return manifest

    def _write_or_validate_run_record(
        self,
        manifest: _Manifest,
        profile: InfraProfile,
        profile_digest: str,
        *,
        dry_run_passed: bool,
        write_in_progress: bool,
        reservation_ref: str | None,
        replicated: bool,
        receipt_id: str | None,
        dry_run_receipt_id: str | None = None,
        reservation_principal_ref: str | None = None,
        reservation_owner_token: str | None = None,
    ) -> None:
        self._ensure_state_layout()
        run_id = manifest.digest_to_run_id()
        path = self.state_dir / "runs" / f"{run_id}.json"
        with self._state_lock, self._state_file_lock():
            existing: _RunRecord | None = None
            if path.exists():
                existing = self._load_run_record(run_id)
                if (
                    existing.profile_digest != profile_digest
                    or existing.target_id != profile.target_id
                    or existing.profile_id != profile.profile_id
                    or existing.manifest_digest != manifest.digest
                ):
                    raise InfraBrokerError(
                        InfraReasonCode.UNKNOWN_COMPLETION,
                        "RESOLVE_RUN_BINDING_CONFLICT",
                        "run-binding-conflict",
                        policy_revision=profile.policy_revision,
                        run_id=run_id,
                        source_manifest_digest=manifest.digest,
                    )
            record = {
                "run_id": run_id,
                "target_id": profile.target_id,
                "profile_id": profile.profile_id,
                "policy_revision": profile.policy_revision,
                "profile_digest": profile_digest,
                "manifest_digest": manifest.digest,
                "file_count": manifest.file_count,
                "byte_count": manifest.byte_count,
                "dry_run_passed": (existing.dry_run_passed if existing else False)
                or dry_run_passed,
                "write_in_progress": (
                    write_in_progress
                    if reservation_ref is not None
                    else existing.write_in_progress
                    if existing
                    else False
                ),
                "reservation_ref": (
                    None
                    if replicated and not write_in_progress
                    else reservation_ref or (existing.reservation_ref if existing else None)
                ),
                "reservation_principal_ref": (
                    None
                    if replicated and not write_in_progress
                    else reservation_principal_ref
                    or (existing.reservation_principal_ref if existing else None)
                ),
                "reservation_owner_token": (
                    None
                    if replicated and not write_in_progress
                    else reservation_owner_token
                    or (existing.reservation_owner_token if existing else None)
                ),
                "replicated": (existing.replicated if existing else False) or replicated,
                "receipt_id": (
                    existing.receipt_id
                    if existing and existing.replicated
                    else receipt_id or (existing.receipt_id if existing else None)
                ),
                "dry_run_receipt_id": dry_run_receipt_id
                or (existing.dry_run_receipt_id if existing else None),
            }
            _atomic_write(path, _json_bytes(record))

    def _resolve_verified_run(
        self,
        manifest: _Manifest,
        profile: InfraProfile,
        *,
        profile_digest: str,
        principal_ref: str,
        response: InfraResponse,
    ) -> None:
        """Resolve a previously unknown write only after exact read-only verification."""

        if not isinstance(response.receipt, InfraOperationReceipt):
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_CORRUPT_VERIFY_RECEIPT",
                "verify-receipt-invalid",
                policy_revision=profile.policy_revision,
                run_id=manifest.digest_to_run_id(),
                source_manifest_digest=manifest.digest,
            )
        run_id = manifest.digest_to_run_id()
        run_path = self.state_dir / "runs" / f"{run_id}.json"
        idempotency_key_ref: str | None = None
        if self._load_run_record(run_id).replicated:
            self._reconcile_resolved_admissions(run_id, profile, response)
            resolved = self._load_run_record(run_id)
            if not self._has_durable_replicate_receipt(
                resolved.receipt_id,
                run_id=run_id,
                manifest_digest=manifest.digest,
                profile=profile,
            ):
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                    "completion-record-unavailable",
                    policy_revision=profile.policy_revision,
                    run_id=run_id,
                    source_manifest_digest=manifest.digest,
                )
            return
        with self._state_lock, self._state_file_lock():
            current = self._load_run_record(run_id)
            if (
                current.profile_digest != profile_digest
                or current.target_id != profile.target_id
                or current.profile_id != profile.profile_id
                or current.manifest_digest != manifest.digest
                or response.receipt.source_manifest_digest != manifest.digest
            ):
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_RUN_BINDING_CONFLICT",
                    "verify-run-binding-conflict",
                    policy_revision=profile.policy_revision,
                    run_id=run_id,
                    source_manifest_digest=manifest.digest,
                )
            if current.replicated:
                return
            if not current.write_in_progress:
                return
            if current.reservation_ref is None:
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_CORRUPT_RUN_RESERVATION",
                    "verify-reservation-missing",
                    policy_revision=profile.policy_revision,
                    run_id=run_id,
                    source_manifest_digest=manifest.digest,
                )
            idempotency_key_ref = current.reservation_ref
            owners = self._find_admission_owners(
                idempotency_key_ref,
                run_id=run_id,
                manifest_digest=manifest.digest,
                profile=profile,
                profile_digest=profile_digest,
            )
            if len(owners) != 1:
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_RESERVATION_OWNER_UNAVAILABLE",
                    "verify-reservation-owner-unavailable",
                    policy_revision=profile.policy_revision,
                    run_id=run_id,
                    source_manifest_digest=manifest.digest,
                )
            writer_principal_ref = owners[0]
            idempotency = self._read_idempotency(idempotency_key_ref, writer_principal_ref)
            admission = self._read_admission(idempotency_key_ref, writer_principal_ref)
            if (
                idempotency is None
                or admission is None
                or idempotency.get("status") != "in-progress"
                or idempotency.get("run_id") != run_id
                or idempotency.get("source_manifest_digest") != manifest.digest
                or idempotency.get("principal_ref") != writer_principal_ref
                or idempotency.get("idempotency_key_ref") != idempotency_key_ref
                or idempotency.get("request_digest") != admission.get("request_digest")
                or current.reservation_principal_ref != writer_principal_ref
                or current.reservation_owner_token != admission.get("owner_token")
            ):
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_IDEMPOTENCY_BINDING_CONFLICT",
                    "verify-idempotency-binding-conflict",
                    policy_revision=profile.policy_revision,
                    run_id=run_id,
                    source_manifest_digest=manifest.digest,
                )
            writer_response = self._build_resolved_writer_response(
                response,
                profile,
                manifest,
                writer_principal_ref=writer_principal_ref,
                key_ref=idempotency_key_ref,
                request_digest=cast("str", admission["request_digest"]),
                approval_ref=(
                    cast("str", admission["approval_ref"])
                    if isinstance(admission.get("approval_ref"), str)
                    else None
                ),
            )
            if not self._record_receipt(writer_response):
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                    "completion-record-unavailable",
                    policy_revision=profile.policy_revision,
                    run_id=run_id,
                    source_manifest_digest=manifest.digest,
                )
            _atomic_write(
                run_path,
                _json_bytes(
                    {
                        "run_id": current.run_id,
                        "target_id": current.target_id,
                        "profile_id": current.profile_id,
                        "policy_revision": current.policy_revision,
                        "profile_digest": current.profile_digest,
                        "manifest_digest": current.manifest_digest,
                        "file_count": current.file_count,
                        "byte_count": current.byte_count,
                        "dry_run_passed": current.dry_run_passed,
                        "write_in_progress": False,
                        "reservation_ref": None,
                        "reservation_principal_ref": None,
                        "reservation_owner_token": None,
                        "replicated": True,
                        "receipt_id": writer_response.receipt.receipt_id,
                        "dry_run_receipt_id": current.dry_run_receipt_id,
                    }
                ),
            )
        if idempotency_key_ref is not None:
            self._complete_idempotency(
                idempotency_key_ref,
                writer_principal_ref,
                writer_response,
                owner_token=cast("str", admission["owner_token"]),
            )
            self._delete_admission(
                idempotency_key_ref,
                writer_principal_ref,
                owner_token=cast("str", admission["owner_token"]),
            )
        self._reconcile_resolved_admissions(run_id, profile, writer_response)

    def _find_admission_owners(
        self,
        key_ref: str,
        *,
        run_id: str,
        manifest_digest: str,
        profile: InfraProfile,
        profile_digest: str,
    ) -> list[str]:
        """Find the writer namespace for a run without trusting the verifier namespace."""

        self._ensure_state_layout()
        try:
            entries = list((self.state_dir / "admissions").iterdir())
        except OSError as exc:
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_RESERVATION_OWNER_UNAVAILABLE",
                "admission-state-unavailable",
                policy_revision=profile.policy_revision,
                run_id=run_id,
                source_manifest_digest=manifest_digest,
            ) from exc

        owners: list[str] = []
        for path in entries:
            if path.name.startswith(".") or path.suffix != ".json":
                continue
            try:
                payload = json.loads(
                    _read_secure_file(path, max_bytes=MAX_RECEIPT_BYTES, private=True).decode(
                        "utf-8"
                    ),
                    object_pairs_hook=_reject_duplicate_json_keys,
                )
            except FileNotFoundError:
                continue
            except (OSError, TypeError, UnicodeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            owner = payload.get("principal_ref")
            if not isinstance(owner, str) or not re.fullmatch(_UID_PATTERN, owner):
                continue
            if self._admission_path(key_ref, owner) != path:
                continue
            if not all(
                payload.get(field) == expected
                for field, expected in {
                    "status": payload.get("status"),
                    "idempotency_key_ref": key_ref,
                    "run_id": run_id,
                    "source_manifest_digest": manifest_digest,
                    "profile_id": profile.profile_id,
                    "target_id": profile.target_id,
                    "policy_revision": profile.policy_revision,
                    "profile_digest": profile_digest,
                }.items()
            ) or payload.get("status") not in {"prepared", "started"}:
                continue
            # Re-run the complete schema and timestamp validation for a
            # candidate that can authorize cleanup; unrelated corrupt entries
            # remain ignorable, but a matching malformed record fails closed.
            admission = self._read_admission(key_ref, owner)
            if admission is not None:
                owners.append(owner)
        return owners

    def _build_resolved_writer_response(
        self,
        verify_response: InfraResponse,
        profile: InfraProfile,
        manifest: _Manifest,
        *,
        writer_principal_ref: str,
        key_ref: str,
        request_digest: str,
        approval_ref: str | None,
    ) -> InfraResponse:
        """Convert verify evidence into canonical writer replay data."""

        receipt = verify_response.receipt
        if not isinstance(receipt, InfraOperationReceipt):
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_VERIFY_RECEIPT_INVALID",
                "verify-receipt-invalid",
                policy_revision=profile.policy_revision,
                run_id=manifest.digest_to_run_id(),
                source_manifest_digest=manifest.digest,
            )
        writer_request = InfraRequest(
            operation=InfraOperation.REPLICATE,
            target=profile.target_id,
            profile=profile.profile_id,
            task_id=verify_response.task_id,
            idempotency_key=key_ref,
        )
        writer_data = verify_response.data.model_copy(
            update={
                "run_id": manifest.digest_to_run_id(),
                "dry_run": False,
                "verification": "passed",
                "replay": False,
            }
        )
        return self._operation_response(
            writer_request,
            principal_ref=writer_principal_ref,
            policy_revision=profile.policy_revision,
            target_id=profile.target_id,
            profile_id=profile.profile_id,
            approval_ref=approval_ref,
            source_manifest_digest=manifest.digest,
            host_key_fingerprint=profile.host_key_fingerprint,
            credential_id=profile.credential_id,
            run_id=manifest.digest_to_run_id(),
            data=writer_data.model_dump(mode="json"),
            exit_category=InfraExitCategory.SUCCESS,
            transport="ssh-rsync",
            dry_run=False,
            file_count=receipt.file_count,
            byte_count=receipt.byte_count,
            duration_ms=receipt.duration_ms,
            verification_result="passed",
            request_digest_override=request_digest,
            idempotency_key_ref_override=key_ref,
        )

    def _reconcile_resolved_admissions(
        self,
        run_id: str,
        profile: InfraProfile,
        response: InfraResponse,
    ) -> None:
        """Finish or remove stale started admissions after a run is already resolved."""

        candidates: list[tuple[str, str]] = []
        for path in (self.state_dir / "admissions").iterdir():
            if path.name.startswith("."):
                continue
            try:
                payload = json.loads(
                    _read_secure_file(path, max_bytes=MAX_RECEIPT_BYTES, private=True).decode(
                        "utf-8"
                    ),
                    object_pairs_hook=_reject_duplicate_json_keys,
                )
            except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if (
                not isinstance(payload, dict)
                or payload.get("status") not in {"started", "prepared"}
                or payload.get("run_id") != run_id
                or payload.get("profile_id") != profile.profile_id
                or payload.get("target_id") != profile.target_id
            ):
                continue
            key_ref = payload.get("idempotency_key_ref")
            owner = payload.get("principal_ref")
            if not isinstance(key_ref, str) or not isinstance(owner, str):
                continue
            try:
                admission = self._read_admission(key_ref, owner)
            except InfraBrokerError:
                continue
            if admission is not None and admission.get("status") in {"started", "prepared"}:
                candidates.append((key_ref, owner))
        for key_ref, owner in candidates:
            idempotency = self._read_idempotency(key_ref, owner)
            if idempotency is None:
                continue
            admission = self._read_admission(key_ref, owner)
            if admission is None or any(
                idempotency.get(field) != expected
                for field, expected in {
                    "run_id": run_id,
                    "source_manifest_digest": response.receipt.source_manifest_digest,
                    "principal_ref": owner,
                    "idempotency_key_ref": key_ref,
                    "request_digest": admission.get("request_digest"),
                }.items()
            ):
                continue
            completion_response = response
            if (
                isinstance(response.receipt, InfraOperationReceipt)
                and response.receipt.operation is InfraOperation.VERIFY
            ):
                source_digest = response.receipt.source_manifest_digest
                if not isinstance(source_digest, str):
                    continue
                manifest = _Manifest(
                    digest=source_digest,
                    file_count=response.receipt.file_count,
                    byte_count=response.receipt.byte_count,
                    snapshot_dir=Path("."),
                    source_dirs=(),
                )
                completion_response = self._build_resolved_writer_response(
                    response,
                    profile,
                    manifest,
                    writer_principal_ref=owner,
                    key_ref=key_ref,
                    request_digest=cast("str", admission["request_digest"]),
                    approval_ref=(
                        cast("str", admission["approval_ref"])
                        if isinstance(admission.get("approval_ref"), str)
                        else None
                    ),
                )
            owner_token = (
                cast("str", admission["owner_token"])
                if isinstance(admission.get("owner_token"), str)
                else None
            )
            if idempotency.get("status") == "in-progress":
                if (
                    idempotency.get("run_id") != run_id
                    or idempotency.get("source_manifest_digest")
                    != completion_response.receipt.source_manifest_digest
                ):
                    continue
                if not self._record_receipt(completion_response):
                    continue
                self._complete_idempotency(
                    key_ref, owner, completion_response, owner_token=owner_token
                )
            elif idempotency.get("status") != "completed":
                continue
            self._delete_admission(key_ref, owner, owner_token=owner_token)

    def _release_pre_execution_reservation(
        self,
        manifest: _Manifest,
        profile: InfraProfile,
        profile_digest: str,
        key_ref: str,
        principal_ref: str,
        approval_ref: str | None = None,
        owner_token: str | None = None,
    ) -> None:
        """Release only a reservation proven not to have spawned a process."""

        run_path = self.state_dir / "runs" / f"{manifest.digest_to_run_id()}.json"
        released = False
        with self._state_lock, self._state_file_lock():
            current = self._load_run_record(manifest.digest_to_run_id())
            if current.reservation_ref != key_ref or current.replicated:
                return
            if owner_token is not None and (
                current.reservation_principal_ref != principal_ref
                or current.reservation_owner_token != owner_token
            ):
                return
            if owner_token is not None and not self._admission_owned(
                key_ref, principal_ref, owner_token
            ):
                return
            _atomic_write(
                run_path,
                _json_bytes(
                    {
                        "run_id": current.run_id,
                        "target_id": current.target_id,
                        "profile_id": current.profile_id,
                        "policy_revision": current.policy_revision,
                        "profile_digest": profile_digest,
                        "manifest_digest": current.manifest_digest,
                        "file_count": current.file_count,
                        "byte_count": current.byte_count,
                        "dry_run_passed": current.dry_run_passed,
                        "write_in_progress": False,
                        "reservation_ref": None,
                        "reservation_principal_ref": None,
                        "reservation_owner_token": None,
                        "replicated": False,
                        "receipt_id": current.receipt_id,
                        "dry_run_receipt_id": current.dry_run_receipt_id,
                    }
                ),
            )
            released = True
        if released:
            self._discard_idempotency_reservation(key_ref, principal_ref, owner_token=owner_token)
            if approval_ref is not None and (
                owner_token is None or self._admission_owned(key_ref, principal_ref, owner_token)
            ):
                self._release_one_time_approval(
                    approval_ref,
                    profile.policy_revision,
                    reservation_ref=key_ref,
                    owner_token=owner_token,
                )
            self._delete_admission(key_ref, principal_ref, owner_token=owner_token)

    def _release_one_time_approval(
        self,
        approval_ref: str,
        policy_revision: str,
        *,
        reservation_ref: str,
        owner_token: str | None = None,
    ) -> None:
        """Undo an approval claim only when it belongs to this pre-effect reservation."""

        marker = self.state_dir / "approval-uses" / hashlib_sha256(approval_ref.encode("utf-8"))
        with self._state_lock, self._state_file_lock():
            try:
                payload = json.loads(
                    _read_secure_file(marker, max_bytes=MAX_RECEIPT_BYTES, private=True).decode(
                        "utf-8"
                    ),
                    object_pairs_hook=_reject_duplicate_json_keys,
                )
            except FileNotFoundError:
                return
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                return
            expected = {
                "approval_ref": approval_ref,
                "policy_revision": policy_revision,
                "reservation_ref": reservation_ref,
            }
            if not isinstance(payload, dict) or any(
                payload.get(key) != value for key, value in expected.items()
            ):
                return
            if owner_token is not None and payload.get("owner_token") != owner_token:
                return
            _unlink_and_fsync(marker)

    def _reserve_run_for_write(
        self,
        manifest: _Manifest,
        profile: InfraProfile,
        profile_digest: str,
        reservation_ref: str,
        *,
        principal_ref: str | None = None,
        owner_token: str | None = None,
    ) -> None:
        """CAS-claim one deterministic run before any write-side subprocess."""

        self._ensure_state_layout()
        path = self.state_dir / "runs" / f"{manifest.digest_to_run_id()}.json"
        with self._state_lock, self._state_file_lock():
            current = self._load_run_record(manifest.digest_to_run_id())
            if current.replicated:
                raise InfraBrokerError(
                    InfraReasonCode.RUN_ALREADY_REPLICATED,
                    "VERIFY_EXISTING_RUN_BEFORE_NEW_WRITE",
                    "run-already-replicated",
                    policy_revision=profile.policy_revision,
                    run_id=current.run_id,
                    source_manifest_digest=current.manifest_digest,
                )
            if current.write_in_progress:
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                    "run-write-in-progress",
                    policy_revision=profile.policy_revision,
                    run_id=current.run_id,
                    source_manifest_digest=current.manifest_digest,
                )
            if (
                current.profile_digest != profile_digest
                or current.manifest_digest != manifest.digest
                or current.profile_id != profile.profile_id
                or current.target_id != profile.target_id
            ):
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_RUN_BINDING_CONFLICT",
                    "run-binding-conflict",
                    policy_revision=profile.policy_revision,
                    run_id=manifest.digest_to_run_id(),
                    source_manifest_digest=manifest.digest,
                )
            if (
                not isinstance(principal_ref, str)
                or not re.fullmatch(_UID_PATTERN, principal_ref)
                or not isinstance(owner_token, str)
                or not _ADMISSION_TOKEN_PATTERN.fullmatch(owner_token)
            ):
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_RESERVATION_OWNER_UNAVAILABLE",
                    "reservation-owner-unavailable",
                    policy_revision=profile.policy_revision,
                    run_id=manifest.digest_to_run_id(),
                    source_manifest_digest=manifest.digest,
                )
            admission = self._read_admission(reservation_ref, principal_ref)
            if (
                admission is None
                or admission.get("status") != "prepared"
                or admission.get("owner_token") != owner_token
            ):
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                    "admission-fenced-by-another-attempt",
                    policy_revision=profile.policy_revision,
                    run_id=manifest.digest_to_run_id(),
                    source_manifest_digest=manifest.digest,
                )
            _atomic_write(
                path,
                _json_bytes(
                    {
                        "run_id": current.run_id,
                        "target_id": current.target_id,
                        "profile_id": current.profile_id,
                        "policy_revision": current.policy_revision,
                        "profile_digest": current.profile_digest,
                        "manifest_digest": current.manifest_digest,
                        "file_count": current.file_count,
                        "byte_count": current.byte_count,
                        "dry_run_passed": current.dry_run_passed,
                        "write_in_progress": True,
                        "reservation_ref": reservation_ref,
                        "reservation_principal_ref": principal_ref,
                        "reservation_owner_token": owner_token,
                        "replicated": False,
                        "receipt_id": current.receipt_id,
                        "dry_run_receipt_id": current.dry_run_receipt_id,
                    }
                ),
            )

    def _rebind_run_reservation(
        self,
        manifest: _Manifest,
        profile: InfraProfile,
        profile_digest: str,
        reservation_ref: str,
        *,
        principal_ref: str,
        owner_token: str,
    ) -> None:
        """Fence a prepared crash-recovery attempt onto the live run reservation."""

        path = self.state_dir / "runs" / f"{manifest.digest_to_run_id()}.json"
        with self._state_lock, self._state_file_lock():
            current = self._load_run_record(manifest.digest_to_run_id())
            admission = self._read_admission(reservation_ref, principal_ref)
            if (
                admission is None
                or admission.get("status") != "prepared"
                or admission.get("owner_token") != owner_token
            ):
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                    "admission-fenced-by-another-attempt",
                    policy_revision=profile.policy_revision,
                    run_id=current.run_id,
                    source_manifest_digest=current.manifest_digest,
                )
            if current.replicated or not current.write_in_progress:
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                    "run-reservation-unavailable",
                    policy_revision=profile.policy_revision,
                    run_id=current.run_id,
                    source_manifest_digest=current.manifest_digest,
                )
            if current.reservation_ref != reservation_ref:
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_RUN_BINDING_CONFLICT",
                    "run-reservation-binding-conflict",
                    policy_revision=profile.policy_revision,
                    run_id=current.run_id,
                    source_manifest_digest=current.manifest_digest,
                )
            if current.reservation_principal_ref != principal_ref:
                previous_owner = current.reservation_principal_ref
                if previous_owner is None:
                    raise InfraBrokerError(
                        InfraReasonCode.UNKNOWN_COMPLETION,
                        "RESOLVE_RESERVATION_OWNER_UNAVAILABLE",
                        "run-reservation-owner-unavailable",
                        policy_revision=profile.policy_revision,
                        run_id=current.run_id,
                        source_manifest_digest=current.manifest_digest,
                    )
                previous_admission = self._read_admission(reservation_ref, previous_owner)
                if previous_admission is None or previous_admission.get("status") == "started":
                    raise InfraBrokerError(
                        InfraReasonCode.UNKNOWN_COMPLETION,
                        "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                        "run-reservation-owned-by-another-attempt",
                        policy_revision=profile.policy_revision,
                        run_id=current.run_id,
                        source_manifest_digest=current.manifest_digest,
                    )
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                    "run-reservation-owned-by-another-principal",
                    policy_revision=profile.policy_revision,
                    run_id=current.run_id,
                    source_manifest_digest=current.manifest_digest,
                )
            if (
                current.reservation_principal_ref == principal_ref
                and current.reservation_owner_token == owner_token
            ):
                return
            _atomic_write(
                path,
                _json_bytes(
                    {
                        "run_id": current.run_id,
                        "target_id": current.target_id,
                        "profile_id": current.profile_id,
                        "policy_revision": current.policy_revision,
                        "profile_digest": profile_digest,
                        "manifest_digest": current.manifest_digest,
                        "file_count": current.file_count,
                        "byte_count": current.byte_count,
                        "dry_run_passed": current.dry_run_passed,
                        "write_in_progress": True,
                        "reservation_ref": reservation_ref,
                        "reservation_principal_ref": principal_ref,
                        "reservation_owner_token": owner_token,
                        "replicated": False,
                        "receipt_id": current.receipt_id,
                        "dry_run_receipt_id": current.dry_run_receipt_id,
                    }
                ),
            )

    def _discard_idempotency_reservation(
        self, key_ref: str, principal_ref: str, *, owner_token: str | None = None
    ) -> None:
        """Remove only a pre-execution claim that never reached a subprocess."""

        path = (
            self.state_dir
            / "idempotency"
            / (hashlib_sha256(f"{principal_ref}|{key_ref}".encode()) + ".json")
        )
        with self._state_lock, self._state_file_lock():
            try:
                record = self._read_idempotency(key_ref, principal_ref)
            except InfraBrokerError:
                return
            if (
                record is not None
                and record.get("status") == "in-progress"
                and (owner_token is None or record.get("owner_token") == owner_token)
            ):
                _unlink_and_fsync(path)

    def _ensure_state_layout(self) -> None:
        state_existed = self.state_dir.exists()
        _assert_secure_directory(self.state_dir, create=True, private=True)
        if not state_existed:
            _fsync_directory(self.state_dir.parent)
        for name in ("snapshots", "runs", "idempotency", "admissions", "approval-uses", "receipts"):
            child = self.state_dir / name
            if not child.exists():
                child.mkdir(mode=0o700)
                _fsync_directory(self.state_dir)
            _assert_secure_directory(child, private=True)

    @contextmanager
    def _state_file_lock(self) -> Iterator[None]:
        """Serialize broker state claims across manually duplicated daemons."""

        self._ensure_state_layout()
        lock_path = self.state_dir / ".state.lock"
        descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            with suppress(OSError):
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _ensure_state_capacity(self) -> None:
        """Fail closed before an external operation when broker state is full."""

        self._ensure_state_layout()
        self._cleanup_stale_prepared_admissions()
        for name in ("snapshots", "runs", "idempotency", "admissions", "approval-uses", "receipts"):
            directory = self.state_dir / name
            count = sum(1 for entry in directory.iterdir() if not entry.name.startswith("."))
            if count >= MAX_STATE_RECORDS:
                raise InfraBrokerError(
                    InfraReasonCode.RESOURCE_LIMIT,
                    "RESOLVE_OLD_BROKER_STATE_RECORDS",
                    "state-capacity-exhausted",
                )

    def _cleanup_orphaned_state(self) -> None:
        """Reap only broker-generated temporary state before accepting connections."""

        with self._state_lock, self._state_file_lock():
            snapshots = self.state_dir / "snapshots"
            for entry in snapshots.iterdir():
                if entry.name.startswith(".staging-"):
                    _remove_tree_and_fsync(entry)
            for name in (
                "runs",
                "idempotency",
                "admissions",
                "approval-uses",
                "receipts",
            ):
                for entry in (self.state_dir / name).iterdir():
                    if entry.name.startswith(".") and entry.name.endswith(".tmp"):
                        _remove_tree_and_fsync(entry)

    def _cleanup_stale_prepared_admissions(self) -> None:
        """Remove only expired pre-effect records; started records remain unknown."""

        directory = self.state_dir / "admissions"
        now = datetime.now(UTC)
        for path in directory.iterdir():
            if path.name.startswith("."):
                continue
            try:
                payload = json.loads(
                    _read_secure_file(path, max_bytes=MAX_RECEIPT_BYTES, private=True).decode(
                        "utf-8"
                    ),
                    object_pairs_hook=_reject_duplicate_json_keys,
                )
                if not isinstance(payload, dict) or payload.get("status") != "prepared":
                    continue
                prepared_at = payload.get("prepared_at")
                if not isinstance(prepared_at, str):
                    continue
                timestamp = datetime_from_iso(prepared_at)
            except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if (now - timestamp).total_seconds() > MAX_PREPARED_ADMISSION_AGE_SECONDS:
                with self._state_lock, self._state_file_lock():
                    try:
                        current = json.loads(
                            _read_secure_file(
                                path, max_bytes=MAX_RECEIPT_BYTES, private=True
                            ).decode("utf-8"),
                            object_pairs_hook=_reject_duplicate_json_keys,
                        )
                    except (
                        FileNotFoundError,
                        OSError,
                        TypeError,
                        ValueError,
                        json.JSONDecodeError,
                    ):
                        continue
                    if (
                        isinstance(current, dict)
                        and current.get("status") == "prepared"
                        and current.get("prepared_at") == prepared_at
                        and current.get("owner_token") == payload.get("owner_token")
                    ):
                        self._rollback_prepared_admission(path, current)

    def _rollback_prepared_admission(
        self, admission_path: Path, payload: dict[str, object]
    ) -> None:
        """Rollback all pre-effect claims for one expired prepared admission."""

        key_ref = payload.get("idempotency_key_ref")
        principal_ref = payload.get("principal_ref")
        run_id = payload.get("run_id")
        if not all(isinstance(value, str) for value in (key_ref, principal_ref, run_id)):
            return
        key_ref = cast("str", key_ref)
        principal_ref = cast("str", principal_ref)
        run_id = cast("str", run_id)
        owner_token = payload.get("owner_token")
        if not isinstance(owner_token, str) or not _ADMISSION_TOKEN_PATTERN.fullmatch(owner_token):
            return
        try:
            run = self._load_run_record(run_id)
            if (
                run.write_in_progress
                and run.reservation_ref == key_ref
                and run.reservation_principal_ref == principal_ref
                and run.reservation_owner_token == owner_token
                and not run.replicated
            ):
                _atomic_write(
                    self.state_dir / "runs" / f"{run_id}.json",
                    _json_bytes(
                        {
                            "run_id": run.run_id,
                            "target_id": run.target_id,
                            "profile_id": run.profile_id,
                            "policy_revision": run.policy_revision,
                            "profile_digest": run.profile_digest,
                            "manifest_digest": run.manifest_digest,
                            "file_count": run.file_count,
                            "byte_count": run.byte_count,
                            "dry_run_passed": run.dry_run_passed,
                            "write_in_progress": False,
                            "reservation_ref": None,
                            "reservation_principal_ref": None,
                            "reservation_owner_token": None,
                            "replicated": False,
                            "receipt_id": run.receipt_id,
                            "dry_run_receipt_id": run.dry_run_receipt_id,
                        }
                    ),
                )
            idempotency_path = (
                self.state_dir
                / "idempotency"
                / (hashlib_sha256(f"{principal_ref}|{key_ref}".encode()) + ".json")
            )
            try:
                idempotency = json.loads(
                    _read_secure_file(
                        idempotency_path, max_bytes=MAX_RECEIPT_BYTES, private=True
                    ).decode("utf-8"),
                    object_pairs_hook=_reject_duplicate_json_keys,
                )
            except FileNotFoundError:
                idempotency = None
            if (
                isinstance(idempotency, dict)
                and idempotency.get("status") == "in-progress"
                and idempotency.get("run_id") == run_id
                and idempotency.get("request_digest") == payload.get("request_digest")
                and idempotency.get("owner_token") == owner_token
            ):
                _unlink_and_fsync(idempotency_path)
            approval_ref = payload.get("approval_ref")
            if isinstance(approval_ref, str):
                approval_path = (
                    self.state_dir / "approval-uses" / hashlib_sha256(approval_ref.encode("utf-8"))
                )
                try:
                    approval_marker = json.loads(
                        _read_secure_file(
                            approval_path, max_bytes=MAX_RECEIPT_BYTES, private=True
                        ).decode("utf-8"),
                        object_pairs_hook=_reject_duplicate_json_keys,
                    )
                except FileNotFoundError:
                    approval_marker = None
                if (
                    isinstance(approval_marker, dict)
                    and approval_marker.get("reservation_ref") == key_ref
                    and approval_marker.get("owner_token") == owner_token
                ):
                    _unlink_and_fsync(approval_path)
            _unlink_and_fsync(admission_path)
        except (InfraBrokerError, OSError, TypeError, ValueError, json.JSONDecodeError):
            logger.warning("INFRA-1 prepared admission rollback unavailable")
            return

    def _ensure_runtime_dir(self, *, scrub: bool = False) -> None:
        """Use an ephemeral private directory for copied credential material."""

        _assert_secure_directory(self.runtime_dir, create=True, private=True)
        if not scrub:
            return
        for entry in self.runtime_dir.iterdir():
            if not entry.name.startswith("exec-"):
                continue
            if entry.is_symlink() or not entry.is_dir():
                raise ValueError("broker runtime contains an unsafe execution entry")
            shutil.rmtree(entry)

    def _admission_path(self, key_ref: str, principal_ref: str) -> Path:
        return (
            self.state_dir
            / "admissions"
            / (hashlib_sha256(f"{principal_ref}|{key_ref}".encode()) + ".json")
        )

    def _read_admission(self, key_ref: str, principal_ref: str) -> dict[str, object] | None:
        """Read one bounded pre-effect admission record, if present."""

        self._ensure_state_layout()
        path = self._admission_path(key_ref, principal_ref)
        try:
            raw = _read_secure_file(path, max_bytes=MAX_RECEIPT_BYTES, private=True)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, UnicodeError) as exc:
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_CORRUPT_ADMISSION_RECORD",
                "admission-record-invalid",
            ) from exc
        try:
            payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
        except (TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_CORRUPT_ADMISSION_RECORD",
                "admission-record-invalid",
            ) from exc
        if not isinstance(payload, dict):
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_CORRUPT_ADMISSION_RECORD",
                "admission-record-invalid",
            )
        required = {
            "status",
            "prepared_at",
            "principal_ref",
            "idempotency_key_ref",
            "request_digest",
            "run_id",
            "source_manifest_digest",
            "profile_id",
            "target_id",
            "policy_revision",
            "profile_digest",
            "approval_ref",
            "owner_token",
        }
        if set(payload) != required or payload.get("status") not in {"prepared", "started"}:
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_CORRUPT_ADMISSION_RECORD",
                "admission-record-invalid",
            )
        prepared_at = payload.get("prepared_at")
        if not isinstance(prepared_at, str):
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_CORRUPT_ADMISSION_RECORD",
                "admission-record-invalid",
            )
        try:
            prepared_timestamp = datetime_from_iso(prepared_at)
        except ValueError as exc:
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_CORRUPT_ADMISSION_RECORD",
                "admission-record-invalid",
            ) from exc
        if prepared_timestamp.timestamp() > datetime.now(UTC).timestamp() + 60:
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_CORRUPT_ADMISSION_RECORD",
                "admission-record-invalid",
            )
        if (
            not isinstance(payload.get("prepared_at"), str)
            or payload.get("principal_ref") != principal_ref
            or payload.get("idempotency_key_ref") != key_ref
            or not isinstance(payload.get("request_digest"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", cast("str", payload["request_digest"]))
            or not isinstance(payload.get("run_id"), str)
            or not re.fullmatch(r"run_[0-9a-f]{64}", cast("str", payload["run_id"]))
            or not isinstance(payload.get("source_manifest_digest"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", cast("str", payload["source_manifest_digest"]))
            or not isinstance(payload.get("profile_digest"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", cast("str", payload["profile_digest"]))
            or not isinstance(payload.get("owner_token"), str)
            or not _ADMISSION_TOKEN_PATTERN.fullmatch(cast("str", payload["owner_token"]))
            or any(
                not isinstance(payload.get(field), str)
                for field in ("profile_id", "target_id", "policy_revision")
            )
            or not (
                isinstance(payload.get("approval_ref"), str) or payload.get("approval_ref") is None
            )
        ):
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_CORRUPT_ADMISSION_RECORD",
                "admission-record-invalid",
            )
        return cast("dict[str, object]", payload)

    def _admission_matches(
        self,
        admission: dict[str, object] | None,
        *,
        request_digest: str,
        record: _RunRecord,
        profile: InfraProfile,
        profile_digest: str,
        key_ref: str,
        principal_ref: str,
        approval_ref: str | None,
    ) -> bool:
        if admission is None or admission.get("status") not in {"prepared", "started"}:
            return False
        expected = {
            "principal_ref": principal_ref,
            "idempotency_key_ref": key_ref,
            "request_digest": request_digest,
            "run_id": record.run_id,
            "source_manifest_digest": record.manifest_digest,
            "profile_id": profile.profile_id,
            "target_id": profile.target_id,
            "policy_revision": profile.policy_revision,
            "profile_digest": profile_digest,
            "approval_ref": approval_ref,
        }
        return all(admission.get(key) == value for key, value in expected.items())

    def _prepare_admission(
        self,
        *,
        request_digest: str,
        record: _RunRecord,
        profile: InfraProfile,
        profile_digest: str,
        key_ref: str,
        principal_ref: str,
        approval_ref: str | None,
        owner_token: str | None = None,
    ) -> dict[str, object]:
        """Durably record intent before separately claiming approval/idempotency/run state."""

        self._ensure_state_layout()
        path = self._admission_path(key_ref, principal_ref)
        owner_token = owner_token or uuid.uuid4().hex
        if not _ADMISSION_TOKEN_PATTERN.fullmatch(owner_token):
            raise ValueError("admission owner token is invalid")
        payload: dict[str, object] = {
            "status": "prepared",
            "prepared_at": utc_now(),
            "principal_ref": principal_ref,
            "idempotency_key_ref": key_ref,
            "request_digest": request_digest,
            "run_id": record.run_id,
            "source_manifest_digest": record.manifest_digest,
            "profile_id": profile.profile_id,
            "target_id": profile.target_id,
            "policy_revision": profile.policy_revision,
            "profile_digest": profile_digest,
            "approval_ref": approval_ref,
            "owner_token": owner_token,
        }
        with self._state_lock, self._state_file_lock():
            existing = self._read_admission(key_ref, principal_ref)
            if existing is not None:
                if not self._admission_matches(
                    existing,
                    request_digest=request_digest,
                    record=record,
                    profile=profile,
                    profile_digest=profile_digest,
                    key_ref=key_ref,
                    principal_ref=principal_ref,
                    approval_ref=approval_ref,
                ):
                    raise InfraBrokerError(
                        InfraReasonCode.UNKNOWN_COMPLETION,
                        "RESOLVE_CORRUPT_ADMISSION_RECORD",
                        "admission-binding-conflict",
                        policy_revision=profile.policy_revision,
                        run_id=record.run_id,
                        source_manifest_digest=record.manifest_digest,
                    )
                if existing.get("status") == "prepared":
                    fenced = {
                        **existing,
                        "owner_token": owner_token,
                        "prepared_at": utc_now(),
                    }
                    _atomic_write(path, _json_bytes(fenced))
                    return fenced
                return existing
            _atomic_write(path, _json_bytes(payload))
        return payload

    def _mark_admission_started(
        self, key_ref: str, principal_ref: str, *, owner_token: str | None = None
    ) -> str:
        """Mark an admission started immediately before the first subprocess call."""

        path = self._admission_path(key_ref, principal_ref)
        with self._state_lock, self._state_file_lock():
            existing = self._read_admission(key_ref, principal_ref)
            if existing is None:
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_CORRUPT_ADMISSION_RECORD",
                    "admission-record-invalid",
                )
            if existing.get("status") == "started":
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                    "admission-started",
                    run_id=cast("str | None", existing.get("run_id")),
                    source_manifest_digest=cast(
                        "str | None", existing.get("source_manifest_digest")
                    ),
                )
            if existing.get("status") != "prepared":
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_CORRUPT_ADMISSION_RECORD",
                    "admission-record-invalid",
                )
            stored_token = existing.get("owner_token")
            effective_token = owner_token or (stored_token if isinstance(stored_token, str) else "")
            if (
                not _ADMISSION_TOKEN_PATTERN.fullmatch(effective_token)
                or stored_token != effective_token
            ):
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                    "admission-fenced-by-another-attempt",
                    run_id=cast("str | None", existing.get("run_id")),
                    source_manifest_digest=cast(
                        "str | None", existing.get("source_manifest_digest")
                    ),
                )
            _atomic_write(path, _json_bytes({**existing, "status": "started"}))
            return effective_token

    def _admission_owned(self, key_ref: str, principal_ref: str, owner_token: str) -> bool:
        """Return whether this fencing token still owns one admission record."""

        try:
            admission = self._read_admission(key_ref, principal_ref)
        except InfraBrokerError:
            return False
        return admission is not None and admission.get("owner_token") == owner_token

    def _delete_admission(
        self, key_ref: str, principal_ref: str, *, owner_token: str | None = None
    ) -> None:
        path = self._admission_path(key_ref, principal_ref)
        with self._state_lock, self._state_file_lock():
            if owner_token is not None and not self._admission_owned(
                key_ref, principal_ref, owner_token
            ):
                return
            _unlink_and_fsync(path)

    def _read_idempotency(self, key_ref: str, principal_ref: str) -> dict[str, object] | None:
        self._ensure_state_layout()
        path = (
            self.state_dir
            / "idempotency"
            / (hashlib_sha256(f"{principal_ref}|{key_ref}".encode()) + ".json")
        )
        try:
            raw = _read_secure_file(path, max_bytes=MAX_RECEIPT_BYTES, private=True)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, UnicodeError) as exc:
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_CORRUPT_IDEMPOTENCY_RECORD",
                "idempotency-record-invalid",
            ) from exc
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys)
        if not isinstance(payload, dict):
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_CORRUPT_IDEMPOTENCY_RECORD",
                "idempotency-record-invalid",
            )
        return cast("dict[str, object]", payload)

    def _has_durable_receipt(
        self,
        receipt_id: str | None,
        *,
        request: InfraRequest,
        operation: InfraOperation,
        run_id: str,
    ) -> bool:
        """Require a persisted receipt before a dry-run can authorize a write."""

        if receipt_id is None:
            return False
        path = self.state_dir / "receipts" / f"{receipt_id}.json"
        try:
            raw = _read_secure_file(path, max_bytes=MAX_RECEIPT_BYTES, private=True)
            payload = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_json_keys,
                parse_constant=_reject_json_constant,
            )
            receipt = InfraOperationReceipt.model_validate(payload)
        except (FileNotFoundError, OSError, TypeError, ValueError, ValidationError):
            return False
        receipt_request = InfraRequest(
            operation=operation,
            target=request.target,
            profile=request.profile,
            dry_run=operation is InfraOperation.RSYNC_DRY_RUN,
        )
        expected_id = derive_receipt_id(
            "ir",
            {
                "trace_id": receipt.trace_id,
                "request_digest": _request_digest(receipt_request),
                "operation": receipt.operation.value,
                "target_id": receipt.target_id,
                "profile_id": receipt.profile_id,
                "policy_revision": receipt.policy_revision,
                "principal_ref": receipt.principal_ref,
                "task_id": receipt.task_id,
                "approval_ref": receipt.approval_ref,
                "source_manifest_digest": receipt.source_manifest_digest,
                "host_key_fingerprint": receipt.host_key_fingerprint,
                "credential_id": receipt.credential_id,
                "transport": receipt.transport,
                "run_id": receipt.run_id,
                "dry_run": receipt.dry_run,
                "file_count": receipt.file_count,
                "byte_count": receipt.byte_count,
                "duration_ms": receipt.duration_ms,
                "exit_category": receipt.exit_category.value,
                "verification_result": receipt.verification_result,
                "idempotency_key_ref": receipt.idempotency_key_ref,
                "recorded_at": receipt.recorded_at,
            },
        )
        return (
            receipt.receipt_id == receipt_id
            and receipt.receipt_id == expected_id
            and receipt.operation is operation
            and receipt.run_id == run_id
            and receipt.dry_run is True
            and receipt.exit_category is InfraExitCategory.SUCCESS
            and receipt.verification_result == "dry-run-passed"
        )

    def _claim_idempotency(
        self,
        key_ref: str,
        principal_ref: str,
        request_digest: str,
        record: _RunRecord,
        *,
        owner_token: str | None = None,
        allow_existing_in_progress: bool = False,
    ) -> None:
        self._ensure_state_layout()
        path = (
            self.state_dir
            / "idempotency"
            / (hashlib_sha256(f"{principal_ref}|{key_ref}".encode()) + ".json")
        )
        payload = {
            "status": "in-progress",
            "principal_ref": principal_ref,
            "idempotency_key_ref": key_ref,
            "request_digest": request_digest,
            "run_id": record.run_id,
            "source_manifest_digest": record.manifest_digest,
            "profile_id": record.profile_id,
            "target_id": record.target_id,
            "policy_revision": record.policy_revision,
        }
        if owner_token is not None:
            if not _ADMISSION_TOKEN_PATTERN.fullmatch(owner_token):
                raise ValueError("admission owner token is invalid")
            payload["owner_token"] = owner_token
        encoded = _json_bytes(payload)
        with self._state_lock, self._state_file_lock():
            if owner_token is not None:
                admission = self._read_admission(key_ref, principal_ref)
                if (
                    admission is None
                    or admission.get("status") != "prepared"
                    or admission.get("owner_token") != owner_token
                ):
                    raise InfraBrokerError(
                        InfraReasonCode.UNKNOWN_COMPLETION,
                        "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                        "admission-fenced-by-another-attempt",
                        policy_revision=record.policy_revision,
                        run_id=record.run_id,
                        source_manifest_digest=record.manifest_digest,
                    )
            existing = self._read_idempotency(key_ref, principal_ref)
            if existing is not None:
                if existing.get("request_digest") != request_digest:
                    raise InfraBrokerError(
                        InfraReasonCode.IDEMPOTENCY_CONFLICT,
                        "ISSUE_NEW_IDEMPOTENCY_KEY",
                        "idempotency-conflict",
                        policy_revision=record.policy_revision,
                    )
                if allow_existing_in_progress and existing.get("status") == "in-progress":
                    if (
                        existing.get("run_id") != record.run_id
                        or existing.get("source_manifest_digest") != record.manifest_digest
                        or existing.get("principal_ref") != principal_ref
                        or existing.get("idempotency_key_ref") != key_ref
                    ):
                        raise InfraBrokerError(
                            InfraReasonCode.UNKNOWN_COMPLETION,
                            "RESOLVE_IDEMPOTENCY_BINDING_CONFLICT",
                            "idempotency-binding-conflict",
                            policy_revision=record.policy_revision,
                            run_id=record.run_id,
                            source_manifest_digest=record.manifest_digest,
                        )
                    _atomic_write(
                        path,
                        _json_bytes({**existing, "owner_token": owner_token}),
                    )
                    return
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                    "operation-in-flight",
                    policy_revision=record.policy_revision,
                    run_id=record.run_id,
                    source_manifest_digest=record.manifest_digest,
                )
            try:
                _write_bounded_file(path, encoded, mode=0o600)
            except FileExistsError:
                raise InfraBrokerError(
                    InfraReasonCode.UNKNOWN_COMPLETION,
                    "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                    "operation-in-flight",
                    policy_revision=record.policy_revision,
                    run_id=record.run_id,
                    source_manifest_digest=record.manifest_digest,
                ) from None
            except (OSError, ValueError) as exc:
                raise InfraBrokerError(
                    InfraReasonCode.MISSING_EXECUTION_CAPABILITY,
                    "REPAIR_IDEMPOTENCY_STATE",
                    "idempotency-unavailable",
                    policy_revision=record.policy_revision,
                ) from exc

    def _complete_idempotency(
        self,
        key_ref: str | None,
        principal_ref: str,
        response: InfraResponse,
        *,
        owner_token: str | None = None,
    ) -> None:
        if key_ref is None:
            raise ValueError("completion requires an idempotency key")
        path = (
            self.state_dir
            / "idempotency"
            / (hashlib_sha256(f"{principal_ref}|{key_ref}".encode()) + ".json")
        )
        with self._state_lock, self._state_file_lock():
            existing = self._read_idempotency(key_ref, principal_ref)
            if existing is None or existing.get("status") != "in-progress":
                raise ValueError("idempotency reservation is missing")
            if owner_token is not None and existing.get("owner_token") != owner_token:
                raise ValueError("idempotency reservation is fenced")
            payload = {
                **existing,
                "status": "completed",
                "response": response.model_dump(mode="json"),
            }
            _atomic_write(path, _json_bytes(payload))

    def _replay_response(
        self,
        request: InfraRequest,
        stored: InfraResponse,
        principal_ref: str,
        profile: InfraProfile,
    ) -> InfraResponse:
        """Return a new bounded replay receipt without re-running the effect."""

        if not isinstance(stored.receipt, InfraOperationReceipt):
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_CORRUPT_IDEMPOTENCY_RECORD",
                "idempotency-record-invalid",
                policy_revision=profile.policy_revision,
            )
        data = stored.data.model_copy(update={"replay": True})
        return self._operation_response(
            request,
            principal_ref=principal_ref,
            policy_revision=profile.policy_revision,
            target_id=profile.target_id,
            profile_id=profile.profile_id,
            approval_ref=stored.receipt.approval_ref,
            source_manifest_digest=stored.receipt.source_manifest_digest,
            host_key_fingerprint=profile.host_key_fingerprint,
            credential_id=profile.credential_id,
            run_id=stored.receipt.run_id,
            data=data.model_dump(mode="json"),
            exit_category=InfraExitCategory.REPLAY,
            transport="ssh-rsync",
            dry_run=False,
            file_count=stored.receipt.file_count,
            byte_count=stored.receipt.byte_count,
            verification_result=stored.receipt.verification_result,
        )

    def _execute_operation(
        self,
        request: InfraRequest,
        profile: InfraProfile,
        *,
        principal_ref: str,
        approval_ref: str | None,
        manifest: _Manifest,
        deadline: float,
        execution_started: Callable[[], None] | None = None,
        execution_effect_started: Callable[[], None] | None = None,
    ) -> InfraResponse:
        try:
            self._validate_snapshot_inventory(manifest, profile, deadline=deadline)
        except TimeoutError:
            raise self._operation_timeout_error(profile, manifest, request.operation) from None
        except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION
                if request.operation is InfraOperation.REPLICATE
                else InfraReasonCode.RESOURCE_LIMIT,
                "RESOLVE_SNAPSHOT_MANIFEST_DRIFT",
                "snapshot-invalid",
                policy_revision=profile.policy_revision,
                run_id=manifest.digest_to_run_id(),
                source_manifest_digest=manifest.digest,
            ) from exc
        credential_id = (
            profile.verify_credential_id
            if request.operation is InfraOperation.VERIFY
            else profile.credential_id
        )
        credential_source, credential_material = self._snapshot_execution_material(
            profile, credential_id=credential_id
        )
        del credential_source
        exec_dir = credential_material.path.parent
        try:
            if request.operation is InfraOperation.PROBE:
                operation = InfraOperation.RSYNC_DRY_RUN
            else:
                operation = request.operation
            results: list[_ProcessResult] = []
            inventory_results: list[_ProcessResult] = []
            effect_started = False
            try:
                expected_inventory = (
                    self._snapshot_expected_inventory(manifest, deadline=deadline)
                    if request.operation is InfraOperation.VERIFY
                    else ()
                )
                expected_files = (
                    self._snapshot_expected_files(manifest, deadline=deadline)
                    if request.operation is InfraOperation.VERIFY
                    else ()
                )
            except TimeoutError:
                raise self._operation_timeout_error(profile, manifest, request.operation) from None
            for root_index, source_dir in enumerate(manifest.source_dirs):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise self._operation_timeout_error(
                        profile, manifest, request.operation, effect_started=effect_started
                    )
                if request.operation is InfraOperation.VERIFY:
                    inventory_dir = exec_dir / "inventory" / f"source-{root_index:03d}"
                    inventory_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
                    _assert_secure_directory(inventory_dir, private=True)
                    inventory_argv = _build_verify_inventory_argv(
                        profile,
                        run_id=manifest.digest_to_run_id(),
                        root_index=root_index,
                        known_hosts_file=exec_dir / "known_hosts",
                        credential_file=credential_material.path,
                        destination_dir=inventory_dir,
                    )
                    try:
                        inventory_result = self.command_runner(
                            inventory_argv, remaining, profile.max_output_bytes
                        )
                    except TimeoutError:
                        raise self._operation_timeout_error(
                            profile, manifest, request.operation, effect_started=effect_started
                        ) from None
                    except Exception as exc:
                        raise InfraBrokerError(
                            InfraReasonCode.UNKNOWN_COMPLETION,
                            "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                            "command-runner-failed",
                            policy_revision=profile.policy_revision,
                            run_id=manifest.digest_to_run_id(),
                            source_manifest_digest=manifest.digest,
                        ) from exc
                    inventory_results.append(inventory_result)
                    if (
                        inventory_result.category is not InfraExitCategory.SUCCESS
                        or inventory_result.returncode != 0
                    ):
                        return self._failed_response(
                            request,
                            profile,
                            principal_ref=principal_ref,
                            approval_ref=approval_ref,
                            manifest=manifest,
                            result=inventory_result,
                            duration_ms=sum(
                                item.duration_ms for item in results + inventory_results
                            ),
                            credential_id=credential_id,
                        )
                    if not _rsync_inventory_is_exact(
                        inventory_result, expected_inventory[root_index]
                    ):
                        return self._verification_mismatch_response(
                            request,
                            profile,
                            principal_ref=principal_ref,
                            approval_ref=approval_ref,
                            manifest=manifest,
                            credential_id=credential_id,
                            duration_ms=sum(
                                item.duration_ms for item in results + inventory_results
                            ),
                        )
                    expected_directory_names = set(expected_inventory[root_index]).difference(
                        expected_files[root_index]
                    )
                    for relative in sorted(expected_directory_names):
                        directory = inventory_dir / relative
                        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
                        _assert_secure_directory(directory, private=True)
                    for file_index, (relative, (expected_size, _digest)) in enumerate(
                        sorted(expected_files[root_index].items())
                    ):
                        files_from = exec_dir / (
                            f"verify-file-{root_index:03d}-{file_index:06d}.txt"
                        )
                        _write_bounded_file(files_from, f"{relative}\n".encode(), mode=0o600)
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise self._operation_timeout_error(
                                profile, manifest, request.operation
                            )
                        if (
                            shutil.disk_usage(inventory_dir).free
                            < max(1, expected_size) + MIN_SNAPSHOT_FREE_BYTES
                        ):
                            raise InfraBrokerError(
                                InfraReasonCode.RESOURCE_LIMIT,
                                "LOWER_PROFILE_SIZE_OR_FREE_BROKER_STORAGE",
                                "verify-free-space-limit",
                                policy_revision=profile.policy_revision,
                                run_id=manifest.digest_to_run_id(),
                                source_manifest_digest=manifest.digest,
                            )
                        content_argv = _build_verify_content_argv(
                            profile,
                            run_id=manifest.digest_to_run_id(),
                            root_index=root_index,
                            known_hosts_file=exec_dir / "known_hosts",
                            credential_file=credential_material.path,
                            files_from=files_from,
                            destination_dir=inventory_dir,
                            max_file_bytes=max(1, expected_size),
                        )
                        try:
                            content_result = self.command_runner(
                                content_argv, remaining, profile.max_output_bytes
                            )
                        except TimeoutError:
                            raise self._operation_timeout_error(
                                profile, manifest, request.operation
                            ) from None
                        except Exception as exc:
                            raise InfraBrokerError(
                                InfraReasonCode.UNKNOWN_COMPLETION,
                                "RESOLVE_BROKER_RUN_BEFORE_RETRY",
                                "command-runner-failed",
                                policy_revision=profile.policy_revision,
                                run_id=manifest.digest_to_run_id(),
                                source_manifest_digest=manifest.digest,
                            ) from exc
                        inventory_results.append(content_result)
                        if (
                            content_result.category is not InfraExitCategory.SUCCESS
                            or content_result.returncode != 0
                        ):
                            return self._failed_response(
                                request,
                                profile,
                                principal_ref=principal_ref,
                                approval_ref=approval_ref,
                                manifest=manifest,
                                result=content_result,
                                duration_ms=sum(
                                    item.duration_ms for item in results + inventory_results
                                ),
                                credential_id=credential_id,
                            )
                    try:
                        inventory_valid = _verify_pulled_inventory(
                            inventory_dir,
                            expected_files[root_index],
                            expected_inventory[root_index],
                            deadline=deadline,
                            max_bytes=profile.max_bytes,
                        )
                    except TimeoutError:
                        raise self._operation_timeout_error(
                            profile, manifest, request.operation
                        ) from None
                    if not inventory_valid:
                        return self._verification_mismatch_response(
                            request,
                            profile,
                            principal_ref=principal_ref,
                            approval_ref=approval_ref,
                            manifest=manifest,
                            credential_id=credential_id,
                            duration_ms=sum(
                                item.duration_ms for item in results + inventory_results
                            ),
                        )
                    continue
                argv = _build_rsync_argv(
                    profile,
                    source_dir=source_dir,
                    run_id=manifest.digest_to_run_id(),
                    root_index=root_index,
                    known_hosts_file=exec_dir / "known_hosts",
                    credential_file=credential_material.path,
                    operation=operation,
                )
                try:
                    if (
                        execution_started is not None
                        and request.operation is InfraOperation.REPLICATE
                    ):
                        execution_started()
                    result = self.command_runner(argv, remaining, profile.max_output_bytes)
                except TimeoutError:
                    # An injectable runner can raise after spawning a child
                    # without returning a bounded result.  Timeout is therefore
                    # an unknown write outcome, never proof of pre-effect
                    # failure; retain the reservation and require verify.
                    if request.operation is InfraOperation.REPLICATE and not effect_started:
                        effect_started = True
                        if execution_effect_started is not None:
                            execution_effect_started()
                    raise self._operation_timeout_error(
                        profile,
                        manifest,
                        request.operation,
                        effect_started=effect_started,
                    ) from None
                except Exception as exc:
                    if (
                        request.operation is InfraOperation.REPLICATE
                        and execution_effect_started is not None
                    ):
                        execution_effect_started()
                    raise InfraBrokerError(
                        InfraReasonCode.UNKNOWN_COMPLETION
                        if request.operation is InfraOperation.REPLICATE
                        else InfraReasonCode.OPERATION_FAILED,
                        "RESOLVE_BROKER_RUN_BEFORE_RETRY"
                        if request.operation is InfraOperation.REPLICATE
                        else "INSPECT_BROKER_LOG",
                        "command-runner-failed",
                        policy_revision=profile.policy_revision,
                        run_id=manifest.digest_to_run_id(),
                        source_manifest_digest=manifest.digest,
                    ) from exc
                results.append(result)
                if result.category is not InfraExitCategory.PROCESS_UNAVAILABLE:
                    effect_started = True
                    if execution_effect_started is not None:
                        execution_effect_started()
                if result.category is not InfraExitCategory.SUCCESS or result.returncode != 0:
                    if (
                        request.operation is InfraOperation.REPLICATE
                        and result.category is InfraExitCategory.PROCESS_UNAVAILABLE
                        and any(
                            item.category is not InfraExitCategory.PROCESS_UNAVAILABLE
                            for item in results[:-1]
                        )
                    ):
                        return _block_response(
                            request,
                            InfraReasonCode.UNKNOWN_COMPLETION,
                            policy_revision=profile.policy_revision,
                            broker_status="partial-run-outcome-unknown",
                            remediation_code="RESOLVE_BROKER_RUN_BEFORE_RETRY",
                            run_id=manifest.digest_to_run_id(),
                            source_manifest_digest=manifest.digest,
                        )
                    return self._failed_response(
                        request,
                        profile,
                        principal_ref=principal_ref,
                        approval_ref=approval_ref,
                        manifest=manifest,
                        result=result,
                        duration_ms=sum(item.duration_ms for item in results),
                        credential_id=credential_id,
                    )

            if time.monotonic() >= deadline:
                raise self._operation_timeout_error(
                    profile, manifest, request.operation, effect_started=effect_started
                )
            verification: InfraVerificationResult
            if request.operation is InfraOperation.VERIFY:
                verification = "inventory-matched"
            elif (
                request.operation is InfraOperation.RSYNC_DRY_RUN
                or request.operation is InfraOperation.PROBE
            ):
                verification = (
                    "dry-run-passed"
                    if request.operation is InfraOperation.RSYNC_DRY_RUN
                    else "status"
                )
            else:
                verification = "replicated-awaiting-verify"
            return self._operation_response(
                request,
                principal_ref=principal_ref,
                policy_revision=profile.policy_revision,
                target_id=profile.target_id,
                profile_id=profile.profile_id,
                approval_ref=approval_ref,
                source_manifest_digest=manifest.digest,
                host_key_fingerprint=profile.host_key_fingerprint,
                credential_id=credential_id,
                run_id=manifest.digest_to_run_id(),
                data={
                    "broker_status": "active",
                    "run_id": manifest.digest_to_run_id(),
                    "file_count": manifest.file_count,
                    "byte_count": manifest.byte_count,
                    "dry_run": request.operation
                    in {InfraOperation.PROBE, InfraOperation.RSYNC_DRY_RUN, InfraOperation.VERIFY},
                    "reachable": request.operation is InfraOperation.PROBE,
                    "verification": verification,
                },
                exit_category=InfraExitCategory.SUCCESS,
                transport="ssh-rsync",
                dry_run=request.operation
                in {InfraOperation.PROBE, InfraOperation.RSYNC_DRY_RUN, InfraOperation.VERIFY},
                file_count=manifest.file_count,
                byte_count=manifest.byte_count,
                duration_ms=sum(item.duration_ms for item in results + inventory_results),
                verification_result=verification,
            )
        finally:
            with suppress(OSError):
                shutil.rmtree(exec_dir)

    def _snapshot_execution_material(
        self, profile: InfraProfile, *, credential_id: str | None = None
    ) -> tuple[str, _CredentialMaterial]:
        self._ensure_state_layout()
        _, original_credential = self._credential_candidate(profile, credential_id=credential_id)
        known_hosts = self._require_host_key(profile)
        credential_bytes = _read_secure_file(
            original_credential.path,
            max_bytes=MAX_CREDENTIAL_BYTES,
            private=True,
        )
        self._ensure_runtime_dir()
        exec_dir = self.runtime_dir / f"exec-{uuid.uuid4().hex}"
        exec_dir.mkdir(mode=0o700)
        credential_path = exec_dir / "identity"
        known_hosts_path = exec_dir / "known_hosts"
        try:
            _write_bounded_file(credential_path, credential_bytes, mode=0o400)
            _write_bounded_file(known_hosts_path, known_hosts, mode=0o400)
        except (OSError, ValueError):
            with suppress(OSError):
                shutil.rmtree(exec_dir)
            raise InfraBrokerError(
                InfraReasonCode.BROKER_CREDENTIAL_UNAVAILABLE,
                "REPAIR_CREDENTIAL_SNAPSHOT_BOUNDARY",
                "credential-unavailable",
                policy_revision=profile.policy_revision,
            ) from None
        # The caller needs the known_hosts path in the same execution directory.
        return original_credential.source, _CredentialMaterial(
            path=credential_path, source=original_credential.source
        )

    def _validate_snapshot_inventory(
        self, manifest: _Manifest, profile: InfraProfile, *, deadline: float | None = None
    ) -> None:
        """Recheck every sealed snapshot file before handing it to rsync."""

        sealed = self._load_snapshot_manifest(manifest.snapshot_dir, profile)
        if sealed.digest != manifest.digest:
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_SNAPSHOT_MANIFEST_DRIFT",
                "snapshot-digest-mismatch",
                policy_revision=profile.policy_revision,
                run_id=manifest.digest_to_run_id(),
                source_manifest_digest=manifest.digest,
            )
        raw_manifest = _read_secure_file(
            manifest.snapshot_dir / "manifest.json",
            max_bytes=MAX_STATE_BYTES,
            private=True,
        )
        payload = json.loads(
            raw_manifest.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
        if (
            not isinstance(payload, dict)
            or set(payload)
            != {
                "profile_digest",
                "target_id",
                "policy_revision",
                "control_files",
                "entries",
                "directories",
            }
            or not isinstance(payload.get("entries"), list)
            or not isinstance(payload.get("directories"), list)
            or payload.get("control_files") != ["source-000/.power-infra-run.json"]
        ):
            raise InfraBrokerError(
                InfraReasonCode.UNKNOWN_COMPLETION,
                "RESOLVE_SNAPSHOT_MANIFEST_DRIFT",
                "snapshot-invalid",
                policy_revision=profile.policy_revision,
                run_id=manifest.digest_to_run_id(),
                source_manifest_digest=manifest.digest,
            )
        expected: dict[str, tuple[int, str]] = {}
        for entry in cast("list[object]", payload["entries"]):
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("snapshot validation deadline elapsed")
            if not isinstance(entry, dict) or set(entry) != {"root", "path", "size", "sha256"}:
                raise ValueError("snapshot entry is invalid")
            root_index = entry.get("root")
            relative = entry.get("path")
            size = entry.get("size")
            digest = entry.get("sha256")
            if (
                type(root_index) is not int
                or not 0 <= root_index < len(profile.source_roots)
                or not isinstance(relative, str)
                or type(size) is not int
                or size < 0
                or not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
            ):
                raise ValueError("snapshot entry is invalid")
            _validate_relative_source_path(relative)
            key = f"source-{root_index:03d}/{relative}"
            if key in expected:
                raise ValueError("snapshot manifest contains duplicate entries")
            expected[key] = (size, digest)

        expected_directories: set[str] = set()
        for directory in cast("list[object]", payload["directories"]):
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("snapshot validation deadline elapsed")
            if not isinstance(directory, dict) or set(directory) != {"root", "path"}:
                raise ValueError("snapshot directory entry is invalid")
            root_index = directory.get("root")
            relative = directory.get("path")
            if (
                type(root_index) is not int
                or not 0 <= root_index < len(profile.source_roots)
                or not isinstance(relative, str)
            ):
                raise ValueError("snapshot directory entry is invalid")
            _validate_relative_source_path(relative)
            key = f"source-{root_index:03d}/{relative}"
            if key in expected or key in expected_directories:
                raise ValueError("snapshot manifest contains duplicate entries")
            expected_directories.add(key)

        if len(expected) + len(expected_directories) > profile.max_files:
            raise ValueError("snapshot exceeds profile entry bound")
        observed: set[str] = set()
        observed_directories: set[str] = set()
        for root_index, source_dir in enumerate(manifest.source_dirs):
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("snapshot validation deadline elapsed")
            if not source_dir.is_dir() or source_dir.is_symlink():
                raise ValueError("snapshot source directory is invalid")
            for current_text, dirnames, filenames in os.walk(
                source_dir,
                topdown=True,
                onerror=_raise_walk_error,
                followlinks=False,
            ):
                current = Path(current_text)
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("snapshot validation deadline elapsed")
                for dirname in sorted(dirnames):
                    directory = current / dirname
                    metadata = directory.lstat()
                    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                        raise ValueError("snapshot contains a symlink directory")
                    relative = directory.relative_to(source_dir).as_posix()
                    key = f"source-{root_index:03d}/{relative}"
                    if key not in expected_directories:
                        raise ValueError("snapshot contains an unexpected directory")
                    observed_directories.add(key)
                for filename in sorted(filenames):
                    if deadline is not None and time.monotonic() >= deadline:
                        raise TimeoutError("snapshot validation deadline elapsed")
                    candidate = current / filename
                    if candidate.is_symlink() or not candidate.is_file():
                        raise ValueError("snapshot contains a non-regular file")
                    relative = candidate.relative_to(source_dir).as_posix()
                    key = f"source-{root_index:03d}/{relative}"
                    if key == "source-000/.power-infra-run.json":
                        marker = json.loads(
                            _read_secure_file(candidate, max_bytes=MAX_RECEIPT_BYTES, private=True),
                            object_pairs_hook=_reject_duplicate_json_keys,
                            parse_constant=_reject_json_constant,
                        )
                        if (
                            not isinstance(marker, dict)
                            or marker.get("run_id") != manifest.digest_to_run_id()
                        ):
                            raise ValueError("snapshot run marker changed")
                        continue
                    if key not in expected:
                        raise ValueError("snapshot contains an unexpected file")
                    raw = _read_secure_file(
                        candidate,
                        max_bytes=profile.max_bytes,
                        private=True,
                    )
                    size, digest = expected[key]
                    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
                        raise ValueError("snapshot file digest changed")
                    observed.add(key)
        if observed != set(expected):
            raise ValueError("snapshot inventory does not match its manifest")
        if observed_directories != expected_directories:
            raise ValueError("snapshot directory inventory does not match its manifest")

    def _snapshot_expected_files(
        self, manifest: _Manifest, *, deadline: float | None = None
    ) -> tuple[dict[str, tuple[int, str]], ...]:
        """Return expected remote files with bounded size and content digests."""

        raw = _read_secure_file(
            manifest.snapshot_dir / "manifest.json",
            max_bytes=MAX_STATE_BYTES,
            private=True,
        )
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
        if (
            not isinstance(payload, dict)
            or set(payload)
            != {
                "profile_digest",
                "target_id",
                "policy_revision",
                "control_files",
                "entries",
                "directories",
            }
            or not isinstance(payload.get("entries"), list)
            or not isinstance(payload.get("directories"), list)
            or payload.get("control_files") != ["source-000/.power-infra-run.json"]
        ):
            raise ValueError("snapshot manifest is invalid")
        expected: list[dict[str, tuple[int, str]]] = [{} for _ in range(len(manifest.source_dirs))]
        for entry in cast("list[object]", payload["entries"]):
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("verify deadline elapsed")
            if not isinstance(entry, dict) or set(entry) != {"root", "path", "size", "sha256"}:
                raise ValueError("snapshot manifest entry is invalid")
            root_index = entry.get("root")
            relative = entry.get("path")
            size = entry.get("size")
            digest = entry.get("sha256")
            if (
                type(root_index) is not int
                or not 0 <= root_index < len(expected)
                or not isinstance(relative, str)
                or type(size) is not int
                or size < 0
                or not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
            ):
                raise ValueError("snapshot manifest entry is invalid")
            _validate_relative_source_path(relative)
            if relative in expected[root_index]:
                raise ValueError("snapshot manifest contains duplicate entries")
            expected[root_index][relative] = (size, digest)
        directory_keys: set[tuple[int, str]] = set()
        for directory in cast("list[object]", payload["directories"]):
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("verify deadline elapsed")
            if not isinstance(directory, dict) or set(directory) != {"root", "path"}:
                raise ValueError("snapshot directory entry is invalid")
            root_index = directory.get("root")
            relative = directory.get("path")
            if (
                type(root_index) is not int
                or not 0 <= root_index < len(expected)
                or not isinstance(relative, str)
            ):
                raise ValueError("snapshot directory entry is invalid")
            _validate_relative_source_path(relative)
            key = (root_index, relative)
            if key in directory_keys or relative in expected[root_index]:
                raise ValueError("snapshot manifest contains duplicate entries")
            directory_keys.add(key)

        marker = {
            "schema_version": "power.infra-run.v1",
            "run_id": manifest.digest_to_run_id(),
            "profile_digest": payload["profile_digest"],
            "target_id": payload["target_id"],
            "policy_revision": payload["policy_revision"],
            "manifest_digest": manifest.digest,
            "file_count": manifest.file_count,
            "byte_count": manifest.byte_count,
        }
        marker_bytes = _json_bytes(marker)
        expected[0][".power-infra-run.json"] = (
            len(marker_bytes),
            hashlib_sha256(marker_bytes),
        )
        return tuple(expected)

    def _snapshot_expected_inventory(
        self, manifest: _Manifest, *, deadline: float | None = None
    ) -> tuple[dict[str, InfraInventoryType], ...]:
        """Return expected remote files and all required parent directories."""

        expected_files = self._snapshot_expected_files(manifest, deadline=deadline)
        expected: list[dict[str, InfraInventoryType]] = []
        for files in expected_files:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("verify deadline elapsed")
            names: dict[str, InfraInventoryType] = dict.fromkeys(files, "file")
            for relative in files:
                parent = Path(relative).parent
                while parent != Path("."):
                    names[parent.as_posix()] = "directory"
                    parent = parent.parent
            expected.append(names)
        raw = _read_secure_file(
            manifest.snapshot_dir / "manifest.json",
            max_bytes=MAX_STATE_BYTES,
            private=True,
        )
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("directories"), list):
            raise ValueError("snapshot manifest directories are invalid")
        for directory in cast("list[object]", payload["directories"]):
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("verify deadline elapsed")
            if not isinstance(directory, dict):
                raise ValueError("snapshot directory entry is invalid")
            root_index = directory.get("root")
            directory_relative = directory.get("path")
            if (
                type(root_index) is not int
                or not 0 <= root_index < len(expected)
                or not isinstance(directory_relative, str)
            ):
                raise ValueError("snapshot directory entry is invalid")
            _validate_relative_source_path(directory_relative)
            expected[root_index][directory_relative] = "directory"
        return tuple(expected)

    def _verification_mismatch_response(
        self,
        request: InfraRequest,
        profile: InfraProfile,
        *,
        principal_ref: str,
        approval_ref: str | None,
        manifest: _Manifest,
        credential_id: str | None,
        duration_ms: int,
    ) -> InfraResponse:
        """Return a bounded mismatch receipt without exposing remote inventory data."""

        return self._operation_response(
            request,
            principal_ref=principal_ref,
            policy_revision=profile.policy_revision,
            target_id=profile.target_id,
            profile_id=profile.profile_id,
            approval_ref=approval_ref,
            source_manifest_digest=manifest.digest,
            host_key_fingerprint=profile.host_key_fingerprint,
            credential_id=credential_id,
            run_id=manifest.digest_to_run_id(),
            data={
                "run_id": manifest.digest_to_run_id(),
                "file_count": manifest.file_count,
                "byte_count": manifest.byte_count,
                "dry_run": True,
                "verification": "mismatch",
            },
            exit_category=InfraExitCategory.FAILED,
            transport="ssh-rsync",
            dry_run=True,
            file_count=manifest.file_count,
            byte_count=manifest.byte_count,
            duration_ms=duration_ms,
            verification_result="mismatch",
        )

    def _failed_response(
        self,
        request: InfraRequest,
        profile: InfraProfile,
        *,
        principal_ref: str,
        approval_ref: str | None,
        manifest: _Manifest,
        result: _ProcessResult,
        duration_ms: int,
        credential_id: str | None = None,
    ) -> InfraResponse:
        category = result.category
        if category is InfraExitCategory.PROCESS_UNAVAILABLE:
            return _block_response(
                request,
                InfraReasonCode.MISSING_EXECUTION_CAPABILITY,
                policy_revision=profile.policy_revision,
                broker_status="process-unavailable",
                remediation_code="INSTALL_FIXED_SSH_RSYNC_RUNTIME",
                run_id=manifest.digest_to_run_id(),
                source_manifest_digest=manifest.digest,
            )
        if category in {
            InfraExitCategory.HOST_IDENTITY_MISMATCH,
            InfraExitCategory.HOST_IDENTITY_UNTRUSTED,
        }:
            reason = (
                InfraReasonCode.HOST_IDENTITY_MISMATCH
                if category is InfraExitCategory.HOST_IDENTITY_MISMATCH
                else InfraReasonCode.HOST_IDENTITY_UNTRUSTED
            )
            return _block_response(
                request,
                reason,
                policy_revision=profile.policy_revision,
                broker_status=category.value,
                remediation_code="OPERATOR_ROTATE_OR_REPAIR_HOST_KEY_PIN",
                run_id=manifest.digest_to_run_id(),
                source_manifest_digest=manifest.digest,
            )
        if category is InfraExitCategory.NETWORK_UNAVAILABLE:
            reason = (
                InfraReasonCode.UNKNOWN_COMPLETION
                if request.operation is InfraOperation.REPLICATE
                else InfraReasonCode.NETWORK_UNAVAILABLE
            )
            return _block_response(
                request,
                reason,
                policy_revision=profile.policy_revision,
                broker_status=category.value,
                remediation_code=(
                    "RESOLVE_BROKER_RUN_BEFORE_RETRY"
                    if reason is InfraReasonCode.UNKNOWN_COMPLETION
                    else "CHECK_APPROVED_TARGET_NETWORK"
                ),
                run_id=manifest.digest_to_run_id(),
                source_manifest_digest=manifest.digest,
            )
        if category is InfraExitCategory.TIMEOUT:
            return _block_response(
                request,
                InfraReasonCode.UNKNOWN_COMPLETION
                if request.operation is InfraOperation.REPLICATE
                else InfraReasonCode.TIMEOUT,
                policy_revision=profile.policy_revision,
                broker_status=category.value,
                remediation_code=(
                    "RESOLVE_BROKER_RUN_BEFORE_RETRY"
                    if request.operation is InfraOperation.REPLICATE
                    else "LOWER_PROFILE_TIMEOUT"
                ),
                run_id=manifest.digest_to_run_id(),
                source_manifest_digest=manifest.digest,
            )
        if category is InfraExitCategory.OUTPUT_LIMIT:
            return _block_response(
                request,
                InfraReasonCode.UNKNOWN_COMPLETION
                if request.operation is InfraOperation.REPLICATE
                else InfraReasonCode.RESOURCE_LIMIT,
                policy_revision=profile.policy_revision,
                broker_status=category.value,
                remediation_code=(
                    "RESOLVE_BROKER_RUN_BEFORE_RETRY"
                    if request.operation is InfraOperation.REPLICATE
                    else "LOWER_PROFILE_RESOURCE_BOUND"
                ),
                run_id=manifest.digest_to_run_id(),
                source_manifest_digest=manifest.digest,
            )
        if request.operation is InfraOperation.REPLICATE:
            return _block_response(
                request,
                InfraReasonCode.UNKNOWN_COMPLETION,
                policy_revision=profile.policy_revision,
                broker_status=category.value,
                remediation_code="RESOLVE_BROKER_RUN_BEFORE_RETRY",
                run_id=manifest.digest_to_run_id(),
                source_manifest_digest=manifest.digest,
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
            credential_id=credential_id or profile.credential_id,
            run_id=manifest.digest_to_run_id(),
            data={
                "broker_status": "remote-rejected"
                if category is InfraExitCategory.REMOTE_REJECTED
                else "failed",
                "run_id": manifest.digest_to_run_id(),
                "file_count": manifest.file_count,
                "byte_count": manifest.byte_count,
                "dry_run": True,
                "verification": "unknown",
            },
            exit_category=category,
            transport="ssh-rsync",
            dry_run=True,
            file_count=manifest.file_count,
            byte_count=manifest.byte_count,
            duration_ms=duration_ms,
            verification_result="unknown",
        )

    def _operation_response(
        self,
        request: InfraRequest,
        *,
        principal_ref: str,
        policy_revision: str,
        data: Mapping[str, object],
        exit_category: InfraExitCategory,
        transport: Literal["unix", "ssh-rsync"],
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
        verification_result: InfraVerificationResult | None = None,
        request_digest_override: str | None = None,
        idempotency_key_ref_override: str | None = None,
    ) -> InfraResponse:
        trace_id = _trace_id()
        request_digest = request_digest_override or _request_digest(request)
        idempotency_key_ref = (
            idempotency_key_ref_override
            if idempotency_key_ref_override is not None
            else idempotency_key_reference(request.idempotency_key)
        )
        recorded_at = utc_now()
        payload = {
            "trace_id": trace_id,
            "request_digest": request_digest,
            "operation": request.operation.value,
            "target_id": target_id,
            "profile_id": profile_id,
            "policy_revision": policy_revision,
            "principal_ref": principal_ref,
            "task_id": request.task_id,
            "approval_ref": approval_ref,
            "run_id": run_id,
            "source_manifest_digest": source_manifest_digest,
            "host_key_fingerprint": host_key_fingerprint,
            "credential_id": credential_id,
            "transport": transport,
            "dry_run": dry_run,
            "file_count": file_count,
            "byte_count": byte_count,
            "duration_ms": duration_ms,
            "exit_category": exit_category.value,
            "verification_result": verification_result,
            "idempotency_key_ref": idempotency_key_ref,
            "recorded_at": recorded_at,
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
            transport=transport,
            run_id=run_id,
            dry_run=dry_run,
            file_count=file_count,
            byte_count=byte_count,
            duration_ms=duration_ms,
            exit_category=exit_category,
            verification_result=verification_result,
            idempotency_key_ref=idempotency_key_ref,
            recorded_at=recorded_at,
        )
        response_data = InfraResponseData.model_validate(dict(data))
        status = (
            InfraResponseStatus.OK
            if exit_category in {InfraExitCategory.SUCCESS, InfraExitCategory.REPLAY}
            else InfraResponseStatus.FAILED
        )
        return InfraResponse(
            status=status,
            operation=request.operation,
            target=request.target,
            profile=request.profile,
            task_id=request.task_id,
            request_digest=request_digest,
            data=response_data,
            receipt=receipt,
        )

    def _persist_receipt_or_degrade(
        self,
        request: InfraRequest,
        response: InfraResponse,
        *,
        principal_ref: str | None = None,
    ) -> InfraResponse:
        """Never expose a success response when its durable broker receipt is unavailable."""

        if request.operation is InfraOperation.STATUS:
            return response
        if self._record_receipt(response):
            return response
        receipt = response.receipt
        is_committed_operation = (
            isinstance(receipt, InfraOperationReceipt)
            and receipt.operation is InfraOperation.REPLICATE
            and receipt.exit_category in {InfraExitCategory.SUCCESS, InfraExitCategory.REPLAY}
        )
        is_unknown_outcome = isinstance(
            receipt, InfraCapabilityBlockReceipt
        ) and receipt.reason_code in {
            InfraReasonCode.UNKNOWN_COMPLETION,
            InfraReasonCode.OPERATION_IN_FLIGHT,
        }
        if response.status is InfraResponseStatus.BLOCKED and not is_committed_operation:
            # Case A: Operation never became externally effectful (or already failed closed
            # with unknown outcome). Preserve primary operational / security rejection;
            # do not mask it with MISSING_EXECUTION_CAPABILITY or retry unavailable storage.
            return response

        # Case B: Operation reported success or committed state, but durable receipt cannot
        # be established. Fail closed and degrade to UNKNOWN_COMPLETION or MISSING_EXECUTION_CAPABILITY.
        return _block_response(
            request,
            InfraReasonCode.UNKNOWN_COMPLETION
            if is_committed_operation or is_unknown_outcome
            else InfraReasonCode.MISSING_EXECUTION_CAPABILITY,
            policy_revision=getattr(receipt, "policy_revision", "unknown"),
            broker_status="receipt-state-unavailable",
            remediation_code="REPAIR_BROKER_RECEIPT_STATE",
            principal_ref=principal_ref,
            run_id=getattr(receipt, "run_id", None),
            source_manifest_digest=getattr(receipt, "source_manifest_digest", None),
        )

    def _record_receipt(self, response: InfraResponse) -> bool:
        """Persist one bounded receipt without exposing payloads or raw diagnostics."""

        try:
            self._ensure_state_layout()
            receipt = response.receipt
            path = self.state_dir / "receipts" / f"{receipt.receipt_id}.json"
            _atomic_write(path, _json_bytes(receipt.model_dump(mode="json")))
            return True
        except (OSError, ValueError, ValidationError):
            logger.warning("INFRA-1 receipt persistence unavailable")
            return False

    def _has_durable_replicate_receipt(
        self,
        receipt_id: str | None,
        *,
        run_id: str,
        manifest_digest: str,
        profile: InfraProfile | None = None,
        principal_ref: str | None = None,
        key_ref: str | None = None,
        response_request_digest: str | None = None,
        task_id: str | None = None,
    ) -> bool:
        """Validate the canonical durable receipt before treating a run as complete."""

        if not isinstance(receipt_id, str) or not re.fullmatch(r"ir_[0-9a-f]{64}", receipt_id):
            return False
        path = self.state_dir / "receipts" / f"{receipt_id}.json"
        try:
            receipt = InfraOperationReceipt.model_validate(
                json.loads(
                    _read_secure_file(path, max_bytes=MAX_RECEIPT_BYTES, private=True).decode(
                        "utf-8"
                    ),
                    object_pairs_hook=_reject_duplicate_json_keys,
                    parse_constant=_reject_json_constant,
                )
            )
        except (FileNotFoundError, OSError, TypeError, ValueError, ValidationError):
            return False
        valid = (
            receipt.receipt_id == receipt_id
            and receipt.operation is InfraOperation.REPLICATE
            and receipt.target_id
            == (profile.target_id if profile is not None else receipt.target_id)
            and receipt.profile_id
            == (profile.profile_id if profile is not None else receipt.profile_id)
            and receipt.policy_revision
            == (profile.policy_revision if profile is not None else receipt.policy_revision)
            and (principal_ref is None or receipt.principal_ref == principal_ref)
            and (key_ref is None or receipt.idempotency_key_ref == key_ref)
            and (task_id is None or receipt.task_id == task_id)
            and receipt.run_id == run_id
            and receipt.source_manifest_digest == manifest_digest
            and receipt.dry_run is False
            and receipt.exit_category is InfraExitCategory.SUCCESS
            and receipt.verification_result in {"replicated-awaiting-verify", "passed"}
        )
        if not valid or response_request_digest is None:
            return valid
        expected_id = derive_receipt_id(
            "ir",
            {
                "trace_id": receipt.trace_id,
                "request_digest": response_request_digest,
                "operation": receipt.operation.value,
                "target_id": receipt.target_id,
                "profile_id": receipt.profile_id,
                "policy_revision": receipt.policy_revision,
                "principal_ref": receipt.principal_ref,
                "task_id": receipt.task_id,
                "approval_ref": receipt.approval_ref,
                "run_id": receipt.run_id,
                "source_manifest_digest": receipt.source_manifest_digest,
                "host_key_fingerprint": receipt.host_key_fingerprint,
                "credential_id": receipt.credential_id,
                "transport": receipt.transport,
                "dry_run": receipt.dry_run,
                "file_count": receipt.file_count,
                "byte_count": receipt.byte_count,
                "duration_ms": receipt.duration_ms,
                "exit_category": receipt.exit_category.value,
                "verification_result": receipt.verification_result,
                "idempotency_key_ref": receipt.idempotency_key_ref,
                "recorded_at": receipt.recorded_at,
            },
        )
        return receipt.receipt_id == expected_id

    def _timeout_error(
        self, profile: InfraProfile, manifest: _Manifest | None = None
    ) -> InfraBrokerError:
        return InfraBrokerError(
            InfraReasonCode.UNKNOWN_COMPLETION if manifest is not None else InfraReasonCode.TIMEOUT,
            "RESOLVE_BROKER_RUN_BEFORE_RETRY" if manifest is not None else "LOWER_PROFILE_TIMEOUT",
            "timeout",
            policy_revision=profile.policy_revision,
            run_id=manifest.digest_to_run_id() if manifest else None,
            source_manifest_digest=manifest.digest if manifest else None,
        )

    def _operation_timeout_error(
        self,
        profile: InfraProfile,
        manifest: _Manifest,
        operation: InfraOperation,
        *,
        effect_started: bool = False,
    ) -> InfraBrokerError:
        """Return an honest deadline outcome for local validation or read-only verify."""

        if operation is InfraOperation.REPLICATE and effect_started:
            return self._timeout_error(profile, manifest)
        if operation is InfraOperation.REPLICATE:
            return InfraBrokerError(
                InfraReasonCode.TIMEOUT,
                "LOWER_PROFILE_TIMEOUT_OR_SNAPSHOT_SIZE",
                "pre-execution-timeout",
                policy_revision=profile.policy_revision,
                run_id=manifest.digest_to_run_id(),
                source_manifest_digest=manifest.digest,
            )
        return InfraBrokerError(
            InfraReasonCode.TIMEOUT,
            "LOWER_PROFILE_TIMEOUT_OR_SNAPSHOT_SIZE",
            "operation-timeout",
            policy_revision=profile.policy_revision,
            run_id=manifest.digest_to_run_id(),
            source_manifest_digest=manifest.digest,
        )

    def serve_forever(self, *, socket_activation: bool = False) -> None:
        """Serve one-request connections; production service must run non-root."""

        if os.name != "posix" or os.geteuid() == 0:
            raise RuntimeError("INFRA-1 broker must run as a dedicated non-root POSIX identity")
        if not self.authorized_uids and not self.authorized_gids:
            raise RuntimeError("INFRA-1 broker requires an explicit caller UID/GID allowlist")
        self._ensure_state_layout()
        self._cleanup_orphaned_state()
        self._ensure_runtime_dir(scrub=True)
        listener = (
            _listener_from_systemd(self.socket_path) if socket_activation else self._bind_listener()
        )
        self._served_socket = listener
        connection_slots = threading.BoundedSemaphore(MAX_ACTIVE_CONNECTIONS)
        try:
            while True:
                connection, _ = listener.accept()
                if not connection_slots.acquire(blocking=False):
                    connection.close()
                    continue
                try:
                    threading.Thread(
                        target=self._serve_connection,
                        args=(connection, connection_slots),
                        daemon=True,
                    ).start()
                except RuntimeError:
                    connection_slots.release()
                    connection.close()
        finally:
            self._served_socket = None
            if not socket_activation:
                with suppress(OSError):
                    listener.close()
                with suppress(OSError):
                    self.socket_path.unlink()

    def _serve_connection(
        self, connection: socket.socket, connection_slots: threading.BoundedSemaphore
    ) -> None:
        """Serve one connection without allowing a slow peer to serialize accept."""

        try:
            with connection:
                self.handle_connection(connection)
        finally:
            connection_slots.release()

    def _bind_listener(self) -> socket.socket:
        parent = self.socket_path.parent
        if not parent.exists():
            parent.mkdir(parents=True, mode=0o750)
        _assert_secure_directory(parent)
        if self.socket_path.exists():
            if self.socket_path.is_symlink() or not stat.S_ISSOCK(self.socket_path.lstat().st_mode):
                raise RuntimeError("refusing to replace a non-socket broker endpoint")
            raise RuntimeError("refusing to replace an existing broker socket")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.socket_path))
        listener.listen(8)
        return listener


def _listener_from_systemd(socket_path: Path) -> socket.socket:
    """Accept exactly one systemd-passed AF_UNIX listener after PID validation."""

    if os.getenv("LISTEN_PID") != str(os.getpid()) or os.getenv("LISTEN_FDS") != "1":
        raise RuntimeError("invalid systemd socket activation environment")
    listener = socket.fromfd(3, socket.AF_UNIX, socket.SOCK_STREAM)
    if listener.family != socket.AF_UNIX or listener.type != socket.SOCK_STREAM:
        listener.close()
        raise RuntimeError("systemd activation descriptor is not an AF_UNIX stream")
    try:
        if Path(listener.getsockname()).absolute() != path_absolute(socket_path):
            raise RuntimeError("systemd socket activation path mismatch")
    except (OSError, TypeError):
        listener.close()
        raise RuntimeError("systemd socket activation endpoint is invalid") from None
    return listener


def path_absolute(path: Path) -> Path:
    return Path(path).absolute()


def _raise_walk_error(error: OSError) -> None:
    """Turn an os.walk permission/disappearance error into a hard failure."""

    raise error


def _open_directory_no_symlinks(path: Path) -> int:
    """Open every path component relative to a directory descriptor."""

    _assert_no_symlink_components(path)
    descriptor = os.open(
        path.anchor or "/",
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        for component in path.parts[1:]:
            child = os.open(
                component,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("source root is not a directory")
        return descriptor
    except BaseException:
        with suppress(OSError):
            os.close(descriptor)
        raise


def _snapshot_source_root(
    source_root: Path,
    destination_root: Path,
    *,
    root_index: int,
    max_entries: int,
    remaining_bytes: int,
    deadline: float,
) -> tuple[list[dict[str, object]], int, int, list[str]]:
    """Walk a source root using descriptor-relative, no-follow operations."""

    root_fd = _open_directory_no_symlinks(source_root)
    try:
        root_stat = os.fstat(root_fd)
    except BaseException:
        with suppress(OSError):
            os.close(root_fd)
        raise
    stack: list[tuple[str, int]] = [("", root_fd)]
    entries: list[dict[str, object]] = []
    directories: list[str] = []
    total_bytes = 0
    entry_count = 0
    try:
        while stack:
            relative_dir, current_fd = stack.pop()
            try:
                if time.monotonic() >= deadline:
                    raise TimeoutError("snapshot deadline elapsed")
                children: list[os.DirEntry[str]] = []
                with os.scandir(current_fd) as iterator:
                    for child in iterator:
                        children.append(child)
                        if len(children) > max_entries:
                            raise ValueError("source snapshot exceeds its entry bound")
                children.sort(key=lambda entry: entry.name)
                initial_names = {child.name for child in children}
                for child in children:
                    entry_count += 1
                    if entry_count > max_entries:
                        raise ValueError("source snapshot exceeds its entry bound")
                    if time.monotonic() >= deadline:
                        raise TimeoutError("snapshot deadline elapsed")
                    relative = f"{relative_dir}/{child.name}" if relative_dir else child.name
                    _validate_relative_source_path(relative)
                    metadata = child.stat(follow_symlinks=False)
                    if stat.S_ISLNK(metadata.st_mode):
                        raise ValueError("source tree contains a symlink")
                    if relative.count("/") > 32 or _is_sensitive_source_name(relative):
                        raise ValueError("source path is outside the admitted data class")
                    if stat.S_ISDIR(metadata.st_mode):
                        if metadata.st_dev != root_stat.st_dev:
                            raise ValueError("source tree crosses a mount boundary")
                        child_fd = os.open(
                            child.name,
                            os.O_RDONLY
                            | getattr(os, "O_DIRECTORY", 0)
                            | getattr(os, "O_NOFOLLOW", 0)
                            | getattr(os, "O_CLOEXEC", 0),
                            dir_fd=current_fd,
                        )
                        child_after_open = os.fstat(child_fd)
                        if (
                            child_after_open.st_dev != metadata.st_dev
                            or child_after_open.st_ino != metadata.st_ino
                            or not stat.S_ISDIR(child_after_open.st_mode)
                        ):
                            os.close(child_fd)
                            raise ValueError("source directory changed during snapshot")
                        destination_directory = destination_root / relative
                        destination_directory.mkdir(mode=0o700)
                        _assert_secure_directory(destination_directory, private=True)
                        directories.append(relative)
                        stack.append((relative, child_fd))
                        continue
                    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                        raise ValueError("source entry is not a regular single-link file")
                    if (
                        len(entries) >= max_entries
                        or metadata.st_size > remaining_bytes - total_bytes
                    ):
                        raise ValueError("source snapshot exceeds its resource bound")
                    copied_file = destination_root / relative
                    copied_file.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                    _assert_secure_directory(copied_file.parent, private=True)
                    file_digest, file_size = _copy_source_file(
                        current_fd,
                        child.name,
                        copied_file,
                        metadata,
                        deadline,
                        remaining_bytes - total_bytes,
                    )
                    total_bytes += file_size
                    entries.append(
                        {
                            "root": root_index,
                            "path": relative,
                            "size": file_size,
                            "sha256": file_digest,
                        }
                    )
                final_names: set[str] = set()
                with os.scandir(current_fd) as iterator:
                    for entry in iterator:
                        final_names.add(entry.name)
                        if len(final_names) > max_entries:
                            raise ValueError("source directory exceeds its entry bound")
                if final_names != initial_names:
                    raise ValueError("source directory changed during snapshot")
            finally:
                os.close(current_fd)
        return entries, total_bytes, entry_count, directories
    except BaseException:
        for _, descriptor in stack:
            with suppress(OSError):
                os.close(descriptor)
        raise


def _copy_source_file(
    source_directory_fd: int,
    source_name: str,
    destination: Path,
    expected: os.stat_result,
    deadline: float,
    max_bytes: int,
) -> tuple[str, int]:
    """Copy one regular source file relative to its already-open parent."""

    source_fd = os.open(
        source_name,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        dir_fd=source_directory_fd,
    )
    destination_fd = -1
    digest = hashlib.sha256()
    total = 0
    copied = False
    try:
        source_stat = os.fstat(source_fd)
        if (
            not stat.S_ISREG(source_stat.st_mode)
            or source_stat.st_nlink != 1
            or source_stat.st_size < 0
            or source_stat.st_dev != expected.st_dev
            or source_stat.st_ino != expected.st_ino
            or source_stat.st_size != expected.st_size
        ):
            raise ValueError("source entry is not a regular single-link file")
        destination_fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("snapshot deadline elapsed")
            chunk = os.read(source_fd, min(64 * 1024, max_bytes - total + 1))
            if not chunk:
                break
            if total + len(chunk) > max_bytes:
                raise ValueError("source snapshot exceeds its resource bound")
            digest.update(chunk)
            total += len(chunk)
            written = 0
            while written < len(chunk):
                written += os.write(destination_fd, chunk[written:])
        after = os.fstat(source_fd)
        if (
            after.st_dev != source_stat.st_dev
            or after.st_ino != source_stat.st_ino
            or after.st_size != total
            or after.st_mtime_ns != source_stat.st_mtime_ns
            or after.st_ctime_ns != source_stat.st_ctime_ns
        ):
            raise ValueError("source entry changed during snapshot")
        os.fsync(destination_fd)
        copied = True
        return digest.hexdigest(), total
    finally:
        os.close(source_fd)
        if destination_fd >= 0:
            os.close(destination_fd)
        if copied:
            _fsync_directory(destination.parent)
        else:
            with suppress(OSError):
                _unlink_and_fsync(destination)


def _validate_relative_source_path(relative: str) -> None:
    if (
        not relative
        or "\\" in relative
        or "://" in relative
        or relative.startswith("-")
        or any(part in {"", ".", ".."} for part in relative.split("/"))
        or any(ord(char) < 32 or ord(char) == 127 for char in relative)
        or len(relative) > 512
    ):
        raise ValueError("source path is unsafe")
    if any(part.startswith("-") for part in relative.split("/")):
        raise ValueError("source path component is unsafe")


def _is_sensitive_source_name(relative: str) -> bool:
    names = {part.casefold() for part in relative.split("/")}
    return bool(
        names.intersection({".git", ".ssh", ".env", ".git-credentials", "known_hosts"})
        or any(
            part.casefold().endswith((".pem", ".key", ".p12", ".pfx"))
            or part.casefold() in {"id_rsa", "id_ed25519", "credentials", "credentials.json"}
            for part in names
        )
    )


def _build_rsync_argv(
    profile: InfraProfile,
    *,
    source_dir: Path,
    run_id: str,
    root_index: int,
    known_hosts_file: Path,
    credential_file: Path,
    operation: InfraOperation,
) -> list[str]:
    """Build a fixed rsync argv; caller-controlled options never enter this list."""

    host = f"[{profile.hostname}]" if ":" in profile.hostname else profile.hostname
    destination = (
        f"{profile.remote_user}@{host}:{profile.remote_root}/runs/{run_id}/source-{root_index:03d}/"
    )
    argv = [
        RSYNC_BINARY,
        "-rt",
        "--no-motd",
        "--no-links",
        "--no-devices",
        "--no-specials",
        "--no-owner",
        "--no-group",
        f"--timeout={profile.timeout_seconds}",
        f"--contimeout={profile.timeout_seconds}",
        "--itemize-changes",
        "--out-format=%i",
        "--dry-run"
        if operation in {InfraOperation.PROBE, InfraOperation.RSYNC_DRY_RUN, InfraOperation.VERIFY}
        else "--recursive",
        "--rsh",
        _build_ssh_command(profile, known_hosts_file, credential_file),
        str(source_dir) + "/",
        destination,
    ]
    if operation is InfraOperation.VERIFY:
        argv.insert(3, "--checksum")
    return argv


def _build_verify_inventory_argv(
    profile: InfraProfile,
    *,
    run_id: str,
    root_index: int,
    known_hosts_file: Path,
    credential_file: Path,
    destination_dir: Path,
) -> list[str]:
    """Build the fixed read-only rsync inventory request used by verify."""

    host = f"[{profile.hostname}]" if ":" in profile.hostname else profile.hostname
    remote = (
        f"{profile.remote_user}@{host}:{profile.remote_root}/runs/{run_id}/source-{root_index:03d}/"
    )
    return [
        RSYNC_BINARY,
        "-r",
        "--list-only",
        "--dry-run",
        "--checksum",
        "--no-links",
        "--no-devices",
        "--no-specials",
        "--no-motd",
        "--out-format=%i\t%n",
        "--rsh",
        _build_ssh_command(profile, known_hosts_file, credential_file),
        remote,
        str(destination_dir) + "/",
    ]


def _build_verify_content_argv(
    profile: InfraProfile,
    *,
    run_id: str,
    root_index: int,
    known_hosts_file: Path,
    credential_file: Path,
    files_from: Path,
    destination_dir: Path,
    max_file_bytes: int,
) -> list[str]:
    """Build a read-only remote-to-local pull for the already enumerated files."""

    host = f"[{profile.hostname}]" if ":" in profile.hostname else profile.hostname
    remote = (
        f"{profile.remote_user}@{host}:{profile.remote_root}/runs/{run_id}/source-{root_index:03d}/"
    )
    return [
        RSYNC_BINARY,
        "-rt",
        "--checksum",
        "--files-from=" + str(files_from),
        f"--max-size={max_file_bytes}",
        "--no-motd",
        "--no-links",
        "--no-devices",
        "--no-specials",
        f"--timeout={profile.timeout_seconds}",
        f"--contimeout={profile.timeout_seconds}",
        "--rsh",
        _build_ssh_command(profile, known_hosts_file, credential_file),
        remote,
        str(destination_dir) + "/",
    ]


def _run_bounded_process(
    argv: list[str], timeout_seconds: float, max_output_bytes: int = 1_000_000
) -> _ProcessResult:
    """Run fixed argv with bounded I/O, process-group cleanup, and no ambient secrets."""

    started = time.perf_counter()
    environment = _safe_environment()
    try:
        process = subprocess.Popen(  # noqa: S603 - argv is broker-generated and shell=False
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            shell=False,
            close_fds=True,
            start_new_session=True,
        )
    except FileNotFoundError:
        return _ProcessResult(
            None, 0, 0, InfraExitCategory.PROCESS_UNAVAILABLE, elapsed_ms(started)
        )
    except OSError:
        # No child exists when Popen itself fails; callers may safely release a
        # pre-execution reservation and retry after repairing the fixed runtime.
        return _ProcessResult(
            None, 0, 0, InfraExitCategory.PROCESS_UNAVAILABLE, elapsed_ms(started)
        )

    selector = selectors.DefaultSelector()
    assert process.stdout is not None
    assert process.stderr is not None
    selector.register(process.stdout, selectors.EVENT_READ)
    selector.register(process.stderr, selectors.EVENT_READ)
    stdout_sample = bytearray()
    stderr_sample = bytearray()
    stdout_bytes = 0
    stderr_bytes = 0
    deadline = time.perf_counter() + timeout_seconds
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
                    if len(stdout_sample) < max_output_bytes:
                        stdout_sample.extend(chunk[: max_output_bytes - len(stdout_sample)])
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
            _terminate_process_group(process)
        else:
            try:
                process.wait(timeout=max(0.1, deadline - time.perf_counter()))
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process_group(process)
    except BaseException:
        _terminate_process_group(process)
        raise
    finally:
        selector.close()
        with suppress(OSError):
            process.stdout.close()
        with suppress(OSError):
            process.stderr.close()

    if timed_out:
        category = InfraExitCategory.TIMEOUT
    elif output_limited:
        category = InfraExitCategory.OUTPUT_LIMIT
    elif process.returncode == 0:
        category = InfraExitCategory.SUCCESS
    else:
        category = _classify_process_failure(bytes(stderr_sample))
    return _ProcessResult(
        process.returncode,
        stdout_bytes,
        stderr_bytes,
        category,
        elapsed_ms(started),
        bytes(stdout_sample),
        bytes(stderr_sample),
        output_limited,
    )


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    """Terminate and reap the broker-created process group; no retry is attempted."""

    with suppress(OSError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        with suppress(OSError):
            os.killpg(process.pid, signal.SIGKILL)
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=1)


def elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _classify_process_failure(stderr_sample: bytes) -> InfraExitCategory:
    """Map bounded SSH/rsync diagnostics to finite categories without returning text."""

    message = stderr_sample.decode("utf-8", errors="replace").casefold()
    if (
        "remote host identification has changed" in message
        or "host key verification failed" in message
    ):
        return InfraExitCategory.HOST_IDENTITY_MISMATCH
    if "known_hosts" in message or "no matching host key type" in message:
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
            "connection closed",
        )
    ):
        return InfraExitCategory.NETWORK_UNAVAILABLE
    if "permission denied" in message or "access denied" in message or "rrsync" in message:
        return InfraExitCategory.REMOTE_REJECTED
    return InfraExitCategory.FAILED


def _rsync_verification_is_clean(result: _ProcessResult) -> bool:
    """Fail closed on any unparsed/truncated itemized output."""

    if result.category is not InfraExitCategory.SUCCESS or result.output_truncated:
        return False
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
        if len(line) >= 11 and line[0] in "<>ch*":
            return False
        # rsync emitted something outside the fixed itemized protocol.
        if line:
            return False
    return True


def _rsync_inventory_is_exact(
    result: _ProcessResult, expected: Mapping[str, InfraInventoryType]
) -> bool:
    """Validate bounded read-only receiver names and entry types."""

    if result.category is not InfraExitCategory.SUCCESS or result.output_truncated:
        return False
    observed: set[str] = set()
    for raw_line in result.stdout_sample.decode("utf-8", errors="replace").splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            continue
        fields = line.split("\t", 1)
        if len(fields) != 2 or len(fields[0]) < 2:
            return False
        itemized_type = fields[0][1]
        normalized = fields[1].removeprefix("./")
        if normalized in {"", "."} and itemized_type == "d":
            continue
        if itemized_type == "d":
            normalized = normalized.rstrip("/")
            expected_type: InfraInventoryType = "directory"
        elif itemized_type == "f":
            if normalized.endswith("/"):
                return False
            expected_type = "file"
        else:
            return False
        if (
            not normalized
            or normalized not in expected
            or normalized in observed
            or expected[normalized] != expected_type
        ):
            return False
        observed.add(normalized)
    return observed == set(expected)


def _hash_secure_file(
    path: Path,
    *,
    expected_size: int,
    max_bytes: int,
    deadline: float | None = None,
) -> tuple[int, str]:
    """Hash one downloaded regular file without loading it into process memory."""

    candidate = Path(path)
    _assert_no_symlink_components(candidate)
    _assert_secure_ancestors(candidate)
    before = candidate.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size != expected_size
        or before.st_size > max_bytes
    ):
        raise ValueError("downloaded inventory file is not within its expected bound")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(candidate, flags)
    digest = hashlib.sha256()
    total = 0
    try:
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
        ):
            raise ValueError("downloaded inventory file changed during admission")
        while total <= max_bytes:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("verify digest deadline elapsed")
            chunk = os.read(descriptor, min(64 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("downloaded inventory exceeds its size limit")
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (
            after.st_dev != before.st_dev
            or after.st_ino != before.st_ino
            or after.st_size != total
            or after.st_mtime_ns != before.st_mtime_ns
            or after.st_ctime_ns != before.st_ctime_ns
        ):
            raise ValueError("downloaded inventory file changed while it was read")
        return total, digest.hexdigest()
    finally:
        os.close(descriptor)


def _verify_pulled_inventory(
    destination_root: Path,
    expected: dict[str, tuple[int, str]],
    expected_inventory: Mapping[str, InfraInventoryType],
    *,
    deadline: float | None = None,
    max_bytes: int,
) -> bool:
    """Check exact files, parent directories, sizes, and digests in a pull."""

    try:
        root_metadata = destination_root.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        return False
    expected_dirs = set(expected_inventory).difference(expected)
    observed_files: set[str] = set()
    observed_dirs: set[str] = set()
    total_expected = sum(size for size, _ in expected.values())
    if total_expected > max_bytes + max(0, expected.get(".power-infra-run.json", (0, ""))[0]):
        return False
    try:
        for current_text, dirnames, filenames in os.walk(
            destination_root,
            topdown=True,
            onerror=_raise_walk_error,
            followlinks=False,
        ):
            current = Path(current_text)
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("verify inventory deadline elapsed")
            if current != destination_root:
                relative_dir = current.relative_to(destination_root).as_posix()
                if relative_dir not in expected_dirs:
                    return False
                observed_dirs.add(relative_dir)
            for dirname in sorted(dirnames):
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("verify inventory deadline elapsed")
                directory = current / dirname
                metadata = directory.lstat()
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                    return False
            for filename in sorted(filenames):
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("verify inventory deadline elapsed")
                candidate = current / filename
                relative = candidate.relative_to(destination_root).as_posix()
                if relative not in expected or relative in observed_files:
                    return False
                size, digest = expected[relative]
                actual_size, actual_digest = _hash_secure_file(
                    candidate,
                    expected_size=size,
                    max_bytes=min(max_bytes, max(1, size)),
                    deadline=deadline,
                )
                if actual_size != size or actual_digest != digest:
                    return False
                observed_files.add(relative)
    except TimeoutError:
        raise
    except (OSError, ValueError):
        return False
    return observed_files == set(expected) and observed_dirs == expected_dirs


def datetime_from_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("approval expiry must include timezone")
    return parsed.astimezone(UTC)


def datetime_now_utc() -> datetime:
    return datetime.now(UTC)


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
    serve.add_argument("--credential-dir", default=None)
    serve.add_argument("--caller-allowlist", default=None)
    serve.add_argument("--socket-activation", action="store_true")
    serve.add_argument("--allow-uid", action="append", type=int, default=[])
    serve.add_argument("--allow-gid", action="append", type=int, default=[])
    args = parser.parse_args(argv)
    if args.command != "serve":
        raise SystemExit(2)
    if os.name != "posix" or os.geteuid() == 0:
        raise SystemExit("power-infra-broker must run as a dedicated non-root POSIX identity")
    if args.caller_allowlist:
        configured_uids, configured_gids = _load_caller_allowlist(Path(args.caller_allowlist))
    else:
        configured_uids = _parse_id_set(os.getenv("POWER_INFRA_ALLOWED_UIDS"))
        configured_gids = _parse_id_set(os.getenv("POWER_INFRA_ALLOWED_GIDS"))
    server = InfraBrokerServer(
        policy_path=Path(args.policy),
        socket_path=Path(args.socket),
        state_dir=Path(args.state),
        credential_dir=Path(args.credential_dir) if args.credential_dir else None,
        approval_path=Path(args.approvals),
        authorized_uids=set(args.allow_uid) | configured_uids,
        authorized_gids=set(args.allow_gid) | configured_gids,
    )
    server.serve_forever(socket_activation=args.socket_activation)


def _parse_id_set(value: str | None) -> set[int]:
    if not value:
        return set()
    values: set[int] = set()
    for item in value.split(","):
        if not item.isdigit():
            raise SystemExit("POWER_INFRA_ALLOWED_UIDS/GIDS must contain decimal IDs only")
        values.add(int(item))
    return values


def _load_caller_allowlist(path: Path) -> tuple[set[int], set[int]]:
    """Load a strict, non-secret caller UID/GID allowlist from operator storage."""

    try:
        raw = _read_secure_file(path, max_bytes=MAX_POLICY_BYTES, private=False)
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except (OSError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit("caller allowlist is unavailable or invalid") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "uids", "gids"}
        or payload.get("schema_version") != "power.infra-callers.v1"
        or not isinstance(payload.get("uids"), list)
        or not isinstance(payload.get("gids"), list)
    ):
        raise SystemExit("caller allowlist schema is invalid")
    uids = cast("list[object]", payload["uids"])
    gids = cast("list[object]", payload["gids"])
    if len(uids) > 64 or len(gids) > 64:
        raise SystemExit("caller allowlist is too large")
    parsed_uids = {value for value in uids if type(value) is int and 0 < value <= 2_147_483_647}
    parsed_gids = {value for value in gids if type(value) is int and 0 < value <= 2_147_483_647}
    if len(parsed_uids) != len(uids) or len(parsed_gids) != len(gids):
        raise SystemExit("caller allowlist IDs must be positive decimal integers")
    if not parsed_uids and not parsed_gids:
        raise SystemExit("caller allowlist must authorize at least one UID or GID")
    return parsed_uids, parsed_gids


if __name__ == "__main__":  # pragma: no cover - exercised by package/service smoke
    broker_main()


__all__ = [
    "DEFAULT_APPROVAL_PATH",
    "DEFAULT_POLICY_PATH",
    "DEFAULT_RUNTIME_DIR",
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
    "peer_principal",
]
