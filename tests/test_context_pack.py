"""Tests for ContextPack builder and validator modules."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.meta_mcp.rag.context_pack.builder import (
    ContextPack,
    ContextPackBuilder,
    _count_tokens,
    create_builder,
)
from src.meta_mcp.rag.context_pack.validator import (
    ContextPackValidator,
    ValidationResult,
    ValidationStatus,
    create_validator,
    validate_pack,
)


class TestCountTokens:
    """Tests for _count_tokens utility function."""

    def test_count_tokens_empty_string(self):
        """Should return 0 for empty string."""
        result = _count_tokens("")
        assert result == 0

    def test_count_tokens_simple_text(self):
        """Should estimate tokens for simple text."""
        text = "Hello world this is a test"
        result = _count_tokens(text)
        assert result > 0

    def test_count_tokens_long_text(self):
        """Should count more tokens for longer text."""
        short_text = "Hello"
        long_text = "Hello world this is a much longer text with many words"
        
        short_count = _count_tokens(short_text)
        long_count = _count_tokens(long_text)
        
        assert long_count > short_count


class TestContextPack:
    """Tests for ContextPack dataclass."""

    def _create_sample_pack(self):
        """Create a sample ContextPack for testing."""
        return ContextPack(
            pack_id="test-pack-123",
            query="How to read files?",
            query_rewritten=None,
            lease_id="lease-456",
            scope="read:files",
            embedding_config={"model": "test"},
            retrieval_config={"hybrid": True},
            candidates_raw=[{"id": "c1", "score": 0.9}],
            candidates_selected=[{"id": "c1", "score": 0.9}],
            selected_chunk_full_text={"c1": "Full text content"},
            explainer_output={"explanation": "test"},
            token_budget={"total_budget": 8000, "used_by_selection": 100, "available_for_generation": 7900},
            signature="abcd1234",
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )

    def test_to_dict(self):
        """Should convert pack to dictionary."""
        pack = self._create_sample_pack()
        
        result = pack.to_dict()
        
        assert isinstance(result, dict)
        assert result["pack_id"] == "test-pack-123"
        assert result["query"] == "How to read files?"
        assert result["lease_id"] == "lease-456"

    def test_from_dict(self):
        """Should create pack from dictionary."""
        pack = self._create_sample_pack()
        pack_dict = pack.to_dict()
        
        restored = ContextPack.from_dict(pack_dict)
        
        assert restored.pack_id == pack.pack_id
        assert restored.query == pack.query
        assert restored.lease_id == pack.lease_id

    def test_is_expired_false(self):
        """Should return False when not expired."""
        pack = self._create_sample_pack()
        
        assert pack.is_expired is False

    def test_is_expired_true(self):
        """Should return True when expired."""
        pack = ContextPack(
            pack_id="test",
            query="test",
            query_rewritten=None,
            lease_id="lease",
            scope="scope",
            embedding_config={},
            retrieval_config={},
            candidates_raw=[],
            candidates_selected=[],
            selected_chunk_full_text={},
            explainer_output={},
            token_budget={},
            signature="sig",
            created_at=datetime.utcnow() - timedelta(hours=1),
            expires_at=datetime.utcnow() - timedelta(minutes=5),
        )
        
        assert pack.is_expired is True

    def test_selected_count(self):
        """Should return count of selected candidates."""
        pack = self._create_sample_pack()
        
        assert pack.selected_count == 1

    def test_raw_count(self):
        """Should return count of raw candidates."""
        pack = self._create_sample_pack()
        
        assert pack.raw_count == 1

    def test_available_tokens(self):
        """Should return available tokens for generation."""
        pack = self._create_sample_pack()
        
        assert pack.available_tokens == 7900


class TestContextPackBuilder:
    """Tests for ContextPackBuilder class."""

    def test_init_with_valid_secret(self):
        """Should initialize with valid HMAC secret."""
        builder = ContextPackBuilder(hmac_secret="secret-key-123")
        
        assert builder._hmac_secret == "secret-key-123"
        assert builder._packs_created == 0

    def test_init_with_empty_secret_raises(self):
        """Should raise ValueError for empty secret."""
        with pytest.raises(ValueError, match="cannot be empty"):
            ContextPackBuilder(hmac_secret="")

    def test_init_with_custom_ttl(self):
        """Should accept custom TTL."""
        builder = ContextPackBuilder(hmac_secret="secret", default_ttl_seconds=600)
        
        assert builder._default_ttl_seconds == 600

    def test_init_with_custom_token_budget(self):
        """Should accept custom token budget."""
        builder = ContextPackBuilder(hmac_secret="secret", token_budget=16000)
        
        assert builder._token_budget == 16000

    def test_build_creates_signed_pack(self):
        """Should build a signed ContextPack."""
        builder = ContextPackBuilder(hmac_secret="test-secret")
        
        pack = builder.build(
            query="How to read files?",
            lease_id="lease-123",
            scope="read:files",
            candidates_raw=[{"id": "c1"}],
            selected_chunks=[{"id": "c1"}],
            explainer_output={"explanation": "test"},
            chunk_texts={"c1": "Sample text"},
            embedding_config={"model": "test"},
            retrieval_config={"hybrid": True},
        )
        
        assert pack.pack_id is not None
        assert pack.signature is not None
        assert len(pack.signature) == 64  # SHA-256 hex digest

    def test_build_with_empty_query_raises(self):
        """Should raise ValueError for empty query."""
        builder = ContextPackBuilder(hmac_secret="secret")
        
        with pytest.raises(ValueError, match="Query cannot be empty"):
            builder.build(
                query="",
                lease_id="lease",
                scope="scope",
                candidates_raw=[],
                selected_chunks=[],
                explainer_output={},
                chunk_texts={},
                embedding_config={},
                retrieval_config={},
            )

    def test_build_with_empty_lease_id_raises(self):
        """Should raise ValueError for empty lease_id."""
        builder = ContextPackBuilder(hmac_secret="secret")
        
        with pytest.raises(ValueError, match="lease_id cannot be empty"):
            builder.build(
                query="test query",
                lease_id="",
                scope="scope",
                candidates_raw=[],
                selected_chunks=[],
                explainer_output={},
                chunk_texts={},
                embedding_config={},
                retrieval_config={},
            )

    def test_build_with_empty_scope_raises(self):
        """Should raise ValueError for empty scope."""
        builder = ContextPackBuilder(hmac_secret="secret")
        
        with pytest.raises(ValueError, match="scope cannot be empty"):
            builder.build(
                query="test query",
                lease_id="lease",
                scope="",
                candidates_raw=[],
                selected_chunks=[],
                explainer_output={},
                chunk_texts={},
                embedding_config={},
                retrieval_config={},
            )

    def test_build_with_custom_ttl(self):
        """Should use custom TTL when provided."""
        builder = ContextPackBuilder(hmac_secret="secret", default_ttl_seconds=300)
        
        pack = builder.build(
            query="test",
            lease_id="lease",
            scope="scope",
            candidates_raw=[],
            selected_chunks=[],
            explainer_output={},
            chunk_texts={},
            embedding_config={},
            retrieval_config={},
            ttl_seconds=600,
        )
        
        # TTL should be 600 seconds (10 minutes)
        time_diff = (pack.expires_at - pack.created_at).total_seconds()
        assert 599 <= time_diff <= 601

    def test_build_increments_metrics(self):
        """Should increment packs_created metric."""
        builder = ContextPackBuilder(hmac_secret="secret")
        
        assert builder._packs_created == 0
        
        builder.build(
            query="test",
            lease_id="lease",
            scope="scope",
            candidates_raw=[],
            selected_chunks=[],
            explainer_output={},
            chunk_texts={},
            embedding_config={},
            retrieval_config={},
        )
        
        assert builder._packs_created == 1

    def test_get_metrics(self):
        """Should return builder metrics."""
        builder = ContextPackBuilder(hmac_secret="secret", token_budget=8000)
        
        metrics = builder.get_metrics()
        
        assert "packs_created" in metrics
        assert "total_tokens_budgeted" in metrics
        assert "default_ttl_seconds" in metrics
        assert "token_budget" in metrics


class TestContextPackValidator:
    """Tests for ContextPackValidator class."""

    def _create_valid_pack(self, builder):
        """Create a valid pack using the builder."""
        return builder.build(
            query="test query",
            lease_id="lease-123",
            scope="test:scope",
            candidates_raw=[],
            selected_chunks=[],
            explainer_output={},
            chunk_texts={},
            embedding_config={},
            retrieval_config={},
        )

    def test_init_with_valid_secret(self):
        """Should initialize with valid secret."""
        validator = ContextPackValidator(hmac_secret="secret")
        
        assert validator._hmac_secret == "secret"

    def test_init_with_empty_secret_raises(self):
        """Should raise ValueError for empty secret."""
        with pytest.raises(ValueError, match="cannot be empty"):
            ContextPackValidator(hmac_secret="")

    def test_validate_valid_pack(self):
        """Should validate a valid, unexpired pack."""
        secret = "shared-secret-key"
        builder = ContextPackBuilder(hmac_secret=secret)
        validator = ContextPackValidator(hmac_secret=secret)
        
        pack = self._create_valid_pack(builder)
        result = validator.validate(pack)
        
        assert result.is_valid is True
        assert result.status == ValidationStatus.VALID
        assert result.error_message == ""

    def test_validate_tampered_pack(self):
        """Should reject pack with tampered data."""
        secret = "shared-secret-key"
        builder = ContextPackBuilder(hmac_secret=secret)
        validator = ContextPackValidator(hmac_secret=secret)
        
        pack = self._create_valid_pack(builder)
        
        # Tamper with the pack
        pack.query = "tampered query"
        
        result = validator.validate(pack)
        
        assert result.is_valid is False
        assert result.status == ValidationStatus.INVALID_SIGNATURE

    def test_validate_wrong_secret(self):
        """Should reject pack signed with different secret."""
        builder = ContextPackBuilder(hmac_secret="builder-secret")
        validator = ContextPackValidator(hmac_secret="different-secret")
        
        pack = self._create_valid_pack(builder)
        result = validator.validate(pack)
        
        assert result.is_valid is False
        assert result.status == ValidationStatus.INVALID_SIGNATURE

    def test_validate_expired_pack(self):
        """Should reject expired pack."""
        secret = "secret"
        builder = ContextPackBuilder(hmac_secret=secret, default_ttl_seconds=1)
        validator = ContextPackValidator(hmac_secret=secret)
        
        pack = builder.build(
            query="test",
            lease_id="lease",
            scope="scope",
            candidates_raw=[],
            selected_chunks=[],
            explainer_output={},
            chunk_texts={},
            embedding_config={},
            retrieval_config={},
            ttl_seconds=-10,  # Already expired
        )
        
        result = validator.validate(pack)
        
        # Note: pack may fail signature check if created_at > expires_at
        # The important thing is it's not valid
        assert result.is_valid is False

    def test_is_expired(self):
        """Should correctly check pack expiration."""
        secret = "secret"
        builder = ContextPackBuilder(hmac_secret=secret)
        validator = ContextPackValidator(hmac_secret=secret)
        
        pack = self._create_valid_pack(builder)
        
        # Fresh pack should not be expired
        assert validator.is_expired(pack) is False

    def test_time_until_expiration(self):
        """Should return time until expiration."""
        secret = "secret"
        builder = ContextPackBuilder(hmac_secret=secret, default_ttl_seconds=300)
        validator = ContextPackValidator(hmac_secret=secret)
        
        pack = self._create_valid_pack(builder)
        
        remaining = validator.time_until_expiration(pack)
        
        assert remaining is not None
        assert remaining > 0
        assert remaining <= 300

    def test_get_metrics(self):
        """Should return validator metrics."""
        validator = ContextPackValidator(hmac_secret="secret")
        
        metrics = validator.get_metrics()
        
        assert "validations_performed" in metrics
        assert "validations_passed" in metrics
        assert "validations_failed_signature" in metrics
        assert "validations_failed_expired" in metrics
        assert "pass_rate" in metrics


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_to_dict(self):
        """Should convert result to dictionary."""
        result = ValidationResult(
            is_valid=True,
            status=ValidationStatus.VALID,
            error_message="",
            validated_at=datetime.utcnow(),
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["is_valid"] is True
        assert result_dict["status"] == "valid"
        assert result_dict["error_message"] == ""


class TestConvenienceFunctions:
    """Tests for module convenience functions."""

    def test_create_builder(self):
        """Should create ContextPackBuilder."""
        builder = create_builder(hmac_secret="secret", default_ttl_seconds=600)
        
        assert isinstance(builder, ContextPackBuilder)
        assert builder._default_ttl_seconds == 600

    def test_create_validator(self):
        """Should create ContextPackValidator."""
        validator = create_validator(hmac_secret="secret")
        
        assert isinstance(validator, ContextPackValidator)

    def test_validate_pack_function(self):
        """Should validate pack using convenience function."""
        secret = "secret"
        builder = ContextPackBuilder(hmac_secret=secret)
        
        pack = builder.build(
            query="test",
            lease_id="lease",
            scope="scope",
            candidates_raw=[],
            selected_chunks=[],
            explainer_output={},
            chunk_texts={},
            embedding_config={},
            retrieval_config={},
        )
        
        is_valid, error_message = validate_pack(pack, hmac_secret=secret)
        
        assert is_valid is True
        assert error_message == ""
