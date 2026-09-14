"""Hermetic INFRA-1 broker contract and security tests."""

from __future__ import annotations

import json
import os
import socket
import struct
import threading
from base64 import b64encode
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from power_framework.core.application import ApplicationService, RequestContext
from power_framework.core.infra_broker import (
    InfraBrokerClient,
    InfraBrokerServer,
    _ProcessResult,
    _receive_frame,
    _request_digest,
    build_ssh_options,
    load_infra_policy,
)
from power_framework.core.infra_models import (
    InfraCapabilityBlockReceipt,
    InfraExitCategory,
    InfraOperation,
    InfraRequest,
    canonical_profile_digest,
    ssh_fingerprint_from_blob,
)

if TYPE_CHECKING:
    from pathlib import Path


def _send_frame(connection: socket.socket, payload: dict[str, object]) -> None:
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    connection.sendall(struct.pack(">I", len(encoded)) + encoded)


def _response_payload(request: InfraRequest) -> dict[str, object]:
    return {
        "schema_version": "power.infra-response.v1",
        "status": "ok",
        "operation": request.operation.value,
        "target": request.target,
        "profile": request.profile,
        "request_digest": _request_digest(request),
        "data": {
            "broker_status": "active",
            "transport": "unix",
            "principal_source": "SO_PEERCRED",
            "profiles": [],
            "ready": True,
            "verification": "status",
        },
        "receipt": {
            "schema_version": "power.infra-receipt.v1",
            "receipt_id": "ir_" + "1" * 64,
            "trace_id": "tr_" + "2" * 32,
            "operation": request.operation.value,
            "target_id": None,
            "profile_id": None,
            "policy_revision": "none",
            "principal_ref": "uid:1000",
            "approval_ref": None,
            "source_manifest_digest": None,
            "host_key_fingerprint": None,
            "credential_id": None,
            "transport": "unix",
            "run_id": None,
            "dry_run": True,
            "file_count": 0,
            "byte_count": 0,
            "duration_ms": 0,
            "exit_category": "success",
            "verification_result": "status",
            "idempotency_key_ref": None,
            "recorded_at": "2026-09-12T00:00:00+00:00",
        },
    }


def test_request_rejects_arbitrary_infrastructure_fields() -> None:
    with pytest.raises(ValidationError):
        InfraRequest.model_validate(
            {
                "operation": "probe",
                "target": "prxmx01",
                "profile": "power-vault",
                "host": "attacker.example",
                "ssh_options": ["-o", "StrictHostKeyChecking=no"],
            }
        )


def test_replicate_requires_idempotency_key() -> None:
    with pytest.raises(ValidationError, match="idempotency_key"):
        InfraRequest(operation=InfraOperation.REPLICATE, target="prxmx01", profile="power-vault")


def test_replicate_dry_run_flag_cannot_turn_into_a_write() -> None:
    with pytest.raises(ValidationError, match="rsync-dry-run"):
        InfraRequest(
            operation=InfraOperation.REPLICATE,
            target="prxmx01",
            profile="power-vault",
            idempotency_key="replicate-dry-run",
            dry_run=True,
        )


def test_block_receipt_has_no_secret_or_command_fields() -> None:
    receipt = InfraCapabilityBlockReceipt(
        receipt_id="ibr_" + "a" * 64,
        trace_id="tr_" + "b" * 32,
        operation=InfraOperation.REPLICATE,
        profile_id="power-vault",
        reason_code="MISSING_EXECUTION_CAPABILITY",
        required_capability="infra.broker.v1",
        policy_revision="policy-1",
        broker_status="broker-not-installed",
        remediation_code="INSTALL_ENABLE_BROKER",
        recorded_at="2026-09-12T00:00:00+00:00",
    )
    serialized = json.dumps(receipt.model_dump())
    assert "password" not in serialized.casefold()
    assert "private_key" not in serialized.casefold()
    assert "command" not in serialized.casefold()
    assert "stderr" not in serialized.casefold()


