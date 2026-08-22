"""Content-addressed POWER Suite compatibility validation.

The native installer consumes this module before it creates or changes the
managed environment.  The manifest is deliberately small and facts-only: it
binds the two wheel identities, the application schema, the supported Python
range, the packaged Skill tree, and the tested dependency constraints.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

SUITE_MANIFEST_SCHEMA = "power.suite.manifest.v2"
LEGACY_SUITE_MANIFEST_SCHEMA = "power.suite.manifest.v1"
SUPPORTED_SUITE_MANIFEST_SCHEMAS = {
    LEGACY_SUITE_MANIFEST_SCHEMA,
    SUITE_MANIFEST_SCHEMA,
}
APPLICATION_SCHEMA = "power.application.v2"
_DIST_NAME_RE = re.compile(r"[^a-z0-9]+")
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:[-+].*)?$")
_SPECIFIER_RE = re.compile(r"^(>=|>|<=|<|==)\s*(\d+(?:\.\d+){1,2})$")


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of an exact artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_distribution(value: str) -> str:
    return _DIST_NAME_RE.sub("", value.lower())


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = _VERSION_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"unsupported version: {value}")
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 0),
    )


def _parse_specifiers(value: str) -> list[tuple[str, tuple[int, int, int]]]:
    clauses = [clause.strip() for clause in value.split(",") if clause.strip()]
    parsed: list[tuple[str, tuple[int, int, int]]] = []
    for clause in clauses:
        match = _SPECIFIER_RE.fullmatch(clause)
        if not match:
            raise ValueError(f"unsupported Python requirement: {value}")
        parsed.append((match.group(1), _version_tuple(match.group(2))))
    if not parsed:
        raise ValueError("Python requirement must not be empty")
    return parsed


def python_satisfies(version: tuple[int, int, int], requirement: str) -> bool:
    """Evaluate the small PEP 440 subset used by the release manifest."""
    for operator, bound in _parse_specifiers(requirement):
        if operator == ">=" and version < bound:
            return False
        if operator == ">" and version <= bound:
            return False
        if operator == "<=" and version > bound:
            return False
        if operator == "<" and version >= bound:
            return False
        if operator == "==" and version != bound:
            return False
    return True


def _normalise_requirement(value: str) -> tuple[str, ...]:
    return tuple(sorted(clause.strip() for clause in value.split(",") if clause.strip()))


def read_wheel_metadata(path: Path) -> dict[str, Any]:
    """Read wheel metadata without importing or installing the artifact."""
    with zipfile.ZipFile(path) as archive:
        metadata_names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_names) != 1:
            raise ValueError(f"wheel must contain exactly one METADATA file: {path.name}")
        raw = archive.read(metadata_names[0]).decode("utf-8")

    fields: dict[str, str] = {}
    requirements: list[str] = []
    for line in raw.splitlines():
        if line.startswith("Requires-Dist:"):
            requirements.append(line.split(":", 1)[1].strip())
        elif ":" in line:
            key, value = line.split(":", 1)
            if key in {"Name", "Version", "Requires-Python"}:
                fields[key] = value.strip()
    for required in ("Name", "Version"):
        if required not in fields:
            raise ValueError(f"wheel metadata is missing {required}: {path.name}")
    return {
        "name": fields["Name"],
        "version": fields["Version"],
        "requires_python": fields.get("Requires-Python"),
        "requires_dist": requirements,
    }


def load_manifest(path: Path) -> dict[str, Any]:
    """Load and minimally validate a JSON Suite manifest."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read Suite manifest: {path}") from exc
    if not isinstance(document, dict):
        raise ValueError("Suite manifest must be a JSON object")
    if document.get("schema") not in SUPPORTED_SUITE_MANIFEST_SCHEMAS:
        raise ValueError(f"unsupported Suite manifest schema: {document.get('schema')!r}")
    if document.get("status") not in {"candidate", "stable"}:
        raise ValueError("Suite manifest status must be candidate or stable")
    return document


