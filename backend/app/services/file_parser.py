"""Extract readable text and structured tables from PDF/DOCX documents."""

from io import BytesIO
from pathlib import Path

import pdfplumber
from docx import Document

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def validate_file_type(filename: str, content_type: str | None = None) -> str:
    """Validate an uploaded file is a supported PDF or DOCX. Returns the normalized extension."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type '{ext}'. Only PDF and DOCX files are allowed.")

    if content_type and content_type not in ALLOWED_MIME_TYPES and content_type != "application/octet-stream":
        raise ValueError(f"Unsupported content type '{content_type}'. Only PDF and DOCX are allowed.")

    return ext


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Uses pdfplumber rather than pypdf — it preserves visual reading order far better on
    tabular invoices, which matters for regex-based metadata extraction (invoice #, dates)."""
    pages = []
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
    return "\n\n".join(pages)


def extract_text_from_docx(file_bytes: bytes) -> str:
    doc = Document(BytesIO(file_bytes))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def extract_text(file_bytes: bytes, file_type: str) -> str:
    if file_type == ".pdf":
        return extract_text_from_pdf(file_bytes)
    if file_type == ".docx":
        return extract_text_from_docx(file_bytes)
    raise ValueError(f"Cannot extract text from unsupported type: {file_type}")


def extract_tables_from_pdf(file_bytes: bytes) -> list[list[list[str | None]]]:
    """Extract every detected table from a PDF as a list of tables (rows of cell strings)."""
    tables: list[list[list[str | None]]] = []
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if table:
                    tables.append(table)
    return tables
