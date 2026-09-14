"""Static tests for opt-in INFRA-1 packaging and receiver references."""

from __future__ import annotations

import json
from pathlib import Path

from power_framework import __version__
from power_framework.core.infra_broker import _load_caller_allowlist, load_infra_policy

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_systemd_unit_is_non_root_and_not_a_direct_shell_wrapper() -> None:
    unit = (REPO_ROOT / "deploy" / "systemd" / "power-infra-broker.service").read_text(
        encoding="utf-8"
    )

    assert "User=power-infra" in unit
    assert "Group=power-infra" in unit
    assert "User=root" not in unit
    assert "NoNewPrivileges=yes" in unit
    assert "ProtectSystem=strict" in unit
    assert "ProtectHome=yes" in unit
    assert "PrivateDevices=yes" in unit
    assert "CapabilityBoundingSet=" in unit
    assert "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" in unit
    assert "LoadCredential=" in unit
    assert "--caller-allowlist /etc/power/infra/callers.json" in unit
    assert "ConditionPathExists=/etc/power/infra/callers.json" in unit
    assert "ExecStartPre=/usr/bin/python3 -E -c" in unit
    assert "sys.version_info" in unit
    assert "raise SystemExit" in unit
    assert " assert " not in unit
    assert f"m.version('power-framework') == '{__version__}'" in unit
    assert "EnvironmentFile=" not in unit
    assert "sshpass" not in unit
    assert "KillMode=control-group" in unit
    assert "LimitCORE=0" in unit
    assert "Restart=no" in unit

    socket = (REPO_ROOT / "deploy" / "systemd" / "power-infra-broker.socket").read_text(
        encoding="utf-8"
    )
    assert "ListenStream=/run/power-infra/broker.sock" in socket
    assert "ConditionPathIsDirectory=/run/power-infra" in socket
    assert "SocketGroup=power-infra-callers" in socket
    assert "Accept=no" in socket


def test_receiver_reference_requires_forced_rrsync_and_no_delete() -> None:
    receiver = (REPO_ROOT / "deploy" / "infra" / "receiver.md").read_text(encoding="utf-8")

    assert "rrsync" in receiver
    assert "-wo -no-del" in receiver
    assert "restrict" in receiver
    assert "no root login" in receiver
    key_line = next(
        line
        for line in receiver.splitlines()
        if line.startswith('from="<STABLE_POWER_SOURCE_IP_OR_CIDR>"')
    )
    assert "-no-del" in key_line
    assert "-no-overwrite" in key_line
    assert "--delete" not in key_line
    assert "--rsync-path" not in key_line
    assert "SSH_ORIGINAL_COMMAND" in receiver


def test_operator_profile_example_is_strict_and_identifier_bound() -> None:
    profile_path = REPO_ROOT / "deploy" / "infra" / "profiles.d" / "power-vault.example.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    policy = load_infra_policy(profile_path)

    assert payload["schema_version"] == "power.infra-policy.v1"
    assert policy.profiles[0].profile_id == "power-vault"
    assert policy.profiles[0].target_id == "prxmx01"
    assert policy.profiles[0].approval_policy == "explicit"
    assert policy.profiles[0].dry_run_policy == "required"
    assert policy.profiles[0].verify_credential_id == "power-vault-verify-key"
    assert "host" not in payload["profiles"][0]
    assert "private_key" not in json.dumps(payload)


def test_caller_allowlist_example_is_strict_and_non_empty() -> None:
    path = REPO_ROOT / "deploy" / "infra" / "callers.example.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    uids, gids = _load_caller_allowlist(path)
    assert payload["schema_version"] == "power.infra-callers.v1"
    assert uids == {1000}
    assert gids == set()
