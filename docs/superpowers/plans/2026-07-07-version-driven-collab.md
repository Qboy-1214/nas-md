# 版本号驱动的段落级协同编辑 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用整数版本号替代mtime乐观锁，所有服务器挂载的修改走单一 `POST /changes` 路径，实现段落级合并、消除并发保存竞态。

**Architecture:** 服务器维护 `file_key -> {version, content}` 内存存储（带锁），所有写入通过 `apply_changes()` 单一入口。客户端用 `baseVersion` 提交diff，服务器做段落级合并。mtime轮询被移除，改由SSE驱动。watchdog监听外部修改（仅host挂载）。

**Tech Stack:** Python 3 (stdlib + watchdog), Vanilla JS前端, ThreadingHTTPServer, SSE

**设计文档:** `docs/superpowers/specs/2026-07-07-version-driven-collab-design.md`

---

## 文件结构

**新增文件**:
- `nas_md/webserver/file_version_store.py` — 版本号存储+合并逻辑（核心模块）
- `nas_md/webserver/file_watcher.py` — watchdog文件监听，仅host挂载
- `tests/test_file_version_store.py` — 版本号存储测试
- `tests/test_file_watcher.py` — 文件监听测试

**修改文件**:
- `nas_md/webserver/paragraph_diff.py` — 新增 `apply_changes()` 和 `merge_changes()` 函数
- `nas_md/webserver/version_history.py` — VersionEntry新增 `version` 字段
- `nas_md/webserver/__init__.py` — 新增 `POST /api/mounts/{id}/changes` 端点，GET /file返回版本号，PUT /file标记deprecated
- `web/files.js` — 新增 `submitChanges()` 方法
- `web/app.js` — 重写 `saveFile()`，移除 `pollCurrentFile/startFilePoll/stopFilePoll/state.fileMtimes`
- `web/sync_layer.js` — 移除mtime同步，改为更新 `state.baseVersion/baseContent`

---

## Task 1: paragraph_diff 新增 apply_changes 函数

**Files:**
- Modify: `nas_md/webserver/paragraph_diff.py`
- Test: `tests/test_paragraph_diff.py`

- [ ] **Step 1: 写 apply_changes 的失败测试**

在 `tests/test_paragraph_diff.py` 末尾追加：

```python
from nas_md.webserver.paragraph_diff import apply_changes


def test_apply_changes_replace():
    """apply_changes 应将 replace change 应用到文本。"""
    text = "para one\n\npara two\n\npara three"
    changes = [{"type": "replace", "paraIdx": 1, "content": "CHANGED"}]
    result = apply_changes(text, changes)
    assert result == "para one\n\nCHANGED\n\npara three"


def test_apply_changes_insert():
    """apply_changes 应在指定位置插入段落。"""
    text = "para one\n\npara three"
    changes = [{"type": "insert", "paraIdx": 1, "content": "para two"}]
    result = apply_changes(text, changes)
    assert result == "para one\n\npara two\n\npara three"


def test_apply_changes_delete():
    """apply_changes 应删除指定段落。"""
    text = "para one\n\npara two\n\npara three"
    changes = [{"type": "delete", "paraIdx": 1}]
    result = apply_changes(text, changes)
    assert result == "para one\n\npara three"


def test_apply_changes_empty_changes():
    """空 changes 列表应返回原文本。"""
    text = "para one\n\npara two"
    result = apply_changes(text, [])
    assert result == text


def test_apply_changes_multiple():
    """多个 changes 应按顺序应用（paraIdx基于原文本位置）。"""
    text = "A\n\nB\n\nC"
    changes = [
        {"type": "replace", "paraIdx": 0, "content": "A2"},
        {"type": "insert", "paraIdx": 2, "content": "B2"},
    ]
    result = apply_changes(text, changes)
    assert result == "A2\n\nB\n\nB2\n\nC"


def test_apply_changes_para_idx_out_of_range():
    """paraIdx 越界时 replace 应忽略，insert 应追加到末尾。"""
    text = "para one"
    changes = [
        {"type": "replace", "paraIdx": 5, "content": "X"},
        {"type": "insert", "paraIdx": 10, "content": "appended"},
    ]
    result = apply_changes(text, changes)
    assert result == "para one\n\nappended"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_paragraph_diff.py::test_apply_changes_replace -v`
Expected: FAIL with ImportError (apply_changes not defined)

- [ ] **Step 3: 实现 apply_changes**

在 `nas_md/webserver/paragraph_diff.py` 末尾追加：

```python
def apply_changes(text: str, changes: list) -> str:
    """将 changes 应用到 text，返回新文本。

    changes 中的 paraIdx 基于**原文本**的段落位置。
    采用"重建"策略：把原文本切成段落列表，根据changes构建结果。
    """
    if not changes:
        return text

    paragraphs = split_paragraphs(text)

    # 分类 changes
    replaces = {}  # paraIdx -> new_content
    deletes = set()  # paraIdx
    inserts = []  # list of (paraIdx, content)

    for ch in changes:
        t = ch.get("type")
        idx = ch.get("paraIdx", 0)
        if t == "replace":
            replaces[idx] = ch.get("content", "")
        elif t == "delete":
            deletes.add(idx)
        elif t == "insert":
            inserts.append((idx, ch.get("content", "")))

    # 按 paraIdx 分组 inserts
    inserts_by_idx = {}
    for idx, content in inserts:
        inserts_by_idx.setdefault(idx, []).append(content)

    result_paras = []
    n = len(paragraphs)
    for i in range(n):
        # 先插入"在此段落之前"的 inserts
        if i in inserts_by_idx:
            for content in inserts_by_idx[i]:
                result_paras.append(content)
        # 处理原段落
        if i in deletes:
            continue
        if i in replaces:
            result_paras.append(replaces[i])
        else:
            result_paras.append(paragraphs[i])

    # 处理 paraIdx >= n 的 inserts（追加到末尾）
    for idx in sorted(inserts_by_idx.keys()):
        if idx >= n:
            for content in inserts_by_idx[idx]:
                result_paras.append(content)

    return "\n\n".join(result_paras)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_paragraph_diff.py -v -k apply_changes`
Expected: PASS (all 6 tests)

- [ ] **Step 5: Commit**

```bash
git add nas_md/webserver/paragraph_diff.py tests/test_paragraph_diff.py
git commit -m "feat(diff): add apply_changes function to apply change list to text"
```

---

## Task 2: paragraph_diff 新增 merge_changes 函数

**Files:**
- Modify: `nas_md/webserver/paragraph_diff.py`
- Test: `tests/test_paragraph_diff.py`

- [ ] **Step 1: 写 merge_changes 的失败测试**

在 `tests/test_paragraph_diff.py` 末尾追加：

