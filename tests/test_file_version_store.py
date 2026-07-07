# tests/test_file_version_store.py
import threading
import pytest
from nas_md.webserver.file_version_store import FileVersionStore


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
