"""Tests for plugins module."""

from nas_md.plugins import WorldClockPlugin


class TestWorldClockPlugin:
    def setup_method(self):
        self.plugin = WorldClockPlugin()

    def test_can_handle_date(self):
        assert self.plugin.can_handle("01.01.2025")

    def test_can_handle_time(self):
        assert self.plugin.can_handle("01.01.2025 12:00:00")

    def test_can_handle_timestamp(self):
        assert self.plugin.can_handle("1704067200")

    def test_cannot_handle_text(self):
        assert not self.plugin.can_handle("hello world")

    def test_cannot_handle_small_number(self):
        assert not self.plugin.can_handle("123")

    def test_parse_date(self):
        result = self.plugin.parse_date("01.01.2025")
        assert result is not None
        assert result > 0

    def test_parse_date_invalid(self):
        assert self.plugin.parse_date("invalid") is None

    def test_parse_time(self):
        result = self.plugin.parse_time("01.01.2025 12:00:00")
        assert result is not None
        assert result > 0

    def test_parse_time_invalid(self):
        assert self.plugin.parse_time("invalid") is None

    def test_parse_timestamp_seconds(self):
        result = self.plugin.parse_timestamp("1704067200")
        assert result == 1704067200.0

    def test_parse_timestamp_milliseconds(self):
        result = self.plugin.parse_timestamp("1704067200000")
        assert result == 1704067200.0

    def test_parse_timestamp_microseconds(self):
        result = self.plugin.parse_timestamp("1704067200000000")
        assert result == 1704067200.0

    def test_parse_timestamp_too_small(self):
        assert self.plugin.parse_timestamp("123") is None

    def test_handle_date(self):
        result, err = self.plugin.handle("01.01.2025")
        assert err is None
        assert result is not None
        assert "UTC" in result

    def test_handle_timestamp(self):
        result, err = self.plugin.handle("1704067200")
        assert err is None
        assert result is not None
        assert "UTC" in result

    def test_handle_text(self):
        result, err = self.plugin.handle("hello")
        assert err is None
        assert result == ""
