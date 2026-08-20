#!/usr/bin/env python3
"""Fail-closed hourly updater for the P.O.W.E.R. runtime fleet.

The updater consumes only stable GitHub Releases, verifies the wheel metadata
and published digest, updates existing POWER installations in configured
Python environments, and optionally rebuilds the LXC POWER-GUI image with the
new wheel. It never installs into an unrelated virtual environment and never
prints credentials or release payloads.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import ipaddress
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


LOG = logging.getLogger("power-auto-updater")
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
WHEEL_RE = re.compile(r"^power_framework-(\d+\.\d+\.\d+)-py3-none-any\.whl$")
SKILL_FILES = (
    "SKILL.md",
    "references/agent-workflow.md",
    "references/runtime-contract.md",
    "scripts/generate_index.py",
    "scripts/lint_brain.py",
)
SECRET_RE = re.compile(
    r"(?i)(?:gh[pousr]_[A-Za-z0-9_]{12,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)"
)
KEY_VALUE_SECRET_RE = re.compile(
    r"(?i)(\b(?:token|password|secret|api[_-]?key|authorization)\b\s*[:=]\s*)\S+"
)
Version = tuple[int, int, int]


def parse_version(value: str) -> Version:
    """Parse a strict stable POWER version."""

    match = VERSION_RE.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"unsupported stable version: {value!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def version_text(version: Version) -> str:
    return ".".join(str(part) for part in version)


def redact(value: str) -> str:
    """Remove common credential forms before a message reaches journald."""

    redacted = SECRET_RE.sub("<redacted>", value)
    return KEY_VALUE_SECRET_RE.sub(r"\1<redacted>", redacted)


def parse_env_file(path: Path) -> dict[str, str]:
    """Read a small dotenv file without shell evaluation."""

    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def env_bool(values: dict[str, str], key: str, default: bool) -> bool:
    value = values.get(key, os.environ.get(key, ""))
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_value(values: dict[str, str], key: str, default: str) -> str:
    return os.environ.get(key, values.get(key, default)).strip()


def split_paths(value: str) -> tuple[Path, ...]:
    return tuple(Path(item) for item in value.split(os.pathsep) if item)


def atomic_write(path: Path, content: str, mode: int | None = None) -> None:
    """Write content atomically while preserving an existing file mode."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is None and path.exists():
        mode = stat.S_IMODE(path.stat().st_mode)
    if mode is None:
        mode = 0o600
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, mode)
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def run_command(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = 300,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a command with bounded output and redacted diagnostics."""

    try:
        result = subprocess.run(  # noqa: S603 - command vectors are trusted local configuration
            list(command),
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        LOG.error("command failed: %s: %s", command[0], redact(str(exc)))
        if check:
            raise RuntimeError(f"command failed: {command[0]}") from exc
        return subprocess.CompletedProcess(command, 1, "", str(exc))
    if result.returncode != 0 and check:
        details = redact((result.stderr or result.stdout).strip())[-1200:]
        LOG.error("command failed rc=%s: %s: %s", result.returncode, command[0], details)
        raise RuntimeError(f"command failed: {command[0]} rc={result.returncode}")
    return result


@dataclass(frozen=True)
class Release:
    version: Version
    tag: str
    wheel_name: str
    wheel_url: str
    wheel_digest: str | None


@dataclass(frozen=True)
class Config:
    repo: str
    python_targets: tuple[Path, ...]
    state_dir: Path
    update_gui: bool
    gui_compose_dir: Path
    gui_service: str
    gui_base_image: str
    gui_bind_address: str
    skill_targets: tuple[Path, ...]
    dry_run: bool

    @classmethod
    def load(cls, path: Path, *, dry_run: bool) -> Config:
        values = parse_env_file(path)
        repo = env_value(values, "POWER_UPDATER_REPO", "weby-homelab/power-framework")
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) is None:
            raise ValueError("POWER_UPDATER_REPO must be owner/name")
        python_targets = split_paths(env_value(values, "POWER_UPDATER_PYTHON_TARGETS", ""))
        bind = env_value(values, "POWER_GUI_BIND_ADDRESS", "192.168.2.29")
        try:
            ipaddress.ip_address(bind)
        except ValueError as exc:
            raise ValueError("POWER_GUI_BIND_ADDRESS must be a literal IP address") from exc
        return cls(
            repo=repo,
            python_targets=python_targets,
            state_dir=Path(env_value(values, "POWER_UPDATER_STATE_DIR", "/var/lib/power-updater")),
            update_gui=env_bool(values, "POWER_UPDATER_GUI", False),
            gui_compose_dir=Path(
                env_value(values, "POWER_GUI_COMPOSE_DIR", "/root/power-gui-build")
            ),
            gui_service=env_value(values, "POWER_GUI_SERVICE", "power-gui"),
            gui_base_image=env_value(values, "POWER_GUI_BASE_IMAGE", "webyhomelab/power-gui:0.7.4"),
            gui_bind_address=bind,
            skill_targets=split_paths(env_value(values, "POWER_UPDATER_SKILL_TARGETS", "")),
            dry_run=dry_run,
        )


def fetch_release(repo: str) -> Release:
    """Fetch and validate the latest stable GitHub Release metadata."""

    url = f"https://api.github.com/repos/{repo}/releases/latest"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "power-auto-updater/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError("GitHub release lookup failed") from exc
    if payload.get("draft") or payload.get("prerelease"):
        raise RuntimeError("latest GitHub release is not stable")
    tag = str(payload.get("tag_name", ""))
    version = parse_version(tag)
    expected_name = f"power_framework-{version_text(version)}-py3-none-any.whl"
    assets = payload.get("assets", [])
    asset = next((item for item in assets if item.get("name") == expected_name), None)
    if not isinstance(asset, dict):
        raise RuntimeError(f"stable release {tag} has no canonical wheel")
    wheel_url = str(asset.get("browser_download_url", ""))
    parsed_url = urllib.parse.urlparse(wheel_url)
    if parsed_url.scheme != "https" or parsed_url.hostname not in {
        "github.com",
        "release-assets.githubusercontent.com",
    }:
        raise RuntimeError("release wheel URL is not an approved HTTPS GitHub URL")
    digest = asset.get("digest")
    if digest is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", str(digest)):
        raise RuntimeError("release wheel digest has an invalid format")
    return Release(version, tag, expected_name, wheel_url, str(digest) if digest else None)


def download_verified_wheel(release: Release, state_dir: Path) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    temporary = state_dir / f"{release.wheel_name}.download"
    request = urllib.request.Request(
        release.wheel_url, headers={"User-Agent": "power-auto-updater/1"}
    )
    digest = hashlib.sha256()
    try:
        with (
            urllib.request.urlopen(request, timeout=120) as response,
            temporary.open("wb") as handle,
        ):
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
    except (OSError, urllib.error.URLError) as exc:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("release wheel download failed") from exc
    actual_digest = digest.hexdigest()
    if release.wheel_digest and release.wheel_digest != f"sha256:{actual_digest}":
        temporary.unlink(missing_ok=True)
        raise RuntimeError("release wheel digest does not match GitHub asset digest")
    try:
        with zipfile.ZipFile(temporary) as archive:
            metadata_names = [name for name in archive.namelist() if name.endswith("/METADATA")]
            if len(metadata_names) != 1:
                raise RuntimeError("wheel metadata is ambiguous")
            metadata = archive.read(metadata_names[0]).decode("utf-8", errors="strict")
    except (OSError, zipfile.BadZipFile, UnicodeError) as exc:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("downloaded release is not a valid wheel") from exc
    fields = dict(
        line.split(": ", 1)
        for line in metadata.splitlines()
        if ": " in line and line.split(": ", 1)[0] in {"Name", "Version"}
    )
    if fields.get("Name", "").lower() != "power-framework":
        temporary.unlink(missing_ok=True)
        raise RuntimeError("wheel metadata has an unexpected distribution name")
    if parse_version(fields.get("Version", "")) != release.version:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("wheel metadata version does not match release tag")
    verified = state_dir / release.wheel_name
    os.replace(temporary, verified)
    LOG.info("verified release %s wheel sha256=%s", release.tag, actual_digest)
    return verified


def fetch_tag_file(repo: str, tag: str, relative_path: str) -> str:
    encoded_tag = urllib.parse.quote(tag, safe="")
    url = f"https://raw.githubusercontent.com/{repo}/{encoded_tag}/.agents/skills/power/{relative_path}"
    request = urllib.request.Request(url, headers={"User-Agent": "power-auto-updater/1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="strict")
    except (OSError, urllib.error.URLError, UnicodeError) as exc:
        raise RuntimeError(f"skill asset fetch failed: {relative_path}") from exc


def update_skills(config: Config, release: Release) -> list[str]:
    targets = tuple(path for path in config.skill_targets if (path / "SKILL.md").exists())
    if not targets:
        LOG.info("no active POWER Skill targets configured on this host")
        return []
    if config.dry_run:
        LOG.info("dry-run: would verify %d active POWER Skill targets", len(targets))
        return []
    try:
        payloads = {
            relative_path: fetch_tag_file(config.repo, release.tag, relative_path)
            for relative_path in SKILL_FILES
        }
        declared = re.search(
            r"(?m)^version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$",
            payloads["SKILL.md"],
        )
        if declared is None or parse_version(declared.group(1)) != release.version:
            raise RuntimeError("tag Skill metadata version does not match release")
        for target in targets:
            target.mkdir(parents=True, exist_ok=True)
            for relative_path, content in payloads.items():
                mode = 0o755 if relative_path.endswith(".py") else 0o644
                atomic_write(target / relative_path, content, mode=mode)
            LOG.info("synchronized Skill %s to %s", version_text(release.version), target)
        return []
    except Exception as exc:
        return [f"Skills: {redact(str(exc))}"]


def package_version(python: Path) -> Version | None:
    script = "import importlib.metadata as m; print(m.version('power-framework'))"
    result = run_command((str(python), "-c", script), timeout=20, check=False)
    if result.returncode != 0:
        return None
    try:
        return parse_version(result.stdout.strip())
    except ValueError:
        return None


@dataclass(frozen=True)
class PackageSnapshot:
    """Small rollback copy of the installed POWER distribution."""

    root: Path
    files: tuple[tuple[Path, Path, bool], ...]
    purelib: Path
    scripts: Path


def package_snapshot(python: Path, state_dir: Path) -> PackageSnapshot:
    """Capture POWER files before a potentially destructive reinstall."""

    files_script = (
        "import importlib.metadata as m, json; "
        "d=m.distribution('power-framework'); "
        "print(json.dumps([str(d.locate_file(item)) for item in (d.files or ())]))"
    )
    paths_result = run_command((str(python), "-c", files_script), timeout=20)
    try:
        paths = [Path(item) for item in json.loads(paths_result.stdout)]
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("cannot enumerate installed POWER files") from exc
    paths = [path for path in paths if path.is_file() or path.is_symlink()]

    locations_script = (
        "import json, sysconfig; "
        "print(json.dumps([sysconfig.get_path('purelib'), sysconfig.get_path('scripts')]))"
    )
    locations_result = run_command((str(python), "-c", locations_script), timeout=20)
    try:
        purelib, scripts = (Path(item) for item in json.loads(locations_result.stdout))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError("cannot locate the target Python installation") from exc

    root = Path(tempfile.mkdtemp(prefix="rollback-", dir=state_dir))
    captured: list[tuple[Path, Path, bool]] = []
    try:
        for index, source in enumerate(paths):
            backup = root / "files" / str(index)
            backup.parent.mkdir(parents=True, exist_ok=True)
            if source.is_symlink():
                backup.symlink_to(os.readlink(source))
                is_symlink = True
            else:
                shutil.copy2(source, backup)
                is_symlink = False
            captured.append((source, backup, is_symlink))
        atomic_write(root / "manifest.json", json.dumps([str(path) for path in paths]))
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return PackageSnapshot(root, tuple(captured), purelib, scripts)


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def cleanup_partial_power_install(snapshot: PackageSnapshot) -> None:
    """Remove only POWER-owned paths before restoring a snapshot."""

    for source, _backup, _is_symlink in snapshot.files:
        remove_path(source)
    remove_path(snapshot.purelib / "power_framework")
    for path in snapshot.purelib.glob("power_framework-*.dist-info"):
        remove_path(path)
    for name in ("power", "power.exe", "power-script.py"):  # Linux plus venv wrappers.
        remove_path(snapshot.scripts / name)


def restore_package_snapshot(snapshot: PackageSnapshot) -> None:
    cleanup_partial_power_install(snapshot)
    for source, backup, is_symlink in snapshot.files:
        source.parent.mkdir(parents=True, exist_ok=True)
        if is_symlink:
            source.symlink_to(os.readlink(backup))
        else:
            shutil.copy2(backup, source)


def discover_python_targets(config: Config) -> tuple[Path, ...]:
    if not config.python_targets:
        LOG.info("no explicit POWER Python targets configured on this host")
        return ()
    missing = tuple(
        path for path in config.python_targets if not path.is_file() or not os.access(path, os.X_OK)
    )
    if missing:
        formatted = ", ".join(str(path) for path in missing)
        raise RuntimeError(f"configured POWER Python target is missing: {formatted}")
    targets = tuple(path for path in config.python_targets if package_version(path) is not None)
    ignored = len(config.python_targets) - len(targets)
    LOG.info(
        "validated %d explicit POWER Python targets%s",
        len(targets),
        f"; ignored {ignored} configured paths without POWER" if ignored else "",
    )
    return targets


def install_wheel(python: Path, wheel: Path) -> None:
    uv = shutil.which("uv") or (
        "/root/.local/bin/uv" if Path("/root/.local/bin/uv").exists() else None
    )
    if uv:
        command = (
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "--no-deps",
            "--no-cache",
            "--link-mode=copy",
            "--force-reinstall",
            str(wheel),
        )
    else:
        command = [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-input",
            "--no-deps",
            "--force-reinstall",
            str(wheel),
        ]
        prefix = run_command(
            (str(python), "-c", "import sys; print(sys.prefix == sys.base_prefix)"), timeout=20
        )
        if prefix.stdout.strip() == "True":
            command.append("--break-system-packages")
    run_command(tuple(command), timeout=600)


def update_python_targets(config: Config, release: Release, wheel: Path) -> list[str]:
    failures: list[str] = []
    for python in discover_python_targets(config):
        current = package_version(python)
        if current is None or current >= release.version:
            LOG.info("%s already at %s", python, version_text(current or release.version))
            continue
        if config.dry_run:
            LOG.info(
                "dry-run: would update %s from %s to %s",
                python,
                version_text(current),
                version_text(release.version),
            )
            continue
        snapshot: PackageSnapshot | None = None
        try:
            snapshot = package_snapshot(python, config.state_dir)
            install_wheel(python, wheel)
            verified = package_version(python)
            if verified != release.version:
                raise RuntimeError(f"post-install readback={verified}")
            LOG.info(
                "updated %s from %s to %s",
                python,
                version_text(current),
                version_text(release.version),
            )
        except Exception as exc:
            if snapshot is not None:
                try:
                    restore_package_snapshot(snapshot)
                    LOG.warning("restored %s after failed POWER update", python)
                except Exception as restore_exc:
                    LOG.error("rollback failed for %s: %s", python, redact(str(restore_exc)))
            failures.append(f"{python}: {redact(str(exc))}")
            LOG.error("failed to update %s: %s", python, redact(str(exc)))
        finally:
            if snapshot is not None:
                shutil.rmtree(snapshot.root, ignore_errors=True)
    return failures


def docker_output(command: Sequence[str], *, cwd: Path | None = None, timeout: int = 300) -> str:
    return run_command(command, cwd=cwd, timeout=timeout).stdout.strip()


def container_power_version(service: str) -> Version | None:
    result = run_command(
        (
            "docker",
            "exec",
            service,
            "python",
            "-c",
            "import importlib.metadata as m; print(m.version('power-framework'))",
        ),
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        return parse_version(result.stdout.strip())
    except ValueError:
        return None


def image_digest(image: str) -> str:
    digest = docker_output(
        ("docker", "image", "inspect", image, "--format", "{{index .RepoDigests 0}}"), timeout=30
    )
    if "@" not in digest:
        raise RuntimeError(f"base image has no immutable repository digest: {image}")
    return digest


def update_compose_env(path: Path, key: str, value: str) -> str:
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = old.splitlines()
    replacement = f"{key}={value}"
    found = False
    output: list[str] = []
    for line in lines:
        if line.startswith(f"{key}="):
            if not found:
                output.append(replacement)
                found = True
        else:
            output.append(line)
    if not found:
        output.append(replacement)
    new = "\n".join(output).rstrip("\n") + "\n"
    if old != new:
        atomic_write(path, new, mode=0o600)
    return old


def replace_compose_image(compose: str, image: str) -> str:
    pattern = re.compile(r"(?m)^(\s+image:\s+)(\S+)(\s*)$")
    matches = list(pattern.finditer(compose))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one compose image line, found {len(matches)}")
    match = matches[0]
    return (
        compose[: match.start()]
        + f"{match.group(1)}{image}{match.group(3)}"
        + compose[match.end() :]
    )


def gui_health(bind_address: str, expected_power: Version) -> bool:
    request = urllib.request.Request(f"http://{bind_address}:8008/healthz")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return False
    try:
        reported_version = parse_version(str(payload.get("version", "")))
    except ValueError:
        return False
    return (
        response.status == 200
        and payload.get("status") == "ok"
        and reported_version == expected_power
    )


def wait_for_gui(service: str, bind_address: str, expected_power: Version) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        status = docker_output(
            ("docker", "inspect", service, "--format", "{{.State.Status}}"), timeout=20
        )
        health = docker_output(
            (
                "docker",
                "inspect",
                service,
                "--format",
                "{{if .State.Health}}{{.State.Health.Status}}{{end}}",
            ),
            timeout=20,
        )
        if status == "running" and health == "healthy" and gui_health(bind_address, expected_power):
            return
        time.sleep(2)
    raise RuntimeError("GUI container did not reach healthy POWER version state")


def update_gui(config: Config, release: Release, wheel: Path) -> list[str]:
    if not config.update_gui:
        return []
    service = config.gui_service
    current = container_power_version(service)
    if current == release.version:
        LOG.info("GUI service %s already embeds POWER %s", service, version_text(release.version))
        return []
    if config.dry_run:
        LOG.info("dry-run: would rebuild GUI service %s from %s", service, config.gui_base_image)
        return []
    compose_dir = config.gui_compose_dir
    compose_path = compose_dir / "docker-compose.yml"
    env_path = compose_dir / ".env"
    if not compose_path.exists():
        return [f"GUI compose file is missing: {compose_path}"]
    old_compose = compose_path.read_text(encoding="utf-8")
    old_env = env_path.read_text(encoding="utf-8") if env_path.exists() else None
    image = f"local/power-gui:{version_text(release.version)}"
    try:
        base_ref = image_digest(config.gui_base_image)
        with tempfile.TemporaryDirectory(
            prefix="power-gui-build-", dir=config.state_dir
        ) as build_dir_name:
            build_dir = Path(build_dir_name)
            shutil.copy2(wheel, build_dir / release.wheel_name)
            dockerfile = (
                f"FROM {base_ref}\n"
                "USER root\n"
                f"COPY {release.wheel_name} /tmp/{release.wheel_name}\n"
                f"RUN python -m pip install --no-cache-dir --no-deps --force-reinstall /tmp/{release.wheel_name} "
                "&& rm -f /tmp/"
                f"{release.wheel_name}\n"
                "USER 10001:10001\n"
            )
            (build_dir / "Dockerfile").write_text(dockerfile, encoding="utf-8")
            run_command(
                ("docker", "build", "--pull=false", "--tag", image, str(build_dir)), timeout=900
            )
        verified = docker_output(
            (
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "python",
                image,
                "-c",
                "import importlib.metadata as m; print(m.version('power-framework'))",
            ),
            timeout=60,
        )
        if parse_version(verified) != release.version:
            raise RuntimeError(f"derived GUI image readback={verified}")
        atomic_write(compose_path, replace_compose_image(old_compose, image))
        update_compose_env(env_path, "POWER_GUI_BIND_ADDRESS", config.gui_bind_address)
        run_command(("docker", "compose", "config", "--quiet"), cwd=compose_dir, timeout=60)
        run_command(
            ("docker", "compose", "up", "-d", "--no-build", service), cwd=compose_dir, timeout=300
        )
        wait_for_gui(service, config.gui_bind_address, release.version)
        LOG.info(
            "GUI service %s now runs %s with POWER %s",
            service,
            image,
            version_text(release.version),
        )
        return []
    except Exception as exc:
        LOG.error("GUI update failed; restoring previous compose image: %s", redact(str(exc)))
        atomic_write(compose_path, old_compose)
        if old_env is None:
            env_path.unlink(missing_ok=True)
        else:
            atomic_write(env_path, old_env, mode=0o600)
        run_command(("docker", "compose", "config", "--quiet"), cwd=compose_dir, timeout=60)
        run_command(
            ("docker", "compose", "up", "-d", "--no-build", service), cwd=compose_dir, timeout=300
        )
        raise


def acquire_lock(path: Path) -> object:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError("another power updater run is active") from exc
    return handle


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("/etc/power-updater/power-updater.env"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = Config.load(args.config, dry_run=args.dry_run)
    config.state_dir.mkdir(parents=True, exist_ok=True)
    lock = acquire_lock(config.state_dir / "updater.lock")
    try:
        release = fetch_release(config.repo)
        LOG.info("latest stable release is %s", release.tag)
        wheel = (
            download_verified_wheel(release, config.state_dir)
            if not config.dry_run
            else config.state_dir / release.wheel_name
        )
        failures = update_skills(config, release)
        failures.extend(update_python_targets(config, release, wheel))
        try:
            failures.extend(update_gui(config, release, wheel))
        except Exception as exc:
            failures.append(f"GUI: {redact(str(exc))}")
        if failures:
            for failure in failures:
                LOG.error("update failure: %s", redact(failure))
            return 1
        LOG.info("POWER updater completed successfully at %s", release.tag)
        return 0
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
