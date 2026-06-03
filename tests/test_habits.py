"""Tests for habits module."""

import pytest

from nas_md.fs import FS, DIR_HABITS, DIR_INSIGHTS
from nas_md.habits import (
    habits,
    last_week_habits,
    write as write_habits,
    emoji_for_habit,
    MOOD_HABIT,
)


@pytest.fixture
def mem_fs():
    return FS("/testuser", backend="mem")


class TestHabits:
    def test_empty_habits(self, mem_fs):
        result, err = habits(mem_fs, 2025)
        assert err is None or not err
        assert result == {}

    def test_with_habit_files(self, mem_fs):
        mem_fs.write(DIR_HABITS, "Running.md", "🏃")
        mem_fs.write(DIR_HABITS, "Reading.md", "📚")
        result, err = habits(mem_fs, 2025)
        assert err is None or not err
        assert "Running" in result
        assert "Reading" in result

    def test_with_insights(self, mem_fs):
        mem_fs.write(DIR_HABITS, "Running.md", "🏃")
        insights_content = "### January\n🟢⚪️🟢 Running\n"
        mem_fs.write(DIR_INSIGHTS, "2025 Habits.md", insights_content)
        result, err = habits(mem_fs, 2025)
        assert err is None or not err
        assert "Running" in result
        # Day 1 = completed, day 2 = skipped, day 3 = completed
        assert result["Running"].get(1) == 1
        assert result["Running"].get(2) == 0
        assert result["Running"].get(3) == 1


class TestLastWeekHabits:
    def test_empty(self, mem_fs):
        result, err = last_week_habits(mem_fs)
        assert err is None or not err
        # Mood is always present (it's a built-in habit)
        assert MOOD_HABIT in result
        assert len(result[MOOD_HABIT]) == 7

    def test_with_habits(self, mem_fs):
        mem_fs.write(DIR_HABITS, "Running.md", "🏃")
        result, err = last_week_habits(mem_fs)
        assert err is None or not err
        assert "Running" in result
        # Should have 7 days
        assert len(result["Running"]) == 7


class TestWrite:
    def test_write_empty(self, mem_fs):
        write_habits(mem_fs, 2025, {})
        exists, _ = mem_fs.exists(DIR_INSIGHTS, "2025 Habits.md")
        assert exists

    def test_write_with_data(self, mem_fs):
        data = {"Running": {1: 1, 2: 0, 3: 1}}
        write_habits(mem_fs, 2025, data)
        content, _ = mem_fs.read(DIR_INSIGHTS, "2025 Habits.md")
        assert "Running" in content
        assert "January" in content


class TestEmojiForHabit:
    def test_get_emoji(self, mem_fs):
        mem_fs.write(DIR_HABITS, "Running.md", "🏃")
        assert emoji_for_habit(mem_fs, "Running") == "🏃"

    def test_default_emoji(self, mem_fs):
        assert emoji_for_habit(mem_fs, "Nonexistent") == "⚡️"
