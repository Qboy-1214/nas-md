# tests/test_file_version_store.py
import json
import logging
import os
import stat
import struct
import threading
from pathlib import Path
from unittest.mock import Mock

import nas_md.webserver.file_version_store as file_version_store_module
import pytest
from nas_md.webserver import paragraph_diff, version_history
from nas_md.webserver.file_version_store import FileVersionStore
from nas_md.webserver.paragraph_diff import compute_diff


@pytest.fixture(autouse=True)
def clean_version_history():
    with version_history._lock:
        version_history._histories.clear()
    yield
    with version_history._lock:
        version_history._histories.clear()


@pytest.fixture
def store(tmp_path):
    return FileVersionStore(storage_dir=str(tmp_path / ".version_history"))


@pytest.fixture
def test_file(tmp_path):
    f = tmp_path / "test.md"
    f.write_text("para one\n\npara two\n\npara three", encoding="utf-8")
    return str(f)


def _history_count(store, file_key):
    return len(version_history.get_history(file_key, limit=1000, storage_dir=store._storage_dir))


def _assert_failed_write_preserves_state(store, file_key, file_path, original, result):
    assert result == {
        "applied": False,
        "merged": False,
        "newVersion": 0,
        "content": original,
        "errorCode": "write_failed",
        "message": "Unable to save file",
    }
    assert Path(file_path).read_text(encoding="utf-8") == original
    assert store.get_current_snapshot(file_key) == {"version": 0, "content": original}
    assert _history_count(store, file_key) == 0


def test_init_file_new(store, test_file):
    version = store.init_file("mount-0:/test.md", test_file, "para one\n\npara two\n\npara three")
    assert version == 0


def test_get_current_snapshot_returns_version_and_content_together(store, test_file):
    content = "para one\n\npara two"
    store.init_file("mount-0:/test.md", test_file, content)

    assert store.get_current_snapshot("mount-0:/test.md") == {
        "version": 0,
        "content": content,
    }


def test_init_file_with_existing_history(store, test_file):
    store.init_file("mount-0:/test.md", test_file, "para one\n\npara two\n\npara three")
    store.apply_changes(
        file_key="mount-0:/test.md",
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "CHANGED"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )
    version = store.init_file("mount-0:/test.md", test_file, "CHANGED\n\npara two\n\npara three")
    assert version == 1


def test_apply_changes_no_conflict(store, test_file):
    store.init_file("mount-0:/test.md", test_file, "para one\n\npara two\n\npara three")
    result = store.apply_changes(
        file_key="mount-0:/test.md",
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 1, "content": "CHANGED"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )
    assert result["applied"] is True
    assert result["merged"] is False
    assert result["newVersion"] == 1
    assert "para one\n\nCHANGED\n\npara three" in result["content"]


def test_partial_write_keeps_target_store_and_history_unchanged(store, test_file, monkeypatch):
    file_key = "mount-0:/test.md"
    original = "para one\n\npara two\n\npara three"
    store.init_file(file_key, test_file, original)
    original_fdopen = os.fdopen
    target_dir = os.path.dirname(test_file)

    class PartialWriter:
        def __init__(self, fd, *args, **kwargs):
            self._stream = original_fdopen(fd, *args, **kwargs)

        def __enter__(self):
            self._stream.__enter__()
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return self._stream.__exit__(exc_type, exc_value, traceback)

        def write(self, value):
            self._stream.write(value[:3])
            self._stream.flush()
            raise OSError(f"partial write at {test_file}")

        def __getattr__(self, name):
            return getattr(self._stream, name)

    def partial_fdopen(fd, mode="r", *args, **kwargs):
        if mode == "w":
            return PartialWriter(fd, mode, *args, **kwargs)
        return original_fdopen(fd, mode, *args, **kwargs)

    monkeypatch.setattr(file_version_store_module.os, "fdopen", partial_fdopen)

    result = store.apply_changes(
        file_key=file_key,
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "CHANGED"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )

    _assert_failed_write_preserves_state(store, file_key, test_file, original, result)
    assert test_file not in json.dumps(result)
    assert [entry.name for entry in os.scandir(target_dir)] == [os.path.basename(test_file)]


def test_replace_failure_cleans_temp_rolls_back_watcher_and_preserves_state(
    store, test_file, monkeypatch
):
    from nas_md.webserver.file_watcher import FileWatcher

    file_key = "mount-0:/test.md"
    original = "para one\n\npara two\n\npara three"
    store.init_file(file_key, test_file, original)
    watcher = FileWatcher()
    tokens = []
    replace_sources = []
    original_replace = os.replace
    normalized_target = os.path.normcase(os.path.abspath(test_file))

    def fail_target_replace(src, dst):
        if os.path.normcase(os.path.abspath(dst)) == normalized_target:
            replace_sources.append(os.fspath(src))
            raise OSError(f"replace failed for {test_file}")
        return original_replace(src, dst)

    def mark_expected(prepared_path):
        token = watcher.mark_expected("mount-0", "/test.md", prepared_path)
        tokens.append(token)
        return lambda: watcher.unmark_expected(token)

    monkeypatch.setattr(
        file_version_store_module, "_replace_target", fail_target_replace, raising=False
    )

    result = store.apply_changes(
        file_key=file_key,
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "CHANGED"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
        before_write=mark_expected,
    )

    assert replace_sources
    assert all(not os.path.exists(path) for path in replace_sources)
    _assert_failed_write_preserves_state(store, file_key, test_file, original, result)
    assert tokens
    assert watcher.unmark_expected(tokens[0]) is False


def test_successful_write_marks_immediately_before_atomic_replace(store, test_file, monkeypatch):
    file_key = "mount-0:/test.md"
    original = "para one\n\npara two\n\npara three"
    target = "CHANGED\n\npara two\n\npara three"
    store.init_file(file_key, test_file, original)
    events = []
    original_replace = os.replace
    normalized_target = os.path.normcase(os.path.abspath(test_file))

    def observe_replace(src, dst):
        if os.path.normcase(os.path.abspath(dst)) == normalized_target:
            with open(dst, encoding="utf-8") as f:
                events.append(("before", f.read()))
            original_replace(src, dst)
            with open(dst, encoding="utf-8") as f:
                events.append(("after", f.read()))
            return None
        return original_replace(src, dst)

    def mark_expected(prepared_path):
        events.append(("marked", Path(prepared_path).read_text(encoding="utf-8")))

    monkeypatch.setattr(
        file_version_store_module, "_replace_target", observe_replace, raising=False
    )

    result = store.apply_changes(
        file_key=file_key,
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "CHANGED"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
        before_write=mark_expected,
    )

    assert result["applied"] is True
    assert events == [("marked", target), ("before", original), ("after", target)]
    with open(test_file, encoding="utf-8") as f:
        assert f.read() == target


def test_successful_write_marks_expected_from_prepared_temp_identity(store, test_file):
    from nas_md.webserver.file_watcher import FileWatcher

    file_key = "mount-0:/test.md"
    original = "para one\n\npara two\n\npara three"
    target = "CHANGED\n\npara two\n\npara three"
    store.init_file(file_key, test_file, original)
    watcher = FileWatcher()
    tokens = []

    def mark_prepared(prepared_path):
        assert Path(prepared_path).read_text(encoding="utf-8") == target
        token = watcher.mark_expected("mount-0", "/test.md", prepared_path)
        tokens.append(token)
        return lambda: watcher.unmark_expected(token)

    result = store.apply_changes(
        file_key=file_key,
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "CHANGED"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
        before_write=mark_prepared,
    )

    assert result["applied"] is True
    assert len(tokens) == 1
    _content, fingerprint, digest = watcher._read_state(test_file)
    assert (tokens[0].fingerprint, tokens[0].digest) == (fingerprint, digest)


def test_create_empty_file_resyncs_without_overwriting_persisted_version(store, tmp_path):
    file_path = tmp_path / "created-by-post.md"
    file_key = "mount-0:/created-by-post.md"
    store.init_file(file_key, str(file_path), "", persisted=False)
    post_result = store.apply_changes(
        file_key=file_key,
        file_path=str(file_path),
        base_version=0,
        changes=[{"type": "insert", "paraIdx": 0, "content": "B"}],
        author_id="post",
        author_name="POST",
        author_color="#fff",
        client_content="B",
        base_content="",
    )
    assert post_result["applied"] is True
    assert post_result["newVersion"] == 1

    result = store.create_empty_file(file_key, str(file_path))

    assert result == {
        "applied": False,
        "merged": False,
        "resyncRequired": True,
        "newVersion": 1,
        "content": "B",
    }
    assert file_path.read_text(encoding="utf-8") == "B"
    assert store.get_current_snapshot(file_key) == {"version": 1, "content": "B"}


