"""Paragraph-level diff engine for real-time collaborative editing."""

from dataclasses import dataclass


@dataclass(frozen=True)
class _ParsedDocument:
    prefix: str
    paragraphs: list[str]
    delimiters: list[str]


def _trim_markdown_line_whitespace(line: str) -> str:
    """Trim only the space and tab characters Markdown ignores on a line."""
    return line.strip(" \t")


def _parse_document(text: str) -> _ParsedDocument:
    """Parse normalized text without discarding non-paragraph whitespace."""
    text_norm = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text_norm:
        return _ParsedDocument("", [], [])

    # Each span is (line start, content end, line end, content without LF).
    lines: list[tuple[int, int, int, str]] = []
    start = 0
    while start < len(text_norm):
        newline = text_norm.find("\n", start)
        if newline < 0:
            content_end = len(text_norm)
            line_end = len(text_norm)
        else:
            content_end = newline
            line_end = newline + 1
        lines.append((start, content_end, line_end, text_norm[start:content_end]))
        start = line_end

    line_count = len(lines)
    first_content = 0
    while first_content < line_count and not _trim_markdown_line_whitespace(
        lines[first_content][3]
    ):
        first_content += 1

    if first_content == line_count:
        return _ParsedDocument(text_norm, [], [])

    prefix_end = lines[first_content][0]
    prefix = text_norm[:prefix_end]
    paragraphs: list[str] = []
    delimiters: list[str] = []
    i = first_content

    # Preserve the established rule: frontmatter is special only at the actual
    # beginning of the document. Leading prefix whitespace does not opt in.
    if not prefix and _trim_markdown_line_whitespace(lines[0][3]) == "---":
        closing_idx = -1
        for idx in range(1, min(50, line_count)):
            marker = _trim_markdown_line_whitespace(lines[idx][3])
            if marker in ("---", "..."):
                closing_idx = idx
                break
            if marker.startswith("#") or marker.startswith("```"):
                break
        if closing_idx > 0:
            paragraph_end = lines[closing_idx][1]
            paragraphs.append(text_norm[:paragraph_end])
            i = closing_idx + 1
            while i < line_count and not _trim_markdown_line_whitespace(lines[i][3]):
                i += 1
            delimiter_end = lines[i][0] if i < line_count else len(text_norm)
            delimiters.append(text_norm[paragraph_end:delimiter_end])

    current_start: int | None = None
    current_end: int | None = None
    in_fence: str | None = None
    fence_len = 0
    in_math = False

    while i < line_count:
        line = lines[i][3]
        stripped = _trim_markdown_line_whitespace(line)

        if in_fence is None:
            if stripped.startswith("```"):
                if current_start is None:
                    current_start = i
                current_end = i
                in_fence = "```"
                fence_len = len(stripped) - len(stripped.lstrip("`"))
                i += 1
                continue
            if stripped.startswith("~~~"):
                if current_start is None:
                    current_start = i
                current_end = i
                in_fence = "~~~"
                fence_len = len(stripped) - len(stripped.lstrip("~"))
                i += 1
                continue
        else:
            current_end = i
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

        if not in_math:
            if stripped.startswith("$$"):
                if current_start is None:
                    current_start = i
                current_end = i
                if not (stripped.endswith("$$") and len(stripped) > 2):
                    in_math = True
                i += 1
                continue
        else:
            current_end = i
            if stripped.endswith("$$") or stripped == "$$":
                in_math = False
            i += 1
            continue

        if not stripped:
            if current_start is not None and current_end is not None:
                paragraph_start = lines[current_start][0]
                paragraph_end = lines[current_end][1]
                paragraphs.append(text_norm[paragraph_start:paragraph_end])
                i += 1
                while i < line_count and not _trim_markdown_line_whitespace(lines[i][3]):
                    i += 1
                delimiter_end = lines[i][0] if i < line_count else len(text_norm)
                delimiters.append(text_norm[paragraph_end:delimiter_end])
                current_start = None
                current_end = None
                continue
        else:
            if current_start is None:
                current_start = i
            current_end = i

        i += 1

    if current_start is not None and current_end is not None:
        paragraph_start = lines[current_start][0]
        paragraph_end = lines[current_end][1]
        paragraphs.append(text_norm[paragraph_start:paragraph_end])
        delimiters.append(text_norm[paragraph_end:])

    return _ParsedDocument(prefix, paragraphs, delimiters)


def split_paragraphs_with_delims(text: str) -> tuple[list[str], list[str]]:
    """Split text into paragraphs while preserving exact delimiters between them."""
    parsed = _parse_document(text)
    return parsed.paragraphs, parsed.delimiters


def split_paragraphs(text: str) -> list[str]:
    """Split text into logical Markdown paragraphs / block elements."""
    paras, _ = split_paragraphs_with_delims(text)
    return paras


