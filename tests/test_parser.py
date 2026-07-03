"""Tests for YAML frontmatter parser."""

from __future__ import annotations

from datetime import datetime

from power_framework.core.models import OKFMetadata
from power_framework.core.parser import (
    build_frontmatter,
    extract_frontmatter_raw,
    has_frontmatter,
    has_type_field,
    parse_frontmatter,
    validate_metadata,
)


class TestExtractFrontmatterRaw:
    """Tests for raw frontmatter extraction."""

    def test_valid_frontmatter(self, valid_note_content):
        raw = extract_frontmatter_raw(valid_note_content)
        assert raw is not None
        assert "type: Project" in raw

    def test_no_frontmatter(self):
        content = "# Just a heading\n\nNo frontmatter here."
        assert extract_frontmatter_raw(content) is None

    def test_malformed_frontmatter(self):
        content = "---\ntype: Project\nNo closing delimiter"
        assert extract_frontmatter_raw(content) is None

    def test_windows_line_endings(self):
        content = "---\r\ntype: Project\r\ntitle: Test\r\n---\r\nContent"
        raw = extract_frontmatter_raw(content)
        assert raw is not None
        assert "type: Project" in raw


class TestParseFrontmatter:
    """Tests for YAML parsing."""

    def test_valid_yaml(self, valid_note_content):
        data = parse_frontmatter(valid_note_content)
        assert data is not None
        assert data["type"] == "Project"
        assert data["title"] == "Valid Note"

    def test_invalid_yaml(self):
        content = "---\n: invalid: yaml: [broken\n---\nContent"
        data = parse_frontmatter(content)
        assert data is None or not isinstance(data, dict)

    def test_no_frontmatter(self):
        assert parse_frontmatter("# No frontmatter") is None

    def test_list_as_frontmatter(self):
        content = "---\n- item1\n- item2\n---\nContent"
        data = parse_frontmatter(content)
        assert data is None


class TestValidateMetadata:
    """Tests for Pydantic schema validation."""

    def test_valid_metadata(self, valid_note_content):
        meta = validate_metadata(valid_note_content)
        assert meta is not None
        assert meta.type == "Project"
        assert meta.title == "Valid Note"
        assert meta.resource == "https://github.com/example"
        assert meta.tags == ["test", "valid"]

    def test_invalid_metadata_missing_type(self, invalid_note_content):
        meta = validate_metadata(invalid_note_content)
        assert meta is None

    def test_no_frontmatter(self):
        assert validate_metadata("# No frontmatter") is None


class TestHasFrontmatter:
    """Tests for frontmatter detection."""

    def test_has_frontmatter(self, valid_note_content):
        assert has_frontmatter(valid_note_content) is True

    def test_no_frontmatter(self):
        assert has_frontmatter("# Just content") is False


class TestHasTypeField:
    """Tests for type field detection."""

    def test_has_type(self, valid_note_content):
        assert has_type_field(valid_note_content) is True

    def test_missing_type(self, invalid_note_content):
        assert has_type_field(invalid_note_content) is False

    def test_no_frontmatter(self):
        assert has_type_field("# No frontmatter") is False


class TestBuildFrontmatter:
    """Tests for frontmatter generation."""

    def test_build_minimal(self):
        meta = OKFMetadata(
            type="Project",
            title="Test",
            description="A test note",
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
        )
        result = build_frontmatter(meta)
        assert result.startswith("---")
        assert result.endswith("---")
        assert "type: Project" in result
        assert 'title: "Test"' in result
        assert 'description: "A test note"' in result

    def test_build_full(self):
        meta = OKFMetadata(
            type="Resource",
            title="Full Note",
            description="A full note",
            resource="https://example.com",
            tags=["tag1", "tag2"],
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
        )
        result = build_frontmatter(meta)
        assert 'resource: "https://example.com"' in result
        assert "tags: [tag1, tag2]" in result

    def test_escape_quotes(self):
        meta = OKFMetadata(
            type="Project",
            title='Note with "quotes"',
            description="Test",
            timestamp=datetime(2026, 1, 1),
        )
        result = build_frontmatter(meta)
        assert '\\"quotes\\"' in result
