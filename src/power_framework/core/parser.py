"""
P.O.W.E.R. Safe YAML Frontmatter Parser.

Uses PyYAML for reliable parsing instead of regex-based manual splitting.
"""

from __future__ import annotations

import re
from pathlib import Path  # noqa: TC003

import yaml

from .models import OKFMetadata

FRONTMATTER_PATTERN = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def extract_frontmatter_raw(content: str) -> str | None:
    """Extract raw YAML frontmatter string from markdown content."""
    if not content.startswith("---"):
        return None
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return None
    return match.group(1)


def parse_frontmatter(content: str) -> dict | None:
    """Parse YAML frontmatter into a dict using PyYAML."""
    raw = extract_frontmatter_raw(content)
    if raw is None:
        return None
    try:
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            return None
        return data
    except yaml.YAMLError:
        return None


def validate_metadata(content: str) -> OKFMetadata | None:
    """Parse and validate frontmatter against the OKF Pydantic schema."""
    data = parse_frontmatter(content)
    if data is None:
        return None
    try:
        return OKFMetadata.model_validate(data)
    except Exception:
        return None


def has_frontmatter(content: str) -> bool:
    """Check if content starts with a valid frontmatter block."""
    return extract_frontmatter_raw(content) is not None


def has_type_field(content: str) -> bool:
    """Check if frontmatter contains the required 'type' field."""
    data = parse_frontmatter(content)
    if data is None:
        return False
    return "type" in data


def build_frontmatter(metadata: OKFMetadata) -> str:
    """Build a YAML frontmatter string from validated metadata."""
    lines = [
        "---",
        f"type: {metadata.type}",
        f'title: "{_escape_yaml_string(metadata.title)}"',
        f'description: "{_escape_yaml_string(metadata.description)}"',
    ]
    if metadata.resource:
        lines.append(f'resource: "{metadata.resource}"')
    if metadata.tags:
        tags_str = ", ".join(metadata.tags)
        lines.append(f"tags: [{tags_str}]")
    if metadata.owner:
        lines.append(f'owner: "{metadata.owner}"')
    if metadata.status:
        lines.append(f"status: {metadata.status}")
    if metadata.expiry:
        lines.append(f"expiry: {metadata.expiry.isoformat()}")
    if metadata.okf_version:
        lines.append(f'okf_version: "{metadata.okf_version}"')
    if metadata.memory:
        lines.extend(
            _render_yaml_field(
                "memory",
                metadata.memory.model_dump(mode="json", exclude_none=True),
            )
        )
    if metadata.related:
        related_str = ", ".join(r.path for r in metadata.related)
        lines.append(f"related: [{related_str}]")
    for field, value in (metadata.model_extra or {}).items():
        lines.extend(_render_yaml_field(field, value))
    lines.append(f"timestamp: {metadata.timestamp.isoformat()}")
    lines.append("---")
    return "\n".join(lines)


def _escape_yaml_string(value: str) -> str:
    """Escape double quotes and backslashes in YAML string values."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _render_yaml_field(field: str, value: object) -> list[str]:
    """Render an additive frontmatter field without discarding nested values."""
    rendered = yaml.safe_dump(
        {field: value},
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).strip()
    return rendered.splitlines()


def read_file_content(filepath: Path) -> str:
    """Read file content with UTF-8 encoding, ignoring decode errors."""
    with open(filepath, encoding="utf-8", errors="ignore") as f:
        return f.read()
