#!/usr/bin/env python3
"""Rewrite a source distribution with deterministic tar and gzip metadata.

The build backend may include generated directories whose fractional mtimes
vary between builds. Rebuilding the tar stream here keeps file bytes and
ordinary links intact while removing host-dependent metadata fields.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import os
import stat
import tarfile
import tempfile
from pathlib import Path
from typing import BinaryIO

DEFAULT_MTIME = 0
FIXED_UID = 0
FIXED_GID = 0
FIXED_UNAME = "root"
FIXED_GNAME = "root"
MAX_GZIP_MTIME = 2**32 - 1
SUPPORTED_MEMBER_TYPES = ("regular file", "directory", "symbolic link", "hard link")


def source_date_epoch(value: str | None = None) -> int:
    """Return a validated archive timestamp from *value* or the environment."""

    raw_value = os.environ.get("SOURCE_DATE_EPOCH") if value is None else value
    if raw_value is None:
        return DEFAULT_MTIME

    try:
        timestamp = int(raw_value, 10)
    except ValueError as exc:
        raise ValueError("SOURCE_DATE_EPOCH must be an integer") from exc
    if not 0 <= timestamp <= MAX_GZIP_MTIME:
        raise ValueError(f"SOURCE_DATE_EPOCH must be between 0 and {MAX_GZIP_MTIME}")
    return timestamp


def _member_sort_key(member: tarfile.TarInfo) -> bytes:
    """Sort names by their UTF-8 representation, independent of locale."""

    return member.name.encode("utf-8", "surrogateescape")


def _supported_member(member: tarfile.TarInfo) -> bool:
    return member.isreg() or member.isdir() or member.issym() or member.islnk()


def _canonical_mode(member: tarfile.TarInfo) -> int:
    """Return a portable mode while retaining executable-file semantics."""

    if member.issym():
        # Tar extractors ignore symlink permission bits; retaining the normal
        # symlink mode makes that intent explicit without following the link.
        return 0o777
    if member.isdir():
        return 0o755
    return 0o755 if member.mode & 0o111 else 0o644


def _normalize_member(member: tarfile.TarInfo, timestamp: int) -> tarfile.TarInfo:
    """Copy a member and replace metadata that can vary between build hosts."""

    if not _supported_member(member):
        raise ValueError(
            f"unsupported tar member type for {member.name!r}; "
            f"expected one of {', '.join(SUPPORTED_MEMBER_TYPES)}"
        )

    normalized = copy.copy(member)
    normalized.mtime = timestamp
    normalized.uid = FIXED_UID
    normalized.gid = FIXED_GID
    normalized.uname = FIXED_UNAME
    normalized.gname = FIXED_GNAME
    normalized.mode = _canonical_mode(member)
    normalized.devmajor = 0
    normalized.devminor = 0
    # TarInfo.name and TarInfo.linkname regenerate required PAX path fields.
    # Other PAX fields may contain host-specific timestamps.
    normalized.pax_headers = {}
    return normalized


def _write_member(
    destination: tarfile.TarFile,
    source: tarfile.TarFile,
    member: tarfile.TarInfo,
    timestamp: int,
) -> None:
    normalized = _normalize_member(member, timestamp)
    if not normalized.isreg():
        destination.addfile(normalized)
        return

    source_file = source.extractfile(member)
    if source_file is None:
        raise ValueError(f"tar member {member.name!r} has no readable file payload")
    with source_file:
        destination.addfile(normalized, source_file)


def _ordered_members(members: list[tarfile.TarInfo]) -> list[tarfile.TarInfo]:
    """Sort members deterministically while placing hard-link targets first."""

    by_name = {member.name: member for member in members}
    depths: dict[str, int] = {}
    resolving: set[str] = set()

    def dependency_depth(member: tarfile.TarInfo) -> int:
        cached = depths.get(member.name)
        if cached is not None:
            return cached
        if not member.islnk():
            depths[member.name] = 0
            return 0
        if member.name in resolving:
            raise ValueError(f"cyclic hard-link dependency at {member.name!r}")
        target = by_name.get(member.linkname)
        if target is None:
            raise ValueError(
                f"hard-link member {member.name!r} targets missing member {member.linkname!r}"
            )
        resolving.add(member.name)
        depth = dependency_depth(target) + 1
        resolving.remove(member.name)
        depths[member.name] = depth
        return depth

    return sorted(
        members,
        key=lambda member: (dependency_depth(member), _member_sort_key(member)),
    )


def _normalize_tar(source: BinaryIO, destination: BinaryIO, timestamp: int) -> None:
    with (
        tarfile.open(fileobj=source, mode="r:gz") as source_tar,
        gzip.GzipFile(
            fileobj=destination,
            mode="wb",
            filename="",
            mtime=timestamp,
            compresslevel=9,
        ) as gzip_stream,
        tarfile.open(fileobj=gzip_stream, mode="w", format=tarfile.PAX_FORMAT) as destination_tar,
    ):
        for member in _ordered_members(source_tar.getmembers()):
            _write_member(destination_tar, source_tar, member, timestamp)


def normalize_sdist(path: Path, *, timestamp: int | None = None) -> None:
    """Normalize *path* in place, replacing it atomically on success."""

    resolved_timestamp = (
        source_date_epoch() if timestamp is None else source_date_epoch(str(timestamp))
    )
    original_mode = stat.S_IMODE(path.stat().st_mode)
    temporary_path: Path | None = None
    try:
        with (
            path.open("rb") as source,
            tempfile.NamedTemporaryFile(
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary,
        ):
            temporary_path = Path(temporary.name)
            _normalize_tar(source, temporary, resolved_timestamp)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_path, original_mode)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdists", nargs="+", type=Path, help="sdist .tar.gz files to normalize")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    timestamp = source_date_epoch()
    for path in args.sdists:
        normalize_sdist(path, timestamp=timestamp)


if __name__ == "__main__":
    main()
