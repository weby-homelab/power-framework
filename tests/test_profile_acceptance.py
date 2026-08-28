"""Unit coverage for the disposable Web acceptance fixture."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from scripts import profile_acceptance

if TYPE_CHECKING:
    from pathlib import Path


def test_prepare_vault_uses_privileged_shared_mount_permissions(
    tmp_path: Path, monkeypatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "note.md"
    note.write_text("fixture\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(command: list[str], *, env: dict[str, str] | None = None) -> str:
        del env
        calls.append(command)
        return ""

    monkeypatch.setattr(profile_acceptance, "run", fake_run)

    profile_acceptance.prepare_vault_for_container(vault)

    assert calls == [
        ["sudo", "chown", "-R", "10001:10001", str(vault)],
        ["sudo", "chmod", "-R", "a+rwX", str(vault)],
    ]


def test_prepare_vault_fallback_keeps_host_access_after_restrictive_app_write(
    monkeypatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir(mode=0o700)
    note = vault / "note.md"
    note.write_text("fixture\n", encoding="utf-8")
    note.chmod(0o600)

    def missing_sudo(command: list[str], *, env: dict[str, str] | None = None) -> str:
        del command, env
        raise FileNotFoundError("sudo")

    monkeypatch.setattr(profile_acceptance, "run", missing_sudo)
    monkeypatch.setattr(profile_acceptance.os, "chown", lambda *_args: None)

    profile_acceptance.prepare_vault_for_container(vault)

    assert os.stat(vault).st_mode & 0o777 == 0o777
    assert os.stat(note).st_mode & 0o777 == 0o666
