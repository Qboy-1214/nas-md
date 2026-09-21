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
- Validate the declared changes against the client's submitted base content
- Compute both client and server changes from that common ancestor
- Transform the client changes over the server changes (paragraph-level)
- "Last write wins" for same-paragraph conflicts
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from nas_md.webserver.paragraph_diff import (
    DiffWorkLimitExceeded,
    apply_changes as apply_diff,
    compute_diff,
    split_paragraphs,
    transform_changes,
    validate_changes,
)

logger = logging.getLogger(__name__)


@dataclass
class _FileVersion:
    """In-memory version state for a single file."""

    version: int = 0
    content: str = ""
    # changes_by_version: version -> list of changes that produced this version
    # retained as a bounded record; stale merging uses submitted base content
    changes_by_version: dict = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)


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
            fv = self._files.get(file_key)
        if fv is not None:
            with fv.lock:
                return fv.version

        # Check if there is existing persisted history to maintain version monotonicity
        base_version = 0
        try:
            from nas_md.webserver.version_history import _load

            hist = _load(file_key, storage_dir=self._storage_dir)
            if hist and hist.versions:
                base_version = max((v.version for v in hist.versions), default=0)
        except Exception:
            base_version = 0

        candidate = _FileVersion(version=base_version, content=content, changes_by_version={})
        with self._lock:
            fv = self._files.setdefault(file_key, candidate)
        with fv.lock:
            return fv.version

    def _get_or_load_file(self, file_key: str, file_path: str) -> _FileVersion:
        with self._lock:
            fv = self._files.get(file_key)
        if fv is not None:
            return fv

        try:
            with open(file_path, encoding="utf-8") as f:
                disk_content = f.read()
        except OSError:
            disk_content = ""
        candidate = _FileVersion(version=0, content=disk_content, changes_by_version={})
        with self._lock:
            return self._files.setdefault(file_key, candidate)

    def apply_changes(
        self,
        file_key: str,
        file_path: str,
        base_version: int,
        changes: list,
        author_id: str,
        author_name: str,
        author_color: str,
        client_ip: str = "",
        client_os: str = "",
        client_browser: str = "",
        user_agent: str = "",
        client_content: str | None = None,
        base_content: str | None = None,
        before_write: Callable[[str], None] | None = None,
    ) -> dict:
        """Apply changes with version-based optimistic locking.

        Returns dict with:
          applied: bool
          merged: bool  (True if base_version was stale and changes were merged)
          newVersion: int
          content: str
        """
        fv = self._get_or_load_file(file_key, file_path)
        with fv.lock:
            if base_version < 0 or base_version > fv.version:
                return self._resync_result(fv)

            submitted_base = base_content
            if submitted_base is None and base_version == fv.version:
                submitted_base = fv.content
            if submitted_base is None:
                return self._resync_result(fv)
            if not isinstance(submitted_base, str):
                raise TypeError("baseContent must be a string")

            validate_changes(changes, len(split_paragraphs(submitted_base)))
            reconstructed_content = apply_diff(submitted_base, changes)

            submitted_content = client_content
            if submitted_content is None:
                submitted_content = reconstructed_content
            else:
                if not isinstance(submitted_content, str):
                    raise TypeError("content must be a string")
                if split_paragraphs(reconstructed_content) != split_paragraphs(submitted_content):
                    return self._resync_result(fv)
                if reconstructed_content != submitted_content:
                    # Legacy clients sent full content whose incidental whitespace could
                    # overwrite newer server formatting. Their declared operations are
                    # the authoritative compatible representation.
                    submitted_content = reconstructed_content

            try:
                canonical_changes = compute_diff(submitted_base, submitted_content)
            except DiffWorkLimitExceeded:
                return self._resync_result(fv)
            merged = base_version != fv.version
            if not merged and submitted_base != fv.content:
                return self._resync_result(fv)
            if not canonical_changes:
                return {
                    "applied": False,
                    "merged": False,
                    "newVersion": fv.version,
                    "content": fv.content,
                }

            if not merged:
                changes_to_apply = canonical_changes
                new_content = submitted_content
            else:
                try:
                    remote_changes = compute_diff(submitted_base, fv.content)
                except DiffWorkLimitExceeded:
                    return self._resync_result(fv)
                changes_to_apply = transform_changes(
                    canonical_changes,
                    remote_changes,
                    len(split_paragraphs(submitted_base)),
                )
                new_content = apply_diff(fv.content, changes_to_apply)

            if not changes_to_apply or new_content == fv.content:
                return {
                    "applied": False,
                    "merged": False,
                    "newVersion": fv.version,
                    "content": fv.content,
                }

            # Write to disk
            try:
                if before_write is not None:
                    before_write(new_content)
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
                client_ip=client_ip,
                client_os=client_os,
                client_browser=client_browser,
                user_agent=user_agent,
            )

            return {
                "applied": True,
                "merged": merged,
                "newVersion": fv.version,
                "content": new_content,
                "appliedChanges": changes_to_apply,
            }

    @staticmethod
    def _resync_result(fv: _FileVersion) -> dict:
        return {
            "applied": False,
            "merged": False,
            "resyncRequired": True,
            "newVersion": fv.version,
            "content": fv.content,
        }

    def apply_external_change(self, file_key: str, file_path: str) -> dict:
        """Apply an external file modification (e.g., from watchdog).

        Reads the current disk content and bumps the version number,
        so subsequent client saves will detect the change and merge.

        Returns dict with applied/newVersion/content.
        """
        fv = self._get_or_load_file(file_key, file_path)
        with fv.lock:
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
        if fv is None:
            return 0
        with fv.lock:
            return fv.version

    def get_current_content(self, file_key: str) -> str | None:
        with self._lock:
            fv = self._files.get(file_key)
        if fv is None:
            return None
        with fv.lock:
            return fv.content

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
        client_ip: str = "",
        client_os: str = "",
        client_browser: str = "",
        user_agent: str = "",
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
                client_ip=client_ip,
                client_os=client_os,
                client_browser=client_browser,
                user_agent=user_agent,
                storage_dir=self._storage_dir,
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
