import gzip
import io
import struct
import tarfile
from pathlib import Path

import pytest

from scripts.normalize_sdist import normalize_sdist, source_date_epoch


def _write_archive(
    path: Path,
    members: list[tuple[tarfile.TarInfo, bytes | None]],
    gzip_mtime: int,
) -> None:
    with (
        path.open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=gzip_mtime) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
        for member, payload in members:
            archive.addfile(member, io.BytesIO(payload) if payload is not None else None)


def _member(
    name: str,
    member_type: bytes,
    *,
    mode: int,
    mtime: float,
    uid: int,
    gid: int,
    uname: str,
    gname: str,
    linkname: str = "",
    pax_headers: dict[str, str] | None = None,
) -> tarfile.TarInfo:
    result = tarfile.TarInfo(name)
    result.type = member_type
    result.mode = mode
    result.mtime = mtime
    result.uid = uid
    result.gid = gid
    result.uname = uname
    result.gname = gname
    result.linkname = linkname
    result.pax_headers = pax_headers or {}
    return result


def test_normalize_sdist_is_order_and_metadata_independent(tmp_path: Path) -> None:
    common = {
        "mode": 0o640,
        "mtime": 1_700_000_001.75,
        "uid": 123,
        "gid": 456,
        "uname": "builder-a",
        "gname": "builder-b",
    }
    regular = _member("pkg/z.txt", tarfile.REGTYPE, **common, pax_headers={"atime": "1"})
    regular.size = 5
    directory = _member("pkg", tarfile.DIRTYPE, **common)
    directory.mode = 0o755
    symlink = _member("pkg/link", tarfile.SYMTYPE, **common, linkname="z.txt")
    hardlink = _member("pkg/hard", tarfile.LNKTYPE, **common, linkname="pkg/z.txt")
    members = [(regular, b"hello"), (symlink, None), (directory, None), (hardlink, None)]
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    _write_archive(first, members, gzip_mtime=1_700_000_002)
    _write_archive(second, list(reversed(members)), gzip_mtime=1_700_000_003)

    normalize_sdist(first, timestamp=1_700_000_000)
    normalize_sdist(second, timestamp=1_700_000_000)

    assert first.read_bytes() == second.read_bytes()
    assert struct.unpack("<L", first.read_bytes()[4:8])[0] == 1_700_000_000
    with (
        gzip.open(first, "rb") as compressed,
        tarfile.open(fileobj=compressed, mode="r:") as archive,
    ):
        normalized = archive.getmembers()
        assert [member.name for member in normalized] == [
            "pkg",
            "pkg/hard",
            "pkg/link",
            "pkg/z.txt",
        ]
        for member in normalized:
            assert member.mtime == 1_700_000_000
            assert member.uid == 0
            assert member.gid == 0
            assert member.uname == "root"
            assert member.gname == "root"
        assert normalized[0].mode == 0o755
        assert normalized[1].islnk()
        assert normalized[1].linkname == "pkg/z.txt"
        assert normalized[2].issym()
        assert normalized[2].linkname == "z.txt"
        assert normalized[3].mode == 0o640
        assert normalized[3].pax_headers == {}
        payload = archive.extractfile(normalized[3])
        assert payload is not None
        assert payload.read() == b"hello"


def test_normalize_sdist_defaults_to_epoch_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    member = _member(
        "pkg/file.txt",
        tarfile.REGTYPE,
        mode=0o644,
        mtime=123.5,
        uid=1,
        gid=2,
        uname="one",
        gname="two",
    )
    member.size = 4
    archive_path = tmp_path / "archive.tar.gz"
    _write_archive(archive_path, [(member, b"data")], gzip_mtime=123)
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)

    assert source_date_epoch() == 0
    normalize_sdist(archive_path)

    with (
        gzip.open(archive_path, "rb") as compressed,
        tarfile.open(fileobj=compressed, mode="r:") as archive,
    ):
        first = archive.next()
        assert first is not None
        assert first.mtime == 0


@pytest.mark.parametrize(
    ("raw_value", "message"),
    [("not-an-integer", "must be an integer"), ("-1", "must be between")],
)
def test_source_date_epoch_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
    message: str,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", raw_value)

    with pytest.raises(ValueError, match=message):
        source_date_epoch()


def test_normalize_sdist_rejects_special_files(tmp_path: Path) -> None:
    fifo = _member(
        "pkg/fifo",
        tarfile.FIFOTYPE,
        mode=0o644,
        mtime=123,
        uid=1,
        gid=2,
        uname="one",
        gname="two",
    )
    archive_path = tmp_path / "archive.tar.gz"
    _write_archive(archive_path, [(fifo, None)], gzip_mtime=123)
    original = archive_path.read_bytes()

    with pytest.raises(ValueError, match="unsupported tar member type"):
        normalize_sdist(archive_path, timestamp=0)

    assert archive_path.read_bytes() == original
    assert not list(tmp_path.glob(".archive.tar.gz.*.tmp"))
