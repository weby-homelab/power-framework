"""Tests for shared filesystem helpers."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from power_framework.core.constants import INDEX_MAX_BYTES
from power_framework.core.indexer import _generate_catalog_pages
from power_framework.core.utils import atomic_write


class TestAtomicWrite:
    """A byte-bounded caller can only trust a byte-faithful writer."""

    def test_write_is_byte_identical_to_content(self, tmp_path: Path):
        content = "---\ntype: Resource\n---\n\n# Title\n\nbody\n"
        target = tmp_path / "note.md"

        atomic_write(target, content)

        # Text mode with the default newline=None maps each "\n" to os.linesep,
        # so on Windows the artifact is one byte per line larger than what the
        # caller measured. Every byte-length contract in the codebase depends on
        # this equality holding.
        assert target.read_bytes() == content.encode("utf-8")

    def test_written_catalog_page_respects_the_declared_limit(self, tmp_path: Path):
        notes = [
            {
                "rel_path": f"03_Resources/wiki/batch/Note {index}.md",
                "title": "N" * (1 + index % 37),
                "description": "d" * (1 + index % 53),
                "note_type": "Resource",
                "tags": [],
                "timestamp": "2026-01-01",
                "filename": f"Note {index}.md",
                "owner": "",
                "status": "",
                "expiry": "",
                "related": [],
            }
            for index in range(2_000)
        ]

        pages = _generate_catalog_pages("03_Resources/wiki/batch", notes)
        assert len(pages) > 1, "fixture must paginate for the bound to mean anything"

        oversized = {}
        for filename, content in pages.items():
            target = tmp_path / filename
            atomic_write(target, content)
            size = target.stat().st_size
            if size > INDEX_MAX_BYTES:
                oversized[filename] = size

        # The in-memory bound is already asserted by the renderer; this checks
        # the artifact that actually lands on disk.
        assert not oversized, f"pages exceed INDEX_MAX_BYTES on disk: {oversized}"
