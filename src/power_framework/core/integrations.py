"""Safe, generic integration plans for the POWER suite.

Every operation is dry-run by default.  The functions in this module return
content-free plans first; apply functions require an explicit approval flag and
re-check the plan's source/preimage before making an atomic change.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.resources
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import venv
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .connect import ConnectClient, apply_connect_plan, build_connect_plan
from .utils import atomic_write

INTEGRATIONS_SCHEMA_VERSION = "power.integrations.v1"
SKILL_SCHEMA_VERSION = "power.skill.v1"
NATIVE_INSTALL_SCHEMA_VERSION = "power.native-install.v1"
SKILL_NAME = "power"


@dataclass(frozen=True)
class SkillTree:
    """Immutable in-memory representation of the packaged Skill tree."""

    files: dict[str, bytes]
    sha256: str


def _aggregate_tree_hash(files: dict[str, bytes]) -> str:
    """Hash paths and bytes in deterministic lexical order."""
    digest = hashlib.sha256()
    for relative in sorted(files):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(files[relative]).digest())
    return digest.hexdigest()


def _walk_resource_tree(root: Any, prefix: str = "") -> dict[str, bytes]:
    """Read a Traversable resource tree without assuming a filesystem path."""
    files: dict[str, bytes] = {}
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        relative = f"{prefix}/{child.name}" if prefix else child.name
        if child.is_dir():
            files.update(_walk_resource_tree(child, relative))
        else:
            files[relative] = child.read_bytes()
    return files


def packaged_skill_tree() -> SkillTree:
    """Return the source Skill tree from checkout or wheel package data."""
    repository_root = Path(__file__).resolve().parents[3]
    source = repository_root / "skills" / SKILL_NAME
    if source.is_dir():
        files = {
            path.relative_to(source).as_posix(): path.read_bytes()
            for path in source.rglob("*")
            if path.is_file()
        }
    else:
        resource_root = (
            importlib.resources.files("power_framework") / "data" / "skills" / SKILL_NAME
        )
        files = _walk_resource_tree(resource_root)
    if not files or "SKILL.md" not in files:
        raise FileNotFoundError("packaged POWER Skill tree is missing SKILL.md")
    return SkillTree(files=files, sha256=_aggregate_tree_hash(files))


def _tree_from_directory(root: Path) -> dict[str, bytes]:
    """Read a target directory using relative POSIX paths."""
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def _is_managed_skill_tree(files: dict[str, bytes], source: SkillTree) -> bool:
    """Recognize an existing POWER Skill tree without trusting its contents."""
    if set(files) != set(source.files):
        return False
    header = files.get("SKILL.md", b"").decode("utf-8", errors="ignore")
    return header.startswith("---\n") and "\nname: power\n" in header


def _safe_target(path: str | Path, *, label: str) -> Path:
    """Reject filesystem roots and symlinks for managed integration targets."""
    target = Path(path).expanduser()
    if target == target.parent or target == Path.home().resolve():
        raise ValueError(f"{label} must be a dedicated child directory, not a filesystem root")
    if target.exists() and target.is_symlink():
        raise ValueError(f"{label} symlinks are not followed")
    return target.resolve()


def build_skill_check_plan(target: str | Path) -> dict[str, Any]:
    """Build a read-only Skill install/check plan."""
    skill = packaged_skill_tree()
    target_path = _safe_target(target, label="Skill target")
    target_files = _tree_from_directory(target_path)
    target_hash = _aggregate_tree_hash(target_files) if target_files else None
    if target_files == skill.files:
        status = "no_change"
    elif target_files and _is_managed_skill_tree(target_files, skill):
        status = "upgrade_ready"
    elif target_files:
        status = "manual_review"
    else:
        status = "ready"
    return {
        "schema": SKILL_SCHEMA_VERSION,
        "status": status,
        "skill": SKILL_NAME,
        "source": {"tree_sha256": skill.sha256, "files": sorted(skill.files)},
        "target": {"path": str(target_path), "tree_sha256": target_hash},
        "write_required": status in {"ready", "upgrade_ready"},
        "overwrite_policy": "replace_only_hash_bound_managed_target",
    }


def apply_skill_install_plan(plan: dict[str, Any], *, approved: bool) -> dict[str, Any]:
    """Atomically install a missing Skill tree after an explicit approval."""
    if not approved:
        raise PermissionError("skill install requires explicit approved=True")
    if plan.get("schema") != SKILL_SCHEMA_VERSION:
        raise ValueError("unsupported Skill plan schema")
    target = _safe_target(plan["target"]["path"], label="Skill target")
    current = build_skill_check_plan(target)
    if current["status"] == "no_change":
        return {"schema": SKILL_SCHEMA_VERSION, "status": "no_change", "target": str(target)}
    if current["status"] == "manual_review":
        raise PermissionError("Skill target exists with different content; manual review required")
    if current["target"]["tree_sha256"] != plan["target"].get("tree_sha256"):
        raise RuntimeError("Skill target changed after the plan was created")
    if current["status"] not in {"ready", "upgrade_ready"}:
        raise RuntimeError(f"unsupported Skill plan status: {current['status']}")
    skill = packaged_skill_tree()
    if skill.sha256 != plan["source"]["tree_sha256"]:
        raise RuntimeError("Skill source changed after the plan was created")

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent))
    previous: Path | None = None
    try:
        for relative, content in skill.files.items():
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            destination.chmod(0o755 if relative.startswith("scripts/") else 0o644)
        if target.exists():
            previous = target.parent / f".{target.name}.previous-{os.getpid()}"
            os.replace(target, previous)
        os.replace(staging, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        if previous is not None and previous.exists() and not target.exists():
            os.replace(previous, target)
        raise
    if previous is not None:
        shutil.rmtree(previous)
    return {
        "schema": SKILL_SCHEMA_VERSION,
        "status": "applied",
        "target": str(target),
        "tree_sha256": skill.sha256,
        "files": len(skill.files),
    }


def build_integrations_doctor() -> dict[str, Any]:
    """Return read-only facts about the available suite integration surfaces."""
    skill = packaged_skill_tree()
    try:
        mcp_version = importlib.metadata.version("mcp")
    except importlib.metadata.PackageNotFoundError:
        mcp_version = None
    try:
        power_version = importlib.metadata.version("power-framework")
    except importlib.metadata.PackageNotFoundError:
        power_version = None
    home = Path.home()
    venv_root = home / ".local" / "share" / "power" / "venv"
    launchers = {
        name: home / ".local" / "bin" / name for name in ("power", "power-mcp", "power-gui")
    }
    return {
        "schema": INTEGRATIONS_SCHEMA_VERSION,
        "status": "ok"
        if mcp_version and all(path.is_file() for path in launchers.values())
        else "incomplete",
        "runtime": {
            "power_framework": power_version,
            "mcp_sdk": mcp_version,
            "python": sys.version.split()[0],
        },
        "native": {
            "venv": str(venv_root),
            "venv_exists": venv_root.is_dir(),
            "launchers": {
                name: {"path": str(path), "exists": path.is_file()}
                for name, path in launchers.items()
            },
        },
        "skill": {
            "source": f"skills/{SKILL_NAME}",
            "tree_sha256": skill.sha256,
            "files": len(skill.files),
        },
        "mcp": {"entry_point": "power-mcp", "transport": "stdio", "vault_env": "POWER_VAULT_DIR"},
    }


def build_mcp_config_integration_plan(
    vault_path: str | Path,
    *,
    client: ConnectClient = "auto",
    config_path: str | Path | None = None,
    executable: str = "power-mcp",
    remove: bool = False,
) -> dict[str, Any]:
    """Build the generic, hash-bound MCP client config plan."""
    plan = build_connect_plan(
        client,
        Path(vault_path).expanduser().resolve(),
        config_path=Path(config_path).expanduser() if config_path else None,
        executable=executable,
        action="remove" if remove else "install",
    ).as_dict()
    plan["integration"] = "mcp-config"
    plan["entry_point"] = "power-mcp"
    return plan


def apply_mcp_config_integration_plan(plan: dict[str, Any], *, approved: bool) -> dict[str, Any]:
    """Apply a previously planned MCP config transaction."""
    return apply_connect_plan(plan, approved=approved)


def _sha256_file(path: Path) -> str:
    """Hash an exact wheel or artifact file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wheel_dependencies(path: Path) -> list[str]:
    """Read ordinary runtime dependencies from a wheel without importing it."""
    with zipfile.ZipFile(path) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = archive.read(metadata_name).decode("utf-8")
    dependencies = []
    for line in metadata.splitlines():
        if not line.startswith("Requires-Dist:"):
            continue
        requirement = line.split(":", 1)[1].strip()
        if requirement.lower().startswith("power-framework"):
            continue
        dependencies.append(requirement)
    return dependencies


