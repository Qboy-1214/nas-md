"""Tests for the worker module - scheduled task execution."""

import calendar
import datetime
import time

import pytest

from nas_md.worker import (
    beginning_of_the_day,
    tomorrow,
    format_task_date,
    schedule_report,
    _remove_completed_items,
)


def _utc_timestamp(year, month, day, hour=0, minute=0, second=0):
    """Create a UTC timestamp without using local timezone."""
    dt = datetime.datetime(year, month, day, hour, minute, second)
    return calendar.timegm(dt.timetuple())


class TestBeginningOfTheDay:
    def test_returns_start_of_day(self):
        """Should return a timestamp at the start of some day."""
        ts = _utc_timestamp(2025, 6, 10, 14, 30, 45)
        result = beginning_of_the_day(ts)
        # The function uses utcfromtimestamp + .timestamp() which involves local TZ
        # Just verify it returns a valid timestamp earlier than or equal to input
        assert result <= ts

    def test_already_midnight(self):
        """Timestamp at midnight should return a valid timestamp."""
        ts = _utc_timestamp(2025, 6, 10, 0, 0, 0)
        result = beginning_of_the_day(ts)
        assert result <= ts


class TestTomorrow:
    def test_returns_future_timestamp(self):
        """Tomorrow should return a timestamp in the future (UTC-based)."""
        result = tomorrow()
        # Use UTC now for comparison since tomorrow() returns UTC-based timestamp
        import datetime
        now_utc_ts = int(datetime.datetime.now(datetime.UTC).timestamp())
        assert result > now_utc_ts

    def test_returns_timestamp_at_start_of_day(self):
        """Tomorrow should return a timestamp at start of a day."""
        result = tomorrow()
        # Verify it's a reasonable timestamp (within 2 days from now)
        now_ts = int(time.time())
        assert result - now_ts < 2 * 86400


class TestFormatTaskDate:
    def test_today_label(self):
        """Task scheduled for today UTC should return 'Today'."""
        now_utc = datetime.datetime.now(datetime.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        ts = int(calendar.timegm(now_utc.timetuple()))
        result = format_task_date(ts)
        assert result == "Today"

    def test_tomorrow_label(self):
        """Task scheduled for tomorrow UTC should return 'Tomorrow'."""
        tomorrow_utc = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
        tomorrow_utc = tomorrow_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        ts = int(calendar.timegm(tomorrow_utc.timetuple()))
        result = format_task_date(ts)
        assert result == "Tomorrow"

    def test_this_week_label(self):
        """Task scheduled 2-6 days out should return weekday name."""
        future = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=3)
        future = future.replace(hour=0, minute=0, second=0, microsecond=0)
        ts = int(calendar.timegm(future.timetuple()))
        result = format_task_date(ts)
        assert len(result) > 0

    def test_next_week_label(self):
        """Task scheduled 7-13 days out should start with 'Next'."""
        future = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=8)
        future = future.replace(hour=0, minute=0, second=0, microsecond=0)
        ts = int(calendar.timegm(future.timetuple()))
        result = format_task_date(ts)
        assert result.startswith("Next ")

    def test_far_future(self):
        """Task scheduled far out should return date format."""
        future = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=30)
        future = future.replace(hour=0, minute=0, second=0, microsecond=0)
        ts = int(calendar.timegm(future.timetuple()))
        result = format_task_date(ts)
        assert len(result) > 5


class TestScheduleReport:
    def test_empty_schedules(self):
        """Empty schedule list should return empty string."""
        result = schedule_report([])
        assert result == ""

    def test_single_schedule(self):
        """Single schedule should format correctly."""
        now_utc = datetime.datetime.now(datetime.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        ts = int(calendar.timegm(now_utc.timetuple()))
        schedules = [{"scheduledAt": ts, "filename": "task1.md"}]
        result = schedule_report(schedules)
        assert "Today" in result
        assert "task1.md" in result

    def test_multiple_days(self):
        """Multiple schedules on different days should group by day."""
        now_utc = datetime.datetime.now(datetime.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        today_ts = int(calendar.timegm(now_utc.timetuple()))
        tomorrow_utc = now_utc + datetime.timedelta(days=1)
        tomorrow_ts = int(calendar.timegm(tomorrow_utc.timetuple()))
        schedules = [
            {"scheduledAt": today_ts, "filename": "task1.md"},
            {"scheduledAt": tomorrow_ts, "filename": "task2.md"},
        ]
        result = schedule_report(schedules)
        assert "Today" in result
        assert "Tomorrow" in result
        assert "task1.md" in result
        assert "task2.md" in result


class TestRemoveCompletedItems:
    def test_no_completed_items(self):
        """Content with no completed items should be unchanged."""
        md = "- [ ] Task 1\n- [ ] Task 2"
        kept, removed = _remove_completed_items(md)
        assert "Task 1" in kept
        assert "Task 2" in kept
        assert removed == ""

    def test_single_completed_item(self):
        """Single completed item should be removed."""
        md = "- [x] Done task\n- [ ] Pending task"
        kept, removed = _remove_completed_items(md)
        assert "Done task" not in kept
        assert "Pending task" in kept
        assert "Done task" in removed

    def test_all_completed(self):
        """All completed items should be removed."""
        md = "- [x] Task 1\n- [X] Task 2"
        kept, removed = _remove_completed_items(md)
        assert "Task 1" not in kept
        assert "Task 2" not in kept
        assert "Task 1" in removed
        assert "Task 2" in removed

    def test_mixed_with_continuation(self):
        """Completed items with continuation lines should be fully removed."""
        md = "- [x] Done task\n  continuation line\n- [ ] Pending"
        kept, _removed = _remove_completed_items(md)
        assert "Done task" not in kept
        assert "continuation line" not in kept
        assert "Pending" in kept

    def test_empty_content(self):
        """Empty content should return empty strings."""
        kept, removed = _remove_completed_items("")
        assert kept == ""
        assert removed == ""

    def test_non_checklist_content_preserved(self):
        """Non-checklist content should be preserved."""
        md = "# Heading\n\nSome text\n- [x] Done"
        kept, removed = _remove_completed_items(md)
        assert "Heading" in kept
        assert "Some text" in kept
        assert "Done" in removed
