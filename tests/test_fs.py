"""Tests for fs module - filesystem abstraction."""

import tempfile

import pytest

from nas_md.fs import (
    FS,
    File,
    DIR_USER_ROOT,
    DIR_ARCHIVE,
    DIR_JOURNAL,
    CHAT_FILENAME,
    display_name,
    hash_filename,
    short_hash,
    filename_from_header,
    sanitize_filename,
    unsanitize_filename,
    only_files,
    only_dirs,
    only_note_dirs,
    only_user_md_files,
    only_filenames,
    sort_by_ctime_desc,
    new_file,
    _is_local,
)


@pytest.fixture
def mem_fs():
    """Create a memory-backed FS for testing."""
    return FS("/testuser", backend="mem")


@pytest.fixture
def os_fs():
    """Create an OS-backed FS with temp directory."""
    tmpdir = tempfile.mkdtemp(prefix="filesmd_test_")
    fs = FS(tmpdir, backend="os")
    fs.create_system_dirs()
    yield fs
    # Cleanup
    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)


class TestMemFS:
    def test_create_dirs(self, mem_fs):
        mem_fs.create_dirs_if_not_exist("archive", "media", "journal")
        exists, _ = mem_fs.exists("archive", "")
        assert exists

    def test_write_and_read(self, mem_fs):
        mem_fs.write(DIR_USER_ROOT, "test.md", "Hello World")
        content, _ = mem_fs.read(DIR_USER_ROOT, "test.md")
        assert content == "Hello World"

    def test_exists(self, mem_fs):
        mem_fs.write(DIR_USER_ROOT, "exists.md", "content")
        exists, _ = mem_fs.exists(DIR_USER_ROOT, "exists.md")
        assert exists
        exists, _ = mem_fs.exists(DIR_USER_ROOT, "nonexistent.md")
        assert not exists

    def test_delete(self, mem_fs):
        mem_fs.write(DIR_USER_ROOT, "to_delete.md", "content")
        mem_fs.delete(DIR_USER_ROOT, "to_delete.md")
        exists, _ = mem_fs.exists(DIR_USER_ROOT, "to_delete.md")
        assert not exists

    def test_rename(self, mem_fs):
        mem_fs.write(DIR_USER_ROOT, "old.md", "content")
        mem_fs.rename(DIR_USER_ROOT, "old.md", DIR_USER_ROOT, "new.md")
        exists, _ = mem_fs.exists(DIR_USER_ROOT, "old.md")
        assert not exists
        content, _ = mem_fs.read(DIR_USER_ROOT, "new.md")
        assert content == "content"

    def test_make_dir(self, mem_fs):
        mem_fs.make_dir("subdir")
        exists, _ = mem_fs.exists("subdir", "")
        assert exists

    def test_files_and_dirs(self, mem_fs):
        mem_fs.write(DIR_USER_ROOT, "note1.md", "content1")
        mem_fs.write(DIR_USER_ROOT, "note2.md", "content2")
        mem_fs.make_dir("subdir")
        files, _ = mem_fs.files_and_dirs(DIR_USER_ROOT)
        names = [f.name for f in files]
        assert "note1.md" in names
        assert "note2.md" in names
        assert "subdir" in names

    def test_unhash(self, mem_fs):
        mem_fs.write(DIR_USER_ROOT, "test.md", "content")
        h = hash_filename("test.md")
        name, err = mem_fs.unhash(DIR_USER_ROOT, h[:5])
        assert err is None or not err
        assert name == "test.md"

    def test_safe_path_traversal(self, mem_fs):
        _path, err = mem_fs.safe_path("../../../etc/passwd", "")
        assert err  # Should return error for path traversal

    def test_safe_path_normal(self, mem_fs):
        path, err = mem_fs.safe_path(DIR_USER_ROOT, "test.md")
        assert err is None or not err
        assert "test.md" in path

    def test_touch_new_file(self, mem_fs):
        mem_fs.touch(DIR_USER_ROOT, "touched.md")
        exists, _ = mem_fs.exists(DIR_USER_ROOT, "touched.md")
        assert exists

    def test_touch_existing_file(self, mem_fs):
        mem_fs.write(DIR_USER_ROOT, "existing.md", "content")
        mem_fs.touch(DIR_USER_ROOT, "existing.md")
        content, _ = mem_fs.read(DIR_USER_ROOT, "existing.md")
        assert content == "content"

    def test_is_multiline(self, mem_fs):
        mem_fs.write(DIR_USER_ROOT, "single.md", "one line")
        mem_fs.write(DIR_USER_ROOT, "multi.md", "line1\nline2")
        is_ml, _ = mem_fs.is_multiline(DIR_USER_ROOT, "multi.md")
        assert is_ml

    def test_write_subdir(self, mem_fs):
        mem_fs.write("subdir", "file.md", "content")
        content, _ = mem_fs.read("subdir", "file.md")
        assert content == "content"

    def test_dirs(self, mem_fs):
        mem_fs.make_dir("dir1")
        mem_fs.make_dir("dir2")
        mem_fs.write(DIR_USER_ROOT, "file.md", "content")
        dirs, _ = mem_fs.dirs()
        names = [d.name for d in dirs]
        assert "dir1" in names
        assert "dir2" in names
        assert "file.md" not in names


