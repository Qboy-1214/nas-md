"""Command router - decorator-based command registration for the Telegram bot."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Global command registry
_registry: dict[str, Callable] = {}


def command(name: str):
    """Decorator to register a command handler.

    Usage:
        @command("search")
        def handle_search(server, upd, cmd):
            ...
    """

    def decorator(func: Callable) -> Callable:
        _registry[name] = func
        return func

    return decorator


def get_handler(name: str) -> Callable | None:
    """Get a registered command handler by name."""
    return _registry.get(name)


def all_commands() -> dict[str, Callable]:
    """Return the full command registry."""
    return dict(_registry)


def register_module(module_name: str) -> int:
    """Import a command module to register its handlers.

    Returns the number of commands registered.
    """
    before = len(_registry)
    try:
        import importlib
        import sys

        full_name = f"nas_md.server.commands.{module_name}"
        # Force reload to re-trigger decorators
        if full_name in sys.modules:
            del sys.modules[full_name]
        mod = importlib.import_module(full_name)
        _ = mod
    except (ImportError, AttributeError) as e:
        logger.error("Failed to import command module %s: %s", module_name, e)
    return len(_registry) - before


def register_all_modules() -> int:
    """Register all built-in command modules."""
    modules = ["note", "task", "search", "habit", "settings"]
    total = 0
    for mod in modules:
        total += register_module(mod)
    logger.info("Registered %d commands from %d modules", total, len(modules))
    return total
