"""In-memory database for storing user-specific temporary data."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
import contextlib

if TYPE_CHECKING:
    from nas_md.pkg.tg.types import Cmd


# In-memory stores
_hash_or_path_by_msg_id: dict[str, str] = {}
_input_expectations: dict[str, Cmd] = {}
_recent_commands: dict[int, str] = {}
_recent_commands_targets: dict[int, list[str]] = {}
_sent_photo_msg_ids: dict[str, list[int]] = {}


class DB:
    """Per-user in-memory database backed by temp files for some state."""

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id

    def last_keyboard_msg_id(self) -> tuple[int, bool]:
        path = _tmp_file_path(self.user_id, "msgid")
        try:
            data = Path(path).read_text()
            return int(data), True
        except (FileNotFoundError, ValueError):
            return 0, False

    def set_last_keyboard_msg_id(self, msg_id: int) -> None:
        path = _tmp_file_path(self.user_id, "msgid")
        Path(path).write_text(str(msg_id))

    def del_last_keyboard_msg_id(self) -> None:
        path = _tmp_file_path(self.user_id, "msgid")
        with contextlib.suppress(FileNotFoundError):
            os.remove(path)

    def input_expectation(self) -> Cmd | None:
        key = _input_expectation_key(self.user_id)
        cmd = _input_expectations.get(key)
        return cmd

    def set_input_expectation(self, cmd: Cmd) -> None:
        key = _input_expectation_key(self.user_id)
        _input_expectations[key] = cmd

    def del_input_expectation(self) -> None:
        key = _input_expectation_key(self.user_id)
        _input_expectations.pop(key, None)

    def hash_or_path_by_msg_id(self, msg_id: int) -> tuple[str, bool]:
        key = _hash_or_path_key(self.user_id, msg_id)
        val = _hash_or_path_by_msg_id.get(key)
        if val is None:
            return "", False
        return val, True

    def set_hash_or_path_by_msg_id(self, msg_id: int, value: str) -> None:
        key = _hash_or_path_key(self.user_id, msg_id)
        _hash_or_path_by_msg_id[key] = value

    def recent_command(self) -> tuple[str, bool]:
        cmd = _recent_commands.get(self.user_id)
        if cmd is None:
            return "", False
        return cmd, True

    def set_recent_command(self, cmd: str) -> None:
        _recent_commands[self.user_id] = cmd

    def recent_command_params(self) -> tuple[list[str], bool]:
        params = _recent_commands_targets.get(self.user_id)
        if params is None:
            return None, False
        return params, True

    def set_recent_command_params(self, params: list[str]) -> None:
        _recent_commands_targets[self.user_id] = params

    def add_img_msg_id(self, msg_id: int) -> None:
        key = _photo_msg_id_key(self.user_id)
        ids = _sent_photo_msg_ids.get(key, [])
        ids.append(msg_id)
        _sent_photo_msg_ids[key] = ids

    def img_msg_id(self) -> tuple[list[int], bool]:
        key = _photo_msg_id_key(self.user_id)
        ids = _sent_photo_msg_ids.get(key)
        if ids is None:
            return None, False
        return ids, True

    def del_img_msg_id(self) -> None:
        key = _photo_msg_id_key(self.user_id)
        _sent_photo_msg_ids.pop(key, None)


class FakeDB:
    """Fake database for testing."""

    def __init__(self) -> None:
        self.hash_or_path_by_mid: str = ""
        self.input_expectation_cmd: Cmd | None = None
        self.last_keyboard_mid: int = -1
        self.recent_cmd: str = ""
        self.recent_cmd_params: list[str] | None = None

    def last_keyboard_msg_id(self) -> tuple[int, bool]:
        if self.last_keyboard_mid == -1:
            return 0, False
        return self.last_keyboard_mid, True

    def set_last_keyboard_msg_id(self, msg_id: int) -> None:
        self.last_keyboard_mid = msg_id

    def del_last_keyboard_msg_id(self) -> None:
        self.last_keyboard_mid = -1

    def input_expectation(self) -> Cmd | None:
        return self.input_expectation_cmd

    def set_input_expectation(self, cmd: Cmd) -> None:
        self.input_expectation_cmd = cmd

    def del_input_expectation(self) -> None:
        self.input_expectation_cmd = None

    def hash_or_path_by_msg_id(self, msg_id: int) -> tuple[str, bool]:
        return self.hash_or_path_by_mid, self.hash_or_path_by_mid != ""

    def set_hash_or_path_by_msg_id(self, msg_id: int, value: str) -> None:
        self.hash_or_path_by_mid = value

    def recent_command(self) -> tuple[str, bool]:
        return self.recent_cmd, self.recent_cmd != ""

    def set_recent_command(self, cmd: str) -> None:
        self.recent_cmd = cmd

    def recent_command_params(self) -> tuple[list[str], bool]:
        return (
            self.recent_cmd_params,
            self.recent_cmd_params is not None and len(self.recent_cmd_params) > 0,
        )

    def set_recent_command_params(self, params: list[str]) -> None:
        self.recent_cmd_params = params

    def add_img_msg_id(self, msg_id: int) -> None:
        pass

    def img_msg_id(self) -> tuple[list[int], bool]:
        return None, False

    def del_img_msg_id(self) -> None:
        pass


def _photo_msg_id_key(user_id: int) -> str:
    return f"{user_id}:sentPhotoMsgIDs"


def _input_expectation_key(user_id: int) -> str:
    return f"{user_id}:inputExpectations"


def _hash_or_path_key(user_id: int, msg_id: int) -> str:
    return f"{user_id}:hashOrPathByMsgID:{msg_id}"


def _tmp_file_path(user_id: int, name: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"{user_id}.{name}")
