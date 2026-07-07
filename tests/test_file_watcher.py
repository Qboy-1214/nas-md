# tests/test_file_watcher.py
"""Tests for file_watcher module.

Avoids depending on real watchdog observers (which require filesystem events
and threads). Tests only the mark_expected / is_expected logic and the
singleton accessor.
"""
import os
import pytest
from nas_md.webserver.file_watcher import FileWatcher, get_watcher


def test_mark_and_is_expected_match(tmp_path):
    """When marked content matches disk content, is_expected returns True."""
    w = FileWatcher()
    f = tmp_path / "x.md"
    f.write_text("hello", encoding="utf-8")
    w.mark_expected("mount-0", "x.md", "hello")
    assert w.is_expected("mount-0", "x.md", str(f)) is True


def test_mark_and_is_expected_mismatch(tmp_path):
    """When disk content differs from marked, is_expected returns False."""
    w = FileWatcher()
    f = tmp_path / "x.md"
    f.write_text("actual", encoding="utf-8")
    w.mark_expected("mount-0", "x.md", "expected_different")
    assert w.is_expected("mount-0", "x.md", str(f)) is False


def test_is_expected_without_mark_returns_false(tmp_path):
    """Without prior mark_expected, is_expected returns False."""
    w = FileWatcher()
    f = tmp_path / "x.md"
    f.write_text("content", encoding="utf-8")
    assert w.is_expected("mount-0", "x.md", str(f)) is False


def test_is_expected_consumes_mark(tmp_path):
    """is_expected pops the mark, so a second call returns False."""
    w = FileWatcher()
    f = tmp_path / "x.md"
    f.write_text("hello", encoding="utf-8")
    w.mark_expected("mount-0", "x.md", "hello")
    assert w.is_expected("mount-0", "x.md", str(f)) is True
    # Second call: mark already consumed
    assert w.is_expected("mount-0", "x.md", str(f)) is False


def test_is_expected_missing_file(tmp_path):
    """If the file doesn't exist, is_expected returns False."""
    w = FileWatcher()
    w.mark_expected("mount-0", "x.md", "hello")
    assert w.is_expected("mount-0", "x.md", str(tmp_path / "nonexistent.md")) is False


def test_get_watcher_singleton():
    """get_watcher returns the same instance across calls."""
    a = get_watcher()
    b = get_watcher()
    assert a is b
