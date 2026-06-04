"""Plugin system - base class, loader, and built-in plugins."""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# ── Plugin Base Class ────────────────────────────────────────────────


class Plugin:
    """Base class for all plugins.

    Subclass this and override the hooks you need.
    """

    name: str = "unnamed"
    version: str = "0.1.0"
    description: str = ""

    def on_file_saved(self, path: str, content: str) -> None:
        """Called after a file is saved."""

    def on_file_deleted(self, path: str) -> None:
        """Called after a file is deleted."""

    def on_file_created(self, path: str, content: str) -> None:
        """Called after a new file is created."""

    def register_routes(self, server: Any) -> list[dict]:
        """Register custom HTTP routes. Returns list of route specs."""
        return []

    def register_commands(self, server: Any) -> list[dict]:
        """Register bot commands. Returns list of command specs."""
        return []

    def on_index_updated(self, path: str) -> None:
        """Called after search index is updated for a file."""


# ── Plugin Manager ───────────────────────────────────────────────────


class PluginManager:
    """Manages plugin lifecycle: discovery, loading, and event dispatch."""

    def __init__(self, plugins_dir: str | None = None, config: dict | None = None):
        self._plugins: list[Plugin] = []
        self._plugins_dir = plugins_dir
        self._config = config or {}
        self._enabled: set[str] = set(self._config.get("enabled", []))
        self._disabled: set[str] = set(self._config.get("disabled", []))

    @property
    def plugins(self) -> list[Plugin]:
        return list(self._plugins)

    def load_all(self) -> None:
        """Load all discovered plugins."""
        self._load_builtin_plugins()
        if self._plugins_dir and os.path.isdir(self._plugins_dir):
            self._load_external_plugins()

    def _load_builtin_plugins(self) -> None:
        """Load built-in plugins."""
        builtins = [WorldClockPlugin, DailyTemplatePlugin, WordCountPlugin, RandomNotePlugin]
        for cls in builtins:
            if self._is_enabled(cls.name if hasattr(cls, "name") else cls.__name__):
                try:
                    plugin = cls()
                    self._plugins.append(plugin)
                    logger.info("Loaded built-in plugin: %s v%s", plugin.name, plugin.version)
                except Exception as e:
                    logger.error("Failed to load built-in plugin %s: %s", cls.__name__, e)

    def _load_external_plugins(self) -> None:
        """Load plugins from the plugins directory."""
        for fname in os.listdir(self._plugins_dir):
            if not fname.endswith(".py") or fname.startswith("_"):
                continue
            module_name = fname[:-3]
            filepath = os.path.join(self._plugins_dir, fname)
            try:
                spec = importlib.util.spec_from_file_location(f"nas_md.plugins.ext.{module_name}", filepath)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    # Find Plugin subclasses in the module
                    for attr_name in dir(mod):
                        attr = getattr(mod, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, Plugin)
                            and attr is not Plugin
                        ):
                            if self._is_enabled(attr.name if hasattr(attr, "name") else attr.__name__):
                                plugin = attr()
                                self._plugins.append(plugin)
                                logger.info("Loaded external plugin: %s v%s", plugin.name, plugin.version)
            except Exception as e:
                logger.error("Failed to load external plugin %s: %s", fname, e)

    def _is_enabled(self, name: str) -> bool:
        """Check if a plugin is enabled."""
        if name in self._disabled:
            return False
        if self._enabled and name not in self._enabled:
            return False
        return True

    def dispatch(self, event: str, *args, **kwargs) -> None:
        """Dispatch an event to all loaded plugins."""
        for plugin in self._plugins:
            handler = getattr(plugin, event, None)
            if handler:
                try:
                    handler(*args, **kwargs)
                except Exception as e:
                    logger.error("Plugin %s error in %s: %s", plugin.name, event, e)

    def get_plugin(self, name: str) -> Plugin | None:
        """Get a plugin by name."""
        for plugin in self._plugins:
            if plugin.name == name:
                return plugin
        return None


# ── Built-in Plugins ─────────────────────────────────────────────────


TIME_FORMAT = "%d.%m.%Y %H:%M:%S"
DATE_FORMAT = "%d.%m.%Y"

LOCATION_NAMES = ["UTC", "MSK", "CY", "ME"]
LOCATIONS = {
    "UTC": "UTC",
    "CY": "Asia/Nicosia",
    "ME": "Europe/Podgorica",
    "BG": "Europe/Belgrade",
    "MSK": "Europe/Moscow",
}
LOCATION_ICONS = {
    "UTC": "🕰",
    "CY": "🏝",
    "ME": "⛰",
    "BG": "☕️",
    "MSK": "🔺",
}


