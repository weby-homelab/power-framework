"""Tests for the explicit, conflict-safe local MCP connection workflow."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from power_framework.core.cli import main
from power_framework.core.connect import apply_connect_plan, build_connect_plan

if TYPE_CHECKING:
    from pathlib import Path


def _managed_mcp_launcher(tmp_path: Path) -> str:
    """Create the exact managed-launcher shape accepted by config integration."""
    home = tmp_path / "managed-home"
    managed = home / ".local" / "share" / "power"
    release = managed / "releases" / "3.7.11-test"
    executable = release / "venv" / "bin" / "power-mcp"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    power_executable = release / "venv" / "bin" / "power"
    power_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    current = managed / "current"
    current.symlink_to(release.relative_to(managed), target_is_directory=True)
    launcher_dir = home / ".local" / "bin"
    launcher_dir.mkdir(parents=True)
    launcher = launcher_dir / "power-mcp"
    launcher.symlink_to(executable)
    (launcher_dir / "power").symlink_to(power_executable)
    (managed / "install.json").write_text(
        json.dumps(
            {
                "status": "applied",
                "current": str(current),
                "release_slot": str(release),
                "venv": str(release / "venv"),
                "launchers": [str(launcher_dir / "power"), str(launcher)],
            }
        ),
        encoding="utf-8",
    )
    return str(launcher)


def test_json_connect_is_hash_bound_and_idempotent(sample_vault: Path, tmp_path: Path) -> None:
    config = tmp_path / "settings.json"
    executable = _managed_mcp_launcher(tmp_path)
    preimage = b'{"mcpServers": {"other": {"enabled": true}}}\n'
    config.write_bytes(preimage)
    plan = build_connect_plan(
        "gemini",
        sample_vault,
        config_path=config,
        executable=executable,
    )

    assert plan.status == "ready"
    assert plan.changed is True
    assert "power_framework.mcp" not in json.dumps(plan.as_dict())
    assert apply_connect_plan(plan.as_dict(), approved=True)["status"] == "applied"
    assert json.loads(config.read_text(encoding="utf-8"))["mcpServers"]["power"]["args"] == []

    second = build_connect_plan("gemini", sample_vault, config_path=config, executable=executable)
    assert second.status == "no_change"
    assert second.changed is False
    assert apply_connect_plan(second.as_dict(), approved=True)["status"] == "no_change"

    remove = build_connect_plan(
        "gemini",
        sample_vault,
        config_path=config,
        executable=executable,
        action="remove",
    )
    receipt = apply_connect_plan(remove.as_dict(), approved=True)
    assert receipt["backup_created"] is True
    assert config.read_bytes() == preimage
    assert list((tmp_path / ".power-backups").iterdir())


@pytest.mark.parametrize(
    ("client", "root_key"),
    [("opencode", "mcp"), ("claude", "mcpServers")],
)
def test_additional_json_clients_round_trip_without_touching_foreign_entries(
    sample_vault: Path,
    tmp_path: Path,
    client: str,
    root_key: str,
) -> None:
    """All documented JSON clients preserve foreign config and exact preimages."""
    config = tmp_path / f"{client}.jsonc"
    preimage = (
        json.dumps(
            {
                "$schema": "https://example.invalid/config.json",
                root_key: {"other": {"enabled": True}},
            },
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )
    config.write_bytes(preimage)
    executable = _managed_mcp_launcher(tmp_path)

    plan = build_connect_plan(
        client,
        sample_vault,
        config_path=config,
        executable=executable,
    )
    assert plan.status == "ready"
    assert apply_connect_plan(plan.as_dict(), approved=True)["status"] == "applied"
    payload = json.loads(config.read_text(encoding="utf-8"))
    assert payload[root_key]["other"] == {"enabled": True}
    assert "power" in payload[root_key]

    second = build_connect_plan(
        client,
        sample_vault,
        config_path=config,
        executable=executable,
    )
    assert second.status == "no_change"
    assert apply_connect_plan(second.as_dict(), approved=True)["status"] == "no_change"

    remove = build_connect_plan(
        client,
        sample_vault,
        config_path=config,
        executable=executable,
        action="remove",
    )
    assert apply_connect_plan(remove.as_dict(), approved=True)["status"] == "applied"
    assert config.read_bytes() == preimage


def test_connect_refuses_foreign_entry_and_stale_plan(sample_vault: Path, tmp_path: Path) -> None:
    config = tmp_path / "settings.json"
    executable = _managed_mcp_launcher(tmp_path)
    config.write_text(
        json.dumps({"mcpServers": {"power": {"command": "hand-maintained"}}}),
        encoding="utf-8",
    )
    foreign = build_connect_plan("gemini", sample_vault, config_path=config, executable=executable)
    assert foreign.status == "manual_review"
    with pytest.raises(PermissionError, match="not POWER-owned"):
        apply_connect_plan(foreign.as_dict(), approved=True)

    config.write_text("{}", encoding="utf-8")
    plan = build_connect_plan("gemini", sample_vault, config_path=config, executable=executable)
    config.write_text('{"unrelated": true}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="stale"):
        apply_connect_plan(plan.as_dict(), approved=True)


def test_connect_rejects_unmanaged_launcher(sample_vault: Path, tmp_path: Path) -> None:
    """A same-named arbitrary binary cannot be placed in an MCP client config."""
    arbitrary = tmp_path / "power-mcp"
    arbitrary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"MCP launcher|managed native runtime"):
        build_connect_plan(
            "gemini",
            sample_vault,
            config_path=tmp_path / "settings.json",
            executable=str(arbitrary),
        )


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows symlink creation requires SeCreateSymbolicLinkPrivilege",
)
def test_connect_refuses_symlinked_client_config(sample_vault: Path, tmp_path: Path) -> None:
    """The config transaction must not resolve a symlink before its safety check."""
    real_config = tmp_path / "real-settings.json"
    real_config.write_text("{}", encoding="utf-8")
    config_link = tmp_path / "settings.json"
    config_link.symlink_to(real_config)

    plan = build_connect_plan(
        "gemini",
        sample_vault,
        config_path=config_link,
        executable=_managed_mcp_launcher(tmp_path),
    )

    assert plan.status == "manual_review"
    assert plan.reason == "symlink client config paths are never followed"


def test_codex_toml_connection_round_trip(sample_vault: Path, tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    executable = _managed_mcp_launcher(tmp_path)
    preimage = b'[profile]\nname = "local"\n'
    config.write_bytes(preimage)
    plan = build_connect_plan("codex", sample_vault, config_path=config, executable=executable)
    assert plan.status == "ready"
    apply_connect_plan(plan.as_dict(), approved=True)
    content = config.read_text(encoding="utf-8")
    assert "[profile]" in content
    assert "[mcp_servers.power]" in content

    remove = build_connect_plan(
        "codex",
        sample_vault,
        config_path=config,
        executable=executable,
        action="remove",
    )
    apply_connect_plan(remove.as_dict(), approved=True)
    assert config.read_bytes() == preimage


def test_connect_cli_writes_read_only_plan(sample_vault: Path, tmp_path: Path, capsys) -> None:
    config = tmp_path / "settings.json"
    plan_path = tmp_path / "connect-plan.json"
    executable = _managed_mcp_launcher(tmp_path)
    with (
        patch.object(
            sys,
            "argv",
            [
                "power",
                "connect",
                str(sample_vault),
                "--client",
                "gemini",
                "--config",
                str(config),
                "--executable",
                executable,
                "--plan-output",
                str(plan_path),
            ],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()

    assert exc.value.code == 0
    output_plan = json.loads(capsys.readouterr().out)
    assert output_plan == json.loads(plan_path.read_text(encoding="utf-8"))
    assert not config.exists()
    assert output_plan["schema_version"] == "power.connect-plan.v1"