class TestOsFS:
    def test_write_and_read(self, os_fs):
        os_fs.write(DIR_USER_ROOT, "test.md", "Hello OS")
        content, _ = os_fs.read(DIR_USER_ROOT, "test.md")
        assert content == "Hello OS"

    def test_create_system_dirs(self, os_fs):
        exists, _ = os_fs.exists(DIR_ARCHIVE, "")
        assert exists
        exists, _ = os_fs.exists(DIR_JOURNAL, "")
        assert exists

    def test_files_and_dirs(self, os_fs):
        os_fs.write(DIR_USER_ROOT, "note.md", "content")
        files, _ = os_fs.files_and_dirs(DIR_USER_ROOT)
        names = [f.name for f in files]
        assert "note.md" in names

    def test_mtime(self, os_fs):
        os_fs.write(DIR_USER_ROOT, "timed.md", "content")
        mtime, _ = os_fs.mtime(DIR_USER_ROOT, "timed.md")
        assert mtime > 0

    def test_ctime(self, os_fs):
        os_fs.write(DIR_USER_ROOT, "timed.md", "content")
        ctime, _ = os_fs.ctime(DIR_USER_ROOT, "timed.md")
        assert ctime > 0


class TestSanitizeFilename:
    def test_forbidden_chars(self):
        assert sanitize_filename("test<file") == "test＜file"
        assert sanitize_filename('test"file') == "test″file"
        assert sanitize_filename("test?file") == "test？file"
        assert sanitize_filename("test*file") == "test﹡file"

    def test_null_byte(self):
        assert "\x00" not in sanitize_filename("test\x00file")

    def test_forward_slash(self):
        assert sanitize_filename("test/file") == "test／file"

    def test_backslash(self):
        assert sanitize_filename("test\\file") == "test＼file"

    def test_unsanitize(self):
        sanitized = sanitize_filename('test<>:"\\|?*file')
        unsanitized = unsanitize_filename(sanitized)
        assert unsanitized == 'test<>:"\\|?*file'


class TestDisplayName:
    def test_removes_md_ext(self):
        assert display_name("test.md") == "Test"

    def test_ucfirst(self):
        assert display_name("hello.md") == "Hello"

    def test_strips_whitespace(self):
        assert display_name("  test.md  ") == "Test"


class TestHashFilename:
    def test_returns_11_chars(self):
        h = hash_filename("test.md")
        assert len(h) == 11

    def test_deterministic(self):
        assert hash_filename("test.md") == hash_filename("test.md")

    def test_different_for_different_names(self):
        assert hash_filename("a.md") != hash_filename("b.md")


class TestShortHash:
    def test_returns_5_chars(self):
        h = short_hash("test.md")
        assert len(h) == 5


class TestFilenameFromHeader:
    def test_adds_md_ext(self):
        assert filename_from_header("Test Header") == "Test Header.md"


class TestIsLocal:
    def test_normal_path(self):
        assert _is_local("dir/file.md")

    def test_traversal(self):
        assert not _is_local("../etc/passwd")

    def test_deep_traversal(self):
        assert not _is_local("dir/../../etc/passwd")

    def test_current_dir(self):
        assert _is_local("./file.md")

    def test_absolute_traversal(self):
        assert not _is_local("/../../../etc/passwd")


class TestFilterFunctions:
    def test_only_files(self):
        files = [
            File(name="a.md", is_dir=False),
            File(name="b_dir", is_dir=True),
            File(name="c.md", is_dir=False),
        ]
        result = only_files(files)
        assert len(result) == 2
        assert all(not f.is_dir for f in result)

    def test_only_dirs(self):
        files = [
            File(name="a.md", is_dir=False),
            File(name="b_dir", is_dir=True),
        ]
        result = only_dirs(files)
        assert len(result) == 1
        assert result[0].name == "b_dir"

    def test_only_filenames(self):
        files = [File(name="a.md"), File(name="b.md")]
        assert only_filenames(files) == ["a.md", "b.md"]

    def test_sort_by_ctime_desc(self):
        files = [
            File(name="a.md", ctime=100),
            File(name="b.md", ctime=300),
            File(name="c.md", ctime=200),
        ]
        result = sort_by_ctime_desc(files)
        assert [f.name for f in result] == ["b.md", "c.md", "a.md"]

    def test_only_user_md_files(self):
        files = [
            File(name="note.md", is_dir=False),
            File(name=CHAT_FILENAME, is_dir=False),
            File(name="image.png", is_dir=False),
            File(name="dir", is_dir=True),
        ]
        result = only_user_md_files(files)
        assert len(result) == 1
        assert result[0].name == "note.md"

    def test_only_note_dirs(self):
        files = [
            File(name="notes", is_dir=True),
            File(name=DIR_ARCHIVE, is_dir=True),
            File(name="file.md", is_dir=False),
        ]
        result = only_note_dirs(only_dirs(files))
        names = [d.name for d in result]
        assert "notes" in names
        assert DIR_ARCHIVE not in names

    def test_new_file(self):
        f = new_file("test.md", "abc123", "Test", 1000, True, False, "/")
        assert f.name == "test.md"
        assert f.hash == "abc123"
        assert f.display_name == "Test"
        assert f.ctime == 1000
        assert f.is_multiline is True
        assert f.is_dir is False
        assert f.parent_dir == "/"