def test_create_empty_file_recreates_deleted_file_at_a_new_version(store, tmp_path):
    file_path = tmp_path / "deleted-before-empty-put.md"
    file_path.write_text("A", encoding="utf-8")
    file_key = "mount-0:/deleted-before-empty-put.md"
    store.init_file(file_key, str(file_path), "A")
    write_result = store.apply_changes(
        file_key=file_key,
        file_path=str(file_path),
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "B"}],
        author_id="writer",
        author_name="Writer",
        author_color="#fff",
    )
    assert write_result["newVersion"] == 1
    file_path.unlink()

    result = store.create_empty_file(file_key, str(file_path))

    assert result == {
        "applied": False,
        "merged": False,
        "newVersion": 2,
        "content": "",
    }
    assert file_path.read_text(encoding="utf-8") == ""
    assert store.get_current_snapshot(file_key) == {"version": 2, "content": ""}
    assert _history_count(store, file_key) == 3


def test_init_file_does_not_reassign_existing_unpersisted_version(store, tmp_path):
    file_path = tmp_path / "external-create.md"
    file_key = "mount-0:/external-create.md"
    store.init_file(file_key, str(file_path), "", persisted=False)
    file_path.write_text("external", encoding="utf-8")

    version = store.init_file(file_key, str(file_path), "external", persisted=True)

    assert version == 0
    assert store.get_current_snapshot(file_key) == {"version": 0, "content": ""}
    result = store.apply_external_change(file_key, str(file_path))
    assert result == {"applied": True, "newVersion": 1, "content": "external"}
    assert store.get_current_snapshot(file_key) == {"version": 1, "content": "external"}
    assert _history_count(store, file_key) == 2


def test_create_empty_file_resyncs_invalid_utf8_external_creation(store, tmp_path):
    file_path = tmp_path / "invalid-external.md"
    file_key = "mount-0:/invalid-external.md"
    store.init_file(file_key, str(file_path), "", persisted=False)
    file_path.write_bytes(b"\xff")

    result = store.create_empty_file(file_key, str(file_path))

    assert result == {
        "applied": False,
        "merged": False,
        "resyncRequired": True,
        "newVersion": 1,
        "content": "\ufffd",
        "_externalTransition": {
            "applied": True,
            "newVersion": 1,
            "content": "\ufffd",
        },
    }
    assert file_path.read_bytes() == b"\xff"
    assert store.get_current_snapshot(file_key) == {"version": 1, "content": "\ufffd"}


def test_directory_sync_failure_after_replace_does_not_report_save_failure(
    store, test_file, monkeypatch
):
    file_key = "mount-0:/test.md"
    original = "para one\n\npara two\n\npara three"
    target = "CHANGED\n\npara two\n\npara three"
    store.init_file(file_key, test_file, original)

    def fail_directory_sync(_directory):
        raise OSError("directory sync unavailable")

    monkeypatch.setattr(file_version_store_module, "_fsync_directory", fail_directory_sync)

    result = store.apply_changes(
        file_key=file_key,
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "CHANGED"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )

    assert result["applied"] is True
    assert result["newVersion"] == 1
    assert store.get_current_snapshot(file_key) == {"version": 1, "content": target}
    with open(test_file, encoding="utf-8") as f:
        assert f.read() == target


def test_directory_sync_happens_after_target_replace(store, test_file, monkeypatch):
    file_key = "mount-0:/test.md"
    original = "para one\n\npara two\n\npara three"
    store.init_file(file_key, test_file, original)
    events = []
    original_replace = os.replace

    def observe_replace(src, dst):
        if os.path.abspath(dst) == os.path.abspath(test_file):
            events.append("replace")
        return original_replace(src, dst)

    monkeypatch.setattr(
        file_version_store_module, "_replace_target", observe_replace, raising=False
    )
    monkeypatch.setattr(
        file_version_store_module,
        "_fsync_directory",
        lambda _directory: events.append("directory-fsync"),
    )

    result = store.apply_changes(
        file_key=file_key,
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "changed"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )

    assert result["applied"] is True
    assert events == ["replace", "directory-fsync"]


def test_existing_file_metadata_is_applied_before_replace(store, test_file, monkeypatch):
    file_key = "mount-0:/test.md"
    original = "para one\n\npara two\n\npara three"
    store.init_file(file_key, test_file, original)
    target_stat = os.stat(test_file)
    events = []
    target_replaced = [False]
    original_replace = os.replace
    original_fsync = os.fsync

    monkeypatch.setattr(
        file_version_store_module.os,
        "fchmod",
        lambda _fd, mode: events.append(("mode", mode)),
        raising=False,
    )
    monkeypatch.setattr(
        file_version_store_module.os,
        "fchown",
        lambda _fd, uid, gid: events.append(("owner", uid, gid)),
        raising=False,
    )
    monkeypatch.setattr(
        file_version_store_module,
        "_snapshot_xattrs",
        lambda _path: (("user.nasmd", b"metadata"),),
        raising=False,
    )
    monkeypatch.setattr(
        file_version_store_module,
        "_apply_xattrs",
        lambda _fd, attrs: events.append(("xattrs", attrs)),
        raising=False,
    )

    def observe_fsync(fd):
        if not target_replaced[0] and stat.S_ISREG(os.fstat(fd).st_mode):
            events.append(("file-fsync",))
        return original_fsync(fd)

    def observe_replace(src, dst):
        if os.path.abspath(dst) == os.path.abspath(test_file):
            events.append(("replace",))
            target_replaced[0] = True
        return original_replace(src, dst)

    monkeypatch.setattr(
        file_version_store_module, "_replace_target", observe_replace, raising=False
    )
    monkeypatch.setattr(file_version_store_module.os, "fsync", observe_fsync)

    result = store.apply_changes(
        file_key=file_key,
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "changed"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
        before_write=lambda _prepared_path: events.append(("mark",)),
    )

    assert result["applied"] is True
    assert events == [
        ("owner", target_stat.st_uid, target_stat.st_gid),
        ("mode", stat.S_IMODE(target_stat.st_mode)),
        ("xattrs", (("user.nasmd", b"metadata"),)),
        ("file-fsync",),
        ("mark",),
        ("replace",),
    ]


def test_new_file_uses_private_content_temp_and_normal_permission_probe(
    store, tmp_path, monkeypatch
):
    file_path = tmp_path / "new.md"
    file_key = "mount-0:/new.md"
    store.init_file(file_key, str(file_path), "")
    original_open = os.open
    create_modes = []

    def observe_open(path, flags, mode=0o777, *args, **kwargs):
        if flags & os.O_CREAT and flags & os.O_EXCL:
            create_modes.append((os.path.basename(path), mode))
        return original_open(path, flags, mode, *args, **kwargs)

    monkeypatch.setattr(file_version_store_module.os, "open", observe_open)

    result = store.apply_changes(
        file_key=file_key,
        file_path=str(file_path),
        base_version=0,
        changes=[{"type": "insert", "paraIdx": 0, "content": "new"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )

    assert result["applied"] is True
    assert [mode for name, mode in create_modes if name.startswith(".nasmd-perm-")] == [0o666]
    assert [
        mode
        for name, mode in create_modes
        if name.startswith(".nasmd-") and not name.startswith(".nasmd-perm-")
    ] == [0o600]


@pytest.mark.parametrize("failure_stage", ["owner", "xattr-snapshot", "xattr-apply"])
def test_metadata_failure_keeps_existing_target_and_cleans_temp(
    store, test_file, monkeypatch, failure_stage
):
    file_key = "mount-0:/test.md"
    original = "para one\n\npara two\n\npara three"
    store.init_file(file_key, test_file, original)

    def fail(operation):
        raise OSError(f"{operation} xattr failed")

    if failure_stage == "owner":
        monkeypatch.setattr(
            file_version_store_module.os,
            "fchown",
            lambda _fd, _uid, _gid: fail("owner"),
            raising=False,
        )
    elif failure_stage == "xattr-snapshot":
        monkeypatch.setattr(
            file_version_store_module,
            "_snapshot_xattrs",
            lambda _path: fail("snapshot"),
            raising=False,
        )
    else:
        monkeypatch.setattr(
            file_version_store_module,
            "_snapshot_xattrs",
            lambda _path: (("user.nasmd", b"metadata"),),
            raising=False,
        )
        monkeypatch.setattr(
            file_version_store_module,
            "_apply_xattrs",
            lambda _fd, _attrs: fail("apply"),
            raising=False,
        )

    result = store.apply_changes(
        file_key=file_key,
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "changed"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )

    _assert_failed_write_preserves_state(store, file_key, test_file, original, result)
    assert not list(Path(test_file).parent.glob(".nasmd-*"))


@pytest.mark.skipif(
    os.name != "posix"
    or not all(hasattr(os, name) for name in ("listxattr", "getxattr", "setxattr")),
    reason="POSIX xattrs are unavailable",
)
def test_atomic_replace_preserves_all_readable_posix_xattrs(store, tmp_path):
    file_path = tmp_path / "xattrs.md"
    file_path.write_text("before", encoding="utf-8")
    try:
        os.setxattr(file_path, "user.nasmd", b"metadata")
    except OSError as error:
        pytest.skip(f"filesystem does not support user xattrs: {error}")
    before = {name: os.getxattr(file_path, name) for name in os.listxattr(file_path)}
    file_key = "mount-0:/xattrs.md"
    store.init_file(file_key, str(file_path), "before")

    result = store.apply_changes(
        file_key=file_key,
        file_path=str(file_path),
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "after"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )

    after = {name: os.getxattr(file_path, name) for name in os.listxattr(file_path)}
    assert result["applied"] is True
    assert after == before


@pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "setxattr"),
    reason="POSIX ACL xattrs are unavailable",
)
def test_atomic_replace_preserves_posix_acl_xattr_when_supported(store, tmp_path):
    file_path = tmp_path / "acl.md"
    file_path.write_text("before", encoding="utf-8")
    acl = struct.pack("<I", 2) + b"".join(
        struct.pack("<HHI", tag, permissions, qualifier)
        for tag, permissions, qualifier in (
            (0x01, 0o6, 0xFFFFFFFF),
            (0x02, 0o4, os.geteuid() + 1),
            (0x04, 0o4, 0xFFFFFFFF),
            (0x10, 0o4, 0xFFFFFFFF),
            (0x20, 0o0, 0xFFFFFFFF),
        )
    )
    try:
        os.setxattr(file_path, "system.posix_acl_access", acl)
    except OSError as error:
        pytest.skip(f"filesystem does not support POSIX ACL xattrs: {error}")
    expected_acl = os.getxattr(file_path, "system.posix_acl_access")
    file_key = "mount-0:/acl.md"
    store.init_file(file_key, str(file_path), "before")

    result = store.apply_changes(
        file_key=file_key,
        file_path=str(file_path),
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "after"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )

    assert result["applied"] is True
    assert os.getxattr(file_path, "system.posix_acl_access") == expected_acl


