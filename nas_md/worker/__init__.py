"""Worker module - scheduled task execution."""

from __future__ import annotations

import os
import re
import time

from nas_md.config import server_cfg
from nas_md.fs import (
    DIR_USER_ROOT,
    DIR_ARCHIVE,
    CHAT_FILENAME,
    LATER_FILENAME,
    DONE_FILENAME,
    new_user_fs,
)
from nas_md.journal import add_record
from nas_md.pkg.txt.md import (
    checklist_items,
    remove_completed_checklist_items,
    add_header_and_text,
    strip_chat_timestamp,
)
from nas_md.userconfig import UserConfig

_now = time.time


def _get_tz():
    """Get timezone from config, defaults to UTC."""
    import datetime

    tz_name = server_cfg.tz or "UTC"
    try:
        return datetime.ZoneInfo(tz_name)
    except (KeyError, Exception):
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo(tz_name)
        except Exception:
            return datetime.UTC


def beginning_of_the_day(t: float) -> float:
    """Return the beginning of the day for a given timestamp."""
    import datetime

    dt = datetime.datetime.fromtimestamp(t, tz=_get_tz())
    beginning = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return beginning.timestamp()


def tomorrow() -> int:
    """Return tomorrow's beginning of day as unix timestamp."""
    import datetime

    t = datetime.datetime.now(_get_tz()) + datetime.timedelta(days=1)
    beginning = t.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(beginning.timestamp())


def format_task_date(scheduled_at: int) -> str:
    """Format a scheduled date for display."""
    import datetime

    tz = _get_tz()
    today = datetime.datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    task_date = datetime.datetime.fromtimestamp(scheduled_at, tz=tz).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    diff_days = (task_date - today).days

    if diff_days == 0:
        return "Today"
    elif diff_days == 1:
        return "Tomorrow"
    elif 1 < diff_days <= 6:
        return task_date.strftime("%A %d")
    elif 7 <= diff_days <= 13:
        return "Next " + task_date.strftime("%A %d")
    else:
        return task_date.strftime("%d %B, %A")


def schedule_report(schedules: list) -> str:
    """Format scheduled tasks into a report."""
    from collections import OrderedDict

    schedule = OrderedDict()
    order = []

    for s in schedules:
        day = format_task_date(s.get("scheduledAt", 0))
        filename = s.get("filename", "")
        if day not in schedule:
            order.append(day)
            schedule[day] = []
        schedule[day].append(filename)

    parts = []
    for day in order:
        parts.append(f"<b>{day}</b>")
        for task in schedule[day]:
            parts.append(f"- {task}")
        parts.append("")

    return "\n".join(parts).strip()


def move_due_tasks(storage_path: str, config_filename: str, tg) -> None:
    """Move due scheduled tasks into user inboxes."""
    root_fs = new_user_fs(storage_path)
    user_dirs, _ = root_fs.files_and_dirs(DIR_USER_ROOT)

    for user_dir in user_dirs:
        try:
            user_id = int(user_dir.name)
        except (ValueError, TypeError):
            continue

        user_path = os.path.join(storage_path, str(user_id))
        user_fs = new_user_fs(user_path)
        user_config = UserConfig(user_fs, user_id, config_filename)
        schedules = user_config.schedules()

        for sched in schedules:
            scheduled_at = sched.get("scheduledAt", 0)
            seconds_left = scheduled_at - int(_now())
            if seconds_left > 0:
                continue

            filename = sched.get("filename", "")
            cron = sched.get("cron", "")

            # Move task to inbox (Chat.md)
            chat_content, _ = user_fs.read(DIR_USER_ROOT, CHAT_FILENAME)
            chat_content = chat_content or ""
            if chat_content:
                chat_content += "\n"
            chat_content += f"- [ ] {filename}"
            user_fs.write(DIR_USER_ROOT, CHAT_FILENAME, chat_content)

            # Remove from Done.md if present
            done_content, _ = user_fs.read(DIR_ARCHIVE, DONE_FILENAME)
            if done_content:
                # Simple removal of the filename from done
                done_lines = done_content.split("\n")
                done_lines = [ln for ln in done_lines if filename not in ln]
                user_fs.write(DIR_ARCHIVE, DONE_FILENAME, "\n".join(done_lines))

            # Remove from Later.md if present
            later_content, _ = user_fs.read(DIR_USER_ROOT, LATER_FILENAME)
            if later_content:
                later_lines = later_content.split("\n")
                later_lines = [ln for ln in later_lines if filename not in ln]
                user_fs.write(DIR_USER_ROOT, LATER_FILENAME, "\n".join(later_lines))

            if cron:
                # Reschedule for next occurrence
                next_time = int(_now()) + 86400  # Simplified: next day
                user_config.add_to_schedule(filename, next_time, cron)
            else:
                user_config.del_from_schedule(filename)


