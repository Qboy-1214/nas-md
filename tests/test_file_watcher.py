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
    w.mark_expected("mount-0", "x.md", str(f))
    assert w.is_expected("mount-0", "x.md", str(f)) is True


def test_mark_and_is_expected_mismatch(tmp_path):
    """When disk content differs from marked, is_expected returns False."""
    w = FileWatcher()
    f = tmp_path / "x.md"
    prepared = tmp_path / ".expected.tmp"
    f.write_text("actual", encoding="utf-8")
    prepared.write_text("expected_different", encoding="utf-8")
    w.mark_expected("mount-0", "x.md", str(prepared))
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
    w.mark_expected("mount-0", "x.md", str(f))
    assert w.is_expected("mount-0", "x.md", str(f)) is True
    # Second call: mark already consumed
    assert w.is_expected("mount-0", "x.md", str(f)) is False


def test_is_expected_missing_file(tmp_path):
    """If the file doesn't exist, is_expected returns False."""
    w = FileWatcher()
    prepared = tmp_path / ".prepared.tmp"
    prepared.write_text("hello", encoding="utf-8")
    w.mark_expected("mount-0", "x.md", str(prepared))
    assert w.is_expected("mount-0", "x.md", str(tmp_path / "nonexistent.md")) is False


def test_external_invalid_utf8_is_reported_with_replacement_text(tmp_path):
    watcher = FileWatcher()
    target = tmp_path / "invalid.md"
    target.write_bytes(b"\xff")
    changes = []
    handler = _MountWatchHandler(
        "mount-0", str(tmp_path), lambda *args: changes.append(args), watcher
    )

    handler.on_created(SimpleNamespace(is_directory=False, src_path=str(target)))

    assert changes == [("mount-0", "/invalid.md", "\ufffd")]


def test_get_watcher_singleton():
    """get_watcher returns the same instance across calls."""
    a = get_watcher()
    b = get_watcher()
    assert a is b


def test_mark_expected_fifo_queue_consecutive_saves(tmp_path):
    """Consecutive rapid marks for the same file should be queued in FIFO order."""
    w = FileWatcher()
    f = tmp_path / "rapid.md"
    prepared = []

    # Rapid auto-save 1, 2, 3
    for version in range(1, 4):
        temp = tmp_path / f".rapid-{version}.tmp"
        temp.write_text(f"content v{version}", encoding="utf-8")
        prepared.append(temp)
        w.mark_expected("mount-0", "rapid.md", str(temp))

    # Write v1 and check
    os.replace(prepared[0], f)
    assert w.is_expected("mount-0", "rapid.md", str(f)) is True

    # Write v2 and check
    os.replace(prepared[1], f)
    assert w.is_expected("mount-0", "rapid.md", str(f)) is True

    # Write v3 and check
    os.replace(prepared[2], f)
    assert w.is_expected("mount-0", "rapid.md", str(f)) is True

    # Queue is now empty
    assert w.is_expected("mount-0", "rapid.md", str(f)) is False


def test_unmark_expected_removes_only_the_exact_failed_identical_write(tmp_path):
    """Rolling back one save must preserve an older identical expected event."""
    w = FileWatcher()
    f = tmp_path / "same.md"
    f.write_text("same content", encoding="utf-8")

    older = w.mark_expected("mount-0", "same.md", str(f))
    failed = w.mark_expected("mount-0", "same.md", str(f))

    assert failed is not older
    assert w.unmark_expected(failed) is True
    assert w.is_expected("mount-0", "same.md", str(f)) is True
    assert w.is_expected("mount-0", "same.md", str(f)) is False
    assert w.unmark_expected(older) is False


def test_moved_event_consumes_expected_token_without_suppressing_later_rollback(tmp_path):
    watcher = FileWatcher()
    target = tmp_path / "target.md"
    temp = tmp_path / ".nasmd-write.tmp"
    temp.write_text("saved", encoding="utf-8")
    changes = []
    token = watcher.mark_expected("mount-0", "/target.md", str(temp))
    os.replace(temp, target)
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
    watcher.mark_expected("mount-0", "/same-size.md", str(target))

    handler.on_moved(
        SimpleNamespace(is_directory=False, src_path=str(tmp_path / ".tmp"), dest_path=str(target))
    )
    expected_mtime = target.stat().st_mtime_ns
    target.write_text("BBBB", encoding="utf-8")
    os.utime(target, ns=(expected_mtime, expected_mtime))
    handler.on_modified(SimpleNamespace(is_directory=False, src_path=str(target)))

    assert changes == [("mount-0", "/same-size.md", "BBBB")]