```python
from nas_md.webserver.paragraph_diff import merge_changes


def test_merge_changes_no_overlap():
    """无段落重叠的changes应直接合并，全部保留。"""
    existing = [{"type": "replace", "paraIdx": 0, "content": "A2"}]
    incoming = [{"type": "replace", "paraIdx": 2, "content": "C2"}]
    merged = merge_changes(existing, incoming)
    assert len(merged) == 2
    idxs = {c["paraIdx"] for c in merged}
    assert idxs == {0, 2}


def test_merge_changes_overlap_replace():
    """同段落 replace 冲突，incoming 覆盖 existing（后写覆盖）。"""
    existing = [{"type": "replace", "paraIdx": 1, "content": "from_existing"}]
    incoming = [{"type": "replace", "paraIdx": 1, "content": "from_incoming"}]
    merged = merge_changes(existing, incoming)
    replaces = [c for c in merged if c["type"] == "replace" and c["paraIdx"] == 1]
    assert len(replaces) == 1
    assert replaces[0]["content"] == "from_incoming"


def test_merge_changes_insert_non_conflict():
    """insert 到不同位置应全部保留。"""
    existing = [{"type": "insert", "paraIdx": 0, "content": "X"}]
    incoming = [{"type": "insert", "paraIdx": 2, "content": "Y"}]
    merged = merge_changes(existing, incoming)
    assert len(merged) == 2


def test_merge_changes_empty_existing():
    """existing 为空时，merged = incoming。"""
    merged = merge_changes([], [{"type": "replace", "paraIdx": 0, "content": "A"}])
    assert len(merged) == 1
    assert merged[0]["content"] == "A"


def test_merge_changes_empty_incoming():
    """incoming 为空时，merged = existing。"""
    merged = merge_changes([{"type": "replace", "paraIdx": 0, "content": "A"}], [])
    assert len(merged) == 1
    assert merged[0]["content"] == "A"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_paragraph_diff.py::test_merge_changes_no_overlap -v`
Expected: FAIL with ImportError

- [ ] **Step 3: 实现 merge_changes**

在 `nas_md/webserver/paragraph_diff.py` 末尾追加：

```python
def merge_changes(existing: list, incoming: list) -> list:
    """合并两个 changes 列表，处理段落级冲突。

    策略（后写覆盖）：
    - replace: 同 paraIdx 的，incoming 覆盖 existing
    - delete: 同 paraIdx 的，incoming 胜出
    - replace vs delete 同 paraIdx: incoming 胜出
    - insert: 全部保留（不同位置不冲突）

    返回合并后的 changes 列表（基于原文本的 paraIdx）。
    """
    if not existing:
        return list(incoming)
    if not incoming:
        return list(existing)

    existing_rd = {}  # paraIdx -> change
    existing_inserts = []
    for ch in existing:
        t = ch.get("type")
        if t in ("replace", "delete"):
            existing_rd[ch.get("paraIdx", 0)] = ch
        elif t == "insert":
            existing_inserts.append(ch)

    incoming_rd = {}
    incoming_inserts = []
    for ch in incoming:
        t = ch.get("type")
        if t in ("replace", "delete"):
            incoming_rd[ch.get("paraIdx", 0)] = ch
        elif t == "insert":
            incoming_inserts.append(ch)

    # 合并 replace/delete: incoming 覆盖 existing
    merged_rd = dict(existing_rd)
    for idx, ch in incoming_rd.items():
        merged_rd[idx] = ch

    result = []
    result.extend(existing_inserts)
    result.extend(incoming_inserts)
    for idx in sorted(merged_rd.keys()):
        result.append(merged_rd[idx])

    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_paragraph_diff.py -v -k merge_changes`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add nas_md/webserver/paragraph_diff.py tests/test_paragraph_diff.py
git commit -m "feat(diff): add merge_changes for paragraph-level conflict resolution"
```

---

## Task 3: file_version_store.py 核心模块

**Files:**
- Create: `nas_md/webserver/file_version_store.py`
- Test: `tests/test_file_version_store.py`

- [ ] **Step 1: 写 file_version_store 的失败测试**

创建 `tests/test_file_version_store.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_file_version_store.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: 实现 file_version_store.py**

创建 `nas_md/webserver/file_version_store.py`：