def compute_diff(old_text: str, new_text: str) -> list[dict]:
    """Compute a deterministic text diff plus non-content delimiter changes."""
    old_document = _parse_document(old_text)
    new_document = _parse_document(new_text)
    old_paras = old_document.paragraphs
    old_delimiters = old_document.delimiters
    new_paras = new_document.paragraphs
    new_delimiters = new_document.delimiters

    changes = []
    if old_document.prefix != new_document.prefix:
        changes.append({"type": "prefix", "content": new_document.prefix})

    if old_paras == new_paras and old_delimiters == new_delimiters:
        return changes

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

    def add_delimiter_change(old_idx: int, new_idx: int) -> None:
        if old_delimiters[old_idx] != new_delimiters[new_idx]:
            changes.append(
                {
                    "type": "delimiter",
                    "paraIdx": old_idx,
                    "delimiter": new_delimiters[new_idx],
                }
            )

    for idx in range(prefix):
        add_delimiter_change(idx, idx)

    mid_old = old_paras[prefix : m - suffix]
    mid_new = new_paras[prefix : n - suffix]
    mid_m = len(mid_old)
    mid_n = len(mid_new)

    dp = [[0] * (mid_n + 1) for _ in range(mid_m + 1)]
    for i in range(1, mid_m + 1):
        for j in range(1, mid_n + 1):
            if mid_old[i - 1] == mid_new[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    operations = []
    i = mid_m
    j = mid_n
    while i > 0 or j > 0:
        if i > 0 and j > 0 and mid_old[i - 1] == mid_new[j - 1]:
            operations.append("equal")
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j - 1] >= dp[i - 1][j]):
            operations.append("insert")
            j -= 1
        else:
            operations.append("delete")
            i -= 1
    operations.reverse()

    old_cursor = 0
    new_cursor = 0
    block_start: tuple[int, int] | None = None

    def emit_block(old_start: int, new_start: int, old_end: int, new_end: int) -> None:
        old_len = old_end - old_start
        new_len = new_end - new_start
        paired = min(old_len, new_len)

        for offset in range(paired):
            target_idx = prefix + new_start + offset
            changes.append(
                {
                    "type": "replace",
                    "paraIdx": prefix + old_start + offset,
                    "content": new_paras[target_idx],
                    "delimiter": new_delimiters[target_idx],
                }
            )
        for offset in range(paired, old_len):
            changes.append({"type": "delete", "paraIdx": prefix + old_start + offset})
        for offset in range(paired, new_len):
            target_idx = prefix + new_start + offset
            changes.append(
                {
                    "type": "insert",
                    "paraIdx": prefix + old_end,
                    "content": new_paras[target_idx],
                    "delimiter": new_delimiters[target_idx],
                }
            )

    for operation in operations:
        if operation == "equal":
            if block_start is not None:
                emit_block(*block_start, old_cursor, new_cursor)
                block_start = None
            add_delimiter_change(prefix + old_cursor, prefix + new_cursor)
            old_cursor += 1
            new_cursor += 1
        else:
            if block_start is None:
                block_start = (old_cursor, new_cursor)
            if operation == "delete":
                old_cursor += 1
            else:
                new_cursor += 1

    if block_start is not None:
        emit_block(*block_start, old_cursor, new_cursor)

    for offset in range(suffix):
        add_delimiter_change(m - suffix + offset, n - suffix + offset)

    return changes


