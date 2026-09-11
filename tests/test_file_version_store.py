# tests/test_file_version_store.py
import threading
import pytest
from nas_md.webserver.file_version_store import FileVersionStore
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
    store.init_file("mount-0:/test.md", test_file, "para one\n\npara two\n\npara three")
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
    )
    assert result["applied"] is True
    assert result["merged"] is True
    assert result["newVersion"] == 2
    assert "A2" in result["content"]
    assert "C2" in result["content"]


def test_apply_changes_same_paragraph_overwrite(store, test_file):
    store.init_file("mount-0:/test.md", test_file, "para one\n\npara two\n\npara three")
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
    store.init_file("mount-0:/test.md", test_file, "para one\n\npara two\n\npara three")
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
    store.init_file("mount-0:/test.md", test_file, "P0\n\nP1\n\nP2")

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
    )
    assert r2["applied"] is True
    assert r2["merged"] is True
    assert r2["newVersion"] == 2

    # Verify content on disk has both HEADER and P2_EDITED at the right places
    with open(test_file, encoding="utf-8") as f:
        disk_content = f.read()
    assert disk_content == "HEADER\n\nP0\n\nP1\n\nP2_EDITED"


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


def test_apply_changes_with_client_content(store, test_file):
    """apply_changes with client_content should write client content directly and compute canonical changes."""
    store.init_file("mount-0:/test.md", test_file, "para one\n\npara two\n")
    result = store.apply_changes(
        file_key="mount-0:/test.md",
        file_path=test_file,
        base_version=0,
        changes=[{"type": "replace", "paraIdx": 0, "content": "BOGUS"}],
        author_id="user1",
        author_name="Tester",
        author_color="#fff",
        client_content="para one edited\n\npara two\n",
    )
    assert result["applied"] is True
    assert result["newVersion"] == 1
    assert result["content"] == "para one edited\n\npara two\n"
    # Verify disk content is exact
    with open(test_file, encoding="utf-8") as f:
        assert f.read() == "para one edited\n\npara two\n"
    # Verify appliedChanges was computed canonically on server
    assert len(result["appliedChanges"]) == 1
    assert result["appliedChanges"][0]["type"] == "replace"
    assert result["appliedChanges"][0]["paraIdx"] == 0
    assert result["appliedChanges"][0]["content"] == "para one edited"