def test_delayed_events_do_not_consume_tokens_for_external_rollback(tmp_path):
    watcher = FileWatcher()
    target = tmp_path / "delayed.md"
    changes = []
    handler = _MountWatchHandler(
        "mount-0", str(tmp_path), lambda *args: changes.append(args), watcher
    )

    temp_a = tmp_path / ".write-a.tmp"
    temp_a.write_text("A", encoding="utf-8")
    token_a = watcher.mark_expected("mount-0", "/delayed.md", str(temp_a))
    os.replace(temp_a, target)

    temp_b = tmp_path / ".write-b.tmp"
    temp_b.write_text("B", encoding="utf-8")
    token_b = watcher.mark_expected("mount-0", "/delayed.md", str(temp_b))
    os.replace(temp_b, target)

    target.write_text("A", encoding="utf-8")
    handler.on_modified(SimpleNamespace(is_directory=False, src_path=str(target)))

    assert changes == [("mount-0", "/delayed.md", "A")]
    assert watcher.unmark_expected(token_a) is True
    assert watcher.unmark_expected(token_b) is True


def test_expected_tokens_store_only_digest_and_fingerprint(tmp_path):
    watcher = FileWatcher()
    prepared = tmp_path / ".prepared.tmp"
    prepared.write_text("sensitive body", encoding="utf-8")

    token = watcher.mark_expected("mount-0", "/secret.md", str(prepared))

    assert not hasattr(token, "content")
    assert "sensitive body" not in repr(token)
    assert token.digest
    assert token.fingerprint.size == len(b"sensitive body")


def test_expected_tokens_expire_with_injected_clock(tmp_path):
    now = [100.0]
    watcher = FileWatcher(monotonic=lambda: now[0], expected_ttl=1.0)
    prepared = tmp_path / ".expired.tmp"
    target = tmp_path / "expired.md"
    prepared.write_text("saved", encoding="utf-8")
    watcher.mark_expected("mount-0", "/expired.md", str(prepared))
    os.replace(prepared, target)

    now[0] += 1.1

    assert watcher.is_expected("mount-0", "/expired.md", str(target)) is False
    assert watcher._expected == {}


def test_expected_tokens_have_global_lru_limit_across_unwatched_paths(tmp_path):
    watcher = FileWatcher(expected_limit=2)
    tokens = []
    for index in range(3):
        prepared = tmp_path / f".prepared-{index}.tmp"
        prepared.write_text(f"body-{index}", encoding="utf-8")
        tokens.append(watcher.mark_expected("mount-0", f"/{index}.md", str(prepared)))

    with watcher._expected_lock:
        assert sum(len(queue) for queue in watcher._expected.values()) == 2
    assert watcher.unmark_expected(tokens[0]) is False
    assert watcher.unmark_expected(tokens[1]) is True
    assert watcher.unmark_expected(tokens[2]) is True


def test_stop_all_clears_expected_and_recent_without_observers(tmp_path):
    watcher = FileWatcher()
    pending = tmp_path / ".pending.tmp"
    consumed = tmp_path / ".consumed.tmp"
    target = tmp_path / "consumed.md"
    pending.write_text("pending", encoding="utf-8")
    consumed.write_text("consumed", encoding="utf-8")
    watcher.mark_expected("mount-0", "/pending.md", str(pending))
    watcher.mark_expected("mount-0", "/consumed.md", str(consumed))
    os.replace(consumed, target)
    assert watcher.is_expected("mount-0", "/consumed.md", str(target)) is True

    watcher.stop_all()

    assert watcher._expected == {}
    assert watcher._recent_expected == {}


def test_duplicate_expected_event_expires_with_injected_clock(tmp_path):
    now = [100.0]
    watcher = FileWatcher(monotonic=lambda: now[0], recent_expected_ttl=1.0)
    target = tmp_path / "expired.md"
    target.write_text("saved", encoding="utf-8")
    changes = []
    handler = _MountWatchHandler(
        "mount-0", str(tmp_path), lambda *args: changes.append(args), watcher
    )
    watcher.mark_expected("mount-0", "/expired.md", str(target))
    handler.on_moved(
        SimpleNamespace(is_directory=False, src_path=str(tmp_path / ".tmp"), dest_path=str(target))
    )

    now[0] += 1.1
    handler.on_modified(SimpleNamespace(is_directory=False, src_path=str(target)))

    assert changes == [("mount-0", "/expired.md", "saved")]


def test_duplicate_check_without_recent_key_does_not_read_file(monkeypatch):
    watcher = FileWatcher()
    monkeypatch.setattr(
        watcher,
        "_read_state",
        lambda _path: pytest.fail("duplicate check must not read without a recent key"),
    )

    assert watcher.is_duplicate_expected_event("mount-0", "/missing.md", "unused") is False


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
        watcher.mark_expected("mount-0", f"/{name}", str(target))
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
        watcher.mark_expected(mount_id, "/target.md", str(target))
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
        temp.write_text("saved", encoding="utf-8")
        token = watcher.mark_expected("mount-0", "/observer.md", str(temp))
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
