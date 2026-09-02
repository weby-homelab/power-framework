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
import json
import os
import subprocess
import tempfile
from pathlib import Path

from power_framework.core import __version__
from power_framework.core.metrics.udcg_real import _load_semantic_gt

distribution_version = importlib.metadata.version("power-framework")
assert distribution_version == __version__, (
    f"distribution/runtime version mismatch: {distribution_version} != {__version__}"
)
version_result = subprocess.run(
    ["power", "--version"], capture_output=True, check=True, text=True
)

mcp_version = subprocess.run(
    ["power-mcp", "--version"], capture_output=True, check=True, text=True
)
assert distribution_version in mcp_version.stdout, (
    f"MCP launcher version mismatch: {mcp_version.stdout!r}"
)
with tempfile.TemporaryDirectory(prefix="power-mcp-smoke-") as directory:
    vault = Path(directory) / "vault"
    vault.mkdir()
    mcp_environment = os.environ | {"POWER_VAULT_DIR": str(vault)}
    preflight = subprocess.run(
        ["power-mcp", "preflight"],
        capture_output=True,
        check=True,
        env=mcp_environment,
        text=True,
    )
    assert preflight.stderr == ""
    assert json.loads(preflight.stdout)["vault_root"] == str(vault.resolve())
assert distribution_version in version_result.stdout, (
    f"CLI version mismatch: {version_result.stdout!r}"
)

qrels = _load_semantic_gt()
assert len(qrels) > 0
assert all(qrels[query] for query in qrels)
print(f"package smoke passed: version={distribution_version}, queries={len(qrels)}")
"""


def _run(command: list[str], *, cwd: Path, environment: dict[str, str] | None = None) -> None:
    """Run one smoke command and preserve its output in the CI log."""
    run_environment = environment or os.environ.copy()
    # The release job must not let a checkout-relative source path shadow the
    # package installed from the wheel/sdist under test.
    run_environment.pop("PYTHONPATH", None)
    subprocess.run(  # noqa: S603 -- commands are assembled by this script.
        command,
        check=True,
        cwd=cwd,
        env=run_environment,
    )


def smoke_artifact(artifact: Path, root: Path, dependency_lock: Path | None) -> None:
    """Install one artifact into a fresh venv outside the repository."""
    name = artifact.stem.replace("-", "_")
    venv_dir = root / f"venv-{name}"
    _run([sys.executable, "-m", "venv", str(venv_dir)], cwd=root)
    python = (
        venv_dir
        / ("Scripts" if sys.platform == "win32" else "bin")
        / ("python.exe" if sys.platform == "win32" else "python")
    )
    scripts_dir = python.parent
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join([str(scripts_dir), environment.get("PATH", "")]).rstrip(
        os.pathsep
    )
    if dependency_lock is not None:
        _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--require-hashes",
                "--only-binary=:all:",
                "--no-deps",
                "-r",
                str(dependency_lock),
            ],
            cwd=root,
            environment=environment,
        )
        install_target = str(artifact)
        install_arguments = [
            str(python),
            "-m",
            "pip",
            "install",
            "--force-reinstall",
            "--no-deps",
            install_target,
        ]
    else:
        install_arguments = [
            str(python),
            "-m",
            "pip",
            "install",
            "--force-reinstall",
            f"{artifact}[mcp]",
        ]
    _run(install_arguments, cwd=root, environment=environment)
    _run([str(python), "-c", SMOKE_CODE], cwd=root, environment=environment)


def main() -> int:
    """Smoke-test the requested package artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    parser.add_argument("--dependency-lock", type=Path)
    args = parser.parse_args()

    raw_artifacts = [args.wheel, args.sdist]
    if any(artifact.is_symlink() or not artifact.is_file() for artifact in raw_artifacts):
        invalid = ", ".join(
            str(artifact)
            for artifact in raw_artifacts
            if artifact.is_symlink() or not artifact.is_file()
        )
        parser.error(f"artifact is missing or symlinked: {invalid}")
    dependency_lock = args.dependency_lock.expanduser() if args.dependency_lock else None
    if dependency_lock is not None and (
        dependency_lock.is_symlink() or not dependency_lock.is_file()
    ):
        parser.error(f"dependency lock is missing or symlinked: {dependency_lock}")
    if dependency_lock is not None:
        dependency_lock = dependency_lock.resolve()
    artifacts = [artifact.resolve() for artifact in raw_artifacts]

    with tempfile.TemporaryDirectory(prefix="power-package-smoke-") as temp_dir:
        root = Path(temp_dir)
        for artifact in artifacts:
            smoke_artifact(artifact, root, dependency_lock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
