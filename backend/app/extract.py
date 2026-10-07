"""Read uploaded files into provider-neutral `SourceDoc`s.

PDFs keep their raw bytes so providers that read PDFs natively (Claude) can use
them; `text` is always filled so text-only providers work too.

Uploads are untrusted: every limit below exists to bound memory, CPU, and LLM
cost for a single request.
"""

import io
import zipfile
from dataclasses import dataclass

from docx import Document
from pypdf import PdfReader

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 30
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # zip-bomb guard
MAX_DOC_CHARS = 100_000  # per document, after extraction; bounds tokens sent to the LLM


class UnsupportedFileError(ValueError):
    pass


@dataclass
class SourceDoc:
    title: str  # e.g. "resume", "job_description"
    text: str
    pdf_bytes: bytes | None = None


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        if sum(i.file_size for i in zf.infolist()) > MAX_DOCX_UNCOMPRESSED_BYTES:
            raise UnsupportedFileError("DOCX expands to an unreasonable size.")
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(p for p in parts if p.strip())


def _pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    if len(reader.pages) > MAX_PDF_PAGES:
        raise UnsupportedFileError(f"PDF has more than {MAX_PDF_PAGES} pages.")
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _check_length(text: str, title: str) -> str:
    text = text.strip()
    if len(text) > MAX_DOC_CHARS:
        raise UnsupportedFileError(f"{title} is too long (max {MAX_DOC_CHARS:,} characters).")
    return text


def from_upload(filename: str, data: bytes, title: str) -> SourceDoc:
    if not data:
        raise UnsupportedFileError(f"{title} file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UnsupportedFileError(f"{title} file is larger than 10 MB.")

    name = (filename or "").lower()
    pdf_bytes = None
    try:
        if name.endswith(".pdf"):
            text = _pdf_text(data)
            pdf_bytes = data
        elif name.endswith(".docx"):
            text = _docx_text(data)
        elif name.endswith((".txt", ".md")):
            text = data.decode("utf-8", errors="replace")
        else:
            raise UnsupportedFileError("unsupported file type. Use PDF, DOCX, or TXT.")
    except UnsupportedFileError as e:
        raise UnsupportedFileError(f"{title}: {e}")
    except Exception:
        # Malformed/corrupt files from parser libraries: don't leak internals or 500.
        raise UnsupportedFileError(f"{title}: the file could not be read. Is it corrupted?")

    # A scanned PDF may have no text layer; Claude can still read it natively.
    if not text.strip() and pdf_bytes is None:
        raise UnsupportedFileError(f"{title}: no text could be read from the file.")
    return SourceDoc(title=title, text=_check_length(text, title), pdf_bytes=pdf_bytes)


def from_text(text: str, title: str) -> SourceDoc:
    return SourceDoc(title=title, text=_check_length(text, title))
