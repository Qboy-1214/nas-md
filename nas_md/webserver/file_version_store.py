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

import contextlib
import hashlib
import io
import logging
import os
import secrets
import stat
import sys
import threading
from collections.abc import Callable, Iterator
from contextvars import ContextVar
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

_ATOMIC_TEMP_ATTEMPTS = 10


def _create_atomic_temp(
    directory: str, *, mode: int = 0o600, prefix: str = ".nasmd-"
) -> tuple[int, str]:
    """Exclusively create a short, same-directory temporary file."""
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    for _ in range(_ATOMIC_TEMP_ATTEMPTS):
        temp_path = os.path.join(directory, f"{prefix}{secrets.token_hex(8)}.tmp")
        try:
            return os.open(temp_path, flags, mode), temp_path
        except FileExistsError:
            continue
        except PermissionError:
            if os.path.isdir(temp_path):
                continue
            raise
    raise FileExistsError("unable to allocate atomic write temporary file")


def _probe_new_file_mode(directory: str) -> int:
    """Ask the kernel for the directory's umask/default-ACL-derived mode."""
    fd, probe_path = _create_atomic_temp(directory, mode=0o666, prefix=".nasmd-perm-")
    try:
        return stat.S_IMODE(os.fstat(fd).st_mode)
    finally:
        try:
            os.close(fd)
        finally:
            os.remove(probe_path)


def _snapshot_xattrs(file_path: str) -> tuple[tuple[str | bytes, bytes], ...]:
    """Read every extended attribute or fail before replacing the target."""
    listxattr = getattr(os, "listxattr", None)
    getxattr = getattr(os, "getxattr", None)
    if listxattr is None or getxattr is None:
        return ()
    names = listxattr(file_path, follow_symlinks=False)
    return tuple((name, getxattr(file_path, name, follow_symlinks=False)) for name in names)


def _apply_xattrs(fd: int, attributes: tuple[tuple[str | bytes, bytes], ...]) -> None:
    """Apply a complete extended-attribute snapshot to an open temp file."""
    if not attributes:
        return
    setxattr = getattr(os, "setxattr", None)
    if setxattr is None:
        raise OSError("extended attributes cannot be preserved on this platform")
    for name, value in attributes:
        setxattr(fd, name, value)


def _copy_file_windows(source_path: str, destination_path: str) -> None:
    """Copy a Windows file and all of its streams and security metadata."""
    import ctypes
    from ctypes import wintypes

    copy_file = ctypes.WinDLL("kernel32", use_last_error=True).CopyFileW
    copy_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.BOOL,
    )
    copy_file.restype = wintypes.BOOL
    if not copy_file(source_path, destination_path, True):
        error_code = ctypes.get_last_error()
        if error_code in (80, 183):
            raise FileExistsError(error_code, ctypes.FormatError(error_code), destination_path)
        if error_code == 5:
            raise PermissionError(error_code, ctypes.FormatError(error_code), destination_path)
        raise OSError(error_code, ctypes.FormatError(error_code), destination_path)


def _copy_atomic_temp_windows(
    source_path: str, directory: str, *, prefix: str = ".nasmd-"
) -> tuple[int, str]:
    """Copy an existing Windows file to a short temp, then open its default stream."""
    flags = os.O_WRONLY | os.O_TRUNC
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    for _ in range(_ATOMIC_TEMP_ATTEMPTS):
        temp_path = os.path.join(directory, f"{prefix}{secrets.token_hex(8)}.tmp")
        try:
            _copy_file_windows(source_path, temp_path)
        except FileExistsError:
            continue
        except PermissionError:
            if os.path.isdir(temp_path):
                continue
            raise
        except OSError:
            with contextlib.suppress(OSError):
                os.remove(temp_path)
            raise
        try:
            return os.open(temp_path, flags), temp_path
        except BaseException:
            with contextlib.suppress(OSError):
                os.remove(temp_path)
            raise
    raise FileExistsError("unable to allocate atomic write temporary file")


