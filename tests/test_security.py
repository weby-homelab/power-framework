"""Tests for security utilities (Path Traversal, atomic writes, etc.)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from power_framework.core.utils import (
    atomic_write,
    atomic_write_in_vault,
    clean_note_name,
    create_backup,
    is_excluded_dir,
    is_excluded_orphan,
    resolve_path_in_vault,
    resolve_vault_path,
    validate_vault_path,
)


class TestValidateVaultPath:
    """Tests for path validation and traversal protection."""

    def test_valid_path(self, tmp_path: Path):
        result = validate_vault_path(str(tmp_path))
        assert result == tmp_path.resolve()

    def test_nonexistent_path(self):
        with pytest.raises(FileNotFoundError):
            validate_vault_path("/nonexistent/path/that/does/not/exist")

    def test_file_not_directory(self, tmp_path: Path):
        file_path = tmp_path / "file.txt"
        file_path.write_text("test")
        with pytest.raises(NotADirectoryError):
            validate_vault_path(str(file_path))

    def test_allowed_root_within(self, tmp_path: Path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        result = validate_vault_path(str(sub), allowed_root=str(tmp_path))
        assert result == sub.resolve()

    def test_allowed_root_escape(self, tmp_path: Path):
        with pytest.raises(ValueError, match="Path traversal"):
            validate_vault_path("/etc", allowed_root=str(tmp_path))


class TestResolveVaultPath:
    """Tests for vault path resolution from arguments/env/fallback."""

    def test_explicit_argument(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("POWER_VAULT_DIR", raising=False)
        arguments = {"vault_path": str(tmp_path)}
        result = resolve_vault_path(arguments)
        assert result == tmp_path.resolve()

    def test_env_variable(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("POWER_VAULT_DIR", str(tmp_path))
        arguments = {}
        result = resolve_vault_path(arguments)
        assert result == tmp_path.resolve()

    def test_fallback_cwd(self, monkeypatch):
        monkeypatch.delenv("POWER_VAULT_DIR", raising=False)
        arguments = {}
        result = resolve_vault_path(arguments)
        assert result == Path(os.getcwd()).resolve()

    def test_argument_takes_priority(self, tmp_path: Path, monkeypatch):
        other = tmp_path / "other"
        other.mkdir()
        monkeypatch.setenv("POWER_VAULT_DIR", str(other))
        arguments = {"vault_path": str(tmp_path)}
        result = resolve_vault_path(arguments)
        assert result == tmp_path.resolve()


class TestAtomicWrite:
    """Tests for atomic file writing."""

    def test_creates_file(self, tmp_path: Path):
        filepath = tmp_path / "test.txt"
        atomic_write(filepath, "hello world")
        assert filepath.read_text() == "hello world"

    def test_overwrites_existing(self, tmp_path: Path):
        filepath = tmp_path / "test.txt"
        filepath.write_text("old content")
        atomic_write(filepath, "new content")
        assert filepath.read_text() == "new content"

    def test_creates_parent_dirs(self, tmp_path: Path):
        filepath = tmp_path / "sub" / "dir" / "test.txt"
        atomic_write(filepath, "nested content")
        assert filepath.read_text() == "nested content"

    def test_no_temp_file_left(self, tmp_path: Path):
        filepath = tmp_path / "test.txt"
        atomic_write(filepath, "content")
        temps = list(tmp_path.glob(".test.txt.*.tmp"))
        assert len(temps) == 0


class TestVaultRelativeWritePaths:
    """Tests for centralized validation of untrusted note paths."""

    _allowed_directories = ("01_Projects", "06_Daily_Logs")

    def test_allows_existing_nested_markdown_path(self, sample_vault: Path):
        target = resolve_path_in_vault(
            sample_vault,
            "01_Projects/Weby-QRank/Architecture.md",
            self._allowed_directories,
        )
        assert target == sample_vault / "01_Projects" / "Weby-QRank" / "Architecture.md"

    @pytest.mark.parametrize(
        "untrusted_path",
        [
            "../../outside.md",
            "01_Projects/../outside.md",
            "%2e%2e/outside.md",
            "C:\\outside.md",
            "01_Projects\\outside.md",
            "01_Projects/outside.txt",
        ],
    )
    def test_rejects_unsafe_untrusted_paths(self, sample_vault: Path, untrusted_path: str):
        with pytest.raises(ValueError, match=r"path|Path|Markdown|Symlink|Target"):
            resolve_path_in_vault(sample_vault, untrusted_path, self._allowed_directories)

    def test_rejects_absolute_path(self, sample_vault: Path, tmp_path: Path):
        outside_path = tmp_path.parent / "outside.md"

        with pytest.raises(ValueError, match="Absolute"):
            resolve_path_in_vault(sample_vault, str(outside_path), self._allowed_directories)

    def test_rejects_symlinked_parent_that_escapes_vault(self, sample_vault: Path, tmp_path: Path):
        outside_directory = tmp_path / "outside"
        outside_directory.mkdir()
        escape_link = sample_vault / "01_Projects" / "escape"
        escape_link.symlink_to(outside_directory, target_is_directory=True)

        with pytest.raises(ValueError, match="Target"):
            resolve_path_in_vault(
                sample_vault,
                "01_Projects/escape/Outside.md",
                self._allowed_directories,
            )

    def test_atomic_write_rejects_symlinked_note_without_changing_sentinel(
        self,
        sample_vault: Path,
        tmp_path: Path,
    ):
        sentinel = tmp_path / "outside.md"
        sentinel.write_text("do not modify", encoding="utf-8")
        target_link = sample_vault / "01_Projects" / "Escape.md"
        target_link.symlink_to(sentinel)

        with pytest.raises(ValueError, match="Symlink"):
            atomic_write_in_vault(
                sample_vault,
                "01_Projects/Escape.md",
                "unsafe content",
                allowed_directories=self._allowed_directories,
            )

        assert sentinel.read_text(encoding="utf-8") == "do not modify"

    def test_atomic_write_creates_note_inside_vault(self, sample_vault: Path):
        target = atomic_write_in_vault(
            sample_vault,
            "01_Projects/Safe.md",
            "safe content",
            allowed_directories=self._allowed_directories,
        )
        assert target.read_text(encoding="utf-8") == "safe content"


class TestCreateBackup:
    """Tests for backup creation."""

    def test_creates_backup(self, tmp_path: Path):
        filepath = tmp_path / "test.md"
        filepath.write_text("original content")
        backup = create_backup(filepath)
        assert backup is not None
        assert backup.exists()
        assert backup.read_text() == "original content"

    def test_nonexistent_source(self, tmp_path: Path):
        filepath = tmp_path / "nonexistent.md"
        backup = create_backup(filepath)
        assert backup is None

    def test_custom_backup_dir(self, tmp_path: Path):
        filepath = tmp_path / "test.md"
        filepath.write_text("content")
        backup_dir = tmp_path / "my_backups"
        backup = create_backup(filepath, backup_dir=backup_dir)
        assert backup is not None
        assert str(backup).startswith(str(backup_dir))


class TestCleanNoteName:
    """Tests for note name normalization."""

    def test_removes_extension(self):
        assert clean_note_name("Test.md") == "test"

    def test_strips_whitespace(self):
        assert clean_note_name("  Test  .md") == "test"

    def test_lowercase(self):
        assert clean_note_name("MyNote.md") == "mynote"

    def test_complex_name(self):
        assert clean_note_name("My Complex Note.md") == "my complex note"


class TestExclusionHelpers:
    """Tests for directory and file exclusion logic."""

    def test_excluded_dirs(self):
        assert is_excluded_dir(".git")
        assert is_excluded_dir("05_Templates")
        assert is_excluded_dir("scratch")
        assert is_excluded_dir(".system_generated")
        assert is_excluded_dir(".agents")
        assert not is_excluded_dir("01_Projects")
        assert not is_excluded_dir("brain")

    def test_excluded_orphan_files(self):
        assert is_excluded_orphan("README.md", "README.md")
        assert is_excluded_orphan("index.md", "index.md")
        assert is_excluded_orphan("log.md", "log.md")
        assert is_excluded_orphan("test.md", "06_Daily_Logs/test.md")
        assert not is_excluded_orphan("test.md", "01_Projects/test.md")


def test_atomic_write_exception(tmp_path: Path):
    from unittest.mock import patch

    target = tmp_path / "test.txt"
    with (
        patch("os.fdopen", side_effect=OSError("Disk write error")),
        pytest.raises(OSError, match="Disk write error"),
    ):
        atomic_write(target, "content")


def test_resolve_path_in_vault_extra_checks(tmp_path: Path):
    with pytest.raises(ValueError, match="Invalid vault-relative path"):
        resolve_path_in_vault(tmp_path, "note\x01.md")

    with pytest.raises(ValueError, match="Path is outside the allowed vault directories"):
        resolve_path_in_vault(tmp_path, "02_Areas/note.md", allowed_directories=("01_Projects",))
