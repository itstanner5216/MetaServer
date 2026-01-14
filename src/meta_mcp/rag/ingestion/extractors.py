# ingestion/extractors.py
"""
Document text extractors for various file formats.
Each extractor is versioned for reproducibility.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import pypdf
from docx import Document as DOCXDocument

logger = logging.getLogger(__name__)


class Extractor(ABC):
    """Base class for document text extractors."""

    # Each extractor must define name and version for tracking
    name: str = "base"
    version: str = "1.0"

    @abstractmethod
    def extract(self, path: str) -> str:
        """Extract plain text from file."""

    @abstractmethod
    def can_extract(self, path: str) -> bool:
        """Check if this extractor can handle the file."""

    def get_metadata(self) -> dict:
        """Return extractor metadata for audit trail."""
        return {"extractor": self.name, "extractor_version": self.version}


class PlainTextExtractor(Extractor):
    """Extract text from plain text and markdown files."""

    name = "text-direct"
    version = "1.0"

    SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".text", ".rst"}

    def extract(self, path: str) -> str:
        try:
            return Path(path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Fallback to latin-1 for legacy files
            return Path(path).read_text(encoding="latin-1")

    def can_extract(self, path: str) -> bool:
        return Path(path).suffix.lower() in self.SUPPORTED_EXTENSIONS


class PDFExtractor(Extractor):
    """Extract text from PDF files using pypdf."""

    name = "pdf-pypdf"
    version = "1.0"

    def extract(self, path: str) -> str:
        try:
            reader = pypdf.PdfReader(path)
            pages = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    pages.append(f"[Page {i + 1}]\n{text}")
            return "\n\n".join(pages)
        except Exception as e:
            logger.error(f"PDF extraction failed for {path}: {e}")
            raise

    def can_extract(self, path: str) -> bool:
        return Path(path).suffix.lower() == ".pdf"


class DOCXExtractor(Extractor):
    """Extract text from Microsoft Word documents."""

    name = "docx-python-docx"
    version = "1.0"

    def extract(self, path: str) -> str:
        try:
            doc = DOCXDocument(path)
            paragraphs = []
            for para in doc.paragraphs:
                if para.text.strip():
                    # Preserve heading structure
                    if para.style.name.startswith("Heading"):
                        level = para.style.name[-1] if para.style.name[-1].isdigit() else "1"
                        paragraphs.append(f"{'#' * int(level)} {para.text}")
                    else:
                        paragraphs.append(para.text)
            return "\n\n".join(paragraphs)
        except Exception as e:
            logger.error(f"DOCX extraction failed for {path}: {e}")
            raise

    def can_extract(self, path: str) -> bool:
        return Path(path).suffix.lower() in {".docx", ".doc"}


class ExtractorRegistry:
    """Registry of available extractors with MIME type mapping."""

    def __init__(self):
        self.extractors: dict[str, Extractor] = {}
        self.mime_type_map: dict[str, str] = {}

    def register(self, mime_type: str, extractor: Extractor):
        """Register an extractor for a MIME type."""
        self.extractors[mime_type] = extractor
        logger.info(f"Registered extractor: {extractor.name} v{extractor.version} for {mime_type}")

    def extract(self, path: str, mime_type: str) -> str:
        """Extract text using the appropriate extractor."""
        if mime_type not in self.extractors:
            raise ValueError(f"No extractor registered for MIME type: {mime_type}")
        return self.extractors[mime_type].extract(path)

    def get_extractor(self, mime_type: str) -> Extractor | None:
        """Get extractor for a MIME type."""
        return self.extractors.get(mime_type)

    def get_extractor_metadata(self, mime_type: str) -> dict:
        """Get metadata for the extractor that would handle this MIME type."""
        extractor = self.extractors.get(mime_type)
        if extractor:
            return extractor.get_metadata()
        return {"extractor": "unknown", "extractor_version": "0.0"}


def create_default_registry() -> ExtractorRegistry:
    """Create registry with all default extractors."""
    registry = ExtractorRegistry()

    # Plain text
    text_extractor = PlainTextExtractor()
    registry.register("text/plain", text_extractor)
    registry.register("text/markdown", text_extractor)
    registry.register("text/x-markdown", text_extractor)

    # PDF
    pdf_extractor = PDFExtractor()
    registry.register("application/pdf", pdf_extractor)

    # Word documents
    docx_extractor = DOCXExtractor()
    registry.register(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx_extractor
    )
    registry.register("application/msword", docx_extractor)

    return registry