def _replace_target(temp_path: str, target_path: str) -> None:
    """Atomically move the fully prepared temporary file into place."""
    os.replace(temp_path, target_path)


def _link_target(temp_path: str, target_path: str) -> None:
    """Publish a prepared missing target without replacing an existing path."""
    os.link(temp_path, target_path)


def _unused_recovery_path(directory: str) -> str:
    for _ in range(_ATOMIC_TEMP_ATTEMPTS):
        path = os.path.join(directory, f".nasmd-recovery-{secrets.token_hex(8)}.tmp")
        if not os.path.lexists(path):
            return path
    raise FileExistsError("unable to allocate recovery path")


def _exchange_target_windows(prepared_path: str, target_path: str) -> str:
    """Replace a Windows target while atomically retaining its old file."""
    import ctypes
    from ctypes import wintypes

    replace_file = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
    replace_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
    )
    replace_file.restype = wintypes.BOOL
    directory = os.path.dirname(os.path.abspath(target_path)) or "."
    backup_path = _unused_recovery_path(directory)
    _record_exchange_displaced_path(backup_path)
    if replace_file(target_path, prepared_path, backup_path, 0, None, None):
        return backup_path
    error_code = ctypes.get_last_error()
    raise ctypes.WinError(error_code)


def _exchange_target_linux(prepared_path: str, target_path: str) -> str:
    """Atomically exchange two Linux paths with renameat2."""
    import ctypes
    import errno

    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise OSError(errno.ENOTSUP, "renameat2(RENAME_EXCHANGE) is unavailable")
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    _record_exchange_displaced_path(prepared_path)
    if (
        renameat2(
            -100,
            os.fsencode(prepared_path),
            -100,
            os.fsencode(target_path),
            2,
        )
        != 0
    ):
        error_code = ctypes.get_errno()
        raise OSError(error_code, os.strerror(error_code), target_path)
    return prepared_path


def _exchange_target_macos(prepared_path: str, target_path: str) -> str:
    """Atomically exchange two macOS paths with renamex_np."""
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    renamex_np = libc.renamex_np
    renamex_np.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
    renamex_np.restype = ctypes.c_int
    _record_exchange_displaced_path(prepared_path)
    if renamex_np(os.fsencode(prepared_path), os.fsencode(target_path), 0x00000002) != 0:
        error_code = ctypes.get_errno()
        raise OSError(error_code, os.strerror(error_code), target_path)
    return prepared_path


def _exchange_target(prepared_path: str, target_path: str) -> str:
    """Atomically publish prepared_path and return the displaced target path."""
    if os.name == "nt":
        return _exchange_target_windows(prepared_path, target_path)
    if sys.platform.startswith("linux"):
        return _exchange_target_linux(prepared_path, target_path)
    if sys.platform == "darwin":
        return _exchange_target_macos(prepared_path, target_path)

    import errno

    raise OSError(errno.ENOTSUP, "atomic target exchange is unavailable on this platform")


