"""Filesystem abstraction layer - provides user-isolated file operations."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from nas_md.config import server_cfg
from nas_md.pkg.txt.md import _hash as md_hash
from nas_md.pkg.txt.str import ucfirst, similar

# Callbacks for tracking
log_rename: Callable[[int, str, str], None] = lambda ts, old, new: None
log_delete: Callable[[int, str], None] = lambda ts, path: None

# Errors
ERR_QUOTA_EXCEEDED = "storage quota exceeded"
ERR_UNSAFE_PATH = "unsafe path, possible security issue"
ERR_CANNOT_UNHASH = "cannot unhash, maybe the file is missing"

# Directory constants
DIR_USER_ROOT = "/"
DIR_ARCHIVE = "archive"
DIR_MEDIA = "media"
DIR_JOURNAL = "journal"
DIR_HABITS = "habits"
DIR_INSIGHTS = "insights"

# Filename constants
CHAT_FILENAME = "Chat.md"
LATER_FILENAME = "Later.md"
DONE_FILENAME = "Done.md"
SHOP_FILENAME = "Shop.md"
WATCH_FILENAME = "Watch.md"
READ_FILENAME = "Read.md"

POMODORO_TASK = "Finished a break"
MD_EXT = ".md"
MIN_SEARCH_SIMILARITY = 70

# Forbidden characters in filenames (cross-platform)
FORBIDDEN_CHARS = {
    "<": "＜",
    ">": "＞",
    ":": "꞉",
    '"': "″",
    "|": "⼁",
    "\\": "＼",
    "?": "？",
    "*": "﹡",
    "\x00": "",
    "/": "／",
}


@dataclass
class File:
    """Represents a file or directory."""
    name: str = ""
    hash: str = ""
    display_name: str = ""
    ctime: int = 0
    is_multiline: bool = False
    is_dir: bool = False
    parent_dir: str = ""


class FS:
    """User-isolated filesystem with pluggable backend."""

    def __init__(self, root_path: str, backend: str = "os", quota_kb: int = 0) -> None:
        self.root_path = root_path.rstrip("/")
        self.backend = backend
        self.quota_kb = quota_kb
        self._mem: dict[str, bytes] = {} if backend == "mem" else None
        self._ensure_dir(root_path)

    def _ensure_dir(self, path: str) -> None:
        if self._mem is not None:
            path = path.rstrip("/")
            self._mem[path.encode()] = b""
        else:
            Path(path).mkdir(parents=True, exist_ok=True)

    def _read(self, path: str) -> bytes:
        if self._mem is not None:
            path = path.rstrip("/")
            data = self._mem.get(path.encode())
            if data is None:
                raise FileNotFoundError(path)
            return data
        return Path(path).read_bytes()

    def _write(self, path: str, data: bytes) -> None:
        if self._mem is not None:
            path = path.rstrip("/")
            self._mem[path.encode()] = data
        else:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(data)

    def _remove(self, path: str) -> None:
        if self._mem is not None:
            path = path.rstrip("/")
            self._mem.pop(path.encode(), None)
        else:
            Path(path).unlink()

    def _rename(self, old: str, new: str) -> None:
        if self._mem is not None:
            old = old.rstrip("/")
            new = new.rstrip("/")
            data = self._mem.pop(old.encode(), None)
            if data is not None:
                self._mem[new.encode()] = data
        else:
            Path(new).parent.mkdir(parents=True, exist_ok=True)
            Path(old).rename(new)

    def _exists(self, path: str) -> bool:
        if self._mem is not None:
            path = path.rstrip("/")
            return path.encode() in self._mem
        return Path(path).exists()

    def _is_dir(self, path: str) -> bool:
        if self._mem is not None:
            path = path.rstrip("/")
            return self._mem.get(path.encode(), None) == b""
        return Path(path).is_dir()

    def _stat(self, path: str) -> os.stat_result:
        if self._mem is not None:
            path = path.rstrip("/")
            data = self._mem.get(path.encode(), b"")
            # Return a fake stat with ctime in milliseconds
            now_ms = int(time.time() * 1000)
            st = os.stat_result((0, 0, 0, 0, 0, 0, len(data), now_ms, now_ms, now_ms))
            return st
        return os.stat(path)

    def _list_dir(self, path: str) -> list[str]:
        if self._mem is not None:
            prefix = path.rstrip("/") + "/"
            results = set()
            for k in self._mem:
                k_str = k.decode()
                if k_str.startswith(prefix):
                    rest = k_str[len(prefix):]
                    if "/" not in rest:
                        results.add(rest)
            return sorted(results)
        return sorted(os.listdir(path))

    def _walk(self, path: str):
        """Yield (dirpath, dirnames, filenames) like os.walk."""
        if self._mem is not None:
            prefix = path.rstrip("/") + "/"
            dirs = set()
            files = set()
            for k in self._mem:
                k_str = k.decode()
                if k_str.startswith(prefix) and k_str != path:
                    rest = k_str[len(prefix):]
                    parts = rest.split("/", 1)
                    if len(parts) == 2:
                        dirs.add(parts[0])
                    elif self._mem[k] != b"":
                        files.add(parts[0])
            yield path, sorted(dirs), sorted(files)
        else:
            yield from os.walk(path)

    def create_dirs_if_not_exist(self, *dirs: str) -> None:
        for d in dirs:
            if d == DIR_USER_ROOT:
                continue
            user_path = os.path.join(self.root_path, d)
            if not self._exists(user_path):
                self._ensure_dir(user_path)

    def create_system_dirs(self) -> None:
        self.create_dirs_if_not_exist(DIR_ARCHIVE, DIR_MEDIA, DIR_JOURNAL)

    def exists(self, dir_name: str, filename: str) -> tuple[bool, None]:
        file_path, err = self.safe_path(dir_name, filename)
        if err:
            return False, None
        return self._exists(file_path), None

    def read(self, dir_name: str, filename: str) -> tuple[str, None]:
        file_path, err = self.safe_path(dir_name, filename)
        if err:
            return "", None
        try:
            return self._read(file_path).decode(), None
        except FileNotFoundError:
            return "", None

    def write(self, dir_name: str, filename: str, content: str) -> None:
        file_path, err = self.safe_path(dir_name, filename)
        if err:
            raise ValueError(err)
        # Ensure parent dirs exist
        if self._mem is not None:
            parent = os.path.dirname(file_path)
            if parent and not self._exists(parent):
                self._ensure_dir(parent)
        else:
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        self._write(file_path, content.encode())

    def make_dir(self, dir_name: str) -> None:
        dir_path, err = self.safe_path(dir_name, "")
        if err:
            raise ValueError(err)
        self._ensure_dir(dir_path)

    def delete(self, dir_name: str, filename: str) -> None:
        file_path, err = self.safe_path(dir_name, filename)
        if err:
            raise ValueError(err)
        self._remove(file_path)
        log_delete(int(time.time()), file_path)

    def rename(self, old_dir: str, old_filename: str, new_dir: str, new_filename: str) -> None:
        old_path, err = self.safe_path(old_dir, old_filename)
        if err:
            raise ValueError(err)
        new_path, err = self.safe_path(new_dir, new_filename)
        if err:
            raise ValueError(err)
        self.create_dirs_if_not_exist(old_dir, new_dir)
        self._rename(old_path, new_path)

    def unhash(self, dir_name: str, filename_hash: str) -> tuple[str, None]:
        if dir_name == DIR_USER_ROOT and filename_hash == DIR_USER_ROOT:
            return DIR_USER_ROOT, None
        files_and_dirs, _ = self.files_and_dirs(dir_name)
        for f in files_and_dirs:
            if f.hash.startswith(filename_hash):
                return f.name, None
        # Fallback: treat hash as filename prefix
        for f in files_and_dirs:
            if f.name.startswith(filename_hash):
                return f.name, None
        return "", ValueError(f"cannot unhash '{filename_hash}' in '{dir_name}': {ERR_CANNOT_UNHASH}")

    def files_and_dirs(self, dir_name: str) -> tuple[list[File], None]:
        user_path, err = self.safe_path(dir_name, "")
        if err:
            return [], ValueError(err)
        try:
            entries = self._list_dir(user_path)
        except FileNotFoundError:
            return [], None

        ignored = {".", "..", ".obsidian", ".gitignore", ".DS_Store", ".git"}
        files = []
        for entry in entries:
            if entry in ignored:
                continue
            full_path = os.path.join(user_path, entry)
            is_dir = self._is_dir(full_path)
            try:
                st = self._stat(full_path)
                ctime = int(st.st_ctime * 1000) if hasattr(st, 'st_ctime') else 0
            except Exception:
                ctime = 0
            size = 0
            try:
                if not is_dir:
                    data = self._read(full_path)
                    size = len(data)
            except Exception:
                pass
            files.append(File(
                name=entry,
                hash=md_hash(entry),
                display_name=display_name(entry),
                ctime=ctime,
                is_multiline=size > 0,
                is_dir=is_dir,
                parent_dir=dir_name,
            ))
        return files, None

    def dirs(self) -> tuple[list[File], None]:
        files, err = self.files_and_dirs(DIR_USER_ROOT)
        if err:
            return [], err
        result = []
        for f in files:
            file_path, _ = self.safe_path(DIR_USER_ROOT, f.name)
            if self._is_dir(file_path):
                result.append(f)
        return result, None

    def is_multiline(self, dir_name: str, filename: str) -> tuple[bool, None]:
        content, _ = self.read(dir_name, filename)
        content = content.strip()
        return len(content) > 0, None

    def search_files_by_name(self, query: str) -> tuple[list[File], None]:
        query = query.lower().strip()
        if "/" in query:
            return [], ValueError(f"search notes: unsafe query '{query}': {ERR_UNSAFE_PATH}")

        supposed_dir = ""
        search = ""
        dir_exists, _ = self.exists(DIR_USER_ROOT, query)
        if dir_exists:
            supposed_dir = query
        else:
            parts = query.split(None, 1)
            supposed_dir = parts[0]
            if len(parts) > 1:
                search = parts[1].strip()

        root_path, _ = self.safe_path(DIR_USER_ROOT, "")
        notes = []
        self._walk_collect_md(root_path, root_path, notes, 0)
        notes = only_user_md_files(notes)

        if supposed_dir:
            pruned = []
            for n in notes:
                top = n.parent_dir.split("/")[0] if n.parent_dir else ""
                if top == DIR_USER_ROOT:
                    top = ""
                if top.startswith(supposed_dir):
                    pruned.append(n)
            if pruned:
                notes = pruned
            else:
                search = query

        notes = sort_by_ctime_desc(notes)
        matched = []
        for note in notes:
            is_wildcard = len(search) == 0
            is_substring = search in note.display_name.lower()
            is_similar = similar(note.display_name.lower(), search) > MIN_SEARCH_SIMILARITY
            if is_wildcard or is_substring or is_similar:
                matched.append(note)
        return matched, None

    def _walk_collect_md(self, root: str, current: str, notes: list[File], depth: int) -> None:
        try:
            entries = self._list_dir(current)
        except FileNotFoundError:
            return
        for entry in entries:
            if entry.startswith("."):
                continue
            full_path = os.path.join(current, entry)
            if self._is_dir(full_path):
                rel = os.path.relpath(full_path, root)
                if rel != "." and rel.count(os.sep) >= 10:
                    continue
                self._walk_collect_md(root, full_path, notes, depth + 1)
            else:
                if not entry.endswith(MD_EXT):
                    continue
                rel_dir = os.path.relpath(os.path.dirname(full_path), root)
                if rel_dir == ".":
                    rel_dir = DIR_USER_ROOT
                try:
                    st = self._stat(full_path)
                    ctime = int(st.st_ctime * 1000) if hasattr(st, 'st_ctime') else 0
                except Exception:
                    ctime = 0
                try:
                    size = len(self._read(full_path))
                except Exception:
                    size = 0
                notes.append(File(
                    name=entry,
                    hash=md_hash(entry),
                    display_name=display_name(entry),
                    ctime=ctime,
                    is_multiline=size > 0,
                    is_dir=False,
                    parent_dir=rel_dir,
                ))

    def touch(self, dir_name: str, filename: str) -> None:
        file_path, err = self.safe_path(dir_name, filename)
        if err:
            raise ValueError(err)
        exists, _ = self.exists(dir_name, filename)
        if exists:
            now = time.time()
            if self._mem is None:
                os.utime(file_path, (now, now))
        else:
            self.write(dir_name, filename, "")

    def ctime(self, dir_name: str, filename: str) -> tuple[int, None]:
        file_path, err = self.safe_path(dir_name, filename)
        if err:
            return 0, ValueError(err)
        try:
            st = self._stat(file_path)
            return int(st.st_ctime * 1000), None
        except FileNotFoundError:
            return 0, FileNotFoundError(f"file not found: {file_path}")

    def mtime(self, dir_name: str, filename: str) -> tuple[int, None]:
        file_path, err = self.safe_path(dir_name, filename)
        if err:
            return 0, ValueError(err)
        try:
            st = self._stat(file_path)
            return int(st.st_mtime * 1000), None
        except FileNotFoundError:
            return 0, FileNotFoundError(f"file not found: {file_path}")

    def mtimes(self, root: str, *extensions: str) -> tuple[dict[str, int], None]:
        root_path, err = self.safe_path(root, "")
        if err:
            return {}, ValueError(err)
        result: dict[str, int] = {}
        for dirpath, dirnames, filenames in self._walk(root_path):
            for fn in filenames:
                if fn.startswith("."):
                    continue
                if extensions:
                    ext = os.path.splitext(fn)[1]
                    if ext not in extensions:
                        continue
                full_path = os.path.join(dirpath, fn)
                try:
                    st = self._stat(full_path)
                    rel_path = os.path.relpath(full_path, root_path)
                    if rel_path == ".":
                        rel_path = "."
                    result[rel_path] = int(st.st_mtime * 1000)
                except Exception:
                    pass
        return result, None

    def safe_path(self, dir_name: str, filename: str) -> tuple[str, None]:
        """Return safe absolute path, preventing directory traversal."""
        if dir_name == "/":
            if not filename:
                return self.root_path, None
            relative_path = filename
        else:
            relative_path = os.path.join(dir_name, filename)

        # Check for path traversal
        if not _is_local(relative_path):
            return "", ValueError(ERR_UNSAFE_PATH)

        return os.path.join(self.root_path, relative_path), None


def _is_local(path: str) -> bool:
    """Check if path is local (doesn't escape via ..)."""
    parts = path.replace("\\", "/").split("/")
    depth = 0
    for p in parts:
        if p == "..":
            depth -= 1
        elif p and p != ".":
            depth += 1
        if depth < 0:
            return False
    return True


def sanitize_filename(filename: str) -> str:
    for forbidden, safe in FORBIDDEN_CHARS.items():
        filename = filename.replace(forbidden, safe)
    return filename


def unsanitize_filename(filename: str) -> str:
    for forbidden, safe in FORBIDDEN_CHARS.items():
        if safe:
            filename = filename.replace(safe, forbidden)
    return filename


def display_name(filename: str) -> str:
    return ucfirst(filename.strip().removesuffix(MD_EXT))


def hash_filename(filename: str) -> str:
    return hashlib.md5(filename.encode()).hexdigest()[:11]


def short_hash(filename: str) -> str:
    return hashlib.md5(filename.encode()).hexdigest()[:5]


def filename_from_header(header: str) -> str:
    return ucfirst(header) + MD_EXT


def is_checklist_item(filename: str) -> bool:
    return bool(re.match(r'^-.*?-(.+)', filename))


def exclude_checklists(dirs: list[File]) -> list[File]:
    return [d for d in dirs if not (d.name.startswith("_") and d.name.endswith("_"))]


def exclude_system_dirs(dirs: list[File]) -> list[File]:
    system = {DIR_MEDIA, DIR_ARCHIVE, DIR_JOURNAL, DIR_INSIGHTS, "img"}
    return [d for d in dirs if d.name not in system]


def exclude_config(files: list[File]) -> list[File]:
    return [f for f in files if not (f.name == server_cfg.config_filename and f.parent_dir == DIR_USER_ROOT)]


def only_note_dirs(dirs: list[File]) -> list[File]:
    return exclude_system_dirs(exclude_checklists(dirs))


def only_checklists(dirs: list[File]) -> list[File]:
    entries = only_files(dirs)
    checklists = []
    for entry in entries:
        if not entry.name.endswith(MD_EXT):
            continue
        fn = entry.name[:-3]  # Remove .md
        if fn.endswith("_") or entry.name in (SHOP_FILENAME, WATCH_FILENAME, READ_FILENAME):
            checklists.append(entry)
    return checklists


def only_user_md_files(entries: list[File]) -> list[File]:
    system_files = {CHAT_FILENAME, LATER_FILENAME, DONE_FILENAME, SHOP_FILENAME, WATCH_FILENAME, READ_FILENAME}
    return [f for f in entries if not f.is_dir and f.name.endswith(MD_EXT) and f.name not in system_files]


def only_files(entries: list[File]) -> list[File]:
    return [f for f in entries if not f.is_dir]


def only_dirs(entries: list[File]) -> list[File]:
    return [f for f in entries if f.is_dir]


def only_user_dirs(entries: list[File]) -> list[File]:
    result = []
    for f in entries:
        if not f.is_dir:
            continue
        try:
            int(f.name)
            result.append(f)
        except ValueError:
            pass
    return result


def only_filenames(entries: list[File]) -> list[str]:
    return [e.name for e in entries]


def sort_by_ctime_desc(entries: list[File]) -> list[File]:
    return sorted(entries, key=lambda e: e.ctime, reverse=True)


def new_user_fs(user_id: int) -> FS:
    """Create a new FS for a specific user with OS backend."""
    user_abs_path = os.path.join(server_cfg.storage_dir, str(user_id))
    quota_kb = server_cfg.storage_quota_kb
    if _is_unlimited_quota(user_id, server_cfg.unlimited_quota_ids):
        quota_kb = 0
    return FS(user_abs_path, backend="os", quota_kb=quota_kb)


def new_fs(abs_root_path: str, backend: str = "os", quota_kb: int = 0) -> FS:
    return FS(abs_root_path, backend=backend, quota_kb=quota_kb)


def new_file(name: str, hash_val: str, display_name: str, ctime: int,
             is_multiline: bool, is_dir: bool, parent_dir: str) -> File:
    return File(name=name, hash=hash_val, display_name=display_name,
                ctime=ctime, is_multiline=is_multiline, is_dir=is_dir, parent_dir=parent_dir)


def _is_unlimited_quota(user_id: int, unlimited_ids: str) -> bool:
    if not unlimited_ids:
        return False
    for id_str in unlimited_ids.split(","):
        try:
            if int(id_str.strip()) == user_id:
                return True
        except ValueError:
            pass
    return False
