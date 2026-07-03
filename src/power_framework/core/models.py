"""
P.O.W.E.R. OKF Metadata Models.

Pydantic v2 schemas for strict validation of Open Knowledge Format (OKF) metadata.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NoteType(str, Enum):
    """Allowed OKF note types according to P.A.R.A. + LLM-Wiki schema."""

    PROJECT = "Project"
    AREA = "Area"
    RESOURCE = "Resource"
    DAILY_LOG = "Daily Log"
    ARCHIVE = "Archive"
    SYSTEM_GUIDE = "System Guide"


NOTE_TYPE_ORDER: list[str] = [
    "System Guide",
    "Project",
    "Area",
    "Resource",
    "Daily Log",
    "Archive",
]

PARA_FOLDERS: tuple[str, ...] = (
    "00_Inbox",
    "01_Projects",
    "02_Areas",
    "03_Resources",
    "04_Archive",
    "06_Daily_Logs",
)

VAULT_STRUCTURE: tuple[str, ...] = (*PARA_FOLDERS, "05_Templates", "PROTOCOLS")

MAX_DESCRIPTION_LENGTH = 150
MAX_TITLE_LENGTH = 200


class OKFMetadata(BaseModel):
    """Strict Pydantic model for OKF YAML frontmatter validation."""

    type: NoteType = Field(description="OKF note category")
    title: str = Field(
        min_length=1, max_length=MAX_TITLE_LENGTH, description="Human-friendly title"
    )
    description: str = Field(
        min_length=1,
        max_length=MAX_DESCRIPTION_LENGTH,
        description="Single-line summary for the catalog index",
    )
    resource: str | None = Field(default=None, description="External source URL")
    tags: list[str] = Field(default_factory=list, description="Obsidian tags")
    timestamp: datetime = Field(description="Last modified ISO-8601 timestamp")

    model_config = ConfigDict(extra="ignore", use_enum_values=True)

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: str) -> str:
        return v.strip()

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v: str) -> str:
        return v.strip()

    @field_validator("resource")
    @classmethod
    def validate_resource_url(cls, v: str | None) -> str | None:
        if v is not None and v.strip():
            v = v.strip()
            if not v.startswith(("http://", "https://")):
                raise ValueError("resource must be a valid http(s) URL")
        return v if v and v.strip() else None

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        return [t.strip() for t in v if t.strip()]


class NoteFile:
    """Represents a parsed note file with metadata and path info."""

    def __init__(
        self,
        abs_path: str,
        rel_path: str,
        metadata: OKFMetadata | None = None,
        raw_content: str = "",
    ) -> None:
        self.abs_path = abs_path
        self.rel_path = rel_path
        self.metadata = metadata
        self.raw_content = raw_content

    @property
    def filename(self) -> str:
        import os

        return os.path.basename(self.rel_path)

    @property
    def clean_name(self) -> str:
        return self.filename.replace(".md", "").strip().lower()

    @property
    def has_valid_metadata(self) -> bool:
        return self.metadata is not None

    @property
    def note_type(self) -> str | None:
        if self.metadata:
            return self.metadata.type
        return None