def _component_manifest(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    component = manifest.get(name)
    if not isinstance(component, dict):
        raise ValueError(f"Suite manifest is missing {name} component")
    for field in ("distribution", "version", "filename", "sha256"):
        if not isinstance(component.get(field), str) or not component[field]:
            raise ValueError(f"Suite manifest {name}.{field} is required")
    if not re.fullmatch(r"[0-9a-f]{64}", component["sha256"]):
        raise ValueError(f"Suite manifest {name}.sha256 is invalid")
    return component


def _wheel_skill_tree_sha256(path: Path) -> str:
    """Hash the exact packaged POWER Skill tree from a candidate wheel."""
    prefix = "power_framework/data/skills/power/"
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not name.startswith(prefix) or name.endswith("/"):
                continue
            relative = name.removeprefix(prefix)
            relative_path = Path(relative)
            if "__pycache__" in relative_path.parts or relative_path.suffix == ".pyc":
                continue
            files[relative_path.as_posix()] = archive.read(name)
    if "SKILL.md" not in files:
        raise ValueError("POWER wheel is missing the packaged Skill tree")
    digest = hashlib.sha256()
    for relative in sorted(files):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(files[relative]).digest())
    return digest.hexdigest()


def validate_suite_artifacts(
    manifest_path: str | Path,
    power_wheel: str | Path,
    gui_wheel: str | Path | None,
    *,
    python_version: tuple[int, int, int] | None = None,
) -> dict[str, Any]:
    """Validate all immutable Suite inputs before installer mutation."""
    manifest_file = Path(manifest_path).expanduser().resolve()
    manifest = load_manifest(manifest_file)
    power_path = Path(power_wheel).expanduser().resolve()
    gui_path = Path(gui_wheel).expanduser().resolve() if gui_wheel else None
    errors: list[str] = []

    try:
        suite_version = manifest["suite_version"]
        _version_tuple(str(suite_version))
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"invalid suite_version: {exc}")
        suite_version = None

    application_schema = manifest.get("application_schema")
    if application_schema != APPLICATION_SCHEMA:
        errors.append(f"unsupported application schema: {application_schema!r}")

    try:
        python_requirement = str(manifest["python"]["requires_python"])
        _parse_specifiers(python_requirement)
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"invalid Python contract: {exc}")
        python_requirement = ""
    if python_requirement:
        current_python = python_version or sys.version_info[:3]
        if not python_satisfies(current_python, python_requirement):
            errors.append(
                f"Python {'.'.join(map(str, current_python))} is outside {python_requirement}"
            )

    components: dict[str, dict[str, Any]] = {}
    for name, artifact_path, required in (
        ("power", power_path, True),
        ("gui", gui_path, manifest.get("status") == "stable"),
    ):
        if artifact_path is None:
            if required:
                errors.append(f"{name} wheel is required by the Suite manifest")
            continue
        if not artifact_path.is_file() or artifact_path.suffix != ".whl":
            errors.append(f"{name} wheel is not an existing .whl: {artifact_path}")
            continue
        try:
            expected = _component_manifest(manifest, name)
            metadata = read_wheel_metadata(artifact_path)
            actual_hash = sha256_file(artifact_path)
            if artifact_path.name != expected["filename"]:
                errors.append(f"{name} filename does not match the manifest")
            if actual_hash != expected["sha256"]:
                errors.append(f"{name} wheel hash does not match the manifest")
            if _normalise_distribution(metadata["name"]) != _normalise_distribution(
                expected["distribution"]
            ):
                errors.append(f"{name} distribution name does not match the manifest")
            if metadata["version"] != expected["version"]:
                errors.append(f"{name} version does not match the manifest")
            expected_python = expected.get("requires_python")
            if (
                expected_python
                and metadata.get("requires_python")
                and _normalise_requirement(metadata["requires_python"])
                != _normalise_requirement(str(expected_python))
            ):
                errors.append(f"{name} Python requirement does not match the manifest")
            components[name] = {
                "path": str(artifact_path),
                "sha256": actual_hash,
                "metadata": metadata,
            }
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            errors.append(f"{name} wheel validation failed: {exc}")

    skill = manifest.get("skill")
    if not isinstance(skill, dict) or not re.fullmatch(
        r"[0-9a-f]{64}", str(skill.get("tree_sha256", ""))
    ):
        errors.append("Suite manifest skill.tree_sha256 is required")
    elif components.get("power", {}).get("metadata", {}).get("version") != skill.get(
        "compatible_power_version"
    ):
        errors.append("Skill/core version compatibility does not match the manifest")

    power_version = components.get("power", {}).get("metadata", {}).get("version")
    if (
        suite_version is not None
        and power_version is not None
        and str(suite_version) != power_version
    ):
        errors.append("Suite version does not match the POWER artifact")

    if manifest.get("schema") == SUITE_MANIFEST_SCHEMA:
        gui_manifest = manifest.get("gui")
        gui_metadata = components.get("gui", {}).get("metadata", {})
        if not isinstance(gui_manifest, dict):
            errors.append("Suite v2 manifest requires the GUI component")
        else:
            expected_power = gui_manifest.get("expected_power_version")
            if expected_power != power_version:
                errors.append("GUI expected POWER version does not match the POWER artifact")
            if gui_manifest.get("application_schema") != application_schema:
                errors.append("GUI application schema does not match the Suite schema")
            requires_power = gui_manifest.get("requires_power")
            if not isinstance(requires_power, str) or requires_power not in gui_metadata.get(
                "requires_dist", []
            ):
                errors.append("GUI wheel does not contain the manifest-bound POWER requirement")
            elif power_version not in requires_power:
                errors.append("GUI POWER requirement does not bind the exact POWER version")
        try:
            actual_skill_hash = _wheel_skill_tree_sha256(power_path)
            if isinstance(skill, dict) and actual_skill_hash != skill.get("tree_sha256"):
                errors.append("POWER wheel Skill tree hash does not match the manifest")
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            errors.append(f"POWER wheel Skill validation failed: {exc}")

    dependencies = manifest.get("dependencies")
    constraints_path: Path | None = None
    if not isinstance(dependencies, dict):
        errors.append("Suite manifest dependencies are required")
    else:
        constraints_name = dependencies.get("constraints")
        constraints_sha = dependencies.get("sha256")
        if not isinstance(constraints_name, str) or not constraints_name:
            errors.append("Suite manifest dependencies.constraints is required")
        if not isinstance(constraints_sha, str) or not re.fullmatch(
            r"[0-9a-f]{64}", constraints_sha
        ):
            errors.append("Suite manifest dependencies.sha256 is invalid")
        if isinstance(constraints_name, str):
            constraints_path = (manifest_file.parent / constraints_name).resolve()
            if not constraints_path.is_file():
                errors.append("Suite dependency constraints artifact is missing")
            elif (
                isinstance(constraints_sha, str)
                and sha256_file(constraints_path) != constraints_sha
            ):
                errors.append("Suite dependency constraints hash does not match the manifest")

    if errors:
        raise ValueError("; ".join(errors))
    return {
        "manifest_path": str(manifest_file),
        "manifest_sha256": sha256_file(manifest_file),
        "suite_version": suite_version,
        "application_schema": application_schema,
        "python": {"requires_python": python_requirement},
        "components": components,
        "skill": manifest["skill"],
        "dependencies": {
            "path": str(constraints_path) if constraints_path else None,
            "sha256": manifest["dependencies"]["sha256"],
        },
    }


__all__ = [
    "APPLICATION_SCHEMA",
    "SUITE_MANIFEST_SCHEMA",
    "load_manifest",
    "python_satisfies",
    "read_wheel_metadata",
    "sha256_file",
    "validate_suite_artifacts",
]