@pytest.mark.skipif(os.name != "nt", reason="Windows alternate data streams")
def test_windows_existing_replace_preserves_alternate_data_stream(store, tmp_path):
    file_path = tmp_path / "streams.md"
    file_path.write_text("before", encoding="utf-8")
    stream_path = f"{file_path}:nasmd-metadata"
    try:
        Path(stream_path).write_text("stream metadata", encoding="utf-8")
    except OSError as error:
        pytest.skip(f"filesystem does not support alternate data streams: {error}")
    file_key = "mount-0:/streams.md"
    store.init_file(file_key, str(file_path), "before")

    result = store.apply_changes(
        file_key=file_key,
        file_path=str(file_path),
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "after"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )

    assert result["applied"] is True
    assert Path(stream_path).read_text(encoding="utf-8") == "stream metadata"


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL behavior")
def test_windows_existing_replace_preserves_dacl_descriptor(store, tmp_path):
    import ctypes
    from ctypes import wintypes

    get_file_security = ctypes.WinDLL("advapi32", use_last_error=True).GetFileSecurityW
    get_file_security.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPDWORD,
    )
    get_file_security.restype = wintypes.BOOL

    def read_dacl(path):
        needed = wintypes.DWORD()
        get_file_security(path, 0x00000004, None, 0, ctypes.byref(needed))
        descriptor = ctypes.create_string_buffer(needed.value)
        if not get_file_security(
            path,
            0x00000004,
            descriptor,
            needed.value,
            ctypes.byref(needed),
        ):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, ctypes.FormatError(error_code), path)
        return descriptor.raw

    file_path = tmp_path / "dacl.md"
    file_path.write_text("before", encoding="utf-8")
    expected_dacl = read_dacl(str(file_path))
    file_key = "mount-0:/dacl.md"
    store.init_file(file_key, str(file_path), "before")

    result = store.apply_changes(
        file_key=file_key,
        file_path=str(file_path),
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "after"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )

    assert result["applied"] is True
    assert read_dacl(str(file_path)) == expected_dacl


@pytest.mark.skipif(os.name != "nt", reason="Windows CopyFileW behavior")
def test_windows_existing_write_uses_copy_file_helper(store, tmp_path, monkeypatch):
    file_path = tmp_path / "replace-file.md"
    file_path.write_text("before", encoding="utf-8")
    file_key = "mount-0:/replace-file.md"
    store.init_file(file_key, str(file_path), "before")
    calls = []

    def observe_copy_file(target, replacement):
        calls.append((target, replacement))
        Path(replacement).write_bytes(Path(target).read_bytes())

    monkeypatch.setattr(
        file_version_store_module,
        "_copy_file_windows",
        observe_copy_file,
        raising=False,
    )

    result = store.apply_changes(
        file_key=file_key,
        file_path=str(file_path),
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "after"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )

    assert result["applied"] is True
    assert len(calls) == 1
    assert os.path.abspath(calls[0][0]) == os.path.abspath(file_path)


@pytest.mark.skipif(os.name != "nt", reason="Windows CopyFileW behavior")
def test_windows_copy_failure_preserves_existing_target(store, tmp_path, monkeypatch):
    file_path = tmp_path / "copy-failure.md"
    file_path.write_text("before", encoding="utf-8")
    file_key = "mount-0:/copy-failure.md"
    store.init_file(file_key, str(file_path), "before")
    calls = []

    def fail_copy_file(target, replacement):
        calls.append((target, replacement))
        Path(replacement).write_text("partial", encoding="utf-8")
        raise OSError("copy failed")

    monkeypatch.setattr(
        file_version_store_module,
        "_copy_file_windows",
        fail_copy_file,
        raising=False,
    )

    result = store.apply_changes(
        file_key=file_key,
        file_path=str(file_path),
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "after"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )

    assert len(calls) == 1
    assert result["errorCode"] == "write_failed"
    assert result["newVersion"] == 0
    assert file_path.read_text(encoding="utf-8") == "before"
    assert store.get_current_snapshot(file_key) == {"version": 0, "content": "before"}
    assert not list(tmp_path.glob(".nasmd-*"))


