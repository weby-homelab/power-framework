"""Cross-process proof for the canonical vault mutation boundary."""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_SCRIPT = "from power_framework.core.cli import main; raise SystemExit(main())"


def _run_cli(arguments: list[str], environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run one source-checkout CLI child with a fixed executable and cwd."""
    return subprocess.run(  # noqa: S603 - executable and arguments are test-local constants.
        [sys.executable, "-c", CLI_SCRIPT, *arguments],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_parallel_cli_processes_preserve_one_canonical_vault_state(tmp_path: Path) -> None:
    """Two independent processes can mutate one vault without lost notes/catalog state."""
    vault = tmp_path / "vault"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT / "src"), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)

    initialized = _run_cli(["init", str(vault)], environment)
    assert initialized.returncode == 0, initialized.stderr

    commands = [
        [
            "ingest",
            str(vault),
            "--type",
            "Resource",
            "--title",
            "Process one",
            "--description",
            "Cross-process acceptance note one",
            "--tags",
            "process-one",
        ],
        [
            "ingest",
            str(vault),
            "--type",
            "Resource",
            "--title",
            "Process two",
            "--description",
            "Cross-process acceptance note two",
            "--tags",
            "process-two",
        ],
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda command: _run_cli(command, environment), commands))

    assert [result.returncode for result in results] == [0, 0], [
        result.stderr for result in results
    ]
    assert (vault / "03_Resources" / "process_one.md").is_file()
    assert (vault / "03_Resources" / "process_two.md").is_file()
    catalog = (vault / "03_Resources" / "_index.md").read_text(encoding="utf-8")
    assert "Process one" in catalog
    assert "Process two" in catalog
    assert (vault / ".power" / "mutation.lock").is_file()
