"""Journal module - daily record keeping."""

from __future__ import annotations

import re
import time
from threading import Lock

from nas_md.fs import FS, DIR_JOURNAL, DIR_USER_ROOT
from nas_md.pkg.txt.str import norm_new_lines
from nas_md.pkg.txt.tgtxt import has_image, IMG_PATTERN

_now = time.time
_user_locks: dict[str, Lock] = {}
_global_lock = Lock()


def add_record(user_fs: FS, record: str, timezone_offset: int = 0) -> None:
    """Add a record for the current day. Creates file if none exists for the month."""
    key, _ = user_fs.safe_path(DIR_USER_ROOT, "")
    lock = _user_lock(key)
    lock.acquire()
    try:
        record = record.strip()
        journal_filename = _today_journal_filename(timezone_offset)
        exists, _ = user_fs.exists(DIR_JOURNAL, journal_filename)

        md = ""
        if exists:
            md, _ = user_fs.read(DIR_JOURNAL, journal_filename)
            md = norm_new_lines(md)
            md = md.strip()
            if md:
                md += "\n"

        today_header = _today_header(timezone_offset)
        if today_header not in md:
            md += today_header + "\n"

        tz = _tz_from_offset(timezone_offset)
        timestamp = time.strftime("`%H:%M`", time.gmtime(_now() + timezone_offset))

        if has_image(record):
            img_match = re.search(IMG_PATTERN, record)
            if img_match:
                img_link = img_match.group()
                record = record.replace(img_link, "", 1).strip()
                record = f"{img_link}\n{timestamp} {record}\n"
        else:
            record = f"{timestamp} {record}\n"

        md += record
        user_fs.write(DIR_JOURNAL, journal_filename, md)
    finally:
        lock.release()


def add_emoji(user_fs: FS, emoji: str, timezone_offset: int = 0) -> None:
    """Add an emoji to the current day's record."""
    if not emoji:
        return

    key, _ = user_fs.safe_path(DIR_USER_ROOT, "")
    lock = _user_lock(key)
    lock.acquire()
    try:
        journal_filename = _today_journal_filename(timezone_offset)
        exists, _ = user_fs.exists(DIR_JOURNAL, journal_filename)

        if not exists:
            md = f"{_today_header(timezone_offset)} {emoji}"
            user_fs.write(DIR_JOURNAL, journal_filename, md)
            return

        md, _ = user_fs.read(DIR_JOURNAL, journal_filename)
        md = norm_new_lines(md)
        md = md.strip()

        today_h = _today_header(timezone_offset)
        pattern = re.compile(f"({re.escape(today_h)}) *(.*)")
        if pattern.search(md):
            if emoji in ("⚪️", "🤕", "😔", "😐", "🙂", "😊"):
                replacement = f"\\1 {emoji}\\2"
            else:
                replacement = f"\\1 \\2{emoji}"
            md = pattern.sub(replacement, md)
        else:
            md += f"\n{today_h} {emoji}"

        user_fs.write(DIR_JOURNAL, journal_filename, md)
    finally:
        lock.release()


def _today_journal_filename(timezone_offset: int = 0) -> str:
    return time.strftime("%Y.%m %B.md", time.gmtime(_now() + timezone_offset))


def _today_header(timezone_offset: int = 0) -> str:
    t = time.gmtime(_now() + timezone_offset)
    day = t.tm_mday
    month = time.strftime("%B", t)
    weekday = time.strftime("%A", t)
    return f"## {day} {month}, {weekday}"


def _tz_from_offset(offset: int):
    return None  # Simplified - Python's time doesn't have *time.Location


def _user_lock(root_path: str) -> Lock:
    with _global_lock:
        if root_path not in _user_locks:
            _user_locks[root_path] = Lock()
        return _user_locks[root_path]
