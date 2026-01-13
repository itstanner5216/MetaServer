"""Tests for TOON threshold configuration and feature flag."""

import pytest
from unittest.mock import patch
from src.meta_mcp.toon import encode_output
from src.meta_mcp.config import Config
from src.meta_mcp.middleware import GovernanceMiddleware


class TestThresholdConfiguration:
    """Test TOON threshold configuration from Config."""

    def test_default_threshold_value(self):
        """Default TOON_ARRAY_THRESHOLD should be 5."""
        assert Config.TOON_ARRAY_THRESHOLD == 5

    def test_default_toon_enabled(self):
        """Default ENABLE_TOON_OUTPUTS should be True."""
        assert Config.ENABLE_TOON_OUTPUTS is True

    def test_threshold_applied_correctly(self):
        """Encoding should respect configured threshold."""
        # Array of length 6 with threshold 5 should be compressed
        data = {"items": list(range(6))}
        result = encode_output(data, threshold=Config.TOON_ARRAY_THRESHOLD)

        assert result["items"]["__toon"] is True
        assert result["items"]["count"] == 6

    def test_custom_threshold_value(self):
        """Encoding should work with custom threshold values."""
        # Test with threshold of 10
        data = {"items": list(range(8))}
        result = encode_output(data, threshold=10)

        # Array of 8 with threshold 10 should NOT be compressed
        assert isinstance(result["items"], list)
        assert len(result["items"]) == 8

        # But array of 11 should be compressed
        data2 = {"items": list(range(11))}
        result2 = encode_output(data2, threshold=10)

        assert result2["items"]["__toon"] is True
        assert result2["items"]["count"] == 11


class TestFeatureFlagToggling:
    """Test ENABLE_TOON_OUTPUTS feature flag behavior."""

    def test_toon_encoding_when_enabled(self):
        """When ENABLE_TOON_OUTPUTS is True, encoding should be applied."""
        with patch.object(Config, 'ENABLE_TOON_OUTPUTS', True):
            middleware = GovernanceMiddleware()
            data = {"items": list(range(10))}

            result = middleware._apply_toon_encoding(data)

            # Should be compressed (threshold is 5 by default)
            assert result["items"]["__toon"] is True
            assert result["items"]["count"] == 10

    def test_toon_encoding_when_disabled(self):
        """When ENABLE_TOON_OUTPUTS is False, encoding should be skipped."""
        with patch.object(Config, 'ENABLE_TOON_OUTPUTS', False):
            middleware = GovernanceMiddleware()
            data = {"items": list(range(10))}

            result = middleware._apply_toon_encoding(data)

            # Should be unchanged
            assert isinstance(result["items"], list)
            assert len(result["items"]) == 10
            assert result == data

    def test_feature_flag_affects_all_encoding(self):
        """Feature flag should control all TOON encoding operations."""
        test_data = {
            "large_array": list(range(100)),
            "nested": {
                "another_large_array": list(range(50))
            }
        }

        # Test with flag enabled
        with patch.object(Config, 'ENABLE_TOON_OUTPUTS', True):
            middleware = GovernanceMiddleware()
            result_enabled = middleware._apply_toon_encoding(test_data)

            assert result_enabled["large_array"]["__toon"] is True
            assert result_enabled["nested"]["another_large_array"]["__toon"] is True

        # Test with flag disabled
        with patch.object(Config, 'ENABLE_TOON_OUTPUTS', False):
            middleware = GovernanceMiddleware()
            result_disabled = middleware._apply_toon_encoding(test_data)

            assert isinstance(result_disabled["large_array"], list)
            assert isinstance(result_disabled["nested"]["another_large_array"], list)


class TestMiddlewareIntegration:
    """Test TOON encoding integration in middleware."""

    def test_middleware_applies_toon_to_results(self):
        """Middleware should apply TOON encoding to tool results."""
        middleware = GovernanceMiddleware()

        # Simulate a tool result with large arrays
        tool_result = {
            "files": [f"file{i}.txt" for i in range(50)],
            "message": "Success"
        }

        with patch.object(Config, 'ENABLE_TOON_OUTPUTS', True):
            encoded = middleware._apply_toon_encoding(tool_result)

            assert encoded["files"]["__toon"] is True
            assert encoded["files"]["count"] == 50
            assert encoded["message"] == "Success"

    def test_middleware_handles_encoding_errors_gracefully(self):
        """Middleware should return original result if encoding fails."""
        middleware = GovernanceMiddleware()

        # Test with data that might cause encoding issues
        tool_result = {"data": "valid_data"}

        # Mock encode_output to raise an exception
        with patch('src.meta_mcp.middleware.encode_output', side_effect=Exception("Encoding error")):
            result = middleware._apply_toon_encoding(tool_result)

            # Should return original result on error
            assert result == tool_result

    def test_middleware_preserves_non_array_results(self):
        """Middleware should preserve results without arrays."""
        middleware = GovernanceMiddleware()

        tool_result = {
            "status": "success",
            "code": 200,
            "data": {
                "name": "test",
                "value": 42
            }
        }

        encoded = middleware._apply_toon_encoding(tool_result)

        # Should be unchanged
        assert encoded == tool_result

    def test_middleware_respects_threshold_config(self):
        """Middleware should use threshold from Config."""
        middleware = GovernanceMiddleware()

        # Create array exactly at threshold
        tool_result = {"items": list(range(Config.TOON_ARRAY_THRESHOLD))}

        encoded = middleware._apply_toon_encoding(tool_result)

        # Should NOT be compressed (at threshold, not above)
        assert isinstance(encoded["items"], list)
        assert len(encoded["items"]) == Config.TOON_ARRAY_THRESHOLD

        # Create array just above threshold
        tool_result2 = {"items": list(range(Config.TOON_ARRAY_THRESHOLD + 1))}

        encoded2 = middleware._apply_toon_encoding(tool_result2)

        # Should be compressed
        assert encoded2["items"]["__toon"] is True