def build_native_install_plan(
    *,
    home: str | Path | None = None,
    power_wheel: str | Path | None = None,
    gui_wheel: str | Path | None = None,
) -> dict[str, Any]:
    """Build a dry-run native installer plan for one managed venv."""
    install_home = _safe_target(home or Path.home() / ".power-install-home", label="installer home")
    if home is None:
        install_home = Path.home().resolve()
    managed = install_home / ".local" / "share" / "power"
    venv_root = managed / "venv"
    launcher_dir = install_home / ".local" / "bin"
    if not power_wheel:
        return {
            "schema": NATIVE_INSTALL_SCHEMA_VERSION,
            "status": "blocked",
            "reason": "an exact POWER wheel is required",
            "native": {
                "home": str(install_home),
                "venv": str(venv_root),
                "launcher_dir": str(launcher_dir),
            },
        }
    power_path = Path(power_wheel).expanduser().resolve()
    if not power_path.is_file() or power_path.suffix != ".whl":
        raise ValueError("power_wheel must be an existing .whl file")
    gui_path = Path(gui_wheel).expanduser().resolve() if gui_wheel else None
    if gui_path is not None and (not gui_path.is_file() or gui_path.suffix != ".whl"):
        raise ValueError("gui_wheel must be an existing .whl file")
    state_path = managed / "suite-install.json"
    return {
        "schema": NATIVE_INSTALL_SCHEMA_VERSION,
        "status": "ready" if not state_path.is_file() else "update",
        "native": {
            "home": str(install_home),
            "venv": str(venv_root),
            "launcher_dir": str(launcher_dir),
            "state": str(state_path),
        },
        "artifacts": {
            "power_wheel": {"path": str(power_path), "sha256": _sha256_file(power_path)},
            "gui_wheel": (
                {"path": str(gui_path), "sha256": _sha256_file(gui_path)} if gui_path else None
            ),
        },
        "launchers": ["power", "power-mcp", "power-gui"] if gui_path else ["power", "power-mcp"],
        "system_python_mutation": False,
        "dry_run_default": True,
    }