```python
"""File version store with paragraph-level merge.

Central in-memory store of {file_key -> (version, content)} with thread-safe
access. All writes go through apply_changes() which handles version-based
optimistic locking and paragraph-level merge on conflict.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Optional

from nas_md.webserver.paragraph_diff import apply_changes as apply_diff_changes
from nas_md.webserver.paragraph_diff import compute_diff

logger = logging.getLogger("file_version_store")


@dataclass
class _FileVersion:
    """In-memory version state for a single file."""

    version: int = 0
    content: str = ""
    changes_by_version: dict = field(default_factory=dict)


class FileVersionStore:
    """Thread-safe file version store with paragraph-level merge."""

    def __init__(self, storage_dir: str = None):
        self._lock = threading.RLock()
        self._files: dict[str, _FileVersion] = {}
        self._storage_dir = storage_dir

    def init_file(self, file_key: str, file_path: str, content: str) -> int:
        """Initialize file in store. Returns current version number."""
        with self._lock:
            if file_key in self._files:
                return self._files[file_key].version

            version = self._load_version_from_history(file_key)
            self._files[file_key] = _FileVersion(
                version=version,
                content=content,
                changes_by_version={},
            )
            return version

    def _load_version_from_history(self, file_key: str) -> int:
        """Load latest version number from version history."""
        try:
            from nas_md.webserver.version_history import get_history

            history = get_history(file_key, limit=1)
            if history:
                return history[0].get("version", 0)
        except Exception as e:
            logger.warning("Failed to load version from history for %s: %s", file_key, e)
        return 0

    def get_current_version(self, file_key: str) -> int:
        with self._lock:
            fv = self._files.get(file_key)
            return fv.version if fv else 0

    def get_current_content(self, file_key: str) -> Optional[str]:
        with self._lock:
            fv = self._files.get(file_key)
            return fv.content if fv else None

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
        """Apply changes with version-based optimistic locking."""
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
                try:
                    with open(file_path, encoding="utf-8") as f:
                        disk_content = f.read()
                except OSError:
                    disk_content = ""
                fv = _FileVersion(version=0, content=disk_content, changes_by_version={})
                self._files[file_key] = fv

            merged = False

            if base_version == fv.version:
                new_content = apply_diff_changes(fv.content, changes)
            else:
                merged = True
                # 段落级合并：对当前内容直接应用incoming changes
                # 非重叠段落：两处修改都保留
                # 重叠段落：incoming覆盖（后写覆盖）
                new_content = apply_diff_changes(fv.content, changes)

            try:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
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

            fv.version += 1
            fv.content = new_content
            fv.changes_by_version[fv.version] = list(changes)
            self._prune_changes_history(fv)

            self._record_version_history(
                file_key=file_key,
                author_id=author_id,
                author_name=author_name,
                author_color=author_color,
                changes=changes,
                content_snapshot=new_content,
                version=fv.version,
            )

            logger.info(
                "apply_changes: file_key=%s base=%d -> new=%d merged=%s",
                file_key,
                base_version,
                fv.version,
                merged,
            )

            return {
                "applied": True,
                "merged": merged,
                "newVersion": fv.version,
                "content": new_content,
            }

    def _prune_changes_history(self, fv: _FileVersion, keep: int = 50):
        if len(fv.changes_by_version) > keep:
            sorted_versions = sorted(fv.changes_by_version.keys(), reverse=True)
            to_remove = sorted_versions[keep:]
            for v in to_remove:
                del fv.changes_by_version[v]

    def _record_version_history(
        self,
        file_key: str,
        author_id: str,
        author_name: str,
        author_color: str,
        changes: list,
        content_snapshot: str,
        version: int,
    ):
        try:
            from nas_md.webserver.version_history import record_version

            record_version(
                file_key=file_key,
                author_id=author_id,
                author_name=author_name,
                author_color=author_color,
                changes=changes,
                content_snapshot=content_snapshot,
                version=version,
            )
        except Exception as e:
            logger.warning("Version history record failed for %s: %s", file_key, e)

    def apply_external_change(
        self,
        file_key: str,
        file_path: str,
    ) -> dict:
        """Handle external file modification (detected by watchdog)."""
        with self._lock:
            try:
                with open(file_path, encoding="utf-8") as f:
                    disk_content = f.read()
            except OSError as e:
                logger.error("Failed to read external file %s: %s", file_path, e)
                return {
                    "applied": False,
                    "newVersion": 0,
                    "content": "",
                    "changes": [],
                }

            fv = self._files.get(file_key)
            if fv is None:
                fv = _FileVersion(version=0, content=disk_content, changes_by_version={})
                self._files[file_key] = fv
                return {
                    "applied": False,
                    "newVersion": 0,
                    "content": disk_content,
                    "changes": [],
                }

            if disk_content == fv.content:
                return {
                    "applied": False,
                    "newVersion": fv.version,
                    "content": fv.content,
                    "changes": [],
                }

            changes = compute_diff(fv.content, disk_content)
            if not changes:
                changes = [{"type": "replace", "paraIdx": 0, "content": disk_content}]

            fv.version += 1
            fv.content = disk_content
            fv.changes_by_version[fv.version] = list(changes)
            self._prune_changes_history(fv)

            self._record_version_history(
                file_key=file_key,
                author_id="system",
                author_name="外部修改",
                author_color="#95a5a6",
                changes=changes,
                content_snapshot=disk_content,
                version=fv.version,
            )

            logger.info(
                "apply_external_change: file_key=%s new_version=%d changes=%d",
                file_key,
                fv.version,
                len(changes),
            )

            return {
                "applied": True,
                "newVersion": fv.version,
                "content": disk_content,
                "changes": changes,
            }


_global_store: Optional[FileVersionStore] = None
_global_store_lock = threading.Lock()


def get_store() -> FileVersionStore:
    """Get the global FileVersionStore instance."""
    global _global_store
    if _global_store is None:
        with _global_store_lock:
            if _global_store is None:
                _global_store = FileVersionStore()
    return _global_store
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_file_version_store.py -v`
Expected: PASS (all 9 tests, `test_init_file_with_existing_history` may need Task 4)

- [ ] **Step 5: Commit**

```bash
git add nas_md/webserver/file_version_store.py tests/test_file_version_store.py
git commit -m "feat(version-store): add FileVersionStore with version-based optimistic locking"
```

---

## Task 4: version_history.py 增加 version 字段

**Files:**
- Modify: `nas_md/webserver/version_history.py`

- [ ] **Step 1: 修改 VersionEntry 增加 version 字段**

修改 `nas_md/webserver/version_history.py` 的 `VersionEntry` dataclass：

```python
@dataclass
class VersionEntry:
    """A single version snapshot."""

    version: int  # 新增
    timestamp: float
    author_id: str
    author_name: str
    author_color: str
    changes: list
    content_snapshot: str
```

- [ ] **Step 2: 修改 FileHistory.add 接受 version 参数**

```python
    def add(
        self,
        author_id: str,
        author_name: str,
        author_color: str,
        changes: list,
        content_snapshot: str,
        version: int = 0,  # 新增
    ) -> VersionEntry:
        entry = VersionEntry(
            version=version,
            timestamp=time.time(),
            author_id=author_id,
            author_name=author_name,
            author_color=author_color,
            changes=changes,
            content_snapshot=content_snapshot,
        )
        self.versions.append(entry)
        return entry
```

- [ ] **Step 3: 修改 to_dict/from_dict 包含 version**

```python
    def to_dict(self) -> dict:
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
                }
                for v in self.versions
            ]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FileHistory":
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
            )
            fh.versions.append(entry)
        return fh
```

- [ ] **Step 4: 修改 record_version 接受 version 参数**

```python
def record_version(
    file_key: str,
    author_id: str,
    author_name: str,
    author_color: str,
    changes: list,
    content_snapshot: str,
    previous_content: str | None = None,
    version: int = 0,  # 新增
) -> VersionEntry:
    with _lock:
        if file_key not in _histories:
            loaded = _load(file_key)
            _histories[file_key] = loaded if loaded else FileHistory()

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
            author_id, author_name, author_color, changes, content_snapshot, version=version
        )
        _persist(file_key, _histories[file_key])
        return entry
```

- [ ] **Step 5: 修改 get_history 返回 version 字段**

在 `get_history` 函数返回的dict中添加 `"version": v.version,`：

```python
        return [
            {
                "version": v.version,
                "timestamp": v.timestamp,
                "authorId": v.author_id,
                "authorName": v.author_name,
                "authorColor": v.author_color,
                "changes": v.changes,
                "contentLength": len(v.content_snapshot),
            }
            for v in hist.list(limit)
        ]
```

- [ ] **Step 6: 运行所有现有测试确认无回归**

Run: `python -m pytest tests/ -v -k "version or history or paragraph or sse"`
Expected: PASS (向后兼容，version字段默认0)

- [ ] **Step 7: 运行 Task 3 中之前可能失败的测试**

Run: `python -m pytest tests/test_file_version_store.py::test_init_file_with_existing_history -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add nas_md/webserver/version_history.py
git commit -m "feat(version-history): add version field to VersionEntry"
```

