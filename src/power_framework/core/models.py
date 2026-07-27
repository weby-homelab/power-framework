"""
P.O.W.E.R. OKF Metadata Models.

Pydantic v2 schemas for strict validation of Open Knowledge Format (OKF) metadata.
Supports:
  - Core: type, title, description, resource, tags, timestamp
  - Governance: owner, status, expiry
  - Graph RAG: related (knowledge graph links between notes)
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TypedRelation(BaseModel):
    """A typed relation between two notes in the knowledge graph.

    Fields:
      path: Relative path to the related note
      relation: Semantic relation type (e.g. 'related_to', 'depends_on', 'references')
      confidence: Confidence score for the relation (0.0 - 1.0)
    """

    path: str = Field(description="Relative path to the related note")
    relation: str = Field(default="related_to", description="Semantic relation type")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0 - 1.0)",
    )

    model_config = ConfigDict(extra="ignore")


class NoteType(str, Enum):
    """Allowed OKF note types according to P.A.R.A. + LLM-Wiki schema."""

    PROJECT = "Project"
    AREA = "Area"
    RESOURCE = "Resource"
    DAILY_LOG = "Daily Log"
    ARCHIVE = "Archive"
    SYSTEM_GUIDE = "System Guide"


class NoteStatus(str, Enum):
    """Lifecycle status for governance tracking."""

    ACTIVE = "active"
    REVIEW = "review"
    ARCHIVED = "archived"


class MemoryKind(str, Enum):
    """Functional role of a governed memory record."""

    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    INTENT = "intent"


class WritePolicy(str, Enum):
    """How a memory record was allowed to enter the vault."""

    HUMAN = "human"
    AGENT_PROPOSED = "agent-proposed"
    AGENT_APPROVED = "agent-approved"


class Sensitivity(str, Enum):
    """Local handling class for memory content."""

    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"


class MemoryMetadata(BaseModel):
    """Optional OKF v0.2 lifecycle and provenance metadata for one note."""

    kind: MemoryKind
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    valid_from: date_type | None = None
    valid_until: date_type | None = None
    supersedes: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    write_policy: WritePolicy = WritePolicy.HUMAN
    sensitivity: Sensitivity = Sensitivity.INTERNAL

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    @field_validator("supersedes", "sources", "evidence")
    @classmethod
    def normalize_string_list(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]

    @model_validator(mode="after")
    def validate_lifecycle_and_provenance(self) -> MemoryMetadata:
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until must not be before valid_from")
        if self.write_policy != WritePolicy.HUMAN.value and (not self.sources or not self.evidence):
            raise ValueError("agent-managed memory requires sources and evidence")
        return self


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
    """Strict Pydantic model for OKF YAML frontmatter validation.

    Fields:
      type, title, description, resource, tags, timestamp — core OKF
      owner, status, expiry — governance
      related — knowledge graph links (Graph RAG)
    """

    type: NoteType = Field(description="OKF note category")
    title: str = Field(
        min_length=1, max_length=MAX_TITLE_LENGTH, description="Human-friendly title"
    )
    description: str = Field(
        min_length=1,
        description="Single-line summary for the catalog index",
    )
    resource: str | None = Field(default=None, description="External source URL")
    tags: list[str] = Field(default_factory=list, description="Markdown tags")
    timestamp: datetime = Field(description="Last modified ISO-8601 timestamp")

    owner: str | None = Field(
        default=None,
        description="Responsible person/team for governance tracking",
    )
    status: NoteStatus | None = Field(
        default=None,
        description="Lifecycle status: active, review, or archived",
    )
    expiry: date_type | None = Field(
        default=None,
        description="Date after which the note should be reviewed",
    )
    okf_version: Literal["0.2"] | None = Field(
        default=None,
        description="Optional additive OKF Memory Contract version",
    )
    memory: MemoryMetadata | None = Field(
        default=None,
        description="Optional lifecycle, provenance, and sensitivity metadata",
    )

    related: list[TypedRelation] = Field(
        default_factory=list,
        description="Typed knowledge graph links to related notes",
    )

    # Unknown fields must survive parsing and healing during the v0.2 rollout.
    model_config = ConfigDict(extra="allow", use_enum_values=True)

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

    @field_validator("related", mode="before")
    @classmethod
    def coerce_related(cls, v: object) -> list[TypedRelation]:
        if v is None:
            return []
        if isinstance(v, list):
            result: list[TypedRelation] = []
            for item in v:
                if isinstance(item, TypedRelation):
                    result.append(item)
                elif isinstance(item, str):
                    stripped = item.strip()
                    if stripped:
                        result.append(
                            TypedRelation(
                                path=stripped,
                                relation="related_to",
                                confidence=1.0,
                            )
                        )
                elif isinstance(item, dict):
                    result.append(TypedRelation.model_validate(item))
                else:
                    raise ValueError(f"Invalid related item: {item!r}")
            return result
        raise ValueError("related must be a list")

    @field_validator("timestamp", mode="before")
    @classmethod
    def normalize_timestamp(cls, v: object) -> datetime:
        if isinstance(v, datetime):
            if v.tzinfo is None:
                from datetime import timezone

                v = v.replace(tzinfo=timezone.utc)
            return v
        raise ValueError("timestamp must be a datetime")


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
