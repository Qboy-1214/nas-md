"""Tests for the command router and modular command system."""

from nas_md.server.router import command, get_handler, all_commands, register_module, _registry


class TestCommandRouter:
    def setup_method(self):
        # Clear registry before each test
        _registry.clear()

    def test_command_decorator(self):
        @command("test_cmd")
        def handler(server, upd, cmd):
            pass

        assert get_handler("test_cmd") is handler

    def test_get_handler_not_found(self):
        assert get_handler("nonexistent") is None

    def test_all_commands(self):
        @command("cmd1")
        def h1(server, upd, cmd):
            pass

        @command("cmd2")
        def h2(server, upd, cmd):
            pass

        cmds = all_commands()
        assert "cmd1" in cmds
        assert "cmd2" in cmds

    def test_register_module(self):
        count = register_module("search")
        assert count > 0
        # search module should register "search" command
        assert get_handler("search") is not None

    def test_register_all_modules(self):
        from nas_md.server.router import register_all_modules

        _registry.clear()
        total = register_all_modules()
        assert total > 0
        # Check key commands are registered
        assert get_handler("search") is not None
        assert get_handler("backlink") is not None
        assert get_handler("home") is not None
        assert get_handler("habits") is not None
