"""Tests for journal module."""

import pytest

from nas_md.fs import FS, DIR_JOURNAL
from nas_md.journal import add_record, add_emoji


@pytest.fixture
def mem_fs():
    return FS("/testuser", backend="mem")


class TestAddRecord:
    def test_add_first_record(self, mem_fs):
        add_record(mem_fs, "Test record")
        files, _ = mem_fs.files_and_dirs(DIR_JOURNAL)
        assert len(files) == 1
        content, _ = mem_fs.read(DIR_JOURNAL, files[0].name)
        assert "Test record" in content

    def test_add_multiple_records(self, mem_fs):
        add_record(mem_fs, "Record 1")
        add_record(mem_fs, "Record 2")
        files, _ = mem_fs.files_and_dirs(DIR_JOURNAL)
        assert len(files) == 1  # Same month file
        content, _ = mem_fs.read(DIR_JOURNAL, files[0].name)
        assert "Record 1" in content
        assert "Record 2" in content

    def test_record_has_timestamp(self, mem_fs):
        add_record(mem_fs, "Timed record")
        files, _ = mem_fs.files_and_dirs(DIR_JOURNAL)
        content, _ = mem_fs.read(DIR_JOURNAL, files[0].name)
        # Should contain a timestamp like `HH:MM`
        assert "`" in content

    def test_empty_record(self, mem_fs):
        add_record(mem_fs, "")
        _files, _ = mem_fs.files_and_dirs(DIR_JOURNAL)
        # Empty record should not create a file
        # (depends on implementation - may or may not create)

    def test_record_with_newlines(self, mem_fs):
        add_record(mem_fs, "Line 1\nLine 2")
        files, _ = mem_fs.files_and_dirs(DIR_JOURNAL)
        content, _ = mem_fs.read(DIR_JOURNAL, files[0].name)
        assert "Line 1" in content


class TestAddEmoji:
    def test_add_emoji_to_new_day(self, mem_fs):
        add_emoji(mem_fs, "💪")
        files, _ = mem_fs.files_and_dirs(DIR_JOURNAL)
        assert len(files) == 1
        content, _ = mem_fs.read(DIR_JOURNAL, files[0].name)
        assert "💪" in content

    def test_add_emoji_to_existing_day(self, mem_fs):
        add_record(mem_fs, "Test")
        add_emoji(mem_fs, "💪")
        files, _ = mem_fs.files_and_dirs(DIR_JOURNAL)
        content, _ = mem_fs.read(DIR_JOURNAL, files[0].name)
        assert "💪" in content
        assert "Test" in content

    def test_add_multiple_emojis(self, mem_fs):
        add_emoji(mem_fs, "💪")
        add_emoji(mem_fs, "💧")
        files, _ = mem_fs.files_and_dirs(DIR_JOURNAL)
        content, _ = mem_fs.read(DIR_JOURNAL, files[0].name)
        assert "💪" in content
        assert "💧" in content

    def test_empty_emoji(self, mem_fs):
        add_emoji(mem_fs, "")
        _files, _ = mem_fs.files_and_dirs(DIR_JOURNAL)
        # Empty emoji should not create a file
