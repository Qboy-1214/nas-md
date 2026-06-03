"""Habits HTML renderer - renders habits view as HTML."""

from __future__ import annotations


from nas_md.config import server_cfg
from nas_md.habits import (
    last_week_habits,
    MOOD_HABIT,
    MOOD_EMOJIS,
    emoji_for_habit,
)
from nas_md.userconfig import UserConfig
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nas_md.fs import FS


def render(user_fs: FS, user_id: int) -> str:
    """Render the habits view as HTML string."""
    user_config = UserConfig(user_fs, user_id, server_cfg.config_filename)
    tz_str = user_config.timezone()
    try:
        tz_offset = int(tz_str)
    except (ValueError, TypeError):
        tz_offset = 0

    habits_data, _ = last_week_habits(user_fs, tz_offset)
    if not habits_data:
        return "<p>No habits yet.</p>"

    moods = habits_data.pop(MOOD_HABIT, None)

    # Build habit keys: non-mood habits sorted, then mood last
    habit_keys = sorted(k for k in habits_data if k != MOOD_HABIT)
    if moods:
        habit_keys.append(MOOD_HABIT)

    # Get current day of year (1-based, matching Go)
    import datetime

    current_day = datetime.datetime.utcnow().timetuple().tm_yday

    # Build HTML
    parts = ['<div class="habits">']

    # Render non-mood habits
    for name in habit_keys:
        if name == MOOD_HABIT:
            continue
        days = habits_data.get(name, {})
        streak = sum(1 for d in days.values() if d == 1)
        total = len(days)
        pct = int((streak / max(total, 1)) * 100)
        em = emoji_for_habit(user_fs, name)
        parts.append('<div class="habit">')
        parts.append(f'  <span class="habit-name">{em} {name}</span>')
        parts.append(f'  <span class="habit-streak">{streak}/7 ({pct}%)</span>')
        parts.append("</div>")

    # Render mood habit
    if moods:
        parts.append('<div class="moods">')
        parts.append("  <h3>Mood</h3>")
        for day_num, power in sorted(moods.items()):
            if 0 <= power < len(MOOD_EMOJIS):
                mood_emoji = MOOD_EMOJIS[power]
                is_today = " today" if day_num == current_day else ""
                parts.append(
                    f'  <span class="mood-day{is_today}" data-day="{day_num}">{mood_emoji}</span>'
                )
        parts.append("</div>")

    parts.append("</div>")
    return "\n".join(parts)
