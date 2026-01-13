"""Ingestion pipeline for document processing and embedding."""

from .extractors import (
    Extractor,
    PlainTextExtractor,
    PDFExtractor,
    DOCXExtractor,
    ExtractorRegistry,
    create_default_registry
)

__all__ = [
    "Extractor",
    "PlainTextExtractor",
    "PDFExtractor",
    "DOCXExtractor",
    "ExtractorRegistry",
    "create_default_registry"
]
