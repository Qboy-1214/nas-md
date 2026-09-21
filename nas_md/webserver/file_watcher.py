# nas_md/webserver/file_watcher.py
"""File watcher for external modifications on host mounts.

Uses watchdog to observe filesystem events on mount directories. When a file
changes on disk and the content doesn't match what the server itself just wrote
(tracked via mark_expected), an `external_reload` SSE event is broadcast so
connected clients can refresh.

watchdog is an optional dependency — if not available, the watcher is a no-op.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass

try:
    from typing import TYPE_CHECKING
except ImportError:
    TYPE_CHECKING = False

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True, eq=False)
class _ExpectedWriteToken:
    """Opaque identity for one expected watcher event."""

    key: str
    fingerprint: _FileFingerprint
    digest: bytes
    expires_at: float


@dataclass(frozen=True)
class _FileFingerprint:
    """Filesystem identity for suppressing duplicate events from one write."""

    device: int
    inode: int
    size: int
    modified_ns: int


@dataclass(frozen=True)
class _RecentExpectedWrite:
    """Content and filesystem identity for a short duplicate-event window."""

    fingerprint: _FileFingerprint
    digest: bytes
    expires_at: float


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

    def __init__(
        self,
        mount_id: str,
        mount_dir: str,
        on_change: Callable[[str, str, str], None],
        watcher: FileWatcher,
    ):
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

    def on_moved(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        destination = getattr(event, "dest_path", None)
        if not destination or not os.path.exists(destination):
            return
        self._handle(destination)

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
        # Atomic replacement can emit both moved and modified. Check the last
        # consumed fingerprint first so a duplicate cannot consume a token for
        # a later save.
        if self._watcher.is_duplicate_expected_event(self._mount_id, rel_path, abs_path):
            return
        # Skip if this is the server's own write.
        if self._watcher.is_expected(self._mount_id, rel_path, abs_path):
            return
        # Read content (best-effort)
        try:
            with open(abs_path, encoding="utf-8", errors="replace") as f:
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

    def __init__(
        self,
        *,
        monotonic: Callable[[], float] | None = None,
        expected_ttl: float = 30.0,
        expected_limit: int = 1024,
        recent_expected_ttl: float = 2.0,
        recent_expected_limit: int = 1024,
    ):
        if expected_ttl < 0:
            raise ValueError("expected_ttl must be non-negative")
        if expected_limit < 1:
            raise ValueError("expected_limit must be positive")
        if recent_expected_ttl < 0:
            raise ValueError("recent_expected_ttl must be non-negative")
        if recent_expected_limit < 1:
            raise ValueError("recent_expected_limit must be positive")
        self._observers: dict = {}
        self._handlers: dict = {}
        self._expected: dict[str, deque[_ExpectedWriteToken]] = {}
        self._expected_order: OrderedDict[_ExpectedWriteToken, None] = OrderedDict()
        self._recent_expected: OrderedDict[str, _RecentExpectedWrite] = OrderedDict()
        self._monotonic = monotonic or time.monotonic
        self._expected_ttl = expected_ttl
        self._expected_limit = expected_limit
        self._recent_expected_ttl = recent_expected_ttl
        self._recent_expected_limit = recent_expected_limit
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
        key_prefix = f"{mount_id}:"
        with self._expected_lock:
            for key in [key for key in self._expected if key.startswith(key_prefix)]:
                for token in self._expected.pop(key):
                    self._expected_order.pop(token, None)
            for key in [key for key in self._recent_expected if key.startswith(key_prefix)]:
                self._recent_expected.pop(key, None)

    def stop_all(self):
        """Stop all observers."""
        with self._lock:
            ids = list(self._observers.keys())
        for mid in ids:
            self.stop_mount(mid)
        with self._expected_lock:
            self._expected.clear()
            self._expected_order.clear()
            self._recent_expected.clear()

    def mark_expected(self, mount_id: str, rel_path: str, abs_path: str) -> _ExpectedWriteToken:
        """Mark an upcoming server write so watchdog doesn't flag it as external."""
        key = f"{mount_id}:{rel_path}"
        _content, fingerprint, digest = self._read_state(abs_path)
        now = self._monotonic()
        token = _ExpectedWriteToken(
            key=key,
            fingerprint=fingerprint,
            digest=digest,
            expires_at=now + self._expected_ttl,
        )
        with self._expected_lock:
            self._prune_expected(now)
            if key not in self._expected:
                self._expected[key] = deque()
            self._expected[key].append(token)
            self._expected_order[token] = None
            while len(self._expected_order) > self._expected_limit:
                oldest = next(iter(self._expected_order))
                self._discard_expected(oldest)
        return token

    def unmark_expected(self, token: _ExpectedWriteToken) -> bool:
        """Remove only the mark represented by ``token`` after a failed write."""
        if not isinstance(token, _ExpectedWriteToken):
            return False
        with self._expected_lock:
            return self._discard_expected(token)

    def is_expected(self, mount_id: str, rel_path: str, abs_path: str) -> bool:
        """Check if the file content matches any expected (server's own) write.

        Pops the matching mark from FIFO queue. Returns True if content matches.
        """
        key = f"{mount_id}:{rel_path}"
        now = self._monotonic()
        with self._expected_lock:
            self._prune_expected(now)
            q = self._expected.get(key)
            if not q:
                return False

        try:
            _actual, fingerprint, digest = self._read_state(abs_path)
        except OSError:
            return False

        with self._expected_lock:
            self._prune_expected(self._monotonic())
            q = self._expected.get(key)
            if not q:
                return False

            matching = next(
                (mark for mark in q if mark.fingerprint == fingerprint and mark.digest == digest),
                None,
            )
            if matching is not None:
                # Remove up to and including the matched item
                while q:
                    mark = q.popleft()
                    self._expected_order.pop(mark, None)
                    if mark is matching:
                        break
                if not q:
                    self._expected.pop(key, None)
                now = self._monotonic()
                self._prune_recent_expected(now)
                self._recent_expected[key] = _RecentExpectedWrite(
                    fingerprint=fingerprint,
                    digest=digest,
                    expires_at=now + self._recent_expected_ttl,
                )
                self._recent_expected.move_to_end(key)
                while len(self._recent_expected) > self._recent_expected_limit:
                    self._recent_expected.popitem(last=False)
                return True
            return False

    def is_duplicate_expected_event(self, mount_id: str, rel_path: str, abs_path: str) -> bool:
        """Return True while an event still describes the last expected write."""
        key = f"{mount_id}:{rel_path}"
        now = self._monotonic()
        with self._expected_lock:
            self._prune_recent_expected(now)
            if key not in self._recent_expected:
                return False

        try:
            _content, fingerprint, digest = self._read_state(abs_path)
        except OSError:
            return False

        with self._expected_lock:
            self._prune_recent_expected(self._monotonic())
            expected = self._recent_expected.get(key)
            if (
                expected is not None
                and expected.fingerprint == fingerprint
                and expected.digest == digest
            ):
                self._recent_expected.move_to_end(key)
                return True
            if expected is not None:
                self._recent_expected.pop(key, None)
            return False

    def _discard_expected(self, token: _ExpectedWriteToken) -> bool:
        q = self._expected.get(token.key)
        if not q:
            return False
        for index, item in enumerate(q):
            if item is token:
                del q[index]
                self._expected_order.pop(token, None)
                if not q:
                    self._expected.pop(token.key, None)
                return True
        return False

    def _prune_expected(self, now: float) -> None:
        for token in [token for token in self._expected_order if token.expires_at <= now]:
            self._discard_expected(token)

    def _prune_recent_expected(self, now: float) -> None:
        for key in [key for key, item in self._recent_expected.items() if item.expires_at <= now]:
            self._recent_expected.pop(key, None)

    @staticmethod
    def _read_state(abs_path: str) -> tuple[str, _FileFingerprint, bytes]:
        with open(abs_path, "rb") as f:
            raw_content = f.read()
            fingerprint = FileWatcher._fingerprint_from_stat(os.fstat(f.fileno()))
        content = raw_content.decode("utf-8", errors="replace")
        digest = hashlib.sha256(raw_content).digest()
        return content, fingerprint, digest

    @staticmethod
    def _fingerprint_from_stat(stat_result: os.stat_result) -> _FileFingerprint:
        return _FileFingerprint(
            device=stat_result.st_dev,
            inode=stat_result.st_ino,
            size=stat_result.st_size,
            modified_ns=stat_result.st_mtime_ns,
        )


_watcher: FileWatcher | None = None
_watcher_lock = threading.Lock()


def get_watcher() -> FileWatcher:
    global _watcher
    if _watcher is None:
        with _watcher_lock:
            if _watcher is None:
                _watcher = FileWatcher()
    return _watcher