class TestTokenThreshold:
    """Test TOON_TOKEN_THRESHOLD configuration (currently not used in Phase 6)."""

    def test_token_threshold_config_exists(self):
        """TOON_TOKEN_THRESHOLD should be defined in Config."""
        assert hasattr(Config, 'TOON_TOKEN_THRESHOLD')
        assert isinstance(Config.TOON_TOKEN_THRESHOLD, int)
        assert Config.TOON_TOKEN_THRESHOLD > 0

    def test_token_threshold_default_value(self):
        """Default TOON_TOKEN_THRESHOLD should be 200."""
        assert Config.TOON_TOKEN_THRESHOLD == 200


class TestEndToEndScenarios:
    """Test complete encoding scenarios with configuration."""

    def test_list_directory_scenario(self):
        """Simulate list_directory tool output with many files."""
        # Simulate output from a directory with 100 files
        tool_result = {
            "path": "/workspace/data",
            "files": [f"file_{i:03d}.txt" for i in range(100)],
            "directories": ["subdir1", "subdir2"],
            "total_items": 102
        }

        middleware = GovernanceMiddleware()
        with patch.object(Config, 'ENABLE_TOON_OUTPUTS', True):
            encoded = middleware._apply_toon_encoding(tool_result)

            # Files array should be compressed
            assert encoded["files"]["__toon"] is True
            assert encoded["files"]["count"] == 100
            assert len(encoded["files"]["sample"]) == 3

            # Directories array should be preserved (only 2 items)
            assert isinstance(encoded["directories"], list)
            assert encoded["directories"] == ["subdir1", "subdir2"]

            # Other fields unchanged
            assert encoded["path"] == "/workspace/data"
            assert encoded["total_items"] == 102

    def test_search_results_scenario(self):
        """Simulate search tool output with many matches."""
        tool_result = {
            "query": "test",
            "matches": [
                {"file": f"test_{i}.py", "line": i, "content": f"test content {i}"}
                for i in range(50)
            ],
            "total_matches": 50
        }

        middleware = GovernanceMiddleware()
        with patch.object(Config, 'ENABLE_TOON_OUTPUTS', True):
            encoded = middleware._apply_toon_encoding(tool_result)

            # Matches array should be compressed
            assert encoded["matches"]["__toon"] is True
            assert encoded["matches"]["count"] == 50
            assert len(encoded["matches"]["sample"]) == 3

            # First sample item should be a complete dict
            assert "file" in encoded["matches"]["sample"][0]
            assert "line" in encoded["matches"]["sample"][0]
            assert "content" in encoded["matches"]["sample"][0]

    def test_database_query_scenario(self):
        """Simulate database query with many rows."""
        tool_result = {
            "query": "SELECT * FROM users",
            "rows": [
                {"id": i, "name": f"user_{i}", "email": f"user{i}@example.com"}
                for i in range(200)
            ],
            "row_count": 200,
            "execution_time_ms": 45
        }

        middleware = GovernanceMiddleware()
        with patch.object(Config, 'ENABLE_TOON_OUTPUTS', True):
            encoded = middleware._apply_toon_encoding(tool_result)

            # Rows should be compressed
            assert encoded["rows"]["__toon"] is True
            assert encoded["rows"]["count"] == 200

            # Sample should show structure
            assert len(encoded["rows"]["sample"]) == 3
            assert encoded["rows"]["sample"][0]["id"] == 0
            assert encoded["rows"]["sample"][0]["name"] == "user_0"

    def test_mixed_small_and_large_arrays(self):
        """Test output with both small and large arrays."""
        tool_result = {
            "small_list": ["a", "b", "c"],
            "large_list": list(range(100)),
            "another_small": [1, 2],
            "another_large": [f"item_{i}" for i in range(50)]
        }

        middleware = GovernanceMiddleware()
        with patch.object(Config, 'ENABLE_TOON_OUTPUTS', True):
            encoded = middleware._apply_toon_encoding(tool_result)

            # Small arrays preserved
            assert isinstance(encoded["small_list"], list)
            assert isinstance(encoded["another_small"], list)

            # Large arrays compressed
            assert encoded["large_list"]["__toon"] is True
            assert encoded["large_list"]["count"] == 100
            assert encoded["another_large"]["__toon"] is True
            assert encoded["another_large"]["count"] == 50