@pytest.mark.skipif(os.name != "nt", reason="Windows replacement behavior")
def test_windows_new_file_still_uses_os_replace(store, tmp_path, monkeypatch):
    file_path = tmp_path / "new-replace.md"
    file_key = "mount-0:/new-replace.md"
    store.init_file(file_key, str(file_path), "")
    calls = []
    original_replace = os.replace

    def observe_replace(src, dst):
        if os.path.abspath(dst) == os.path.abspath(file_path):
            calls.append((src, dst))
        return original_replace(src, dst)

    monkeypatch.setattr(
        file_version_store_module, "_replace_target", observe_replace, raising=False
    )
    monkeypatch.setattr(
        file_version_store_module,
        "_copy_file_windows",
        lambda _target, _replacement: pytest.fail("new files must not use CopyFileW"),
        raising=False,
    )

    result = store.apply_changes(
        file_key=file_key,
        file_path=str(file_path),
        base_version=0,
        changes=[{"type": "insert", "paraIdx": 0, "content": "new"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )

    assert result["applied"] is True
    assert len(calls) == 1


@pytest.mark.skipif(os.name != "nt", reason="Windows directory collision semantics")
def test_atomic_temp_retries_permission_error_for_existing_directory(tmp_path, monkeypatch):
    collision = tmp_path / ".nasmd-collision.tmp"
    collision.mkdir()
    tokens = iter(("collision", "available"))
    monkeypatch.setattr(file_version_store_module.secrets, "token_hex", lambda _size: next(tokens))

    fd, temp_path = file_version_store_module._create_atomic_temp(str(tmp_path))
    os.close(fd)
    os.remove(temp_path)

    assert Path(temp_path).name == ".nasmd-available.tmp"


def test_atomic_temp_propagates_unrelated_permission_error(tmp_path, monkeypatch):
    def deny_open(_path, _flags, _mode):
        raise PermissionError("access denied")

    monkeypatch.setattr(file_version_store_module.os, "open", deny_open)
    with pytest.raises(PermissionError, match="access denied"):
        file_version_store_module._create_atomic_temp(str(tmp_path))


def test_atomic_write_uses_fixed_short_temp_name(store, tmp_path, monkeypatch):
    name = "x" * 60 + ".md"
    file_path = tmp_path / name
    original = "before"
    file_path.write_text(original, encoding="utf-8")
    file_key = f"mount-0:/{name}"
    store.init_file(file_key, str(file_path), original)
    original_replace = os.replace
    temp_names = []

    def observe_replace(src, dst):
        if os.path.abspath(dst) == os.path.abspath(file_path):
            temp_names.append(os.path.basename(src))
        return original_replace(src, dst)

    monkeypatch.setattr(
        file_version_store_module, "_replace_target", observe_replace, raising=False
    )

    result = store.apply_changes(
        file_key=file_key,
        file_path=str(file_path),
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "after"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )

    assert result["applied"] is True
    assert file_path.read_text(encoding="utf-8") == "after"
    assert len(temp_names) == 1
    assert temp_names[0].startswith(".nasmd-")
    assert len(temp_names[0]) <= 32


@pytest.mark.skipif(os.name != "posix", reason="POSIX NAME_MAX behavior")
def test_atomic_write_supports_target_near_name_max(store, tmp_path):
    name = "x" * 235 + ".md"
    file_path = tmp_path / name
    file_path.write_text("before", encoding="utf-8")
    file_key = f"mount-0:/{name}"
    store.init_file(file_key, str(file_path), "before")

    result = store.apply_changes(
        file_key=file_key,
        file_path=str(file_path),
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "after"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )

    assert result["applied"] is True
    assert file_path.read_text(encoding="utf-8") == "after"


@pytest.mark.skipif(os.name != "posix", reason="POSIX ownership semantics")
def test_atomic_replace_preserves_posix_mode_uid_and_gid(store, tmp_path):
    file_path = tmp_path / "owned.md"
    file_path.write_text("before", encoding="utf-8")
    os.chmod(file_path, 0o2640)
    if os.geteuid() == 0:
        os.chown(file_path, 1000, 1000)
    original_stat = file_path.stat()
    file_key = "mount-0:/owned.md"
    store.init_file(file_key, str(file_path), "before")

    result = store.apply_changes(
        file_key=file_key,
        file_path=str(file_path),
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "after"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )

    replaced_stat = file_path.stat()
    assert result["applied"] is True
    assert stat.S_IMODE(replaced_stat.st_mode) == stat.S_IMODE(original_stat.st_mode)
    assert (replaced_stat.st_uid, replaced_stat.st_gid) == (
        original_stat.st_uid,
        original_stat.st_gid,
    )


@pytest.mark.skipif(os.name != "posix", reason="POSIX umask semantics")
def test_new_atomic_file_uses_normal_create_mode_under_umask(store, tmp_path):
    file_path = tmp_path / "umask.md"
    file_key = "mount-0:/umask.md"
    store.init_file(file_key, str(file_path), "")
    content_temp_modes = []

    def observe_before_replace(_prepared_path):
        content_temps = [
            path for path in tmp_path.glob(".nasmd-*") if not path.name.startswith(".nasmd-perm-")
        ]
        assert len(content_temps) == 1
        content_temp_modes.append(stat.S_IMODE(content_temps[0].stat().st_mode))

    previous_umask = os.umask(0o022)
    try:
        result = store.apply_changes(
            file_key=file_key,
            file_path=str(file_path),
            base_version=0,
            changes=[{"type": "insert", "paraIdx": 0, "content": "new"}],
            author_id="user1",
            author_name="Tester",
            author_color="#fff",
            before_write=observe_before_replace,
        )
    finally:
        os.umask(previous_umask)

    assert result["applied"] is True
    assert content_temp_modes == [0o600]
    assert stat.S_IMODE(file_path.stat().st_mode) == 0o644


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode semantics")
def test_existing_private_file_remains_private_after_atomic_replace(store, tmp_path):
    file_path = tmp_path / "private.md"
    file_path.write_text("before", encoding="utf-8")
    os.chmod(file_path, 0o600)
    file_key = "mount-0:/private.md"
    store.init_file(file_key, str(file_path), "before")

    result = store.apply_changes(
        file_key=file_key,
        file_path=str(file_path),
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "after"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )

    assert result["applied"] is True
    assert stat.S_IMODE(file_path.stat().st_mode) == 0o600


def test_apply_changes_with_merge(store, test_file):
    base = "para one\n\npara two\n\npara three"
    store.init_file("mount-0:/test.md", test_file, base)
    store.apply_changes(
        file_key="mount-0:/test.md",
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "A2"}],
        author_id="user1",
        author_name="A",
        author_color="#fff",
    )
    result = store.apply_changes(
        file_key="mount-0:/test.md",
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 2, "content": "C2"}],
        author_id="user2",
        author_name="B",
        author_color="#000",
        client_content="para one\n\npara two\n\nC2",
        base_content=base,
    )
    assert result["applied"] is True
    assert result["merged"] is True
    assert result["newVersion"] == 2
    assert "A2" in result["content"]
    assert "C2" in result["content"]


def test_apply_changes_same_paragraph_overwrite(store, test_file):
    base = "para one\n\npara two\n\npara three"
    store.init_file("mount-0:/test.md", test_file, base)
    store.apply_changes(
        file_key="mount-0:/test.md",
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 1, "content": "from_A"}],
        author_id="userA",
        author_name="A",
        author_color="#fff",
    )
    result = store.apply_changes(
        file_key="mount-0:/test.md",
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 1, "content": "from_B"}],
        author_id="userB",
        author_name="B",
        author_color="#000",
        client_content="para one\n\nfrom_B\n\npara three",
        base_content=base,
    )
    assert result["merged"] is True
    assert "from_B" in result["content"]
    assert "from_A" not in result["content"]


def test_apply_changes_empty_changes(store, test_file):
    store.init_file("mount-0:/test.md", test_file, "para one\n\npara two\n\npara three")
    result = store.apply_changes(
        file_key="mount-0:/test.md",
        file_path=test_file,
        base_version=0,
        changes=[],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )
    assert result["applied"] is False
    assert result["newVersion"] == 0


def test_apply_changes_concurrent_thread_safety(store, test_file):
    base = "para one\n\npara two\n\npara three"
    store.init_file("mount-0:/test.md", test_file, base)
    results = []
    lock = threading.Lock()

    def worker(idx):
        result = store.apply_changes(
            file_key="mount-0:/test.md",
            file_path=test_file,
            base_version=0,
            changes=[{"type": "insert", "paraIdx": 0, "content": f"insert_{idx}"}],
            author_id=f"user{idx}",
            author_name=f"U{idx}",
            author_color="#fff",
            client_content=f"insert_{idx}\n\n{base}",
            base_content=base,
        )
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(r["applied"] for r in results)
    versions = [r["newVersion"] for r in results]
    assert max(versions) == 5
    with open(test_file, encoding="utf-8") as f:
        final_content = f.read()
    for i in range(5):
        assert f"insert_{i}" in final_content


def test_large_diff_for_one_file_does_not_block_another_file_query(store, tmp_path, monkeypatch):
    file_a = tmp_path / "a.md"
    file_b = tmp_path / "b.md"
    base_a = "A\n\nB"
    target_a = "A-local\n\nB"
    base_b = "B-current"
    file_a.write_text(base_a, encoding="utf-8")
    file_b.write_text(base_b, encoding="utf-8")
    store.init_file("mount-0:/a.md", str(file_a), base_a)
    store.init_file("mount-0:/b.md", str(file_b), base_b)
    diff_started = threading.Event()
    release_diff = threading.Event()
    query_done = threading.Event()
    original_compute_diff = file_version_store_module.compute_diff

    def controlled_compute_diff(old_text, new_text):
        if old_text == base_a and new_text == target_a:
            diff_started.set()
            assert release_diff.wait(timeout=5)
        return original_compute_diff(old_text, new_text)

    monkeypatch.setattr(file_version_store_module, "compute_diff", controlled_compute_diff)
    apply_thread = threading.Thread(
        target=lambda: store.apply_changes(
            "mount-0:/a.md",
            str(file_a),
            0,
            compute_diff(base_a, target_a),
            "local",
            "Local",
            "#0f0",
            client_content=target_a,
            base_content=base_a,
        )
    )
    query_result = {}

    def query_other_file():
        query_result["version"] = store.get_current_version("mount-0:/b.md")
        query_result["content"] = store.get_current_content("mount-0:/b.md")
        query_done.set()

    apply_thread.start()
    assert diff_started.wait(timeout=5)
    query_thread = threading.Thread(target=query_other_file)
    query_thread.start()
    completed_while_diff_blocked = query_done.wait(timeout=0.5)
    release_diff.set()
    apply_thread.join(timeout=5)
    query_thread.join(timeout=5)

    assert completed_while_diff_blocked
    assert query_result == {"version": 0, "content": base_b}


def test_history_persist_for_one_file_does_not_block_another_file_apply(
    store, tmp_path, monkeypatch
):
    file_a = tmp_path / "history-a.md"
    file_b = tmp_path / "history-b.md"
    base_a = "A"
    base_b = "B"
    target_a = "A-local"
    target_b = "B-local"
    key_a = "mount-0:/history-a.md"
    key_b = "mount-0:/history-b.md"
    file_a.write_text(base_a, encoding="utf-8")
    file_b.write_text(base_b, encoding="utf-8")
    store.init_file(key_a, str(file_a), base_a)
    store.init_file(key_b, str(file_b), base_b)
    persist_started = threading.Event()
    release_persist = threading.Event()
    apply_b_done = threading.Event()
    original_persist = version_history._persist
    results = {}

    def controlled_persist(file_key, history, storage_dir=None):
        if file_key == key_a:
            persist_started.set()
            assert release_persist.wait(timeout=5)
        return original_persist(file_key, history, storage_dir=storage_dir)

    def apply(key, path, base, target):
        return store.apply_changes(
            key,
            str(path),
            0,
            compute_diff(base, target),
            "local",
            "Local",
            "#0f0",
            client_content=target,
            base_content=base,
        )

    monkeypatch.setattr(version_history, "_persist", controlled_persist)
    thread_a = threading.Thread(
        target=lambda: results.setdefault("a", apply(key_a, file_a, base_a, target_a))
    )

    def apply_b():
        results["b"] = apply(key_b, file_b, base_b, target_b)
        apply_b_done.set()

    thread_a.start()
    assert persist_started.wait(timeout=5)
    thread_b = threading.Thread(target=apply_b)
    thread_b.start()
    completed_while_a_persist_blocked = apply_b_done.wait(timeout=1)
    release_persist.set()
    thread_a.join(timeout=5)
    thread_b.join(timeout=5)

    assert completed_while_a_persist_blocked
    assert results["a"]["applied"] is True
    assert results["b"]["applied"] is True
    assert file_a.read_text(encoding="utf-8") == target_a
    assert file_b.read_text(encoding="utf-8") == target_b


