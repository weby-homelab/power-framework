#!/usr/bin/env python3
"""Host-side P.O.W.E.R runtime version audit and update CLI.

Audits and updates P.O.W.E.R runtime virtual environments, MCP client configurations,
and Skill targets against the latest or specified public release.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# System Python paths that must NEVER be mutated or treated as project venvs
SYSTEM_PREFIXES = (
    "/",
    "/var",
    "/run",
    "/usr",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
    "/opt/local",
    "/etc",
    "/sys",
    "/proc",
    "/dev",
)

DEFAULT_REPO = "weby-homelab/power-framework"
DEFAULT_REF = "latest"
HOME = Path.home()
DEFAULT_VAULT = HOME / "brain"
DEFAULT_STATE_DIR = HOME / ".local" / "share" / "power" / "audit"
MAX_RELEASE_WHEEL_BYTES = 100 * 1024 * 1024
MAX_RELEASE_MANIFEST_BYTES = 10 * 1024 * 1024
MAX_RELEASE_METADATA_BYTES = 10 * 1024 * 1024
MAX_RELEASE_PYPROJECT_BYTES = 1 * 1024 * 1024

DEFAULT_VENV_ROOTS = [
    str(HOME / ".config" / "opencode"),
    str(HOME / ".local" / "share" / "power"),
    str(HOME / "projects"),
]

DEFAULT_SKILL_TARGETS = [
    str(HOME / ".agents" / "skills" / "power"),
    str(HOME / ".opencode" / "skills" / "power"),
    str(HOME / ".config" / "opencode" / "skills" / "power"),
    str(HOME / ".gemini" / "config" / "skills" / "power"),
    str(HOME / ".codex" / "skills" / "power"),
]

ALLOWED_SKILL_TARGET_ROOTS = [
    HOME / ".agents" / "skills",
    HOME / ".opencode" / "skills",
    HOME / ".config" / "opencode" / "skills",
    HOME / ".gemini" / "config" / "skills",
    HOME / ".gemini" / "skills",
    HOME / ".codex" / "skills",
    HOME / ".local" / "share" / "power" / "skills",
]

DEFAULT_MCP_CONFIGS = [
    str(HOME / ".config" / "opencode" / "opencode.jsonc"),
    str(HOME / ".gemini" / "config" / "mcp_config.json"),
    str(HOME / ".codex" / "config.toml"),
    str(HOME / ".codex" / "mcp.json"),
]

ALLOWED_SKILL_TOP_LEVEL_FILES = frozenset({"SKILL.md", "README.md"})
ALLOWED_SKILL_DIRECTORIES = frozenset({"references", "scripts", "templates", "assets"})
ALLOWED_SKILL_EXTENSIONS = frozenset(
    {
        ".md",
        ".txt",
        ".json",
        ".jsonc",
        ".yaml",
        ".yml",
        ".toml",
        ".py",
        ".sh",
        ".bash",
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".template",
        ".jinja",
        ".j2",
        ".csv",
    }
)

_SECRET_PATTERNS = [
    re.compile(r"(?i)(password|secret|token|apikey|api_key|auth|bearer)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"github_pat_[a-zA-Z0-9_]{82}"),
]


def redact_secrets(text: str) -> str:
    """Sanitize error messages and logs to prevent secret leakage."""
    if not text:
        return text
    sanitized = text
    for pat in _SECRET_PATTERNS:
        sanitized = pat.sub("[REDACTED]", sanitized)
    return sanitized


def is_safe_skill_relative_path(relative: str) -> bool:
    """Validate relative skill path against allowlist and safety rules."""
    if not relative or relative.startswith(("/", "\\")):
        return False
    rel_p = Path(relative)
    if rel_p.is_absolute() or ".." in rel_p.parts:
        return False

    for part in rel_p.parts:
        if part.startswith(".") or part == "__pycache__":
            return False
        if ":" in part or "\0" in part:
            return False

    parts = rel_p.parts
    if len(parts) == 1:
        return parts[0] in ALLOWED_SKILL_TOP_LEVEL_FILES

    top_dir = parts[0]
    if top_dir not in ALLOWED_SKILL_DIRECTORIES:
        return False

    suffix = rel_p.suffix.lower()
    return suffix in ALLOWED_SKILL_EXTENSIONS


class ReleaseValidationError(ValueError):
    """Raised when release payload or artifacts violate integrity contracts."""


class ProcessLock:
    """Acquires a non-blocking exclusive file lock to prevent concurrent runs."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self._fd: int | None = None

    def __enter__(self) -> ProcessLock:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            os.close(self._fd)
            self._fd = None
            raise RuntimeError("Another audit/update process is currently running") from exc
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._fd is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None


@dataclass(frozen=True)
class ReleasePayload:
    """Validated published release contract and artifacts."""

    tag: str
    version: str
    pyproject_version: str
    commit: str | None = None
    wheel_filename: str | None = None
    wheel_sha256: str | None = None
    wheel_path: Path | None = None
    wheel_url: str | None = None
    skill_tree_sha256: str | None = None
    skill_files: dict[str, bytes] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "version": self.version,
            "pyproject_version": self.pyproject_version,
            "commit": self.commit,
            "wheel_filename": self.wheel_filename,
            "wheel_sha256": self.wheel_sha256,
            "wheel_path": str(self.wheel_path) if self.wheel_path else None,
            "wheel_url": self.wheel_url,
            "skill_tree_sha256": self.skill_tree_sha256,
            "skill_files_count": len(self.skill_files),
        }


@dataclass
class VenvAuditResult:
    """Audit result for a single bounded virtual environment."""

    path: str
    python_path: str
    installed_version: str | None
    is_writable: bool
    status: str  # "up_to_date", "outdated", "not_installed", "newer", "unwritable", "broken_venv"
    action_taken: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class MCPAuditResult:
    """Audit result for an MCP client configuration."""

    client: str
    config_path: str
    config_format: str  # "json", "jsonc", "toml"
    status: str  # "canonical", "outdated", "missing_runtime", "mismatch", "missing_entry", "manual_review", "missing_file"
    entry_present: bool = False
    executable: str | None = None
    resolved_executable: str | None = None
    runtime_python: str | None = None
    installed_version: str | None = None
    env_keys: list[str] = field(default_factory=list)  # NEVER store secret values
    has_comments: bool = False
    action_taken: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class SkillAuditResult:
    """Audit result for a managed Skill target."""

    target_path: str
    installed_version: str | None
    tree_sha256: str | None
    status: str  # "up_to_date", "upgrade_ready", "ready", "manual_review", "missing"
    file_count: int = 0
    action_taken: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class AuditReport:
    """Complete host-side runtime audit report."""

    timestamp: str
    release: dict[str, Any]
    venvs: list[VenvAuditResult]
    mcp_configs: list[MCPAuditResult]
    skills: list[SkillAuditResult]
    applied: bool
    recorded: bool
    has_drift: bool
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "release": self.release,
            "has_drift": self.has_drift,
            "applied": self.applied,
            "recorded": self.recorded,
            "errors": self.errors,
            "venvs": [v.as_dict() for v in self.venvs],
            "mcp_configs": [m.as_dict() for m in self.mcp_configs],
            "skills": [s.as_dict() for s in self.skills],
        }


# ============================================================================
# Version Parsing and Lexical Tree Hashing
# ============================================================================