def test_client_without_socket_returns_blocked_receipt(tmp_path: Path) -> None:
    client = InfraBrokerClient(socket_path=tmp_path / "missing.sock")

    response = client.execute(InfraRequest(operation=InfraOperation.STATUS))

    assert response.status == "blocked"
    assert isinstance(response.receipt, InfraCapabilityBlockReceipt)
    assert response.receipt.reason_code == "MISSING_EXECUTION_CAPABILITY"
    assert response.receipt.required_capability == "infra.broker.v1"


def test_client_uses_bounded_unix_socket_protocol(tmp_path: Path) -> None:
    socket_path = tmp_path / "broker.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen(1)
    received: list[dict[str, object]] = []

    def serve_once() -> None:
        connection, _ = listener.accept()
        with connection:
            frame = _receive_frame(connection)
            received.append(frame)
            _send_frame(
                connection,
                {
                    "schema_version": "power.infra-wire-response.v1",
                    "nonce": frame["nonce"],
                    "response": _response_payload(InfraRequest.model_validate(frame["request"])),
                },
            )

    worker = threading.Thread(target=serve_once)
    worker.start()
    try:
        response = InfraBrokerClient(
            socket_path=socket_path, expected_broker_uid=os.getuid()
        ).execute(InfraRequest(operation=InfraOperation.STATUS))
    finally:
        worker.join(timeout=2)
        listener.close()

    assert response.status == "ok"
    assert received[0]["schema_version"] == "power.infra-wire.v1"
    assert isinstance(received[0]["nonce"], str)
    assert received[0]["request"] == {
        "operation": "status",
        "target": None,
        "profile": None,
        "dry_run": False,
        "idempotency_key": None,
        "run_id": None,
        "approval_ref": None,
        "task_id": None,
        "expected_revision": None,
    }


def test_policy_loader_rejects_unknown_fields_and_symlinks(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps({"schema_version": "power.infra-policy.v1", "profiles": [], "extra": True}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"unknown|extra|schema"):
        load_infra_policy(policy)

    symlink = tmp_path / "policy-link.json"
    symlink.symlink_to(policy)
    with pytest.raises(ValueError, match="symlink"):
        load_infra_policy(symlink)


def test_policy_loader_rejects_group_or_world_writable_file(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"schema_version": "power.infra-policy.v1", "profiles": []}))
    policy.chmod(0o664)
    with pytest.raises(ValueError, match="writable"):
        load_infra_policy(policy)


def test_ssh_options_pin_noninteractive_transport(tmp_path: Path) -> None:
    options = build_ssh_options(
        hostname="prxmx01",
        port=22,
        username="power-receiver",
        known_hosts_file=tmp_path / "known_hosts",
        credential_file=tmp_path / "credential",
    )
    assert "BatchMode=yes" in options
    assert "PasswordAuthentication=no" in options
    assert "KbdInteractiveAuthentication=no" in options
    assert "IdentitiesOnly=yes" in options
    assert "IdentityAgent=none" in options
    assert "StrictHostKeyChecking=yes" in options
    assert f"UserKnownHostsFile={tmp_path / 'known_hosts'}" in options
    assert "RemoteCommand=none" in options
    assert "--delete" not in options


def test_server_principal_is_derived_from_peer_not_payload(tmp_path: Path) -> None:
    server = InfraBrokerServer(
        policy_path=tmp_path / "policy.json",
        socket_path=tmp_path / "broker.sock",
        state_dir=tmp_path / "state",
        authorized_uids={os.getuid()},
    )
    left, right = socket.socketpair()
    try:
        principal = server.peer_principal(left)
    finally:
        left.close()
        right.close()

    assert principal.startswith("uid:")
    assert "actor" not in principal


