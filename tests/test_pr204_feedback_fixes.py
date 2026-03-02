from pathlib import Path

import pytest

from src.meta_mcp.governance.artifacts import ApprovalArtifactGenerator
from src.meta_mcp.rag.ingestion import extractors


def test_artifact_generator_allows_safe_absolute_root(tmp_path: Path):
    root = tmp_path / "artifacts"
    generator = ApprovalArtifactGenerator(str(root))
    assert generator.artifacts_root == root.resolve()


def test_pdf_extractor_reports_missing_optional_dependency(tmp_path: Path):
    if extractors._HAS_PYPDF:
        pytest.skip("pypdf installed in environment")

    with pytest.raises(RuntimeError, match="pypdf is required"):
        extractors.PDFExtractor().extract(str(tmp_path / "missing.pdf"))


def test_docx_extractor_reports_missing_optional_dependency(tmp_path: Path):
    if extractors._HAS_DOCX:
        pytest.skip("python-docx installed in environment")

    with pytest.raises(RuntimeError, match="python-docx is required"):
        extractors.DOCXExtractor().extract(str(tmp_path / "missing.docx"))
