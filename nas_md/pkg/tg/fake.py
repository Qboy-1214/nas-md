"""Fake Telegram API for testing."""

from __future__ import annotations

from dataclasses import dataclass, field

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nas_md.pkg.tg.types import Keyboard


@dataclass
class FakeMessage:
    text: str = ""
    buttons: list = field(default_factory=list)


class FakeTG:
    """Fake Telegram API that records sent messages."""

    def __init__(self) -> None:
        self.sent_texts: list[str] = []
        self.last_sent_text: str = ""
        self.last_edited_text: str = ""
        self.last_sent_keyboard: Keyboard | None = None
        self.last_edited_keyboard: Keyboard | None = None
        self.inline_query_results: list = []
        self.last_sent_message_id: int = 0
        self.messages: list[FakeMessage] = []
        self.edited_messages: list[FakeMessage] = []

    def send(self, user_id: int, text: str, kb: Keyboard | None, markup: str) -> tuple[int, None]:
        self.last_sent_text = text
        self.sent_texts.append(text)
        self.last_sent_keyboard = kb
        self.last_edited_keyboard = None
        self.last_edited_text = ""
        self.last_sent_message_id += 1
        msg = FakeMessage(text=text)
        if kb is not None:
            msg.buttons = kb.btns
        self.messages.append(msg)
        return self.last_sent_message_id, None

    def send_images(self, user_id: int, images: list[str]) -> tuple[list[int] | None, None]:
        return [], None

    def send_reaction(self, user_id: int, msg_id: int, reaction: str) -> None:
        pass

    def edit(self, user_id: int, msg_id: int, text: str, kb: Keyboard | None, markup: str) -> None:
        self.last_edited_text = text
        self.last_edited_keyboard = kb
        self.last_sent_keyboard = None
        msg = FakeMessage(text=text)
        if kb is not None:
            msg.buttons = kb.btns
        self.edited_messages.append(msg)

    def del_msg(self, user_id: int, msg_id: int) -> None:
        pass

    def answer_callback_query(self, query_id: str, text: str) -> None:
        pass

    def answer_inline_query(
        self, query_id: str, results: list, cache_time: int, offset: str
    ) -> None:
        self.inline_query_results = results

    def download_file(self, file_id: str, writer) -> tuple[str, None]:
        return "", None

    def channel_creator_id(self, chat_id: int) -> tuple[int, None]:
        return 0, None