def _fsync_directory(directory: str) -> None:
    """Best-effort directory sync after a completed atomic replacement."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)


def _write_text_atomically(
    file_path: str,
    content: str,
    before_replace: Callable[[str], Callable[[], None] | None] | None,
    expected_snapshot: _DiskSnapshot | None,
) -> None:
    """Write complete text and publish only if the reconciled target is unchanged."""
    target_path = os.path.abspath(file_path)
    directory = os.path.dirname(target_path) or "."
    os.makedirs(directory, exist_ok=True)

    try:
        existing_stat = os.stat(target_path)
    except FileNotFoundError:
        existing_stat = None

    if existing_stat is None:
        final_mode = _probe_new_file_mode(directory)
        xattrs = ()
    else:
        final_mode = stat.S_IMODE(existing_stat.st_mode)
        xattrs = _snapshot_xattrs(target_path)

    if existing_stat is not None and os.name == "nt":
        fd, temp_path = _copy_atomic_temp_windows(target_path, directory, prefix=".nasmd-recovery-")
    else:
        prefix = ".nasmd-recovery-" if expected_snapshot is not None else ".nasmd-"
        fd, temp_path = _create_atomic_temp(directory, mode=0o600, prefix=prefix)

    rollback_expected = None
    published = False
    preserved_paths: set[str] = set()
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            fd = -1
            f.write(content)
            f.flush()
            if existing_stat is not None:
                fchown = getattr(os, "fchown", None)
                if fchown is not None:
                    fchown(f.fileno(), existing_stat.st_uid, existing_stat.st_gid)
            fchmod = getattr(os, "fchmod", None)
            if fchmod is not None:
                fchmod(f.fileno(), final_mode)
            else:
                os.chmod(temp_path, final_mode)
            _apply_xattrs(f.fileno(), xattrs)
            os.fsync(f.fileno())
        if before_replace is not None:
            rollback_expected = before_replace(temp_path)
        try:
            if expected_snapshot is None:
                try:
                    _link_target(temp_path, target_path)
                except FileExistsError as e:
                    raise _ConditionalWriteConflict from e
                published = True
                with contextlib.suppress(OSError):
                    os.remove(temp_path)
            else:
                prepared_snapshot = _read_disk_snapshot(temp_path)
                _publish_existing_target(
                    temp_path,
                    target_path,
                    expected_snapshot,
                    prepared_snapshot,
                )
                published = True
        except BaseException as error:
            preserved_paths.update(getattr(error, "preserve_paths", ()))
            if rollback_expected is not None:
                try:
                    rollback_expected()
                except Exception:
                    logger.warning("Failed to roll back expected file watcher mark", exc_info=True)
            raise
    finally:
        if fd >= 0:
            with contextlib.suppress(OSError):
                os.close(fd)
        if not published and temp_path not in preserved_paths:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning("Failed to clean temporary file %s", temp_path, exc_info=True)

    try:
        _fsync_directory(directory)
    except OSError:
        logger.warning(
            "Failed to sync directory %s after file replacement", directory, exc_info=True
        )


@dataclass
class _FileVersion:
    """In-memory version state for a single file."""

    version: int = 0
    content: str = ""
    persisted: bool = False
    # changes_by_version: version -> list of changes that produced this version
    # retained as a bounded record; stale merging uses submitted base content
    changes_by_version: dict = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)


@dataclass(frozen=True)
class _DiskSnapshot:
    data: bytes
    content: str
    mod_time: int
    identity: tuple[int, int, int, int, int]
    digest: bytes
    metadata: tuple[int, int, int, int, tuple[tuple[str | bytes, bytes], ...]]


class _ConditionalWriteConflict(Exception):
    """The target changed after reconciliation but before publication."""

    def __init__(self, preserve_paths: tuple[str, ...] = ()):
        super().__init__("target changed during conditional publication")
        self.preserve_paths = preserve_paths


class _ConditionalRollbackError(OSError):
    """A publish conflict could not be fully restored without retaining data."""

    def __init__(self, preserve_paths: tuple[str, ...]):
        super().__init__("conditional publication rollback failed")
        self.preserve_paths = preserve_paths


@dataclass
class _ExchangeAttempt:
    token: object = field(default_factory=object)
    displaced_path: str | None = None


_exchange_attempt_context: ContextVar[_ExchangeAttempt | None] = ContextVar(
    "nasmd_exchange_attempt", default=None
)


@contextlib.contextmanager
def _track_exchange_attempt() -> Iterator[_ExchangeAttempt]:
    attempt = _ExchangeAttempt()
    context_token = _exchange_attempt_context.set(attempt)
    try:
        yield attempt
    finally:
        _exchange_attempt_context.reset(context_token)


def _record_exchange_displaced_path(path: str) -> None:
    attempt = _exchange_attempt_context.get()
    if attempt is not None:
        attempt.displaced_path = path


def _read_disk_snapshot(file_path: str) -> _DiskSnapshot:
    with open(file_path, "rb") as f:
        data = f.read()
        file_stat = os.fstat(f.fileno())
        listxattr = getattr(os, "listxattr", None)
        getxattr = getattr(os, "getxattr", None)
        if listxattr is None or getxattr is None:
            xattrs = ()
        else:
            names = listxattr(f.fileno())
            xattrs = tuple(
                sorted(
                    ((name, getxattr(f.fileno(), name)) for name in names),
                    key=lambda item: os.fsencode(item[0]),
                )
            )
    return _DiskSnapshot(
        data=data,
        content=io.TextIOWrapper(
            io.BytesIO(data),
            encoding="utf-8",
            errors="replace",
            newline=None,
        ).read(),
        mod_time=int(file_stat.st_mtime * 1000),
        identity=(
            file_stat.st_dev,
            file_stat.st_ino,
            file_stat.st_size,
            file_stat.st_mtime_ns,
            file_stat.st_ctime_ns,
        ),
        digest=hashlib.sha256(data).digest(),
        metadata=(
            stat.S_IMODE(file_stat.st_mode),
            getattr(file_stat, "st_uid", 0),
            getattr(file_stat, "st_gid", 0),
            getattr(file_stat, "st_flags", 0),
            xattrs,
        ),
    )


def _matches_reconciled_snapshot(actual: _DiskSnapshot, expected: _DiskSnapshot) -> bool:
    # Atomic rename/exchange may alter ctime, so compare stable inode identity,
    # mtime, size, and bytes. In-place writes are still caught by the digest.
    return (
        actual.identity[:4] == expected.identity[:4]
        and actual.digest == expected.digest
        and actual.metadata == expected.metadata
    )


def _matches_content_and_metadata(actual: _DiskSnapshot, expected: _DiskSnapshot) -> bool:
    return actual.digest == expected.digest and actual.metadata == expected.metadata


def _recovery_paths(directory: str) -> set[str]:
    try:
        with os.scandir(directory) as entries:
            return {
                entry.path
                for entry in entries
                if entry.name.startswith(".nasmd-recovery-") and entry.name.endswith(".tmp")
            }
    except OSError:
        return set()


def _remove_transaction_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        return
    except OSError:
        logger.warning("Failed to clean conditional-write transaction file", exc_info=True)


def _rollback_conflicting_publish(
    displaced_path: str,
    target_path: str,
    prepared_snapshot: _DiskSnapshot,
) -> None:
    try:
        preserved_current_path = _exchange_target(displaced_path, target_path)
    except OSError as error:
        raise _ConditionalRollbackError((displaced_path,)) from error

    try:
        preserved_current = _read_disk_snapshot(preserved_current_path)
    except OSError as error:
        raise _ConditionalRollbackError((preserved_current_path,)) from error

    if _matches_content_and_metadata(preserved_current, prepared_snapshot):
        _remove_transaction_file(preserved_current_path)
        raise _ConditionalWriteConflict

    # A third-party write reached the target during rollback. Put that newest
    # content back and retain the older displaced external version for recovery.
    try:
        recovery_path = _exchange_target(preserved_current_path, target_path)
    except OSError as error:
        raise _ConditionalRollbackError((preserved_current_path,)) from error
    logger.error(
        "Concurrent writes prevented complete transaction cleanup; "
        "an external version was retained in a .nasmd-recovery file"
    )
    raise _ConditionalWriteConflict((recovery_path,))


def _recover_failed_initial_exchange(
    prepared_path: str,
    target_path: str,
    expected_snapshot: _DiskSnapshot,
    prepared_snapshot: _DiskSnapshot,
    recovery_paths_before: set[str],
    displaced_path_hint: str | None,
    exchange_error: OSError,
) -> None:
    directory = os.path.dirname(os.path.abspath(target_path)) or "."
    new_recovery_paths = _recovery_paths(directory) - recovery_paths_before
    candidate_paths = []
    if displaced_path_hint and os.path.lexists(displaced_path_hint):
        candidate_paths.append(displaced_path_hint)
    if os.path.lexists(prepared_path) and prepared_path not in candidate_paths:
        candidate_paths.append(prepared_path)
    known_candidate_paths = set(candidate_paths)
    known_candidate_paths.add(prepared_path)
    candidate_paths.extend(sorted(new_recovery_paths - known_candidate_paths))

    try:
        target_snapshot = _read_disk_snapshot(target_path)
    except FileNotFoundError:
        if os.path.lexists(prepared_path) and not new_recovery_paths:
            raise _ConditionalWriteConflict from exchange_error
        raise _ConditionalRollbackError(tuple(candidate_paths)) from exchange_error
    except OSError as error:
        raise _ConditionalRollbackError(tuple(candidate_paths)) from error

    if _matches_reconciled_snapshot(target_snapshot, expected_snapshot):
        raise exchange_error

    if not _matches_content_and_metadata(target_snapshot, prepared_snapshot):
        raise _ConditionalRollbackError(tuple(candidate_paths)) from exchange_error

    displaced_candidates = []
    for path in candidate_paths:
        try:
            snapshot = _read_disk_snapshot(path)
        except OSError:
            continue
        if path == displaced_path_hint or snapshot.identity[:2] == expected_snapshot.identity[:2]:
            displaced_candidates.append(path)

    if not displaced_candidates:
        raise _ConditionalRollbackError(tuple(candidate_paths)) from exchange_error

    _rollback_conflicting_publish(displaced_candidates[0], target_path, prepared_snapshot)


def _publish_existing_target(
    prepared_path: str,
    target_path: str,
    expected_snapshot: _DiskSnapshot,
    prepared_snapshot: _DiskSnapshot,
) -> None:
    directory = os.path.dirname(os.path.abspath(target_path)) or "."
    recovery_paths_before = _recovery_paths(directory)
    with _track_exchange_attempt() as attempt:
        try:
            displaced_path = _exchange_target(prepared_path, target_path)
        except OSError as error:
            _recover_failed_initial_exchange(
                prepared_path,
                target_path,
                expected_snapshot,
                prepared_snapshot,
                recovery_paths_before,
                attempt.displaced_path,
                error,
            )
    try:
        displaced_snapshot = _read_disk_snapshot(displaced_path)
    except OSError:
        _rollback_conflicting_publish(displaced_path, target_path, prepared_snapshot)

    if _matches_reconciled_snapshot(displaced_snapshot, expected_snapshot):
        _remove_transaction_file(displaced_path)
        return

    _rollback_conflicting_publish(displaced_path, target_path, prepared_snapshot)


class FileVersionStore:
    """Thread-safe file version store with paragraph-level merge."""

    def __init__(self, storage_dir: str | None = None):
        self._lock = threading.RLock()
        self._files: dict[str, _FileVersion] = {}
        self._storage_dir = storage_dir

    def init_file(
        self,
        file_key: str,
        file_path: str,
        content: str,
        *,
        persisted: bool | None = None,
    ) -> int:
        """Initialize a file in the store if not already present.

        Returns the current version number.
        """
        if persisted is None:
            persisted = os.path.isfile(file_path)

        with self._lock:
            fv = self._files.get(file_key)
        if fv is not None:
            with fv.lock:
                return fv.version

        # Check if there is existing persisted history to maintain version monotonicity
        base_version = 0
        base_content = content
        base_persisted = persisted
        try:
            from nas_md.webserver.version_history import _load

            hist = _load(file_key, storage_dir=self._storage_dir)
            if hist and hist.versions:
                latest = max(hist.versions, key=lambda entry: entry.version)
                base_version = latest.version
                base_content = latest.content_snapshot
                base_persisted = persisted and content == base_content
        except Exception:
            base_version = 0

        candidate = _FileVersion(
            version=base_version,
            content=base_content,
            persisted=base_persisted,
            changes_by_version={},
        )
        with self._lock:
            fv = self._files.setdefault(file_key, candidate)
        with fv.lock:
            return fv.version

    def _apply_external_content(
        self,
        fv: _FileVersion,
        file_key: str,
        file_path: str,
        new_content: str,
    ) -> bool:
        """Apply content observed outside the store while ``fv.lock`` is held."""
        fv.persisted = True
        if new_content == fv.content:
            return False

        previous_content = fv.content
        fv.version += 1
        fv.content = new_content
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
        return True

    def _reconcile_disk_locked(
        self,
        fv: _FileVersion,
        file_key: str,
        file_path: str,
        enqueue_event: Callable[[str, dict], None] | None = None,
    ) -> tuple[dict, _DiskSnapshot | None]:
        """Reconcile one file from its current disk state while ``fv.lock`` is held."""
        try:
            snapshot = _read_disk_snapshot(file_path)
        except FileNotFoundError:
            fv.persisted = False
            return (
                {
                    "applied": False,
                    "newVersion": fv.version,
                    "content": fv.content,
                },
                None,
            )
        except OSError as e:
            logger.error("Failed to reconcile file %s: %s", file_path, e)
            return (
                {
                    "applied": False,
                    "newVersion": fv.version,
                    "content": fv.content,
                    "errorCode": "read_failed",
                    "message": "Unable to verify current file state",
                },
                None,
            )

        applied = self._apply_external_content(fv, file_key, file_path, snapshot.content)
        transition = {
            "applied": applied,
            "newVersion": fv.version,
            "content": fv.content,
        }
        if applied:
            self._enqueue_event(enqueue_event, "external_reload", transition)
        return transition, snapshot

    @staticmethod
    def _enqueue_event(
        enqueue_event: Callable[[str, dict], None] | None,
        event_type: str,
        result: dict,
    ) -> None:
        if enqueue_event is None:
            return
        try:
            enqueue_event(event_type, result)
        except Exception:
            logger.warning("Failed to enqueue %s event", event_type, exc_info=True)

    @staticmethod
    def _with_external_transition(result: dict, transition: dict) -> dict:
        if transition["applied"]:
            result["_externalTransition"] = transition
        return result

    @staticmethod
    def _reconciliation_error_result(fv: _FileVersion, transition: dict) -> dict:
        return {
            "applied": False,
            "merged": False,
            "newVersion": fv.version,
            "content": fv.content,
            "errorCode": transition["errorCode"],
            "message": transition["message"],
        }

    def _get_or_load_file(self, file_key: str, file_path: str) -> _FileVersion:
        with self._lock:
            fv = self._files.get(file_key)
        if fv is not None:
            return fv

        persisted = False
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                disk_content = f.read()
            persisted = True
        except OSError:
            disk_content = ""
        candidate = _FileVersion(
            version=0,
            content=disk_content,
            persisted=persisted,
            changes_by_version={},
        )
        with self._lock:
            return self._files.setdefault(file_key, candidate)

    def create_empty_file(
        self,
        file_key: str,
        file_path: str,
        before_write: Callable[[str], Callable[[], None] | None] | None = None,
        *,
        author_id: str = "system",
        author_name: str = "File recreation",
        author_color: str = "#95a5a6",
        enqueue_event: Callable[[str, dict], None] | None = None,
    ) -> dict:
        """Persist an empty file only if it is still missing."""
        fv = self._get_or_load_file(file_key, file_path)
        with fv.lock:
            transition, snapshot = self._reconcile_disk_locked(
                fv, file_key, file_path, enqueue_event
            )
            if transition.get("errorCode"):
                return self._reconciliation_error_result(fv, transition)
            if fv.persisted:
                return self._with_external_transition(self._resync_result(fv), transition)

            try:
                _write_text_atomically(file_path, "", before_write, snapshot)
            except _ConditionalWriteConflict:
                conflict_transition, _snapshot = self._reconcile_disk_locked(
                    fv, file_key, file_path, enqueue_event
                )
                if conflict_transition.get("errorCode"):
                    return self._reconciliation_error_result(fv, conflict_transition)
                effective_transition = (
                    conflict_transition if conflict_transition["applied"] else transition
                )
                return self._with_external_transition(self._resync_result(fv), effective_transition)
            previous_content = fv.content
            fv.content = ""
            fv.persisted = True
            if previous_content:
                fv.version += 1
                fv.changes_by_version[fv.version] = [
                    {"type": "external_reload", "paraIdx": 0, "content": ""}
                ]
                self._prune_changes_history(fv)
                self._record_version_history(
                    file_key=file_key,
                    file_path=file_path,
                    author_id=author_id,
                    author_name=author_name,
                    author_color=author_color,
                    changes=[],
                    content_snapshot="",
                    previous_content=previous_content,
                    version=fv.version,
                )
            return {
                "applied": False,
                "merged": False,
                "newVersion": fv.version,
                "content": "",
            }

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
        before_write: Callable[[str], Callable[[], None] | None] | None = None,
        enqueue_event: Callable[[str, dict], None] | None = None,
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
            transition, snapshot = self._reconcile_disk_locked(
                fv, file_key, file_path, enqueue_event
            )
            if transition.get("errorCode"):
                return self._reconciliation_error_result(fv, transition)

            def finish(result: dict) -> dict:
                return self._with_external_transition(result, transition)

            def attach_transition(error: TypeError | ValueError) -> TypeError | ValueError:
                if transition["applied"]:
                    error._external_transition = transition
                return error

            if (
                transition["applied"]
                and base_content is None
                and base_version == fv.version - 1
                and isinstance(client_content, str)
            ):
                try:
                    validate_changes(changes, len(split_paragraphs(fv.content)))
                    confirmed_content = apply_diff(fv.content, changes)
                except (TypeError, ValueError):
                    pass
                else:
                    if confirmed_content == client_content:
                        base_version = fv.version
            if base_version < 0 or base_version > fv.version:
                return finish(self._resync_result(fv))

            submitted_base = base_content
            if submitted_base is None and base_version == fv.version:
                submitted_base = fv.content
            if submitted_base is None:
                return finish(self._resync_result(fv))
            if not isinstance(submitted_base, str):
                raise attach_transition(TypeError("baseContent must be a string"))

            try:
                validate_changes(changes, len(split_paragraphs(submitted_base)))
                reconstructed_content = apply_diff(submitted_base, changes)
            except (TypeError, ValueError) as e:
                raise attach_transition(e)

            submitted_content = client_content
            if submitted_content is None:
                submitted_content = reconstructed_content
            else:
                if not isinstance(submitted_content, str):
                    raise attach_transition(TypeError("content must be a string"))
                if split_paragraphs(reconstructed_content) != split_paragraphs(submitted_content):
                    return finish(self._resync_result(fv))
                if reconstructed_content != submitted_content:
                    # Legacy clients sent full content whose incidental whitespace could
                    # overwrite newer server formatting. Their declared operations are
                    # the authoritative compatible representation.
                    submitted_content = reconstructed_content

            try:
                canonical_changes = compute_diff(submitted_base, submitted_content)
            except DiffWorkLimitExceeded:
                return finish(self._resync_result(fv))
            merged = base_version != fv.version
            if not merged and submitted_base != fv.content:
                return finish(self._resync_result(fv))
            if not canonical_changes:
                return finish(
                    {
                        "applied": False,
                        "merged": False,
                        "newVersion": fv.version,
                        "content": fv.content,
                    }
                )

            if not merged:
                changes_to_apply = canonical_changes
                new_content = submitted_content
            else:
                try:
                    remote_changes = compute_diff(submitted_base, fv.content)
                except DiffWorkLimitExceeded:
                    return finish(self._resync_result(fv))
                try:
                    changes_to_apply = transform_changes(
                        canonical_changes,
                        remote_changes,
                        len(split_paragraphs(submitted_base)),
                    )
                    new_content = apply_diff(fv.content, changes_to_apply)
                except (TypeError, ValueError) as e:
                    raise attach_transition(e)

            if not changes_to_apply or new_content == fv.content:
                return finish(
                    {
                        "applied": False,
                        "merged": False,
                        "newVersion": fv.version,
                        "content": fv.content,
                    }
                )

            # Write to disk
            try:
                _write_text_atomically(file_path, new_content, before_write, snapshot)
            except _ConditionalWriteConflict:
                conflict_transition, _snapshot = self._reconcile_disk_locked(
                    fv, file_key, file_path, enqueue_event
                )
                if conflict_transition.get("errorCode"):
                    return self._reconciliation_error_result(fv, conflict_transition)
                effective_transition = (
                    conflict_transition if conflict_transition["applied"] else transition
                )
                return self._with_external_transition(self._resync_result(fv), effective_transition)
            except _ConditionalRollbackError:
                conflict_transition, _snapshot = self._reconcile_disk_locked(
                    fv, file_key, file_path, enqueue_event
                )
                if conflict_transition.get("errorCode"):
                    return self._reconciliation_error_result(fv, conflict_transition)
                effective_transition = (
                    conflict_transition if conflict_transition["applied"] else transition
                )
                return self._with_external_transition(self._resync_result(fv), effective_transition)
            except OSError:
                logger.exception("Failed to write file %s", file_path)
                return finish(
                    {
                        "applied": False,
                        "merged": False,
                        "newVersion": fv.version,
                        "content": fv.content,
                        "errorCode": "write_failed",
                        "message": "Unable to save file",
                    }
                )

            # Update in-memory state
            previous_content = fv.content
            fv.persisted = True
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

            result = {
                "applied": True,
                "merged": merged,
                "newVersion": fv.version,
                "content": new_content,
                "appliedChanges": changes_to_apply,
            }
            self._enqueue_event(enqueue_event, "remote_edit", result)
            return finish(result)

    @staticmethod
    def _resync_result(fv: _FileVersion) -> dict:
        return {
            "applied": False,
            "merged": False,
            "resyncRequired": True,
            "newVersion": fv.version,
            "content": fv.content,
        }

    def reconcile_disk(
        self,
        file_key: str,
        file_path: str,
        *,
        enqueue_event: Callable[[str, dict], None] | None = None,
    ) -> dict:
        """Apply the current disk state once and return its version transition."""
        fv = self._get_or_load_file(file_key, file_path)
        with fv.lock:
            transition, _snapshot = self._reconcile_disk_locked(
                fv, file_key, file_path, enqueue_event
            )
            return transition

    def read_reconciled_disk(
        self,
        file_key: str,
        file_path: str,
        *,
        enqueue_event: Callable[[str, dict], None] | None = None,
    ) -> dict:
        """Return bytes and metadata from the same locked read used for reconciliation."""
        fv = self._get_or_load_file(file_key, file_path)
        with fv.lock:
            transition, snapshot = self._reconcile_disk_locked(
                fv, file_key, file_path, enqueue_event
            )
            return {
                "transition": transition,
                "data": snapshot.data if snapshot is not None else None,
                "modTime": snapshot.mod_time if snapshot is not None else None,
            }

    def apply_external_change(
        self,
        file_key: str,
        file_path: str,
        *,
        enqueue_event: Callable[[str, dict], None] | None = None,
    ) -> dict:
        """Apply an external file modification (e.g., from watchdog).

        Reads the current disk content and bumps the version number,
        so subsequent client saves will detect the change and merge.

        Returns dict with applied/newVersion/content.
        """
        return self.reconcile_disk(file_key, file_path, enqueue_event=enqueue_event)

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

    def get_current_snapshot(self, file_key: str) -> dict:
        """Return the current version and content from one file-lock acquisition."""
        with self._lock:
            fv = self._files.get(file_key)
        if fv is None:
            return {"version": 0, "content": None}
        with fv.lock:
            return {"version": fv.version, "content": fv.content}

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


def _initialize_store(storage_dir: str) -> FileVersionStore:
    """Bind a fresh process-global store to one server lifecycle."""
    global _store
    with _store_lock:
        _store = FileVersionStore(storage_dir=storage_dir)
        return _store
