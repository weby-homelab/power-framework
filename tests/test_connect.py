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


def test_json_connect_is_hash_bound_and_idempotent(sample_vault: Path, tmp_path: Path) -> None:
    config = tmp_path / "settings.json"
    preimage = b'{"mcpServers": {"other": {"enabled": true}}}\n'
    config.write_bytes(preimage)
    plan = build_connect_plan(
        "gemini",
        sample_vault,
        config_path=config,
        executable=sys.executable,
    )

    assert plan.status == "ready"
    assert plan.changed is True
    assert "power_framework.mcp" not in json.dumps(plan.as_dict())
    assert apply_connect_plan(plan.as_dict(), approved=True)["status"] == "applied"
    assert json.loads(config.read_text(encoding="utf-8"))["mcpServers"]["power"]["args"] == [
        "-m",
        "power_framework.mcp",
    ]

    second = build_connect_plan(
        "gemini", sample_vault, config_path=config, executable=sys.executable
    )
    assert second.status == "no_change"
    assert second.changed is False
    assert apply_connect_plan(second.as_dict(), approved=True)["status"] == "no_change"

    remove = build_connect_plan(
        "gemini",
        sample_vault,
        config_path=config,
        executable=sys.executable,
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

    plan = build_connect_plan(
        client,
        sample_vault,
        config_path=config,
        executable=sys.executable,  # type: ignore[arg-type]
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
        executable=sys.executable,  # type: ignore[arg-type]
    )
    assert second.status == "no_change"
    assert apply_connect_plan(second.as_dict(), approved=True)["status"] == "no_change"

    remove = build_connect_plan(
        client,
        sample_vault,
        config_path=config,
        executable=sys.executable,  # type: ignore[arg-type]
        action="remove",
    )
    assert apply_connect_plan(remove.as_dict(), approved=True)["status"] == "applied"
    assert config.read_bytes() == preimage


def test_connect_refuses_foreign_entry_and_stale_plan(sample_vault: Path, tmp_path: Path) -> None:
    config = tmp_path / "settings.json"
    config.write_text(
        json.dumps({"mcpServers": {"power": {"command": "hand-maintained"}}}),
        encoding="utf-8",
    )
    foreign = build_connect_plan(
        "gemini", sample_vault, config_path=config, executable=sys.executable
    )
    assert foreign.status == "manual_review"
    with pytest.raises(PermissionError, match="not POWER-owned"):
        apply_connect_plan(foreign.as_dict(), approved=True)

    config.write_text("{}", encoding="utf-8")
    plan = build_connect_plan("gemini", sample_vault, config_path=config, executable=sys.executable)
    config.write_text('{"unrelated": true}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="stale"):
        apply_connect_plan(plan.as_dict(), approved=True)


def test_codex_toml_connection_round_trip(sample_vault: Path, tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    preimage = b'[profile]\nname = "local"\n'
    config.write_bytes(preimage)
    plan = build_connect_plan("codex", sample_vault, config_path=config, executable=sys.executable)
    assert plan.status == "ready"
    apply_connect_plan(plan.as_dict(), approved=True)
    content = config.read_text(encoding="utf-8")
    assert "[profile]" in content
    assert "[mcp_servers.power]" in content

    remove = build_connect_plan(
        "codex",
        sample_vault,
        config_path=config,
        executable=sys.executable,
        action="remove",
    )
    apply_connect_plan(remove.as_dict(), approved=True)
    assert config.read_bytes() == preimage


def test_connect_cli_writes_read_only_plan(sample_vault: Path, tmp_path: Path, capsys) -> None:
    config = tmp_path / "settings.json"
    plan_path = tmp_path / "connect-plan.json"
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
