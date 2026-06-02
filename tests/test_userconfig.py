"""Tests for userconfig module."""

import pytest

from nas_md.fs import FS, DIR_USER_ROOT
from nas_md.userconfig import (
    UserConfig, DEFAULT_CONFIG,
    MODE_CHAT, MODE_FULL, MODE_TASKS, MODE_NOTES, MODE_JOURNAL,
)


@pytest.fixture
def mem_fs():
    return FS("/testuser", backend="mem")


@pytest.fixture
def user_config(mem_fs):
    return UserConfig(mem_fs, 123, "config.json")


class TestUserConfig:
    def test_create_default(self, user_config, mem_fs):
        user_config.create_default_if_not_exists()
        exists, _ = mem_fs.exists(DIR_USER_ROOT, "config.json")
        assert exists

    def test_timezone_default(self, user_config):
        assert user_config.timezone() == "UTC"

    def test_set_timezone(self, user_config):
        user_config.set_timezone("Europe/Moscow")
        assert user_config.timezone() == "Europe/Moscow"

    def test_chat_only_mode_default(self, user_config):
        assert not user_config.chat_only_mode()

    def test_set_mode(self, user_config):
        user_config.set_mode(MODE_CHAT)
        assert user_config.chat_only_mode()

    def test_tasks_only_mode(self, user_config):
        user_config.set_mode(MODE_TASKS)
        assert user_config.tasks_only_mode()

    def test_notes_only_mode(self, user_config):
        user_config.set_mode(MODE_NOTES)
        assert user_config.notes_only_mode()

    def test_journal_only_mode(self, user_config):
        user_config.set_mode(MODE_JOURNAL)
        assert user_config.journal_only_mode()

    def test_pomodoro_duration_default(self, user_config):
        assert user_config.pomodoro_duration() == 50 * 60

    def test_set_pomodoro_duration(self, user_config):
        user_config.set_pomodoro_duration(25 * 60)
        assert user_config.pomodoro_duration() == 25 * 60

    def test_set_pomodoro_duration_invalid(self, user_config):
        with pytest.raises(ValueError):
            user_config.set_pomodoro_duration(0)
        with pytest.raises(ValueError):
            user_config.set_pomodoro_duration(-1)
        with pytest.raises(ValueError):
            user_config.set_pomodoro_duration(86401)

    def test_schedules_default(self, user_config):
        assert user_config.schedules() == []

    def test_add_to_schedule(self, user_config):
        user_config.add_to_schedule("task.md", 1000, "0 9 * * *")
        schedules = user_config.schedules()
        assert len(schedules) == 1
        assert schedules[0]["filename"] == "task.md"

    def test_del_from_schedule(self, user_config):
        user_config.add_to_schedule("task.md", 1000, "0 9 * * *")
        user_config.del_from_schedule("task.md")
        assert user_config.schedules() == []

    def test_two_emojis_default(self, user_config):
        assert not user_config.two_emojis_per_button_enabled()

    def test_quick_habits_default(self, user_config):
        assert not user_config.quick_habits_enabled()

    def test_channels_default(self, user_config):
        assert user_config.channels() == []

    def test_persistence(self, mem_fs):
        """Test that config persists across UserConfig instances."""
        config1 = UserConfig(mem_fs, 456, "config.json")
        config1.create_default_if_not_exists()
        config1.set_timezone("Asia/Tokyo")
        config1.set_mode(MODE_TASKS)

        config2 = UserConfig(mem_fs, 456, "config.json")
        assert config2.timezone() == "Asia/Tokyo"
        assert config2.tasks_only_mode()
