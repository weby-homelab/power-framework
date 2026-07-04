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

## `NoteType`

Enum of valid OKF note types.

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

