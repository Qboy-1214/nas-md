"""Telegram type definitions - Cmd, Btn, Keyboard, Row interfaces."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

CMD_TYPE_CALLBACK = "cmd"
CMD_TYPE_INLINE_QUERY_CURRENT_CHAT = "iq"
CMD_TYPE_WEB_APP = "web"
CMD_TYPE_URL = "url"


@dataclass
class Cmd:
    """Represents a callback command."""

    name: str = ""
    params: list[str] = field(default_factory=list)
    type: str = CMD_TYPE_CALLBACK
    data: dict | None = None

    def __post_init__(self) -> None:
        if not self.type:
            self.type = CMD_TYPE_CALLBACK


@dataclass
class Btn:
    """A keyboard button."""

    name: str = ""
    cmd: Cmd = field(default_factory=Cmd)


class Row:
    """Marker interface for keyboard rows."""

    pass


@dataclass
class Keyboard:
    """Telegram inline keyboard."""

    btns: list[Any] = field(default_factory=list)

    def add_row(self, row: Any) -> None:
        self.btns.append(row)

    def prepend_row(self, row: Any) -> None:
        self.btns.insert(0, row)


def new_cmd(name: str, params: list[str] | None = None) -> Cmd:
    return Cmd(name=name, params=params or [], type=CMD_TYPE_CALLBACK)


def new_url_cmd(url: str) -> Cmd:
    return Cmd(name="", params=[url], type=CMD_TYPE_URL)


def new_custom_cmd(name: str, params: list[str], cmd_type: str) -> Cmd:
    return Cmd(name=name, params=params, type=cmd_type)


def new_btn(name: str, cmd: Cmd) -> Btn:
    return Btn(name=name, cmd=cmd)


def new_row(*btns: Btn) -> list[Btn]:
    return list(btns)


def new_keyboard(rows: list[Any] | None = None) -> Keyboard:
    return Keyboard(btns=rows or [])


def cmd_from_json(data: str | bytes) -> Cmd:
    """Parse a Cmd from JSON, always resetting type to 'cmd' (matches Go UnmarshalJSON)."""
    parsed = json.loads(data)
    return Cmd(
        name=parsed.get("n", ""),
        params=parsed.get("p", []),
        type=CMD_TYPE_CALLBACK,
    )
