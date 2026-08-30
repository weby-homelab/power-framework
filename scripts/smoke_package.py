#!/usr/bin/env python3
"""Install wheel and sdist artifacts in isolated environments and smoke-test them."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SMOKE_CODE = """
import importlib.metadata
import subprocess

from power_framework.core import __version__
from power_framework.core.metrics.udcg_real import _load_semantic_gt

distribution_version = importlib.metadata.version("power-framework")
assert distribution_version == __version__, (
    f"distribution/runtime version mismatch: {distribution_version} != {__version__}"
)
version_result = subprocess.run(
    ["power", "--version"], capture_output=True, check=True, text=True
)
assert distribution_version in version_result.stdout, (
    f"CLI version mismatch: {version_result.stdout!r}"
)

qrels = _load_semantic_gt()
assert len(qrels) > 0
assert all(qrels[query] for query in qrels)
print(f"package smoke passed: version={distribution_version}, queries={len(qrels)}")
"""


def _run(command: list[str], *, cwd: Path) -> None:
    """Run one smoke command and preserve its output in the CI log."""
    environment = os.environ.copy()
    # The release job must not let a checkout-relative source path shadow the
    # package installed from the wheel/sdist under test.
    environment.pop("PYTHONPATH", None)
    subprocess.run(  # noqa: S603 -- commands are assembled by this script.
        command,
        check=True,
        cwd=cwd,
        env=environment,
    )


def smoke_artifact(artifact: Path, root: Path) -> None:
    """Install one artifact into a fresh venv outside the repository."""
    name = artifact.stem.replace("-", "_")
    venv_dir = root / f"venv-{name}"
    _run([sys.executable, "-m", "venv", str(venv_dir)], cwd=root)
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

    raw_artifacts = [args.wheel, args.sdist]
    if any(artifact.is_symlink() or not artifact.is_file() for artifact in raw_artifacts):
        invalid = ", ".join(
            str(artifact)
            for artifact in raw_artifacts
            if artifact.is_symlink() or not artifact.is_file()
        )
        parser.error(f"artifact is missing or symlinked: {invalid}")
    artifacts = [artifact.resolve() for artifact in raw_artifacts]

    with tempfile.TemporaryDirectory(prefix="power-package-smoke-") as temp_dir:
        root = Path(temp_dir)
        for artifact in artifacts:
            smoke_artifact(artifact, root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
