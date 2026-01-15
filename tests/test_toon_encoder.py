"""Tests for TOON encoder functionality."""

import pytest

from src.meta_mcp.toon import encode_output


class TestBasicEncoding:
    """Test basic TOON encoding behavior."""

    def test_arrays_above_threshold_are_compressed(self):
        """Arrays exceeding threshold should be compressed to TOON metadata."""
        data = {"files": ["a", "b", "c", "d", "e", "f"]}
        result = encode_output(data, threshold=5)

        assert isinstance(result["files"], dict)
        assert result["files"]["__toon"] is True
        assert result["files"]["count"] == 6
        assert result["files"]["sample"] == ["a", "b", "c"]

    def test_arrays_at_threshold_are_preserved(self):
        """Arrays exactly at threshold should NOT be compressed."""
        data = {"files": ["a", "b", "c", "d", "e"]}
        result = encode_output(data, threshold=5)

        # Should be preserved as-is
        assert isinstance(result["files"], list)
        assert result["files"] == ["a", "b", "c", "d", "e"]

    def test_arrays_below_threshold_are_preserved(self):
        """Arrays below threshold should be preserved unchanged."""
        data = {"files": ["a", "b", "c"]}
        result = encode_output(data, threshold=5)

        # Should be preserved as-is
        assert isinstance(result["files"], list)
        assert result["files"] == ["a", "b", "c"]

    def test_empty_arrays_are_preserved(self):
        """Empty arrays should be preserved."""
        data = {"files": []}
        result = encode_output(data, threshold=5)

        assert isinstance(result["files"], list)
        assert result["files"] == []

    def test_non_array_data_unchanged(self):
        """Non-array data should pass through unchanged."""
        data = {"message": "Hello", "count": 42, "active": True, "score": 3.14, "nullable": None}
        result = encode_output(data, threshold=5)

        assert result == data

    def test_top_level_array_compression(self):
        """Top-level arrays should be compressed if they exceed threshold."""
        data = ["item1", "item2", "item3", "item4", "item5", "item6"]
        result = encode_output(data, threshold=5)

        assert isinstance(result, dict)
        assert result["__toon"] is True
        assert result["count"] == 6
        assert result["sample"] == ["item1", "item2", "item3"]

    def test_top_level_array_preservation(self):
        """Top-level arrays below threshold should be preserved."""
        data = ["item1", "item2", "item3"]
        result = encode_output(data, threshold=5)

        assert isinstance(result, list)
        assert result == ["item1", "item2", "item3"]


class TestNestedStructures:
    """Test TOON encoding with nested data structures."""

    def test_nested_arrays_in_dict(self):
        """Nested arrays in dictionaries should be recursively encoded."""
        data = {"level1": {"level2": {"items": ["a", "b", "c", "d", "e", "f"]}}}
        result = encode_output(data, threshold=5)

        assert result["level1"]["level2"]["items"]["__toon"] is True
        assert result["level1"]["level2"]["items"]["count"] == 6

    def test_arrays_in_arrays(self):
        """Arrays containing arrays should be recursively encoded."""
        data = {
            "matrix": [
                ["a", "b", "c", "d", "e", "f"],
                ["1", "2", "3"],
                ["x", "y", "z", "p", "q", "r", "s"],
            ]
        }
        result = encode_output(data, threshold=5)

        # Outer array is below threshold (3 items), should be preserved
        assert isinstance(result["matrix"], list)
        assert len(result["matrix"]) == 3

        # First inner array exceeds threshold, should be compressed
        assert result["matrix"][0]["__toon"] is True
        assert result["matrix"][0]["count"] == 6

        # Second inner array is below threshold, should be preserved
        assert isinstance(result["matrix"][1], list)
        assert result["matrix"][1] == ["1", "2", "3"]

        # Third inner array exceeds threshold, should be compressed
        assert result["matrix"][2]["__toon"] is True
        assert result["matrix"][2]["count"] == 7

    def test_mixed_nested_structures(self):
        """Complex mixed structures should be correctly encoded."""
        data = {
            "users": [
                {"id": 1, "tags": ["a", "b", "c", "d", "e", "f"]},
                {"id": 2, "tags": ["x", "y"]},
                {"id": 3, "tags": ["p", "q", "r", "s", "t", "u", "v"]},
            ],
            "metadata": {"count": 3, "active": True},
        }
        result = encode_output(data, threshold=5)

        # Top-level users array is below threshold
        assert isinstance(result["users"], list)

        # First user's tags exceed threshold
        assert result["users"][0]["tags"]["__toon"] is True
        assert result["users"][0]["tags"]["count"] == 6

        # Second user's tags are below threshold
        assert isinstance(result["users"][1]["tags"], list)
        assert result["users"][1]["tags"] == ["x", "y"]

        # Third user's tags exceed threshold
        assert result["users"][2]["tags"]["__toon"] is True
        assert result["users"][2]["tags"]["count"] == 7

        # Metadata unchanged
        assert result["metadata"] == {"count": 3, "active": True}


