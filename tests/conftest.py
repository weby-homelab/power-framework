"""
Pytest fixtures for P.O.W.E.R. tests.

Provides temporary vault directories with sample notes for testing.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest


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
