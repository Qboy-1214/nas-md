"""Tests for stats module."""

import pytest

from nas_md.fs import FS, DIR_ARCHIVE
from nas_md.stats import today_report, done_today


@pytest.fixture
def mem_fs():
    return FS("/testuser", backend="mem")


class TestTodayReport:
    def test_empty(self, mem_fs):
        report, err = today_report(mem_fs, 123)
        assert err is None or not err
        assert "0 tasks done in total" in report

    def test_with_completed_tasks(self, mem_fs):
        # Create archived files with recent ctime
        mem_fs.write(DIR_ARCHIVE, "Task1.md", "content")
        mem_fs.write(DIR_ARCHIVE, "Task2.md", "content")
        report, err = today_report(mem_fs, 123)
        assert err is None or not err
        assert "Task1" in report
        assert "Task2" in report


class TestDoneToday:
    def test_empty(self, mem_fs):
        files, err = done_today(mem_fs, 123)
        assert err is None or not err
        assert files == []

    def test_with_files(self, mem_fs):
        mem_fs.write(DIR_ARCHIVE, "Done.md", "content")
        files, err = done_today(mem_fs, 123)
        assert err is None or not err
        assert "Done" in files
