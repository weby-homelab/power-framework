#!/usr/bin/env python3
"""Install wheel and sdist artifacts in isolated environments and smoke-test them."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

SMOKE_CODE = """
from power_framework.core.metrics.udcg_real import _load_semantic_gt

qrels = _load_semantic_gt()
assert len(qrels) > 0
assert all(qrels[query] for query in qrels)
print(f"package smoke passed: {len(qrels)} queries")
"""


def _run(command: list[str], *, cwd: Path) -> None:
    """Run one smoke command and preserve its output in the CI log."""
    subprocess.run(command, check=True, cwd=cwd)  # noqa: S603 -- commands are assembled by this script.


def smoke_artifact(artifact: Path, root: Path) -> None:
    """Install one artifact into a fresh venv outside the repository."""
    name = artifact.stem.replace("-", "_")
    venv_dir = root / f"venv-{name}"
    _run([sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)], cwd=root)
    python = (
        venv_dir
        / ("Scripts" if sys.platform == "win32" else "bin")
        / ("python.exe" if sys.platform == "win32" else "python")
    )
    _run(
        [str(python), "-m", "pip", "install", "--force-reinstall", str(artifact)],
        cwd=root,
    )
    _run([str(python), "-c", SMOKE_CODE], cwd=root)


def main() -> int:
    """Smoke-test the requested package artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    args = parser.parse_args()

    artifacts = [args.wheel.resolve(), args.sdist.resolve()]
    if any(not artifact.is_file() for artifact in artifacts):
        missing = ", ".join(str(artifact) for artifact in artifacts if not artifact.is_file())
        parser.error(f"artifact does not exist: {missing}")

    with tempfile.TemporaryDirectory(prefix="power-package-smoke-") as temp_dir:
        root = Path(temp_dir)
        for artifact in artifacts:
            smoke_artifact(artifact, root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
