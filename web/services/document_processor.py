"""PDF text extraction using PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import pymupdf


def extract_text_from_pdf(file_path: str | Path) -> str:
    """Extract all text from a PDF file using PyMuPDF."""
    doc = pymupdf.open(str(file_path))
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()
    return "\n".join(text_parts)


def extract_text_from_file(file_path: str | Path, file_type: str) -> str:
    """Extract text from a file based on its type."""
    path = Path(file_path)
    if path.suffix.lower() == ".pdf":
        return extract_text_from_pdf(path)
    elif path.suffix.lower() in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="ignore")
    else:
        # Try PDF first, fallback to raw text
        try:
            return extract_text_from_pdf(path)
        except Exception:
            return path.read_text(encoding="utf-8", errors="ignore")
