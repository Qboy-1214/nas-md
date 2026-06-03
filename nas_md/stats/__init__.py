"""Stats module - generate reports about completed tasks."""

from __future__ import annotations

import time

from nas_md.fs import FS, DIR_ARCHIVE, display_name, is_checklist_item

_now = time.time


def today_report(user_fs: FS, user_id: int) -> tuple[str, None]:
    """Generate today's completion report."""
    files, err = done_today(user_fs, user_id)
    if err:
        return "", err

    stats = []
    for f in files:
        stats.append(f"{_emoji(f)} <b>{display_name(f)}</b>")

    archived_files, err = user_fs.files_and_dirs(DIR_ARCHIVE)
    if err:
        return "", err
    done_total = len(archived_files)
    stats.append(f"\n📊 {done_total} tasks done in total")

    return "\n".join(stats), None


def _emoji(filename: str) -> str:
    if is_checklist_item(filename):
        return "☑️"
    return "✅"


def done_today(user_fs: FS, user_id: int) -> tuple[list[str], None]:
    """Return list of files completed today."""
    files, err = user_fs.files_and_dirs(DIR_ARCHIVE)
    if err:
        return [], err

    today_start = _beginning_of_day()
    today_files = [f for f in files if f.ctime > today_start]
    return [f.display_name for f in today_files], None


def _beginning_of_day() -> int:
    t = time.gmtime(_now())
    # Return milliseconds to match File.ctime
    return (
        int(time.mktime(time.struct_time((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, 0))))
        * 1000
    )
