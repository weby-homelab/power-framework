"""Tests for OKF metadata models (Pydantic schemas)."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from power_framework.core.models import (
    MAX_DESCRIPTION_LENGTH,
    MAX_TITLE_LENGTH,
    NoteFile,
    NoteStatus,
    NoteType,
    OKFMetadata,
)


class TestNoteType:
    """Tests for NoteType enum."""

    def test_all_types_exist(self):
        assert NoteType.PROJECT.value == "Project"
        assert NoteType.AREA.value == "Area"
        assert NoteType.RESOURCE.value == "Resource"
        assert NoteType.DAILY_LOG.value == "Daily Log"
        assert NoteType.ARCHIVE.value == "Archive"
        assert NoteType.SYSTEM_GUIDE.value == "System Guide"

    def test_type_count(self):
        assert len(NoteType) == 6


class TestNoteStatus:
    """Tests for NoteStatus enum."""

    def test_all_statuses_exist(self):
        assert NoteStatus.ACTIVE.value == "active"
        assert NoteStatus.REVIEW.value == "review"
        assert NoteStatus.ARCHIVED.value == "archived"

    def test_status_count(self):
        assert len(NoteStatus) == 3


class TestNoteFile:
    """Tests for NoteFile helper class."""

    def test_note_file_properties(self) -> None:
        meta = OKFMetadata(
            type="Project",
            title="My Project",
            description="Test description",
            timestamp=datetime(2026, 1, 1),
        )
        note = NoteFile(
            abs_path="/root/vault/01_Projects/MyProject.md",
            rel_path="01_Projects/MyProject.md",
            metadata=meta,
            raw_content="Some content",
        )
        assert note.abs_path == "/root/vault/01_Projects/MyProject.md"
        assert note.rel_path == "01_Projects/MyProject.md"
        assert note.metadata == meta
        assert note.raw_content == "Some content"
        assert note.filename == "MyProject.md"
        assert note.clean_name == "myproject"
        assert note.has_valid_metadata is True
        assert note.note_type == "Project"

    def test_note_file_no_metadata(self) -> None:
        note = NoteFile(
            abs_path="/root/vault/01_Projects/MyProject.md",
            rel_path="01_Projects/MyProject.md",
            metadata=None,
            raw_content="Some content",
        )
        assert note.has_valid_metadata is False
        assert note.note_type is None


class TestOKFMetadata:
    """Tests for OKFMetadata Pydantic model."""

    def test_valid_minimal(self):
        meta = OKFMetadata(
            type="Project",
            title="Test",
            description="A test note",
            timestamp=datetime(2026, 1, 1),
        )
        assert meta.type == "Project"
        assert meta.title == "Test"
        assert meta.description == "A test note"
        assert meta.resource is None
        assert meta.tags == []

    def test_valid_full(self):
        meta = OKFMetadata(
            type="Resource",
            title="Full Note",
            description="A fully populated note",
            resource="https://github.com/example/repo",
            tags=["python", "test"],
            timestamp=datetime(2026, 6, 15, 12, 0, 0),
        )
        assert meta.type == "Resource"
        assert meta.resource == "https://github.com/example/repo"
        assert meta.tags == ["python", "test"]

    def test_invalid_type(self):
        with pytest.raises(ValidationError):
            OKFMetadata(
                type="InvalidType",
                title="Test",
                description="Test",
                timestamp=datetime(2026, 1, 1),
            )

    def test_empty_title_rejected(self):
        with pytest.raises(ValidationError):
            OKFMetadata(
                type="Project",
                title="",
                description="Test",
                timestamp=datetime(2026, 1, 1),
            )

    def test_empty_description_rejected(self):
        with pytest.raises(ValidationError):
            OKFMetadata(
                type="Project",
                title="Test",
                description="",
                timestamp=datetime(2026, 1, 1),
            )

    def test_description_too_long(self):
        long_desc = "x" * (MAX_DESCRIPTION_LENGTH + 1)
        with pytest.raises(ValidationError):
            OKFMetadata(
                type="Project",
                title="Test",
                description=long_desc,
                timestamp=datetime(2026, 1, 1),
            )

    def test_title_too_long(self):
        long_title = "x" * (MAX_TITLE_LENGTH + 1)
        with pytest.raises(ValidationError):
            OKFMetadata(
                type="Project",
                title=long_title,
                description="Test",
                timestamp=datetime(2026, 1, 1),
            )

    def test_invalid_resource_url(self):
        with pytest.raises(ValidationError):
            OKFMetadata(
                type="Resource",
                title="Test",
                description="Test",
                resource="not-a-url",
                timestamp=datetime(2026, 1, 1),
            )

    def test_valid_resource_urls(self):
        for url in ["https://github.com", "http://example.com/path?q=1"]:
            meta = OKFMetadata(
                type="Resource",
                title="Test",
                description="Test",
                resource=url,
                timestamp=datetime(2026, 1, 1),
            )
            assert meta.resource == url

    def test_tags_stripped(self):
        meta = OKFMetadata(
            type="Project",
            title="Test",
            description="Test",
            tags=[" tag1 ", "", " tag2 "],
            timestamp=datetime(2026, 1, 1),
        )
        assert meta.tags == ["tag1", "tag2"]

    def test_extra_fields_ignored(self):
        meta = OKFMetadata(
            type="Project",
            title="Test",
            description="Test",
            timestamp=datetime(2026, 1, 1),
            unknown_field="should be ignored",
        )
        assert meta.type == "Project"

    def test_title_whitespace_stripped(self):
        meta = OKFMetadata(
            type="Project",
            title="  Test Title  ",
            description="Test",
            timestamp=datetime(2026, 1, 1),
        )
        assert meta.title == "Test Title"

    def test_related_field(self):
        meta = OKFMetadata(
            type="Resource",
            title="Test",
            description="Test",
            timestamp=datetime(2026, 1, 1),
            related=["01_Projects/OtherNote.md", "02_Areas/SomeArea.md"],
        )
        assert "01_Projects/OtherNote.md" in meta.related
        assert len(meta.related) == 2

    def test_related_empty_by_default(self):
        meta = OKFMetadata(
            type="Project",
            title="Test",
            description="Test",
            timestamp=datetime(2026, 1, 1),
        )
        assert meta.related == []

    def test_related_strips_whitespace(self):
        meta = OKFMetadata(
            type="Resource",
            title="Test",
            description="Test",
            timestamp=datetime(2026, 1, 1),
            related=["  path/to/note.md  ", "", " other.md "],
        )
        assert meta.related == ["path/to/note.md", "other.md"]

    def test_owner_field(self):
        meta = OKFMetadata(
            type="Project",
            title="Test",
            description="Test",
            timestamp=datetime(2026, 1, 1),
            owner="weby-homelab",
        )
        assert meta.owner == "weby-homelab"
        assert meta.status is None
        assert meta.expiry is None

    def test_status_field(self):
        meta = OKFMetadata(
            type="Project",
            title="Test",
            description="Test",
            timestamp=datetime(2026, 1, 1),
            status="review",
        )
        assert meta.status == "review"

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            OKFMetadata(
                type="Project",
                title="Test",
                description="Test",
                timestamp=datetime(2026, 1, 1),
                status="unknown_status",
            )

    def test_expiry_field(self):
        meta = OKFMetadata(
            type="Project",
            title="Test",
            description="Test",
            timestamp=datetime(2026, 1, 1),
            expiry=datetime(2026, 7, 1).date(),
        )
        assert meta.expiry is not None
        assert meta.expiry.isoformat() == "2026-07-01"

    def test_all_governance_fields(self):
        meta = OKFMetadata(
            type="Area",
            title="Governed Area",
            description="A fully governed note",
            timestamp=datetime(2026, 1, 1),
            owner="team-alpha",
            status="active",
            expiry=datetime(2027, 1, 1).date(),
            related=["03_Resources/Guide.md"],
        )
        assert meta.owner == "team-alpha"
        assert meta.status == "active"
        assert meta.expiry.isoformat() == "2027-01-01"
        assert "03_Resources/Guide.md" in meta.related
