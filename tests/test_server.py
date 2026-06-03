"""Tests for server module - core bot logic."""

import pytest

from nas_md.fs import FS, DIR_USER_ROOT, DIR_ARCHIVE, DIR_HABITS
from nas_md.db import FakeDB
from nas_md.pkg.tg.fake import FakeTG
from nas_md.pkg.tg.types import new_cmd
from nas_md.server import new_server


class FakeUpd:
    """Fake update for testing."""

    def __init__(self, user_id=123, msg="", cmd=None):
        self._user_id = user_id
        self._msg = msg
        self._cmd = cmd

    def msg_text(self):
        return self._msg

    def cmd(self):
        return self._cmd


@pytest.fixture
def bot():
    """Create a bot server with fake dependencies."""
    tg = FakeTG()
    db = FakeDB()
    user_fs = FS("/testuser", backend="mem")
    user_fs.create_system_dirs()
    server = new_server(tg, db, user_fs, 123)
    return server, tg, db, user_fs


class TestServerHome:
    def test_home_empty(self, bot):
        server, tg, _db, _user_fs = bot
        upd = FakeUpd(cmd=new_cmd("home"))
        server.handle(upd)
        # Should send something (home screen)
        assert tg.last_sent_text != "" or len(tg.messages) > 0

    def test_home_with_files(self, bot):
        server, tg, _db, user_fs = bot
        user_fs.write(DIR_USER_ROOT, "Task.md", "Task content")
        upd = FakeUpd(cmd=new_cmd("home"))
        server.handle(upd)
        assert "Task" in tg.last_sent_text


class TestServerAddTask:
    def test_add_simple_task(self, bot):
        server, tg, _db, user_fs = bot
        upd = FakeUpd(msg="Buy milk")
        server.handle(upd)
        assert "Added" in tg.last_sent_text
        exists, _ = user_fs.exists(DIR_USER_ROOT, "Buy milk.md")
        assert exists

    def test_add_empty_message(self, bot):
        server, tg, _db, _user_fs = bot
        upd = FakeUpd(msg="")
        server.handle(upd)
        # Should not crash
        assert tg.last_sent_text == "" or "Added" not in tg.last_sent_text


class TestServerCommand:
    def test_home_command(self, bot):
        server, tg, _db, _user_fs = bot
        upd = FakeUpd(cmd=new_cmd("home"))
        server.handle(upd)
        assert tg.last_sent_text != ""

    def test_help_command(self, bot):
        server, tg, _db, _user_fs = bot
        upd = FakeUpd(cmd=new_cmd("help"))
        server.handle(upd)
        assert "Help" in tg.last_sent_text

    def test_settings_command(self, bot):
        server, tg, _db, _user_fs = bot
        upd = FakeUpd(cmd=new_cmd("settings"))
        server.handle(upd)
        assert "Settings" in tg.last_sent_text

    def test_habits_command(self, bot):
        server, tg, _db, _user_fs = bot
        upd = FakeUpd(cmd=new_cmd("habits"))
        server.handle(upd)
        assert "Habits" in tg.last_sent_text

    def test_stats_command(self, bot):
        server, tg, _db, _user_fs = bot
        upd = FakeUpd(cmd=new_cmd("stats"))
        server.handle(upd)
        assert tg.last_sent_text != ""

    def test_cancel_command(self, bot):
        server, tg, _db, _user_fs = bot
        upd = FakeUpd(cmd=new_cmd("cancel"))
        server.handle(upd)
        assert "Cancelled" in tg.last_sent_text


class TestServerFileOperations:
    def test_done_task(self, bot):
        server, tg, _db, user_fs = bot
        user_fs.write(DIR_USER_ROOT, "Task.md", "content")
        from nas_md.fs import hash_filename

        h = hash_filename("Task.md")
        upd = FakeUpd(cmd=new_cmd("done", [h]))
        server.handle(upd)
        assert "✅" in tg.last_sent_text
        # Should be moved to archive
        exists, _ = user_fs.exists(DIR_ARCHIVE, "Task.md")
        assert exists

    def test_delete_task(self, bot):
        server, tg, _db, user_fs = bot
        user_fs.write(DIR_USER_ROOT, "Task.md", "content")
        from nas_md.fs import hash_filename

        h = hash_filename("Task.md")
        upd = FakeUpd(cmd=new_cmd("del", [h]))
        server.handle(upd)
        assert "Deleted" in tg.last_sent_text
        exists, _ = user_fs.exists(DIR_USER_ROOT, "Task.md")
        assert not exists

    def test_rename_expectation(self, bot):
        server, tg, _db, user_fs = bot
        user_fs.write(DIR_USER_ROOT, "Old.md", "content")
        from nas_md.fs import hash_filename

        h = hash_filename("Old.md")
        upd = FakeUpd(cmd=new_cmd("rename", [h]))
        server.handle(upd)
        assert "new name" in tg.last_sent_text.lower() or "Send me" in tg.last_sent_text

    def test_new_expectation(self, bot):
        server, tg, _db, _user_fs = bot
        upd = FakeUpd(cmd=new_cmd("new"))
        server.handle(upd)
        assert "new task" in tg.last_sent_text.lower() or "Send me" in tg.last_sent_text


class TestServerInputExpectation:
    def test_new_task_via_expectation(self, bot):
        server, tg, db, _user_fs = bot
        # Set expectation
        db.set_input_expectation(new_cmd("new"))
        # Send message
        upd = FakeUpd(msg="New task from input")
        server.handle(upd)
        assert "Added" in tg.last_sent_text
        # Expectation should be cleared
        assert db.input_expectation() is None

    def test_cancel_clears_expectation(self, bot):
        server, _tg, db, _user_fs = bot
        db.set_input_expectation(new_cmd("new"))
        upd = FakeUpd(cmd=new_cmd("cancel"))
        server.handle(upd)
        assert db.input_expectation() is None


class TestServerJournal:
    def test_add_journal_entry(self, bot):
        server, tg, _db, _user_fs = bot
        upd = FakeUpd(msg="## 23 May, Friday\nTest journal entry")
        server.handle(upd)
        assert "journal" in tg.last_sent_text.lower()


class TestServerHabit:
    def test_add_habit(self, bot):
        server, tg, _db, user_fs = bot
        upd = FakeUpd(msg="#habit Running")
        server.handle(upd)
        assert "Habit" in tg.last_sent_text
        exists, _ = user_fs.exists(DIR_HABITS, "Running.md")
        assert exists


class TestServerSearch:
    def test_search_expectation(self, bot):
        server, tg, _db, _user_fs = bot
        upd = FakeUpd(cmd=new_cmd("searchNotes"))
        server.handle(upd)
        assert "search" in tg.last_sent_text.lower()

    def test_search_results(self, bot):
        server, tg, db, user_fs = bot
        user_fs.write(DIR_USER_ROOT, "Python Notes.md", "content")
        user_fs.write(DIR_USER_ROOT, "JavaScript.md", "content")
        # Set expectation and search
        db.set_input_expectation(new_cmd("searchNotes"))
        upd = FakeUpd(msg="python")
        server.handle(upd)
        assert "Python" in tg.last_sent_text or "results" in tg.last_sent_text.lower()
