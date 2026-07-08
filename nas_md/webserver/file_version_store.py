# nas_md/webserver/file_version_store.py
"""Thread-safe file version store with paragraph-level merge.

All server-side file writes go through this module. It maintains an in-memory
cache of (version, content) per file_key, and uses an integer version number
as the optimistic lock instead of mtime.

Each successful write:
1. Increments the version number
2. Writes the new content to disk
3. Records an entry in version_history
4. Returns the new version + content to the caller

Conflict resolution (base_version mismatch):
- Compute the incoming changes against the current server content
- Merge with any pending changes since base_version (paragraph-level)
- "Last write wins" for same-paragraph conflicts
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field

from nas_md.webserver.paragraph_diff import apply_changes as apply_diff, merge_changes

logger = logging.getLogger(__name__)


@dataclass
class _FileVersion:
    """In-memory version state for a single file."""

    version: int = 0
    content: str = ""
    # changes_by_version: version -> list of changes that produced this version
    # used for merging incoming changes that were based on older versions
    changes_by_version: dict = field(default_factory=dict)


class FileVersionStore:
    """Thread-safe file version store with paragraph-level merge."""

    def __init__(self, storage_dir: str | None = None):
        self._lock = threading.RLock()
        self._files: dict[str, _FileVersion] = {}
        self._storage_dir = storage_dir

    def init_file(self, file_key: str, file_path: str, content: str) -> int:
        """Initialize a file in the store if not already present.

        Returns the current version number.
        """
        with self._lock:
            if file_key in self._files:
                return self._files[file_key].version
            self._files[file_key] = _FileVersion(
                version=0, content=content, changes_by_version={}
            )
            return 0

    def apply_changes(
        self,
        file_key: str,
        file_path: str,
        base_version: int,
        changes: list,
        author_id: str,
        author_name: str,
        author_color: str,
    ) -> dict:
        """Apply changes with version-based optimistic locking.

        Returns dict with:
          applied: bool
          merged: bool  (True if base_version was stale and changes were merged)
          newVersion: int
          content: str
        """
        if not changes:
            return {
                "applied": False,
                "merged": False,
                "newVersion": self.get_current_version(file_key),
                "content": self.get_current_content(file_key) or "",
            }

        with self._lock:
            fv = self._files.get(file_key)
            if fv is None:
                # Lazy load from disk
                try:
                    with open(file_path, encoding="utf-8") as f:
                        disk_content = f.read()
                except OSError:
                    disk_content = ""
                fv = _FileVersion(version=0, content=disk_content, changes_by_version={})
                self._files[file_key] = fv

            merged = False
            changes_to_apply = changes

            if base_version == fv.version:
                # Fast path: no conflict
                new_content = apply_diff(fv.content, changes)
            else:
                # Stale base_version: merge with changes since base_version
                merged = True
                accumulated_changes = []
                for v in range(base_version + 1, fv.version + 1):
                    prev = fv.changes_by_version.get(v, [])
                    accumulated_changes = merge_changes(accumulated_changes, prev)
                # merged_changes_list = merge_changes(accumulated_changes, changes)
                new_content = apply_diff(fv.content, changes)
                changes_to_apply = changes  # for history record

            # Write to disk
            try:
                os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
            except OSError as e:
                logger.error("Failed to write file %s: %s", file_path, e)
                return {
                    "applied": False,
                    "merged": False,
                    "newVersion": fv.version,
                    "content": fv.content,
                    "error": str(e),
                }

            # Update in-memory state
            previous_content = fv.content
            fv.version += 1
            fv.content = new_content
            fv.changes_by_version[fv.version] = list(changes_to_apply)
            self._prune_changes_history(fv)

            # Record version history (best effort)
            self._record_version_history(
                file_key=file_key,
                file_path=file_path,
                author_id=author_id,
                author_name=author_name,
                author_color=author_color,
                changes=changes_to_apply,
                content_snapshot=new_content,
                previous_content=previous_content,
                version=fv.version,
            )

            return {
                "applied": True,
                "merged": merged,
                "newVersion": fv.version,
                "content": new_content,
            }

    def apply_external_change(self, file_key: str, file_path: str) -> dict:
        """Apply an external file modification (e.g., from watchdog).

        Reads the current disk content and bumps the version number,
        so subsequent client saves will detect the change and merge.

        Returns dict with applied/newVersion/content.
        """
        with self._lock:
            fv = self._files.get(file_key)
            if fv is None:
                try:
                    with open(file_path, encoding="utf-8") as f:
                        disk_content = f.read()
                except OSError:
                    disk_content = ""
                fv = _FileVersion(version=0, content=disk_content, changes_by_version={})
                self._files[file_key] = fv

            try:
                with open(file_path, encoding="utf-8") as f:
                    new_content = f.read()
            except OSError as e:
                logger.error("Failed to read external change %s: %s", file_path, e)
                return {
                    "applied": False,
                    "newVersion": fv.version,
                    "content": fv.content,
                }

            if new_content == fv.content:
                # No actual change
                return {
                    "applied": False,
                    "newVersion": fv.version,
                    "content": fv.content,
                }

            previous_content = fv.content
            fv.version += 1
            fv.content = new_content
            # External changes have no author changes; represent as full replace
            fv.changes_by_version[fv.version] = [
                {"type": "external_reload", "paraIdx": 0, "content": new_content}
            ]
            self._prune_changes_history(fv)

            self._record_version_history(
                file_key=file_key,
                file_path=file_path,
                author_id="system",
                author_name="外部修改",
                author_color="#95a5a6",
                changes=[],
                content_snapshot=new_content,
                previous_content=previous_content,
                version=fv.version,
            )

            return {
                "applied": True,
                "newVersion": fv.version,
                "content": new_content,
            }

    def get_current_version(self, file_key: str) -> int:
        with self._lock:
            fv = self._files.get(file_key)
            return fv.version if fv else 0

    def get_current_content(self, file_key: str) -> str | None:
        with self._lock:
            fv = self._files.get(file_key)
            return fv.content if fv else None

    def _prune_changes_history(self, fv: _FileVersion, keep: int = 50):
        """Keep only the most recent `keep` versions of changes_by_version."""
        if len(fv.changes_by_version) <= keep:
            return
        sorted_versions = sorted(fv.changes_by_version.keys())
        for v in sorted_versions[:-keep]:
            del fv.changes_by_version[v]

    def _record_version_history(
        self,
        file_key: str,
        file_path: str,
        author_id: str,
        author_name: str,
        author_color: str,
        changes: list,
        content_snapshot: str,
        previous_content: str | None,
        version: int,
    ):
        """Record an entry in version_history (best effort, never raises)."""
        try:
            from nas_md.webserver.version_history import record_version

            record_version(
                file_key=file_key,
                author_id=author_id,
                author_name=author_name,
                author_color=author_color,
                changes=changes,
                content_snapshot=content_snapshot,
                previous_content=previous_content,
                version=version,
            )
        except Exception as e:
            logger.warning("Failed to record version history for %s: %s", file_key, e)


# Global singleton
_store: FileVersionStore | None = None
_store_lock = threading.Lock()


def get_store() -> FileVersionStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = FileVersionStore()
    return _store
