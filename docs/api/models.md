# Models

## `OKFMetadata`

Pydantic model for Open Knowledge Format frontmatter.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `type` | `NoteType` | Yes | Enum: `Project`, `Area`, `Resource`, `Daily Log`, `Archive`, `System Guide` |
| `title` | `str` | Yes | Max 120 chars |
| `description` | `str` | Yes | Max 150 chars |
| `resource` | `str\|None` | No | Valid URL |
| `tags` | `list[str]\|None` | No | Lowercased, stripped |
| `timestamp` | `datetime` | Yes | UTC-aware |

## `NoteType`

Enum of valid OKF note types.

## `NoteFile`

TypedDict representing a scanned note.

| Key | Type | Description |
|-----|------|-------------|
| `category` | `str` | P.A.R.A. folder name |
| `path` | `Path` | Absolute path |
| `title` | `str` | First H1 or filename |
| `type` | `str\|None` | OKF type from frontmatter |
