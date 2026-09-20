"""Paragraph-level diff engine for real-time collaborative editing."""

from difflib import SequenceMatcher


def split_paragraphs_with_delims(text: str) -> tuple[list[str], list[str]]:
    """Split text into paragraphs while preserving exact delimiters between them."""
    if not text:
        return [], []

    # Normalize CRLF -> LF
    text_norm = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = text_norm.split("\n")
    paragraphs: list[str] = []
    delimiters: list[str] = []
    current_lines: list[str] = []

    in_fence: str | None = None  # '```' or '~~~'
    fence_len: int = 0
    in_math: bool = False

    # Check if document starts with YAML frontmatter
    if lines and lines[0].strip() == "---":
        closing_idx = -1
        for idx in range(1, min(50, len(lines))):
            s = lines[idx].strip()
            if s in ("---", "..."):
                closing_idx = idx
                break
            if s.startswith("#") or s.startswith("```"):
                break
        if closing_idx > 0:
            paragraphs.append("\n".join(lines[: closing_idx + 1]))
            # Count following empty lines for delimiter
            post_idx = closing_idx + 1
            sep_count = 0
            while post_idx < len(lines) and lines[post_idx].strip() == "":
                sep_count += 1
                post_idx += 1
            has_following_content = post_idx < len(lines)
            delimiters.append("\n" * (sep_count + (1 if has_following_content else 0)))
            lines = lines[post_idx:]

    i = 0
    num_lines = len(lines)
    while i < num_lines:
        line = lines[i]
        stripped = line.strip()

        # Handle Fenced Code Blocks
        if in_fence is None:
            if stripped.startswith("```"):
                in_fence = "```"
                fence_len = len(stripped) - len(stripped.lstrip("`"))
                current_lines.append(line)
                i += 1
                continue
            elif stripped.startswith("~~~"):
                in_fence = "~~~"
                fence_len = len(stripped) - len(stripped.lstrip("~"))
                current_lines.append(line)
                i += 1
                continue
        else:
            current_lines.append(line)
            if in_fence == "```" and stripped.startswith("```"):
                closing_len = len(stripped) - len(stripped.lstrip("`"))
                if closing_len >= fence_len:
                    in_fence = None
            elif in_fence == "~~~" and stripped.startswith("~~~"):
                closing_len = len(stripped) - len(stripped.lstrip("~"))
                if closing_len >= fence_len:
                    in_fence = None
            i += 1
            continue

        # Handle Math Blocks ($$)
        if not in_math:
            if stripped.startswith("$$"):
                if stripped.endswith("$$") and len(stripped) > 2:
                    current_lines.append(line)
                    i += 1
                    continue
                else:
                    in_math = True
                    current_lines.append(line)
                    i += 1
                    continue
        else:
            current_lines.append(line)
            if stripped.endswith("$$") or stripped == "$$":
                in_math = False
            i += 1
            continue

        # Normal markdown text
        if stripped == "":
            if current_lines:
                paragraphs.append("\n".join(current_lines))
                current_lines = []
                sep_count = 1
                while i + 1 < num_lines and lines[i + 1].strip() == "":
                    sep_count += 1
                    i += 1
                if i == num_lines - 1:
                    delimiters.append("\n" * sep_count)
                else:
                    delimiters.append("\n" * (sep_count + 1))
        else:
            current_lines.append(line)

        i += 1

    if current_lines:
        paragraphs.append("\n".join(current_lines))
        if text_norm.endswith("\n"):
            delimiters.append("\n")
        else:
            delimiters.append("")

    while len(delimiters) < len(paragraphs):
        delimiters.append("\n\n")

    return paragraphs, delimiters


def split_paragraphs(text: str) -> list[str]:
    """Split text into logical Markdown paragraphs / block elements."""
    paras, _ = split_paragraphs_with_delims(text)
    return paras


def compute_diff(old_text: str, new_text: str) -> list[dict]:
    """Compute paragraph-level diff between old and new text with prefix/suffix acceleration."""
    old_paras = split_paragraphs(old_text)
    new_paras = split_paragraphs(new_text)

    if old_paras == new_paras:
        return []

    m = len(old_paras)
    n = len(new_paras)

    # Common Prefix & Common Suffix fast-path
    prefix = 0
    while prefix < m and prefix < n and old_paras[prefix] == new_paras[prefix]:
        prefix += 1

    suffix = 0
    while (
        suffix < m - prefix
        and suffix < n - prefix
        and old_paras[m - 1 - suffix] == new_paras[n - 1 - suffix]
    ):
        suffix += 1

    mid_old = old_paras[prefix : m - suffix]
    mid_new = new_paras[prefix : n - suffix]

    changes = []
    sm = SequenceMatcher(None, mid_old, mid_new, autojunk=False)

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace":
            old_len = i2 - i1
            new_len = j2 - j1
            paired = min(old_len, new_len)

            for k in range(paired):
                changes.append(
                    {
                        "type": "replace",
                        "paraIdx": prefix + i1 + k,
                        "content": mid_new[j1 + k],
                    }
                )

            if old_len > new_len:
                for k in range(paired, old_len):
                    changes.append(
                        {
                            "type": "delete",
                            "paraIdx": prefix + i1 + k,
                        }
                    )
            elif new_len > old_len:
                for k in range(paired, new_len):
                    changes.append(
                        {
                            "type": "insert",
                            "paraIdx": prefix + i2,
                            "content": mid_new[j1 + k],
                        }
                    )
        elif tag == "delete":
            for i in range(i1, i2):
                changes.append({"type": "delete", "paraIdx": prefix + i})
        elif tag == "insert":
            for j in range(j1, j2):
                changes.append(
                    {
                        "type": "insert",
                        "paraIdx": prefix + i1,
                        "content": mid_new[j],
                    }
                )

    return changes