---

## Task 5: POST /api/mounts/{id}/changes API 端点

**Files:**
- Modify: `nas_md/webserver/__init__.py`

- [ ] **Step 1: 在 do_POST 中添加 /changes 路由**

在 `nas_md/webserver/__init__.py` 的 `do_POST` 方法中，在 `/move` 路由之后添加：

```python
            # POST /api/mounts/{id}/changes — submit paragraph-level changes
            if path.startswith("/api/mounts/") and path.endswith("/changes"):
                parts = path.split("/")
                if len(parts) >= 4:
                    mount_id = parts[3]
                    qs = parse_qs(parsed.query)
                    self._handle_submit_changes(mount_id, qs)
                    return
```

- [ ] **Step 2: 实现 _handle_submit_changes 方法**

在 `_handle_write_file` 方法之后添加：

```python
    def _handle_submit_changes(self, mount_id: str, qs: dict):
        """Handle POST /api/mounts/{id}/changes — version-based paragraph merge."""
        if not self.mount_manager:
            return self._send_error("No mounts configured", 404)
        mount = self.mount_manager.find_mount(mount_id)
        if not mount:
            return self._send_error("Mount not found", 404)
        session_id = self._get_session_id()
        if mount.host:
            if not self._is_admin_request() and not mount.public:
                return self._send_error("Mount not found", 404)
        elif not self._owns_mount(mount, session_id):
            return self._send_error("Mount not found", 404)
        if mount.readonly:
            return self._send_error("Mount is read-only", 403)

        rel_path = qs.get("path", [None])[0]
        if not rel_path:
            return self._send_error("Missing path parameter", 400)
        abs_path = self.mount_manager._safe_path(mount, rel_path)
        if abs_path is None:
            return self._send_error("Path escapes mount root", 403)

        body = self._read_body()
        try:
            payload = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return self._send_error(f"Invalid JSON body: {e}", 400)

        base_version = payload.get("baseVersion", 0)
        changes = payload.get("changes", [])
        author_name = payload.get("authorName") or self.headers.get("X-Client-Name", "Anonymous")
        author_color = payload.get("authorColor") or self.headers.get("X-Client-Color", "#3498db")

        from nas_md.webserver.file_version_store import get_store

        store = get_store()
        file_key = f"{mount_id}:{rel_path}"

        try:
            with open(abs_path, encoding="utf-8") as f:
                current_content = f.read()
        except OSError:
            current_content = ""
        store.init_file(file_key, abs_path, current_content)

        result = store.apply_changes(
            file_key=file_key,
            file_path=abs_path,
            base_version=base_version,
            changes=changes,
            author_id=session_id,
            author_name=author_name,
            author_color=author_color,
        )

        if not result.get("applied"):
            self._send_json({
                "status": "ok",
                "applied": False,
                "newVersion": result.get("newVersion", 0),
                "content": result.get("content", ""),
            })
            return

        try:
            from nas_md.webserver.sse_handler import sse_broadcast

            sse_broadcast(
                file_key,
                exclude_id=session_id,
                event={
                    "type": "remote_edit",
                    "authorId": session_id,
                    "authorName": author_name,
                    "authorColor": author_color,
                    "mountId": mount_id,
                    "path": rel_path,
                    "changes": changes,
                    "newVersion": result["newVersion"],
                },
            )
        except Exception as e:
            logger.warning("SSE broadcast failed: %s", e)

        if self.search_dirs:
            self._update_search_index(file_path=abs_path)

        self._send_json({
            "status": "ok",
            "applied": True,
            "merged": result.get("merged", False),
            "newVersion": result["newVersion"],
            "content": result["content"],
        })
```

- [ ] **Step 3: 在 _handle_file (GET) 中返回版本号**

在 `_handle_file` 方法中，找到 `self.send_header("X-Mod-Time", str(mtime))` 这一行，在其后添加：

```python
            self.send_header("X-Mod-Time", str(mtime))
            # Include file version for version-based optimistic locking
            from nas_md.webserver.file_version_store import get_store

            store = get_store()
            file_key = f"{mount_id}:{rel_path}"
            version = store.get_current_version(file_key)
            self.send_header("X-File-Version", str(version))
```

- [ ] **Step 4: 手动测试API**

启动服务器后用curl测试：
```bash
# 1. 获取文件和版本号
curl -i "http://localhost:8080/api/mounts/mount-0/file?path=/test.md"
# 记录 X-File-Version 头

# 2. 提交changes
curl -X POST "http://localhost:8080/api/mounts/mount-0/changes?path=/test.md" \
  -H "Content-Type: application/json" \
  -d '{"baseVersion": 0, "changes": [{"type": "replace", "paraIdx": 0, "content": "CHANGED"}], "authorName": "Test", "authorColor": "#fff"}'
# 期望: {"status":"ok","applied":true,"merged":false,"newVersion":1,...}

# 3. 再次提交，baseVersion=0 触发合并
curl -X POST "http://localhost:8080/api/mounts/mount-0/changes?path=/test.md" \
  -H "Content-Type: application/json" \
  -d '{"baseVersion": 0, "changes": [{"type": "replace", "paraIdx": 1, "content": "OTHER"}], "authorName": "Test2", "authorColor": "#000"}'
# 期望: {"status":"ok","applied":true,"merged":true,"newVersion":2,...}
```

- [ ] **Step 5: 运行现有测试确认无回归**

Run: `python -m pytest tests/test_webserver.py tests/test_sse_handler.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add nas_md/webserver/__init__.py
git commit -m "feat(api): add POST /changes endpoint for version-based paragraph merge"
```

---

## Task 6: PUT /file 标记为 deprecated 包装

**Files:**
- Modify: `nas_md/webserver/__init__.py`

- [ ] **Step 1: 修改 _handle_write_file 内部走 apply_changes**

在 `_handle_write_file` 方法中，找到 `body = self._read_body()` 这一行（约line 1395），从这行开始到方法末尾的 `return abs_path` 之前，替换整段代码为：

