"""Version history tracking for collaborative editing.

Stores recent edit snapshots per file key, including timestamp, author
identity, and the diff applied. Persists to disk as JSON files so history
survives server restarts.
"""

import contextlib
import json
import os
import threading
import time
import weakref
from collections import OrderedDict, deque
from dataclasses import dataclass, field

_MAX_HISTORY_PER_FILE = 50
_MAX_CACHE_FILES = 200
_HISTORY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "storage",
    ".version_history",
)


@dataclass
class VersionEntry:
    """A single version snapshot."""

    version: int  # monotonic version number from FileVersionStore
    timestamp: float
    author_id: str
    author_name: str
    author_color: str
    changes: list  # list of diff change dicts
    content_snapshot: str  # full content after this edit
    client_ip: str = ""
    client_os: str = ""
    client_browser: str = ""
    user_agent: str = ""


@dataclass
class FileHistory:
    """Version history for a single file."""

    versions: deque = field(default_factory=lambda: deque(maxlen=_MAX_HISTORY_PER_FILE))

    def add(
        self,
        author_id: str,
        author_name: str,
        author_color: str,
        changes: list,
        content_snapshot: str,
        version: int = 0,
        client_ip: str = "",
        client_os: str = "",
        client_browser: str = "",
        user_agent: str = "",
    ) -> VersionEntry:
        entry = VersionEntry(
            version=version,
            timestamp=time.time(),
            author_id=author_id,
            author_name=author_name,
            author_color=author_color,
            changes=changes,
            content_snapshot=content_snapshot,
            client_ip=client_ip,
            client_os=client_os,
            client_browser=client_browser,
            user_agent=user_agent,
        )
        self.versions.append(entry)
        return entry

    def list(self, limit: int = 20) -> list:
        """Return recent versions, newest first."""
        items = list(self.versions)
        items.reverse()
        return items[:limit]

    def get(self, index: int) -> VersionEntry | None:
        """Get a specific version by index (0 = newest)."""
        items = list(self.versions)
        items.reverse()
        if 0 <= index < len(items):
            return items[index]
        return None

    def to_dict(self) -> dict:
        """Serialize for disk persistence."""
        return {
            "versions": [
                {
                    "version": v.version,
                    "timestamp": v.timestamp,
                    "author_id": v.author_id,
                    "author_name": v.author_name,
                    "author_color": v.author_color,
                    "changes": v.changes,
                    "content_snapshot": v.content_snapshot,
                    "client_ip": v.client_ip,
                    "client_os": v.client_os,
                    "client_browser": v.client_browser,
                    "user_agent": v.user_agent,
                }
                for v in self.versions
            ]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FileHistory":
        """Deserialize from disk."""
        fh = cls()
        for v in data.get("versions", []):
            entry = VersionEntry(
                version=v.get("version", 0),
                timestamp=v["timestamp"],
                author_id=v["author_id"],
                author_name=v["author_name"],
                author_color=v["author_color"],
                changes=v["changes"],
                content_snapshot=v["content_snapshot"],
                client_ip=v.get("client_ip", ""),
                client_os=v.get("client_os", ""),
                client_browser=v.get("client_browser", ""),
                user_agent=v.get("user_agent", ""),
            )
            fh.versions.append(entry)
        return fh


_lock = threading.Lock()
_histories: OrderedDict[str, FileHistory] = OrderedDict()
_history_locks = weakref.WeakValueDictionary()


def _history_lock_for(file_key: str) -> threading.RLock:
    """Return the stable per-key lock shared by concurrent history operations."""
    with _lock:
        file_lock = _history_locks.get(file_key)
        if file_lock is None:
            file_lock = threading.RLock()
            _history_locks[file_key] = file_lock
        return file_lock


def _safe_filename(file_key: str) -> str:
    """Convert file_key to a safe filename with SHA-256 digest to prevent collision/overflow."""
    import hashlib

    key_hash = hashlib.sha256(file_key.encode("utf-8")).hexdigest()[:16]
    safe_prefix = "".join(c if c.isalnum() or c in "._-" else "_" for c in file_key)[:40]
    return f"{safe_prefix}_{key_hash}.json"


def _safe_filename_legacy(file_key: str) -> str:
    """Legacy filename format for backwards compatibility."""
    safe = file_key.replace(":", "_").replace("\\", "_").replace("/", "_")
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in safe)
    if len(safe) > 200:
        safe = safe[:200]
    return safe + ".json"


def _persist(file_key: str, hist: FileHistory, storage_dir: str | None = None):
    """Save history to disk (best-effort, non-blocking on errors)."""
    file_lock = _history_lock_for(file_key)
    with file_lock:
        try:
            target_dir = storage_dir or _HISTORY_DIR
            os.makedirs(target_dir, exist_ok=True)
            filepath = os.path.join(target_dir, _safe_filename(file_key))
            data = hist.to_dict()
            tmp = filepath + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, filepath)

            # Clean up legacy unhashed file if it exists
            legacy_path = os.path.join(target_dir, _safe_filename_legacy(file_key))
            if legacy_path != filepath and os.path.exists(legacy_path):
                with contextlib.suppress(OSError):
                    os.remove(legacy_path)
        except Exception:
            pass