def apply_changes(text: str, changes: list) -> str:
    """将 changes 应用到 text，返回新文本，保留未修改段落的原生空白分隔符。"""
    if not changes:
        return text

    paragraphs, delimiters = split_paragraphs_with_delims(text)

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
    result_delims = []
    n = len(paragraphs)
    for i in range(n):
        # 先插入"在此段落之前"的 inserts
        if i in inserts_by_idx:
            for content in inserts_by_idx[i]:
                result_paras.append(content)
                result_delims.append("\n\n")
        # 处理原段落
        if i in deletes:
            continue
        if i in replaces:
            result_paras.append(replaces[i])
        else:
            result_paras.append(paragraphs[i])
        if i < len(delimiters):
            result_delims.append(delimiters[i])
        else:
            result_delims.append("\n\n")

    # 处理 paraIdx >= n 的 inserts（追加到末尾）
    trailing_indices = [idx for idx in sorted(inserts_by_idx.keys()) if idx >= n]
    if trailing_indices and result_delims and result_delims[-1] in ("", "\n"):
        result_delims[-1] = "\n\n"

    for idx in trailing_indices:
        for content in inserts_by_idx[idx]:
            result_paras.append(content)
            result_delims.append("\n\n")

    if trailing_indices and result_delims and result_delims[-1] == "\n\n":
        result_delims[-1] = ""

    result_parts = []
    for idx, p in enumerate(result_paras):
        result_parts.append(p)
        if idx < len(result_delims):
            result_parts.append(result_delims[idx])

    return "".join(result_parts)


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


def validate_changes(
    changes: list[dict], base_para_count: int, changes_name: str = "changes"
) -> None:
    """Validate a change batch against its pre-change paragraph count."""
    if isinstance(base_para_count, bool) or not isinstance(base_para_count, int):
        raise TypeError("base_para_count must be an integer")
    if base_para_count < 0 or base_para_count > 2**53 - 1:
        raise ValueError("base_para_count must be a nonnegative safe integer")

    if not isinstance(changes, list):
        raise TypeError(f"{changes_name} must be a list")
    for change in changes:
        if not isinstance(change, dict):
            raise TypeError(f"each {changes_name} entry must be a dict")

        change_type = change.get("type")
        if change_type not in {"insert", "delete", "replace"}:
            raise ValueError(f"invalid change type: {change_type!r}")

        para_idx = change.get("paraIdx")
        if isinstance(para_idx, bool) or not isinstance(para_idx, int):
            raise TypeError("paraIdx must be an integer")
        if para_idx < 0:
            raise ValueError("paraIdx must be nonnegative")
        if change_type == "insert":
            if para_idx > base_para_count:
                raise ValueError("insert paraIdx exceeds base paragraph count")
        elif para_idx >= base_para_count:
            raise ValueError("replace/delete paraIdx exceeds base paragraph count")

        if change_type in {"insert", "replace"} and not isinstance(change.get("content"), str):
            raise TypeError("insert/replace content must be a string")


def transform_changes(
    incoming_changes: list[dict],
    accumulated_changes: list[dict],
    base_para_count: int = 1000,
) -> list[dict]:
    """Transform incoming changes' paraIdx against accumulated intermediate changes.

    Maps paragraph indices from base_version coordinate space to current server
    content coordinate space using Operational Transformation (OT).
    """
    validate_changes(incoming_changes, base_para_count, "incoming_changes")
    validate_changes(accumulated_changes, base_para_count, "accumulated_changes")

    if not accumulated_changes or not incoming_changes:
        return list(incoming_changes)

    deleted = {ch["paraIdx"] for ch in accumulated_changes if ch["type"] == "delete"}
    insert_positions = [ch["paraIdx"] for ch in accumulated_changes if ch["type"] == "insert"]

    def map_position(base_idx: int) -> int:
        deletes_before = sum(1 for idx in deleted if idx < base_idx)
        inserts_through = sum(1 for idx in insert_positions if idx <= base_idx)
        return base_idx - deletes_before + inserts_through

    transformed = []
    for ch in incoming_changes:
        t = ch["type"]
        idx = ch["paraIdx"]
        target_idx = map_position(idx)
        if t == "insert":
            transformed.append({"type": "insert", "paraIdx": target_idx, "content": ch["content"]})
        elif t == "replace":
            if idx in deleted:
                # Target was deleted by another user: preserve content as insert
                transformed.append(
                    {"type": "insert", "paraIdx": target_idx, "content": ch["content"]}
                )
            else:
                transformed.append(
                    {"type": "replace", "paraIdx": target_idx, "content": ch["content"]}
                )
        elif t == "delete" and idx not in deleted:
            transformed.append({"type": "delete", "paraIdx": target_idx})

    return transformed