```python
        body = self._read_body()
        new_text = body.decode("utf-8", errors="replace")

        # DEPRECATED: PUT /file is now a wrapper around apply_changes.
        # New clients should use POST /changes instead.
        from nas_md.webserver.file_version_store import get_store

        store = get_store()
        file_key = f"{mount_id}:{rel_path}"

        old_content = None
        if os.path.isfile(abs_path):
            try:
                with open(abs_path, encoding="utf-8") as f:
                    old_content = f.read()
            except OSError:
                pass

        store.init_file(file_key, abs_path, old_content or "")

        if old_content is not None and old_content != new_text:
            from nas_md.webserver.paragraph_diff import compute_diff

            changes = compute_diff(old_content, new_text)
            if not changes:
                changes = [{"type": "replace", "paraIdx": 0, "content": new_text}]
        else:
            changes = []

        author_name = self.headers.get("X-Client-Name", "Anonymous")
        author_color = self.headers.get("X-Client-Color", "#3498db")

        result = store.apply_changes(
            file_key=file_key,
            file_path=abs_path,
            base_version=store.get_current_version(file_key),
            changes=changes,
            author_id=session_id,
            author_name=author_name,
            author_color=author_color,
        )

        if changes and result.get("applied"):
            try:
                from nas_md.webserver.sse_handler import sse_broadcast

                sse_broadcast(
                    file_key,
                    exclude_id=session_id,
                    event={
                        "type": "remote_edit",
                        "authorId": session_id,
                        "authorName": author_name,
                        "authorColor": author_color,
                        "mountId": mount_id,
                        "path": rel_path,
                        "changes": changes,
                        "newVersion": result["newVersion"],
                    },
                )
            except Exception as e:
                logger.warning("SSE broadcast failed: %s", e)

        st = os.stat(abs_path)
        self._send_json(
            {
                "status": "ok",
                "modTime": int(st.st_mtime * 1000),
                "size": st.st_size,
                "conflict": False,
                "newVersion": result.get("newVersion", store.get_current_version(file_key)),
            }
        )
        return abs_path
```

- [ ] **Step 2: 运行webserver测试确认无回归**

Run: `python -m pytest tests/test_webserver.py -v`
Expected: PASS

- [ ] **Step 3: 手动测试PUT端点仍工作**

```bash
curl -X PUT "http://localhost:8080/api/mounts/mount-0/file?path=/test.md" \
  -H "Content-Type: text/plain" \
  --data-binary "new content via PUT"
# 期望: {"status":"ok","modTime":...,"size":...,"conflict":false,"newVersion":N}
```

- [ ] **Step 4: Commit**

```bash
git add nas_md/webserver/__init__.py
git commit -m "refactor(api): deprecate PUT /file, route through apply_changes"
```

---

## Task 7: file_watcher.py watchdog 文件监听

**Files:**
- Create: `nas_md/webserver/file_watcher.py`
- Test: `tests/test_file_watcher.py`

- [ ] **Step 1: 写 file_watcher 的失败测试**

创建 `tests/test_file_watcher.py`：

