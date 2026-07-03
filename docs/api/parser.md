# Parser

Functions for YAML frontmatter extraction and validation.

| Function | Returns | Description |
|----------|---------|-------------|
| `extract_frontmatter_raw(content)` | `str\|None` | Extract raw YAML block between `---` markers |
| `parse_frontmatter(content)` | `dict\|None` | Parse YAML frontmatter into dict |
| `validate_metadata(data)` | `bool` | Check type field exists |
| `has_frontmatter(content)` | `bool` | Quick check for `---` delimiter |
| `has_type_field(content)` | `bool` | Check frontmatter contains `type:` |
| `build_frontmatter(metadata)` | `str` | Serialize `OKFMetadata` to YAML string |
