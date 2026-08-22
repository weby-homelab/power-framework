"""
Pytest fixtures for P.O.W.E.R. tests.

Provides temporary vault directories with sample notes for testing.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path  # noqa: TC003

import pytest


class DeterministicEmbedder:
    """Small lexical embedder for mandatory offline semantic contract tests.

    Stable SHA-256 buckets make the fixture independent of Python's randomized
    ``hash()`` seed while retaining enough shared-token signal for dedup and
    contradiction scenarios. It is deliberately not a production model.
    """

    dimension = 128

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in re.findall(r"\w+", text.casefold()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            vector[index] += 1.0
        return vector

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        del batch_size
        return [self.embed(text) for text in texts]


class _FakeEncoding:
    def __init__(self, ids: list[int], attention_mask: list[int]) -> None:
        self.ids = ids
        self.attention_mask = attention_mask


class FakeTokenizer:
    """Minimal tokenizer surface consumed by ``BGEM3OnnxManager`` tests."""

    def enable_truncation(self, max_length: int) -> None:
        return None

    def enable_padding(self) -> None:
        return None

    def encode_batch(self, texts: list[str]) -> list[_FakeEncoding]:
        token_rows = []
        for text in texts:
            tokens = re.findall(r"\w+", text.casefold()) or ["<empty>"]
            ids = [
                int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:4], "big") % 10_000
                for token in tokens
            ]
            token_rows.append(ids)
        width = max(map(len, token_rows), default=1)
        return [
            _FakeEncoding(ids + [0] * (width - len(ids)), [1] * len(ids) + [0] * (width - len(ids)))
            for ids in token_rows
        ]


class FakeSession:
    """Deterministic ONNX-session double with the production output shape."""

    def get_providers(self) -> list[str]:
        return ["CPUExecutionProvider"]

    def run(self, output_names: list[str], inputs: dict[str, object]) -> list[list[list[float]]]:
        del output_names
        rows = inputs["input_ids"]
        vectors: list[list[float]] = []
        for row in rows:  # type: ignore[union-attr]
            seed = int(sum(int(value) for value in row)) % 997
            vectors.append([float(seed + (index % 17)) for index in range(1024)])
        return [vectors]


@pytest.fixture
def deterministic_embedder() -> DeterministicEmbedder:
    """Return the explicit fake embedder used by hermetic semantic tests."""

    return DeterministicEmbedder()


@pytest.fixture
def fake_bge_manager():
    """Return a BGE manager with injected tokenizer/session doubles."""

    from power_framework.experimental.embeddings import BGEM3OnnxManager

    manager = BGEM3OnnxManager()
    manager._session = FakeSession()
    manager._tokenizer = FakeTokenizer()
    manager.active_provider = "CPUExecutionProvider"
    return manager


@pytest.fixture(autouse=True)
def isolated_search_db(tmp_path: Path, monkeypatch):
    """Isolate the shared search index DB so tests don't cross-contaminate.

    Each test gets its own power_search.db in a temp dir (Performance Plan §1
    background indexer uses POWER_SEARCH_DB when set).
    """
    db = tmp_path / "power_search.db"
    monkeypatch.setenv("POWER_SEARCH_DB", str(db))
    return db


@pytest.fixture
def sample_vault(tmp_path: Path) -> Path:
    """Create a sample vault directory with valid OKF notes."""
    vault = tmp_path / "test_vault"
    vault.mkdir()

    (vault / "01_Projects").mkdir()
    (vault / "02_Areas").mkdir()
    (vault / "03_Resources").mkdir()
    (vault / "06_Daily_Logs").mkdir()

    project_note = vault / "01_Projects" / "TestProject.md"
    project_note.write_text(
        """---
type: Project
title: "Test Project"
description: "A sample project note for testing"
timestamp: 2026-01-01T00:00:00
---

# Test Project

