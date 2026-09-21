# tests/test_file_watcher.py
"""Tests for file_watcher module.

Avoids depending on real watchdog observers (which require filesystem events
and threads). Tests only the mark_expected / is_expected logic and the
singleton accessor.
"""

import os
import time
from types import SimpleNamespace

import pytest
from nas_md.webserver.file_watcher import (
    WATCHDOG_AVAILABLE,
    FileWatcher,
    _MountWatchHandler,
    get_watcher,
)


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


def test_mark_expected_fifo_queue_consecutive_saves(tmp_path):
    """Consecutive rapid marks for the same file should be queued in FIFO order."""
    w = FileWatcher()
    f = tmp_path / "rapid.md"

    # Rapid auto-save 1, 2, 3
    w.mark_expected("mount-0", "rapid.md", "content v1")
    w.mark_expected("mount-0", "rapid.md", "content v2")
    w.mark_expected("mount-0", "rapid.md", "content v3")

    # Write v1 and check
    f.write_text("content v1", encoding="utf-8")
    assert w.is_expected("mount-0", "rapid.md", str(f)) is True

    # Write v2 and check
    f.write_text("content v2", encoding="utf-8")
    assert w.is_expected("mount-0", "rapid.md", str(f)) is True

    # Write v3 and check
    f.write_text("content v3", encoding="utf-8")
    assert w.is_expected("mount-0", "rapid.md", str(f)) is True

    # Queue is now empty
    assert w.is_expected("mount-0", "rapid.md", str(f)) is False


def test_unmark_expected_removes_only_the_exact_failed_identical_write(tmp_path):
    """Rolling back one save must preserve an older identical expected event."""
    w = FileWatcher()
    f = tmp_path / "same.md"
    f.write_text("same content", encoding="utf-8")

    older = w.mark_expected("mount-0", "same.md", "same content")
    failed = w.mark_expected("mount-0", "same.md", "same content")

    assert failed is not older
    assert w.unmark_expected(failed) is True
    assert w.is_expected("mount-0", "same.md", str(f)) is True
    assert w.is_expected("mount-0", "same.md", str(f)) is False
    assert w.unmark_expected(older) is False


def test_moved_event_consumes_expected_token_without_suppressing_later_rollback(tmp_path):
    watcher = FileWatcher()
    target = tmp_path / "target.md"
    temp = tmp_path / ".nasmd-write.tmp"
    target.write_text("saved", encoding="utf-8")
    changes = []
    token = watcher.mark_expected("mount-0", "/target.md", "saved")
    handler = _MountWatchHandler(
        "mount-0", str(tmp_path), lambda *args: changes.append(args), watcher
    )

    handler.on_moved(SimpleNamespace(is_directory=False, src_path=str(temp), dest_path=str(target)))

    assert changes == []
    assert watcher.unmark_expected(token) is False

    previous_mtime = target.stat().st_mtime_ns
    target.write_text("saved", encoding="utf-8")
    os.utime(target, ns=(previous_mtime + 1_000_000, previous_mtime + 1_000_000))
    handler.on_modified(SimpleNamespace(is_directory=False, src_path=str(target)))
    assert changes == [("mount-0", "/target.md", "saved")]


def test_same_fingerprint_with_different_content_is_not_suppressed(tmp_path):
    watcher = FileWatcher()
    target = tmp_path / "same-size.md"
    target.write_text("AAAA", encoding="utf-8")
    changes = []
    handler = _MountWatchHandler(
        "mount-0", str(tmp_path), lambda *args: changes.append(args), watcher
    )
    watcher.mark_expected("mount-0", "/same-size.md", "AAAA")

    handler.on_moved(
        SimpleNamespace(is_directory=False, src_path=str(tmp_path / ".tmp"), dest_path=str(target))
    )
    expected_mtime = target.stat().st_mtime_ns
    target.write_text("BBBB", encoding="utf-8")
    os.utime(target, ns=(expected_mtime, expected_mtime))
    handler.on_modified(SimpleNamespace(is_directory=False, src_path=str(target)))

    assert changes == [("mount-0", "/same-size.md", "BBBB")]