class TestMetadataFormat:
    """Test TOON metadata structure and content."""

    def test_metadata_includes_toon_flag(self):
        """Compressed output must include __toon: true."""
        data = ["a", "b", "c", "d", "e", "f"]
        result = encode_output(data, threshold=5)

        assert "__toon" in result
        assert result["__toon"] is True

    def test_metadata_includes_count(self):
        """Compressed output must include accurate count."""
        data = {"items": list(range(50))}
        result = encode_output(data, threshold=5)

        assert result["items"]["count"] == 50

    def test_metadata_includes_sample(self):
        """Compressed output must include first 3 items as sample."""
        data = {"items": ["first", "second", "third", "fourth", "fifth", "sixth"]}
        result = encode_output(data, threshold=5)

        assert result["items"]["sample"] == ["first", "second", "third"]

    def test_sample_contains_fewer_than_three_if_array_small(self):
        """Sample should contain all items if array has < 3 items but > threshold."""
        # Edge case: array with 2 items but threshold of 1
        data = {"items": ["a", "b"]}
        result = encode_output(data, threshold=1)

        assert result["items"]["sample"] == ["a", "b"]

    def test_sample_preserves_item_types(self):
        """Sample should preserve the types of items."""
        data = {"items": [1, "two", 3.0, True, None, "six", 7]}
        result = encode_output(data, threshold=5)

        assert result["items"]["sample"] == [1, "two", 3.0]
        assert isinstance(result["items"]["sample"][0], int)
        assert isinstance(result["items"]["sample"][1], str)
        assert isinstance(result["items"]["sample"][2], float)


class TestThresholdConfiguration:
    """Test different threshold values."""

    def test_threshold_of_one(self):
        """Threshold of 1 should compress arrays with 2+ items."""
        data = {"items": ["a", "b"]}
        result = encode_output(data, threshold=1)

        assert result["items"]["__toon"] is True
        assert result["items"]["count"] == 2

    def test_threshold_of_ten(self):
        """Threshold of 10 should preserve arrays with <= 10 items."""
        data = {"items": list(range(10))}
        result = encode_output(data, threshold=10)

        assert isinstance(result["items"], list)
        assert len(result["items"]) == 10

    def test_high_threshold(self):
        """High threshold should preserve most arrays."""
        data = {"items": list(range(100))}
        result = encode_output(data, threshold=1000)

        assert isinstance(result["items"], list)
        assert len(result["items"]) == 100

    def test_invalid_threshold_raises_error(self):
        """Threshold <= 0 should raise ValueError."""
        with pytest.raises(ValueError, match="threshold must be > 0"):
            encode_output({"items": [1, 2, 3]}, threshold=0)

        with pytest.raises(ValueError, match="threshold must be > 0"):
            encode_output({"items": [1, 2, 3]}, threshold=-5)


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_none_value(self):
        """None should be preserved."""
        result = encode_output(None, threshold=5)
        assert result is None

    def test_primitive_values(self):
        """Primitive values should be preserved."""
        assert encode_output("string", threshold=5) == "string"
        assert encode_output(42, threshold=5) == 42
        assert encode_output(3.14, threshold=5) == 3.14
        assert encode_output(True, threshold=5) is True

    def test_tuple_handling(self):
        """Tuples should be treated like lists."""
        data = {"coords": (1, 2, 3, 4, 5, 6)}
        result = encode_output(data, threshold=5)

        # Tuple exceeds threshold, should be compressed
        assert result["coords"]["__toon"] is True
        assert result["coords"]["count"] == 6

    def test_tuple_below_threshold(self):
        """Tuples below threshold should be converted to lists."""
        data = {"coords": (1, 2, 3)}
        result = encode_output(data, threshold=5)

        # Should be converted to list
        assert isinstance(result["coords"], list)
        assert result["coords"] == [1, 2, 3]

    def test_deeply_nested_structure(self):
        """Deeply nested structures should be handled correctly."""
        data = {"a": {"b": {"c": {"d": {"e": ["i1", "i2", "i3", "i4", "i5", "i6"]}}}}}
        result = encode_output(data, threshold=5)

        assert result["a"]["b"]["c"]["d"]["e"]["__toon"] is True

    def test_mixed_types_in_array(self):
        """Arrays with mixed types should be handled correctly."""
        data = {"mixed": ["string", 42, 3.14, True, None, {"nested": "dict"}, ["nested", "list"]]}
        result = encode_output(data, threshold=5)

        # Array exceeds threshold
        assert result["mixed"]["__toon"] is True
        assert result["mixed"]["count"] == 7
        assert len(result["mixed"]["sample"]) == 3

    def test_array_of_objects_with_arrays(self):
        """Array of objects where objects contain arrays."""
        data = {
            "items": [
                {"id": 1, "tags": ["a", "b", "c", "d", "e", "f"]},
                {"id": 2, "tags": ["x", "y", "z", "p", "q", "r"]},
                {"id": 3, "tags": ["m", "n", "o", "s", "t", "u"]},
                {"id": 4, "tags": ["1", "2", "3", "4", "5", "6"]},
                {"id": 5, "tags": ["w", "x", "y", "z", "a", "b"]},
                {"id": 6, "tags": ["p", "q", "r", "s", "t", "u"]},
            ]
        }
        result = encode_output(data, threshold=5)

        # Top-level array exceeds threshold
        assert result["items"]["__toon"] is True
        assert result["items"]["count"] == 6

        # Sample should contain 3 items
        assert len(result["items"]["sample"]) == 3

        # Each item in sample should have its tags compressed
        for item in result["items"]["sample"]:
            assert item["tags"]["__toon"] is True
            assert item["tags"]["count"] == 6

    def test_empty_dict(self):
        """Empty dictionary should be preserved."""
        result = encode_output({}, threshold=5)
        assert result == {}

    def test_dict_with_no_arrays(self):
        """Dictionary with no arrays should be unchanged."""
        data = {"name": "test", "value": 42, "nested": {"key": "value"}}
        result = encode_output(data, threshold=5)
        assert result == data