def _write_executable(path: Path, content: str) -> None:
    """Atomically install one executable launcher."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.staging-{os.getpid()}")
    temporary.write_text(content, encoding="utf-8")
    temporary.chmod(
        stat.S_IRUSR
        | stat.S_IWUSR
        | stat.S_IXUSR
        | stat.S_IRGRP
        | stat.S_IXGRP
        | stat.S_IROTH
        | stat.S_IXOTH
    )
    os.replace(temporary, path)


def apply_native_install_plan(
    plan: dict[str, Any],
    *,
    approved: bool,
    no_deps: bool = False,
) -> dict[str, Any]:
    """Create the managed venv, install exact wheels, and publish launchers."""
    if not approved:
        raise PermissionError("native install requires explicit approved=True")
    if plan.get("schema") != NATIVE_INSTALL_SCHEMA_VERSION or plan.get("status") == "blocked":
        raise ValueError("native install plan is not applicable")
    native = plan["native"]
    venv_root = Path(native["venv"])
    launcher_dir = Path(native["launcher_dir"])
    venv_python = venv_root / "bin" / "python"
    if not venv_python.is_file():
        venv.EnvBuilder(with_pip=True, clear=False, symlinks=True).create(venv_root)

    power_artifact = plan["artifacts"]["power_wheel"]
    artifacts = [power_artifact]
    gui_artifact = plan["artifacts"].get("gui_wheel")
    if gui_artifact:
        artifacts.append(gui_artifact)
    for artifact in artifacts:
        path = Path(artifact["path"])
        if _sha256_file(path) != artifact["sha256"]:
            raise RuntimeError(f"artifact changed after the plan was created: {path}")
        command = [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--upgrade",
        ]
        if no_deps:
            command.append("--no-deps")
        if artifact is power_artifact and not no_deps:
            command.append(f"{path}[remote]")
        elif artifact is gui_artifact and not no_deps:
            command.append("--no-deps")
            command.append(str(path))
        else:
            command.append(str(path))
        subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603
        if artifact is gui_artifact and not no_deps:
            dependencies = _wheel_dependencies(path)
            if dependencies:
                dependency_command = [
                    str(venv_python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-input",
                    "--upgrade",
                    *dependencies,
                ]
                subprocess.run(  # noqa: S603 - dependencies come from verified wheel metadata
                    dependency_command,
                    check=True,
                    capture_output=True,
                    text=True,
                )

    venv_text = str(venv_root)
    _write_executable(launcher_dir / "power", f"#!/bin/sh\nexec '{venv_text}/bin/power' \"$@\"\n")
    _write_executable(
        launcher_dir / "power-mcp",
        f"#!/bin/sh\nexec '{venv_text}/bin/power-mcp' \"$@\"\n",
    )
    if plan["artifacts"].get("gui_wheel"):
        _write_executable(
            launcher_dir / "power-gui",
            f"#!/bin/sh\nexec '{venv_text}/bin/power-gui' \"$@\"\n",
        )
    receipt = {
        "schema": NATIVE_INSTALL_SCHEMA_VERSION,
        "status": "applied",
        "venv": str(venv_root),
        "launchers": [
            str(launcher_dir / name)
            for name in ("power", "power-mcp", "power-gui")
            if name != "power-gui" or plan["artifacts"].get("gui_wheel")
        ],
        "artifacts": plan["artifacts"],
        "no_deps": no_deps,
    }
    state_path = Path(native["state"])
    atomic_write(
        state_path, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return receipt


__all__ = [
    "apply_mcp_config_integration_plan",
    "apply_native_install_plan",
    "apply_skill_install_plan",
    "build_integrations_doctor",
    "build_mcp_config_integration_plan",
    "build_native_install_plan",
    "build_skill_check_plan",
    "packaged_skill_tree",
]
