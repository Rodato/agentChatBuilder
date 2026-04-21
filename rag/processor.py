"""Document text extraction and chunking."""

import os
import re
from typing import List, Dict, Any, Optional
from loguru import logger


def extract_sections(file_path: str) -> List[Dict[str, Any]]:
    """Extract text sections from a file. Each section has {text, page?}."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext in (".txt", ".md"):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return [{"text": f.read(), "page": None}]

    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        return [
            {"text": (page.extract_text() or "").strip(), "page": i + 1}
            for i, page in enumerate(reader.pages)
            if (page.extract_text() or "").strip()
        ]

    if ext == ".docx":
        from docx import Document
        doc = Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return [{"text": "\n\n".join(paragraphs), "page": None}]

    raise ValueError(f"Tipo de archivo no soportado: {ext}")


def extract_text(file_path: str) -> str:
    """Legacy: plain concatenation of all sections."""
    return "\n\n".join(s["text"] for s in extract_sections(file_path))


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[\.\?\!])\s+")


def _split_sentences(text: str) -> List[str]:
    return [s for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def _hard_split(text: str, max_chars: int) -> List[str]:
    """Last-resort split for pieces that have no sentence boundaries."""
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def _pack(pieces: List[str], max_chars: int) -> List[str]:
    """Greedy-pack pieces (paragraphs or sentences) into chunks up to max_chars."""
    chunks: List[str] = []
    buf = ""
    for p in pieces:
        p = p.strip()
        if not p:
            continue
        if len(p) > max_chars:
            if buf:
                chunks.append(buf)
                buf = ""
            sentences = _split_sentences(p)
            # If splitting by sentences doesn't make progress, fall back to a hard character split.
            if len(sentences) <= 1:
                chunks.extend(_hard_split(p, max_chars))
            else:
                chunks.extend(_pack(sentences, max_chars))
            continue
        if not buf:
            buf = p
        elif len(buf) + 2 + len(p) <= max_chars:
            buf += "\n\n" + p
        else:
            chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> List[str]:
    """Paragraph-aware chunking. Returns a list of chunk strings."""
    text = (text or "").strip()
    if not text:
        return []
    paragraphs = re.split(r"\n\n+", text)
    packed = _pack(paragraphs, chunk_size)
    # Overlap: prepend the tail of the previous chunk to the next one.
    if overlap <= 0 or len(packed) <= 1:
        return packed
    out = [packed[0]]
    for chunk in packed[1:]:
        tail = out[-1][-overlap:]
        out.append((tail + "\n\n" + chunk).strip())
    return out


def chunk_sections(
    sections: List[Dict[str, Any]],
    chunk_size: int = 1200,
    overlap: int = 150,
) -> List[Dict[str, Any]]:
    """Chunk each section preserving page metadata. Returns [{content, page?}]."""
    out: List[Dict[str, Any]] = []
    for section in sections:
        for chunk in chunk_text(section["text"], chunk_size=chunk_size, overlap=overlap):
            out.append({"content": chunk, "page": section.get("page")})
    return out
