"""Tests for time utilities module."""

from amzn_nova_act_human_intervention.utils.time_utils import format_seconds_to_human_readable


class TestFormatSecondsToHumanReadable:
    """Test cases for format_seconds_to_human_readable function."""

    def test_less_than_one_minute(self) -> None:
        """Test formatting for less than 60 seconds."""
        assert format_seconds_to_human_readable(0) == "less than a minute"
        assert format_seconds_to_human_readable(30) == "less than a minute"
        assert format_seconds_to_human_readable(59) == "less than a minute"

    def test_exactly_one_minute(self) -> None:
        """Test formatting for exactly 1 minute."""
        assert format_seconds_to_human_readable(60) == "1 minute"

    def test_multiple_minutes_only(self) -> None:
        """Test formatting for multiple minutes (no hours)."""
        assert format_seconds_to_human_readable(120) == "2 minutes"
        assert format_seconds_to_human_readable(300) == "5 minutes"
        assert format_seconds_to_human_readable(1800) == "30 minutes"
        assert format_seconds_to_human_readable(3540) == "59 minutes"

    def test_exactly_one_hour(self) -> None:
        """Test formatting for exactly 1 hour."""
        assert format_seconds_to_human_readable(3600) == "1 hour"

    def test_multiple_hours_only(self) -> None:
        """Test formatting for multiple hours (no remaining minutes)."""
        assert format_seconds_to_human_readable(7200) == "2 hours"
        assert format_seconds_to_human_readable(10800) == "3 hours"
        assert format_seconds_to_human_readable(36000) == "10 hours"

    def test_hours_and_one_minute(self) -> None:
        """Test formatting for hours and exactly 1 minute."""
        assert format_seconds_to_human_readable(3660) == "1 hour and 1 minute"
        assert format_seconds_to_human_readable(7260) == "2 hours and 1 minute"

    def test_one_hour_and_minutes(self) -> None:
        """Test formatting for 1 hour and multiple minutes."""
        assert format_seconds_to_human_readable(3720) == "1 hour and 2 minutes"
        assert format_seconds_to_human_readable(5400) == "1 hour and 30 minutes"

    def test_hours_and_minutes(self) -> None:
        """Test formatting for multiple hours and minutes."""
        assert format_seconds_to_human_readable(7320) == "2 hours and 2 minutes"
        assert format_seconds_to_human_readable(9000) == "2 hours and 30 minutes"
        assert format_seconds_to_human_readable(25200) == "7 hours"
        assert format_seconds_to_human_readable(25260) == "7 hours and 1 minute"
        assert format_seconds_to_human_readable(26100) == "7 hours and 15 minutes"

    def test_large_values(self) -> None:
        """Test formatting for large time values (many hours)."""
        assert format_seconds_to_human_readable(86400) == "24 hours"
        assert format_seconds_to_human_readable(86460) == "24 hours and 1 minute"
        assert format_seconds_to_human_readable(90000) == "25 hours"

    def test_edge_case_59_minutes_59_seconds(self) -> None:
        """Test edge case with 59 minutes and 59 seconds."""
        # 59 minutes 59 seconds = 3599 seconds, should display as "59 minutes"
        assert format_seconds_to_human_readable(3599) == "59 minutes"
