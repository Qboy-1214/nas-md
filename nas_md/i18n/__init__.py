"""Internationalization - emoji keyword mapping."""

from __future__ import annotations

import json
import os

_emojis_by_keyword: dict[str, str] = {}
_loaded = False


def load_emoji_file(filepath: str = "") -> None:
    """Load emoji mappings from JSON file."""
    global _loaded, _emojis_by_keyword
    if not filepath:
        # Look for emojis.json in the same directory as this module
        dir_path = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(dir_path, "emojis.json")

    try:
        with open(filepath, encoding="utf-8") as f:
            emojis = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _emojis_by_keyword = {}
        _loaded = True
        return

    _emojis_by_keyword = {}
    for emoji, keywords in emojis.items():
        for keyword in keywords:
            _emojis_by_keyword[keyword] = emoji
    _loaded = True


def add_emoji(s: str) -> str:
    """Add auto emoji to a string based on keywords."""
    e = emoji(s)
    if not e:
        return s
    return f"{e} {s}"


def emoji(s: str) -> str:
    """Find emoji for a string based on keyword matching."""
    global _loaded
    if not _loaded:
        load_emoji_file()

    s_lower = s.lower()
    aliases = [s_lower, s_lower + "s", s_lower.rstrip("s")]
    for alias in aliases:
        icon = _emojis_by_keyword.get(alias)
        if icon:
            return icon

    for word in s_lower.split():
        icon = _emojis_by_keyword.get(word)
        if icon:
            return icon

    return ""
