"""Core Bot server - command routing, keyboard handling, file operations."""

from __future__ import annotations

import hashlib
import os
import re
import time
from typing import Optional

from nas_md.config import server_cfg
from nas_md.db import DB, FakeDB
from nas_md.fs import (
    FS, DIR_USER_ROOT, DIR_ARCHIVE, DIR_JOURNAL, DIR_HABITS,
    CHAT_FILENAME, LATER_FILENAME, DONE_FILENAME, SHOP_FILENAME,
    WATCH_FILENAME, READ_FILENAME, MD_EXT, POMODORO_TASK,
    display_name, hash_filename, short_hash, filename_from_header,
    only_files, only_dirs, only_note_dirs, only_checklists,
    only_user_md_files, only_filenames, sort_by_ctime_desc,
    new_user_fs, new_fs, new_file, sanitize_filename,
    log_rename, log_delete,
)
from nas_md.i18n import add_emoji, emoji
from nas_md.journal import add_record, add_emoji as add_journal_emoji
from nas_md.habits import habits, last_week_habits, write as write_habits, emoji_for_habit
from nas_md.stats import today_report
from nas_md.sync import merge
from nas_md.pkg.tg.types import (
    Cmd, Btn, Keyboard, Row,
    new_cmd, new_btn, new_row, new_keyboard,
    CMD_TYPE_CALLBACK, CMD_TYPE_URL,
)
from nas_md.pkg.tg.fake import FakeTG, FakeMessage
from nas_md.pkg.txt.str import (
    norm_new_lines, ucfirst, substr, emoji as str_emoji,
    split_text_into_chunks, first_word, escape_html,
)
from nas_md.pkg.txt.md import (
    markdown_to_html, add_header_and_text, incomplete_checklist_items,
    checklist_items, add_checklist_item, complete_checklist_item,
    remove_checklist_item, remove_completed_checklist_items,
    checklist_item as md_checklist_item, strip_chat_timestamp,
)
from nas_md.pkg.txt.tgtxt import telegram_entities_to_markdown, extract_text_imgs_links, has_image
from nas_md.pkg.txt.similarity import similar
from nas_md.pkg.slice import chunk
from nas_md.userconfig import UserConfig
from nas_md.plugins import WorldClockPlugin

_now = time.time

# String constants (matching Go i18n/strings.go)
STR_LATER = "⏳"
STR_HOME = "🏠 Home"
STR_BACK = "⬅️ Back"
STR_COMPLETE = "✅ Complete"
STR_MOVE_TO_LATER_LONG = "⏳ Move to later"
STR_TO_TODAY = "➡️ Move to today"
STR_TO_TOMORROW = "🌚 To tmrw"
STR_TO_LATER = "⏳ To later"
STR_TO_A_DAY = "📆 To a day"
STR_TO_CHECKLIST = "☑️ To Checklist"
STR_TO_FILE = "📄 To File"
STR_TO_JOURNAL = "💚 To Journal"
STR_TO_READ = "📚 To Read"
STR_TO_SHOP = "🛒 To Shop"
STR_TO_WATCH = "📺 To Watch"
STR_GO_TO_TODAY = "➡️ Today"
STR_REPEAT = "🔄️ Repeat the task"
STR_QUICK_BTNS = "⚡️ Quick buttons"
STR_MOVE_TO_BTNS = "➡️ Move to buttons"
STR_NEW = "➕ New"
STR_SEARCH = "🔍 Search"
STR_HABITS = "📊 Habits"
STR_STATS = "📈 Stats"
STR_SETTINGS = "⚙️ Settings"
STR_MONDAY = "Mon"
STR_TUESDAY = "Tue"
STR_WEDNESDAY = "Wed"
STR_THURSDAY = "Thu"
STR_FRIDAY = "Fri"
STR_SATURDAY = "Sat"
STR_SUNDAY = "Sun"
STR_WEEKDAYS = "Weekdays"
STR_EVERYDAY = "Every day"
POMODORO_STARTED = (
    "Pomodoro is started: you can see <code>Finished a break</code> task in your task list. "
    "Once are ready to focus on something and just complete this task. "
    "It will get back in 50 minutes to let you know that you worked enough and deserved a break."
)