def _load(file_key: str, storage_dir: str | None = None) -> FileHistory | None:
    """Load history from disk if available."""
    file_lock = _history_lock_for(file_key)
    with file_lock:
        try:
            target_dir = storage_dir or _HISTORY_DIR
            filepath = os.path.join(target_dir, _safe_filename(file_key))
            if not os.path.exists(filepath):
                # Check legacy filename
                legacy_path = os.path.join(target_dir, _safe_filename_legacy(file_key))
                if os.path.exists(legacy_path):
                    filepath = legacy_path
                else:
                    return None

            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            return FileHistory.from_dict(data)
        except Exception:
            return None


def _evict_lru_if_needed():
    """Evict least-recently used FileHistory if cache exceeds _MAX_CACHE_FILES."""
    while len(_histories) > _MAX_CACHE_FILES:
        _histories.popitem(last=False)


def _cache_history(file_key: str, hist: FileHistory) -> None:
    """Insert or touch one cache entry while holding the registry lock briefly."""
    with _lock:
        _histories[file_key] = hist
        _histories.move_to_end(file_key)
        _evict_lru_if_needed()


def _get_or_load_history(
    file_key: str, storage_dir: str | None, *, create: bool
) -> FileHistory | None:
    """Get one history while the caller holds its per-key lock."""
    with _lock:
        hist = _histories.get(file_key)
        if hist is not None:
            _histories.move_to_end(file_key)
            return hist

    hist = _load(file_key, storage_dir=storage_dir)
    if hist is None:
        if not create:
            return None
        hist = FileHistory()
    _cache_history(file_key, hist)
    return hist


def record_version(
    file_key: str,
    author_id: str,
    author_name: str,
    author_color: str,
    changes: list,
    content_snapshot: str,
    previous_content: str | None = None,
    version: int = 0,
    client_ip: str = "",
    client_os: str = "",
    client_browser: str = "",
    user_agent: str = "",
    storage_dir: str | None = None,
) -> VersionEntry:
    """Record a new version for a file."""
    file_lock = _history_lock_for(file_key)
    with file_lock:
        hist = _get_or_load_history(file_key, storage_dir, create=True)
        assert hist is not None

        if not hist.versions and previous_content is not None:
            hist.add(
                author_id="system",
                author_name="初始版本",
                author_color="#95a5a6",
                changes=[],
                content_snapshot=previous_content,
                version=0,
            )

        entry = hist.add(
            author_id,
            author_name,
            author_color,
            changes,
            content_snapshot,
            version=version,
            client_ip=client_ip,
            client_os=client_os,
            client_browser=client_browser,
            user_agent=user_agent,
        )
        _persist(file_key, hist, storage_dir=storage_dir)
        _cache_history(file_key, hist)
        return entry


def get_history(file_key: str, limit: int = 20, storage_dir: str | None = None) -> list:
    """Get version history for a file, newest first."""
    file_lock = _history_lock_for(file_key)
    with file_lock:
        hist = _get_or_load_history(file_key, storage_dir, create=False)
        if not hist:
            return []
        result = [
            {
                "version": v.version,
                "timestamp": v.timestamp,
                "authorId": v.author_id,
                "authorName": v.author_name,
                "authorColor": v.author_color,
                "changes": v.changes,
                "contentLength": len(v.content_snapshot),
                "clientIp": v.client_ip,
                "clientOs": v.client_os,
                "clientBrowser": v.client_browser,
            }
            for v in hist.list(limit)
        ]
        _cache_history(file_key, hist)
        return result


def get_version_content(file_key: str, index: int) -> str | None:
    """Get full content of a specific version (0 = newest)."""
    file_lock = _history_lock_for(file_key)
    with file_lock:
        hist = _get_or_load_history(file_key, None, create=False)
        if not hist:
            return None
        v = hist.get(index)
        _cache_history(file_key, hist)
        return v.content_snapshot if v else None


def get_version_with_previous(file_key: str, index: int) -> dict | None:
    """Get version content and the previous version's content for diff.

    Returns {"content": str, "previousContent": str or None}.
    index 0 = newest. previousContent is from index+1 (older).
    """
    file_lock = _history_lock_for(file_key)
    with file_lock:
        hist = _get_or_load_history(file_key, None, create=False)
        if not hist:
            return None
        v = hist.get(index)
        if not v:
            return None
        # Get previous (older) version for diff comparison
        prev = hist.get(index + 1) if index + 1 < len(list(hist.versions)) else None
        result = {
            "content": v.content_snapshot,
            "previousContent": prev.content_snapshot if prev else None,
            "version": v.version,
            "timestamp": v.timestamp,
            "authorName": v.author_name,
            "authorColor": v.author_color,
            "clientIp": v.client_ip,
            "clientOs": v.client_os,
            "clientBrowser": v.client_browser,
        }
        _cache_history(file_key, hist)
        return result
