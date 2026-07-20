"""
P.O.W.E.R. Semantic Chunker.

Anthropic-style Contextual Retrieval chunking:
- Splits markdown documents by H2/H3 headers, paragraphs, or fixed character count.
- Prefixes each chunk with contextual document metadata.
"""

from __future__ import annotations

import re
from typing import Literal

ChunkMode = Literal["headers", "paragraphs", "fixed"]

HEADER_PATTERN = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)


class SemanticChunker:
    """Split markdown into semantically coherent chunks with document context."""

    def __init__(
        self,
        mode: ChunkMode = "headers",
        chunk_size: int = 512,
        chunk_overlap: int = 0,
    ) -> None:
        self.mode = mode
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(
        self,
        content: str,
        title: str = "",
        description: str = "",
    ) -> list[str]:
        """Split markdown content into contextualized chunks.

        Each chunk is prefixed with document-level context
        (R6 Contextual Retrieval):
            [Document: {title} | Description: {description} | Section: {section}]

        Args:
            content: Raw markdown content (with or without YAML frontmatter).
            title: Document title from OKF metadata.
            description: Document description from OKF metadata.

        Returns:
            List of chunk strings, each with the document context prefix.
        """
        body = _strip_frontmatter(content)
        doc_prefix = f"[Document: {title} | Description: {description}]"

        if self.mode == "headers":
            raw_chunks = self._split_by_headers(body, doc_prefix)
        elif self.mode == "paragraphs":
            raw_chunks = self._split_by_paragraphs(body)
            # R6 Contextual Retrieval: every chunk carries document context.
            raw_chunks = [f"{doc_prefix} | Section: (paragraph)\n{p}" for p in raw_chunks]
        else:
            raw_chunks = self._split_fixed(body, self.chunk_size, self.chunk_overlap)
            raw_chunks = [f"{doc_prefix} | Section: (fixed)\n{c}" for c in raw_chunks]

        return [chunk.strip() for chunk in raw_chunks if chunk.strip()]

    def _split_by_headers(self, text: str, doc_prefix: str = "") -> list[str]:
        """Split on H2 (##) and H3 (###) headers, each chunk carrying its
        section name in the contextual prefix (R6 Contextual Retrieval)."""
        matches = list(HEADER_PATTERN.finditer(text))
        if not matches:
            return [f"{doc_prefix}\n{text.strip()}"] if text.strip() else []

        chunks: list[str] = []

        for i, match in enumerate(matches):
            if i == 0 and match.start() > 0:
                preamble = text[: match.start()].strip()
                if preamble:
                    chunks.append(f"{doc_prefix} | Section: (preamble)\n{preamble}")
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section = text[start:end].strip()
            # The first line of the section is the header itself — extract the
            # section name to surface it in the prefix for retrieval context.
            section_name = match.group(2).strip()
            if section:
                chunks.append(f"{doc_prefix} | Section: {section_name}\n{section}")

        return chunks

    def _split_by_paragraphs(self, text: str) -> list[str]:
        """Split on double newlines (paragraph breaks)."""
        paragraphs = re.split(r"\n\s*\n", text)
        return [p.strip() for p in paragraphs if p.strip()]

    def _split_fixed(self, text: str, size: int, overlap: int) -> list[str]:
        """Split into fixed-size character chunks with optional overlap."""
        if not text.strip():
            return []
        if len(text) <= size:
            return [text.strip()]

        step = size - overlap
        chunks: list[str] = []
        for i in range(0, len(text), step):
            chunk = text[i : i + size].strip()
            if chunk:
                chunks.append(chunk)
        return chunks


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter (--- ... ---) from markdown content."""
    match = re.match(r"^---\r?\n.*?\r?\n---\r?\n", content, re.DOTALL)
    if match:
        return content[match.end() :]
    return content
