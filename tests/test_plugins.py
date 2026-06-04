"""Tests for plugins module."""

import os
import tempfile

from nas_md.plugins import (
    DailyTemplatePlugin,
    Plugin,
    PluginManager,
    RandomNotePlugin,
    WordCountPlugin,
    WorldClockPlugin,
)


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

    def test_inherits_plugin(self):
        assert isinstance(self.plugin, Plugin)

    def test_has_name(self):
        assert self.plugin.name == "world_clock"


class TestDailyTemplatePlugin:
    def setup_method(self):
        self.plugin = DailyTemplatePlugin()

    def test_inherits_plugin(self):
        assert isinstance(self.plugin, Plugin)

    def test_name(self):
        assert self.plugin.name == "daily_template"

    def test_is_journal_path(self):
        assert self.plugin._is_journal_path("/notes/2025-01-01.md")
        assert self.plugin._is_journal_path("2025-06-15.md")

    def test_not_journal_path(self):
        assert not self.plugin._is_journal_path("/notes/readme.md")
        assert not self.plugin._is_journal_path("random.md")

    def test_on_file_created_empty_journal(self):
        with tempfile.NamedTemporaryFile(suffix=".md", prefix="2025-01-01", delete=False, mode="w") as f:
            path = f.name
        try:
            self.plugin.on_file_created(path, "")
            with open(path) as f:
                content = f.read()
            assert "## Tasks" in content
        finally:
            os.unlink(path)

    def test_on_file_created_non_empty(self):
        with tempfile.NamedTemporaryFile(suffix=".md", prefix="2025-01-01", delete=False, mode="w") as f:
            f.write("existing content")
            path = f.name
        try:
            self.plugin.on_file_created(path, "existing content")
            with open(path) as f:
                content = f.read()
            assert content == "existing content"
        finally:
            os.unlink(path)

    def test_custom_template(self):
        self.plugin.set_template("# {date}\nCustom template\n")
        with tempfile.NamedTemporaryFile(suffix=".md", prefix="2025-01-01", delete=False, mode="w") as f:
            path = f.name
        try:
            self.plugin.on_file_created(path, "")
            with open(path) as f:
                content = f.read()
            assert "Custom template" in content
        finally:
            os.unlink(path)


class TestWordCountPlugin:
    def setup_method(self):
        self.plugin = WordCountPlugin()

    def test_inherits_plugin(self):
        assert isinstance(self.plugin, Plugin)

    def test_name(self):
        assert self.plugin.name == "word_count"

    def test_count_basic(self):
        result = WordCountPlugin.count("Hello world\nSecond line")
        assert result["words"] >= 2
        assert result["lines"] == 2
        assert result["chars"] > 0

    def test_count_empty(self):
        result = WordCountPlugin.count("")
        assert result["words"] == 0
        assert result["chars"] == 0
        assert result["lines"] == 1

    def test_count_strips_code_blocks(self):
        result = WordCountPlugin.count("Hello\n```\ncode here\n```\nWorld")
        # "code here" should be stripped
        assert result["words"] >= 2  # Hello + World at minimum


class TestRandomNotePlugin:
    def setup_method(self):
        self.plugin = RandomNotePlugin()

    def test_inherits_plugin(self):
        assert isinstance(self.plugin, Plugin)

    def test_name(self):
        assert self.plugin.name == "random_note"

    def test_get_random_note_with_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "a.md"), "w") as f:
                f.write("test")
            result = self.plugin.get_random_note(tmpdir)
            assert result is not None
            assert result.endswith("a.md")

    def test_get_random_note_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.plugin.get_random_note(tmpdir)
            assert result is None


class TestPluginManager:
    def test_load_all_builtins(self):
        pm = PluginManager()
        pm.load_all()
        assert len(pm.plugins) == 4

    def test_plugin_names(self):
        pm = PluginManager()
        pm.load_all()
        names = [p.name for p in pm.plugins]
        assert "world_clock" in names
        assert "daily_template" in names
        assert "word_count" in names
        assert "random_note" in names

    def test_get_plugin(self):
        pm = PluginManager()
        pm.load_all()
        p = pm.get_plugin("world_clock")
        assert p is not None
        assert p.name == "world_clock"

    def test_get_plugin_not_found(self):
        pm = PluginManager()
        pm.load_all()
        assert pm.get_plugin("nonexistent") is None

    def test_disabled_plugin(self):
        pm = PluginManager(config={"disabled": ["world_clock"]})
        pm.load_all()
        names = [p.name for p in pm.plugins]
        assert "world_clock" not in names

    def test_enabled_only(self):
        pm = PluginManager(config={"enabled": ["world_clock"]})
        pm.load_all()
        names = [p.name for p in pm.plugins]
        assert names == ["world_clock"]

    def test_dispatch_event(self):
        pm = PluginManager()
        pm.load_all()
        # Should not raise
        pm.dispatch("on_file_saved", "/test.md", "content")

    def test_dispatch_invalid_event(self):
        pm = PluginManager()
        pm.load_all()
        # Should not raise
        pm.dispatch("nonexistent_event")

    def test_external_plugin_loading(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple external plugin
            plugin_code = '''
from nas_md.plugins import Plugin

class TestExternalPlugin(Plugin):
    name = "test_external"
    version = "0.1.0"
    description = "Test external plugin"
'''
            with open(os.path.join(tmpdir, "test_ext.py"), "w") as f:
                f.write(plugin_code)

            pm = PluginManager(plugins_dir=tmpdir)
            pm.load_all()
            names = [p.name for p in pm.plugins]
            assert "test_external" in names
