# tests/test_file_version_store.py
import os
import threading
from unittest.mock import Mock

import pytest
from nas_md.webserver.file_version_store import FileVersionStore
from nas_md.webserver.paragraph_diff import compute_diff
from nas_md.webserver import version_history


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


def test_init_file_new(store, test_file):
    version = store.init_file("mount-0:/test.md", test_file, "para one\n\npara two\n\npara three")
    assert version == 0


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


def test_apply_changes_3way_merge_with_shifting_indices(store, test_file):
    """When a prior version inserts paragraphs, subsequent edits based on older base_version shift correctly."""
    # Seed document: P0, P1, P2 (version 0)
    base = "P0\n\nP1\n\nP2"
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
            {"type": "replace", "paraIdx": 4, "content": "C-stale", "delimiter": ""}
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
    before_write = Mock()

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
    before_write.assert_called_once_with(target)


@pytest.mark.parametrize(
    ("base", "changes", "target"),
    [
        (
            "A\n\nB\n\nC",
            [{"type": "delete", "paraIdx": 2}],
            "A\n\nB",
        ),
        (
            "A\n\nB",
            [{"type": "replace", "paraIdx": 1, "content": "B2"}],
            "A\n\nB2\n",
        ),
    ],
    ids=["legacy-final-delete", "legacy-trailing-newline"],
)
def test_legacy_changes_accept_exact_delimiter_differences(store, test_file, base, changes, target):
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
        client_content=target,
        base_content=base,
    )

    assert result["applied"] is True
    assert result["content"] == target
    assert any("delimiter" in change for change in result["appliedChanges"])
    with open(test_file, "rb") as f:
        assert f.read() == target.replace("\n", os.linesep).encode("utf-8")


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
            changes=[{"type": "replace", "paraIdx": 0, "content": f"content v{i+1}"}],
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