def test_history_persistence_failure_is_logged_without_rolling_back_body(
    store, tmp_path, monkeypatch, caplog
):
    file_path = tmp_path / "history-warning.md"
    original = "before"
    target = "after"
    file_key = "mount-0:/history-warning.md"
    file_path.write_text(original, encoding="utf-8")
    store.init_file(file_key, str(file_path), original)
    original_replace = os.replace

    def fail_history_replace(src, dst):
        if os.fspath(dst).endswith(".json"):
            raise OSError("history persistence unavailable")
        return original_replace(src, dst)

    monkeypatch.setattr(version_history.os, "replace", fail_history_replace)

    with caplog.at_level(logging.WARNING, logger=version_history.__name__):
        result = store.apply_changes(
            file_key=file_key,
            file_path=str(file_path),
            base_version=0,
            changes=[{"type": "replace", "paraIdx": 0, "content": target}],
            author_id="user1",
            author_name="Tester",
            author_color="#fff",
        )

    assert result["applied"] is True
    assert result["newVersion"] == 1
    assert file_path.read_text(encoding="utf-8") == target
    warning = next(
        record
        for record in caplog.records
        if "Failed to persist version history" in record.getMessage()
    )
    assert warning.exc_info is not None


def test_history_updates_for_the_same_file_remain_serialized_and_persisted(store, monkeypatch):
    key = "mount-0:/same-history.md"
    persist_started = threading.Event()
    release_persist = threading.Event()
    second_persist_started = threading.Event()
    original_persist = version_history._persist
    errors = []

    def controlled_persist(file_key, history, storage_dir=None):
        newest_content = history.versions[-1].content_snapshot
        if newest_content == "version one":
            persist_started.set()
            assert release_persist.wait(timeout=5)
        elif newest_content == "version two":
            second_persist_started.set()
        return original_persist(file_key, history, storage_dir=storage_dir)

    def record(version, content):
        try:
            version_history.record_version(
                file_key=key,
                author_id="local",
                author_name="Local",
                author_color="#0f0",
                changes=[],
                content_snapshot=content,
                version=version,
                storage_dir=store._storage_dir,
            )
        except Exception as exc:
            errors.append(exc)

    monkeypatch.setattr(version_history, "_persist", controlled_persist)
    first = threading.Thread(target=record, args=(1, "version one"))
    first.start()
    assert persist_started.wait(timeout=5)
    second = threading.Thread(target=record, args=(2, "version two"))
    second.start()
    second_started_before_release = second_persist_started.wait(timeout=0.5)
    release_persist.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not second_started_before_release
    assert not errors
    loaded = version_history._load(key, storage_dir=store._storage_dir)
    assert loaded is not None
    assert [(entry.version, entry.content_snapshot) for entry in loaded.versions] == [
        (1, "version one"),
        (2, "version two"),
    ]


def test_apply_changes_3way_merge_with_shifting_indices(store, test_file):
    """When a prior version inserts paragraphs, subsequent edits based on older base_version shift correctly."""
    # Seed document: P0, P1, P2 (version 0)
    base = "P0\n\nP1\n\nP2"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    store.init_file("mount-0:/test.md", test_file, base)

    # User 1 inserts HEADER at index 0 -> version 1
    r1 = store.apply_changes(
        file_key="mount-0:/test.md",
        file_path=test_file,
        base_version=0,
        changes=[{"type": "insert", "paraIdx": 0, "content": "HEADER"}],
        author_id="user1",
        author_name="User1",
        author_color="#f00",
    )
    assert r1["applied"] is True
    assert r1["newVersion"] == 1

    # User 2 made an edit to P2 (index 2 in version 0), base_version=0 (stale!)
    r2 = store.apply_changes(
        file_key="mount-0:/test.md",
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 2, "content": "P2_EDITED"}],
        author_id="user2",
        author_name="User2",
        author_color="#0f0",
        client_content="P0\n\nP1\n\nP2_EDITED",
        base_content=base,
    )
    assert r2["applied"] is True
    assert r2["merged"] is True
    assert r2["newVersion"] == 2

    # Verify content on disk has both HEADER and P2_EDITED at the right places
    with open(test_file, encoding="utf-8") as f:
        disk_content = f.read()
    assert disk_content == "HEADER\n\nP0\n\nP1\n\nP2_EDITED"


def test_stale_change_rebases_through_each_version_coordinate_space(store, test_file):
    file_key = "mount-0:/test.md"
    initial_content = "A\n\nB\n\nC"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(initial_content)
    store.init_file(file_key, test_file, initial_content)

    store.apply_changes(
        file_key=file_key,
        file_path=test_file,
        base_version=0,
        changes=[{"type": "insert", "paraIdx": 0, "content": "X"}],
        author_id="user1",
        author_name="User1",
        author_color="#f00",
    )
    store.apply_changes(
        file_key=file_key,
        file_path=test_file,
        base_version=1,
        changes=[{"type": "insert", "paraIdx": 3, "content": "Y"}],
        author_id="user2",
        author_name="User2",
        author_color="#0f0",
    )

    result = store.apply_changes(
        file_key=file_key,
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 2, "content": "C-stale"}],
        author_id="user3",
        author_name="User3",
        author_color="#00f",
        client_content="A\n\nB\n\nC-stale",
        base_content=initial_content,
    )

    expected = "X\n\nA\n\nB\n\nY\n\nC-stale"
    assert result == {
        "applied": True,
        "merged": True,
        "newVersion": 3,
        "content": expected,
        "appliedChanges": [
            {
                "type": "replace",
                "paraIdx": 4,
                "content": "C-stale",
                "fallbackDelimiter": "",
            }
        ],
    }
    assert store.get_current_content(file_key) == expected
    with open(test_file, "rb") as f:
        assert f.read() == expected.replace("\n", os.linesep).encode("utf-8")


def test_stale_change_uses_pre_delete_paragraph_count(store, test_file):
    file_key = "mount-0:/test.md"
    initial_content = "A\n\nB\n\nC"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(initial_content)
    store.init_file(file_key, test_file, initial_content)

    store.apply_changes(
        file_key=file_key,
        file_path=test_file,
        base_version=0,
        changes=[{"type": "delete", "paraIdx": 2}],
        author_id="user1",
        author_name="User1",
        author_color="#f00",
    )

    result = store.apply_changes(
        file_key=file_key,
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 2, "content": "C-stale"}],
        author_id="user2",
        author_name="User2",
        author_color="#0f0",
        client_content="A\n\nB\n\nC-stale",
        base_content=initial_content,
    )

    expected = "A\n\nB\n\nC-stale"
    assert result == {
        "applied": True,
        "merged": True,
        "newVersion": 2,
        "content": expected,
        "appliedChanges": [{"type": "insert", "paraIdx": 2, "content": "C-stale", "delimiter": ""}],
    }
    assert store.get_current_content(file_key) == expected
    with open(test_file, "rb") as f:
        assert f.read() == expected.replace("\n", os.linesep).encode("utf-8")


def test_stale_change_requires_resync_when_history_version_is_missing(store, test_file):
    file_key = "mount-0:/test.md"
    initial_content = "A\n\nB"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(initial_content)
    store.init_file(file_key, test_file, initial_content)
    first_result = store.apply_changes(
        file_key=file_key,
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "A1"}],
        author_id="user1",
        author_name="User1",
        author_color="#f00",
    )
    del store._files[file_key].changes_by_version[1]
    with open(test_file, "rb") as f:
        disk_before = f.read()

    result = store.apply_changes(
        file_key=file_key,
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 1, "content": "B-stale"}],
        author_id="user2",
        author_name="User2",
        author_color="#0f0",
    )

    expected = first_result["content"]
    assert result == {
        "applied": False,
        "merged": False,
        "resyncRequired": True,
        "newVersion": 1,
        "content": expected,
    }
    assert store.get_current_version(file_key) == 1
    assert store.get_current_content(file_key) == expected
    with open(test_file, "rb") as f:
        assert f.read() == disk_before


def test_stale_change_requires_resync_after_external_reload(store, test_file):
    file_key = "mount-0:/test.md"
    initial_content = "A\n\nB"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(initial_content)
    store.init_file(file_key, test_file, initial_content)
    external_content = "external\n\ncontent"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(external_content)
    store.apply_external_change(file_key=file_key, file_path=test_file)
    with open(test_file, "rb") as f:
        disk_before = f.read()

    result = store.apply_changes(
        file_key=file_key,
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 1, "content": "B-stale"}],
        author_id="user2",
        author_name="User2",
        author_color="#0f0",
    )

    assert result == {
        "applied": False,
        "merged": False,
        "resyncRequired": True,
        "newVersion": 1,
        "content": external_content,
    }
    assert store.get_current_version(file_key) == 1
    assert store.get_current_content(file_key) == external_content
    with open(test_file, "rb") as f:
        assert f.read() == disk_before