def apply_changes(text: str, changes: list) -> str:
    """将 changes 应用到 text，返回新文本，保留未修改段落的原生空白分隔符。"""
    if not changes:
        return text

    document = _parse_document(text)
    prefix = document.prefix
    paragraphs = document.paragraphs
    delimiters = document.delimiters

    # 分类 changes
    missing_delimiter = object()
    replaces = {}  # paraIdx -> (new_content, optional delimiter)
    delimiter_changes = {}  # paraIdx -> new delimiter without changing text
    deletes = set()  # paraIdx
    inserts = []  # list of (paraIdx, content)

    for ch in changes:
        t = ch.get("type")
        idx = ch.get("paraIdx", 0)
        if t == "prefix":
            prefix = ch.get("content", "")
        elif t == "replace":
            replaces[idx] = (ch.get("content", ""), ch.get("delimiter", missing_delimiter))
        elif t == "delete":
            deletes.add(idx)
        elif t == "delimiter":
            delimiter_changes[idx] = ch.get("delimiter", "")
        elif t == "insert":
            inserts.append((idx, ch.get("content", ""), ch.get("delimiter", missing_delimiter)))

    # 按 paraIdx 分组 inserts
    inserts_by_idx = {}
    for idx, content, delimiter in inserts:
        inserts_by_idx.setdefault(idx, []).append((content, delimiter))

    result_paras = []
    result_delims = []
    result_delims_explicit = []
    n = len(paragraphs)
    for i in range(n):
        # 先插入"在此段落之前"的 inserts
        if i in inserts_by_idx:
            for content, delimiter in inserts_by_idx[i]:
                result_paras.append(content)
                result_delims.append("\n\n" if delimiter is missing_delimiter else delimiter)
                result_delims_explicit.append(delimiter is not missing_delimiter)
        # 处理原段落
        if i in deletes:
            continue
        if i in replaces:
            content, delimiter = replaces[i]
            result_paras.append(content)
        else:
            result_paras.append(paragraphs[i])
            delimiter = missing_delimiter
        if i in delimiter_changes:
            result_delims.append(delimiter_changes[i])
            result_delims_explicit.append(True)
        elif delimiter is not missing_delimiter:
            result_delims.append(delimiter)
            result_delims_explicit.append(True)
        elif i < len(delimiters):
            result_delims.append(delimiters[i])
            result_delims_explicit.append(False)
        else:
            result_delims.append("\n\n")
            result_delims_explicit.append(False)

    # 处理 paraIdx >= n 的 inserts（追加到末尾）
    trailing_indices = [idx for idx in sorted(inserts_by_idx.keys()) if idx >= n]
    if (
        trailing_indices
        and result_delims
        and not result_delims_explicit[-1]
        and result_delims[-1] in ("", "\n")
    ):
        result_delims[-1] = "\n\n"

    last_trailing_delimiter = missing_delimiter
    for idx in trailing_indices:
        for content, delimiter in inserts_by_idx[idx]:
            result_paras.append(content)
            result_delims.append("\n\n" if delimiter is missing_delimiter else delimiter)
            result_delims_explicit.append(delimiter is not missing_delimiter)
            last_trailing_delimiter = delimiter

    if (
        trailing_indices
        and last_trailing_delimiter is missing_delimiter
        and result_delims
        and result_delims[-1] == "\n\n"
    ):
        result_delims[-1] = ""

    result_parts = [prefix]
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
        if change_type not in {"insert", "delete", "replace", "delimiter", "prefix"}:
            raise ValueError(f"invalid change type: {change_type!r}")

        if change_type == "prefix":
            if "paraIdx" in change:
                raise ValueError("prefix changes must not include paraIdx")
            if "delimiter" in change:
                raise ValueError("prefix changes must not include delimiter")
            if not isinstance(change.get("content"), str):
                raise TypeError("prefix content must be a string")
            continue

        para_idx = change.get("paraIdx")
        if isinstance(para_idx, bool) or not isinstance(para_idx, int):
            raise TypeError("paraIdx must be an integer")
        if para_idx < 0:
            raise ValueError("paraIdx must be nonnegative")
        if change_type == "insert":
            if para_idx > base_para_count:
                raise ValueError("insert paraIdx exceeds base paragraph count")
        elif para_idx >= base_para_count:
            if change_type == "delimiter":
                raise ValueError("delimiter paraIdx exceeds base paragraph count")
            raise ValueError("replace/delete paraIdx exceeds base paragraph count")

        if change_type == "delimiter":
            if "content" in change:
                raise ValueError("delimiter changes must not include content")
            if not isinstance(change.get("delimiter"), str):
                raise TypeError("delimiter must be a string")
        else:
            if change_type in {"insert", "replace"} and not isinstance(change.get("content"), str):
                raise TypeError("insert/replace content must be a string")
            if "delimiter" in change and change_type not in {"insert", "replace"}:
                raise ValueError("delimiter is only valid for insert/replace changes")
            if "delimiter" in change and not isinstance(change["delimiter"], str):
                raise TypeError("delimiter must be a string")


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
        if t == "prefix":
            transformed.append(dict(ch))
            continue
        idx = ch["paraIdx"]
        target_idx = map_position(idx)
        if t == "insert":
            transformed_change = {
                "type": "insert",
                "paraIdx": target_idx,
                "content": ch["content"],
            }
            if "delimiter" in ch:
                transformed_change["delimiter"] = ch["delimiter"]
            transformed.append(transformed_change)
        elif t == "replace":
            if idx in deleted:
                # Target was deleted by another user: preserve content as insert
                transformed_change = {
                    "type": "insert",
                    "paraIdx": target_idx,
                    "content": ch["content"],
                }
            else:
                transformed_change = {
                    "type": "replace",
                    "paraIdx": target_idx,
                    "content": ch["content"],
                }
            if "delimiter" in ch:
                transformed_change["delimiter"] = ch["delimiter"]
            transformed.append(transformed_change)
        elif t == "delete" and idx not in deleted:
            transformed.append({"type": "delete", "paraIdx": target_idx})
        elif t == "delimiter" and idx not in deleted:
            transformed.append({**ch, "paraIdx": target_idx})

    return transformed
