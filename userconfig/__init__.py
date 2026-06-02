"""User configuration module - stores user settings in JSON files."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any

from nas_md.fs import FS, DIR_USER_ROOT

MODE_CHAT = "chat"
MODE_FULL = "full"
MODE_TASKS = "tasks"
MODE_NOTES = "notes"
MODE_JOURNAL = "journal"

DEFAULT_CONFIG = {
    "language": "en",
    "timezone": "UTC",
    "moveToCommands": [],
    "pomodoroDurationInMinutes": 50,
    "schedules": [],
    "quickCommands": [],
    "twoEmojisEnabled": False,
    "mode": "full",
    "quickHabitsEnabled": False,
    "channels": [],
}

_user_locks: dict[int, Lock] = {}
_global_lock = Lock()


@dataclass
class Schedule:
    filename: str
    scheduled_at: int
    cron: str
    cmd: str = ""


class UserConfig:
    """Per-user configuration stored in a JSON file."""

    def __init__(self, user_fs: FS, user_id: int, filename: str) -> None:
        self.user_fs = user_fs
        self.user_id = user_id
        self.filename = filename

    def create_default_if_not_exists(self) -> None:
        exists, _ = self.user_fs.exists(DIR_USER_ROOT, self.filename)
        if exists:
            return
        self._write(DEFAULT_CONFIG)

    def timezone(self) -> str:
        cfg = self._read()
        tz = cfg.get("timezone", "")
        if not tz:
            return "UTC"
        return tz

    def set_timezone(self, tz: str) -> None:
        with self._user_lock():
            cfg = self._read()
            cfg["timezone"] = tz
            self._write(cfg)

    def chat_only_mode(self) -> bool:
        return self._read().get("mode", "") == MODE_CHAT

    def tasks_only_mode(self) -> bool:
        return self._read().get("mode", "") == MODE_TASKS

    def notes_only_mode(self) -> bool:
        return self._read().get("mode", "") == MODE_NOTES

    def journal_only_mode(self) -> bool:
        return self._read().get("mode", "") == MODE_JOURNAL

    def set_mode(self, mode: str) -> None:
        with self._user_lock():
            cfg = self._read()
            cfg["mode"] = mode
            self._write(cfg)

    def pomodoro_duration(self) -> int:
        """Return pomodoro duration in seconds."""
        return self._read().get("pomodoroDurationInMinutes", 50) * 60

    def set_pomodoro_duration(self, duration_seconds: int) -> None:
        if duration_seconds <= 0 or duration_seconds > 86400:
            raise ValueError(f"invalid duration: {duration_seconds}")
        with self._user_lock():
            cfg = self._read()
            cfg["pomodoroDurationInMinutes"] = duration_seconds // 60
            self._write(cfg)

    def schedules(self) -> list[dict]:
        cfg = self._read()
        schedules = cfg.get("schedules", [])
        # Sort by scheduled_at descending
        schedules.sort(key=lambda s: s.get("scheduledAt", 0), reverse=True)
        return schedules

    def add_to_schedule(self, filename: str, schedule_at: int, cron: str) -> None:
        with self._user_lock():
            cfg = self._read()
            schedules = cfg.get("schedules", [])
            found = False
            for s in schedules:
                if s.get("filename") == filename:
                    s["scheduledAt"] = schedule_at
                    s["cron"] = cron
                    found = True
                    break
            if not found:
                schedules.append({"filename": filename, "scheduledAt": schedule_at, "cron": cron, "cmd": ""})
            cfg["schedules"] = schedules
            self._write(cfg)

    def del_from_schedule(self, filename: str) -> None:
        with self._user_lock():
            cfg = self._read()
            schedules = [s for s in cfg.get("schedules", []) if s.get("filename") != filename]
            cfg["schedules"] = schedules
            self._write(cfg)

    def two_emojis_per_button_enabled(self) -> bool:
        return self._read().get("twoEmojisEnabled", False)

    def quick_habits_enabled(self) -> bool:
        return self._read().get("quickHabitsEnabled", False)

    def channels(self) -> list[int]:
        return self._read().get("channels", [])

    def add_channel(self, channel_id: int) -> None:
        with self._user_lock():
            cfg = self._read()
            channels = cfg.get("channels", [])
            if channel_id not in channels:
                channels.append(channel_id)
                cfg["channels"] = channels
                self._write(cfg)

    def del_channel(self, channel_id: int) -> None:
        with self._user_lock():
            cfg = self._read()
            channels = [c for c in cfg.get("channels", []) if c != channel_id]
            cfg["channels"] = channels
            self._write(cfg)

    def quick_cmds(self) -> list[str]:
        return self._read().get("quickCommands", [])

    def add_quick_cmd(self, cmd: str) -> None:
        with self._user_lock():
            cfg = self._read()
            cmds = cfg.get("quickCommands", [])
            if cmd not in cmds:
                cmds.append(cmd)
                cfg["quickCommands"] = cmds
                self._write(cfg)

    def del_quick_cmd(self, cmd: str) -> None:
        with self._user_lock():
            cfg = self._read()
            cmds = [c for c in cfg.get("quickCommands", []) if c != cmd]
            cfg["quickCommands"] = cmds
            self._write(cfg)

    def move_to_cmds(self) -> list[str]:
        return self._read().get("moveToCommands", [])

    def add_move_to_cmd(self, cmd: str) -> None:
        with self._user_lock():
            cfg = self._read()
            cmds = cfg.get("moveToCommands", [])
            if cmd not in cmds:
                cmds.append(cmd)
                cfg["moveToCommands"] = cmds
                self._write(cfg)

    def del_move_to_cmd(self, cmd: str) -> None:
        with self._user_lock():
            cfg = self._read()
            cmds = [c for c in cfg.get("moveToCommands", []) if c != cmd]
            cfg["moveToCommands"] = cmds
            self._write(cfg)

    def set_two_emojis(self, enabled: bool) -> None:
        with self._user_lock():
            cfg = self._read()
            cfg["twoEmojisEnabled"] = enabled
            self._write(cfg)

    def set_quick_habits(self, enabled: bool) -> None:
        with self._user_lock():
            cfg = self._read()
            cfg["quickHabitsEnabled"] = enabled
            self._write(cfg)

    def _read(self) -> dict:
        exists, _ = self.user_fs.exists(DIR_USER_ROOT, self.filename)
        if not exists:
            return dict(DEFAULT_CONFIG)
        content, _ = self.user_fs.read(DIR_USER_ROOT, self.filename)
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return dict(DEFAULT_CONFIG)

    def _write(self, cfg: dict) -> None:
        self.user_fs.write(DIR_USER_ROOT, self.filename, json.dumps(cfg, indent=4))

    def _user_lock(self) -> Lock:
        with _global_lock:
            if self.user_id not in _user_locks:
                _user_locks[self.user_id] = Lock()
            return _user_locks[self.user_id]
