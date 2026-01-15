"""Ingestion pipeline for document processing and embedding."""

from .extractors import (
    DOCXExtractor,
    Extractor,
    ExtractorRegistry,
    PDFExtractor,
    PlainTextExtractor,
    create_default_registry,
)

__all__ = [
    "DOCXExtractor",
    "Extractor",
    "ExtractorRegistry",
    "PDFExtractor",
    "PlainTextExtractor",
    "create_default_registry",
]
