"""Read uploaded files into provider-neutral `SourceDoc`s.

PDFs keep their raw bytes so providers that read PDFs natively (Claude) can use
them; `text` is always filled so text-only providers work too.
"""

import io
from dataclasses import dataclass

from docx import Document
from pypdf import PdfReader

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class UnsupportedFileError(ValueError):
    pass


@dataclass
class SourceDoc:
    title: str  # e.g. "resume", "job_description"
    text: str
    pdf_bytes: bytes | None = None


def _docx_text(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(p for p in parts if p.strip())


def _pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def from_upload(filename: str, data: bytes, title: str) -> SourceDoc:
    if not data:
        raise UnsupportedFileError(f"{title} file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UnsupportedFileError(f"{title} file is larger than 10 MB.")

    name = (filename or "").lower()
    pdf_bytes = None
    if name.endswith(".pdf"):
        try:
            text = _pdf_text(data)
        except Exception:
            raise UnsupportedFileError(f"{title}: could not read the PDF.")
        pdf_bytes = data
    elif name.endswith(".docx"):
        text = _docx_text(data)
    elif name.endswith((".txt", ".md")):
        text = data.decode("utf-8", errors="replace")
    else:
        raise UnsupportedFileError(f"{title}: unsupported file type. Use PDF, DOCX, or TXT.")

    # A scanned PDF may have no text layer; Claude can still read it natively.
    if not text.strip() and pdf_bytes is None:
        raise UnsupportedFileError(f"{title}: no text could be read from the file.")
    return SourceDoc(title=title, text=text.strip(), pdf_bytes=pdf_bytes)


def from_text(text: str, title: str) -> SourceDoc:
    return SourceDoc(title=title, text=text.strip())
