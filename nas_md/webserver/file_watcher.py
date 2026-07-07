# nas_md/webserver/file_watcher.py
"""File watcher for external modifications on host mounts.

Uses watchdog to observe filesystem events on mount directories. When a file
changes on disk and the content doesn't match what the server itself just wrote
(tracked via mark_expected), an `external_reload` SSE event is broadcast so
connected clients can refresh.

watchdog is an optional dependency — if not available, the watcher is a no-op.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Callable

logger = logging.getLogger(__name__)

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None  # type: ignore
    FileSystemEventHandler = object  # type: ignore


class _MountWatchHandler(FileSystemEventHandler if WATCHDOG_AVAILABLE else object):  # type: ignore[misc]
    """Watchdog event handler for a single mount."""

    def __init__(self, mount_id: str, mount_dir: str, on_change: Callable[[str, str, str], None], watcher: "FileWatcher"):
        super().__init__()
        self._mount_id = mount_id
        self._mount_dir = os.path.abspath(mount_dir)
        self._on_change = on_change
        self._watcher = watcher

    def _is_markdown(self, path: str) -> bool:
        return path.lower().endswith((".md", ".markdown"))

    def on_modified(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        self._handle(event.src_path)

    def on_created(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        self._handle(event.src_path)

    def _handle(self, abs_path: str):
        abs_path = os.path.abspath(abs_path)
        if not self._is_markdown(abs_path):
            return
        # Compute rel_path within mount
        try:
            rel_path = os.path.relpath(abs_path, self._mount_dir).replace(os.sep, "/")
        except ValueError:
            return
        if rel_path.startswith(".."):
            return
        # Normalize to leading slash
        if not rel_path.startswith("/"):
            rel_path = "/" + rel_path
        # Skip if this is the server's own write
        if self._watcher.is_expected(self._mount_id, rel_path, abs_path):
            return
        # Read content (best-effort)
        try:
            with open(abs_path, encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            logger.warning("file_watcher: failed to read %s: %s", abs_path, e)
            return
        logger.info("file_watcher: external change on %s:%s", self._mount_id, rel_path)
        try:
            self._on_change(self._mount_id, rel_path, content)
        except Exception as e:
            logger.error("file_watcher: on_change callback error: %s", e)


class FileWatcher:
    """Manages watchdog observers for all host mounts."""

    def __init__(self):
        self._observers: dict = {}
        self._handlers: dict = {}
        self._expected: dict = {}  # "mount_id:rel_path" -> expected_content
        self._expected_lock = threading.Lock()
        self._lock = threading.Lock()

    def watch_mount(
        self,
        mount_id: str,
        mount_dir: str,
        on_change: Callable[[str, str, str], None],
    ) -> bool:
        """Start watching a mount directory. Returns True if started."""
        if not WATCHDOG_AVAILABLE:
            logger.warning("watchdog not available, skipping %s", mount_id)
            return False
        if not os.path.isdir(mount_dir):
            logger.warning("Mount dir does not exist: %s", mount_dir)
            return False

        with self._lock:
            if mount_id in self._observers:
                return True

            handler = _MountWatchHandler(mount_id, mount_dir, on_change, self)
            observer = Observer()
            observer.schedule(handler, mount_dir, recursive=True)
            observer.start()

            self._observers[mount_id] = observer
            self._handlers[mount_id] = handler
            logger.info("Started watching mount %s at %s", mount_id, mount_dir)
            return True

    def stop_mount(self, mount_id: str):
        """Stop watching a mount."""
        with self._lock:
            observer = self._observers.pop(mount_id, None)
            self._handlers.pop(mount_id, None)
        if observer:
            try:
                observer.stop()
                observer.join(timeout=1.0)
            except Exception as e:
                logger.warning("Error stopping observer for %s: %s", mount_id, e)

    def stop_all(self):
        """Stop all observers."""
        with self._lock:
            ids = list(self._observers.keys())
        for mid in ids:
            self.stop_mount(mid)

    def mark_expected(self, mount_id: str, rel_path: str, content: str):
        """Mark an upcoming server write so watchdog doesn't flag it as external."""
        key = f"{mount_id}:{rel_path}"
        with self._expected_lock:
            self._expected[key] = content

    def is_expected(self, mount_id: str, rel_path: str, abs_path: str) -> bool:
        """Check if the file content matches the expected (server's own) write.

        Pops the mark (one-shot). Returns True if content matches.
        """
        key = f"{mount_id}:{rel_path}"
        with self._expected_lock:
            expected = self._expected.pop(key, None)
        if expected is None:
            return False
        try:
            with open(abs_path, encoding="utf-8") as f:
                actual = f.read()
            return actual == expected
        except OSError:
            return False


_watcher: FileWatcher | None = None
_watcher_lock = threading.Lock()


def get_watcher() -> FileWatcher:
    global _watcher
    if _watcher is None:
        with _watcher_lock:
            if _watcher is None:
                _watcher = FileWatcher()
    return _watcher
