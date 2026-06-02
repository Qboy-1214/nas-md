"""Telegram update interface and implementations."""

from __future__ import annotations

from dataclasses import dataclass

from nas_md.pkg.tg.types import Cmd


@dataclass
class Upd:
    """Fake update for testing."""
    user_id: int = 0
    _cmd: Cmd | None = None
    msg: str = ""
    photo_id: str = ""
    photo_caption: str = ""
    reply_to_message_id: int = -1
    is_sent_via_bot_val: bool = False
    inline_query_val: str = ""
    is_inline_query_val: bool = False
    time_val: int = 0
    has_time_val: bool = False

    def msg_text(self) -> str:
        return self.msg

    def user_id(self) -> int:
        return self.user_id

    def cmd(self) -> Cmd | None:
        if self._cmd is None or not self._cmd.name:
            return None
        return self._cmd

    def msg_entities(self) -> list:
        return []

    def caption_entities(self) -> list:
        return []

    def callback_query_id(self) -> tuple[str, bool]:
        return "", True

    def inline_query_id(self) -> tuple[str, bool]:
        return "", False

    def inline_query(self) -> tuple[str, bool]:
        return self.inline_query_val, self.is_inline_query_val

    def inline_query_offset(self) -> int:
        return 0

    def is_forwarded(self) -> bool:
        return False

    def is_sent_via_bot(self) -> bool:
        return self.is_sent_via_bot_val

    def reply_to_msg_id(self) -> tuple[int, bool]:
        return self.reply_to_message_id, self.reply_to_message_id != -1

    def photo_or_image_id(self) -> tuple[str, bool]:
        if self.photo_id:
            return self.photo_id, True
        return "", False

    def caption(self) -> str:
        return self.photo_caption

    def msg_id(self) -> tuple[int, bool]:
        return 0, False

    def time(self) -> tuple[int, bool]:
        return self.time_val, self.has_time_val

    def channel_id(self) -> tuple[int, bool]:
        return 0, False

    def channel_name(self) -> tuple[str, bool]:
        return "", False


@dataclass
class Message:
    """Represents a sent/received message."""
    text: str = ""
    buttons: list = None

    def __post_init__(self):
        if self.buttons is None:
            self.buttons = []
