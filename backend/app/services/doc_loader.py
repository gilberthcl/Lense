"""
Extract plain text from uploaded methodology documents.

Supports .docx (paragraphs AND tables — the executed-query tables in a
methodology must be preserved), plus .txt / .md passthrough. The extracted text
becomes the hunt's `methodology_text`, which the comprehension step then reads.
"""
from __future__ import annotations

import io

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

SUPPORTED_SUFFIXES = (".docx", ".txt", ".md", ".markdown")


def _table_to_text(table: Table) -> str:
    lines = []
    for row in table.rows:
        cells = [c.text.strip().replace("\n", " ") for c in row.cells]
        lines.append(" | ".join(cells))
    return "\n".join(lines)


def _iter_blocks(document: Document):
    """Yield paragraphs and tables in document order."""
    body = document.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def extract_docx_text(data: bytes) -> str:
    document = Document(io.BytesIO(data))
    parts: list[str] = []
    for block in _iter_blocks(document):
        if isinstance(block, Paragraph):
            if block.text.strip():
                parts.append(block.text)
        else:  # Table
            text = _table_to_text(block)
            if text.strip():
                parts.append(f"\n[TABLE]\n{text}\n[/TABLE]\n")
    return "\n".join(parts)


def extract_text(filename: str, data: bytes) -> str:
    """Dispatch on file extension. Raises ValueError for unsupported types."""
    lower = (filename or "").lower()
    if lower.endswith(".docx"):
        return extract_docx_text(data)
    if lower.endswith((".txt", ".md", ".markdown")):
        return data.decode("utf-8", errors="replace")
    raise ValueError(
        f"Unsupported methodology file type. Allowed: {', '.join(SUPPORTED_SUFFIXES)}"
    )