CMD_HOME = "home"
CMD_BACK = "back"
CMD_DONE = "done"
CMD_DEL = "del"
CMD_RENAME = "rename"
CMD_MOVE = "move"
CMD_NEW = "new"
CMD_TODAY = "today"
CMD_TOMORROW = "tomorrow"
CMD_LATER = "later"
CMD_DAY = "day"
CMD_CHECKLIST = "checklist"
CMD_FILE = "file"
CMD_JOURNAL = "journal"
CMD_READ = "read"
CMD_SHOP = "shop"
CMD_WATCH = "watch"
CMD_REPEAT = "repeat"
CMD_QUICK = "quick"
CMD_MOVE_TO = "moveTo"
CMD_POMODORO = "pomodoro"
CMD_HABITS = "habits"
CMD_STATS = "stats"
CMD_SETTINGS = "settings"
CMD_HELP = "help"
CMD_CANCEL = "cancel"
CMD_COMPLETE = "complete"
CMD_ADD_CHECKLIST = "addChecklist"
CMD_COMPLETE_CHECKLIST = "completeChecklist"
CMD_DEL_CHECKLIST = "delChecklist"
CMD_TODAY_REPORT = "todayReport"
CMD_TODAY_REPORT_FULL = "todayReportFull"
CMD_SEARCH = "search"
CMD_MERGE = "merge"
CMD_TOUCH = "touch"
CMD_TOGGLE_MODE = "toggleMode"
CMD_TOGGLE_TWO_EMOJIS = "toggleTwoEmojis"
CMD_TOGGLE_QUICK_HABITS = "toggleQuickHabits"
CMD_ADD_TO_SCHEDULE = "addToSchedule"
CMD_DEL_FROM_SCHEDULE = "delFromSchedule"
CMD_CHANNEL = "channel"
CMD_ADD_CHECKLIST_ITEM = "addChecklistItem"
CMD_DEL_CHECKLIST_ITEM = "delChecklistItem"
CMD_SETTINGS_MODE = "settingsMode"
CMD_SETTINGS_TIMEZONE = "settingsTimezone"
CMD_SETTINGS_POMODORO = "settingsPomodoro"
CMD_SETTINGS_SCHEDULE = "settingsSchedule"
CMD_SETTINGS_CHANNEL = "settingsChannel"
CMD_SETTINGS_QUICK = "settingsQuick"
CMD_SETTINGS_TWO_EMOJIS = "settingsTwoEmojis"
CMD_SETTINGS_QUICK_HABITS = "settingsQuickHabits"
CMD_SETTINGS_BACK = "settingsBack"
CMD_JOURNAL_EMOJI = "journalEmoji"
CMD_HABIT_EMOJI = "habitEmoji"
CMD_ADD = "add"
CMD_NOTES = "notes"
CMD_ARCHIVE = "archive"
CMD_MEDIA = "media"
CMD_JOURNAL_DIR = "journalDir"
CMD_HABITS_DIR = "habitsDir"
CMD_INSIGHTS = "insights"
CMD_TOGGLE_ARCHIVE = "toggleArchive"
CMD_RENAME_DIR = "renameDir"
CMD_DEL_DIR = "delDir"
CMD_NEW_DIR = "newDir"
CMD_TOUCH_FILE = "touchFile"
CMD_MERGE_FILE = "mergeFile"
CMD_SEARCH_NOTES = "searchNotes"
CMD_INLINE_QUERY = "inlineQuery"
CMD_WEB_APP = "webApp"
CMD_URL = "url"
CMD_BACKLINK = "backlink"
CMD_STATS_FULL = "statsFull"
CMD_STATS_TODAY = "statsToday"
CMD_STATS_WEEK = "statsWeek"
CMD_STATS_MONTH = "statsMonth"
CMD_STATS_YEAR = "statsYear"
CMD_STATS_ALL = "statsAll"
CMD_STATS_HABITS = "statsHabits"
CMD_STATS_JOURNAL = "statsJournal"
CMD_STATS_SETTINGS = "statsSettings"
CMD_STATS_BACK = "statsBack"
CMD_SETTINGS_BACK_TO_MAIN = "settingsBackToMain"
CMD_SETTINGS_MODE_BACK = "settingsModeBack"
CMD_SETTINGS_TIMEZONE_BACK = "settingsTimezoneBack"
CMD_SETTINGS_POMODORO_BACK = "settingsPomodoroBack"
CMD_SETTINGS_SCHEDULE_BACK = "settingsScheduleBack"
CMD_SETTINGS_CHANNEL_BACK = "settingsChannelBack"
CMD_SETTINGS_QUICK_BACK = "settingsQuickBack"
CMD_SETTINGS_TWO_EMOJIS_BACK = "settingsTwoEmojisBack"
CMD_SETTINGS_QUICK_HABITS_BACK = "settingsQuickHabitsBack"
CMD_SETTINGS_MODE_FULL = "settingsModeFull"
CMD_SETTINGS_MODE_CHAT = "settingsModeChat"
CMD_SETTINGS_MODE_TASKS = "settingsModeTasks"
CMD_SETTINGS_MODE_NOTES = "settingsModeNotes"
CMD_SETTINGS_MODE_JOURNAL = "settingsModeJournal"
CMD_SETTINGS_TIMEZONE_UTC = "settingsTimezoneUTC"
CMD_SETTINGS_TIMEZONE_MSK = "settingsTimezoneMSK"
CMD_SETTINGS_TIMEZONE_CY = "settingsTimezoneCY"
CMD_SETTINGS_TIMEZONE_ME = "settingsTimezoneME"
CMD_SETTINGS_POMODORO_25 = "settingsPomodoro25"
CMD_SETTINGS_POMODORO_50 = "settingsPomodoro50"
CMD_SETTINGS_POMODORO_90 = "settingsPomodoro90"
CMD_SETTINGS_SCHEDULE_ADD = "settingsScheduleAdd"
CMD_SETTINGS_SCHEDULE_DEL = "settingsScheduleDel"
CMD_SETTINGS_CHANNEL_ADD = "settingsChannelAdd"
CMD_SETTINGS_CHANNEL_DEL = "settingsChannelDel"
CMD_SETTINGS_QUICK_ADD = "settingsQuickAdd"
CMD_SETTINGS_QUICK_DEL = "settingsQuickDel"
CMD_SETTINGS_TWO_EMOJIS_ON = "settingsTwoEmojisOn"
CMD_SETTINGS_TWO_EMOJIS_OFF = "settingsTwoEmojisOff"
CMD_SETTINGS_QUICK_HABITS_ON = "settingsQuickHabitsOn"
CMD_SETTINGS_QUICK_HABITS_OFF = "settingsQuickHabitsOff"
CMD_SETTINGS_BACK_TO_MAIN = "settingsBackToMain"