def worker_remove_completed_checklist_items(storage_path: str, config_filename: str) -> None:
    """Remove completed checklist items from Chat.md and Later.md, archive to Done.md."""
    import datetime

    root_fs = new_user_fs(storage_path)
    user_dirs, _ = root_fs.files_and_dirs(DIR_USER_ROOT)

    for user_dir in user_dirs:
        try:
            user_id = int(user_dir.name)
        except (ValueError, TypeError):
            continue

        user_path = os.path.join(storage_path, str(user_id))
        user_fs = new_user_fs(user_path)
        # Ensure user config exists
        _ = UserConfig(user_fs, user_id, config_filename)

        # Process Chat.md and Later.md
        for filename in [CHAT_FILENAME, LATER_FILENAME]:
            content, _ = user_fs.read(DIR_USER_ROOT, filename)
            if not content:
                continue

            reduced, removed = _remove_completed_items(content)
            if not removed:
                continue

            user_fs.write(DIR_USER_ROOT, filename, reduced)

            # Archive to Done.md
            done_content, _ = user_fs.read(DIR_ARCHIVE, DONE_FILENAME)
            done_content = done_content or ""
            today = datetime.datetime.now(_get_tz())
            header = f"#### {today.day} {today.strftime('%B')} {today.year}, {today.strftime('%A')}"
            done_content = add_header_and_text(done_content, header, removed)
            user_fs.write(DIR_ARCHIVE, DONE_FILENAME, done_content)

            # Add to journal
            items = checklist_items(removed)
            for item_text, _item_hash, _is_done in items:
                clean_text = strip_chat_timestamp(item_text)
                add_record(user_fs, f"✅ {clean_text}")


def _remove_completed_items(md: str) -> tuple:
    """Remove completed checklist items from markdown content.
    Returns (reduced_md, removed_items_md).
    """
    lines = md.split("\n")
    done_re = re.compile(r"^- \[[xX]\] ")

    kept = []
    removed_lines = []
    in_block = False
    block_lines = []
    is_done_block = False

    for line in lines:
        if done_re.match(line):
            # Start of a done block
            if block_lines and not is_done_block:
                kept.extend(block_lines)
            elif block_lines and is_done_block:
                removed_lines.extend(block_lines)
            block_lines = [line]
            is_done_block = True
            in_block = True
        elif line.startswith("- [ ] ") or line.startswith("- [x] "):
            # Start of a new item block
            if block_lines:
                if is_done_block:
                    removed_lines.extend(block_lines)
                else:
                    kept.extend(block_lines)
            block_lines = [line]
            is_done_block = False
            in_block = True
        elif in_block and line.strip() and not line.startswith("- ["):
            # Continuation of current block
            block_lines.append(line)
        else:
            # End of block or non-item line
            if block_lines:
                if is_done_block:
                    removed_lines.extend(block_lines)
                else:
                    kept.extend(block_lines)
                block_lines = []
                in_block = False
            kept.append(line)

    # Handle last block
    if block_lines:
        if is_done_block:
            removed_lines.extend(block_lines)
        else:
            kept.extend(block_lines)

    # Format removed items as checklist
    removed_md = "\n".join(removed_lines).strip()
    kept_md = "\n".join(kept).strip()

    return kept_md, removed_md


class Worker:
    """Handles scheduled tasks like moving scheduled items and cleaning up completed tasks."""

    def __init__(self, tg, get_user_fs) -> None:
        self.tg = tg
        self.get_user_fs = get_user_fs

    def run(self) -> None:
        """Run all scheduled tasks."""
        self._run_schedules()
        self._cleanup_done()

    def _run_schedules(self) -> None:
        """Process scheduled tasks for all users."""
        storage_path = server_cfg.storage_path
        config_filename = server_cfg.config_filename
        move_due_tasks(storage_path, config_filename, self.tg)

    def _cleanup_done(self) -> None:
        """Clean up old completed tasks."""
        import datetime

        # Only run near end of day (23:50+)
        now = datetime.datetime.now(_get_tz())
        if now.hour != 23 or now.minute < 50:
            return
        storage_path = server_cfg.storage_path
        config_filename = server_cfg.config_filename
        remove_completed_checklist_items(storage_path, config_filename)


def new_worker(tg, get_user_fs) -> Worker:
    return Worker(tg, get_user_fs)
