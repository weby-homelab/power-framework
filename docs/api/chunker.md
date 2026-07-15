# Chunker

## `SemanticChunker`

Class for splitting markdown notes into contextualized chunks using the Anthropic Contextual Retrieval pattern.

### Constructor

```python
SemanticChunker(mode: ChunkMode = "headers", chunk_size: int = 512, chunk_overlap: int = 0)
```

- `mode` (ChunkMode): The splitting mode, one of:
  - `"headers"` (default): Split by H2 (`##`) and H3 (`###`) headers.
  - `"paragraphs"`: Split by double newlines.
  - `"fixed"`: Split by fixed character counts.
- `chunk_size` (int): Target character count for `"fixed"` mode. Default is `512`.
- `chunk_overlap` (int): Overlap character count for `"fixed"` mode. Default is `0`.

### Methods

#### `chunk(content: str, title: str = "", description: str = "") -> list[str]`

Split raw markdown content into chunks, prepending document-level context to each chunk.

- **Parameters**:
  - `content` (str): Raw markdown document (frontmatter is automatically stripped).
  - `title` (str): Optional document title.
  - `description` (str): Optional document description.
- **Returns**: A list of chunk strings, each prefixed with `[Document: {title} | Description: {description}]\n`.
