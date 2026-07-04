# Parser

Functions for YAML frontmatter extraction and validation.

| Function | Returns | Description |
|----------|---------|-------------|
| `extract_frontmatter_raw(content)` | `str\|None` | Extract raw YAML block between `---` markers |
| `parse_frontmatter(content)` | `dict\|None` | Parse YAML frontmatter into dict |
| `validate_metadata(content)` | `OKFMetadata\|None` | Parse and validate frontmatter against the OKF Pydantic schema |
| `has_frontmatter(content)` | `bool` | Quick check for `---` delimiter |
| `has_type_field(content)` | `bool` | Check frontmatter contains `type:` |
| `build_frontmatter(metadata)` | `str` | Serialize `OKFMetadata` to YAML string |
| `read_file_content(filepath)` | `str` | Read file content with UTF-8 encoding, ignoring decode errors |

