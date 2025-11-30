"""Tests for utility functions."""

from amzn_nova_act_human_intervention_common.utils.utils import Utils


class TestUtils:
    """Test Utils class."""

    def test_is_valid_json_valid(self):
        """Test is_valid_json with valid JSON."""
        assert Utils.is_valid_json('{"key": "value"}') is True
        assert Utils.is_valid_json("[]") is True
        assert Utils.is_valid_json("null") is True
        assert Utils.is_valid_json("123") is True
        assert Utils.is_valid_json('"string"') is True

    def test_is_valid_json_invalid(self):
        """Test is_valid_json with invalid JSON."""
        assert Utils.is_valid_json("invalid json") is False
        assert Utils.is_valid_json('{key: "value"}') is False
        assert Utils.is_valid_json('{"key": }') is False
        assert Utils.is_valid_json("") is False
