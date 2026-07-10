"""Version history tracking for collaborative editing.

Stores recent edit snapshots per file key, including timestamp, author
identity, and the diff applied. Persists to disk as JSON files so history
survives server restarts.
"""

import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field

_MAX_HISTORY_PER_FILE = 50
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
_histories: dict[str, FileHistory] = {}


def _safe_filename(file_key: str) -> str:
    """Convert file_key to a safe filename."""
    # Replace path separators and colons
    safe = file_key.replace(":", "_").replace("\\", "_").replace("/", "_")
    # Remove or replace other unsafe chars
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in safe)
    # Truncate to avoid filesystem limits
    if len(safe) > 200:
        safe = safe[:200]
    return safe + ".json"


def _persist(file_key: str, hist: FileHistory):
    """Save history to disk (best-effort, non-blocking on errors)."""
    try:
        os.makedirs(_HISTORY_DIR, exist_ok=True)
        filepath = os.path.join(_HISTORY_DIR, _safe_filename(file_key))
        data = hist.to_dict()
        # Write to temp file then rename for atomicity
        tmp = filepath + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, filepath)
    except Exception:
        pass  # Persistence is best-effort; don't break editing


def _load(file_key: str) -> FileHistory | None:
    """Load history from disk if available."""
    try:
        filepath = os.path.join(_HISTORY_DIR, _safe_filename(file_key))
        if not os.path.exists(filepath):
            return None
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        return FileHistory.from_dict(data)
    except Exception:
        return None


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
) -> VersionEntry:
    """Record a new version for a file.

    If previous_content is provided and the file has no history yet,
    an initial version is recorded first using previous_content as snapshot,
    so the first edit can be diffed against it.
    """
    with _lock:
        if file_key not in _histories:
            # Try loading from disk
            loaded = _load(file_key)
            _histories[file_key] = loaded if loaded else FileHistory()

        # If this is the first version and we have previous content,
        # record the previous content as an initial baseline version
        if not _histories[file_key].versions and previous_content is not None:
            _histories[file_key].add(
                author_id="system",
                author_name="初始版本",
                author_color="#95a5a6",
                changes=[],
                content_snapshot=previous_content,
                version=0,
            )

        entry = _histories[file_key].add(
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
        # Persist to disk
        _persist(file_key, _histories[file_key])
        return entry


def get_history(file_key: str, limit: int = 20) -> list:
    """Get version history for a file, newest first."""
    with _lock:
        hist = _histories.get(file_key)
        if not hist:
            # Try loading from disk
            loaded = _load(file_key)
            if loaded:
                _histories[file_key] = loaded
                hist = loaded
        if not hist:
            return []
        return [
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


def get_version_content(file_key: str, index: int) -> str | None:
    """Get full content of a specific version (0 = newest)."""
    with _lock:
        hist = _histories.get(file_key)
        if not hist:
            loaded = _load(file_key)
            if loaded:
                _histories[file_key] = loaded
                hist = loaded
        if not hist:
            return None
        v = hist.get(index)
        return v.content_snapshot if v else None


def get_version_with_previous(file_key: str, index: int) -> dict | None:
    """Get version content and the previous version's content for diff.

    Returns {"content": str, "previousContent": str or None}.
    index 0 = newest. previousContent is from index+1 (older).
    """
    with _lock:
        hist = _histories.get(file_key)
        if not hist:
            loaded = _load(file_key)
            if loaded:
                _histories[file_key] = loaded
                hist = loaded
        if not hist:
            return None
        v = hist.get(index)
        if not v:
            return None
        # Get previous (older) version for diff comparison
        prev = hist.get(index + 1) if index + 1 < len(list(hist.versions)) else None
        return {
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
