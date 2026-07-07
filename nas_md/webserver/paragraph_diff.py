"""Paragraph-level diff engine for real-time collaborative editing."""

from difflib import SequenceMatcher


def split_paragraphs(text: str) -> list[str]:
    """Split text by double newline (paragraph boundary)."""
    paragraphs = text.split("\n\n")
    while paragraphs and paragraphs[-1].strip() == "":
        paragraphs.pop()
    return paragraphs


def compute_diff(old_text: str, new_text: str) -> list[dict]:
    """Compute paragraph-level diff between old and new text.

    Returns list of changes:
    - {"type": "replace", "paraIdx": int, "content": str}
    - {"type": "insert", "paraIdx": int, "content": str}
    - {"type": "delete", "paraIdx": int}

    paraIdx: 0-indexed paragraph position.
    For insert: insert BEFORE the paragraph at paraIdx.
    For replace/delete: target the paragraph at paraIdx.
    """
    old_paras = split_paragraphs(old_text)
    new_paras = split_paragraphs(new_text)

    if old_paras == new_paras:
        return []

    sm = SequenceMatcher(None, old_paras, new_paras, autojunk=False)
    changes = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace":
            # Handle potentially unequal length replacements
            old_len = i2 - i1
            new_len = j2 - j1
            paired = min(old_len, new_len)

            for k in range(paired):
                changes.append(
                    {
                        "type": "replace",
                        "paraIdx": i1 + k,
                        "content": new_paras[j1 + k],
                    }
                )

            if old_len > new_len:
                # More old paragraphs than new -> extras are deletions
                for k in range(paired, old_len):
                    changes.append(
                        {
                            "type": "delete",
                            "paraIdx": i1 + k,
                        }
                    )
            elif new_len > old_len:
                # More new paragraphs than old -> extras are insertions
                for k in range(paired, new_len):
                    changes.append(
                        {
                            "type": "insert",
                            "paraIdx": i2,
                            "content": new_paras[j1 + k],
                        }
                    )
        elif tag == "delete":
            for i in range(i1, i2):
                changes.append({"type": "delete", "paraIdx": i})
        elif tag == "insert":
            for j in range(j1, j2):
                changes.append({"type": "insert", "paraIdx": i1, "content": new_paras[j]})

    return changes


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
