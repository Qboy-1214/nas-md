"""Tests for db module."""

import os
import tempfile

import pytest

from nas_md.db import DB, FakeDB, _hash_or_path_by_msg_id, _input_expectations, _recent_commands


class TestFakeDB:
    def setup_method(self):
        self.db = FakeDB()

    def test_last_keyboard_msg_id_default(self):
        mid, found = self.db.last_keyboard_msg_id()
        assert not found
        assert mid == 0

    def test_set_last_keyboard_msg_id(self):
        self.db.set_last_keyboard_msg_id(42)
        mid, found = self.db.last_keyboard_msg_id()
        assert found
        assert mid == 42

    def test_del_last_keyboard_msg_id(self):
        self.db.set_last_keyboard_msg_id(42)
        self.db.del_last_keyboard_msg_id()
        _, found = self.db.last_keyboard_msg_id()
        assert not found

    def test_input_expectation_default(self):
        assert self.db.input_expectation() is None

    def test_set_input_expectation(self):
        from nas_md.pkg.tg.types import Cmd
        cmd = Cmd(name="test", params=["a", "b"])
        self.db.set_input_expectation(cmd)
        result = self.db.input_expectation()
        assert result is not None
        assert result.name == "test"

    def test_del_input_expectation(self):
        from nas_md.pkg.tg.types import Cmd
        self.db.set_input_expectation(Cmd(name="test"))
        self.db.del_input_expectation()
        assert self.db.input_expectation() is None

    def test_hash_or_path_by_msg_id_default(self):
        val, found = self.db.hash_or_path_by_msg_id(123)
        assert not found
        assert val == ""

    def test_set_hash_or_path_by_msg_id(self):
        self.db.set_hash_or_path_by_msg_id(123, "test-hash")
        val, found = self.db.hash_or_path_by_msg_id(123)
        assert found
        assert val == "test-hash"

    def test_recent_command_default(self):
        cmd, found = self.db.recent_command()
        assert not found
        assert cmd == ""

    def test_set_recent_command(self):
        self.db.set_recent_command("done")
        cmd, found = self.db.recent_command()
        assert found
        assert cmd == "done"

    def test_recent_command_params_default(self):
        params, found = self.db.recent_command_params()
        assert not found

    def test_set_recent_command_params(self):
        self.db.set_recent_command_params(["a", "b"])
        params, found = self.db.recent_command_params()
        assert found
        assert params == ["a", "b"]

    def test_img_msg_id_default(self):
        ids, found = self.db.img_msg_id()
        assert not found

    def test_add_img_msg_id(self):
        self.db.add_img_msg_id(1)
        # FakeDB.add_img_msg_id is a no-op
        ids, found = self.db.img_msg_id()
        assert not found

    def test_del_img_msg_id(self):
        self.db.del_img_msg_id()  # Should not raise


class TestDB:
    """Test real DB with temp files."""

    def setup_method(self):
        self.user_id = 999999
        self.db = DB(self.user_id)

    def teardown_method(self):
        # Clean up temp files
        for name in ["msgid"]:
            path = os.path.join(tempfile.gettempdir(), f"{self.user_id}.{name}")
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    def test_last_keyboard_msg_id_file(self):
        self.db.set_last_keyboard_msg_id(100)
        mid, found = self.db.last_keyboard_msg_id()
        assert found
        assert mid == 100

    def test_del_last_keyboard_msg_id_file(self):
        self.db.set_last_keyboard_msg_id(100)
        self.db.del_last_keyboard_msg_id()
        _, found = self.db.last_keyboard_msg_id()
        assert not found
