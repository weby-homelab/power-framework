"""Adversarial INFRA-1 tests for the protected admission boundary."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import struct
import sys
import threading
import time
from base64 import b64encode
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from power_framework import __version__
from power_framework.core import infra_broker
from power_framework.core.application import (
    ApplicationService,
    DeadlineExceededError,
    RequestContext,
    ResultBudgetExceededError,
)
from power_framework.core.errors import ConflictError
from power_framework.core.infra_broker import (
    InfraBrokerError,
    InfraBrokerServer,
    _block_response,
    _copy_source_file,
    _encode_frame,
    _ProcessResult,
    _receive_frame,
    _request_digest,
    _rsync_inventory_is_exact,
    _rsync_verification_is_clean,
    _run_bounded_process,
    build_ssh_options,
    load_infra_policy,
)
from power_framework.core.infra_models import (
    InfraCapabilityBlockReceipt,
    InfraExitCategory,
    InfraOperation,
    InfraOperationReceipt,
    InfraPolicyFile,
    InfraReasonCode,
    InfraRequest,
    InfraResponse,
    InfraResponseData,
    canonical_profile_digest,
    idempotency_key_reference,
    ssh_fingerprint_from_blob,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _profile_fixture(
    tmp_path: Path,
    *,
    root_count: int = 1,
    approval_policy: str = "standing",
    dry_run_policy: str = "required",
    allowed_principal_refs: list[str] | None = None,
) -> tuple[Path, Path, list[Path], Path, bytes]:
    source_roots: list[Path] = []
    for index in range(root_count):
        root = tmp_path / f"source-{index}"
        root.mkdir()
        (root / f"note-{index}.txt").write_text(f"fixture {index}\n", encoding="utf-8")
        source_roots.append(root)

    key_blob = b"synthetic-host-key-for-infra-tests"
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(
        f"prxmx01 ssh-ed25519 {b64encode(key_blob).decode('ascii')}\n",
        encoding="utf-8",
    )
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    (credentials / "power-vault-key").write_bytes(b"synthetic-key-boundary")
    (credentials / "power-vault-key").chmod(0o600)
    (credentials / "power-vault-verify-key").write_bytes(b"synthetic-verify-key-boundary")
    (credentials / "power-vault-verify-key").chmod(0o600)
    policy = tmp_path / "policy.json"
    profile: dict[str, object] = {
        "profile_id": "power-vault",
        "target_id": "prxmx01",
        "hostname": "prxmx01",
        "port": 22,
        "remote_user": "power-receiver",
        "remote_root": "/srv/power-vault/staging",
        "allowed_operations": ["probe", "rsync-dry-run", "replicate", "verify"],
        "source_roots": [str(root) for root in source_roots],
        "known_hosts_file": str(known_hosts),
        "host_key_fingerprint": ssh_fingerprint_from_blob(key_blob),
        "credential_id": "power-vault-key",
        "verify_credential_id": "power-vault-verify-key",
        "allow_plaintext_credential_fallback": True,
        "allowed_principal_refs": allowed_principal_refs or [],
        "max_files": 100,
        "max_bytes": 100_000,
        "timeout_seconds": 30,
        "max_output_bytes": 8_192,
        "max_concurrent": 1,
        "max_retries": 0,
        "approval_policy": approval_policy,
        "dry_run_policy": dry_run_policy,
        "receiver_mode": "rrsync-immutable",
        "immutable_snapshot": True,
        "no_delete": True,
        "policy_revision": "test-policy-v1",
    }
    if approval_policy == "standing":
        profile["standing_approval_ref"] = "standing-power-vault"
        profile["standing_principal_ref"] = f"uid:{os.getuid()}"
    policy.write_text(
        json.dumps({"schema_version": "power.infra-policy.v1", "profiles": [profile]}),
        encoding="utf-8",
    )
    return policy, credentials, source_roots, known_hosts, key_blob


def _server(
    policy: Path,
    credentials: Path,
    tmp_path: Path,
    runner: Callable[[list[str], float, int], _ProcessResult] | None = None,
    *,
    approval_path: Path | None = None,
    authorized_uids: set[int] | None = None,
) -> InfraBrokerServer:
    return InfraBrokerServer(
        policy_path=policy,
        state_dir=tmp_path / "state",
        credential_dir=credentials,
        approval_path=approval_path or tmp_path / "approvals.json",
        authorized_uids=authorized_uids or {os.getuid()},
        command_runner=runner,
    )


def _request(operation: InfraOperation, **kwargs: object) -> InfraRequest:
    return InfraRequest(
        operation=operation,
        target="prxmx01",
        profile="power-vault",
        **kwargs,
    )


def test_request_contract_rejects_prompt_injection_fields() -> None:
    with pytest.raises(ValidationError):
        InfraRequest.model_validate(
            {
                "operation": "replicate",
                "target": "prxmx01",
                "profile": "power-vault",
                "idempotency_key": "request-1",
                "host": "attacker.example",
                "username": "root",
                "private_key": "sentinel",
                "remote_command": "id",
                "rsync_options": ["--delete"],
                "known_hosts": "disable",
            }
        )


@pytest.mark.parametrize(
    ("operation", "kwargs"),
    [
        (InfraOperation.REPLICATE, {}),
        (InfraOperation.VERIFY, {}),
        (InfraOperation.VERIFY, {"run_id": "run_not-a-digest"}),
    ],
)
def test_request_requires_execution_references(
    operation: InfraOperation, kwargs: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        _request(operation, **kwargs)


def test_missing_business_identifiers_are_input_required_not_capability_block(
    tmp_path: Path,
) -> None:
    from power_framework.core.infra_broker import InfraBrokerClient

    response = InfraBrokerClient(socket_path=tmp_path / "missing.sock").execute(
        InfraRequest(operation=InfraOperation.PROBE, profile="power-vault")
    )
    assert isinstance(response.receipt, InfraCapabilityBlockReceipt)
    assert response.receipt.reason_code == "REQUEST_INPUT_MISSING"
    assert response.receipt.required_capability == "infra.ssh.probe.v1"


def test_status_reports_client_support_separately_from_broker_availability(
    tmp_path: Path,
) -> None:
    from power_framework.core.infra_broker import InfraBrokerClient

    response = InfraBrokerClient(socket_path=tmp_path / "missing.sock").status()

    assert response.data.client_supported is True
    assert response.data.transport == "unix"
    assert response.data.broker_status in {"broker-not-installed", "broker-disabled"}


def test_response_binding_rejects_wrong_nonce_and_operation(tmp_path: Path) -> None:
    from power_framework.core.infra_broker import InfraBrokerClient

    socket_path = tmp_path / "broker.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(1)
    request = InfraRequest(operation=InfraOperation.STATUS)

    def serve_once() -> None:
        connection, _ = listener.accept()
        with connection:
            _receive_frame(connection)
            receipt = InfraOperationReceipt(
                receipt_id="ir_" + "a" * 64,
                trace_id="tr_" + "b" * 32,
                operation=InfraOperation.STATUS,
                policy_revision="none",
                principal_ref=f"uid:{os.getuid()}",
                transport="unix",
                dry_run=True,
                exit_category="success",
                verification_result="status",
                recorded_at="2026-09-13T00:00:00+00:00",
            )
            response = InfraResponse(
                status="ok",
                operation=InfraOperation.STATUS,
                request_digest=_request_digest(request),
                data=InfraResponseData(broker_status="active", transport="unix"),
                receipt=receipt,
            )
            connection.sendall(
                _encode_frame(
                    {
                        "schema_version": "power.infra-wire-response.v1",
                        "nonce": "0" * 32,
                        "response": response.model_dump(mode="json"),
                    }
                )
            )

    worker = threading.Thread(target=serve_once)
    worker.start()
    try:
        result = InfraBrokerClient(
            socket_path=socket_path,
            expected_broker_uid=os.getuid(),
        ).execute(request)
    finally:
        worker.join(timeout=2)
        listener.close()
    assert isinstance(result.receipt, InfraCapabilityBlockReceipt)
    assert result.receipt.reason_code == "PROTOCOL_ERROR"


def test_response_binding_rejects_foreign_block_receipt() -> None:
    request = _request(InfraOperation.PROBE)
    response = _block_response(request, InfraReasonCode.MISSING_EXECUTION_CAPABILITY)
    forged_receipt = response.receipt.model_copy(update={"target_id": "other-target"})
    with pytest.raises(ValidationError, match="target/profile"):
        InfraResponse.model_validate(
            response.model_copy(update={"receipt": forged_receipt}).model_dump(mode="json")
        )


def test_response_binding_rejects_ok_status_for_failed_operation_receipt() -> None:
    request = _request(InfraOperation.PROBE)
    receipt = InfraOperationReceipt(
        receipt_id="ir_" + "e" * 64,
        trace_id="tr_" + "f" * 32,
        operation=InfraOperation.PROBE,
        target_id=request.target,
        profile_id=request.profile,
        policy_revision="stub-policy-v1",
        principal_ref=f"uid:{os.getuid()}",
        transport="ssh-rsync",
        dry_run=True,
        exit_category="failed",
        verification_result="unknown",
        recorded_at="2026-09-13T00:00:00+00:00",
    )
    with pytest.raises(ValidationError, match="exit category"):
        InfraResponse(
            status="ok",
            operation=InfraOperation.PROBE,
            target=request.target,
            profile=request.profile,
            request_digest=_request_digest(request),
            receipt=receipt,
        )


def test_broker_frame_deadline_is_absolute_and_deep_json_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(infra_broker, "SERVER_IO_TIMEOUT_SECONDS", 0.05)
    server = InfraBrokerServer(
        policy_path=tmp_path / "missing.json",
        state_dir=tmp_path / "state",
        credential_dir=tmp_path / "credentials",
        authorized_uids={os.getuid()},
    )
    left, right = socket.socketpair()
    worker = threading.Thread(target=server.handle_connection, args=(left,))
    worker.start()
    right.sendall(struct.pack(">I", 10))
    right.sendall(b"{")
    time.sleep(0.08)
    worker.join(timeout=1)
    assert not worker.is_alive()
    left.close()
    right.close()

    left, right = socket.socketpair()
    worker = threading.Thread(target=server.handle_connection, args=(left,))
    worker.start()
    nested = b"[" * 4000 + b"0" + b"]" * 4000
    right.sendall(struct.pack(">I", len(nested)) + nested)
    worker.join(timeout=1)
    assert not worker.is_alive()
    left.close()
    right.close()


def test_unauthorized_socket_peer_cannot_create_receipts(tmp_path: Path) -> None:
    server = InfraBrokerServer(
        policy_path=tmp_path / "missing.json",
        state_dir=tmp_path / "state",
        credential_dir=tmp_path / "credentials",
        authorized_uids={os.getuid() + 1},
    )
    left, right = socket.socketpair()
    try:
        worker = threading.Thread(target=server.handle_connection, args=(left,))
        worker.start()
        worker.join(timeout=1)
        assert not worker.is_alive()
    finally:
        left.close()
        right.close()
    assert not (tmp_path / "state").exists()


def test_profile_and_policy_are_strict_and_profile_digest_is_complete(tmp_path: Path) -> None:
    policy, _credentials, _roots, _known_hosts, _key = _profile_fixture(tmp_path)
    loaded = load_infra_policy(policy)
    profile = loaded.profiles[0]
    digest_before = canonical_profile_digest(profile)
    changed = json.loads(policy.read_text(encoding="utf-8"))
    changed["profiles"][0]["remote_root"] = "/srv/other"
    policy.write_text(json.dumps(changed), encoding="utf-8")
    digest_after = canonical_profile_digest(load_infra_policy(policy).profiles[0])
    assert digest_before != digest_after
    with pytest.raises(ValidationError):
        InfraPolicyFile.model_validate(
            {"schema_version": "power.infra-policy.v1", "profiles": [], "unknown": True}
        )


def test_policy_loader_rejects_duplicate_json_and_yaml_keys(tmp_path: Path) -> None:
    json_policy = tmp_path / "duplicate.json"
    json_policy.write_text(
        '{"schema_version":"power.infra-policy.v1","schema_version":"power.infra-policy.v1","profiles":[]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"schema|policy"):
        load_infra_policy(json_policy)

    yaml_policy = tmp_path / "duplicate.yaml"
    yaml_policy.write_text(
        "schema_version: power.infra-policy.v1\nschema_version: power.infra-policy.v1\nprofiles: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"schema|policy"):
        load_infra_policy(yaml_policy)


def test_source_root_cannot_overlap_credential_state_or_policy(tmp_path: Path) -> None:
    policy, credentials, roots, _known_hosts, _key = _profile_fixture(tmp_path)
    document = json.loads(policy.read_text(encoding="utf-8"))
    document["profiles"][0]["source_roots"] = [str(credentials)]
    policy.write_text(json.dumps(document), encoding="utf-8")
    calls: list[list[str]] = []
    server = _server(
        policy,
        credentials,
        tmp_path,
        lambda argv, _timeout, _limit: (
            calls.append(argv) or _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)
        ),
    )
    response = server.handle_request(
        _request(InfraOperation.RSYNC_DRY_RUN), principal_ref=f"uid:{os.getuid()}"
    )
    assert response.receipt.reason_code == "POLICY_INVALID"
    assert calls == []
    assert roots


def test_profile_principal_acl_is_checked_after_kernel_principal_derivation(tmp_path: Path) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(
        tmp_path, allowed_principal_refs=["uid:424242"]
    )
    calls: list[list[str]] = []
    server = _server(
        policy,
        credentials,
        tmp_path,
        lambda argv, _timeout, _limit: (
            calls.append(argv) or _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)
        ),
    )
    response = server.handle_request(
        _request(InfraOperation.RSYNC_DRY_RUN), principal_ref=f"uid:{os.getuid()}"
    )
    assert response.receipt.reason_code == "PRINCIPAL_DENIED"
    assert calls == []


def test_non_systemd_credential_directory_requires_explicit_lower_assurance_opt_in(
    tmp_path: Path,
) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(
        tmp_path, dry_run_policy="standing"
    )
    document = json.loads(policy.read_text(encoding="utf-8"))
    document["profiles"][0]["allow_plaintext_credential_fallback"] = False
    policy.write_text(json.dumps(document), encoding="utf-8")
    calls: list[list[str]] = []
    response = _server(
        policy,
        credentials,
        tmp_path,
        lambda argv, _timeout, _limit: (
            calls.append(argv) or _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)
        ),
    ).handle_request(_request(InfraOperation.RSYNC_DRY_RUN), principal_ref=f"uid:{os.getuid()}")
    assert response.receipt.reason_code == "BROKER_CREDENTIAL_UNAVAILABLE"
    assert calls == []


def test_server_rejects_a_peer_without_an_explicit_global_acl(tmp_path: Path) -> None:
    server = InfraBrokerServer(
        policy_path=tmp_path / "missing.json",
        state_dir=tmp_path / "state",
        credential_dir=tmp_path / "credentials",
    )
    left, right = socket.socketpair()
    try:
        with pytest.raises(InfraBrokerError) as error:
            server.peer_principal(left)
        assert error.value.reason_code == "PRINCIPAL_DENIED"
    finally:
        left.close()
        right.close()


@pytest.mark.parametrize("mutator", ["symlink", "hardlink", "fifo", "leading-dash", "sensitive"])
def test_source_snapshot_rejects_unsafe_entries_before_runner(tmp_path: Path, mutator: str) -> None:
    policy, credentials, roots, _known_hosts, _key = _profile_fixture(tmp_path)
    source = roots[0]
    if mutator == "symlink":
        (source / "escape").symlink_to(tmp_path / "outside")
    elif mutator == "hardlink":
        os.link(source / "note-0.txt", source / "hardlink.txt")
    elif mutator == "fifo":
        os.mkfifo(source / "fifo")
    elif mutator == "leading-dash":
        (source / "-option.txt").write_text("unsafe", encoding="utf-8")
    else:
        (source / ".env").write_text("SENTINEL_SOURCE_SECRET", encoding="utf-8")
    calls: list[list[str]] = []
    server = _server(
        policy,
        credentials,
        tmp_path,
        lambda argv, _timeout, _limit: (
            calls.append(argv) or _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)
        ),
    )
    response = server.handle_request(
        _request(InfraOperation.RSYNC_DRY_RUN), principal_ref=f"uid:{os.getuid()}"
    )
    assert response.status == "blocked"
    assert response.receipt.reason_code in {"RESOURCE_LIMIT", "POLICY_INVALID"}
    assert calls == []


def test_source_snapshot_rejects_a_symlinked_source_root(tmp_path: Path) -> None:
    policy, credentials, roots, _known_hosts, _key = _profile_fixture(tmp_path)
    source_link = tmp_path / "source-link"
    source_link.symlink_to(roots[0], target_is_directory=True)
    document = json.loads(policy.read_text(encoding="utf-8"))
    document["profiles"][0]["source_roots"] = [str(source_link)]
    policy.write_text(json.dumps(document), encoding="utf-8")
    calls: list[list[str]] = []
    response = _server(
        policy,
        credentials,
        tmp_path,
        lambda argv, _timeout, _limit: (
            calls.append(argv) or _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)
        ),
    ).handle_request(_request(InfraOperation.RSYNC_DRY_RUN), principal_ref=f"uid:{os.getuid()}")
    assert response.receipt.reason_code == "POLICY_INVALID"
    assert calls == []


def test_source_snapshot_rejects_a_growing_file_before_writing_past_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"12345")
    destination = tmp_path / "destination.bin"
    parent_fd = os.open(tmp_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    original_open = infra_broker.os.open
    original_read = infra_broker.os.read
    source_fd: int | None = None
    grew = False

    def open_hook(path: object, *args: object, **kwargs: object) -> int:
        nonlocal source_fd
        descriptor = original_open(path, *args, **kwargs)
        if path == "source.bin" and kwargs.get("dir_fd") == parent_fd:
            source_fd = descriptor
        return descriptor

    def read_hook(fd: int, size: int) -> bytes:
        nonlocal grew
        if source_fd == fd and not grew:
            source.write_bytes(b"1234567890")
            grew = True
        return original_read(fd, size)

    monkeypatch.setattr(infra_broker.os, "open", open_hook)
    monkeypatch.setattr(infra_broker.os, "read", read_hook)
    try:
        with pytest.raises(ValueError, match="resource bound"):
            _copy_source_file(
                parent_fd,
                "source.bin",
                destination,
                source.stat(),
                time.monotonic() + 5,
                5,
            )
    finally:
        os.close(parent_fd)
    assert grew is True
    assert not destination.exists()


def test_source_snapshot_bounds_directories_as_well_as_files(tmp_path: Path) -> None:
    policy, credentials, roots, _known_hosts, _key = _profile_fixture(tmp_path)
    (roots[0] / "empty-a").mkdir()
    (roots[0] / "empty-b").mkdir()
    document = json.loads(policy.read_text(encoding="utf-8"))
    document["profiles"][0]["max_files"] = 1
    policy.write_text(json.dumps(document), encoding="utf-8")
    calls: list[list[str]] = []
    response = _server(
        policy,
        credentials,
        tmp_path,
        lambda argv, _timeout, _limit: (
            calls.append(argv) or _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)
        ),
    ).handle_request(_request(InfraOperation.RSYNC_DRY_RUN), principal_ref=f"uid:{os.getuid()}")
    assert response.receipt.reason_code == "RESOURCE_LIMIT"
    assert calls == []


def test_host_key_file_requires_one_exact_pinned_entry(tmp_path: Path) -> None:
    policy, credentials, _roots, known_hosts, key = _profile_fixture(tmp_path)
    known_hosts.write_text(
        f"prxmx01 ssh-ed25519 {b64encode(key).decode('ascii')}\n"
        f"prxmx01 ssh-ed25519 {b64encode(b'other').decode('ascii')}\n",
        encoding="utf-8",
    )
    calls: list[list[str]] = []
    response = _server(
        policy,
        credentials,
        tmp_path,
        lambda argv, _timeout, _limit: (
            calls.append(argv) or _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)
        ),
    ).handle_request(_request(InfraOperation.RSYNC_DRY_RUN), principal_ref=f"uid:{os.getuid()}")
    assert response.receipt.reason_code == "HOST_IDENTITY_MISMATCH"
    assert calls == []


def test_fixed_ssh_options_are_hermetic_and_no_agent_or_shell_fallback(tmp_path: Path) -> None:
    options = build_ssh_options(
        hostname="prxmx01",
        port=22,
        username="power-receiver",
        known_hosts_file=tmp_path / "known_hosts",
        credential_file=tmp_path / "identity",
    )
    required = {
        "-F",
        "/dev/null",
        "BatchMode=yes",
        "PasswordAuthentication=no",
        "KbdInteractiveAuthentication=no",
        "PubkeyAuthentication=yes",
        "IdentitiesOnly=yes",
        "IdentityAgent=none",
        "StrictHostKeyChecking=yes",
        "GlobalKnownHostsFile=/dev/null",
        "KnownHostsCommand=none",
        "ProxyCommand=none",
        "ProxyJump=none",
        "LocalCommand=none",
        "RemoteCommand=none",
        "GSSAPIAuthentication=no",
        "HostbasedAuthentication=no",
        "PKCS11Provider=none",
        "ControlMaster=no",
        "ControlPath=none",
    }
    assert required.issubset(set(options))
    assert not {"--delete", "--rsync-path", "--remove-source-files"}.intersection(options)


def test_process_runner_has_bounded_output_minimal_environment_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INFRA_SENTINEL", "SENTINEL_PRIVATE_KEY_VALUE")
    result = _run_bounded_process(
        [sys.executable, "-c", "import os; print(os.getenv('INFRA_SENTINEL', 'missing'))"],
        2,
        128,
    )
    assert result.category == InfraExitCategory.SUCCESS
    assert b"SENTINEL_PRIVATE_KEY_VALUE" not in result.stdout_sample
    assert b"missing" in result.stdout_sample

    oversized = _run_bounded_process(
        [sys.executable, "-c", "print('x' * 10000)"],
        2,
        512,
    )
    assert oversized.category == InfraExitCategory.OUTPUT_LIMIT
    assert oversized.output_truncated is True

    timed = _run_bounded_process(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        0.1,
        512,
    )
    assert timed.category == InfraExitCategory.TIMEOUT


def test_process_runner_classifies_all_popen_failures_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_to_start(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("synthetic launch denial")

    monkeypatch.setattr(infra_broker.subprocess, "Popen", fail_to_start)
    result = _run_bounded_process([sys.executable, "-c", "pass"], 1, 512)
    assert result.category == InfraExitCategory.PROCESS_UNAVAILABLE
    assert result.returncode is None


def test_replicate_requires_dry_run_and_uses_immutable_broker_snapshot(tmp_path: Path) -> None:
    policy, credentials, roots, _known_hosts, _key = _profile_fixture(
        tmp_path, dry_run_policy="standing"
    )
    calls: list[list[str]] = []

    def runner(argv: list[str], _timeout: float, _limit: int) -> _ProcessResult:
        calls.append(argv)
        return _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)

    server = _server(policy, credentials, tmp_path, runner)
    replicate = _request(InfraOperation.REPLICATE, idempotency_key="replicate-snapshot-one")
    replicated = server.handle_request(replicate, principal_ref=f"uid:{os.getuid()}")
    assert replicated.status == "ok"
    run_id = replicated.receipt.run_id
    assert run_id is not None
    assert len(calls) == 1
    original = (roots[0] / "note-0.txt").read_text(encoding="utf-8")
    snapshot = tmp_path / "state" / "snapshots" / run_id / "source-000" / "note-0.txt"
    assert snapshot.read_text(encoding="utf-8") == original
    (roots[0] / "note-0.txt").write_text("changed after snapshot\n", encoding="utf-8")
    assert snapshot.read_text(encoding="utf-8") == original
    assert str(roots[0]) not in " ".join(calls[-1])
    command_text = " ".join(calls[-1])
    assert "--delete" not in command_text
    assert "--rsync-path" not in command_text
    runtime_dir = tmp_path / "state" / "runtime"
    assert not any(path.name.startswith("exec-") for path in runtime_dir.iterdir())


def test_keyed_dry_run_can_authorize_a_following_replicate(tmp_path: Path) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(tmp_path)
    calls: list[list[str]] = []

    def runner(argv: list[str], _timeout: float, _limit: int) -> _ProcessResult:
        calls.append(argv)
        return _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)

    server = _server(policy, credentials, tmp_path, runner)
    dry_run = server.handle_request(
        _request(InfraOperation.RSYNC_DRY_RUN, idempotency_key="keyed-dry-run-one"),
        principal_ref=f"uid:{os.getuid()}",
    )
    assert dry_run.status == "ok"
    replicate = server.handle_request(
        _request(InfraOperation.REPLICATE, idempotency_key="keyed-replicate-one"),
        principal_ref=f"uid:{os.getuid()}",
    )
    assert replicate.status == "ok"
    assert len(calls) == 2


def test_replicate_requires_a_successful_dry_run_for_a_required_profile(tmp_path: Path) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(
        tmp_path, dry_run_policy="required"
    )
    calls: list[list[str]] = []
    server = _server(
        policy,
        credentials,
        tmp_path,
        lambda argv, _timeout, _limit: (
            calls.append(argv) or _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)
        ),
    )
    response = server.handle_request(
        _request(InfraOperation.REPLICATE, idempotency_key="required-dry-run-one"),
        principal_ref=f"uid:{os.getuid()}",
    )
    assert response.receipt.reason_code == "DRY_RUN_REQUIRED"
    assert calls == []


def test_replicate_same_run_is_reserved_across_idempotency_keys(tmp_path: Path) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(
        tmp_path, dry_run_policy="standing"
    )
    calls: list[list[str]] = []
    server = _server(
        policy,
        credentials,
        tmp_path,
        lambda argv, _timeout, _limit: (
            calls.append(argv) or _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)
        ),
    )
    first = server.handle_request(
        _request(InfraOperation.REPLICATE, idempotency_key="key-one"),
        principal_ref=f"uid:{os.getuid()}",
    )
    second = server.handle_request(
        _request(InfraOperation.REPLICATE, idempotency_key="key-two"),
        principal_ref=f"uid:{os.getuid()}",
    )
    assert first.status == "ok"
    assert second.receipt.reason_code == "RUN_ALREADY_REPLICATED"
    assert len(calls) == 1


def test_standing_approval_can_authorize_distinct_runs(tmp_path: Path) -> None:
    policy, credentials, roots, _known_hosts, _key = _profile_fixture(
        tmp_path, dry_run_policy="standing"
    )
    calls: list[list[str]] = []
    server = _server(
        policy,
        credentials,
        tmp_path,
        lambda argv, _timeout, _limit: (
            calls.append(argv) or _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)
        ),
    )
    first = server.handle_request(
        _request(InfraOperation.REPLICATE, idempotency_key="standing-run-one"),
        principal_ref=f"uid:{os.getuid()}",
    )
    assert first.status == "ok"
    roots[0].joinpath("note-0.txt").write_text("distinct standing run\n", encoding="utf-8")
    second = server.handle_request(
        _request(InfraOperation.REPLICATE, idempotency_key="standing-run-two"),
        principal_ref=f"uid:{os.getuid()}",
    )
    assert second.status == "ok"
    assert len(calls) == 2


def test_explicit_approval_is_reloaded_and_bound_to_complete_profile(tmp_path: Path) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(
        tmp_path, approval_policy="explicit", dry_run_policy="standing"
    )
    approval_path = tmp_path / "approvals.json"
    profile = load_infra_policy(policy).profiles[0]
    approval = {
        "schema_version": "power.infra-approvals.v1",
        "approvals": [
            {
                "approval_ref": "apr-test-one",
                "operation": "replicate",
                "target_id": profile.target_id,
                "profile_id": profile.profile_id,
                "policy_revision": profile.policy_revision,
                "profile_digest": canonical_profile_digest(profile),
                "principal_ref": f"uid:{os.getuid()}",
                "expires_at": "2099-01-01T00:00:00+00:00",
                "one_time": True,
            }
        ],
    }
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    calls: list[list[str]] = []
    server = _server(
        policy,
        credentials,
        tmp_path,
        lambda argv, _timeout, _limit: (
            calls.append(argv) or _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)
        ),
        approval_path=approval_path,
    )
    request = _request(
        InfraOperation.REPLICATE,
        idempotency_key="explicit-one",
        approval_ref="apr-test-one",
    )
    approval_path.unlink()
    missing = server.handle_request(request, principal_ref=f"uid:{os.getuid()}")
    assert missing.status == "auth-required"
    assert missing.receipt.reason_code == "APPROVAL_REQUIRED"
    assert calls == []

    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    success = server.handle_request(request, principal_ref=f"uid:{os.getuid()}")
    assert success.status == "ok"
    replay = server.handle_request(
        _request(
            InfraOperation.REPLICATE,
            idempotency_key="explicit-two",
            approval_ref="apr-test-one",
        ),
        principal_ref=f"uid:{os.getuid()}",
    )
    assert replay.receipt.reason_code in {"APPROVAL_REPLAY", "RUN_ALREADY_REPLICATED"}
    assert len(calls) == 1


def test_multiroot_verify_fails_if_any_root_differs(tmp_path: Path) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(tmp_path, root_count=2)
    calls: list[list[str]] = []

    def runner(argv: list[str], _timeout: float, _limit: int) -> _ProcessResult:
        calls.append(argv)
        if "--checksum" in argv:
            verify_index = sum("--checksum" in call for call in calls)
            output = b">f+++++++++ first-root-drift\n" if verify_index == 1 else b""
            return _ProcessResult(0, len(output), 0, InfraExitCategory.SUCCESS, 1, output)
        return _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)

    server = _server(policy, credentials, tmp_path, runner)
    dry_run = server.handle_request(
        _request(InfraOperation.RSYNC_DRY_RUN), principal_ref=f"uid:{os.getuid()}"
    )
    run_id = dry_run.receipt.run_id
    assert run_id is not None
    verify = server.handle_request(
        _request(InfraOperation.VERIFY, run_id=run_id), principal_ref=f"uid:{os.getuid()}"
    )
    assert verify.status == "failed"
    assert verify.receipt.verification_result == "mismatch"
    assert len(calls) == 3
    assert not any("--files-from=" in call for call in calls)


def test_verify_requires_exact_receiver_inventory_and_read_only_credential(
    tmp_path: Path,
) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(
        tmp_path, dry_run_policy="standing"
    )
    calls: list[list[str]] = []

    def runner(argv: list[str], _timeout: float, _limit: int) -> _ProcessResult:
        calls.append(argv)
        if "--list-only" in argv:
            output = b">f+++++++++\t.power-infra-run.json\n>f+++++++++\tnote-0.txt\n"
            return _ProcessResult(0, len(output), 0, InfraExitCategory.SUCCESS, 1, output)
        files_from = next(
            (
                Path(argument.split("=", 1)[1])
                for argument in argv
                if argument.startswith("--files-from=")
            ),
            None,
        )
        if files_from is not None:
            run_id = replicated.receipt.run_id
            assert run_id is not None
            snapshot_root = tmp_path / "state" / "snapshots" / run_id / "source-000"
            destination_root = Path(argv[-1])
            for relative in files_from.read_text(encoding="utf-8").splitlines():
                source = snapshot_root / relative
                destination = destination_root / relative
                if source.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(source.read_bytes())
                    destination.chmod(0o600)
        return _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)

    server = _server(policy, credentials, tmp_path, runner)
    replicated = server.handle_request(
        _request(InfraOperation.REPLICATE, idempotency_key="verify-inventory-one"),
        principal_ref=f"uid:{os.getuid()}",
    )
    assert replicated.status == "ok"
    verified = server.handle_request(
        _request(InfraOperation.VERIFY, run_id=replicated.receipt.run_id),
        principal_ref=f"uid:{os.getuid()}",
    )
    assert verified.status == "ok"
    assert verified.receipt.verification_result == "inventory-matched"
    assert verified.receipt.credential_id == "power-vault-verify-key"
    assert any("--list-only" in call for call in calls)
    content_calls = [call for call in calls if any("--files-from=" in item for item in call)]
    assert content_calls
    assert all(
        call[-2].startswith("power-receiver@prxmx01:") and call[-1].endswith("/")
        for call in content_calls
    )


def test_verify_preserves_empty_source_directories(tmp_path: Path) -> None:
    policy, credentials, roots, _known_hosts, _key = _profile_fixture(
        tmp_path, dry_run_policy="standing"
    )
    (roots[0] / "empty" / "nested").mkdir(parents=True)
    calls: list[list[str]] = []
    replicated: InfraResponse | None = None

    def runner(argv: list[str], _timeout: float, _limit: int) -> _ProcessResult:
        calls.append(argv)
        if "--list-only" in argv:
            assert replicated is not None
            snapshot_root = (
                tmp_path / "state" / "snapshots" / replicated.receipt.run_id / "source-000"
            )
            names: list[str] = []
            for current_text, dirnames, filenames in os.walk(snapshot_root):
                current = Path(current_text)
                names.extend(
                    ">f+++++++++\t" + (current / filename).relative_to(snapshot_root).as_posix()
                    for filename in sorted(filenames)
                )
                names.extend(
                    "cd+++++++++\t"
                    + (current / dirname).relative_to(snapshot_root).as_posix()
                    + "/"
                    for dirname in sorted(dirnames)
                )
            output = ("\n".join(sorted(names)) + "\n").encode()
            return _ProcessResult(0, len(output), 0, InfraExitCategory.SUCCESS, 1, output)
        files_from = next(
            (
                Path(argument.split("=", 1)[1])
                for argument in argv
                if argument.startswith("--files-from=")
            ),
            None,
        )
        if files_from is not None:
            assert replicated is not None
            snapshot_root = (
                tmp_path / "state" / "snapshots" / replicated.receipt.run_id / "source-000"
            )
            destination_root = Path(argv[-1])
            for relative in files_from.read_text(encoding="utf-8").splitlines():
                source = snapshot_root / relative
                destination = destination_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
                destination.chmod(0o600)
        return _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)

    server = _server(policy, credentials, tmp_path, runner)
    replicated = server.handle_request(
        _request(InfraOperation.REPLICATE, idempotency_key="empty-dir-replicate"),
        principal_ref=f"uid:{os.getuid()}",
    )
    verified = server.handle_request(
        _request(InfraOperation.VERIFY, run_id=replicated.receipt.run_id),
        principal_ref=f"uid:{os.getuid()}",
    )
    assert verified.status == "ok"
    assert verified.receipt.verification_result == "inventory-matched"
    assert len(calls) == 4


def test_verify_inventory_rejects_file_directory_type_swaps() -> None:
    expected = {"empty": "directory", "note.txt": "file"}
    directory_for_file = _ProcessResult(
        0,
        0,
        0,
        InfraExitCategory.SUCCESS,
        1,
        b"cd+++++++++\tnote.txt/\ncd+++++++++\tempty/\n",
    )
    file_for_directory = _ProcessResult(
        0,
        0,
        0,
        InfraExitCategory.SUCCESS,
        1,
        b">f+++++++++\tempty\n>f+++++++++\tnote.txt\n",
    )
    assert not _rsync_inventory_is_exact(directory_for_file, expected)
    assert not _rsync_inventory_is_exact(file_for_directory, expected)


def test_successful_verify_resolves_an_unknown_replicate_run(tmp_path: Path) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(
        tmp_path, dry_run_policy="standing"
    )
    calls: list[list[str]] = []
    server = _server(
        policy,
        credentials,
        tmp_path,
        lambda argv, _timeout, _limit: (
            calls.append(argv) or _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)
        ),
    )
    request = _request(InfraOperation.REPLICATE, idempotency_key="verify-resolve-one")
    profile = load_infra_policy(policy).profiles[0]
    dry_run = server.handle_request(
        _request(InfraOperation.RSYNC_DRY_RUN), principal_ref=f"uid:{os.getuid()}"
    )
    run_id = dry_run.receipt.run_id
    assert run_id is not None
    record = server._load_run_record(run_id)
    profile_digest = canonical_profile_digest(profile)
    principal_ref = f"uid:{os.getuid()}"
    verifier_ref = f"uid:{os.getuid() + 1}"
    key_ref = idempotency_key_reference(request.idempotency_key)
    assert key_ref is not None
    admission = server._prepare_admission(
        request_digest=_request_digest(request, profile_digest),
        record=record,
        profile=profile,
        profile_digest=profile_digest,
        key_ref=key_ref,
        principal_ref=principal_ref,
        approval_ref=profile.standing_approval_ref,
    )
    server._claim_idempotency(
        key_ref,
        principal_ref,
        _request_digest(request, profile_digest),
        record,
        owner_token=str(admission["owner_token"]),
    )
    verifier_collision_path = (
        tmp_path
        / "state"
        / "idempotency"
        / (hashlib.sha256(f"{verifier_ref}|{key_ref}".encode()).hexdigest() + ".json")
    )
    verifier_collision_path.write_text(
        json.dumps(
            {
                "status": "in-progress",
                "principal_ref": verifier_ref,
                "idempotency_key_ref": key_ref,
                "request_digest": "b" * 64,
                "run_id": "run_" + "c" * 64,
                "source_manifest_digest": "d" * 64,
                "profile_id": profile.profile_id,
                "target_id": profile.target_id,
                "policy_revision": profile.policy_revision,
            }
        ),
        encoding="utf-8",
    )
    verifier_collision_path.chmod(0o600)
    manifest = server._load_snapshot(record, profile)
    server._reserve_run_for_write(
        manifest,
        profile,
        profile_digest,
        key_ref,
        principal_ref=principal_ref,
        owner_token=str(admission["owner_token"]),
    )
    server._mark_admission_started(
        key_ref, principal_ref, owner_token=str(admission["owner_token"])
    )
    verify_request = _request(InfraOperation.VERIFY, run_id=run_id)
    verified_response = server._operation_response(
        verify_request,
        principal_ref=verifier_ref,
        policy_revision=profile.policy_revision,
        target_id=profile.target_id,
        profile_id=profile.profile_id,
        source_manifest_digest=manifest.digest,
        host_key_fingerprint=profile.host_key_fingerprint,
        credential_id=profile.verify_credential_id,
        run_id=run_id,
        data={"run_id": run_id, "verification": "inventory-matched", "dry_run": True},
        exit_category=InfraExitCategory.SUCCESS,
        transport="ssh-rsync",
        dry_run=True,
        verification_result="inventory-matched",
    )
    server._resolve_verified_run(
        manifest,
        profile,
        profile_digest=profile_digest,
        principal_ref=verifier_ref,
        response=verified_response,
    )
    resolved = server._load_run_record(run_id)
    assert resolved.replicated is True
    assert resolved.write_in_progress is False
    assert resolved.reservation_ref is None
    assert not list((tmp_path / "state" / "admissions").glob("*.json"))
    replay = server.handle_request(request, principal_ref=principal_ref)
    assert replay.status == "ok"
    assert replay.receipt.exit_category == InfraExitCategory.REPLAY
    assert replay.receipt.dry_run is False
    assert replay.receipt.verification_result == "passed"
    assert replay.data.dry_run is False
    assert replay.data.verification == "passed"
    assert len(calls) == 1


def test_verify_without_read_only_receiver_credential_blocks_closed(
    tmp_path: Path,
) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(tmp_path)
    document = json.loads(policy.read_text(encoding="utf-8"))
    document["profiles"][0].pop("verify_credential_id")
    document["profiles"][0]["allowed_operations"].remove("verify")
    document["profiles"][0]["allowed_operations"].append("verify")
    policy.write_text(json.dumps(document), encoding="utf-8")
    response = _server(policy, credentials, tmp_path).handle_request(
        _request(InfraOperation.VERIFY, run_id="run_" + "a" * 64),
        principal_ref=f"uid:{os.getuid()}",
    )
    assert response.receipt.reason_code == "CAPABILITY_DISABLED"


def test_unknown_completion_stays_blocked_and_is_not_retried(tmp_path: Path) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(
        tmp_path, dry_run_policy="standing"
    )
    calls: list[list[str]] = []

    def runner(argv: list[str], _timeout: float, _limit: int) -> _ProcessResult:
        calls.append(argv)
        raise RuntimeError("synthetic transport failure")

    server = _server(policy, credentials, tmp_path, runner)
    request = _request(InfraOperation.REPLICATE, idempotency_key="unknown-one")
    first = server.handle_request(request, principal_ref=f"uid:{os.getuid()}")
    second = server.handle_request(request, principal_ref=f"uid:{os.getuid()}")
    assert first.receipt.reason_code == "UNKNOWN_COMPLETION"
    assert second.receipt.reason_code == "UNKNOWN_COMPLETION"
    assert len(calls) == 1


def test_process_unavailable_is_missing_capability(tmp_path: Path) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(
        tmp_path, dry_run_policy="standing"
    )
    server = _server(
        policy,
        credentials,
        tmp_path,
        lambda *_args: _ProcessResult(None, 0, 0, InfraExitCategory.PROCESS_UNAVAILABLE, 1),
    )
    response = server.handle_request(
        _request(InfraOperation.RSYNC_DRY_RUN), principal_ref=f"uid:{os.getuid()}"
    )
    assert response.status == "blocked"
    assert response.receipt.reason_code == "MISSING_EXECUTION_CAPABILITY"


def test_pre_execution_process_absence_can_retry_after_runtime_repair(tmp_path: Path) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(
        tmp_path, dry_run_policy="standing"
    )
    calls: list[list[str]] = []
    outcomes = iter(
        [
            _ProcessResult(None, 0, 0, InfraExitCategory.PROCESS_UNAVAILABLE, 1),
            _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1),
        ]
    )

    def runner(argv: list[str], _timeout: float, _limit: int) -> _ProcessResult:
        calls.append(argv)
        return next(outcomes)

    server = _server(policy, credentials, tmp_path, runner)
    request = _request(InfraOperation.REPLICATE, idempotency_key="process-repair-one")
    first = server.handle_request(request, principal_ref=f"uid:{os.getuid()}")
    second = server.handle_request(request, principal_ref=f"uid:{os.getuid()}")
    assert first.receipt.reason_code == "MISSING_EXECUTION_CAPABILITY"
    assert second.status == "ok"
    assert len(calls) == 2


def test_multiroot_process_absence_after_a_successful_root_stays_unknown(
    tmp_path: Path,
) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(
        tmp_path, root_count=2, dry_run_policy="standing"
    )
    calls: list[list[str]] = []
    outcomes = iter(
        [
            _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1),
            _ProcessResult(None, 0, 0, InfraExitCategory.PROCESS_UNAVAILABLE, 1),
        ]
    )

    def runner(argv: list[str], _timeout: float, _limit: int) -> _ProcessResult:
        calls.append(argv)
        return next(outcomes)

    server = _server(policy, credentials, tmp_path, runner)
    request = _request(InfraOperation.REPLICATE, idempotency_key="partial-process-one")
    first = server.handle_request(request, principal_ref=f"uid:{os.getuid()}")
    second = server.handle_request(request, principal_ref=f"uid:{os.getuid()}")
    assert first.receipt.reason_code == "UNKNOWN_COMPLETION"
    assert second.receipt.reason_code == "UNKNOWN_COMPLETION"
    assert len(calls) == 2


def test_runner_timeout_exception_keeps_replicate_admission_unknown(tmp_path: Path) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(
        tmp_path, dry_run_policy="standing"
    )
    calls: list[list[str]] = []

    def runner(argv: list[str], _timeout: float, _limit: int) -> _ProcessResult:
        calls.append(argv)
        raise TimeoutError("synthetic pre-spawn timeout")

    server = _server(policy, credentials, tmp_path, runner)
    response = server.handle_request(
        _request(InfraOperation.REPLICATE, idempotency_key="pre-spawn-timeout-one"),
        principal_ref=f"uid:{os.getuid()}",
    )
    assert response.receipt.reason_code == InfraReasonCode.UNKNOWN_COMPLETION
    run_records = list((tmp_path / "state" / "runs").glob("run_*.json"))
    assert len(run_records) == 1
    record = json.loads(run_records[0].read_text(encoding="utf-8"))
    assert record["write_in_progress"] is True
    assert record["reservation_ref"] is not None
    assert list((tmp_path / "state" / "idempotency").glob("*.json"))
    assert list((tmp_path / "state" / "admissions").glob("*.json"))


def test_pre_effect_failure_releases_write_reservation_and_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(
        tmp_path, approval_policy="explicit", dry_run_policy="standing"
    )
    profile = load_infra_policy(policy).profiles[0]
    approval = {
        "schema_version": "power.infra-approvals.v1",
        "approvals": [
            {
                "approval_ref": "apr-pre-effect",
                "operation": "replicate",
                "target_id": profile.target_id,
                "profile_id": profile.profile_id,
                "policy_revision": profile.policy_revision,
                "profile_digest": canonical_profile_digest(profile),
                "principal_ref": f"uid:{os.getuid()}",
                "expires_at": "2099-01-01T00:00:00+00:00",
                "one_time": True,
            }
        ],
    }
    approval_path = tmp_path / "approvals.json"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    server = _server(
        policy,
        credentials,
        tmp_path,
        approval_path=approval_path,
    )

    def fail_before_subprocess(*_args: object, **_kwargs: object) -> _ProcessResult:
        raise ValueError("synthetic pre-effect failure")

    monkeypatch.setattr(server, "_execute_operation", fail_before_subprocess)
    response = server.handle_request(
        _request(
            InfraOperation.REPLICATE,
            idempotency_key="pre-effect-one",
            approval_ref="apr-pre-effect",
        ),
        principal_ref=f"uid:{os.getuid()}",
    )
    assert response.receipt.reason_code == "MISSING_EXECUTION_CAPABILITY"
    run_records = list((tmp_path / "state" / "runs").glob("run_*.json"))
    assert len(run_records) == 1
    run_record = json.loads(run_records[0].read_text(encoding="utf-8"))
    assert run_record["write_in_progress"] is False
    assert run_record["reservation_ref"] is None
    assert not list((tmp_path / "state" / "idempotency").glob("*.json"))
    assert not list((tmp_path / "state" / "approval-uses").glob("*"))


def test_prepared_admission_recovers_before_subprocess_start(tmp_path: Path) -> None:
    policy, credentials, roots, _known_hosts, _key = _profile_fixture(
        tmp_path, dry_run_policy="standing"
    )
    calls: list[list[str]] = []
    server = _server(
        policy,
        credentials,
        tmp_path,
        lambda argv, _timeout, _limit: (
            calls.append(argv) or _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)
        ),
    )
    dry_run = server.handle_request(
        _request(InfraOperation.RSYNC_DRY_RUN), principal_ref=f"uid:{os.getuid()}"
    )
    run_id = dry_run.receipt.run_id
    assert run_id is not None
    request = _request(InfraOperation.REPLICATE, idempotency_key="prepared-recovery-one")
    profile = load_infra_policy(policy).profiles[0]
    record = server._load_run_record(run_id)
    profile_digest = canonical_profile_digest(profile)
    principal_ref = f"uid:{os.getuid()}"
    key_ref = idempotency_key_reference(request.idempotency_key)
    assert key_ref is not None
    server._prepare_admission(
        request_digest=_request_digest(request, profile_digest),
        record=record,
        profile=profile,
        profile_digest=profile_digest,
        key_ref=key_ref,
        principal_ref=principal_ref,
        approval_ref=profile.standing_approval_ref,
    )
    server._claim_idempotency(
        key_ref,
        principal_ref,
        _request_digest(request, profile_digest),
        record,
    )
    roots[0].joinpath("note-0.txt").write_text(
        "changed after prepared admission\n", encoding="utf-8"
    )
    recovered = server.handle_request(request, principal_ref=principal_ref)
    assert recovered.status == "ok"
    assert len(calls) == 2
    assert not list((tmp_path / "state" / "admissions").glob("*.json"))


def test_stale_prepared_admission_is_rolled_back_before_capacity_check(tmp_path: Path) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(
        tmp_path, dry_run_policy="standing"
    )
    server = _server(policy, credentials, tmp_path)
    dry_run = server.handle_request(
        _request(InfraOperation.RSYNC_DRY_RUN), principal_ref=f"uid:{os.getuid()}"
    )
    run_id = dry_run.receipt.run_id
    assert run_id is not None
    request = _request(InfraOperation.REPLICATE, idempotency_key="stale-admission-one")
    profile = load_infra_policy(policy).profiles[0]
    record = server._load_run_record(run_id)
    key_ref = idempotency_key_reference(request.idempotency_key)
    assert key_ref is not None
    server._prepare_admission(
        request_digest=_request_digest(request, canonical_profile_digest(profile)),
        record=record,
        profile=profile,
        profile_digest=canonical_profile_digest(profile),
        key_ref=key_ref,
        principal_ref=f"uid:{os.getuid()}",
        approval_ref=profile.standing_approval_ref,
    )
    admission_path = next((tmp_path / "state" / "admissions").glob("*.json"))
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    admission["prepared_at"] = "2000-01-01T00:00:00+00:00"
    admission_path.write_text(json.dumps(admission), encoding="utf-8")
    server._ensure_state_capacity()
    assert not admission_path.exists()


def test_receipt_persistence_failure_never_returns_replicate_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(
        tmp_path, dry_run_policy="standing"
    )
    calls: list[list[str]] = []
    server = _server(
        policy,
        credentials,
        tmp_path,
        lambda argv, _timeout, _limit: (
            calls.append(argv) or _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)
        ),
    )
    monkeypatch.setattr(server, "_record_receipt", lambda _response: False)
    response = server.handle_request(
        _request(InfraOperation.REPLICATE, idempotency_key="receipt-state-one"),
        principal_ref=f"uid:{os.getuid()}",
    )
    assert response.status == "blocked"
    assert response.receipt.reason_code == "UNKNOWN_COMPLETION"
    assert len(calls) == 1


def test_lost_dry_run_receipt_cannot_authorize_a_required_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy, credentials, _roots, _known_hosts, _key = _profile_fixture(tmp_path)
    calls: list[list[str]] = []
    server = _server(
        policy,
        credentials,
        tmp_path,
        lambda argv, _timeout, _limit: (
            calls.append(argv) or _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)
        ),
    )
    original_record_receipt = server._record_receipt
    receipt_attempts = 0

    def fail_dry_run_receipt(_response: InfraResponse) -> bool:
        nonlocal receipt_attempts
        receipt_attempts += 1
        return False if receipt_attempts <= 2 else original_record_receipt(_response)

    monkeypatch.setattr(server, "_record_receipt", fail_dry_run_receipt)
    dry_run = server.handle_request(
        _request(InfraOperation.RSYNC_DRY_RUN), principal_ref=f"uid:{os.getuid()}"
    )
    assert dry_run.status == "blocked"
    replicate = server.handle_request(
        _request(InfraOperation.REPLICATE, idempotency_key="lost-dry-run-receipt"),
        principal_ref=f"uid:{os.getuid()}",
    )
    assert replicate.receipt.reason_code == "DRY_RUN_REQUIRED"
    assert len(calls) == 1


def test_application_preserves_task_semantics_and_never_auto_completes(
    sample_vault: Path, tmp_path: Path
) -> None:
    from power_framework.core.infra_broker import InfraBrokerClient

    service = ApplicationService(
        sample_vault,
        infra_broker=InfraBrokerClient(socket_path=tmp_path / "missing.sock"),
    )
    service.task_create(
        "infra-task",
        "Bounded replication",
        state="working",
        authority="apply",
        context=RequestContext(actor="test", authority="apply"),
    )
    request = _request(
        InfraOperation.PROBE,
        task_id="infra-task",
        expected_revision=1,
        idempotency_key="probe-task-one",
    )
    envelope = service.infra_action(
        request,
        context=RequestContext(actor="test", authority="apply", idempotency_key="probe-task-one"),
    )
    assert envelope.data["state"] == "blocked"
    assert envelope.data["execution_outcome"] == "MISSING_EXECUTION_CAPABILITY"
    assert envelope.data["required_input"] is None
    task = service.task_service.get_task("infra-task")
    assert task is not None
    assert task.state == "blocked"
    assert task.execution_state == "none"
    assert task.receipt_ids
    assert all(not receipt.startswith("tcr_") for receipt in task.receipt_ids)


def test_backlog_task_cannot_start_infra_action_before_task_admission(
    sample_vault: Path, tmp_path: Path
) -> None:
    from power_framework.core.infra_broker import InfraBrokerClient

    service = ApplicationService(
        sample_vault,
        infra_broker=InfraBrokerClient(socket_path=tmp_path / "missing.sock"),
    )
    service.task_create(
        "backlog-infra-task",
        "Not ready for infrastructure",
        authority="apply",
        context=RequestContext(actor="test", authority="apply"),
    )
    with pytest.raises(ConflictError, match="ready task"):
        service.infra_action(
            _request(
                InfraOperation.PROBE,
                task_id="backlog-infra-task",
                expected_revision=1,
                idempotency_key="backlog-infra-one",
            ),
            context=RequestContext(actor="test", authority="apply"),
        )
    task = service.task_service.get_task("backlog-infra-task")
    assert task is not None
    assert task.revision == 1
    assert task.execution_state == "none"


def test_task_bound_retry_reuses_claim_without_revision_conflict(
    sample_vault: Path, tmp_path: Path
) -> None:
    from power_framework.core.infra_broker import InfraBrokerClient

    service = ApplicationService(
        sample_vault,
        infra_broker=InfraBrokerClient(socket_path=tmp_path / "missing.sock"),
    )
    service.task_create(
        "retry-task",
        "Retryable broker action",
        state="working",
        authority="apply",
        context=RequestContext(actor="test", authority="apply"),
    )
    request = _request(
        InfraOperation.PROBE,
        task_id="retry-task",
        expected_revision=1,
        idempotency_key="retry-task-one",
    )
    context = RequestContext(actor="test", authority="apply", idempotency_key="retry-task-one")
    first = service.infra_action(request, context=context)
    second = service.infra_action(request, context=context)

    assert first.data["state"] == "blocked"
    assert second.data["state"] == "blocked"
    task = service.task_service.get_task("retry-task")
    assert task is not None
    assert task.state == "blocked"


def test_task_bound_success_records_external_receipt_without_auto_completion(
    sample_vault: Path,
) -> None:
    class StubBroker:
        def execute(self, request: InfraRequest) -> InfraResponse:
            receipt = InfraOperationReceipt(
                receipt_id="ir_" + "c" * 64,
                trace_id="tr_" + "d" * 32,
                task_id=request.task_id,
                operation=request.operation,
                target_id=request.target,
                profile_id=request.profile,
                policy_revision="stub-policy-v1",
                principal_ref=f"uid:{os.getuid()}",
                transport="ssh-rsync",
                dry_run=True,
                exit_category="success",
                verification_result="status",
                recorded_at="2026-09-13T00:00:00+00:00",
            )
            return InfraResponse(
                status="ok",
                operation=request.operation,
                target=request.target,
                profile=request.profile,
                task_id=request.task_id,
                request_digest=_request_digest(request),
                data=InfraResponseData(
                    broker_status="active",
                    dry_run=True,
                    reachable=True,
                    verification="status",
                ),
                receipt=receipt,
            )

    service = ApplicationService(sample_vault, infra_broker=StubBroker())
    service.task_create(
        "success-task",
        "Successful probe",
        state="working",
        authority="apply",
        context=RequestContext(actor="test", authority="apply"),
    )
    envelope = service.infra_action(
        _request(
            InfraOperation.PROBE,
            task_id="success-task",
            expected_revision=1,
            idempotency_key="success-task-one",
        ),
        context=RequestContext(actor="test", authority="apply"),
    )
    task = service.task_service.get_task("success-task")
    assert envelope.data["state"] == "working"
    assert task is not None
    assert task.state == "working"
    assert task.execution_state == "none"
    assert "ir_" + "c" * 64 in task.receipt_ids
    assert task.external_refs["infra_receipt_id"] == "ir_" + "c" * 64


def test_expired_task_bound_context_cannot_create_a_claim(
    sample_vault: Path, tmp_path: Path
) -> None:
    from power_framework.core.infra_broker import InfraBrokerClient

    service = ApplicationService(
        sample_vault,
        infra_broker=InfraBrokerClient(socket_path=tmp_path / "missing.sock"),
    )
    service.task_create(
        "expired-task",
        "Expired action",
        state="working",
        authority="apply",
        context=RequestContext(actor="test", authority="apply"),
    )
    request = _request(
        InfraOperation.PROBE,
        task_id="expired-task",
        expected_revision=1,
        idempotency_key="expired-task-one",
    )
    with pytest.raises(TimeoutError):
        service.infra_action(
            request,
            context=RequestContext(
                actor="test",
                authority="apply",
                deadline_ms=1,
                deadline_at=0,
            ),
        )
    task = service.task_service.get_task("expired-task")
    assert task is not None
    assert task.revision == 1
    assert task.execution_state == "none"


def test_task_bound_result_budget_is_rejected_before_claim(
    sample_vault: Path, tmp_path: Path
) -> None:
    from power_framework.core.infra_broker import InfraBrokerClient

    service = ApplicationService(
        sample_vault,
        infra_broker=InfraBrokerClient(socket_path=tmp_path / "missing.sock"),
    )
    service.task_create(
        "budget-task",
        "Budget-limited action",
        state="working",
        authority="apply",
        context=RequestContext(actor="test", authority="apply"),
    )
    request = _request(
        InfraOperation.PROBE,
        task_id="budget-task",
        expected_revision=1,
        idempotency_key="budget-task-one",
    )
    with pytest.raises(ResultBudgetExceededError):
        service.infra_action(
            request,
            context=RequestContext(actor="test", authority="apply", max_result_bytes=4095),
        )
    task = service.task_service.get_task("budget-task")
    assert task is not None
    assert task.revision == 1
    assert task.execution_state == "none"


def test_task_deadline_expiring_during_claim_clears_the_lease(
    sample_vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from power_framework.core.infra_broker import InfraBrokerClient

    service = ApplicationService(
        sample_vault,
        infra_broker=InfraBrokerClient(socket_path=tmp_path / "missing.sock"),
    )
    service.task_create(
        "claim-deadline-task",
        "Deadline during claim",
        state="working",
        authority="apply",
        context=RequestContext(actor="test", authority="apply"),
    )
    checks = iter([False, False, True])
    monkeypatch.setattr(service, "_deadline_expired", lambda _context: next(checks))
    request = _request(
        InfraOperation.PROBE,
        task_id="claim-deadline-task",
        expected_revision=1,
        idempotency_key="claim-deadline-one",
    )
    with pytest.raises(DeadlineExceededError):
        service.infra_action(
            request,
            context=RequestContext(actor="test", authority="apply"),
        )
    task = service.task_service.get_task("claim-deadline-task")
    assert task is not None
    assert task.state == "working"
    assert task.execution_state == "none"
    assert task.external_refs["infra_claim_aborted"] == "deadline-before-broker"
    monkeypatch.setattr(service, "_deadline_expired", lambda _context: False)
    retry = service.infra_action(
        request,
        context=RequestContext(actor="test", authority="apply"),
    )
    assert retry.data["state"] == "blocked"
    task = service.task_service.get_task("claim-deadline-task")
    assert task is not None
    assert task.state == "blocked"


def test_infra_application_audit_does_not_receive_raw_idempotency_key(
    sample_vault: Path, tmp_path: Path
) -> None:
    from power_framework.core.infra_broker import InfraBrokerClient

    observed = []
    service = ApplicationService(
        sample_vault,
        audit_hook=observed.append,
        infra_broker=InfraBrokerClient(socket_path=tmp_path / "missing.sock"),
    )
    service.infra_action(
        _request(InfraOperation.PROBE),
        context=RequestContext(actor="test", idempotency_key="audit-secret-like-key"),
    )
    assert observed
    assert all(receipt.idempotency_key is None for receipt in observed)


def test_application_unknown_completion_does_not_fake_blocked_state(sample_vault: Path) -> None:
    class StubBroker:
        def execute(self, request: InfraRequest) -> InfraResponse:
            return _block_response(
                request,
                InfraReasonCode.UNKNOWN_COMPLETION,
                run_id="run_" + "a" * 64,
                source_manifest_digest="b" * 64,
            )

    service = ApplicationService(sample_vault, infra_broker=StubBroker())
    service.task_create(
        "unknown-task",
        "Unknown result",
        state="working",
        authority="apply",
        context=RequestContext(actor="test", authority="apply"),
    )
    envelope = service.infra_action(
        _request(
            InfraOperation.REPLICATE,
            task_id="unknown-task",
            expected_revision=1,
            idempotency_key="unknown-task-one",
        ),
        context=RequestContext(actor="test", authority="apply", idempotency_key="unknown-task-one"),
    )
    assert envelope.data["state"] == "working"
    assert envelope.data["execution_outcome"] == "UNKNOWN_COMPLETION"
    task = service.task_service.get_task("unknown-task")
    assert task is not None
    assert task.state == "working"
    assert task.execution_state == "leased"
    assert task.external_refs["infra_run_id"] == "run_" + "a" * 64
    assert task.external_refs["infra_manifest_digest"] == "b" * 64
    assert task.external_refs["infra_profile_id"] == "power-vault"
    assert task.external_refs["infra_target_id"] == "prxmx01"


def test_broker_entrypoint_and_systemd_boundary_are_non_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    systemd = _REPO_ROOT / "deploy" / "systemd"
    monkeypatch.chdir(tmp_path)
    unit = (systemd / "power-infra-broker.service").read_text(encoding="utf-8")
    socket_unit = (systemd / "power-infra-broker.socket").read_text(encoding="utf-8")
    assert "ExecStart=/usr/bin/python3 -E -m power_framework.core.infra_broker serve" in unit
    assert "--caller-allowlist /etc/power/infra/callers.json" in unit
    assert "ExecStartPre=/usr/bin/python3 -E -c" in unit
    assert "raise SystemExit" in unit
    assert " assert " not in unit
    assert f"m.version('power-framework') == '{__version__}'" in unit
    assert "--socket-activation" in unit
    assert "User=power-infra" in unit
    assert "ProtectHome=yes" in unit
    assert "KillMode=control-group" in unit
    assert "LimitCORE=0" in unit
    assert "RuntimeDirectory=power-infra-broker" in unit
    assert "LoadCredential=" in unit
    assert "EnvironmentFile=" not in unit
    assert "Accept=no" in socket_unit
    assert "SocketGroup=power-infra-callers" in socket_unit
    tmpfiles = (systemd / "power-infra-broker.tmpfiles").read_text(encoding="utf-8")
    assert "power-infra-callers" in tmpfiles
    allowlist = (systemd / "power-infra-broker-allowlist.conf.example").read_text(encoding="utf-8")
    assert "caller authorization is no longer sourced" in allowlist


def test_rsync_verification_detects_exact_itemize_marker_and_clean_output() -> None:
    # 1. Exact 11-char itemize marker (>f+++++++++) without filename must NOT be clean
    changed_result = _ProcessResult(
        returncode=0,
        stdout_bytes=len(b">f+++++++++\n"),
        stderr_bytes=0,
        category=InfraExitCategory.SUCCESS,
        duration_ms=10,
        stdout_sample=b">f+++++++++\n",
        stderr_sample=b"",
        output_truncated=False,
    )
    assert _rsync_verification_is_clean(changed_result) is False

    # 2. Attribute-only change marker (>f.st......) must NOT be clean
    attr_changed_result = _ProcessResult(
        returncode=0,
        stdout_bytes=len(b">f.st......\n"),
        stderr_bytes=0,
        category=InfraExitCategory.SUCCESS,
        duration_ms=10,
        stdout_sample=b">f.st......\n",
        stderr_sample=b"",
        output_truncated=False,
    )
    assert _rsync_verification_is_clean(attr_changed_result) is False

    # 3. Clean output with headers and stats must be clean
    clean_sample = (
        b"sending incremental file list\n"
        b"sent 100 bytes  received 20 bytes  240.00 bytes/sec\n"
        b"total size is 0  speedup is 0.00\n"
    )
    clean_result = _ProcessResult(
        returncode=0,
        stdout_bytes=len(clean_sample),
        stderr_bytes=0,
        category=InfraExitCategory.SUCCESS,
        duration_ms=10,
        stdout_sample=clean_sample,
        stderr_sample=b"",
        output_truncated=False,
    )
    assert _rsync_verification_is_clean(clean_result) is True

    # 4. Truncated output or failure category must never be clean
    truncated_result = _ProcessResult(
        returncode=0,
        stdout_bytes=len(clean_sample),
        stderr_bytes=0,
        category=InfraExitCategory.SUCCESS,
        duration_ms=10,
        stdout_sample=clean_sample,
        stderr_sample=b"",
        output_truncated=True,
    )
    assert _rsync_verification_is_clean(truncated_result) is False

    failed_result = _ProcessResult(
        returncode=1,
        stdout_bytes=len(clean_sample),
        stderr_bytes=len(b"error"),
        category=InfraExitCategory.FAILED,
        duration_ms=10,
        stdout_sample=clean_sample,
        stderr_sample=b"error",
        output_truncated=False,
    )
    assert _rsync_verification_is_clean(failed_result) is False