def test_restart_stale_client_three_way_merges(tmp_path, test_file):
    key = "mount-0:/test.md"
    base = "A\n\nB\n\nC"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    first = FileVersionStore(storage_dir=str(tmp_path / ".version_history"))
    first.init_file(key, test_file, base)
    first.apply_changes(
        key,
        test_file,
        0,
        [{"type": "replace", "paraIdx": 0, "content": "A-remote"}],
        "remote",
        "Remote",
        "#f00",
        client_content="A-remote\n\nB\n\nC",
        base_content=base,
    )

    restarted = FileVersionStore(storage_dir=str(tmp_path / ".version_history"))
    restarted.init_file(key, test_file, "A-remote\n\nB\n\nC")
    result = restarted.apply_changes(
        key,
        test_file,
        0,
        [{"type": "replace", "paraIdx": 2, "content": "C-local"}],
        "local",
        "Local",
        "#0f0",
        client_content="A\n\nB\n\nC-local",
        base_content=base,
    )

    assert result["content"] == "A-remote\n\nB\n\nC-local"


def test_ahead_version_returns_resync_without_writing(store, test_file):
    key = "mount-0:/test.md"
    base = "A\n\nB"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    store.init_file(key, test_file, base)
    with open(test_file, "rb") as f:
        disk_before = f.read()
    before_write = Mock()
    history_before = _history_count(store, key)

    result = store.apply_changes(
        key,
        test_file,
        1,
        [{"type": "replace", "paraIdx": 1, "content": "B-local"}],
        "local",
        "Local",
        "#0f0",
        client_content="A\n\nB-local",
        base_content=base,
        before_write=before_write,
    )

    assert result == {
        "applied": False,
        "merged": False,
        "resyncRequired": True,
        "newVersion": 0,
        "content": base,
    }
    with open(test_file, "rb") as f:
        assert f.read() == disk_before
    assert _history_count(store, key) == history_before
    before_write.assert_not_called()


def test_missing_stale_base_content_returns_resync_without_writing(store, test_file):
    key = "mount-0:/test.md"
    base = "A\n\nB"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    store.init_file(key, test_file, base)
    first_result = store.apply_changes(
        key,
        test_file,
        0,
        [{"type": "replace", "paraIdx": 0, "content": "A-remote"}],
        "remote",
        "Remote",
        "#f00",
        client_content="A-remote\n\nB",
        base_content=base,
    )
    with open(test_file, "rb") as f:
        disk_before = f.read()
    before_write = Mock()
    history_before = _history_count(store, key)

    result = store.apply_changes(
        key,
        test_file,
        0,
        [{"type": "replace", "paraIdx": 1, "content": "B-local"}],
        "local",
        "Local",
        "#0f0",
        client_content="A\n\nB-local",
        before_write=before_write,
    )

    assert result == {
        "applied": False,
        "merged": False,
        "resyncRequired": True,
        "newVersion": 1,
        "content": first_result["content"],
    }
    with open(test_file, "rb") as f:
        assert f.read() == disk_before
    assert _history_count(store, key) == history_before
    before_write.assert_not_called()


def test_current_version_wrong_base_content_returns_resync_without_writing(store, test_file):
    key = "mount-0:/test.md"
    current = "A\n\nB"
    submitted_base = "wrong base"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(current)
    store.init_file(key, test_file, current)
    with open(test_file, "rb") as f:
        disk_before = f.read()
    before_write = Mock()
    history_before = _history_count(store, key)

    result = store.apply_changes(
        key,
        test_file,
        0,
        [],
        "local",
        "Local",
        "#0f0",
        client_content=submitted_base,
        base_content=submitted_base,
        before_write=before_write,
    )

    assert result == {
        "applied": False,
        "merged": False,
        "resyncRequired": True,
        "newVersion": 0,
        "content": current,
    }
    with open(test_file, "rb") as f:
        assert f.read() == disk_before
    assert _history_count(store, key) == history_before
    before_write.assert_not_called()


def test_current_version_save_writes_exact_target_content(store, test_file):
    key = "mount-0:/test.md"
    base = "A\n\nB\n\nC"
    target = "A\n\nB"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    store.init_file(key, test_file, base)
    prepared_contents = []

    def before_write(prepared_path):
        prepared_contents.append(Path(prepared_path).read_text(encoding="utf-8"))

    result = store.apply_changes(
        key,
        test_file,
        0,
        compute_diff(base, target),
        "local",
        "Local",
        "#0f0",
        client_content=target,
        base_content=base,
        before_write=before_write,
    )

    assert result["applied"] is True
    assert result["newVersion"] == 1
    assert result["content"] == target
    assert store.get_current_content(key) == target
    with open(test_file, "rb") as f:
        assert f.read() == target.replace("\n", os.linesep).encode("utf-8")
    assert prepared_contents == [target]


@pytest.mark.parametrize(
    ("base", "changes", "submitted", "reconstructed"),
    [
        (
            "A\n\nB\n\nC",
            [{"type": "delete", "paraIdx": 2}],
            "A\n\nB",
            "A\n\nB\n\n",
        ),
        (
            "A\n\nB",
            [{"type": "replace", "paraIdx": 1, "content": "B2"}],
            "A\n\nB2\n",
            "A\n\nB2",
        ),
    ],
    ids=["legacy-final-delete", "legacy-trailing-newline"],
)
def test_legacy_changes_canonicalize_from_declared_operations(
    store, test_file, base, changes, submitted, reconstructed
):
    key = "mount-0:/test.md"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    store.init_file(key, test_file, base)

    result = store.apply_changes(
        key,
        test_file,
        0,
        changes,
        "local",
        "Local",
        "#0f0",
        client_content=submitted,
        base_content=base,
    )

    assert result["applied"] is True
    assert result["content"] == reconstructed
    assert version_history.get_version_content(key, 0) == reconstructed
    with open(test_file, "rb") as f:
        assert f.read() == reconstructed.replace("\n", os.linesep).encode("utf-8")


def test_legacy_stale_text_edit_preserves_remote_tab_delimiter(store, test_file):
    key = "mount-0:/test.md"
    base = "A\n\nB"
    remote_content = "A\n\t\nB"
    legacy_content = "A-local\n\nB"
    expected = "A-local\n\t\nB"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    store.init_file(key, test_file, base)
    remote = store.apply_changes(
        key,
        test_file,
        0,
        compute_diff(base, remote_content),
        "remote",
        "Remote",
        "#f00",
        client_content=remote_content,
        base_content=base,
    )
    assert remote["applied"] is True
    prepared_contents = []

    def before_write(prepared_path):
        prepared_contents.append(Path(prepared_path).read_text(encoding="utf-8"))

    result = store.apply_changes(
        key,
        test_file,
        0,
        [{"type": "replace", "paraIdx": 0, "content": "A-local"}],
        "local",
        "Local",
        "#0f0",
        client_content=legacy_content,
        base_content=base,
        before_write=before_write,
    )

    assert result["applied"] is True
    assert result["merged"] is True
    assert result["content"] == expected
    assert result["appliedChanges"] == [
        {
            "type": "replace",
            "paraIdx": 0,
            "content": "A-local",
            "fallbackDelimiter": "\n\n",
        }
    ]
    assert version_history.get_version_content(key, 0) == expected
    assert prepared_contents == [expected]
    with open(test_file, "rb") as f:
        assert f.read() == expected.replace("\n", os.linesep).encode("utf-8")


@pytest.mark.parametrize(
    ("local_content", "expected"),
    [
        ("A-local\n\nB", "A-local\n\n\nB"),
        ("A-local\n \nB", "A-local\n \nB"),
    ],
    ids=["text-only-preserves-remote-delimiter", "explicit-delimiter-wins"],
)
def test_stale_replace_distinguishes_fallback_from_delimiter_intent(
    store, test_file, local_content, expected
):
    key = "mount-0:/test.md"
    base = "A\n\nB"
    remote_content = "A-remote\n\n\nB"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    store.init_file(key, test_file, base)
    remote = store.apply_changes(
        key,
        test_file,
        0,
        compute_diff(base, remote_content),
        "remote",
        "Remote",
        "#f00",
        client_content=remote_content,
        base_content=base,
    )
    assert remote["applied"] is True

    result = store.apply_changes(
        key,
        test_file,
        0,
        compute_diff(base, local_content),
        "local",
        "Local",
        "#0f0",
        client_content=local_content,
        base_content=base,
    )

    assert result["applied"] is True
    assert result["merged"] is True
    assert result["content"] == expected
    with open(test_file, encoding="utf-8") as f:
        assert f.read() == expected


