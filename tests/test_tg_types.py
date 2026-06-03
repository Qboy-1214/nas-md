"""Tests for pkg/tg types."""

import json


from nas_md.pkg.tg.types import (
    Cmd,
    new_cmd,
    new_btn,
    new_row,
    new_keyboard,
    new_url_cmd,
    new_custom_cmd,
    cmd_from_json,
    CMD_TYPE_CALLBACK,
    CMD_TYPE_URL,
    CMD_TYPE_INLINE_QUERY_CURRENT_CHAT,
)


class TestCmd:
    def test_default(self):
        cmd = Cmd()
        assert cmd.name == ""
        assert cmd.params == []
        assert cmd.type == CMD_TYPE_CALLBACK

    def test_with_params(self):
        cmd = Cmd(name="done", params=["hash123"])
        assert cmd.name == "done"
        assert cmd.params == ["hash123"]

    def test_empty_params_default(self):
        cmd = Cmd(name="test")
        assert cmd.params == []


class TestNewCmd:
    def test_basic(self):
        cmd = new_cmd("done", ["hash"])
        assert cmd.name == "done"
        assert cmd.params == ["hash"]
        assert cmd.type == CMD_TYPE_CALLBACK

    def test_no_params(self):
        cmd = new_cmd("home")
        assert cmd.params == []


class TestNewUrlCmd:
    def test_url_cmd(self):
        cmd = new_url_cmd("https://example.com")
        assert cmd.type == CMD_TYPE_URL
        assert cmd.params == ["https://example.com"]


class TestNewCustomCmd:
    def test_custom_type(self):
        cmd = new_custom_cmd("iq", ["query"], CMD_TYPE_INLINE_QUERY_CURRENT_CHAT)
        assert cmd.type == CMD_TYPE_INLINE_QUERY_CURRENT_CHAT


class TestBtn:
    def test_new_btn(self):
        cmd = new_cmd("done", ["hash"])
        btn = new_btn("✅ Done", cmd)
        assert btn.name == "✅ Done"
        assert btn.cmd.name == "done"


class TestNewRow:
    def test_row(self):
        cmd1 = new_cmd("a")
        cmd2 = new_cmd("b")
        row = new_row(new_btn("A", cmd1), new_btn("B", cmd2))
        assert len(row) == 2
        assert row[0].name == "A"
        assert row[1].name == "B"


class TestKeyboard:
    def test_new_keyboard(self):
        kb = new_keyboard()
        assert kb.btns == []

    def test_add_row(self):
        kb = new_keyboard()
        row = [new_btn("Test", new_cmd("test"))]
        kb.add_row(row)
        assert len(kb.btns) == 1

    def test_prepend_row(self):
        kb = new_keyboard()
        kb.add_row([new_btn("Second", new_cmd("second"))])
        kb.prepend_row([new_btn("First", new_cmd("first"))])
        assert len(kb.btns) == 2


class TestCmdFromJson:
    def test_basic(self):
        data = json.dumps({"n": "done", "p": ["hash"]})
        cmd = cmd_from_json(data)
        assert cmd.name == "done"
        assert cmd.params == ["hash"]
        assert cmd.type == CMD_TYPE_CALLBACK  # Always reset to "cmd"

    def test_empty(self):
        cmd = cmd_from_json("{}")
        assert cmd.name == ""
        assert cmd.params == []

    def test_type_always_reset(self):
        """CmdFromJson always sets type to 'cmd' regardless of input."""
        data = json.dumps({"n": "test", "p": [], "t": "url"})
        cmd = cmd_from_json(data)
        assert cmd.type == CMD_TYPE_CALLBACK

    def test_bytes_input(self):
        data = b'{"n": "home", "p": []}'
        cmd = cmd_from_json(data)
        assert cmd.name == "home"