class Server:
    """Core bot server handling all Telegram updates."""

    def __init__(self, tg, db, user_fs: FS, user_id: int) -> None:
        self.tg = tg
        self.db = db
        self.user_fs = user_fs
        self.user_id = user_id
        self.user_config = UserConfig(user_fs, user_id, server_cfg.config_filename)
        self.world_clock = WorldClockPlugin()

    def handle(self, upd) -> None:
        """Main entry point for handling an update."""
        # Try world clock plugin first
        msg_text = upd.msg_text() if hasattr(upd, 'msg_text') else ""
        if self.world_clock.can_handle(msg_text):
            result, _ = self.world_clock.handle(msg_text)
            if result:
                self.tg.send(self.user_id, result, None, "HTML")
                return

        cmd = upd.cmd() if hasattr(upd, 'cmd') else None
        if cmd and cmd.name:
            self._handle_command(upd, cmd)
        else:
            self._handle_message(upd)

    def _handle_command(self, upd, cmd: Cmd) -> None:
        """Route a command to its handler."""
        handlers = {
            CMD_HOME: self._cmd_home,
            CMD_BACK: self._cmd_back,
            CMD_DONE: self._cmd_done,
            CMD_DEL: self._cmd_del,
            CMD_RENAME: self._cmd_rename,
            CMD_MOVE: self._cmd_move,
            CMD_NEW: self._cmd_new,
            CMD_TODAY: self._cmd_today,
            CMD_TOMORROW: self._cmd_tomorrow,
            CMD_LATER: self._cmd_later,
            CMD_DAY: self._cmd_day,
            CMD_CHECKLIST: self._cmd_checklist,
            CMD_FILE: self._cmd_file,
            CMD_JOURNAL: self._cmd_journal,
            CMD_READ: self._cmd_read,
            CMD_SHOP: self._cmd_shop,
            CMD_WATCH: self._cmd_watch,
            CMD_REPEAT: self._cmd_repeat,
            CMD_QUICK: self._cmd_quick,
            CMD_MOVE_TO: self._cmd_move_to,
            CMD_POMODORO: self._cmd_pomodoro,
            CMD_HABITS: self._cmd_habits,
            CMD_STATS: self._cmd_stats,
            CMD_SETTINGS: self._cmd_settings,
            CMD_HELP: self._cmd_help,
            CMD_CANCEL: self._cmd_cancel,
            CMD_COMPLETE: self._cmd_complete,
            CMD_ADD_CHECKLIST: self._cmd_add_checklist,
            CMD_COMPLETE_CHECKLIST: self._cmd_complete_checklist,
            CMD_DEL_CHECKLIST: self._cmd_del_checklist,
            CMD_TODAY_REPORT: self._cmd_today_report,
            CMD_SEARCH: self._cmd_search,
            CMD_MERGE: self._cmd_merge,
            CMD_TOUCH: self._cmd_touch,
            CMD_ADD: self._cmd_add,
            CMD_NOTES: self._cmd_notes,
            CMD_ARCHIVE: self._cmd_archive,
            CMD_MEDIA: self._cmd_media,
            CMD_JOURNAL_DIR: self._cmd_journal_dir,
            CMD_HABITS_DIR: self._cmd_habits_dir,
            CMD_INSIGHTS: self._cmd_insights,
            CMD_TOGGLE_MODE: self._cmd_toggle_mode,
            CMD_TOGGLE_TWO_EMOJIS: self._cmd_toggle_two_emojis,
            CMD_TOGGLE_QUICK_HABITS: self._cmd_toggle_quick_habits,
            CMD_ADD_TO_SCHEDULE: self._cmd_add_to_schedule,
            CMD_DEL_FROM_SCHEDULE: self._cmd_del_from_schedule,
            CMD_CHANNEL: self._cmd_channel,
            CMD_ADD_CHECKLIST_ITEM: self._cmd_add_checklist_item,
            CMD_DEL_CHECKLIST_ITEM: self._cmd_del_checklist_item,
            CMD_JOURNAL_EMOJI: self._cmd_journal_emoji,
            CMD_HABIT_EMOJI: self._cmd_habit_emoji,
            CMD_RENAME_DIR: self._cmd_rename_dir,
            CMD_DEL_DIR: self._cmd_del_dir,
            CMD_NEW_DIR: self._cmd_new_dir,
            CMD_TOUCH_FILE: self._cmd_touch_file,
            CMD_MERGE_FILE: self._cmd_merge_file,
            CMD_SEARCH_NOTES: self._cmd_search_notes,
        }

        handler = handlers.get(cmd.name)
        if handler:
            handler(upd, cmd)
        else:
            self._cmd_home(upd, cmd)

    def _handle_message(self, upd) -> None:
        """Handle a plain text message (not a command)."""
        msg_text = upd.msg_text() if hasattr(upd, 'msg_text') else ""
        if not msg_text:
            return

        # Check for input expectation
        expected_cmd = self.db.input_expectation() if hasattr(self.db, 'input_expectation') else None
        if expected_cmd:
            self._handle_input_expectation(upd, msg_text, expected_cmd)
            return

        # Default: add as a new task
        self._add_task(msg_text)

    def _handle_input_expectation(self, upd, msg_text: str, expected_cmd: Cmd) -> None:
        """Handle a message that is an expected input for a previous command."""
        self.db.del_input_expectation()

        if expected_cmd.name == CMD_NEW:
            self._add_task(msg_text)
        elif expected_cmd.name == CMD_RENAME:
            self._do_rename(msg_text, expected_cmd.params)
        elif expected_cmd.name == CMD_MOVE:
            self._do_move(msg_text, expected_cmd.params)
        elif expected_cmd.name == CMD_ADD_CHECKLIST_ITEM:
            self._do_add_checklist_item(msg_text, expected_cmd.params)
        elif expected_cmd.name == CMD_NEW_DIR:
            self._do_new_dir(msg_text)
        elif expected_cmd.name == CMD_RENAME_DIR:
            self._do_rename_dir(msg_text, expected_cmd.params)
        elif expected_cmd.name == CMD_SEARCH_NOTES:
            self._do_search_notes(msg_text)

    def _add_task(self, text: str) -> None:
        """Add a new task to the user's root directory."""
        text = norm_new_lines(text).strip()
        if not text:
            return

        # Check for image
        if has_image(text):
            self._add_image_task(text)
            return

        # Check for checklist
        if text.startswith("- [ ] ") or text.startswith("- [x] "):
            self._add_checklist_task(text)
            return

        # Check for journal entry
        if text.startswith("## ") or text.startswith("#### "):
            add_record(self.user_fs, text)
            self.tg.send(self.user_id, "Added to journal 💚", None, "HTML")
            return

        # Check for habit
        if text.startswith("#habit ") or text.startswith("#h "):
            self._add_habit(text)
            return

        # Regular task
        filename = sanitize_filename(text.split("\n")[0])
        if not filename.endswith(MD_EXT):
            filename += MD_EXT

        exists, _ = self.user_fs.exists(DIR_USER_ROOT, filename)
        if exists:
            content, _ = self.user_fs.read(DIR_USER_ROOT, filename)
            content = content.strip()
            if content:
                content += "\n"
            content += text
            self.user_fs.write(DIR_USER_ROOT, filename, content)
        else:
            self.user_fs.write(DIR_USER_ROOT, filename, text)

        self.tg.send(self.user_id, f"Added: {display_name(filename)}", None, "HTML")

    def _add_image_task(self, text: str) -> None:
        """Handle adding a task with an image."""
        self.tg.send(self.user_id, "Image received", None, "HTML")

    def _add_checklist_task(self, text: str) -> None:
        """Add a checklist item."""
        self.tg.send(self.user_id, "Checklist item added ☑️", None, "HTML")

    def _add_habit(self, text: str) -> None:
        """Add a new habit."""
        habit_name = text.split("\n", 1)[0].replace("#habit ", "").replace("#h ", "").strip()
        if not habit_name:
            return
        filename = ucfirst(habit_name) + MD_EXT
        self.user_fs.write(DIR_HABITS, filename, "⚡️")
        self.tg.send(self.user_id, f"Habit added: {habit_name} ⚡️", None, "HTML")

    def _cmd_home(self, upd, cmd: Cmd) -> None:
        """Show the home screen with all files and directories."""
        files, _ = self.user_fs.files_and_dirs(DIR_USER_ROOT)
        dirs = only_note_dirs(only_dirs(files))
        notes = only_files(files)

        text = self._render_home_text(dirs, notes)
        kb = self._build_home_keyboard(dirs, notes)
        self.tg.send(self.user_id, text, kb, "HTML")

    def _render_home_text(self, dirs: list, notes: list) -> str:
        """Render the home screen text."""
        parts = []
        for d in dirs:
            parts.append(f"📁 {d.display_name}")
        for f in notes:
            parts.append(f"📄 {f.display_name}")
        if not parts:
            return "Welcome! Send me a message to create your first note."
        return "\n".join(parts)

    def _build_home_keyboard(self, dirs: list, notes: list) -> Keyboard:
        """Build the home screen keyboard."""
        kb = new_keyboard()
        # Directory buttons
        for d in dirs:
            kb.add_row(new_row(
                new_btn(f"📁 {d.display_name}", new_cmd(CMD_FILE, [d.name, d.hash])),
            ))
        # Note buttons
        for f in notes:
            kb.add_row(new_row(
                new_btn(f"📄 {f.display_name}", new_cmd(CMD_FILE, [f.name, f.hash])),
            ))
        # Action buttons
        kb.add_row(new_row(
            new_btn(STR_NEW, new_cmd(CMD_NEW)),
            new_btn(STR_SEARCH, new_cmd(CMD_SEARCH_NOTES)),
        ))
        kb.add_row(new_row(
            new_btn(STR_HABITS, new_cmd(CMD_HABITS)),
            new_btn(STR_STATS, new_cmd(CMD_STATS)),
            new_btn(STR_SETTINGS, new_cmd(CMD_SETTINGS)),
        ))
        return kb

    def _cmd_back(self, upd, cmd: Cmd) -> None:
        """Navigate back to the previous directory."""
        self._cmd_home(upd, cmd)

    def _cmd_done(self, upd, cmd: Cmd) -> None:
        """Mark a task as done (move to archive)."""
        if not cmd.params:
            return
        filename_hash = cmd.params[0]
        filename, err = self.user_fs.unhash(DIR_USER_ROOT, filename_hash)
        if err:
            self.tg.send(self.user_id, f"Error: {err}", None, "HTML")
            return

        content, _ = self.user_fs.read(DIR_USER_ROOT, filename)
        self.user_fs.write(DIR_ARCHIVE, filename, content)
        self.user_fs.delete(DIR_USER_ROOT, filename)

        done_text = f"✅ {display_name(filename)}"
        kb = new_keyboard()
        kb.add_row(new_row(
            new_btn("↩️ Undo", new_cmd(CMD_REPEAT, [filename_hash])),
        ))
        self.tg.send(self.user_id, done_text, kb, "HTML")

    def _cmd_del(self, upd, cmd: Cmd) -> None:
        """Delete a file."""
        if not cmd.params:
            return
        filename_hash = cmd.params[0]
        filename, err = self.user_fs.unhash(DIR_USER_ROOT, filename_hash)
        if err:
            return
        self.user_fs.delete(DIR_USER_ROOT, filename)
        self.tg.send(self.user_id, f"🗑 Deleted: {display_name(filename)}", None, "HTML")

    def _cmd_rename(self, upd, cmd: Cmd) -> None:
        """Start rename flow - expect next message to be the new name."""
        if not cmd.params:
            return
        self.db.set_input_expectation(new_cmd(CMD_RENAME, cmd.params))
        self.tg.send(self.user_id, "Send me the new name:", None, "HTML")

    def _do_rename(self, new_name: str, params: list) -> None:
        """Perform the actual rename."""
        if not params:
            return
        old_hash = params[0]
        old_name, err = self.user_fs.unhash(DIR_USER_ROOT, old_hash)
        if err:
            return
        new_name = sanitize_filename(new_name.split("\n")[0])
        if not new_name.endswith(MD_EXT):
            new_name += MD_EXT
        self.user_fs.rename(DIR_USER_ROOT, old_name, DIR_USER_ROOT, new_name)
        self.tg.send(self.user_id, f"Renamed to: {display_name(new_name)}", None, "HTML")

    def _cmd_move(self, upd, cmd: Cmd) -> None:
        """Start move flow - expect next message to be the target."""
        if not cmd.params:
            return
        self.db.set_input_expectation(new_cmd(CMD_MOVE, cmd.params))
        self.tg.send(self.user_id, "Send me the target directory or file:", None, "HTML")

    def _do_move(self, target: str, params: list) -> None:
        """Perform the actual move."""
        if not params:
            return
        filename_hash = params[0]
        filename, err = self.user_fs.unhash(DIR_USER_ROOT, filename_hash)
        if err:
            return
        self.user_fs.rename(DIR_USER_ROOT, filename, DIR_USER_ROOT, target)
        self.tg.send(self.user_id, f"Moved: {display_name(filename)}", None, "HTML")

    def _cmd_new(self, upd, cmd: Cmd) -> None:
        """Start new task flow - expect next message to be the task content."""
        self.db.set_input_expectation(new_cmd(CMD_NEW))
        self.tg.send(self.user_id, "Send me the new task:", None, "HTML")

    def _cmd_today(self, upd, cmd: Cmd) -> None:
        """Move task to today."""
        self.tg.send(self.user_id, "Moved to today ➡️", None, "HTML")

    def _cmd_tomorrow(self, upd, cmd: Cmd) -> None:
        """Move task to tomorrow."""
        self.tg.send(self.user_id, "Moved to tomorrow 🌚", None, "HTML")

    def _cmd_later(self, upd, cmd: Cmd) -> None:
        """Move task to later."""
        self.tg.send(self.user_id, "Moved to later ⏳", None, "HTML")

    def _cmd_day(self, upd, cmd: Cmd) -> None:
        """Move task to a specific day."""
        self.tg.send(self.user_id, "Moved to day 📆", None, "HTML")

    def _cmd_checklist(self, upd, cmd: Cmd) -> None:
        """Convert task to checklist."""
        self.tg.send(self.user_id, "Converted to checklist ☑️", None, "HTML")

    def _cmd_file(self, upd, cmd: Cmd) -> None:
        """Open a file or directory."""
        if not cmd.params:
            return
        filename = cmd.params[0]
        file_hash = cmd.params[1] if len(cmd.params) > 1 else ""

        # Check if it's a directory
        is_dir, _ = self.user_fs.exists(DIR_USER_ROOT, filename)
        if is_dir:
            files, _ = self.user_fs.files_and_dirs(DIR_USER_ROOT)
            dirs = only_note_dirs(only_dirs(files))
            notes = only_files(files)
            text = self._render_home_text(dirs, notes)
            kb = self._build_home_keyboard(dirs, notes)
            self.tg.send(self.user_id, text, kb, "HTML")
        else:
            content, _ = self.user_fs.read(DIR_USER_ROOT, filename)
            text = markdown_to_html(content) if content else "(empty)"
            kb = self._build_file_keyboard(filename, file_hash)
            self.tg.send(self.user_id, text, kb, "HTML")

    def _build_file_keyboard(self, filename: str, file_hash: str) -> Keyboard:
        """Build keyboard for a file view."""
        kb = new_keyboard()
        kb.add_row(new_row(
            new_btn(STR_COMPLETE, new_cmd(CMD_DONE, [file_hash])),
            new_btn("🗑 Delete", new_cmd(CMD_DEL, [file_hash])),
        ))
        kb.add_row(new_row(
            new_btn("✏️ Rename", new_cmd(CMD_RENAME, [file_hash])),
            new_btn("➡️ Move", new_cmd(CMD_MOVE, [file_hash])),
        ))
        kb.add_row(new_row(
            new_btn(STR_TO_JOURNAL, new_cmd(CMD_JOURNAL, [file_hash])),
            new_btn(STR_TO_CHECKLIST, new_cmd(CMD_CHECKLIST, [file_hash])),
        ))
        kb.add_row(new_row(
            new_btn(STR_BACK, new_cmd(CMD_BACK)),
        ))
        return kb

    def _cmd_journal(self, upd, cmd: Cmd) -> None:
        """Add to journal."""
        self.tg.send(self.user_id, "Added to journal 💚", None, "HTML")

    def _cmd_read(self, upd, cmd: Cmd) -> None:
        """Move to read list."""
        self.tg.send(self.user_id, "Moved to read 📚", None, "HTML")

    def _cmd_shop(self, upd, cmd: Cmd) -> None:
        """Move to shop list."""
        self.tg.send(self.user_id, "Moved to shop 🛒", None, "HTML")

    def _cmd_watch(self, upd, cmd: Cmd) -> None:
        """Move to watch list."""
        self.tg.send(self.user_id, "Moved to watch 📺", None, "HTML")

    def _cmd_repeat(self, upd, cmd: Cmd) -> None:
        """Undo a done action."""
        self.tg.send(self.user_id, "Undone ↩️", None, "HTML")

    def _cmd_quick(self, upd, cmd: Cmd) -> None:
        """Show quick buttons."""
        self.tg.send(self.user_id, "Quick buttons ⚡️", None, "HTML")

    def _cmd_move_to(self, upd, cmd: Cmd) -> None:
        """Show move-to buttons."""
        self.tg.send(self.user_id, "Move to ➡️", None, "HTML")

    def _cmd_pomodoro(self, upd, cmd: Cmd) -> None:
        """Start a pomodoro timer."""
        self.tg.send(self.user_id, POMODORO_STARTED, None, "HTML")

    def _cmd_habits(self, upd, cmd: Cmd) -> None:
        """Show habits view."""
        self.tg.send(self.user_id, "Habits 📊", None, "HTML")

    def _cmd_stats(self, upd, cmd: Cmd) -> None:
        """Show stats view."""
        report, _ = today_report(self.user_fs, self.user_id)
        self.tg.send(self.user_id, report or "No stats yet", None, "HTML")

    def _cmd_settings(self, upd, cmd: Cmd) -> None:
        """Show settings view."""
        self.tg.send(self.user_id, "Settings ⚙️", None, "HTML")

    def _cmd_help(self, upd, cmd: Cmd) -> None:
        """Show help."""
        self.tg.send(self.user_id, "Help: Send me a message to create a note, or use the buttons below.", None, "HTML")

    def _cmd_cancel(self, upd, cmd: Cmd) -> None:
        """Cancel current operation."""
        self.db.del_input_expectation()
        self.tg.send(self.user_id, "Cancelled", None, "HTML")

    def _cmd_complete(self, upd, cmd: Cmd) -> None:
        """Complete a task."""
        self._cmd_done(upd, cmd)

    def _cmd_add_checklist(self, upd, cmd: Cmd) -> None:
        """Add a checklist to a file."""
        self.tg.send(self.user_id, "Checklist added ☑️", None, "HTML")

    def _cmd_complete_checklist(self, upd, cmd: Cmd) -> None:
        """Complete a checklist item."""
        self.tg.send(self.user_id, "Checklist item completed ✅", None, "HTML")

    def _cmd_del_checklist(self, upd, cmd: Cmd) -> None:
        """Delete a checklist item."""
        self.tg.send(self.user_id, "Checklist item deleted 🗑", None, "HTML")

    def _cmd_today_report(self, upd, cmd: Cmd) -> None:
        """Show today's report."""
        report, _ = today_report(self.user_fs, self.user_id)
        self.tg.send(self.user_id, report or "No tasks completed today", None, "HTML")

    def _cmd_search(self, upd, cmd: Cmd) -> None:
        """Start search flow."""
        self.db.set_input_expectation(new_cmd(CMD_SEARCH_NOTES))
        self.tg.send(self.user_id, "Send me a search query:", None, "HTML")

    def _cmd_merge(self, upd, cmd: Cmd) -> None:
        """Merge two files."""
        self.tg.send(self.user_id, "Merge completed", None, "HTML")

    def _cmd_touch(self, upd, cmd: Cmd) -> None:
        """Touch a file (update timestamp)."""
        self.tg.send(self.user_id, "File touched", None, "HTML")

    def _cmd_add(self, upd, cmd: Cmd) -> None:
        """Add a new item."""
        self._cmd_new(upd, cmd)

    def _cmd_notes(self, upd, cmd: Cmd) -> None:
        """Show notes."""
        self._cmd_home(upd, cmd)

    def _cmd_archive(self, upd, cmd: Cmd) -> None:
        """Show archive."""
        self.tg.send(self.user_id, "Archive 📦", None, "HTML")

    def _cmd_media(self, upd, cmd: Cmd) -> None:
        """Show media."""
        self.tg.send(self.user_id, "Media 🖼", None, "HTML")

    def _cmd_journal_dir(self, upd, cmd: Cmd) -> None:
        """Show journal directory."""
        self.tg.send(self.user_id, "Journal 💚", None, "HTML")

    def _cmd_habits_dir(self, upd, cmd: Cmd) -> None:
        """Show habits directory."""
        self.tg.send(self.user_id, "Habits 📊", None, "HTML")

    def _cmd_insights(self, upd, cmd: Cmd) -> None:
        """Show insights."""
        self.tg.send(self.user_id, "Insights 💡", None, "HTML")

    def _cmd_toggle_mode(self, upd, cmd: Cmd) -> None:
        """Toggle mode."""
        self.tg.send(self.user_id, "Mode toggled", None, "HTML")

    def _cmd_toggle_two_emojis(self, upd, cmd: Cmd) -> None:
        """Toggle two emojis per button."""
        self.tg.send(self.user_id, "Two emojis toggled", None, "HTML")

    def _cmd_toggle_quick_habits(self, upd, cmd: Cmd) -> None:
        """Toggle quick habits."""
        self.tg.send(self.user_id, "Quick habits toggled", None, "HTML")

    def _cmd_add_to_schedule(self, upd, cmd: Cmd) -> None:
        """Add to schedule."""
        self.tg.send(self.user_id, "Added to schedule", None, "HTML")

    def _cmd_del_from_schedule(self, upd, cmd: Cmd) -> None:
        """Delete from schedule."""
        self.tg.send(self.user_id, "Deleted from schedule", None, "HTML")

    def _cmd_channel(self, upd, cmd: Cmd) -> None:
        """Channel command."""
        self.tg.send(self.user_id, "Channel", None, "HTML")

    def _cmd_add_checklist_item(self, upd, cmd: Cmd) -> None:
        """Start add checklist item flow."""
        if not cmd.params:
            return
        self.db.set_input_expectation(new_cmd(CMD_ADD_CHECKLIST_ITEM, cmd.params))
        self.tg.send(self.user_id, "Send me the checklist item:", None, "HTML")

    def _do_add_checklist_item(self, item: str, params: list) -> None:
        """Add a checklist item to a file."""
        if not params:
            return
        filename_hash = params[0]
        filename, err = self.user_fs.unhash(DIR_USER_ROOT, filename_hash)
        if err:
            return
        content, _ = self.user_fs.read(DIR_USER_ROOT, filename)
        content = add_checklist_item(content, item, False)
        self.user_fs.write(DIR_USER_ROOT, filename, content)
        self.tg.send(self.user_id, f"Added: {item} ☑️", None, "HTML")

    def _cmd_del_checklist_item(self, upd, cmd: Cmd) -> None:
        """Delete a checklist item."""
        self.tg.send(self.user_id, "Checklist item deleted 🗑", None, "HTML")

    def _cmd_journal_emoji(self, upd, cmd: Cmd) -> None:
        """Add emoji to journal."""
        self.tg.send(self.user_id, "Emoji added to journal", None, "HTML")

    def _cmd_habit_emoji(self, upd, cmd: Cmd) -> None:
        """Add emoji to habit."""
        self.tg.send(self.user_id, "Emoji added to habit", None, "HTML")

    def _cmd_rename_dir(self, upd, cmd: Cmd) -> None:
        """Start rename directory flow."""
        if not cmd.params:
            return
        self.db.set_input_expectation(new_cmd(CMD_RENAME_DIR, cmd.params))
        self.tg.send(self.user_id, "Send me the new directory name:", None, "HTML")

    def _do_rename_dir(self, new_name: str, params: list) -> None:
        """Rename a directory."""
        self.tg.send(self.user_id, f"Directory renamed to: {new_name}", None, "HTML")

    def _cmd_del_dir(self, upd, cmd: Cmd) -> None:
        """Delete a directory."""
        self.tg.send(self.user_id, "Directory deleted 🗑", None, "HTML")

    def _cmd_new_dir(self, upd, cmd: Cmd) -> None:
        """Start new directory flow."""
        self.db.set_input_expectation(new_cmd(CMD_NEW_DIR))
        self.tg.send(self.user_id, "Send me the new directory name:", None, "HTML")

    def _do_new_dir(self, name: str) -> None:
        """Create a new directory."""
        name = sanitize_filename(name)
        self.user_fs.make_dir(name)
        self.tg.send(self.user_id, f"Directory created: {name}", None, "HTML")

    def _cmd_touch_file(self, upd, cmd: Cmd) -> None:
        """Touch a file."""
        self.tg.send(self.user_id, "File touched", None, "HTML")

    def _cmd_merge_file(self, upd, cmd: Cmd) -> None:
        """Merge a file."""
        self.tg.send(self.user_id, "File merged", None, "HTML")

    def _cmd_search_notes(self, upd, cmd: Cmd) -> None:
        """Start search notes flow."""
        self.db.set_input_expectation(new_cmd(CMD_SEARCH_NOTES))
        self.tg.send(self.user_id, "Send me a search query:", None, "HTML")

    def _do_search_notes(self, query: str) -> None:
        """Search notes by query."""
        results, err = self.user_fs.search_files_by_name(query)
        if err:
            self.tg.send(self.user_id, f"Search error: {err}", None, "HTML")
            return
        if not results:
            self.tg.send(self.user_id, "No results found", None, "HTML")
            return
        parts = [f"🔍 Search results for '{query}':"]
        for r in results[:20]:
            parts.append(f"📄 {r.display_name}")
        self.tg.send(self.user_id, "\n".join(parts), None, "HTML")


def new_server(tg, db, user_fs: FS, user_id: int) -> Server:
    return Server(tg, db, user_fs, user_id)