This is a test project note.
""",
        encoding="utf-8",
    )

    area_note = vault / "02_Areas" / "TestArea.md"
    area_note.write_text(
        """---
type: Area
title: "Test Area"
description: "A sample area note for testing"
timestamp: 2026-01-01T00:00:00
---

# Test Area

This is a test area note.
""",
        encoding="utf-8",
    )

    resource_note = vault / "03_Resources" / "TestResource.md"
    resource_note.write_text(
        """---
type: Resource
title: "Test Resource"
description: "A sample resource note for testing"
resource: "https://example.com"
tags: [test, sample]
timestamp: 2026-01-01T00:00:00
---

# Test Resource

This is a test resource note.

Links to other notes:
- [[TestProject]]
- [[TestArea]]
""",
        encoding="utf-8",
    )

    daily_log = vault / "06_Daily_Logs" / "2026-01-01.md"
    daily_log.write_text(
        """---
type: Daily Log
title: "Daily Log 2026-01-01"
description: "Sample daily log"
timestamp: 2026-01-01T00:00:00
---

# Daily Log

Sample daily log content.
""",
        encoding="utf-8",
    )

    nested_project = vault / "01_Projects" / "Weby-QRank"
    nested_project.mkdir()
    nested_note = nested_project / "Architecture.md"
    nested_note.write_text(
        """---
type: Project
title: "Weby-QRank Architecture"
description: "Nested project architecture note"
tags: [architecture, nested]
timestamp: 2026-01-01T00:00:00
---

# Weby-QRank Architecture

Nested sub-project note.
""",
        encoding="utf-8",
    )

    return vault


@pytest.fixture
def vault_with_issues(tmp_path: Path) -> Path:
    """Create a vault with various issues for linting tests."""
    vault = tmp_path / "broken_vault"
    vault.mkdir()

    (vault / "01_Projects").mkdir()
    (vault / "03_Resources").mkdir()

    no_frontmatter = vault / "01_Projects" / "NoFrontmatter.md"
    no_frontmatter.write_text("# No Frontmatter\n\nThis note has no YAML frontmatter.\n")

    no_type = vault / "01_Projects" / "NoType.md"
    no_type.write_text(
        """---
title: "Missing Type"
description: "This note is missing the type field"
timestamp: 2026-01-01T00:00:00
---

# Missing Type

This note has frontmatter but no type field.
"""
    )

    broken_link = vault / "03_Resources" / "BrokenLink.md"
    broken_link.write_text(
        """---
type: Resource
title: "Broken Link"
description: "This note has a broken link"
timestamp: 2026-01-01T00:00:00
---

# Broken Link

This links to [[NonExistentNote]] which does not exist.
"""
    )

    orphan = vault / "03_Resources" / "Orphan.md"
    orphan.write_text(
        """---
type: Resource
title: "Orphan Note"
description: "This note has no inbound links"
timestamp: 2026-01-01T00:00:00
---

# Orphan

Nobody links to this note.
"""
    )

    stale_note = vault / "03_Resources" / "StaleNote.md"
    stale_note.write_text(
        """---
type: Resource
title: "Stale Note"
description: "This note has an expiry date in the past"
timestamp: 2026-01-01T00:00:00
expiry: 2020-01-01
---

# Stale Note

This note expired long ago and should be flagged.
"""
    )

    return vault


@pytest.fixture
def valid_note_content() -> str:
    """Return valid OKF frontmatter content."""
    return """---
type: Project
title: "Valid Note"
description: "A valid note for testing"
resource: "https://github.com/example"
tags: [test, valid]
timestamp: 2026-01-01T12:00:00
---

# Valid Note

This is valid content.
"""


@pytest.fixture
def invalid_note_content() -> str:
    """Return content with invalid frontmatter."""
    return """---
title: "Missing Type"
description: "This is missing the type field"
timestamp: 2026-01-01T12:00:00
---

# Invalid Note

This note is missing the required type field.
"""