def test_stale_large_diff_preserves_remote_anchor_edit(store, test_file):
    key = "mount-0:/test.md"
    base_paragraphs = [f"old-{idx}" for idx in range(300)]
    base_paragraphs += ["ANCHOR"]
    base_paragraphs += [f"old-tail-{idx}" for idx in range(300)]
    base = "\n\n".join(base_paragraphs)
    remote_paragraphs = list(base_paragraphs)
    remote_paragraphs[300] = "ANCHOR-REMOTE"
    remote_content = "\n\n".join(remote_paragraphs)
    local_paragraphs = [f"new-{idx}" for idx in range(300)]
    local_paragraphs += ["ANCHOR"]
    local_paragraphs += [f"new-tail-{idx}" for idx in range(300)]
    local_content = "\n\n".join(local_paragraphs)
    expected_paragraphs = list(local_paragraphs)
    expected_paragraphs[300] = "ANCHOR-REMOTE"
    expected = "\n\n".join(expected_paragraphs)
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    store.init_file(key, test_file, base)
    remote = store.apply_changes(
        key,
        test_file,
        0,
        compute_diff(base, remote_content),
        "remote",
        "Remote",
        "#f00",
        client_content=remote_content,
        base_content=base,
    )
    assert remote["applied"] is True

    result = store.apply_changes(
        key,
        test_file,
        0,
        compute_diff(base, local_content),
        "local",
        "Local",
        "#0f0",
        client_content=local_content,
        base_content=base,
    )

    assert result["applied"] is True
    assert result["merged"] is True
    assert result["content"] == expected
    with open(test_file, encoding="utf-8") as f:
        assert f.read() == expected


def test_stale_large_repeated_diff_preserves_remote_anchor_edit(store, test_file):
    key = "mount-0:/test.md"
    base_paragraphs = [f"old-{idx}" for idx in range(150)]
    base_paragraphs += ["REPEAT-A", "REPEAT-B"] * 150
    base_paragraphs += [f"old-tail-{idx}" for idx in range(150)]
    base = "\n\n".join(base_paragraphs)
    remote_paragraphs = list(base_paragraphs)
    remote_paragraphs[300] = "REPEAT-A-REMOTE"
    remote_content = "\n\n".join(remote_paragraphs)
    local_paragraphs = [f"new-{idx}" for idx in range(150)]
    local_paragraphs += ["REPEAT-A", "REPEAT-B"] * 150
    local_paragraphs += [f"new-tail-{idx}" for idx in range(150)]
    local_content = "\n\n".join(local_paragraphs)
    expected_paragraphs = list(local_paragraphs)
    expected_paragraphs[300] = "REPEAT-A-REMOTE"
    expected = "\n\n".join(expected_paragraphs)
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    store.init_file(key, test_file, base)
    store.apply_changes(
        key,
        test_file,
        0,
        compute_diff(base, remote_content),
        "remote",
        "Remote",
        "#f00",
        client_content=remote_content,
        base_content=base,
    )

    result = store.apply_changes(
        key,
        test_file,
        0,
        compute_diff(base, local_content),
        "local",
        "Local",
        "#0f0",
        client_content=local_content,
        base_content=base,
    )

    assert result["applied"] is True
    assert result["merged"] is True
    assert result["content"] == expected
    with open(test_file, encoding="utf-8") as f:
        assert f.read() == expected


def test_stale_repeated_rotation_preserves_remote_edit_in_longest_common_block(store, test_file):
    key = "mount-0:/test.md"
    base_paragraphs = ["A"] * 300 + ["B"] * 129
    base = "\n\n".join(base_paragraphs)
    remote_paragraphs = list(base_paragraphs)
    remote_paragraphs[150] = "A-REMOTE"
    remote_content = "\n\n".join(remote_paragraphs)
    local_paragraphs = ["B"] * 129 + ["A"] * 300
    local_content = "\n\n".join(local_paragraphs)
    expected_paragraphs = list(local_paragraphs)
    expected_paragraphs[279] = "A-REMOTE"
    expected = "\n\n".join(expected_paragraphs)
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    store.init_file(key, test_file, base)
    store.apply_changes(
        key,
        test_file,
        0,
        compute_diff(base, remote_content),
        "remote",
        "Remote",
        "#f00",
        client_content=remote_content,
        base_content=base,
    )

    result = store.apply_changes(
        key,
        test_file,
        0,
        compute_diff(base, local_content),
        "local",
        "Local",
        "#0f0",
        client_content=local_content,
        base_content=base,
    )

    assert result["applied"] is True
    assert result["merged"] is True
    assert result["content"] == expected
    with open(test_file, encoding="utf-8") as f:
        assert f.read() == expected


def test_diff_work_limit_returns_resync_without_side_effects(store, test_file, monkeypatch):
    key = "mount-0:/test.md"
    base = "A\n\nB"
    target = "A-local\n\nB"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    store.init_file(key, test_file, base)
    history_before = _history_count(store, key)
    before_write = Mock()

    def exhaust_diff(_old_text, _new_text):
        raise paragraph_diff.DiffWorkLimitExceeded

    monkeypatch.setattr(file_version_store_module, "compute_diff", exhaust_diff)

    result = store.apply_changes(
        key,
        test_file,
        0,
        [{"type": "replace", "paraIdx": 0, "content": "A-local"}],
        "local",
        "Local",
        "#0f0",
        client_content=target,
        base_content=base,
        before_write=before_write,
    )

    assert result == {
        "applied": False,
        "merged": False,
        "resyncRequired": True,
        "newVersion": 0,
        "content": base,
    }
    assert store.get_current_version(key) == 0
    assert store.get_current_content(key) == base
    assert _history_count(store, key) == history_before
    before_write.assert_not_called()
    with open(test_file, encoding="utf-8") as f:
        assert f.read() == base


def test_reconcile_read_failure_blocks_client_write(store, test_file, monkeypatch):
    key = "mount-0:/test.md"
    base = "A\n\nB"
    external = "A-external\n\nB"
    target = "A\n\nB-client"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    store.init_file(key, test_file, base)
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(external)

    original_open = open
    read_attempted = False

    def fail_reconcile_read(path, *args, **kwargs):
        nonlocal read_attempted
        mode = args[0] if args else "r"
        if os.fspath(path) == test_file and "r" in mode:
            read_attempted = True
            raise PermissionError("transient read failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(file_version_store_module, "open", fail_reconcile_read, raising=False)

    result = store.apply_changes(
        key,
        test_file,
        0,
        [{"type": "replace", "paraIdx": 1, "content": "B-client"}],
        "local",
        "Local",
        "#0f0",
        client_content=target,
        base_content=base,
    )

    assert read_attempted
    assert result == {
        "applied": False,
        "merged": False,
        "newVersion": 0,
        "content": base,
        "errorCode": "read_failed",
        "message": "Unable to verify current file state",
    }
    assert store.get_current_snapshot(key) == {"version": 0, "content": base}
    assert original_open(test_file, encoding="utf-8").read() == external


def test_stale_exact_delimiter_edit_three_way_merges(store, test_file):
    key = "mount-0:/test.md"
    base = "A\n\nB\n\nC"
    remote_content = "A-remote\n\nB\n\nC"
    local_content = "A\n\nB\n\nC\n"
    expected = "A-remote\n\nB\n\nC\n"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    store.init_file(key, test_file, base)
    store.apply_changes(
        key,
        test_file,
        0,
        compute_diff(base, remote_content),
        "remote",
        "Remote",
        "#f00",
        client_content=remote_content,
        base_content=base,
    )

    result = store.apply_changes(
        key,
        test_file,
        0,
        compute_diff(base, local_content),
        "local",
        "Local",
        "#0f0",
        client_content=local_content,
        base_content=base,
    )

    assert result["applied"] is True
    assert result["merged"] is True
    assert result["content"] == expected
    with open(test_file, "rb") as f:
        assert f.read() == expected.replace("\n", os.linesep).encode("utf-8")


@pytest.mark.parametrize(
    ("base", "local_content", "remote_content", "expected"),
    [
        (
            "A\n\nB",
            "A\n\n\nB",
            "A-remote\n\nB",
            "A-remote\n\n\nB",
        ),
        (
            "A\n\nB\n\nC",
            "A\n\nB",
            "A\n\nB-remote\n\nC",
            "A\n\nB-remote",
        ),
        (
            "A",
            "\nA",
            "A-remote",
            "\nA-remote",
        ),
        (
            "A\n\nB",
            "A\n \nB",
            "A-remote\n\nB",
            "A-remote\n \nB",
        ),
    ],
    ids=[
        "delimiter-edit-with-remote-text-edit",
        "final-delete-with-remote-preceding-edit",
        "prefix-edit-with-remote-text-edit",
        "whitespace-separator-edit-with-remote-text-edit",
    ],
)
def test_stale_formatting_only_edits_preserve_remote_text(
    store, test_file, base, local_content, remote_content, expected
):
    key = "mount-0:/test.md"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    store.init_file(key, test_file, base)
    remote = store.apply_changes(
        key,
        test_file,
        0,
        compute_diff(base, remote_content),
        "remote",
        "Remote",
        "#f00",
        client_content=remote_content,
        base_content=base,
    )
    assert remote["applied"] is True

    result = store.apply_changes(
        key,
        test_file,
        0,
        compute_diff(base, local_content),
        "local",
        "Local",
        "#0f0",
        client_content=local_content,
        base_content=base,
    )

    assert result["applied"] is True
    assert result["merged"] is True
    assert result["content"] == expected
    with open(test_file, encoding="utf-8") as f:
        assert f.read() == expected


@pytest.mark.parametrize(
    ("remote_changes", "client_changes", "current_content"),
    [
        (
            [{"type": "delete", "paraIdx": 1}],
            [{"type": "delete", "paraIdx": 1}],
            "A\n\nC",
        ),
        (
            [{"type": "replace", "paraIdx": 1, "content": "B2"}],
            [{"type": "replace", "paraIdx": 1, "content": "B2"}],
            "A\n\nB2\n\nC",
        ),
    ],
    ids=["delete-delete", "identical-replace"],
)
def test_stale_transformed_noop_has_no_side_effects(
    store, test_file, remote_changes, client_changes, current_content
):
    key = "mount-0:/test.md"
    base = "A\n\nB\n\nC"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    store.init_file(key, test_file, base)
    first = store.apply_changes(
        key,
        test_file,
        0,
        remote_changes,
        "remote",
        "Remote",
        "#f00",
        client_content=current_content,
        base_content=base,
    )
    assert first["applied"] is True
    with open(test_file, "rb") as f:
        disk_before = f.read()
    history_before = _history_count(store, key)
    before_write = Mock()

    result = store.apply_changes(
        key,
        test_file,
        0,
        client_changes,
        "local",
        "Local",
        "#0f0",
        client_content=current_content,
        base_content=base,
        before_write=before_write,
    )

    assert result["applied"] is False
    assert result["newVersion"] == 1
    assert result["content"] == current_content
    assert store.get_current_version(key) == 1
    assert _history_count(store, key) == history_before
    before_write.assert_not_called()
    with open(test_file, "rb") as f:
        assert f.read() == disk_before


def test_get_current_version(store, test_file):
    store.init_file("mount-0:/test.md", test_file, "para one")
    assert store.get_current_version("mount-0:/test.md") == 0
    store.apply_changes(
        file_key="mount-0:/test.md",
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "changed"}],
        author_id="u",
        author_name="U",
        author_color="#fff",
    )
    assert store.get_current_version("mount-0:/test.md") == 1