```python
# tests/test_file_watcher.py
import time
import pytest
from nas_md.webserver.file_watcher import FileWatcher


@pytest.fixture
def watcher(tmp_path):
    w = FileWatcher()
    yield w
    w.stop_all()


def test_watcher_detects_external_modification(watcher, tmp_path):
    test_file = tmp_path / "test.md"
    test_file.write_text("initial content", encoding="utf-8")

    events = []
    watcher.watch_mount(
        mount_id="mount-0",
        mount_dir=str(tmp_path),
        on_change=lambda mid, rpath, abs_path: events.append((mid, rpath, abs_path)),
    )
    time.sleep(0.5)

    test_file.write_text("modified content", encoding="utf-8")
    time.sleep(1.0)

    assert len(events) >= 1
    assert events[0][0] == "mount-0"


def test_watcher_ignores_own_write(watcher, tmp_path):
    test_file = tmp_path / "test.md"
    test_file.write_text("initial", encoding="utf-8")

    events = []
    watcher.watch_mount(
        mount_id="mount-0",
        mount_dir=str(tmp_path),
        on_change=lambda mid, rpath, abs_path: events.append((mid, rpath, abs_path)),
    )
    time.sleep(0.5)

    watcher.mark_expected("mount-0", "/test.md", "my own write")
    test_file.write_text("my own write", encoding="utf-8")
    time.sleep(1.0)
    assert len(events) == 0


def test_watcher_stop_all(watcher, tmp_path):
    test_file = tmp_path / "test.md"
    test_file.write_text("initial", encoding="utf-8")

    events = []
    watcher.watch_mount(
        mount_id="mount-0",
        mount_dir=str(tmp_path),
        on_change=lambda mid, rpath, abs_path: events.append((mid, rpath, abs_path)),
    )
    time.sleep(0.3)
    watcher.stop_all()
    time.sleep(0.3)

    test_file.write_text("after stop", encoding="utf-8")
    time.sleep(1.0)
    assert len(events) == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_file_watcher.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: 实现 file_watcher.py**

创建 `nas_md/webserver/file_watcher.py`：

```python
"""File watcher using watchdog to detect external file modifications.

Only used for host mounts (server local directories). Self-writes are filtered
via mark_expected(): before writing a file, call mark_expected(); when watchdog
fires, if file content matches expected, skip the callback.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Callable, Optional

logger = logging.getLogger("file_watcher")

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = object  # type: ignore
    FileSystemEvent = object  # type: ignore


class _MountWatchHandler(FileSystemEventHandler):
    """watchdog event handler for a single mount."""

    def __init__(
        self,
        mount_id: str,
        mount_dir: str,
        on_change: Callable[[str, str, str], None],
        watcher: "FileWatcher",
    ):
        super().__init__()
        self.mount_id = mount_id
        self.mount_dir = os.path.abspath(mount_dir)
        self.on_change = on_change
        self.watcher = watcher
        self._debounce_timer = None
        self._debounce_lock = threading.Lock()
        self._pending_events: set = set()

    def on_modified(self, event):
        if event.is_directory:
            return
        self._handle_file_event(event.src_path)

    def on_created(self, event):
        if event.is_directory:
            return
        self._handle_file_event(event.src_path)

    def _handle_file_event(self, abs_path: str):
        if not abs_path.lower().endswith(".md"):
            return

        with self._debounce_lock:
            self._pending_events.add(abs_path)
            if self._debounce_timer:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(0.2, self._flush_pending)
            self._debounce_timer.start()

    def _flush_pending(self):
        with self._debounce_lock:
            paths = list(self._pending_events)
            self._pending_events.clear()
            self._debounce_timer = None

        for abs_path in paths:
            self._check_and_notify(abs_path)

    def _check_and_notify(self, abs_path: str):
        try:
            rel_path = os.path.relpath(abs_path, self.mount_dir)
            rel_path = "/" + rel_path.replace(os.sep, "/")

            if self.watcher.is_expected(self.mount_id, rel_path, abs_path):
                logger.debug("Ignoring self-write: %s:%s", self.mount_id, rel_path)
                return

            logger.info("External file change: %s:%s", self.mount_id, rel_path)
            self.on_change(self.mount_id, rel_path, abs_path)
        except Exception as e:
            logger.error("Error handling file event for %s: %s", abs_path, e)


class FileWatcher:
    """Manages watchdog observers for all host mounts."""

    def __init__(self):
        self._observers: dict = {}
        self._handlers: dict = {}
        self._expected: dict = {}
        self._expected_lock = threading.Lock()
        self._lock = threading.Lock()

    def watch_mount(
        self,
        mount_id: str,
        mount_dir: str,
        on_change: Callable[[str, str, str], None],
    ) -> bool:
        if not WATCHDOG_AVAILABLE:
            logger.warning("watchdog not available, skipping %s", mount_id)
            return False

        if not os.path.isdir(mount_dir):
            logger.warning("Mount dir does not exist: %s", mount_dir)
            return False

        with self._lock:
            if mount_id in self._observers:
                return True

            handler = _MountWatchHandler(mount_id, mount_dir, on_change, self)
            observer = Observer()
            observer.schedule(handler, mount_dir, recursive=True)
            observer.start()

            self._observers[mount_id] = observer
            self._handlers[mount_id] = handler
            logger.info("Started watching mount %s at %s", mount_id, mount_dir)
            return True

    def mark_expected(self, mount_id: str, rel_path: str, content: str):
        key = f"{mount_id}:{rel_path}"
        with self._expected_lock:
            self._expected[key] = content

    def is_expected(self, mount_id: str, rel_path: str, abs_path: str) -> bool:
        key = f"{mount_id}:{rel_path}"
        with self._expected_lock:
            expected = self._expected.pop(key, None)

        if expected is None:
            return False

        try:
            with open(abs_path, encoding="utf-8") as f:
                actual = f.read()
            return actual == expected
        except OSError:
            return False

    def stop_mount(self, mount_id: str):
        with self._lock:
            observer = self._observers.pop(mount_id, None)
            self._handlers.pop(mount_id, None)
        if observer:
            observer.stop()
            observer.join(timeout=1.0)

    def stop_all(self):
        with self._lock:
            mount_ids = list(self._observers.keys())
        for mid in mount_ids:
            self.stop_mount(mid)


_global_watcher: Optional[FileWatcher] = None
_global_watcher_lock = threading.Lock()


def get_watcher() -> FileWatcher:
    global _global_watcher
    if _global_watcher is None:
        with _global_watcher_lock:
            if _global_watcher is None:
                _global_watcher = FileWatcher()
    return _global_watcher
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_file_watcher.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add nas_md/webserver/file_watcher.py tests/test_file_watcher.py
git commit -m "feat(file-watcher): add watchdog-based external file change detection"
```

---

## Task 8: 集成 file_watcher 到 webserver

**Files:**
- Modify: `nas_md/webserver/__init__.py`

- [ ] **Step 1: 添加 _start_file_watchers 函数**

在 `nas_md/webserver/__init__.py` 中（模块级函数，放在 class 之外，例如文件末尾或 run_server 附近）添加：

```python
def _start_file_watchers(mount_manager):
    """Start file watchers for all host mounts."""
    from nas_md.webserver.file_watcher import get_watcher
    from nas_md.webserver.file_version_store import get_store

    watcher = get_watcher()
    store = get_store()

    def on_external_change(mount_id: str, rel_path: str, abs_path: str):
        file_key = f"{mount_id}:{rel_path}"
        result = store.apply_external_change(file_key, abs_path)
        if result.get("applied"):
            try:
                from nas_md.webserver.sse_handler import sse_broadcast

                sse_broadcast(
                    file_key,
                    exclude_id="system",
                    event={
                        "type": "external_reload",
                        "mountId": mount_id,
                        "path": rel_path,
                        "changes": result.get("changes", []),
                        "newVersion": result["newVersion"],
                        "content": result["content"],
                    },
                )
            except Exception as e:
                logger.warning("SSE broadcast for external change failed: %s", e)

    for mount in mount_manager.mounts:
        if mount.host and os.path.isdir(mount.path):
            watcher.watch_mount(mount.id, mount.path, on_external_change)
            logger.info("File watcher started for host mount %s", mount.id)
```

- [ ] **Step 2: 在服务器启动时调用 _start_file_watchers**

找到服务器启动函数（搜索 `serve_forever` 或 `run_server`），在 `serve_forever()` 之前调用：

```python
    # Start file watchers for host mounts
    _start_file_watchers(mount_manager)
```

注意：如果启动函数中 `mount_manager` 变量名不同，请用实际名称。

- [ ] **Step 3: 在 _handle_submit_changes 中标记预期写入**

在 `_handle_submit_changes` 方法中，`store.apply_changes(...)` 调用之前添加：

```python
        # Mark expected write to filter watchdog self-write
        from nas_md.webserver.file_watcher import get_watcher
        from nas_md.webserver.paragraph_diff import apply_changes as apply_diff

        current_content = store.get_current_content(file_key) or ""
        expected_content = apply_diff(current_content, changes)
        get_watcher().mark_expected(mount_id, rel_path, expected_content)
```

- [ ] **Step 4: 手动测试外部修改检测**

启动服务器，浏览器打开文件，用记事本修改同一文件保存。
Expected: 浏览器编辑器应自动更新（通过SSE推送 external_reload）

- [ ] **Step 5: Commit**

```bash
git add nas_md/webserver/__init__.py
git commit -m "feat(server): integrate file_watcher for external change detection"
```

---

## Task 9: files.js 新增 submitChanges 方法

**Files:**
- Modify: `web/files.js`

- [ ] **Step 1: 在 API 对象中添加 submitChanges**

在 `web/files.js` 的 `putFile` 方法之后添加：

```javascript
  // 提交段落级changes（版本号驱动的协同编辑）
  async submitChanges(mountId, path, baseVersion, changes, authorName, authorColor) {
    const url = `/api/mounts/${mountId}/changes?path=${encodeURIComponent(path)}`;
    const body = JSON.stringify({
      baseVersion,
      changes,
      authorName: authorName || 'Anonymous',
      authorColor: authorColor || '#3498db',
    });
    console.log('[submitChanges] sending POST:', {
      url,
      baseVersion,
      changesCount: changes.length,
    });
    try {
      const r = await this.request(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      });
      if (!r || !r.ok) {
        const errText = r ? await r.text().catch(() => '') : '';
        console.error('[submitChanges] error:', errText);
        return null;
      }
      return r.json();
    } catch (e) {
      console.error('[submitChanges] fetch error:', e);
      throw e;
    }
  },
```

- [ ] **Step 2: 修改 getFile 解析版本号**

修改 `getFile` 方法，添加 `X-File-Version` 头解析：

```javascript
  async getFile(mountId, path) {
    const r = await this.request(
      `/api/mounts/${mountId}/file?path=${encodeURIComponent(path)}&_t=${Date.now()}`,
      { cache: 'no-store' },
    );
    if (!r) {
      console.error('getFile: request failed');
      return null;
    }
    if (!r.ok) {
      const errText = await r.text().catch(() => '');
      console.error(`getFile: HTTP ${r.status}`, errText);
      return null;
    }
    const content = await r.text();
    const mtime = parseInt(r.headers.get('X-Mod-Time') || '0', 10);
    const version = parseInt(r.headers.get('X-File-Version') || '0', 10);
    return { content, mtime, version };
  },
```

- [ ] **Step 3: Commit**

```bash
git add web/files.js
git commit -m "feat(api-client): add submitChanges method and version header parsing"
```

---

## Task 10: app.js 重写 saveFile 和移除轮询

**Files:**
- Modify: `web/app.js`

- [ ] **Step 1: 在 state 中添加版本号字段**

找到 `state` 对象定义中 `fileMtimes` 附近，添加：

```javascript
  fileVersions: {},  // { "mountId:path": version }
  baseContent: null,
  baseVersion: 0,
```

- [ ] **Step 2: 重写 saveFile 函数**

找到 `async function saveFile({ silent = false } = {}) {`（约line 2986），整个函数替换为：

```javascript
async function saveFile({ silent = false } = {}) {
  if (_saveInProgress) {
    console.log('[saveFile] skipped: another save in progress');
    return;
  }
  _saveInProgress = true;
  try {
    if (!state.currentPath || !state.currentMountId || !window._vditor) return;
    const mount = state.mounts.find((m) => m.id === state.currentMountId);
    if (mount && mount.readonly) {
      if (!silent) showToast('此文件不允许修改');
      return;
    }
    const content = window._vditor.getValue();
    const btn = $('btn-save');

    if (!silent && btn) {
      btn.classList.add('saving');
      btn.disabled = true;
    }

    if (!navigator.onLine) {
      saveToLocalStorage(state.currentPath, content);
      markClean();
      if (!silent) showToast('已离线保存，恢复连接后自动同步');
      return;
    }

    try {
      if (mount && mount._local && state.localMounts[mount.id]) {
        // Local mount: File System Access API (unchanged)
        const ok = await writeLocalFile(mount.id, state.currentPath, content);
        if (!ok) throw new Error('写入本机文件失败');
        window._originalContent = content;
        state.baseContent = content;
        markClean();
        clearLocalStorage(state.currentPath);
        if (!silent) showToast('已保存');
      } else {
        // Server mount: version-based paragraph merge
        const fileKey = state.currentMountId + ':' + state.currentPath;
        const baseContent = state.baseContent || window._originalContent || '';
        const changes = computeParagraphDiff(baseContent, content);

        if (changes.length === 0) {
          markClean();
          return;
        }

        const identity = window.nasmdIdentity ? window.nasmdIdentity.get() : null;
        const resp = await API.submitChanges(
          state.currentMountId,
          state.currentPath,
          state.baseVersion,
          changes,
          identity ? identity.name : 'Anonymous',
          identity ? identity.color : '#3498db',
        );

        if (!resp || !resp.applied) {
          console.log('[saveFile] changes not applied', resp);
          return;
        }

        // Update version and base content
        state.baseVersion = resp.newVersion;
        state.baseContent = resp.content;
        state.fileVersions[fileKey] = resp.newVersion;
        window._originalContent = resp.content;
        markClean();
        clearLocalStorage(state.currentPath);

        if (resp.merged) {
          showToast('已合并保存');
        } else if (!silent) {
          showToast('已保存');
        } else {
          showToast('自动保存完成');
        }

        performSync();
        if (window.nasmdHistory && window.nasmdHistory.isVisible()) {
          window.nasmdHistory.loadHistory();
        }
      }
    } catch (e) {
      saveToLocalStorage(state.currentPath, content);
      if (!silent) showToast('保存失败，已缓存到本地');
      else showToast('自动保存失败');
      console.error(e);
    } finally {
      _saveInProgress = false;
      if (!silent && btn) {
        btn.classList.remove('saving');
        btn.disabled = false;
      }
      if (state.dirty && state.autoSave && state.currentPath) {
        scheduleAutoSave();
      }
    }
  } finally {
    _saveInProgress = false;
  }
}
```

- [ ] **Step 3: 添加 computeParagraphDiff 辅助函数**

在 `saveFile` 函数之前添加：

```javascript
// 客户端段落级diff计算（简化版，与服务器paragraph_diff.compute_diff对齐）
function computeParagraphDiff(oldText, newText) {
  if (oldText === newText) return [];
  const oldParas = oldText.split('\n\n');
  const newParas = newText.split('\n\n');
  const changes = [];
  const maxLen = Math.max(oldParas.length, newParas.length);
  let oldIdx = 0, newIdx = 0;
  for (let i = 0; i < maxLen; i++) {
    if (i < oldParas.length && i < newParas.length) {
      if (oldParas[i] !== newParas[i]) {
        changes.push({ type: 'replace', paraIdx: i, content: newParas[i] });
      }
    } else if (i < newParas.length) {
      changes.push({ type: 'insert', paraIdx: i, content: newParas[i] });
    } else {
      changes.push({ type: 'delete', paraIdx: i });
    }
  }
  return changes;
}
```

- [ ] **Step 4: 修改 openFile 初始化版本号**

找到 `openFile` 函数中调用 `API.getFile` 的地方（约line 2645），修改为：

```javascript
      const result = await API.getFile(mount.id, path);
      if (result !== null) {
        content = result.content;
        state.fileMtimes[mount.id + ':' + path] = { mtime: result.mtime, size: content.length };
        state.fileVersions[mount.id + ':' + path] = result.version || 0;
      }
```

并在 openFile 函数末尾（设置 `window._originalContent` 之后）添加：

```javascript
    state.baseVersion = state.fileVersions[mount.id + ':' + path] || 0;
    state.baseContent = content;
```

- [ ] **Step 5: 移除 pollCurrentFile 相关代码**

找到 `async function pollCurrentFile()`（约line 3480），整个函数删除。

找到 `function startFilePoll()`（约line 3559）和 `function stopFilePoll()`，删除这两个函数。

搜索 `startFilePoll()` 和 `stopFilePoll()` 的所有调用点（约line 218, 368, 373, 377, 412, 417, 421），全部删除这些调用行。

- [ ] **Step 6: 移除 _filePollTimer 和 FILE_POLL_INTERVAL**

删除 `let _filePollTimer = null;` 和 `const FILE_POLL_INTERVAL = 2000;` 这两行。

- [ ] **Step 7: 手动测试保存功能**

强制刷新浏览器，编辑文件，观察控制台日志：
- 应看到 `[submitChanges] sending POST:`
- 应看到 `[submitChanges] response` 或类似
- 不应再看到 `[putFile]` 或 `conflict: true`
- 应看到 toast 提示"自动保存完成"或"已保存"

- [ ] **Step 8: Commit**

```bash
git add web/app.js
git commit -m "feat(app): rewrite saveFile with version-based merge, remove mtime polling"
```

---

## Task 11: sync_layer.js 简化，移除 mtime 同步

**Files:**
- Modify: `web/sync_layer.js`

- [ ] **Step 1: 移除 handleRemoteEdit 中的 mtime 更新代码**

在 `web/sync_layer.js` 的 `handleRemoteEdit` 函数中（约line 221），找到这段代码：

```javascript
    // Update fileMtimes with server's new modTime so our next save uses the
    // correct expected_mtime (avoids false conflict detection).
    if (data.modTime && window.state && state.fileMtimes && data.mountId && data.path) {
      var key = data.mountId + ':' + data.path;
      var prev = state.fileMtimes[key];
      var newSize = prev ? prev.size : 0;
      state.fileMtimes[key] = { mtime: data.modTime, size: newSize };
    }
```

替换为：

```javascript
    // Update baseVersion for version-based optimistic locking
    if (data.newVersion && window.state && data.mountId && data.path) {
      var key = data.mountId + ':' + data.path;
      if (window.state.fileVersions) {
        state.fileVersions[key] = data.newVersion;
      }
      // Update baseVersion if this is the current file
      if (state.currentMountId === data.mountId && state.currentPath === data.path) {
        state.baseVersion = data.newVersion;
      }
    }
```

- [ ] **Step 2: 添加 external_reload 事件处理**

在 `init` 函数中（约line 301），找到 `window.nasmdSSE.on('remote_edit', handleRemoteEdit);`，在其后添加：

```javascript
    if (window.nasmdSSE) {
      window.nasmdSSE.on('remote_edit', handleRemoteEdit);
      window.nasmdSSE.on('external_reload', handleExternalReload);
    }
```

并在 `handleRemoteEdit` 函数之后添加新函数：

```javascript
  function handleExternalReload(data) {
    // External file modification detected by watchdog
    if (!data.mountId || !data.path) return;
    if (!window.state || state.currentMountId !== data.mountId || state.currentPath !== data.path) {
      return; // Not current file, ignore
    }

    // Update version
    if (data.newVersion) {
      state.baseVersion = data.newVersion;
      state.fileVersions[data.mountId + ':' + data.path] = data.newVersion;
    }

    // If user has unsaved edits, keep them (will merge on next save)
    if (state.dirty) {
      showToast('文件已被外部修改，你的未保存编辑将在下次保存时合并', 'info');
      return;
    }

    // No unsaved edits: reload content
    if (data.content && window._vditor) {
      _applyingRemote = true;
      window._vditor.setValue(data.content);
      window._originalContent = data.content;
      state.baseContent = data.content;
      setTimeout(function () {
        _applyingRemote = false;
      }, 150);
      showToast('文件已被外部修改，已自动重载');
    }
  }
```

- [ ] **Step 3: 手动测试协同编辑**

开两个浏览器窗口登录不同identity，同时编辑同一文件的不同段落。
Expected: 两个窗口都应看到对方的修改，保存时无冲突，版本历史有记录。

- [ ] **Step 4: Commit**

```bash
git add web/sync_layer.js
git commit -m "feat(sync): update baseVersion on remote_edit, add external_reload handler"
```

---

## Task 12: 端到端集成测试

**Files:**
- Manual testing only

- [ ] **Step 1: 测试场景1 - 单人连续编辑**

强制刷新浏览器，打开一个文件，连续输入文字（模拟快速打字）。
Expected:
- 自动保存触发，toast显示"自动保存完成"
- 控制台日志显示 `[submitChanges]` 而非 `[putFile]`
- 无 `conflict: true`
- 无 `.conflict.md` 副本创建

- [ ] **Step 2: 测试场景2 - 多人协同编辑**

开两个浏览器窗口（不同identity），打开同一文件，分别编辑不同段落。
Expected:
- A保存后，B的编辑器实时显示A的修改（SSE推送）
- B保存后，A的编辑器实时显示B的修改
- 两人的修改都保留，无冲突副本
- 版本历史面板显示两人的编辑记录

- [ ] **Step 3: 测试场景3 - 同段并发编辑**

A和B同时编辑同一段落，A先保存，B后保存。
Expected:
- B保存时显示"已合并保存"
- 最终内容为B的版本（后写覆盖）
- 版本历史显示两次修改记录

- [ ] **Step 4: 测试场景4 - 外部修改检测**

浏览器打开文件，用记事本/VSCode修改同一文件保存。
Expected:
- 浏览器编辑器自动更新（如果用户无未保存编辑）
- 或显示提示"文件已被外部修改，你的未保存编辑将在下次保存时合并"
- 版本历史显示"外部修改"作者记录

- [ ] **Step 5: 测试场景5 - 版本历史面板**

打开版本历史面板，编辑文件并保存多次。
Expected:
- 面板显示所有保存记录
- 每条记录显示作者名、时间、变更数
- 可点击查看历史版本内容

- [ ] **Step 6: 运行完整测试套件**

Run: `python -m pytest tests/ -v`
Expected: 所有测试通过

- [ ] **Step 7: 最终Commit（如有修复）**

```bash
git add -A
git commit -m "test: e2e verification of version-driven collaborative editing"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] 版本号替代mtime乐观锁 — Task 3, 5, 10
- [x] 单一写入路径 POST /changes — Task 5
- [x] 段落级合并 — Task 2, 3
- [x] 移除mtime轮询 — Task 10
- [x] 移除conflict副本 — Task 6
- [x] watchdog外部修改检测 — Task 7, 8
- [x] version_history增加version字段 — Task 4
- [x] 客户端submitChanges API — Task 9
- [x] sync_layer简化+external_reload — Task 11
- [x] 端到端测试 — Task 12

**Placeholder scan:** 无TBD/TODO，所有步骤都有完整代码。

**Type consistency:**
- `apply_changes` 在paragraph_diff.py（text, changes -> str）和file_version_store.py（file_key, file_path, base_version, changes, author... -> dict）中签名不同，前者是纯函数后者是方法，无冲突
- `get_store()` / `get_watcher()` 全局单例模式一致
- `baseVersion` / `newVersion` 在API和前端字段命名一致
- `X-File-Version` 响应头在服务器和客户端一致

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-07-version-driven-collab.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — 我每个Task派发一个fresh subagent执行，任务间review，快速迭代。适合这种12个Task的大型计划。

**2. Inline Execution** — 在当前会话中按顺序执行，带checkpoint review。适合需要紧密交互的场景。

**Which approach?**