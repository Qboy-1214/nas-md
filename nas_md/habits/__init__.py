"""Habits module - habit tracking with yearly emoji grids."""

from __future__ import annotations

import time

from nas_md.fs import FS, DIR_HABITS, DIR_INSIGHTS, MD_EXT, display_name
from nas_md.pkg.txt.str import first_word, ucfirst

Year = dict[int, int]  # day_of_year -> status (0=skipped, 1=completed)

HABIT_SKIPPED = "⚪️"
HABIT_COMPLETED = "🟢"
HABIT_COMPLETED_AT_WEEKEND = "🟡"
MOOD_HABIT = "Mood"
MOOD_EMOJIS = ["⚪️", "🤕", "😔", "😐", "🙂", "😊"]

_now = time.time


def habits(user_fs: FS, year: int) -> tuple[dict[str, Year], None]:
    """Return Habit name => {day_of_year => status}."""
    existing_habits, err = user_fs.files_and_dirs(DIR_HABITS)
    if err:
        return {}, err

    result: dict[str, Year] = {}
    for h in existing_habits:
        result[display_name(h.name)] = {}

    filename = f"{year} Habits.md"
    insights_exist, _ = user_fs.exists(DIR_INSIGHTS, filename)
    if not insights_exist:
        return result, None

    content, err = user_fs.read(DIR_INSIGHTS, filename)
    if err:
        return {}, err

    month = 1  # January
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue

        if line.startswith("###"):
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            try:
                month = time.strptime(first_word(parts[1]), "%B").tm_mon
            except ValueError:
                continue
            continue

        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        days_str, habit = parts

        first_day = time.struct_time((year, month, 1, 0, 0, 0, 0, 0, 0))
        day_of_year = first_day.tm_yday + 1  # Go's YearDay is 1-based

        if MOOD_HABIT in habit:
            if MOOD_HABIT not in result:
                result[MOOD_HABIT] = {}
            for ch in _grapheme_clusters(days_str):
                power = _emoji_index(ch, MOOD_EMOJIS)
                result[MOOD_HABIT][day_of_year] = power
                day_of_year += 1
            continue

        marker = HABIT_SKIPPED + HABIT_COMPLETED_AT_WEEKEND + HABIT_COMPLETED
        if not any(c in marker for c in days_str):
            continue

        habit_name = habit.strip()
        if habit_name not in result:
            result[habit_name] = {}

        for ch in _grapheme_clusters(days_str):
            result[habit_name][day_of_year] = 0 if ch == HABIT_SKIPPED else 1
            day_of_year += 1

    return result, None


def last_week_habits(user_fs: FS, tz_offset: int = 0) -> tuple[dict[str, Year], None]:
    """Return habits for the last week."""
    year = time.gmtime(_now() + tz_offset).tm_year
    habits_for_year, err = habits(user_fs, year)
    if err:
        return {}, err

    # Find Monday of current week
    t = time.gmtime(_now() + tz_offset)
    days_since_monday = t.tm_wday
    monday = t.tm_yday - days_since_monday

    existing_habits, err = user_fs.files_and_dirs(DIR_HABITS)
    if err:
        return {}, err
    existing_habits.append(type("F", (), {"name": MOOD_HABIT})())

    result: dict[str, Year] = {}
    for h in existing_habits:
        name = h.name
        if name.endswith(MD_EXT):
            name = name[:-3]
        result[name] = {}
        for offset in range(7):
            yd = monday + offset
            result[name][yd] = 0
            if name in habits_for_year and yd in habits_for_year[name]:
                result[name][yd] = habits_for_year[name][yd]

    return result, None


def write(user_fs: FS, year: int, habits_data: dict[str, Year]) -> None:
    """Write habits to file."""
    habit_keys = sorted(k for k in habits_data if k != MOOD_HABIT)
    if MOOD_HABIT in habits_data:
        habit_keys.append(MOOD_HABIT)

    content = ""
    day = time.struct_time((year, 1, 1, 0, 0, 0, 0, 0, 0))
    while day.tm_year < year + 1:
        month = day.tm_mon
        habits_for_month = ""
        for habit_name in habit_keys:
            statuses = ""
            day_of_month = day
            at_least_one = False
            while day_of_month.tm_mon == month:
                yd = day_of_month.tm_yday
                emoji = HABIT_SKIPPED
                if habit_name in habits_data and yd in habits_data[habit_name]:
                    emoji = _emoji_for_status(habit_name, day_of_month, habits_data[habit_name][yd])
                if emoji != HABIT_SKIPPED:
                    at_least_one = True
                statuses += emoji
                # Next day
                next_t = time.gmtime(time.mktime(day_of_month) + 86400)
                day_of_month = next_t
            if at_least_one:
                habits_for_month += f"{statuses} {habit_name}\n"

        if habits_for_month:
            if content:
                content += "\n"
            content += f"### {time.strftime('%B', day)}\n{habits_for_month}"

        # Next month
        if month == 12:
            day = time.struct_time((year + 1, 1, 1, 0, 0, 0, 0, 0, 0))
        else:
            day = time.struct_time((year, month + 1, 1, 0, 0, 0, 0, 0, 0))

    filename = f"{year} Habits.md"
    user_fs.write(DIR_INSIGHTS, filename, content)


def emoji_for_habit(user_fs: FS, habit_name: str) -> str:
    """Get emoji for a habit."""
    content, _ = user_fs.read(DIR_HABITS, ucfirst(habit_name) + MD_EXT)
    if content:
        return content.strip()
    return "⚡️"


def _emoji_for_status(habit_name: str, day: time.struct_time, status: int) -> str:
    if habit_name == MOOD_HABIT:
        if status < len(MOOD_EMOJIS):
            return MOOD_EMOJIS[status]
        return HABIT_SKIPPED
    if status == 1:
        if day.tm_wday in (5, 6):  # Saturday, Sunday
            return HABIT_COMPLETED_AT_WEEKEND
        return HABIT_COMPLETED
    return HABIT_SKIPPED


def _emoji_index(ch: str, emojis: list[str]) -> int:
    try:
        return emojis.index(ch)
    except ValueError:
        return 0


def _grapheme_clusters(s: str) -> list[str]:
    """Split string into grapheme clusters (simplified)."""
    if not s:
        return []
    clusters = []
    i = 0
    while i < len(s):
        ch = s[i]
        # Check for variation selectors and ZWJ sequences
        j = i + 1
        while j < len(s) and (0xFE00 <= ord(s[j]) <= 0xFE0F or s[j] == "\u200d"):
            if s[j] == "\u200d" and j + 1 < len(s):
                ch += s[j] + s[j + 1]
                j += 2
            else:
                ch += s[j]
                j += 1
        clusters.append(ch)
        i = j
    return clusters
