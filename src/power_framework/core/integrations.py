"""Safe, generic integration plans for unified POWER.

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
import uuid
import venv
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .connect import (
    DEFAULT_MCP_EXECUTABLE,
    ConnectClient,
    apply_connect_plan,
    build_connect_plan,
)
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
        if child.name == "__pycache__" or child.name.endswith(".pyc"):
            continue
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
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
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
        if (
            path.is_file()
            and not path.is_symlink()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        )
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
    """Return read-only facts about the available unified POWER surfaces."""
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
    managed = home / ".local" / "share" / "power"
    legacy_venv = managed / "venv"
    current_link = managed / "current"
    current_target = current_link.resolve() if current_link.is_symlink() else None
    active_venv = (
        current_link / "venv"
        if current_target is not None and current_target.is_dir()
        else legacy_venv
    )
    launchers = {name: home / ".local" / "bin" / name for name in ("power", "power-mcp")}
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
            "managed": str(managed),
            "releases": str(managed / "releases"),
            "current": str(current_link),
            "current_target": str(current_target) if current_target is not None else None,
            "active_venv": str(active_venv),
            "active_venv_exists": active_venv.is_dir(),
            "venv": str(active_venv),
            "venv_exists": active_venv.is_dir(),
            "legacy_venv": str(legacy_venv),
            "legacy_venv_present": legacy_venv.exists() and not legacy_venv.is_symlink(),
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
        "mcp": {
            "entry_point": "power-mcp",
            "transport": "stdio",
            "vault_environment": "POWER_VAULT_DIR",
        },
    }


def build_mcp_config_integration_plan(
    vault_path: str | Path,
    *,
    client: ConnectClient = "auto",
    config_path: str | Path | None = None,
    executable: str = DEFAULT_MCP_EXECUTABLE,
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


def _wheel_text(path: Path, suffix: str) -> str:
    """Read exactly one metadata file from a wheel."""
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith(suffix)]
        if len(names) != 1:
            raise ValueError(f"wheel must contain exactly one {suffix} file")
        return archive.read(names[0]).decode("utf-8")


def _metadata_value(metadata: str, key: str) -> str | None:
    """Read one RFC-822 style wheel metadata field."""
    prefix = f"{key}:"
    for line in metadata.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def _wheel_tree(path: Path, prefix: str) -> dict[str, bytes]:
    """Read a deterministic subtree from a wheel."""
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith(prefix) or name.endswith("/"):
                continue
            relative = name[len(prefix) :]
            if not relative or "__pycache__" in relative or relative.endswith(".pyc"):
                continue
            files[relative] = archive.read(name)
    return files


def _release_contract(manifest: str | Path, power_wheel: Path) -> dict[str, Any]:
    """Validate one release manifest against one exact unified wheel."""
    manifest_path = Path(manifest).expanduser().resolve()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"release manifest is not valid JSON: {manifest_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("release manifest must contain a JSON object")
    if payload.get("schema") != "power.release.manifest.v1":
        raise ValueError("unsupported POWER release manifest schema")

    version = payload.get("version")
    commit = payload.get("commit")
    requires_python = payload.get("requires_python")
    application_schema = payload.get("application_schema")
    if not all(
        isinstance(item, str) and item.strip() for item in (version, commit, requires_python)
    ):
        raise ValueError("release manifest version, commit, and requires_python are required")
    if application_schema != "power.application.v2":
        raise ValueError("release manifest application schema is not power.application.v2")

    profiles = payload.get("profiles")
    if not isinstance(profiles, dict):
        raise ValueError("release manifest profiles are required")
    if profiles.get("native") != ["power", "power-mcp"]:
        raise ValueError("native profile must expose only power and power-mcp")
    if "power-gui" in json.dumps(profiles, sort_keys=True):
        raise ValueError("release manifest contains retired power-gui runtime")

    mcp = payload.get("mcp")
    if (
        not isinstance(mcp, dict)
        or mcp.get("entry_point") != "power-mcp"
        or mcp.get("transport") != "stdio"
    ):
        raise ValueError("release manifest MCP contract must be power-mcp over stdio")
    web = payload.get("web")
    if (
        not isinstance(web, dict)
        or web.get("entry_point") != "power-web"
        or web.get("port") != 8080
    ):
        raise ValueError("release manifest Web contract must expose power-web on port 8080")

    artifacts = payload.get("artifacts")
    wheel_artifact = artifacts.get("power_wheel") if isinstance(artifacts, dict) else None
    if not isinstance(wheel_artifact, dict):
        raise ValueError("release manifest must contain an exact power_wheel artifact")
    if wheel_artifact.get("filename") != power_wheel.name:
        raise ValueError("release manifest wheel filename does not match the supplied artifact")
    wheel_sha256 = wheel_artifact.get("sha256")
    if not isinstance(wheel_sha256, str) or wheel_sha256 != _sha256_file(power_wheel):
        raise ValueError("release manifest wheel hash does not match the supplied artifact")

    metadata = _wheel_text(power_wheel, ".dist-info/METADATA")
    if _metadata_value(metadata, "Name") != "power-framework":
        raise ValueError("native installer accepts only the power-framework distribution")
    if _metadata_value(metadata, "Version") != version:
        raise ValueError("wheel version does not match the release manifest")
    if _metadata_value(metadata, "Requires-Python") != requires_python:
        raise ValueError("wheel Python requirement does not match the release manifest")

    skill_files = _wheel_tree(power_wheel, "power_framework/data/skills/power/")
    if not skill_files or "SKILL.md" not in skill_files:
        raise ValueError("unified wheel does not contain the packaged POWER Skill")
    skill_sha256 = _aggregate_tree_hash(skill_files)
    if payload.get("skill_tree_sha256") != skill_sha256:
        raise ValueError("release manifest Skill tree hash does not match the wheel")

    mcp_files = _wheel_tree(power_wheel, "power_framework/mcp/")
    mcp_sha256 = _aggregate_tree_hash(mcp_files)
    if payload.get("mcp_contract_sha256") != mcp_sha256:
        raise ValueError("release manifest MCP contract hash does not match the wheel")

    return {
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha256_file(manifest_path),
        "version": version,
        "commit": commit,
        "requires_python": requires_python,
        "application_schema": application_schema,
        "skill_tree_sha256": skill_sha256,
        "mcp_contract_sha256": mcp_sha256,
        "profiles": profiles,
        "mcp": mcp,
        "web": web,
    }


def _native_layout(install_home: Path) -> dict[str, Path]:
    """Return the managed native layout without creating any path."""
    managed = install_home / ".local" / "share" / "power"
    return {
        "managed": managed,
        "releases": managed / "releases",
        "current": managed / "current",
        "legacy_venv": managed / "venv",
        "launcher_dir": install_home / ".local" / "bin",
        "state": managed / "install.json",
    }


def build_native_install_plan(
    *,
    home: str | Path | None = None,
    power_wheel: str | Path | None = None,
    manifest: str | Path | None = None,
) -> dict[str, Any]:
    """Build a dry-run installer plan for one exact unified POWER wheel."""
    install_home = _safe_target(home, label="installer home") if home else Path.home().resolve()
    layout = _native_layout(install_home)
    common_native = {
        "home": str(install_home),
        "managed": str(layout["managed"]),
        "releases": str(layout["releases"]),
        "current": str(layout["current"]),
        "launcher_dir": str(layout["launcher_dir"]),
        "state": str(layout["state"]),
    }
    if not manifest:
        return {
            "schema": NATIVE_INSTALL_SCHEMA_VERSION,
            "status": "blocked",
            "reason": "an exact POWER release manifest is required",
            "native": common_native,
        }
    if not power_wheel:
        return {
            "schema": NATIVE_INSTALL_SCHEMA_VERSION,
            "status": "blocked",
            "reason": "an exact power-framework wheel is required",
            "native": common_native,
        }
    power_path = Path(power_wheel).expanduser().resolve()
    if not power_path.is_file() or power_path.suffix != ".whl":
        raise ValueError("power_wheel must be an existing .whl file")
    contract = _release_contract(manifest, power_path)
    slot_name = f"{contract['version']}-{contract['manifest_sha256'][:12]}-{uuid.uuid4().hex[:12]}"
    release_slot = layout["releases"] / slot_name
    state = None
    if layout["state"].is_file():
        try:
            state = json.loads(layout["state"].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = None
    current_target = layout["current"].resolve() if layout["current"].is_symlink() else None
    status = (
        "no_change"
        if isinstance(state, dict)
        and state.get("manifest_sha256") == contract["manifest_sha256"]
        and current_target is not None
        and current_target.is_dir()
        else "update"
        if state is not None
        else "ready"
    )
    return {
        "schema": NATIVE_INSTALL_SCHEMA_VERSION,
        "status": status,
        "native": {
            **common_native,
            "release_slot": str(release_slot),
            "slot_venv": str(release_slot / "venv"),
            "active_venv": str(layout["current"] / "venv"),
            "legacy_venv": str(layout["legacy_venv"]),
            "legacy_venv_present": layout["legacy_venv"].exists()
            and not layout["legacy_venv"].is_symlink(),
        },
        "contract": contract,
        "artifacts": {"power_wheel": {"path": str(power_path), "sha256": _sha256_file(power_path)}},
        "launchers": ["power", "power-mcp"],
        "retired_launchers": ["power-gui"],
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


def _atomic_symlink(target: Path | str, link: Path, *, identifier: str) -> None:
    """Atomically replace one managed symlink without touching its target."""
    temporary = link.with_name(f".{link.name}.next-{identifier}")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target, target_is_directory=True)
    try:
        os.replace(temporary, link)
    finally:
        temporary.unlink(missing_ok=True)


def _verify_installed_launcher(
    path: Path,
    arguments: list[str],
    *,
    expected_version: str | None = None,
) -> None:
    """Execute an installed launcher and fail closed on identity drift."""
    result = subprocess.run(  # noqa: S603 - exact verified install path and fixed arguments.
        [str(path), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    if expected_version is not None:
        output = f"{result.stdout}\n{result.stderr}"
        if expected_version not in output:
            raise RuntimeError(f"launcher identity mismatch: {path}")


def _is_managed_launcher(path: Path) -> bool:
    """Recognize a wrapper generated by the native installer."""
    if path.is_symlink():
        return True
    if not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    return content.startswith("#!/bin/sh\n") and "/.local/share/power/current/venv/bin/" in content


def apply_native_install_plan(
    plan: dict[str, Any],
    *,
    approved: bool,
    no_deps: bool = False,
) -> dict[str, Any]:
    """Build, verify, and atomically activate one unified POWER release slot."""
    if not approved:
        raise PermissionError("native install requires explicit approved=True")
    if plan.get("schema") != NATIVE_INSTALL_SCHEMA_VERSION or plan.get("status") == "blocked":
        raise ValueError("native install plan is not applicable")
    if plan.get("status") == "no_change":
        return {
            "schema": NATIVE_INSTALL_SCHEMA_VERSION,
            "status": "no_change",
            "manifest_sha256": plan["contract"]["manifest_sha256"],
            "version": plan["contract"]["version"],
        }
    native = plan["native"]
    managed = Path(native["managed"])
    releases_root = Path(native["releases"])
    release_slot = Path(native["release_slot"])
    slot_venv = Path(native["slot_venv"])
    current_link = Path(native["current"])
    legacy_venv = Path(native["legacy_venv"])
    launcher_dir = Path(native["launcher_dir"])
    state_path = Path(native["state"])
    manifest_path = Path(plan["contract"]["manifest_path"])
    power_path = Path(plan["artifacts"]["power_wheel"]["path"])
    contract = _release_contract(manifest_path, power_path)
    if contract != plan["contract"]:
        raise RuntimeError("POWER release manifest or wheel changed after the plan was created")

    managed.mkdir(parents=True, exist_ok=True)
    releases_root.mkdir(parents=True, exist_ok=True)
    activation_id = uuid.uuid4().hex
    if release_slot.exists():
        raise RuntimeError("release slot already exists and will not be overwritten")
    if current_link.exists() and not current_link.is_symlink():
        raise RuntimeError("managed current pointer exists but is not a symlink")
    previous_current_target: str | None = None
    previous_release_slot: Path | None = None
    if current_link.is_symlink():
        previous_current_target = os.readlink(current_link)
        previous_release_slot = current_link.resolve()
        if not previous_release_slot.is_dir():
            raise RuntimeError("managed current pointer is dangling")
    launcher_stage = launcher_dir / f".launchers.staging-{activation_id}"
    launcher_names = ["power", "power-mcp"]
    retired_launcher_names = ["power-gui"]
    launcher_snapshots: dict[Path, tuple[bytes, int] | None] = {}
    for name in [*launcher_names, *retired_launcher_names]:
        destination = launcher_dir / name
        if destination.is_symlink():
            launcher_snapshots[destination] = (os.readlink(destination).encode("utf-8"), 0o120777)
        elif destination.is_file():
            launcher_snapshots[destination] = (destination.read_bytes(), destination.stat().st_mode)
        else:
            launcher_snapshots[destination] = None
    state_snapshot = state_path.read_bytes() if state_path.is_file() else None
    pointer_activated = False
    retired_legacy_link: str | None = None
    try:
        # The environment is born at its final physical path.  A populated
        # Python venv is never moved or repaired after installation.
        venv.EnvBuilder(with_pip=True, clear=False, symlinks=True).create(slot_venv)
        slot_python = slot_venv / "bin" / "python"

        def run_pip(arguments: list[str]) -> None:
            command = [
                str(slot_python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                "--upgrade",
            ]
            command.extend(arguments)
            subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603

        if no_deps:
            run_pip(["--no-deps", str(power_path)])
        else:
            run_pip([f"{power_path}[mcp]"])

        check_script = (
            "import importlib.metadata as m; "
            "import power_framework; "
            "from power_framework.core.application import ApplicationEnvelope; "
            "assert m.version('power-framework') == "
            f"{contract['version']!r}; "
            "assert ApplicationEnvelope.__dataclass_fields__['schema_version'].default == "
            f"{contract['application_schema']!r}"
        )
        subprocess.run(  # noqa: S603 - interpreter and script are generated from verified inputs.
            [str(slot_python), "-c", check_script],
            check=True,
            capture_output=True,
            text=True,
        )

        expected_power = contract["version"]
        _verify_installed_launcher(
            slot_venv / "bin" / "power", ["--version"], expected_version=expected_power
        )
        _verify_installed_launcher(
            slot_venv / "bin" / "power-mcp", ["--version"], expected_version=expected_power
        )

        launcher_dir.mkdir(parents=True, exist_ok=True)
        launcher_stage.mkdir(parents=True, exist_ok=False)
        active_venv_text = str(current_link / "venv")
        for name in launcher_names:
            _write_executable(
                launcher_stage / name,
                f"#!/bin/sh\nexec '{active_venv_text}/bin/{name}' \"$@\"\n",
            )

        relative_slot = Path(os.path.relpath(release_slot, managed))
        _atomic_symlink(relative_slot, current_link, identifier=activation_id)
        pointer_activated = True
        for name in launcher_names:
            os.replace(launcher_stage / name, launcher_dir / name)

        _verify_installed_launcher(
            launcher_dir / "power", ["--version"], expected_version=expected_power
        )
        _verify_installed_launcher(
            launcher_dir / "power-mcp", ["--version"], expected_version=expected_power
        )

        retired_launchers: list[str] = []
        for name in retired_launcher_names:
            destination = launcher_dir / name
            if destination.exists() or destination.is_symlink():
                if not _is_managed_launcher(destination):
                    raise PermissionError(f"retired launcher is not POWER-managed: {destination}")
                destination.unlink()
                retired_launchers.append(str(destination))

        if legacy_venv.is_symlink():
            retired_legacy_link = os.readlink(legacy_venv)
            legacy_venv.unlink()

        receipt = {
            "schema": NATIVE_INSTALL_SCHEMA_VERSION,
            "status": "applied",
            "version": contract["version"],
            "commit": contract["commit"],
            "application_schema": contract["application_schema"],
            "manifest_sha256": contract["manifest_sha256"],
            "release_slot": str(release_slot),
            "venv": str(slot_venv),
            "current": str(current_link),
            "previous_release_slot": (
                str(previous_release_slot) if previous_release_slot is not None else None
            ),
            "legacy_venv": str(legacy_venv),
            "legacy_venv_preserved": legacy_venv.exists() and not legacy_venv.is_symlink(),
            "legacy_venv_link_retired": retired_legacy_link is not None,
            "launchers": [str(launcher_dir / name) for name in launcher_names],
            "retired_launchers": retired_launchers,
            "artifacts": plan["artifacts"],
            "profiles": contract["profiles"],
            "web": contract["web"],
            "no_deps": no_deps,
        }
        atomic_write(
            state_path, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        if not current_link.is_symlink() or current_link.resolve() != release_slot.resolve():
            raise RuntimeError("native POWER current-pointer readback is incomplete")
        if not all((launcher_dir / name).is_file() for name in launcher_names):
            raise RuntimeError("native POWER activation readback is incomplete")
        return receipt
    except Exception:
        if pointer_activated:
            if previous_current_target is None:
                current_link.unlink(missing_ok=True)
            else:
                _atomic_symlink(
                    previous_current_target,
                    current_link,
                    identifier=f"rollback-{activation_id}",
                )
        if retired_legacy_link is not None:
            legacy_venv.symlink_to(retired_legacy_link, target_is_directory=True)
        for destination, snapshot in launcher_snapshots.items():
            if snapshot is None:
                destination.unlink(missing_ok=True)
            elif snapshot[1] & stat.S_IFMT(stat.S_IFLNK):
                destination.unlink(missing_ok=True)
                destination.symlink_to(snapshot[0].decode("utf-8"), target_is_directory=False)
            else:
                content, mode = snapshot
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                destination.chmod(mode & 0o7777)
        if state_snapshot is None:
            state_path.unlink(missing_ok=True)
        else:
            state_path.write_bytes(state_snapshot)
        shutil.rmtree(release_slot, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(launcher_stage, ignore_errors=True)


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
