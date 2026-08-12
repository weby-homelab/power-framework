"""Cross-transport conformance for the stable 3.5 application boundary."""

from __future__ import annotations

import json
import sys
import time
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from power_framework.core.application import ApplicationService, RequestContext
from power_framework.core.cli import main
from power_framework.mcp.power_server import search_vault_tool

if TYPE_CHECKING:
    from pathlib import Path


def test_retrieve_data_is_identical_through_direct_api_and_cli(
    sample_vault: Path, capsys: pytest.CaptureFixture
) -> None:
    """CLI JSON is the same application data, not a second storage workflow."""
    with patch("power_framework.core.searcher.time.time", return_value=2_000_000_000):
        direct = ApplicationService(sample_vault).retrieve(
            "Test",
            max_results=3,
            mode="fts",
            as_of="2026-08-11",
        )
        with (
            patch.object(
                sys,
                "argv",
                [
                    "power",
                    "search",
                    str(sample_vault),
                    "Test",
                    "--max-results",
                    "3",
                    "--mode",
                    "fts",
                    "--as-of",
                    "2026-08-11",
                    "--json",
                ],
            ),
            pytest.raises(SystemExit) as exit_info,
        ):
            main()

    assert exit_info.value.code == 0
    cli_data = json.loads(capsys.readouterr().out)
    assert cli_data == direct.data


@pytest.mark.asyncio
async def test_retrieve_data_is_identical_through_local_mcp(
    sample_vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MCP keeps the legacy retrieval envelope while delegating to the service."""
    monkeypatch.setattr("power_framework.core.searcher.time.time", lambda: 2_000_000_000)
    direct = ApplicationService(sample_vault).retrieve(
        "Test",
        max_results=3,
        mode="fts",
        as_of="2026-08-11",
    )

    wire = await search_vault_tool(
        query="Test",
        max_results=3,
        search_mode="fts",
        as_of="2026-08-11",
        vault_path=str(sample_vault),
    )

    assert json.loads(wire) == direct.data


def test_receipt_use_case_is_bounded_and_content_free(sample_vault: Path) -> None:
    result = ApplicationService(sample_vault).receipt(limit=10)

    assert result.operation == "receipt"
    assert list(result.data) == ["receipts"]
    assert "secret" not in json.dumps(result.as_dict()).lower()


def test_deadline_is_enforced_for_slow_read_without_mutating_vault(sample_vault: Path) -> None:
    def slow_search(*_args: object, **_kwargs: object) -> list[object]:
        time.sleep(0.02)
        return []

    with pytest.raises(TimeoutError, match="deadline exceeded"):
        ApplicationService(sample_vault, search_fn=slow_search).retrieve(
            "deadline",
            context=RequestContext(deadline_ms=1),
        )

    assert not (sample_vault / ".power" / "proposals").exists()
