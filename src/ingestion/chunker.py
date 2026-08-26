"""Split the guidelines PDF into deterministic, page-level chunks (BUILD_PLAN.md Step 2).

The source document is short (4 pages) and every section falls cleanly on one
or two pages, so a page is already a meaningful citation unit — no need for
finer-grained splitting. chunk_id is derived from the page's extracted text
via sha256, so the same PDF bytes always produce the same ids (required for
CLAUDE.md constraint 1: reproducibility).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pdfplumber


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    page: int
    start_offset: int
    end_offset: int
    text: str


def chunk_pdf(pdf_path: str | Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:4]
            chunks.append(
                Chunk(
                    chunk_id=f"chunk_{digest}",
                    page=page.page_number,
                    start_offset=0,
                    end_offset=len(text),
                    text=text,
                )
            )
    return chunks


if __name__ == "__main__":
    default_path = Path(__file__).resolve().parents[2] / "sample_docs" / "sample_fund_guidelines.pdf"
    for chunk in chunk_pdf(default_path):
        print(f"page {chunk.page}  {chunk.chunk_id}  ({chunk.end_offset} chars)")
