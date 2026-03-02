"""Tests for governance artifacts module coverage.

Covers path validation, cleanup, HTML/JSON generation, and size limits.
"""

import json
from pathlib import Path

import pytest

from src.meta_mcp.governance.artifacts import (
    ApprovalArtifactGenerator,
    ArtifactGenerationError,
    get_artifact_generator,
)


class TestArtifactGeneratorSafeRoot:
    def test_rejects_root_path(self):
        with pytest.raises(ArtifactGenerationError, match="system directory"):
            ApprovalArtifactGenerator("/")

    def test_rejects_etc(self):
        with pytest.raises(ArtifactGenerationError):
            ApprovalArtifactGenerator("/etc")

    def test_rejects_usr(self):
        with pytest.raises(ArtifactGenerationError):
            ApprovalArtifactGenerator("/usr")

    def test_rejects_bin(self):
        with pytest.raises(ArtifactGenerationError):
            ApprovalArtifactGenerator("/bin")

    def test_rejects_under_etc(self):
        with pytest.raises(ArtifactGenerationError):
            ApprovalArtifactGenerator("/etc/meta_mcp")

    def test_allows_tmp_path(self, tmp_path: Path):
        root = tmp_path / "artifacts"
        gen = ApprovalArtifactGenerator(str(root))
        assert gen.artifacts_root == root.resolve()

    def test_creates_directory(self, tmp_path: Path):
        root = tmp_path / "deep" / "nested" / "artifacts"
        gen = ApprovalArtifactGenerator(str(root))
        assert root.exists()


class TestValidatePath:
    def test_validates_safe_path(self, tmp_path: Path):
        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))
        result = gen._validate_path("test.html")
        assert result.parent == (tmp_path / "artifacts").resolve()

    def test_rejects_path_traversal(self, tmp_path: Path):
        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))
        with pytest.raises(ArtifactGenerationError, match="Path traversal"):
            gen._validate_path("../../etc/passwd")


class TestCleanupOldArtifacts:
    def test_cleanup_removes_oldest(self, tmp_path: Path):
        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))
        gen._max_artifacts = 3

        # Create 5 artifacts
        for i in range(5):
            path = gen.artifacts_root / f"file_{i}.txt"
            path.write_text(f"content {i}")

        gen._cleanup_old_artifacts()

        remaining = list(gen.artifacts_root.glob("*"))
        assert len(remaining) <= 3

    def test_cleanup_no_op_under_limit(self, tmp_path: Path):
        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))
        gen._max_artifacts = 100

        path = gen.artifacts_root / "file.txt"
        path.write_text("content")

        gen._cleanup_old_artifacts()

        assert path.exists()


class TestGenerateHTMLArtifact:
    def test_generates_html(self, tmp_path: Path):
        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))
        result_path = gen.generate_html_artifact(
            request_id="req-1",
            tool_name="write_file",
            message="Write test.txt",
            required_scopes=["write", "filesystem"],
            arguments={"path": "test.txt", "content": "hello"},
            context_metadata={"session_id": "s1", "context_key": "file:test.txt"},
        )
        assert Path(result_path).exists()
        content = Path(result_path).read_text()
        assert "write_file" in content
        assert "req-1" in content
        assert "Write test.txt" in content
        assert "write" in content

    def test_html_escapes_xss(self, tmp_path: Path):
        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))
        result_path = gen.generate_html_artifact(
            request_id="req-xss-test",
            tool_name="<b>evil</b>",
            message="<img onerror=alert(1)>",
            required_scopes=["<script>"],
            arguments={"<key>": "<value>"},
            context_metadata={},
        )
        content = Path(result_path).read_text()
        assert "<b>evil</b>" not in content
        assert "&lt;b&gt;" in content
        assert "&lt;script&gt;" in content

    def test_html_size_limit(self, tmp_path: Path):
        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))
        gen._max_artifact_size = 100  # Very small limit
        with pytest.raises(ArtifactGenerationError, match="size limit"):
            gen.generate_html_artifact(
                request_id="req-big",
                tool_name="tool",
                message="x" * 200,
                required_scopes=["write"],
                arguments={},
                context_metadata={},
            )

    def test_html_no_arguments(self, tmp_path: Path):
        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))
        result_path = gen.generate_html_artifact(
            request_id="req-noargs",
            tool_name="read_file",
            message="Read something",
            required_scopes=["read"],
            arguments={},
            context_metadata={},
        )
        content = Path(result_path).read_text()
        assert "No arguments" in content


class TestGenerateJSONArtifact:
    def test_generates_json(self, tmp_path: Path):
        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))
        result_path = gen.generate_json_artifact(
            request_id="req-j1",
            tool_name="write_file",
            message="Write test.txt",
            required_scopes=["write"],
            arguments={"path": "test.txt"},
            context_metadata={"session_id": "s1"},
        )
        assert Path(result_path).exists()
        data = json.loads(Path(result_path).read_text())
        assert data["request_id"] == "req-j1"
        assert data["tool_name"] == "write_file"
        assert data["required_scopes"] == ["write"]
        assert "generated_at" in data

    def test_json_size_limit(self, tmp_path: Path):
        gen = ApprovalArtifactGenerator(str(tmp_path / "artifacts"))
        gen._max_artifact_size = 50
        with pytest.raises(ArtifactGenerationError, match="size limit"):
            gen.generate_json_artifact(
                request_id="req-big",
                tool_name="tool",
                message="x" * 200,
                required_scopes=["write"],
                arguments={},
                context_metadata={},
            )


class TestGetArtifactGenerator:
    def test_singleton_creation(self, tmp_path: Path, monkeypatch):
        import src.meta_mcp.governance.artifacts as artifacts_module

        original = artifacts_module._artifact_generator
        artifacts_module._artifact_generator = None
        try:
            monkeypatch.setenv("ARTIFACTS_ROOT", str(tmp_path / "gen_artifacts"))
            gen = get_artifact_generator()
            assert gen is not None
            assert gen.artifacts_root == (tmp_path / "gen_artifacts").resolve()
        finally:
            artifacts_module._artifact_generator = original

    def test_singleton_returns_cached(self, tmp_path: Path):
        import src.meta_mcp.governance.artifacts as artifacts_module

        original = artifacts_module._artifact_generator
        try:
            gen1 = ApprovalArtifactGenerator(str(tmp_path / "art1"))
            artifacts_module._artifact_generator = gen1
            gen2 = get_artifact_generator()
            assert gen2 is gen1
        finally:
            artifacts_module._artifact_generator = original