def test_duplicate_expected_event_expires_with_injected_clock(tmp_path):
    now = [100.0]
    watcher = FileWatcher(monotonic=lambda: now[0], recent_expected_ttl=1.0)
    target = tmp_path / "expired.md"
    target.write_text("saved", encoding="utf-8")
    changes = []
    handler = _MountWatchHandler(
        "mount-0", str(tmp_path), lambda *args: changes.append(args), watcher
    )
    watcher.mark_expected("mount-0", "/expired.md", "saved")
    handler.on_moved(
        SimpleNamespace(is_directory=False, src_path=str(tmp_path / ".tmp"), dest_path=str(target))
    )

    now[0] += 1.1
    handler.on_modified(SimpleNamespace(is_directory=False, src_path=str(target)))

    assert changes == [("mount-0", "/expired.md", "saved")]


def test_recent_expected_events_evict_least_recently_used_entry(tmp_path):
    watcher = FileWatcher(recent_expected_limit=2)
    changes = []
    handler = _MountWatchHandler(
        "mount-0", str(tmp_path), lambda *args: changes.append(args), watcher
    )
    targets = []
    for name in ("first.md", "second.md", "third.md"):
        target = tmp_path / name
        target.write_text(name, encoding="utf-8")
        targets.append(target)
        watcher.mark_expected("mount-0", f"/{name}", name)
        handler.on_moved(
            SimpleNamespace(
                is_directory=False,
                src_path=str(tmp_path / f".{name}.tmp"),
                dest_path=str(target),
            )
        )

    for target in targets:
        handler.on_modified(SimpleNamespace(is_directory=False, src_path=str(target)))

    assert changes == [("mount-0", "/first.md", "first.md")]


def test_stop_mount_clears_only_that_mounts_recent_expected_events(tmp_path):
    watcher = FileWatcher()
    changes = []
    handlers = {}
    targets = {}
    for mount_id in ("mount-a", "mount-b"):
        mount_dir = tmp_path / mount_id
        mount_dir.mkdir()
        target = mount_dir / "target.md"
        target.write_text("saved", encoding="utf-8")
        targets[mount_id] = target
        handlers[mount_id] = _MountWatchHandler(
            mount_id, str(mount_dir), lambda *args: changes.append(args), watcher
        )
        watcher.mark_expected(mount_id, "/target.md", "saved")
        handlers[mount_id].on_moved(
            SimpleNamespace(
                is_directory=False,
                src_path=str(mount_dir / ".tmp"),
                dest_path=str(target),
            )
        )

    watcher.stop_mount("mount-a")
    handlers["mount-a"].on_modified(
        SimpleNamespace(is_directory=False, src_path=str(targets["mount-a"]))
    )
    handlers["mount-b"].on_modified(
        SimpleNamespace(is_directory=False, src_path=str(targets["mount-b"]))
    )

    assert changes == [("mount-a", "/target.md", "saved")]


@pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog is not installed")
def test_real_observer_consumes_atomic_move_then_reports_external_rollback(tmp_path):
    watcher = FileWatcher()
    target = tmp_path / "observer.md"
    temp = tmp_path / ".nasmd-observer.tmp"
    target.write_text("before", encoding="utf-8")
    changes = []

    def on_change(*args):
        changes.append(args)

    assert watcher.watch_mount("mount-0", str(tmp_path), on_change) is True
    try:
        token = watcher.mark_expected("mount-0", "/observer.md", "saved")
        temp.write_text("saved", encoding="utf-8")
        os.replace(temp, target)

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with watcher._expected_lock:
                pending = any(
                    item is token for item in watcher._expected.get("mount-0:/observer.md", ())
                )
            if not pending:
                break
            time.sleep(0.01)
        assert pending is False
        assert changes == []

        target.write_text("before", encoding="utf-8")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not any(event[2] == "before" for event in changes):
            time.sleep(0.01)
        assert any(event == ("mount-0", "/observer.md", "before") for event in changes)
    finally:
        watcher.stop_all()