_VERSION_RE = re.compile(
    r"""
    ^\s*[vV]?
    (?P<release>\d+(?:\.\d+)*)
    (?:
        (?:[-._]?)(?P<pre_type>a|alpha|b|beta|rc|c|pre|preview|dev)(?:[-._]?(?P<pre_num>\d+))?
    )?
    (?:
        (?:[-._]?)(?P<post_type>post|r|rev)(?:[-._]?(?P<post_num>\d+))?
    )?
    (?:\+[a-zA-Z0-9._-]+)?
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)

PRE_MAP = {
    "dev": -4,
    "a": -3,
    "alpha": -3,
    "b": -2,
    "beta": -2,
    "c": -1,
    "rc": -1,
    "pre": -1,
    "preview": -1,
}


def parse_version(version_str: str) -> tuple[tuple[int, ...], int, int, int]:
    """Parse a semantic or PEP 440 version string into a comparable tuple.

    Returns ((major, minor, patch, ...), pre_phase, pre_num, post_num)
    where pre_phase is:
      -4: dev
      -3: alpha (a)
      -2: beta (b)
      -1: rc / c / pre / preview
       0: stable
       1: post / r / rev
    """
    m = _VERSION_RE.match(version_str.strip())
    if not m:
        nums = re.findall(r"\d+", version_str)
        if nums:
            return (tuple(int(n) for n in nums), 0, 0, 0)
        return ((0,), 0, 0, 0)

    release_str = m.group("release")
    release_tuple = tuple(int(n) for n in release_str.split("."))

    pre_type = m.group("pre_type")
    post_type = m.group("post_type")

    pre_phase = 0
    pre_num = 0
    post_num = 0

    if pre_type:
        pre_phase = PRE_MAP.get(pre_type.lower(), -1)
        pre_num = int(m.group("pre_num") or 0)

    if post_type:
        pre_phase = 1
        post_num = int(m.group("post_num") or 0)

    return (release_tuple, pre_phase, pre_num, post_num)


def compare_versions(v1: str, v2: str) -> int:
    """Compare two version strings. Returns -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2."""
    base1, phase1, pre1, post1 = parse_version(v1)
    base2, phase2, pre2, post2 = parse_version(v2)
    max_len = max(len(base1), len(base2))
    base1_padded = base1 + (0,) * (max_len - len(base1))
    base2_padded = base2 + (0,) * (max_len - len(base2))

    k1 = (base1_padded, phase1, pre1, post1)
    k2 = (base2_padded, phase2, pre2, post2)
    if k1 < k2:
        return -1
    if k1 > k2:
        return 1
    return 0


def aggregate_tree_hash(files: dict[str, bytes]) -> str:
    """Hash paths and bytes in deterministic lexical order matching POWER contract."""
    digest = hashlib.sha256()
    for relative in sorted(files):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(files[relative]).digest())
    return digest.hexdigest()


def tree_from_directory(root: Path) -> dict[str, bytes]:
    """Read a target directory using relative POSIX paths without bytecode/symlinks."""
    if not root.is_dir() or root.is_symlink():
        return {}
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if (
            path.is_file()
            and not path.is_symlink()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
        ):
            try:
                rel = path.relative_to(root).as_posix()
                if is_safe_skill_relative_path(rel):
                    files[rel] = path.read_bytes()
            except (OSError, ValueError):
                continue
    return files


def sha256_file(path: Path) -> str:
    """Compute SHA-256 digest of a regular file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ============================================================================
# Release Payload Fetching and Validation
# ============================================================================


def _extract_wheel_skill_tree(wheel_path: Path) -> dict[str, bytes]:
    """Extract packaged skill tree from a unified wheel with allowlist & traversal protection."""
    prefix = "power_framework/data/skills/power/"
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(wheel_path) as archive:
        for name in archive.namelist():
            if not name.startswith(prefix) or name.endswith("/"):
                continue
            relative = name[len(prefix) :]
            if not relative or "__pycache__" in relative or relative.endswith(".pyc"):
                continue
            if not is_safe_skill_relative_path(relative):
                raise ReleaseValidationError(f"Unsafe or disallowed path in wheel archive: {name}")
            files[relative] = archive.read(name)
    return files


def _read_pyproject_version_from_text(content: str) -> str:
    """Extract project.version from pyproject.toml text using tomllib."""
    try:
        data = tomllib.loads(content)
    except Exception as exc:
        raise ReleaseValidationError(f"Invalid pyproject.toml TOML: {exc}") from exc

    if not isinstance(data, dict):
        raise ReleaseValidationError("pyproject.toml root is not a table")

    project = data.get("project")
    if isinstance(project, dict) and "version" in project:
        ver = str(project["version"]).strip()
        if ver:
            return ver

    tool = data.get("tool", {})
    if isinstance(tool, dict):
        poetry = tool.get("poetry", {})
        if isinstance(poetry, dict) and "version" in poetry:
            ver = str(poetry["version"]).strip()
            if ver:
                return ver

    raise ReleaseValidationError("pyproject.toml is missing project.version")


def download_and_verify_wheel(
    wheel_url: str,
    expected_sha256: str,
    dest_dir: Path,
) -> Path:
    """Download wheel from URL and verify its SHA-256 digest."""
    if not expected_sha256:
        raise ReleaseValidationError("Cannot download wheel without verified expected SHA-256")
    parsed_url = urllib.parse.urlsplit(wheel_url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.netloc != "github.com"
        or not parsed_url.path.startswith("/")
        or "/releases/download/" not in parsed_url.path
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise ReleaseValidationError("Release wheel URL must be a canonical GitHub release URL")

    headers = {"User-Agent": "power-runtime-audit/1.0"}
    req = urllib.request.Request(wheel_url, headers=headers)
    fd, tmp_file = tempfile.mkstemp(prefix="power_wheel_", suffix=".whl", dir=dest_dir)
    try:
        with os.fdopen(fd, "wb") as handle, urllib.request.urlopen(req, timeout=60) as resp:
            content_length = getattr(resp, "headers", {}).get("Content-Length")
            if (
                isinstance(content_length, str)
                and content_length.isdigit()
                and int(content_length) > MAX_RELEASE_WHEEL_BYTES
            ):
                raise ReleaseValidationError("Release wheel exceeds the maximum download size")
            total = 0
            while chunk := resp.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_RELEASE_WHEEL_BYTES:
                    raise ReleaseValidationError("Release wheel exceeds the maximum download size")
                handle.write(chunk)
        actual_sha256 = sha256_file(Path(tmp_file))
        if actual_sha256.lower() != expected_sha256.lower():
            raise ReleaseValidationError(
                f"Downloaded wheel SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
            )
        return Path(tmp_file)
    except Exception:
        if os.path.exists(tmp_file):
            with contextlib.suppress(OSError):
                os.unlink(tmp_file)
        raise


def fetch_release_payload(
    repo: str = DEFAULT_REPO,
    ref: str = DEFAULT_REF,
    source_dir: Path | None = None,
) -> ReleasePayload:
    """Fetch and validate release metadata and artifacts, failing closed on mismatch."""
    if source_dir is not None:
        return _fetch_from_local_source(source_dir, ref)

    return _fetch_from_github(repo, ref)


def _fetch_from_local_source(source_dir: Path, ref: str) -> ReleasePayload:
    """Load release metadata and artifacts from a local directory or repository checkout."""
    source_root = Path(source_dir).expanduser().resolve()
    pyproject_file = source_root / "pyproject.toml"
    if not pyproject_file.is_file():
        raise ReleaseValidationError(f"pyproject.toml not found in {source_root}")

    pyproject_ver = _read_pyproject_version_from_text(pyproject_file.read_text(encoding="utf-8"))
    tag = ref if ref != "latest" else f"v{pyproject_ver}"
    expected_ver = tag.lstrip("v")

    if ref == "latest":
        _, pre_phase, _, _ = parse_version(pyproject_ver)
        if pre_phase < 0:
            raise ReleaseValidationError(
                f"Local source version '{pyproject_ver}' is not a stable release (prerelease)"
            )

    if pyproject_ver != expected_ver:
        raise ReleaseValidationError(
            f"Release tag {tag} version ({expected_ver}) mismatch with "
            f"pyproject version ({pyproject_ver})"
        )

    # Check for release manifest
    manifest_file = source_root / "release" / "power-release-manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_file.is_file():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ReleaseValidationError(f"Invalid release manifest JSON: {exc}") from exc
        if not isinstance(manifest, dict):
            raise ReleaseValidationError("Release manifest root is not an object")
        manifest_schema = manifest.get("schema")
        if manifest_schema == "power.release.manifest.template.v1":
            if manifest.get("authority") != "candidate-only":
                raise ReleaseValidationError(
                    "source release manifest template must declare authority=candidate-only"
                )
            template_version = manifest.get("version")
            if template_version not in {None, expected_ver}:
                raise ReleaseValidationError(
                    f"Source manifest template version {template_version} does not match {expected_ver}"
                )
            # A source template is not release evidence.  Final package/image
            # identities are read only from a published release asset.
            manifest = {}
        elif manifest_schema != "power.release.manifest.v1":
            raise ReleaseValidationError(f"Unsupported release manifest schema: {manifest_schema}")
        if manifest and manifest.get("version") != expected_ver:
            raise ReleaseValidationError(
                f"Manifest version {manifest.get('version')} does not match {expected_ver}"
            )

    # Locate wheel
    manifest_wheel_filename: str | None = None
    manifest_wheel_sha256: str | None = None

    if manifest and "artifacts" in manifest and isinstance(manifest["artifacts"], dict):
        wheel_meta = manifest["artifacts"].get("power_wheel")
        if isinstance(wheel_meta, dict):
            manifest_wheel_filename = wheel_meta.get("filename")
            manifest_wheel_sha256 = wheel_meta.get("sha256")
            if manifest_wheel_sha256 and (
                len(manifest_wheel_sha256) != 64
                or not re.fullmatch(r"[0-9a-fA-F]{64}", manifest_wheel_sha256)
            ):
                raise ReleaseValidationError(
                    f"Invalid wheel SHA-256 in manifest: {manifest_wheel_sha256}"
                )

    expected_wheel_prefix = f"power_framework-{expected_ver}"
    if manifest_wheel_filename and not manifest_wheel_filename.startswith(expected_wheel_prefix):
        raise ReleaseValidationError(
            f"Manifest wheel filename '{manifest_wheel_filename}' does not match version '{expected_ver}'"
        )

    # Search for wheel in dist or source_root
    dist_dir = source_root / "dist"
    candidates: list[Path] = []
    if dist_dir.is_dir():
        candidates.extend(sorted(dist_dir.glob(f"power_framework-{expected_ver}*.whl")))
    candidates.extend(sorted(source_root.glob(f"power_framework-{expected_ver}*.whl")))

    wheel_filename: str | None = manifest_wheel_filename
    wheel_sha256: str | None = manifest_wheel_sha256
    wheel_path: Path | None = None

    if candidates:
        wheel_path = candidates[0]
        if manifest_wheel_filename and wheel_path.name != manifest_wheel_filename:
            raise ReleaseValidationError(
                f"Local wheel filename '{wheel_path.name}' does not match manifest '{manifest_wheel_filename}'"
            )
        actual_sha256 = sha256_file(wheel_path)
        if wheel_sha256 and actual_sha256.lower() != wheel_sha256.lower():
            raise ReleaseValidationError(
                f"Wheel digest mismatch for {wheel_path.name}: "
                f"expected {wheel_sha256}, got {actual_sha256}"
            )
        wheel_sha256 = actual_sha256
        wheel_filename = wheel_path.name

    # Extract or locate skill tree: check .agents/skills/power first, then skills/power, then wheel
    skill_files: dict[str, bytes] = {}
    agents_skill_dir = source_root / ".agents" / "skills" / "power"
    standard_skill_dir = source_root / "skills" / "power"

    if agents_skill_dir.is_dir():
        skill_files = tree_from_directory(agents_skill_dir)
    elif standard_skill_dir.is_dir():
        skill_files = tree_from_directory(standard_skill_dir)
    elif wheel_path is not None:
        skill_files = _extract_wheel_skill_tree(wheel_path)

    computed_skill_hash = aggregate_tree_hash(skill_files) if skill_files else None
    expected_skill_hash = manifest.get("skill_tree_sha256") if manifest else None

    # If wheel is present, validate wheel skill contents against manifest or computed
    if wheel_path is not None and expected_skill_hash:
        wheel_skills = _extract_wheel_skill_tree(wheel_path)
        if wheel_skills:
            w_hash = aggregate_tree_hash(wheel_skills)
            if w_hash != expected_skill_hash:
                raise ReleaseValidationError(
                    f"Wheel Skill tree hash mismatch: expected {expected_skill_hash}, got {w_hash}"
                )

    effective_skill_hash = computed_skill_hash or expected_skill_hash

    return ReleasePayload(
        tag=tag,
        version=expected_ver,
        pyproject_version=pyproject_ver,
        commit=manifest.get("commit"),
        wheel_filename=wheel_filename,
        wheel_sha256=wheel_sha256,
        wheel_path=wheel_path,
        skill_tree_sha256=effective_skill_hash,
        skill_files=skill_files,
        manifest=manifest,
    )


def _fetch_from_github(repo: str, ref: str) -> ReleasePayload:
    """Fetch release information from public GitHub repository, failing closed if unresolved."""
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) is None:
        raise ReleaseValidationError("GitHub repository must use owner/name syntax")
    if ref != "latest" and re.fullmatch(r"v\d+\.\d+\.\d+", ref) is None:
        raise ReleaseValidationError("GitHub release ref must be latest or a stable v<version> tag")
    headers = {"User-Agent": "power-runtime-audit/1.0", "Accept": "application/json"}

    api_url = (
        f"https://api.github.com/repos/{repo}/releases/latest"
        if ref == "latest"
        else f"https://api.github.com/repos/{repo}/releases/tags/{ref}"
    )

    release_data: dict[str, Any] = {}
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            release_bytes = resp.read(MAX_RELEASE_METADATA_BYTES + 1)
        if len(release_bytes) > MAX_RELEASE_METADATA_BYTES:
            raise ReleaseValidationError("GitHub release metadata exceeds the maximum size")
        release_data = json.loads(release_bytes.decode("utf-8"))
    except Exception as exc:
        raise ReleaseValidationError(
            f"Could not resolve release '{ref}' from GitHub API for {repo}: {exc}"
        ) from exc

    if not isinstance(release_data, dict) or not release_data.get("tag_name"):
        raise ReleaseValidationError(
            f"GitHub API for {repo}@{ref} did not return a valid release with tag_name"
        )

    tag_name = str(release_data["tag_name"]).strip()
    if re.fullmatch(r"v\d+\.\d+\.\d+(?:(?:a|b|rc|dev)\d+)?", tag_name) is None:
        raise ReleaseValidationError(f"Release tag '{tag_name}' is not a valid version tag")
    if ref != "latest" and tag_name != ref:
        raise ReleaseValidationError(f"Requested release ref {ref} resolved to {tag_name}")
    expected_ver = tag_name.lstrip("v")
    if not expected_ver or tag_name != f"v{expected_ver}":
        raise ReleaseValidationError(
            f"Release tag '{tag_name}' does not match expected format 'v<version>'"
        )

    if ref == "latest":
        if release_data.get("draft") is True:
            raise ReleaseValidationError(f"Latest release '{tag_name}' is a draft release")
        if release_data.get("prerelease") is True:
            raise ReleaseValidationError(f"Latest release '{tag_name}' is a prerelease")
        _, pre_phase, _, _ = parse_version(expected_ver)
        if pre_phase < 0:
            raise ReleaseValidationError(
                f"Latest release '{tag_name}' is not a stable release ({expected_ver})"
            )

    # 2. Fetch raw pyproject.toml to validate version
    raw_pyproject_url = f"https://raw.githubusercontent.com/{repo}/{tag_name}/pyproject.toml"
    try:
        req = urllib.request.Request(raw_pyproject_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            pyproject_bytes = resp.read(MAX_RELEASE_PYPROJECT_BYTES + 1)
        if len(pyproject_bytes) > MAX_RELEASE_PYPROJECT_BYTES:
            raise ReleaseValidationError("Release pyproject.toml exceeds the maximum size")
        pyproject_content = pyproject_bytes.decode("utf-8")
    except Exception as exc:
        raise ReleaseValidationError(
            f"Failed to fetch pyproject.toml for {repo}@{tag_name}: {exc}"
        ) from exc

    pyproject_ver = _read_pyproject_version_from_text(pyproject_content)
    if pyproject_ver != expected_ver:
        raise ReleaseValidationError(
            f"Release tag {tag_name} does not match pyproject.toml version {pyproject_ver}"
        )

    release_assets = release_data.get("assets")
    if not isinstance(release_assets, list):
        raise ReleaseValidationError("GitHub release assets must be a list")

    # 3. Fetch the authoritative manifest from the published release asset.
    manifest_assets = [
        asset
        for asset in release_assets
        if isinstance(asset, dict) and asset.get("name") == "power-release-manifest.json"
    ]
    if len(manifest_assets) != 1:
        raise ReleaseValidationError(
            "GitHub release must contain exactly one published power-release-manifest.json asset"
        )
    raw_manifest_digest = manifest_assets[0].get("digest")
    manifest_digest = str(raw_manifest_digest or "").strip().removeprefix("sha256:").lower()
    if len(manifest_digest) != 64 or not re.fullmatch(r"[0-9a-f]{64}", manifest_digest):
        raise ReleaseValidationError("published release manifest is missing a valid API SHA-256")
    manifest_url = (
        f"https://github.com/{repo}/releases/download/{tag_name}/power-release-manifest.json"
    )
    try:
        req = urllib.request.Request(
            manifest_url,
            headers={**headers, "Accept": "application/octet-stream"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            manifest_bytes = resp.read(MAX_RELEASE_MANIFEST_BYTES + 1)
        if len(manifest_bytes) > MAX_RELEASE_MANIFEST_BYTES:
            raise ReleaseValidationError("Published release manifest exceeds the maximum size")
        if hashlib.sha256(manifest_bytes).hexdigest() != manifest_digest:
            raise ReleaseValidationError(
                "published release manifest bytes do not match the GitHub asset digest"
            )
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except ReleaseValidationError:
        raise
    except Exception as exc:
        raise ReleaseValidationError(
            f"Failed to fetch authoritative published release manifest: {exc}"
        ) from exc

    if not isinstance(manifest, dict):
        raise ReleaseValidationError("Release manifest root is not an object")
    if manifest.get("schema") != "power.release.manifest.v1":
        raise ReleaseValidationError(
            f"Unsupported release manifest schema: {manifest.get('schema')}"
        )
    if manifest.get("version") != expected_ver:
        raise ReleaseValidationError(
            f"Manifest version {manifest.get('version')} does not match {expected_ver}"
        )
    if re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("commit", ""))) is None:
        raise ReleaseValidationError("Published release manifest commit is invalid")

    manifest_wheel_filename: str | None = None
    manifest_wheel_sha256: str | None = None

    if manifest and "artifacts" in manifest and isinstance(manifest["artifacts"], dict):
        wheel_meta = manifest["artifacts"].get("power_wheel")
        if isinstance(wheel_meta, dict):
            manifest_wheel_filename = wheel_meta.get("filename")
            manifest_wheel_sha256 = wheel_meta.get("sha256")
            if manifest_wheel_sha256:
                manifest_wheel_sha256 = str(manifest_wheel_sha256).strip()
                if len(manifest_wheel_sha256) != 64 or not re.fullmatch(
                    r"[0-9a-fA-F]{64}", manifest_wheel_sha256
                ):
                    raise ReleaseValidationError(
                        f"Invalid wheel SHA-256 in manifest: {manifest_wheel_sha256}"
                    )
                manifest_wheel_sha256 = manifest_wheel_sha256.lower()

    expected_wheel_prefix = f"power_framework-{expected_ver}"
    if manifest_wheel_filename and not manifest_wheel_filename.startswith(expected_wheel_prefix):
        raise ReleaseValidationError(
            f"Manifest wheel filename '{manifest_wheel_filename}' does not match version '{expected_ver}'"
        )

    # Check assets in release_data
    asset_wheel_name: str | None = None
    asset_wheel_url: str | None = None
    asset_wheel_digest: str | None = None
    for asset in release_assets:
        name = asset.get("name", "")
        if name.endswith(".whl"):
            if not isinstance(name, str) or name != Path(name).name or "\\" in name:
                raise ReleaseValidationError("Wheel asset name is not a safe filename")
            asset_wheel_name = name
            expected_wheel_url = (
                f"https://github.com/{repo}/releases/download/{tag_name}/{asset_wheel_name}"
            )
            if asset.get("browser_download_url") != expected_wheel_url:
                raise ReleaseValidationError(
                    "Wheel asset URL is not the canonical GitHub release URL"
                )
            asset_wheel_url = expected_wheel_url
            raw_digest = asset.get("digest")
            if raw_digest is not None:
                norm_digest = str(raw_digest).strip()
                if norm_digest.lower().startswith("sha256:"):
                    norm_digest = norm_digest[7:].strip()
                if norm_digest:
                    if len(norm_digest) != 64 or not re.fullmatch(r"[0-9a-fA-F]{64}", norm_digest):
                        raise ReleaseValidationError(
                            f"Invalid wheel SHA-256 digest in asset: {raw_digest}"
                        )
                    asset_wheel_digest = norm_digest.lower()
            break

    if asset_wheel_name and not asset_wheel_name.startswith(expected_wheel_prefix):
        raise ReleaseValidationError(
            f"Wheel asset name '{asset_wheel_name}' does not match expected version '{expected_ver}'"
        )

    if manifest_wheel_filename and asset_wheel_name and manifest_wheel_filename != asset_wheel_name:
        raise ReleaseValidationError(
            f"Release asset wheel '{asset_wheel_name}' does not match manifest wheel '{manifest_wheel_filename}'"
        )

    if manifest_wheel_sha256 and asset_wheel_digest and manifest_wheel_sha256 != asset_wheel_digest:
        raise ReleaseValidationError(
            f"Release asset wheel digest '{asset_wheel_digest}' does not match manifest wheel SHA-256 '{manifest_wheel_sha256}'"
        )

    wheel_filename = asset_wheel_name or manifest_wheel_filename
    wheel_sha256 = manifest_wheel_sha256 or asset_wheel_digest
    wheel_url = asset_wheel_url

    expected_skill_hash = manifest.get("skill_tree_sha256") if manifest else None

    return ReleasePayload(
        tag=tag_name,
        version=pyproject_ver,
        pyproject_version=pyproject_ver,
        commit=manifest.get("commit") or release_data.get("target_commitish"),
        wheel_filename=wheel_filename,
        wheel_sha256=wheel_sha256,
        wheel_url=wheel_url,
        skill_tree_sha256=expected_skill_hash,
        manifest=manifest,
    )


# ============================================================================
# Bounded Python Virtual Environments Discovery and Audit
# ============================================================================


def is_system_prefix(path: Path) -> bool:
    """Return True if path resolves inside system python / root library locations."""
    try:
        resolved_str = str(path.resolve())
    except OSError:
        resolved_str = str(path)
    return any(
        resolved_str == prefix or (prefix != "/" and resolved_str.startswith(f"{prefix}/"))
        for prefix in SYSTEM_PREFIXES
    )


def is_python_interpreter(path: Path | str) -> bool:
    """Return True if path/name represents a valid Python interpreter binary."""
    p = Path(path)
    name = p.name.lower()
    if not name:
        return False
    if name in {
        "sh",
        "bash",
        "dash",
        "zsh",
        "ksh",
        "csh",
        "tcsh",
        "fish",
        "busybox",
        "env",
        "node",
        "perl",
        "ruby",
    }:
        return False
    return bool(
        re.match(r"^(?:python|pypy)(?:\d+(?:\.\d+)*)?(?:t)?(?:\.exe)?$", name, re.IGNORECASE)
    )


def find_venv_python(venv_dir: Path) -> Path | None:
    """Find python executable in virtualenv (bin/python, bin/python3, Scripts/python.exe)."""
    if is_system_prefix(venv_dir):
        return None
    for candidate_rel in (
        "bin/python",
        "bin/python3",
        "Scripts/python.exe",
        "Scripts/python",
    ):
        candidate = venv_dir / candidate_rel
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
        if candidate.is_file():
            return candidate
    return None


def find_venv_pip(venv_dir: Path) -> list[str] | None:
    """Find pip invocation for virtualenv (bin/pip, bin/pip3, or python -m pip)."""
    if is_system_prefix(venv_dir):
        return None
    for candidate_rel in (
        "bin/pip",
        "bin/pip3",
        "Scripts/pip.exe",
        "Scripts/pip",
    ):
        candidate = venv_dir / candidate_rel
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return [str(candidate)]
        if candidate.is_file():
            return [str(candidate)]

    py = find_venv_python(venv_dir)
    if py is not None:
        return [str(py), "-m", "pip"]
    return None


def discover_bounded_venvs(roots: list[str | Path]) -> list[Path]:
    """Discover real Python virtual environments within explicitly bounded search roots."""
    discovered: set[Path] = set()

    for root_item in roots:
        root_path = Path(root_item).expanduser()
        if not root_path.exists():
            continue

        # Reject scanning filesystem root or system prefixes directly
        if is_system_prefix(root_path):
            continue

        # Check if root_path itself is a venv
        if (
            (root_path / "pyvenv.cfg").is_file()
            and not is_system_prefix(root_path)
            and find_venv_python(root_path) is not None
        ):
            discovered.add(root_path.resolve())

        # Check current symlink if under managed path
        current_link = root_path / "current" / "venv"
        if current_link.is_dir():
            target_venv = current_link.resolve()
            if not is_system_prefix(target_venv) and find_venv_python(target_venv) is not None:
                discovered.add(target_venv)

        # Recursively search for pyvenv.cfg (bounded)
        try:
            for cfg in root_path.glob("**/pyvenv.cfg"):
                venv_dir = cfg.parent
                if is_system_prefix(venv_dir):
                    continue
                if find_venv_python(venv_dir) is not None:
                    discovered.add(venv_dir.resolve())
        except (PermissionError, OSError):
            continue

    return sorted(discovered)


def get_venv_power_framework_version(venv_dir: Path) -> str | None:
    """Determine installed power-framework version from dist-info metadata or interpreter."""
    if is_system_prefix(venv_dir):
        return None
    if not venv_dir.exists():
        return None

    lib_dir = venv_dir / "lib"
    if lib_dir.is_dir():
        for dist_info in lib_dir.glob("python*/site-packages/power_framework-*.dist-info"):
            metadata_file = dist_info / "METADATA"
            if metadata_file.is_file():
                try:
                    text = metadata_file.read_text(encoding="utf-8", errors="ignore")
                    match = re.search(r"(?m)^Version:\s*([^\s]+)", text)
                    if match:
                        return match.group(1).strip()
                except OSError:
                    continue

    # Check all site-packages under venv
    for dist_info in venv_dir.glob("**/power_framework-*.dist-info"):
        metadata_file = dist_info / "METADATA"
        if metadata_file.is_file():
            try:
                text = metadata_file.read_text(encoding="utf-8", errors="ignore")
                match = re.search(r"(?m)^Version:\s*([^\s]+)", text)
                if match:
                    return match.group(1).strip()
            except OSError:
                continue

    # Fallback to executing python in venv with short timeout
    python_bin = find_venv_python(venv_dir)
    if python_bin is not None and python_bin.is_file():
        try:
            res = subprocess.run(  # noqa: S603
                [
                    str(python_bin),
                    "-c",
                    "import importlib.metadata as m; print(m.version('power-framework'))",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except (subprocess.SubprocessError, OSError):
            return None

    return None


def audit_venv(venv_dir: Path, target_version: str) -> VenvAuditResult:
    """Audit one virtual environment for power-framework presence, version, and writability."""
    python_bin = find_venv_python(venv_dir)
    python_path = str(python_bin) if python_bin else str(venv_dir / "bin" / "python")

    if is_system_prefix(venv_dir):
        return VenvAuditResult(
            path=str(venv_dir),
            python_path=python_path,
            installed_version=None,
            is_writable=False,
            status="unwritable",
            error="System Python installations cannot be audited or mutated as virtualenvs",
        )

    if python_bin is None:
        return VenvAuditResult(
            path=str(venv_dir),
            python_path=python_path,
            installed_version=None,
            is_writable=False,
            status="broken_venv",
            error="Virtual environment lacks valid python binary",
        )

    installed_ver = get_venv_power_framework_version(venv_dir)
    is_writable = os.access(venv_dir, os.W_OK) and (
        not (venv_dir / "bin").exists() or os.access(venv_dir / "bin", os.W_OK)
    )

    if installed_ver is None:
        status = "not_installed"
    else:
        cmp = compare_versions(installed_ver, target_version)
        if cmp == 0:
            status = "up_to_date"
        elif cmp < 0:
            status = "outdated" if is_writable else "unwritable"
        else:
            status = "newer"

    return VenvAuditResult(
        path=str(venv_dir),
        python_path=python_path,
        installed_version=installed_ver,
        is_writable=is_writable,
        status=status,
    )


def apply_venv_update(
    audit: VenvAuditResult,
    release: ReleasePayload,
    dry_run: bool = True,
) -> tuple[str, str | None]:
    """Update an outdated virtual environment to the target release using a verified wheel."""
    if audit.status != "outdated":
        return "skipped", None

    if not audit.is_writable:
        return "unwritable", "Virtual environment is not writable"

    venv_dir = Path(audit.path)
    if is_system_prefix(venv_dir):
        return "unwritable", "Refusing to mutate system Python prefix"

    pip_cmd = find_venv_pip(venv_dir)
    if pip_cmd is None:
        return "failed", "No pip or python binary found in virtual environment"

    if dry_run:
        return "planned_update", None

    # Prohibit installation without a verified wheel
    wheel_path = release.wheel_path
    if wheel_path is None or not wheel_path.is_file():
        return (
            "failed",
            "No verified local release wheel available; installation from unverified PyPI is prohibited",
        )

    if release.wheel_sha256:
        actual_sha = sha256_file(wheel_path)
        if actual_sha.lower() != release.wheel_sha256.lower():
            return (
                "failed",
                f"Wheel digest mismatch: expected {release.wheel_sha256}, got {actual_sha}",
            )

    cmd = [*pip_cmd, "install", "--upgrade", "--no-deps", "--no-input", str(wheel_path)]

    try:
        res = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if res.returncode != 0:
            return "failed", redact_secrets(f"pip install failed: {res.stderr.strip()}")

        new_ver = get_venv_power_framework_version(venv_dir)
        if new_ver != release.version:
            return (
                "failed",
                f"Post-install version check failed: got {new_ver}, expected {release.version}",
            )

        return "updated", None
    except Exception as exc:
        return "failed", redact_secrets(str(exc))


# ============================================================================
# POWER MCP Client Config Inspection and Audit
# ============================================================================


def has_jsonc_comments(content: str) -> bool:
    """Check if JSON/JSONC text contains comments outside of string literals using a tokenizer."""
    in_string = False
    escape = False
    i = 0
    n = len(content)
    while i < n:
        char = content[i]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            i += 1
            continue

        if char == '"':
            in_string = True
            i += 1
            continue

        if char == "/" and i + 1 < n:
            next_char = content[i + 1]
            if next_char in ("/", "*"):
                return True

        i += 1

    return False


def strip_jsonc_comments(content: str) -> str:
    """Strip single-line and multi-line comments from JSONC text for in-memory parsing.

    Preserves string literals, escapes, and structure without mutating files on disk.
    """
    result: list[str] = []
    in_string = False
    escape = False
    i = 0
    n = len(content)
    while i < n:
        char = content[i]
        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            i += 1
            continue

        if char == '"':
            in_string = True
            result.append(char)
            i += 1
            continue

        if char == "/" and i + 1 < n:
            next_char = content[i + 1]
            if next_char == "/":
                i += 2
                while i < n and content[i] not in ("\r", "\n"):
                    i += 1
                continue
            if next_char == "*":
                i += 2
                while i + 1 < n and not (content[i] == "*" and content[i + 1] == "/"):
                    i += 1
                i += 2
                continue

        result.append(char)
        i += 1

    return "".join(result)


MAX_WRAPPER_DEPTH = 5


def _extract_shebang_python(first_line: str) -> Path | None:
    """Extract and validate Python interpreter from a #! shebang line."""
    if not first_line.startswith("#!"):
        return None
    shebang = first_line[2:].strip()
    parts = shebang.split()
    if not parts:
        return None

    if parts[0] == "/usr/bin/env" or parts[0].endswith("/env"):
        args = parts[1:]
        target_cmd: str | None = None
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "-S":
                i += 1
                continue
            if arg.startswith("-S"):
                target_cmd = arg[2:]
                break
            if arg.startswith("-"):
                i += 1
                continue
            target_cmd = arg
            break

        if target_cmd and is_python_interpreter(target_cmd):
            which_py = shutil.which(target_cmd)
            if which_py:
                return Path(which_py)
            p = Path(target_cmd)
            if p.is_file():
                return p
    else:
        if is_python_interpreter(parts[0]):
            direct_p = Path(parts[0])
            if direct_p.is_file():
                return direct_p
            which_direct = shutil.which(parts[0])
            if which_direct:
                return Path(which_direct)

    return None


def _extract_exec_target_from_wrapper(content: str, base_dir: Path | None = None) -> Path | None:
    """Inspect trusted local wrapper script text for an absolute or wrapper-relative exec target."""
    for line in content.splitlines():
        line_str = line.strip()
        if not line_str or line_str.startswith("#"):
            continue

        sub_commands = re.split(r";|&&|\|\|", line_str)
        for sub_cmd in sub_commands:
            sub = sub_cmd.strip()
            if not sub:
                continue

            target_token: str | None = None
            if sub.startswith("exec ") or sub.startswith("exec\t") or sub == "exec":
                try:
                    tokens = shlex.split(sub, comments=True)
                except ValueError:
                    tokens = sub.split()
                if len(tokens) >= 2 and tokens[0] == "exec":
                    target_token = tokens[1]

            if not target_token:
                quoted_match = re.search(r"""(?:^|[\t ])exec[\t ]+(["'])(.+?)\1""", sub)
                if quoted_match:
                    target_token = quoted_match.group(2)
                else:
                    unquoted_match = re.search(r"""(?:^|[\t ])exec[\t ]+([^\s"';#]+)""", sub)
                    if unquoted_match:
                        target_token = unquoted_match.group(1)

            if not target_token:
                continue

            target_token = target_token.strip("\"'")
            if not target_token:
                continue

            if target_token.startswith("/"):
                return Path(target_token)

            if target_token.startswith(("./", "../")):
                if base_dir is not None:
                    return (base_dir / target_token).resolve()
                return Path(target_token)

            if base_dir is not None:
                rel_p = base_dir / target_token
                if rel_p.exists():
                    return rel_p.resolve()

    return None


def _extract_exec_python_from_wrapper(content: str) -> Path | None:
    """Inspect trusted local wrapper script text for an absolute Python interpreter used by exec."""
    target = _extract_exec_target_from_wrapper(content)
    if target is not None and is_python_interpreter(target) and target.is_file():
        return target
    return None


def resolve_mcp_runtime(
    executable_cmd: str,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Inspect MCP executable, resolving shebang/interpreter and installed package version.

    Follows absolute or wrapper-relative local exec targets recursively with depth limit
    and cycle protection. Never treats /bin/sh as Python, never executes wrapper contents,
    and redacts error messages.

    Returns:
        (resolved_executable, runtime_python, installed_version, error_message)
    """
    if not executable_cmd:
        return None, None, None, "No executable specified in MCP config"

    initial_path: Path | None = None
    if "/" in executable_cmd or "\\" in executable_cmd:
        initial_path = Path(executable_cmd).expanduser()
    else:
        which_p = shutil.which(executable_cmd)
        if which_p:
            initial_path = Path(which_p)

    if initial_path is None or not initial_path.exists():
        return executable_cmd, None, None, f"MCP executable '{executable_cmd}' not found"

    resolved_top_exe = str(initial_path)
    current_path = initial_path
    if current_path.is_symlink():
        with contextlib.suppress(OSError):
            current_path = current_path.resolve()

    visited_paths: set[Path] = set()
    depth = 0
    max_depth = MAX_WRAPPER_DEPTH

    runtime_python: Path | None = None

    while current_path is not None and depth <= max_depth:
        # Cycle detection: resolve real path for canonical identity
        try:
            canonical_path = current_path.resolve()
        except OSError:
            canonical_path = current_path

        if canonical_path in visited_paths or current_path in visited_paths:
            return (
                resolved_top_exe,
                None,
                None,
                redact_secrets(f"Cyclic exec wrapper reference detected: {current_path}"),
            )

        visited_paths.add(canonical_path)
        visited_paths.add(current_path)

        # 1. Check if current_path itself is a Python interpreter
        if is_python_interpreter(current_path):
            runtime_python = current_path
            break

        # If it is a system prefix path and not a Python interpreter (e.g. /bin/sh), do not parse
        if is_system_prefix(current_path):
            break

        # 2. Check if file exists and is regular file
        if not current_path.is_file():
            return (
                resolved_top_exe,
                None,
                None,
                redact_secrets(f"Exec target '{current_path}' is not a regular file"),
            )

        # 3. Read content safely without executing
        try:
            content = current_path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            return (
                resolved_top_exe,
                None,
                None,
                redact_secrets(f"Cannot read executable script: {exc}"),
            )

        # 4. Check shebang
        first_line = content.splitlines()[0] if content.splitlines() else ""
        shebang_py = _extract_shebang_python(first_line)
        if shebang_py is not None and is_python_interpreter(shebang_py):
            runtime_python = shebang_py
            break

        # 5. Extract next exec target (absolute or wrapper-relative)
        next_target = _extract_exec_target_from_wrapper(content, base_dir=current_path.parent)
        if next_target is None:
            # Fallback to checking sibling/parent venv structure (only if not a system prefix)
            if not is_system_prefix(current_path.parent.parent):
                sibling_py = find_venv_python(current_path.parent.parent)
                if sibling_py is not None and is_python_interpreter(sibling_py):
                    runtime_python = sibling_py
            break

        # Check if next target exists
        if not next_target.exists():
            return (
                resolved_top_exe,
                None,
                None,
                redact_secrets(f"Exec target '{next_target}' not found"),
            )

        if next_target.is_symlink():
            with contextlib.suppress(OSError):
                next_target = next_target.resolve()

        current_path = next_target
        depth += 1

    if depth > max_depth and runtime_python is None:
        return (
            resolved_top_exe,
            None,
            None,
            redact_secrets(
                f"Exec wrapper depth limit ({max_depth}) exceeded resolving MCP runtime: {resolved_top_exe}"
            ),
        )

    # If runtime_python was found, extract installed version from its venv
    installed_ver: str | None = None
    if runtime_python is not None:
        venv_dir = runtime_python.parent.parent
        installed_ver = get_venv_power_framework_version(venv_dir)
        if installed_ver is None:
            with contextlib.suppress(OSError):
                installed_ver = get_venv_power_framework_version(
                    runtime_python.resolve().parent.parent
                )

    return (
        resolved_top_exe,
        str(runtime_python) if runtime_python else None,
        installed_ver,
        None,
    )


def audit_mcp_config(
    config_path: Path,
    target_version: str | None = None,
) -> MCPAuditResult:
    """Inspect MCP configuration file without exposing credentials."""
    client_name = config_path.stem
    if "opencode" in str(config_path):
        client_name = "opencode"
    elif "gemini" in str(config_path):
        client_name = "gemini"
    elif "codex" in str(config_path):
        client_name = "codex"

    suffix = config_path.suffix.lower()
    config_format = "toml" if suffix == ".toml" else ("jsonc" if suffix == ".jsonc" else "json")

    if not config_path.exists():
        return MCPAuditResult(
            client=client_name,
            config_path=str(config_path),
            config_format=config_format,
            status="missing_file",
        )

    if config_path.is_symlink():
        return MCPAuditResult(
            client=client_name,
            config_path=str(config_path),
            config_format=config_format,
            status="manual_review",
            error="Symlink client configuration files are not followed",
        )

    try:
        content = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        return MCPAuditResult(
            client=client_name,
            config_path=str(config_path),
            config_format=config_format,
            status="manual_review",
            error=redact_secrets(f"Cannot read config: {exc}"),
        )

    has_comments = config_format in {"json", "jsonc"} and has_jsonc_comments(content)

    power_entry: Any = None
    if config_format == "toml":
        try:
            payload = tomllib.loads(content) if content.strip() else {}
        except tomllib.TOMLDecodeError as exc:
            return MCPAuditResult(
                client=client_name,
                config_path=str(config_path),
                config_format=config_format,
                status="manual_review",
                error=redact_secrets(f"TOML decode error: {exc}"),
            )
        if not isinstance(payload, dict):
            return MCPAuditResult(
                client=client_name,
                config_path=str(config_path),
                config_format=config_format,
                status="manual_review",
                error="Root TOML element is not a table",
            )
        servers = payload.get("mcp_servers") or payload.get("mcpServers") or payload.get("mcp")
        if servers is None or not isinstance(servers, dict):
            return MCPAuditResult(
                client=client_name,
                config_path=str(config_path),
                config_format=config_format,
                status="missing_entry",
            )
        power_entry = servers.get("power")
    else:
        parseable_content = strip_jsonc_comments(content) if has_comments else content
        try:
            payload = json.loads(parseable_content) if parseable_content.strip() else {}
        except json.JSONDecodeError as exc:
            return MCPAuditResult(
                client=client_name,
                config_path=str(config_path),
                config_format=config_format,
                status="manual_review",
                has_comments=has_comments,
                error=redact_secrets(f"JSON decode error: {exc}"),
            )
        if not isinstance(payload, dict):
            return MCPAuditResult(
                client=client_name,
                config_path=str(config_path),
                config_format=config_format,
                status="manual_review",
                has_comments=has_comments,
                error="Root JSON element is not an object",
            )
        root_key = "mcp" if client_name == "opencode" else "mcpServers"
        servers = payload.get(root_key)
        if servers is None and "mcp_servers" in payload:
            servers = payload.get("mcp_servers")
        if servers is None and "mcpServers" in payload:
            servers = payload.get("mcpServers")
        if servers is None and "mcp" in payload:
            servers = payload.get("mcp")
        if servers is None or not isinstance(servers, dict):
            return MCPAuditResult(
                client=client_name,
                config_path=str(config_path),
                config_format=config_format,
                status="manual_review" if has_comments else "missing_entry",
                has_comments=has_comments,
                error="JSONC contains user comments; manual review required to preserve structure"
                if has_comments
                else None,
            )
        power_entry = servers.get("power")

    if power_entry is None:
        return MCPAuditResult(
            client=client_name,
            config_path=str(config_path),
            config_format=config_format,
            status="manual_review" if has_comments else "missing_entry",
            has_comments=has_comments,
            error="JSONC contains user comments; manual review required to preserve structure"
            if has_comments
            else None,
        )

    if not isinstance(power_entry, dict):
        return MCPAuditResult(
            client=client_name,
            config_path=str(config_path),
            config_format=config_format,
            status="manual_review",
            has_comments=has_comments,
            error="power entry is not a table/object",
        )

    cmd_val = power_entry.get("command")
    env_obj = power_entry.get("env") or power_entry.get("environment") or {}
    env_keys = sorted(env_obj.keys()) if isinstance(env_obj, dict) else []

    executable_name = ""
    if isinstance(cmd_val, list) and cmd_val:
        executable_name = str(cmd_val[0])
    elif isinstance(cmd_val, str):
        executable_name = cmd_val

    is_canonical_name = (
        executable_name.endswith("/power-mcp")
        or executable_name == "power-mcp"
        or "power_framework.mcp" in str(cmd_val)
    )

    if not is_canonical_name:
        return MCPAuditResult(
            client=client_name,
            config_path=str(config_path),
            config_format=config_format,
            status="manual_review" if has_comments else "mismatch",
            entry_present=True,
            executable=executable_name,
            env_keys=env_keys,
            has_comments=has_comments,
            error=redact_secrets(
                "JSONC contains user comments; manual review required to preserve structure"
                if has_comments
                else "Command does not match canonical power-mcp executable"
            ),
        )

    resolved_exe, runtime_py, inst_ver, run_err = resolve_mcp_runtime(executable_name)

    if run_err or not runtime_py or inst_ver is None:
        raw_status = "missing_runtime"
    elif target_version is not None:
        cmp = compare_versions(inst_ver, target_version)
        raw_status = "outdated" if cmp < 0 else "canonical"
    else:
        raw_status = "canonical"

    final_status = "manual_review" if has_comments else raw_status
    if has_comments:
        error_msg = (
            redact_secrets(run_err)
            if run_err
            else "JSONC contains user comments; manual review required to preserve structure"
        )
    else:
        error_msg = redact_secrets(run_err) if run_err else None

    return MCPAuditResult(
        client=client_name,
        config_path=str(config_path),
        config_format=config_format,
        status=final_status,
        entry_present=True,
        executable=executable_name,
        resolved_executable=resolved_exe,
        runtime_python=runtime_py,
        installed_version=inst_ver,
        env_keys=env_keys,
        has_comments=has_comments,
        error=error_msg,
    )


# ============================================================================
# POWER Skill Targets Inspection and Atomic Update
# ============================================================================


def extract_skill_version(skill_md_content: str) -> str | None:
    """Extract version from SKILL.md YAML frontmatter, stripping quotes."""
    match = re.search(r"(?ms)^---\s*\n(.*?)\n---", skill_md_content)
    if not match:
        return None
    ver_match = re.search(r"(?m)^version:\s*(?:['\"]([^'\"]+)['\"]|([^\s#]+))", match.group(1))
    if not ver_match:
        return None
    ver = (ver_match.group(1) or ver_match.group(2) or "").strip().strip("\"'")
    return ver if ver else None


def is_managed_skill_tree(files: dict[str, bytes]) -> bool:
    """Check if target contains valid managed POWER SKILL.md."""
    if "SKILL.md" not in files:
        return False
    header = files["SKILL.md"].decode("utf-8", errors="ignore")
    return header.startswith("---\n") and "\nname: power\n" in header


def is_allowed_skill_target(
    target_path: Path,
    allowed_roots: list[Path] | None = None,
) -> bool:
    """Verify target path is under an allowed non-system root and not a symlink."""
    if is_system_prefix(target_path):
        return False

    try:
        resolved = target_path.resolve()
    except OSError:
        return False

    if is_system_prefix(resolved):
        return False

    # Disallow root or /root directly
    if resolved in (Path("/"), Path.home(), Path("/root")):
        return False

    # Check symlinks in ancestors
    cur = target_path
    while cur != cur.parent:
        if cur.is_symlink():
            return False
        cur = cur.parent

    roots = allowed_roots if allowed_roots is not None else ALLOWED_SKILL_TARGET_ROOTS
    for allowed in roots:
        try:
            if resolved.is_relative_to(allowed.resolve()):
                return True
        except ValueError:
            continue

    return False


def audit_skill(
    target_path: Path,
    release: ReleasePayload,
    allowed_roots: list[Path] | None = None,
) -> SkillAuditResult:
    """Audit one Skill directory against the release skill payload."""
    if not is_allowed_skill_target(target_path, allowed_roots):
        return SkillAuditResult(
            target_path=str(target_path),
            installed_version=None,
            tree_sha256=None,
            status="manual_review",
            error="Target is outside allowed roots or is a symlink",
        )

    if not target_path.exists():
        return SkillAuditResult(
            target_path=str(target_path),
            installed_version=None,
            tree_sha256=None,
            status="ready",
            file_count=0,
        )

    if not target_path.is_dir() or target_path.is_symlink():
        return SkillAuditResult(
            target_path=str(target_path),
            installed_version=None,
            tree_sha256=None,
            status="manual_review",
            error="Target exists but is a symlink or non-directory",
        )

    target_files = tree_from_directory(target_path)
    if not target_files:
        return SkillAuditResult(
            target_path=str(target_path),
            installed_version=None,
            tree_sha256=None,
            status="ready",
            file_count=0,
        )

    target_hash = aggregate_tree_hash(target_files)
    skill_md = target_files.get("SKILL.md", b"").decode("utf-8", errors="ignore")
    installed_ver = extract_skill_version(skill_md)

    if release.skill_tree_sha256 and target_hash == release.skill_tree_sha256:
        status = "up_to_date"
    elif is_managed_skill_tree(target_files):
        status = "upgrade_ready"
    else:
        status = "manual_review"

    return SkillAuditResult(
        target_path=str(target_path),
        installed_version=installed_ver,
        tree_sha256=target_hash,
        status=status,
        file_count=len(target_files),
    )


def apply_skill_update(
    audit: SkillAuditResult,
    release: ReleasePayload,
    dry_run: bool = True,
    allowed_roots: list[Path] | None = None,
) -> tuple[str, str | None]:
    """Atomically install or upgrade a managed Skill target with path safety checks."""
    if audit.status not in {"ready", "upgrade_ready"}:
        return "skipped", None

    if not release.skill_files:
        return "failed", "Release payload contains no skill files"

    target = Path(audit.target_path).expanduser()
    if not is_allowed_skill_target(target, allowed_roots):
        return "failed", f"Skill target {target} is outside allowed roots or is a symlink"

    # Verify skill tree hash if expected hash is present
    actual_tree_hash = aggregate_tree_hash(release.skill_files)
    if release.skill_tree_sha256 and actual_tree_hash != release.skill_tree_sha256:
        return (
            "failed",
            f"Skill tree hash mismatch: expected {release.skill_tree_sha256}, got {actual_tree_hash}",
        )

    # Check every relative path for allowlist / safety
    for relative in release.skill_files:
        if not is_safe_skill_relative_path(relative):
            return "failed", f"Unsafe or disallowed skill relative path: {relative}"

    if dry_run:
        return "planned_update", None

    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent))
    previous: Path | None = None
    try:
        for relative, content in release.skill_files.items():
            dest = staging / relative
            if not dest.resolve().is_relative_to(staging.resolve()):
                raise ValueError(f"Path traversal detected in skill file: {relative}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            mode = 0o755 if relative.startswith("scripts/") else 0o644
            dest.chmod(mode)

        if target.exists():
            previous = target.parent / f".{target.name}.prev-{os.getpid()}"
            if previous.exists():
                shutil.rmtree(previous, ignore_errors=True)
            os.replace(target, previous)

        os.replace(staging, target)

        # Validate the final installed tree hash before deleting previous
        installed_files = tree_from_directory(target)
        installed_hash = aggregate_tree_hash(installed_files)
        expected_hash = release.skill_tree_sha256 or actual_tree_hash
        if installed_hash != expected_hash:
            raise ValueError(
                f"Installed skill tree hash mismatch: expected {expected_hash}, got {installed_hash}"
            )

        if previous is not None and previous.exists():
            shutil.rmtree(previous, ignore_errors=True)
        return "updated", None
    except Exception as exc:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if previous is not None and previous.exists():
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            with contextlib.suppress(OSError):
                os.replace(previous, target)
        elif target.exists() and previous is None:
            shutil.rmtree(target, ignore_errors=True)
        return "failed", redact_secrets(str(exc))


# ============================================================================
# State Report Persistence and Canonical Brain Log
# ============================================================================


def persist_state_report(report: AuditReport, state_dir: Path) -> Path:
    """Atomically persist a redacted JSON audit report under the state directory."""
    state_dir.mkdir(parents=True, exist_ok=True)
    ts_sec = int(time.time())
    ts_ns = time.time_ns()
    pid = os.getpid()
    report_file = state_dir / f"audit-{ts_sec}-{ts_ns % 1_000_000_000:09d}-{pid}.json"
    latest_file = state_dir / "latest.json"

    data = json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n"

    # Atomic write report_file
    fd, tmp = tempfile.mkstemp(prefix=f".{report_file.name}.", dir=state_dir)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(data)
    os.replace(tmp, report_file)

    # Atomic write latest_file
    fd_lat, tmp_lat = tempfile.mkstemp(prefix=".latest.", dir=state_dir)
    with os.fdopen(fd_lat, "w", encoding="utf-8") as handle:
        handle.write(data)
    os.replace(tmp_lat, latest_file)

    return report_file


def record_brain_log(vault_path: Path, report: AuditReport, *, strict: bool = False) -> bool:
    """Record a deduplicated Action/Result entry in the canonical brain log with file locking."""
    vault = Path(vault_path).expanduser().resolve()
    if not vault.is_dir():
        return False

    log_file = vault / "log.md"
    if not log_file.is_file():
        daily_log = vault / "06_Daily_Logs" / "log.md"
        if daily_log.is_file():
            log_file = daily_log
        else:
            return False

    lock_dir = vault / ".power"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = lock_dir / "mutation.lock"

    mode_str = "Apply" if report.applied else "Audit"
    action_desc = "applied updates" if report.applied else "read-only audit"
    rel_ver = report.release.get("version", "unknown")
    if "error" in report.release and rel_ver == "unknown":
        rel_ver = "failed"
    drift_desc = "Drift detected" if report.has_drift else "No drift"

    sig = f"Runtime {mode_str} (v{rel_ver})"
    date_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")

    if "error" in report.release:
        result_desc = f"Release validation failed: {report.release['error']}."
    else:
        result_desc = (
            f"Checked {len(report.venvs)} venvs, {len(report.mcp_configs)} MCP configs, "
            f"{len(report.skills)} skills. Status: {drift_desc}."
        )

    entry_text = (
        f"\n### {date_str} UTC — {sig}\n"
        f"- **Action**: P.O.W.E.R runtime {action_desc} (target release v{rel_ver}).\n"
        f"- **Result**: {result_desc}\n"
    )

    try:
        with lock_file.open("a+") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                content = log_file.read_text(encoding="utf-8")
                last_entries = "\n".join(content.splitlines()[-20:])
                if sig in last_entries and drift_desc in last_entries:
                    return strict  # Deduplicated

                fd, tmp = tempfile.mkstemp(prefix=".log.", dir=log_file.parent)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(content + entry_text)
                os.replace(tmp, log_file)
                return True
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    except Exception:
        if strict:
            raise
        return False


# ============================================================================
# Human Readable & JSON Report Formatters
# ============================================================================


def format_human_report(report: AuditReport) -> str:
    """Format audit report into structured human-readable tables."""
    lines: list[str] = [
        "=" * 80,
        f" P.O.W.E.R Host-side Runtime Audit Report ({report.timestamp} UTC)",
        "=" * 80,
        f"Release: v{report.release.get('version')} (Tag: {report.release.get('tag')})",
        f"Mode:    {'APPLY (Mutations Active)' if report.applied else 'AUDIT (Read-Only)'}",
        f"Status:  {'DRIFT DETECTED' if report.has_drift else 'ALL UP TO DATE'}",
        "",
        "--- Virtual Environments ---",
        f"{'Venv Path':<50} {'Installed':<12} {'Status':<15}",
        "-" * 80,
    ]

    for v in report.venvs:
        ver = v.installed_version or "(none)"
        st = v.status.upper()
        if v.action_taken:
            st = f"{st} -> {v.action_taken.upper()}"
        lines.append(f"{v.path:<50} {ver:<12} {st:<15}")

    lines.extend(
        [
            "",
            "--- MCP Client Configurations ---",
            f"{'Client / Path':<50} {'Format':<8} {'Status':<18}",
            "-" * 80,
        ]
    )

    for m in report.mcp_configs:
        path_abbr = m.config_path
        if len(path_abbr) > 48:
            path_abbr = "..." + path_abbr[-45:]
        lines.append(f"{path_abbr:<50} {m.config_format:<8} {m.status.upper():<18}")

    lines.extend(
        [
            "",
            "--- Skill Targets ---",
            f"{'Skill Target Path':<50} {'Files':<8} {'Status':<18}",
            "-" * 80,
        ]
    )

    for s in report.skills:
        path_abbr = s.target_path
        if len(path_abbr) > 48:
            path_abbr = "..." + path_abbr[-45:]
        st = s.status.upper()
        if s.action_taken:
            st = f"{st} -> {s.action_taken.upper()}"
        lines.append(f"{path_abbr:<50} {s.file_count:<8} {st:<18}")

    if report.errors:
        lines.extend(["", "--- Errors ---"])
        lines.extend(f"  * {err}" for err in report.errors)

    lines.append("=" * 80)
    return "\n".join(lines)


# ============================================================================
# Main Execution Pipeline
# ============================================================================


def run_audit(
    repo: str = DEFAULT_REPO,
    ref: str = DEFAULT_REF,
    source_dir: Path | None = None,
    vault_path: Path = DEFAULT_VAULT,
    state_dir: Path = DEFAULT_STATE_DIR,
    venv_roots: list[str | Path] | None = None,
    skill_targets: list[str | Path] | None = None,
    mcp_configs: list[str | Path] | None = None,
    apply: bool = False,
    record: bool = False,
    fail_on_drift: bool = False,
) -> tuple[AuditReport, int]:
    """Execute complete runtime audit and optional updates under process lock."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    state_dir_path = Path(state_dir).expanduser().resolve()
    state_dir_path.mkdir(parents=True, exist_ok=True)
    lock_file = state_dir_path / ".process.lock"

    try:
        with ProcessLock(lock_file):
            return _run_audit_internal(
                repo=repo,
                ref=ref,
                source_dir=source_dir,
                vault_path=vault_path,
                state_dir=state_dir_path,
                venv_roots=venv_roots,
                skill_targets=skill_targets,
                mcp_configs=mcp_configs,
                apply=apply,
                record=record,
                fail_on_drift=fail_on_drift,
                timestamp=timestamp,
            )
    except RuntimeError as exc:
        err_msg = redact_secrets(str(exc))
        report = AuditReport(
            timestamp=timestamp,
            release={"error": err_msg},
            venvs=[],
            mcp_configs=[],
            skills=[],
            applied=apply,
            recorded=False,
            has_drift=True,
            errors=[err_msg],
        )
        try:
            persist_state_report(report, state_dir_path)
        except Exception as p_exc:
            report.errors.append(redact_secrets(f"Failed to persist state report: {p_exc}"))
        return report, 1


def _run_audit_internal(
    repo: str,
    ref: str,
    source_dir: Path | None,
    vault_path: Path,
    state_dir: Path,
    venv_roots: list[str | Path] | None,
    skill_targets: list[str | Path] | None,
    mcp_configs: list[str | Path] | None,
    apply: bool,
    record: bool,
    fail_on_drift: bool,
    timestamp: str,
) -> tuple[AuditReport, int]:
    errors: list[str] = []

    # 1. Fetch release metadata
    try:
        release = fetch_release_payload(repo=repo, ref=ref, source_dir=source_dir)
    except Exception as exc:
        err_msg = redact_secrets(f"Release validation failed: {exc}")
        report = AuditReport(
            timestamp=timestamp,
            release={"error": redact_secrets(str(exc))},
            venvs=[],
            mcp_configs=[],
            skills=[],
            applied=apply,
            recorded=False,
            has_drift=True,
            errors=[err_msg],
        )
        try:
            persist_state_report(report, state_dir)
        except Exception as p_exc:
            report.errors.append(redact_secrets(f"Failed to persist state report: {p_exc}"))

        if record:
            rec_ok = record_brain_log(vault_path, report)
            report.recorded = rec_ok
            try:
                persist_state_report(report, state_dir)
            except Exception as p_exc:
                report.errors.append(
                    redact_secrets(f"Failed to persist updated state report: {p_exc}")
                )

        return report, 1

    downloaded_wheel_tmp: Path | None = None
    try:
        if apply:
            if release.wheel_path is None and release.wheel_url and release.wheel_sha256:
                try:
                    downloaded_wheel_tmp = download_and_verify_wheel(
                        wheel_url=release.wheel_url,
                        expected_sha256=release.wheel_sha256,
                        dest_dir=state_dir,
                    )
                    extracted_skills = _extract_wheel_skill_tree(downloaded_wheel_tmp)
                    if release.skill_tree_sha256:
                        actual_tree_hash = aggregate_tree_hash(extracted_skills)
                        if actual_tree_hash != release.skill_tree_sha256:
                            raise ReleaseValidationError(
                                f"Extracted skill tree hash mismatch: expected {release.skill_tree_sha256}, got {actual_tree_hash}"
                            )
                    release = ReleasePayload(
                        tag=release.tag,
                        version=release.version,
                        pyproject_version=release.pyproject_version,
                        commit=release.commit,
                        wheel_filename=release.wheel_filename,
                        wheel_sha256=release.wheel_sha256,
                        wheel_path=downloaded_wheel_tmp,
                        wheel_url=release.wheel_url,
                        skill_tree_sha256=release.skill_tree_sha256,
                        skill_files=extracted_skills if extracted_skills else release.skill_files,
                        manifest=release.manifest,
                    )
                except Exception as exc:
                    err_msg = redact_secrets(f"Wheel download/verification failed: {exc}")
                    errors.append(err_msg)
            elif release.wheel_path is None and not release.skill_files:
                errors.append(
                    "Apply mode requires a verified release wheel; wheel asset or manifest SHA-256 is missing"
                )

        # 2. Discover and audit venvs
        roots = venv_roots if venv_roots is not None else DEFAULT_VENV_ROOTS
        venv_paths = discover_bounded_venvs(roots)
        venv_results: list[VenvAuditResult] = []

        for vp in venv_paths:
            v_audit = audit_venv(vp, release.version)
            if apply and v_audit.status == "outdated":
                if release.wheel_path is None:
                    v_audit.action_taken = "failed"
                    v_audit.error = "No verified release wheel available for apply"
                    errors.append(
                        f"Venv update failed for {vp}: No verified release wheel available"
                    )
                else:
                    action, err = apply_venv_update(v_audit, release, dry_run=False)
                    v_audit.action_taken = action
                    if err:
                        v_audit.error = redact_secrets(err)
                        errors.append(f"Venv update failed for {vp}: {redact_secrets(err)}")
                    else:
                        new_ver = get_venv_power_framework_version(vp)
                        v_audit.installed_version = new_ver
                        if new_ver == release.version:
                            v_audit.status = "up_to_date"
            venv_results.append(v_audit)

        # 3. Audit MCP configs
        mcp_paths = [
            Path(p) for p in (mcp_configs if mcp_configs is not None else DEFAULT_MCP_CONFIGS)
        ]
        mcp_results: list[MCPAuditResult] = []
        for mp in mcp_paths:
            m_audit = audit_mcp_config(mp, target_version=release.version)
            mcp_results.append(m_audit)

        # 4. Audit Skills
        allowed_roots: list[Path] = list(ALLOWED_SKILL_TARGET_ROOTS)
        if skill_targets is not None:
            for st in skill_targets:
                st_p = Path(st).expanduser().resolve()
                if not is_system_prefix(st_p.parent) and st_p.parent not in (
                    Path("/"),
                    HOME,
                ):
                    allowed_roots.append(st_p.parent)

        s_paths = [
            Path(p) for p in (skill_targets if skill_targets is not None else DEFAULT_SKILL_TARGETS)
        ]
        skill_results: list[SkillAuditResult] = []
        for sp in s_paths:
            s_audit = audit_skill(sp, release, allowed_roots=allowed_roots)
            if apply and s_audit.status in {"upgrade_ready", "ready"}:
                if not release.skill_files:
                    s_audit.action_taken = "failed"
                    s_audit.error = "No verified skill files available for apply"
                    errors.append(
                        f"Skill update failed for {sp}: No verified skill files available"
                    )
                else:
                    action, err = apply_skill_update(
                        s_audit, release, dry_run=False, allowed_roots=allowed_roots
                    )
                    s_audit.action_taken = action
                    if err:
                        s_audit.error = redact_secrets(err)
                        errors.append(f"Skill update failed for {sp}: {redact_secrets(err)}")
                    else:
                        re_audit = audit_skill(sp, release, allowed_roots=allowed_roots)
                        s_audit.installed_version = re_audit.installed_version
                        s_audit.tree_sha256 = re_audit.tree_sha256
                        s_audit.file_count = re_audit.file_count
                        s_audit.status = re_audit.status
            skill_results.append(s_audit)

        # Compute has_drift across all audit dimensions
        has_drift = (
            any(v.status in {"outdated", "unwritable", "broken_venv"} for v in venv_results)
            or any(
                m.status
                in {
                    "mismatch",
                    "missing_entry",
                    "missing_runtime",
                    "outdated",
                    "manual_review",
                    "missing_file",
                }
                for m in mcp_results
            )
            or any(s.status in {"upgrade_ready", "ready", "manual_review"} for s in skill_results)
        )

        report = AuditReport(
            timestamp=timestamp,
            release=release.as_dict(),
            venvs=venv_results,
            mcp_configs=mcp_results,
            skills=skill_results,
            applied=apply,
            recorded=False,
            has_drift=has_drift,
            errors=errors,
        )

        # Persist report
        try:
            persist_state_report(report, state_dir)
        except Exception as exc:
            errors.append(redact_secrets(f"Failed to persist state report: {exc}"))

        # Record in canonical brain log if requested
        if record:
            try:
                rec_ok = record_brain_log(vault_path, report, strict=True)
            except Exception as exc:
                errors.append(redact_secrets(f"Failed to record canonical brain log: {exc}"))
                rec_ok = False
            report.recorded = rec_ok
            if not rec_ok:
                errors.append("Canonical brain log recording did not reach its postcondition")
            try:
                persist_state_report(report, state_dir)
            except Exception as exc:
                errors.append(redact_secrets(f"Failed to persist updated state report: {exc}"))

        exit_code = 0
        if errors:
            exit_code = 1
        elif fail_on_drift and has_drift:
            exit_code = 2

        return report, exit_code
    finally:
        if downloaded_wheel_tmp is not None and downloaded_wheel_tmp.is_file():
            with contextlib.suppress(OSError):
                downloaded_wheel_tmp.unlink()


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Host-side P.O.W.E.R version audit and update CLI.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as structured JSON",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates to outdated venvs and skills (default is read-only)",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="Record Action/Result entry in canonical brain log.md",
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"GitHub repository (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--ref",
        default=DEFAULT_REF,
        help=f"Release tag or branch (default: {DEFAULT_REF})",
    )
    parser.add_argument(
        "--vault",
        type=Path,
        default=DEFAULT_VAULT,
        help=f"Obsidian brain vault directory (default: {DEFAULT_VAULT})",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help=f"Directory to persist audit reports (default: {DEFAULT_STATE_DIR})",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="Local repository or dist directory with release artifacts",
    )
    parser.add_argument(
        "--venv-root",
        action="append",
        dest="venv_roots",
        help="Virtual environment search root (can specify multiple times)",
    )
    parser.add_argument(
        "--skill-target",
        action="append",
        dest="skill_targets",
        help="Skill target directory (can specify multiple times)",
    )
    parser.add_argument(
        "--mcp-config",
        action="append",
        dest="mcp_configs",
        help="MCP configuration file path (can specify multiple times)",
    )
    parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="Return exit code 2 if version or configuration drift is detected",
    )

    args = parser.parse_args(argv)

    report, code = run_audit(
        repo=args.repo,
        ref=args.ref,
        source_dir=args.source_dir,
        vault_path=args.vault,
        state_dir=args.state_dir,
        venv_roots=args.venv_roots,
        skill_targets=args.skill_targets,
        mcp_configs=args.mcp_configs,
        apply=args.apply,
        record=args.record,
        fail_on_drift=args.fail_on_drift,
    )

    if args.json:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_human_report(report))

    return code


if __name__ == "__main__":
    sys.exit(main())
