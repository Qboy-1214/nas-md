"""Tests for server.commands modules - verify all commands register correctly."""

from nas_md.server.router import _registry, register_all_modules, get_handler


class TestCommandModules:
    def setup_method(self):
        _registry.clear()

    def test_all_modules_register(self):
        """All command modules should register without errors."""
        total = register_all_modules()
        assert total > 0

    def test_search_commands(self):
        """Search module should register search-related commands."""
        register_all_modules()
        assert get_handler("search") is not None
        assert get_handler("backlink") is not None

    def test_note_commands(self):
        """Note module should register note-related commands."""
        register_all_modules()
        assert get_handler("notes") is not None
        assert get_handler("file") is not None

    def test_task_commands(self):
        """Task module should register task-related commands."""
        register_all_modules()
        assert get_handler("new") is not None
        assert get_handler("done") is not None
        assert get_handler("del") is not None

    def test_settings_commands(self):
        """Settings module should register settings-related commands."""
        register_all_modules()
        assert get_handler("settings") is not None
        assert get_handler("home") is not None
        assert get_handler("help") is not None

    def test_habit_commands(self):
        """Habit module should register habit-related commands."""
        register_all_modules()
        assert get_handler("habits") is not None
        assert get_handler("insights") is not None

    def test_no_duplicate_commands(self):
        """No command should be registered twice."""
        register_all_modules()
        # _registry should have unique keys
        assert len(_registry) == len(set(_registry.keys()))
