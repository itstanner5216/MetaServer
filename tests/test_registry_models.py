"""Tests for registry data models."""

from datetime import datetime

import pytest

from src.meta_mcp.registry.models import AllowedInMode, ServerRecord, ToolCandidate, ToolRecord


@pytest.mark.unit
def test_server_record_creation():
    """ServerRecord should be created with valid fields."""
    server = ServerRecord(
        server_id="test_server", description="Test server", risk_level="safe", tags=["test", "core"]
    )

    assert server.server_id == "test_server"
    assert server.description == "Test server"
    assert server.risk_level == "safe"
    assert server.tags == ["test", "core"]
    assert server.embedding_vector is None


@pytest.mark.unit
def test_tool_record_creation():
    """ToolRecord should be created with valid fields."""
    tool = ToolRecord(
        tool_id="test_tool",
        server_id="test_server",
        description_1line="Test tool description",
        description_full="Full test tool description",
        tags=["test"],
        risk_level="safe",
        requires_permission=False,
    )

    assert tool.tool_id == "test_tool"
    assert tool.server_id == "test_server"
    assert tool.description_1line == "Test tool description"
    assert tool.risk_level == "safe"
    assert tool.requires_permission is False
    assert isinstance(tool.registered_at, datetime)


@pytest.mark.unit
def test_tool_record_invariants_valid_risk_level():
    """ToolRecord invariants should pass for valid risk levels."""
    for risk in ["safe", "sensitive", "dangerous"]:
        tool = ToolRecord(
            tool_id="test",
            server_id="test",
            description_1line="Test",
            description_full="Test full",
            tags=["test"],
            risk_level=risk,
            requires_permission=False,
        )
        assert tool.validate_invariants() is True


@pytest.mark.unit
def test_tool_record_invariants_invalid_risk_level():
    """ToolRecord invariants should fail for invalid risk level."""
    tool = ToolRecord(
        tool_id="test",
        server_id="test",
        description_1line="Test",
        description_full="Test full",
        tags=["test"],
        risk_level="invalid",
        requires_permission=False,
    )

    with pytest.raises(AssertionError, match="risk_level must be one of"):
        tool.validate_invariants()


@pytest.mark.unit
def test_tool_record_invariants_empty_description():
    """ToolRecord invariants should fail for empty description."""
    tool = ToolRecord(
        tool_id="test",
        server_id="test",
        description_1line="",
        description_full="Test full",
        tags=["test"],
        risk_level="safe",
        requires_permission=False,
    )

    with pytest.raises(AssertionError, match="description_1line must not be empty"):
        tool.validate_invariants()


@pytest.mark.unit
def test_tool_record_invariants_empty_tags():
    """ToolRecord invariants should fail for empty tags list."""
    tool = ToolRecord(
        tool_id="test",
        server_id="test",
        description_1line="Test",
        description_full="Test full",
        tags=[],
        risk_level="safe",
        requires_permission=False,
    )

    with pytest.raises(AssertionError, match="tags list must have at least one element"):
        tool.validate_invariants()


@pytest.mark.unit
def test_tool_candidate_creation():
    """ToolCandidate should be created without schema fields."""
    candidate = ToolCandidate(
        tool_id="test_tool",
        server_id="test_server",
        description_1line="Test description",
        tags=["test"],
        risk_level="safe",
        relevance_score=0.95,
    )

    assert candidate.tool_id == "test_tool"
    assert candidate.server_id == "test_server"
    assert candidate.description_1line == "Test description"
    assert candidate.tags == ["test"]
    assert candidate.risk_level == "safe"
    assert candidate.relevance_score == 0.95
    assert candidate.allowed_in_mode == AllowedInMode.ALLOWED


@pytest.mark.unit
def test_tool_candidate_no_schema_fields():
    """ToolCandidate must NOT have schema fields (Nuance 5.1)."""
    candidate = ToolCandidate(
        tool_id="test", server_id="test", description_1line="Test", tags=["test"], risk_level="safe"
    )

    # These fields should NOT exist
    assert not hasattr(candidate, "schema_min")
    assert not hasattr(candidate, "schema_full")
    assert not hasattr(candidate, "description_full")


@pytest.mark.unit
def test_tool_candidate_default_relevance_score():
    """ToolCandidate should have default relevance_score of 0.0."""
    candidate = ToolCandidate(
        tool_id="test", server_id="test", description_1line="Test", tags=["test"], risk_level="safe"
    )

    assert candidate.relevance_score == 0.0
    assert candidate.allowed_in_mode == AllowedInMode.ALLOWED


@pytest.mark.unit
def test_tool_record_optional_fields():
    """ToolRecord optional fields should default to None."""
    tool = ToolRecord(
        tool_id="test",
        server_id="test",
        description_1line="Test",
        description_full="Test full",
        tags=["test"],
        risk_level="safe",
    )

    assert tool.requires_permission is False
    assert tool.schema_min is None
    assert tool.schema_full is None
    assert tool.embedding_vector is None
