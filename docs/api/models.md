# Models

## `OKFMetadata`

Pydantic model for Open Knowledge Format frontmatter.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `type` | `NoteType` | Yes | Enum: `Project`, `Area`, `Resource`, `Daily Log`, `Archive`, `System Guide` |
| `title` | `str` | Yes | Max 200 chars, stripped |
| `description` | `str` | Yes | Max 150 chars, stripped |
| `resource` | `str\|None` | No | Valid URL |
| `tags` | `list[str]` | No | Default: `[]`, elements stripped |
| `timestamp` | `datetime` | Yes | UTC-aware |
| `owner` | `str\|None` | No | Responsible person/team for governance |
| `status` | `NoteStatus\|None` | No | `active` \| `review` \| `archived` |
| `expiry` | `date\|None` | No | Date after which the note should be reviewed |
| `related` | `list[TypedRelation]` | No | Default: `[]`, Typed knowledge graph links to other notes (Graph RAG) |

## `TypedRelation`

Class representing a semantic link to another note.

| Attribute | Type | Description |
|-----------|------|-------------|
| `path` | `str` | Relative path to the related note |
| `relation` | `str` | Semantic relation type (e.g., `related_to`, `depends_on`, `contradicts`, `extends`, `part_of`, `governed_by`) |
| `confidence` | `float` | Confidence score for the relation (0.0 to 1.0, default 1.0) |

## `NoteType`

Enum of valid OKF note types.

## `NoteStatus`

Enum of governance lifecycle statuses: `active`, `review`, `archived`.

## `NoteFile`

Class representing a scanned note file with metadata and path details.

| Attribute/Property | Type | Description |
|--------------------|------|-------------|
| `abs_path` | `str` | Absolute path to the note file |
| `rel_path` | `str` | Relative path to the note file |
| `metadata` | `OKFMetadata\|None` | Parsed note metadata |
| `raw_content` | `str` | Raw note content |
| `filename` (property) | `str` | Note filename |
| `clean_name` (property) | `str` | Note filename without extension, lowercased and stripped |
| `has_valid_metadata` (property) | `bool` | True if metadata is not None |
| `note_type` (property) | `str\|None` | Note type value from metadata |