def _write_test_profile(tmp_path: Path) -> tuple[Path, Path, Path, list[list[str]]]:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "snapshot.txt").write_text("bounded test data", encoding="utf-8")
    known_hosts = tmp_path / "known_hosts"
    key_blob = b"synthetic-host-key-blob"
    known_hosts.write_text(
        f"prxmx01 ssh-ed25519 {b64encode(key_blob).decode('ascii')}\n", encoding="utf-8"
    )
    credential_dir = tmp_path / "credentials"
    credential_dir.mkdir()
    credential = credential_dir / "power-vault"
    credential.write_text("synthetic credential boundary", encoding="utf-8")
    credential.chmod(0o600)
    verify_credential = credential_dir / "power-vault-verify"
    verify_credential.write_text("synthetic verify credential boundary", encoding="utf-8")
    verify_credential.chmod(0o600)
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "schema_version": "power.infra-policy.v1",
                "profiles": [
                    {
                        "profile_id": "power-vault",
                        "target_id": "prxmx01",
                        "hostname": "prxmx01",
                        "port": 22,
                        "remote_user": "power-receiver",
                        "remote_root": "/srv/power-vault/staging",
                        "allowed_operations": [
                            "status",
                            "probe",
                            "rsync-dry-run",
                            "replicate",
                            "verify",
                        ],
                        "source_roots": [str(source_root)],
                        "known_hosts_file": str(known_hosts),
                        "host_key_fingerprint": ssh_fingerprint_from_blob(key_blob),
                        "credential_id": "power-vault",
                        "verify_credential_id": "power-vault-verify",
                        "allow_plaintext_credential_fallback": True,
                        "approval_policy": "standing",
                        "standing_approval_ref": "standing-power-vault",
                        "standing_principal_ref": f"uid:{os.getuid()}",
                        "policy_revision": "test-policy-v1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    calls: list[list[str]] = []
    return policy, credential_dir, source_root, calls


def test_replicate_replays_and_conflicts_without_a_second_transfer(tmp_path: Path) -> None:
    policy, credential_dir, _source_root, calls = _write_test_profile(tmp_path)

    def runner(argv: list[str], _timeout: int, _output_limit: int) -> _ProcessResult:
        calls.append(argv)
        return _ProcessResult(0, 32, 0, InfraExitCategory.SUCCESS, 1)

    server = InfraBrokerServer(
        policy_path=policy,
        state_dir=tmp_path / "state",
        credential_dir=credential_dir,
        authorized_uids={os.getuid()},
        command_runner=runner,
    )
    dry_run = server.handle_request(
        InfraRequest(
            operation=InfraOperation.RSYNC_DRY_RUN,
            target="prxmx01",
            profile="power-vault",
        ),
        principal_ref=f"uid:{os.getuid()}",
    )
    assert dry_run.status == "ok"
    request = InfraRequest(
        operation=InfraOperation.REPLICATE,
        target="prxmx01",
        profile="power-vault",
        idempotency_key="replicate-1",
    )
    first = server.handle_request(request, principal_ref=f"uid:{os.getuid()}")
    repeat_dry_run = server.handle_request(
        InfraRequest(
            operation=InfraOperation.RSYNC_DRY_RUN,
            target="prxmx01",
            profile="power-vault",
        ),
        principal_ref=f"uid:{os.getuid()}",
    )
    profile = load_infra_policy(policy).profiles[0]
    run_id = first.receipt.run_id
    assert run_id is not None
    manifest = server._load_snapshot(server._load_run_record(run_id), profile)
    server._write_or_validate_run_record(
        manifest,
        profile,
        canonical_profile_digest(profile),
        dry_run_passed=True,
        write_in_progress=False,
        reservation_ref=None,
        replicated=True,
        receipt_id="ir_" + "e" * 64,
    )
    replay = server.handle_request(request, principal_ref=f"uid:{os.getuid()}")
    conflict = server.handle_request(
        request.model_copy(update={"dry_run": True}), principal_ref=f"uid:{os.getuid()}"
    )

    assert first.status == "ok"
    assert repeat_dry_run.status == "ok"
    assert server._load_run_record(run_id).receipt_id == first.receipt.receipt_id
    assert replay.data["replay"] is True
    assert conflict.receipt.reason_code == "IDEMPOTENCY_CONFLICT"
    assert len(calls) == 3
    argv_text = " ".join(" ".join(call) for call in calls)
    assert "--delete" not in argv_text
    assert "--rsync-path" not in argv_text
    assert "--remove" not in argv_text
    assert "RemoteCommand=none" in argv_text


def test_idempotency_replay_survives_broker_restart(tmp_path: Path) -> None:
    policy, credential_dir, _source_root, calls = _write_test_profile(tmp_path)
    state_dir = tmp_path / "state"

    def runner(argv: list[str], _timeout: int, _output_limit: int) -> _ProcessResult:
        calls.append(argv)
        return _ProcessResult(0, 8, 0, InfraExitCategory.SUCCESS, 1)

    first_server = InfraBrokerServer(
        policy_path=policy,
        state_dir=state_dir,
        credential_dir=credential_dir,
        authorized_uids={os.getuid()},
        command_runner=runner,
    )
    first_server.handle_request(
        InfraRequest(
            operation=InfraOperation.RSYNC_DRY_RUN,
            target="prxmx01",
            profile="power-vault",
        ),
        principal_ref=f"uid:{os.getuid()}",
    )
    request = InfraRequest(
        operation=InfraOperation.REPLICATE,
        target="prxmx01",
        profile="power-vault",
        idempotency_key="restart-replay-1",
    )
    first = first_server.handle_request(request, principal_ref=f"uid:{os.getuid()}")

    def fail_if_called(_argv: list[str], _timeout: int, _output_limit: int) -> _ProcessResult:
        raise AssertionError("restart replay must not execute a second transfer")

    second_server = InfraBrokerServer(
        policy_path=policy,
        state_dir=state_dir,
        credential_dir=credential_dir,
        authorized_uids={os.getuid()},
        command_runner=fail_if_called,
    )
    replay = second_server.handle_request(request, principal_ref=f"uid:{os.getuid()}")

    assert first.status == "ok"
    assert replay.status == "ok"
    assert replay.data["replay"] is True
    assert len(calls) == 2


def test_inflight_reservation_blocks_retry_after_execution_crash(tmp_path: Path) -> None:
    policy, credential_dir, _source_root, calls = _write_test_profile(tmp_path)
    state_dir = tmp_path / "state"

    def crash_on_write(argv: list[str], _timeout: int, _output_limit: int) -> _ProcessResult:
        calls.append(argv)
        if "--dry-run" not in argv:
            raise RuntimeError("simulated broker crash after reservation")
        return _ProcessResult(0, 8, 0, InfraExitCategory.SUCCESS, 1)

    first_server = InfraBrokerServer(
        policy_path=policy,
        state_dir=state_dir,
        credential_dir=credential_dir,
        authorized_uids={os.getuid()},
        command_runner=crash_on_write,
    )
    first_server.handle_request(
        InfraRequest(
            operation=InfraOperation.RSYNC_DRY_RUN,
            target="prxmx01",
            profile="power-vault",
        ),
        principal_ref=f"uid:{os.getuid()}",
    )
    request = InfraRequest(
        operation=InfraOperation.REPLICATE,
        target="prxmx01",
        profile="power-vault",
        idempotency_key="crash-reservation-1",
    )
    first = first_server.handle_request(request, principal_ref=f"uid:{os.getuid()}")
    assert first.receipt.reason_code == "UNKNOWN_COMPLETION"

    def fail_if_retried(*_args: object) -> _ProcessResult:
        raise AssertionError("an unresolved reservation must not retry")

    second_server = InfraBrokerServer(
        policy_path=policy,
        state_dir=state_dir,
        credential_dir=credential_dir,
        authorized_uids={os.getuid()},
        command_runner=fail_if_retried,
    )
    response = second_server.handle_request(request, principal_ref=f"uid:{os.getuid()}")

    assert response.status == "blocked"
    assert response.receipt.reason_code == "UNKNOWN_COMPLETION"
    assert response.receipt.run_id is not None


def test_source_symlink_is_blocked_before_runner(tmp_path: Path) -> None:
    policy, credential_dir, source_root, calls = _write_test_profile(tmp_path)
    (source_root / "escape").symlink_to(tmp_path / "outside")

    def runner(_argv: list[str], _timeout: int, _output_limit: int) -> _ProcessResult:
        calls.append([])
        return _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)

    server = InfraBrokerServer(
        policy_path=policy,
        credential_dir=credential_dir,
        authorized_uids={os.getuid()},
        command_runner=runner,
    )

    response = server.handle_request(
        InfraRequest(
            operation=InfraOperation.RSYNC_DRY_RUN,
            target="prxmx01",
            profile="power-vault",
        ),
        principal_ref=f"uid:{os.getuid()}",
    )

    assert response.status == "blocked"
    assert response.receipt.reason_code == "RESOURCE_LIMIT"
    assert calls == []


def test_verify_rejects_itemized_diff_even_when_rsync_exits_zero(tmp_path: Path) -> None:
    policy, credential_dir, _source_root, _calls = _write_test_profile(tmp_path)

    def runner(_argv: list[str], _timeout: int, _output_limit: int) -> _ProcessResult:
        return _ProcessResult(
            0,
            64,
            0,
            InfraExitCategory.SUCCESS,
            1,
            stdout_sample=b">f.st...... changed-after-replication\n",
        )

    server = InfraBrokerServer(
        policy_path=policy,
        state_dir=tmp_path / "state",
        credential_dir=credential_dir,
        authorized_uids={os.getuid()},
        command_runner=runner,
    )
    dry_run = server.handle_request(
        InfraRequest(
            operation=InfraOperation.RSYNC_DRY_RUN,
            target="prxmx01",
            profile="power-vault",
        ),
        principal_ref=f"uid:{os.getuid()}",
    )
    run_id = dry_run.receipt.run_id
    assert run_id is not None
    response = server.handle_request(
        InfraRequest(
            operation=InfraOperation.VERIFY,
            target="prxmx01",
            profile="power-vault",
            run_id=run_id,
        ),
        principal_ref=f"uid:{os.getuid()}",
    )

    assert response.status == "failed"
    assert response.receipt.verification_result == "mismatch"


def test_host_key_pin_must_be_bound_to_configured_hostname(tmp_path: Path) -> None:
    policy, credential_dir, _source_root, calls = _write_test_profile(tmp_path)
    target_key = b"target-key"
    unrelated_key = b"unrelated-key"
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(
        "\n".join(
            [
                f"prxmx01 ssh-ed25519 {b64encode(target_key).decode('ascii')}",
                f"other-host ssh-ed25519 {b64encode(unrelated_key).decode('ascii')}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    document = json.loads(policy.read_text(encoding="utf-8"))
    document["profiles"][0]["known_hosts_file"] = str(known_hosts)
    document["profiles"][0]["host_key_fingerprint"] = ssh_fingerprint_from_blob(unrelated_key)
    policy.write_text(json.dumps(document), encoding="utf-8")
    server = InfraBrokerServer(
        policy_path=policy,
        state_dir=tmp_path / "state",
        credential_dir=credential_dir,
        authorized_uids={os.getuid()},
        command_runner=lambda *_args: (
            calls.append([]) or _ProcessResult(0, 0, 0, InfraExitCategory.SUCCESS, 1)
        ),
    )

    response = server.handle_request(
        InfraRequest(
            operation=InfraOperation.RSYNC_DRY_RUN,
            target="prxmx01",
            profile="power-vault",
        ),
        principal_ref=f"uid:{os.getuid()}",
    )

    assert response.receipt.reason_code == "HOST_IDENTITY_MISMATCH"
    assert calls == []


def test_missing_broker_projects_block_receipt_without_required_input(
    sample_vault: Path, tmp_path: Path
) -> None:
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

    response = service.infra_action(
        InfraRequest(
            operation=InfraOperation.PROBE,
            target="prxmx01",
            profile="power-vault",
            task_id="infra-task",
            expected_revision=1,
            idempotency_key="infra-probe-1",
        ),
        context=RequestContext(actor="test", authority="apply", idempotency_key="infra-probe-1"),
    )
    task = service.task_service.get_task("infra-task")

    assert response.data["state"] == "blocked"
    assert task is not None
    assert task.state == "blocked"
    assert task.required_input is None
    infra = response.data["infra"]
    assert isinstance(infra, dict)
    receipt_id = str(infra["receipt"]["receipt_id"])
    assert receipt_id in task.receipt_ids
    assert str(infra["receipt"]["required_capability"]) in task.open_gates


def test_missing_target_is_input_required_before_socket_connect(tmp_path: Path) -> None:
    response = InfraBrokerClient(socket_path=tmp_path / "missing.sock").execute(
        InfraRequest(operation=InfraOperation.PROBE, profile="power-vault")
    )

    assert response.status == "blocked"
    assert response.receipt.reason_code == "REQUEST_INPUT_MISSING"
    assert response.receipt.remediation_code == "PROVIDE_TARGET_AND_PROFILE"