class WorldClockPlugin(Plugin):
    """Plugin that converts dates/timestamps to multiple timezones."""

    name = "world_clock"
    version = "1.0.0"
    description = "Convert dates/timestamps to multiple timezones"

    def can_handle(self, msg_text: str) -> bool:
        return (
            self.parse_date(msg_text) is not None
            or self.parse_time(msg_text) is not None
            or self.parse_timestamp(msg_text) is not None
        )

    def handle(self, msg_text: str) -> tuple[str | None, None]:
        t = self.parse_date(msg_text)
        if t is not None:
            return self._build_message(t, self._fmt_timestamp), None

        t = self.parse_time(msg_text)
        if t is not None:
            return self._build_message(t, self._fmt_timestamp), None

        t = self.parse_timestamp(msg_text)
        if t is not None:
            return self._build_message(t, self._fmt_time), None

        return "", None

    def parse_timestamp(self, message: str) -> float | None:
        try:
            ts = int(message)
        except (ValueError, TypeError):
            return None
        if ts <= 999999:
            return None
        if ts > 9999999999999:
            return ts / 1000000  # microseconds
        elif ts > 9999999999:
            return ts / 1000  # milliseconds
        return float(ts)  # seconds

    def parse_time(self, message: str) -> float | None:
        try:
            t = time.strptime(message.strip(), TIME_FORMAT)
            return time.mktime(t)
        except (ValueError, TypeError):
            return None

    def parse_date(self, message: str) -> float | None:
        try:
            t = time.strptime(message.strip(), DATE_FORMAT)
            return time.mktime(t)
        except (ValueError, TypeError):
            return None

    def _build_message(self, t: float, formatter) -> str:
        parts = []
        for loc_name in LOCATION_NAMES:
            try:
                offset = time.timezone if time.localtime(t).tm_isdst == 0 else time.altzone
                local_t = t - offset
                formatted = formatter(local_t)
                parts.append(f"{LOCATION_ICONS[loc_name]} {formatted} {loc_name}")
            except Exception:
                pass
        return "\n".join(parts)

    def _fmt_time(self, t: float) -> str:
        return time.strftime(TIME_FORMAT, time.localtime(t))

    def _fmt_timestamp(self, t: float) -> str:
        return str(int(t))


class DailyTemplatePlugin(Plugin):
    """Auto-apply templates when creating daily journal entries."""

    name = "daily_template"
    version = "1.0.0"
    description = "Auto-apply templates for daily journal entries"

    DEFAULT_TEMPLATE = """# {date}

## Tasks
- [ ]

## Notes

"""

    def __init__(self):
        self._template = self.DEFAULT_TEMPLATE

    def set_template(self, template: str) -> None:
        self._template = template

    def on_file_created(self, path: str, content: str) -> None:
        """If the file is a daily journal entry and is empty, apply template."""
        if not content.strip() and self._is_journal_path(path):
            from datetime import date

            today = date.today().isoformat()
            template_content = self._template.replace("{date}", today)
            # Write template to file
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(template_content)
                logger.info("Applied daily template to %s", path)
            except OSError as e:
                logger.error("Failed to apply template: %s", e)

    def _is_journal_path(self, path: str) -> bool:
        """Check if path looks like a daily journal entry."""
        import re

        basename = os.path.basename(path)
        return bool(re.match(r"\d{4}-\d{2}-\d{2}", basename))


class WordCountPlugin(Plugin):
    """Count words in markdown files."""

    name = "word_count"
    version = "1.0.0"
    description = "Word count statistics for markdown files"

    def on_file_saved(self, path: str, content: str) -> None:
        if path.endswith(".md"):
            stats = self.count(content)
            logger.info(
                "Word count for %s: %d words, %d chars, %d lines",
                path,
                stats["words"],
                stats["chars"],
                stats["lines"],
            )

    @staticmethod
    def count(content: str) -> dict:
        """Count words, characters, and lines in content."""
        lines = content.split("\n")
        # Remove markdown syntax for word count
        text = content
        import re

        text = re.sub(r"```[\s\S]*?```", "", text)  # code blocks
        text = re.sub(r"`[^`]+`", "", text)  # inline code
        text = re.sub(r"#+ ", "", text)  # headers
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links
        text = re.sub(r"!?\[([^\]]*)\]\([^)]+\)", r"\1", text)  # images
        text = re.sub(r"[*_~]+", "", text)  # emphasis

        words = len(text.split())
        chars = len(content)
        line_count = len(lines)

        return {"words": words, "chars": chars, "lines": line_count}


class RandomNotePlugin(Plugin):
    """Randomly suggest a note for review."""

    name = "random_note"
    version = "1.0.0"
    description = "Randomly suggest a note for review"

    def get_random_note(self, storage_dir: str) -> str | None:
        """Get a random markdown file path from storage."""
        import random

        md_files = []
        for root, dirs, files in os.walk(storage_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if f.endswith(".md") and not f.startswith("."):
                    md_files.append(os.path.join(root, f))
        if not md_files:
            return None
        return random.choice(md_files)