def test_get_current_content(store, test_file):
    store.init_file("mount-0:/test.md", test_file, "para one\n\npara two")
    result = store.apply_changes(
        file_key="mount-0:/test.md",
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "CHANGED"}],
        author_id="u",
        author_name="U",
        author_color="#fff",
    )
    assert store.get_current_content("mount-0:/test.md") == result["content"]


def test_apply_external_change(store, test_file):
    store.init_file("mount-0:/test.md", test_file, "para one\n\npara two\n\npara three")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("external content\n\nnew para")
    result = store.apply_external_change(
        file_key="mount-0:/test.md",
        file_path=test_file,
    )
    assert result["applied"] is True
    assert result["newVersion"] == 1
    assert "external content" in result["content"]


def test_init_file_restores_max_version_after_server_restart(tmp_path, test_file):
    """Simulate server restart with new FileVersionStore instance, verifying max version is restored."""
    store1 = FileVersionStore(storage_dir=str(tmp_path / ".version_history"))
    store1.init_file("mount-0:/test.md", test_file, "initial content")

    # Apply 3 sequential versions
    for i in range(3):
        store1.apply_changes(
            file_key="mount-0:/test.md",
            file_path=test_file,
            base_version=i,
            changes=[{"type": "replace", "paraIdx": 0, "content": f"content v{i + 1}"}],
            author_id="user1",
            author_name="Tester",
            author_color="#fff",
        )

    assert store1.get_current_version("mount-0:/test.md") == 3

    # Create new FileVersionStore (simulating a clean server restart)
    store2 = FileVersionStore(storage_dir=str(tmp_path / ".version_history"))
    restored_version = store2.init_file("mount-0:/test.md", test_file, "content v3")

    assert restored_version == 3
    assert store2.get_current_version("mount-0:/test.md") == 3

    # Subsequent edit advances monotonically to version 4
    result = store2.apply_changes(
        file_key="mount-0:/test.md",
        file_path=test_file,
        base_version=3,
        changes=[{"type": "replace", "paraIdx": 0, "content": "content v4"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
    )
    assert result["newVersion"] == 4


def test_init_file_restores_confirmed_content_before_applying_offline_change(tmp_path):
    storage_dir = str(tmp_path / ".version_history")
    file_path = tmp_path / "offline-change.md"
    file_key = "mount-0:/offline-change.md"
    file_path.write_text("A", encoding="utf-8")
    first_store = FileVersionStore(storage_dir=storage_dir)
    first_store.init_file(file_key, str(file_path), "A")
    result = first_store.apply_changes(
        file_key=file_key,
        file_path=str(file_path),
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "B"}],
        author_id="writer",
        author_name="Writer",
        author_color="#fff",
    )
    assert result["newVersion"] == 1
    file_path.write_text("external", encoding="utf-8")

    restarted_store = FileVersionStore(storage_dir=storage_dir)
    version = restarted_store.init_file(file_key, str(file_path), "external", persisted=True)

    assert version == 1
    assert restarted_store.get_current_snapshot(file_key) == {"version": 1, "content": "B"}
    external_result = restarted_store.apply_external_change(file_key, str(file_path))
    assert external_result == {"applied": True, "newVersion": 2, "content": "external"}


def test_version_history_lru_cache_eviction(tmp_path, monkeypatch):
    """When in-memory file histories exceed _MAX_CACHE_FILES, cold items are evicted and reloaded on demand."""
    from nas_md.webserver import version_history

    storage_dir = str(tmp_path / "lru_history")
    monkeypatch.setattr(version_history, "_MAX_CACHE_FILES", 3)

    # Record versions for 5 distinct files
    for i in range(1, 6):
        version_history.record_version(
            file_key=f"mount-0:/doc_{i}.md",
            author_id="user1",
            author_name="User",
            author_color="#fff",
            changes=[{"type": "insert", "paraIdx": 0, "content": f"v1 of doc {i}"}],
            content_snapshot=f"v1 of doc {i}",
            version=1,
            storage_dir=storage_dir,
        )

    # In-memory dictionary should be capped at 3
    assert len(version_history._histories) <= 3
    # doc_1.md was evicted from memory
    assert "mount-0:/doc_1.md" not in version_history._histories

    # Accessing doc_1 should reload it from disk into memory
    h1 = version_history.get_history("mount-0:/doc_1.md", storage_dir=storage_dir)
    assert len(h1) == 1
    assert h1[0]["version"] == 1
    assert "mount-0:/doc_1.md" in version_history._histories


def test_safe_filename_hashing_and_compatibility(tmp_path):
    """Hashed filenames should load legacy unhashed files and migrate them on write."""
    from nas_md.webserver import version_history
    import json
    import os

    storage_dir = str(tmp_path / "legacy_history")
    os.makedirs(storage_dir, exist_ok=True)
    file_key = "mount-0:/folder/中文文档-test.md"

    # 1. Manually write a legacy-style filename
    legacy_fn = version_history._safe_filename_legacy(file_key)
    legacy_path = os.path.join(storage_dir, legacy_fn)
    legacy_data = {
        "versions": [
            {
                "version": 1,
                "timestamp": 123456789.0,
                "author_id": "legacy_user",
                "author_name": "Legacy",
                "author_color": "#fff",
                "changes": [],
                "content_snapshot": "legacy doc content",
            }
        ]
    }
    with open(legacy_path, "w", encoding="utf-8") as f:
        json.dump(legacy_data, f)

    # 2. _load should successfully read the legacy file
    loaded = version_history._load(file_key, storage_dir=storage_dir)
    assert loaded is not None
    assert len(loaded.versions) == 1
    assert loaded.versions[0].author_name == "Legacy"

    # 3. New record_version should create the new hashed filename and delete the legacy file
    version_history.record_version(
        file_key=file_key,
        author_id="new_user",
        author_name="NewUser",
        author_color="#00f",
        changes=[],
        content_snapshot="new version content",
        version=2,
        storage_dir=storage_dir,
    )

    new_fn = version_history._safe_filename(file_key)
    new_path = os.path.join(storage_dir, new_fn)
    assert os.path.exists(new_path)
    assert not os.path.exists(legacy_path)


def test_declared_changes_must_reconstruct_client_content(store, test_file):
    base = "para one\n\npara two\n"
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(base)
    store.init_file("mount-0:/test.md", test_file, base)
    with open(test_file, "rb") as f:
        disk_before = f.read()
    before_write = Mock()
    history_before = _history_count(store, "mount-0:/test.md")

    result = store.apply_changes(
        file_key="mount-0:/test.md",
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "BOGUS"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
        client_content="para one edited\n\npara two\n",
        base_content=base,
        before_write=before_write,
    )

    assert result == {
        "applied": False,
        "merged": False,
        "resyncRequired": True,
        "newVersion": 0,
        "content": base,
    }
    with open(test_file, "rb") as f:
        assert f.read() == disk_before
    assert _history_count(store, "mount-0:/test.md") == history_before
    before_write.assert_not_called()
