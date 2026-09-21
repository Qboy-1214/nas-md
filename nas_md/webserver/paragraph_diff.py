"""Paragraph-level diff engine for real-time collaborative editing."""

from dataclasses import dataclass


class DiffWorkLimitExceeded(RuntimeError):
    """Raised when an exact paragraph diff would exceed its bounded work budget."""


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


def _backtrack_myers(trace: list[dict[int, int]], old_len: int, new_len: int) -> list[str]:
    """Reconstruct a deterministic edit script from a bounded Myers trace."""
    old_idx = old_len
    new_idx = new_len
    operations: list[str] = []

    for distance in range(len(trace) - 1, 0, -1):
        previous = trace[distance - 1]
        diagonal = old_idx - new_idx
        if diagonal == -distance or (
            diagonal != distance and previous.get(diagonal - 1, -1) < previous.get(diagonal + 1, -1)
        ):
            previous_diagonal = diagonal + 1
            edit = "insert"
        else:
            previous_diagonal = diagonal - 1
            edit = "delete"

        previous_old_idx = previous[previous_diagonal]
        previous_new_idx = previous_old_idx - previous_diagonal
        while old_idx > previous_old_idx and new_idx > previous_new_idx:
            operations.append("equal")
            old_idx -= 1
            new_idx -= 1
        operations.append(edit)
        old_idx = previous_old_idx
        new_idx = previous_new_idx

    while old_idx > 0 and new_idx > 0:
        operations.append("equal")
        old_idx -= 1
        new_idx -= 1
    operations.extend("delete" for _ in range(old_idx))
    operations.extend("insert" for _ in range(new_idx))
    operations.reverse()
    return operations


_MYERS_WORK_BUDGET = 262_144


def _bounded_myers_operations(
    old_items: list[str], new_items: list[str], work_budget: int = _MYERS_WORK_BUDGET
) -> list[str] | None:
    """Return a shortest edit script when Myers completes within the work budget."""
    old_len = len(old_items)
    new_len = len(new_items)
    previous = {1: 0}
    trace: list[dict[int, int]] = []
    work = 0

    for distance in range(old_len + new_len + 1):
        current: dict[int, int] = {}
        for diagonal in range(-distance, distance + 1, 2):
            work += 1
            if work > work_budget:
                return None
            if diagonal == -distance or (
                diagonal != distance
                and previous.get(diagonal - 1, -1) < previous.get(diagonal + 1, -1)
            ):
                old_idx = previous.get(diagonal + 1, 0)
            else:
                old_idx = previous.get(diagonal - 1, 0) + 1
            new_idx = old_idx - diagonal
            while (
                old_idx < old_len and new_idx < new_len and old_items[old_idx] == new_items[new_idx]
            ):
                work += 1
                if work > work_budget:
                    return None
                old_idx += 1
                new_idx += 1
            current[diagonal] = old_idx
            if old_idx >= old_len and new_idx >= new_len:
                trace.append(current)
                return _backtrack_myers(trace, old_len, new_len)
        trace.append(current)
        previous = current
    return None


def _operations_from_matches(
    old_len: int, new_len: int, matches: list[tuple[int, int]]
) -> list[str]:
    operations: list[str] = []
    old_cursor = 0
    new_cursor = 0
    for old_idx, new_idx in matches:
        operations.extend("delete" for _ in range(old_idx - old_cursor))
        operations.extend("insert" for _ in range(new_idx - new_cursor))
        operations.append("equal")
        old_cursor = old_idx + 1
        new_cursor = new_idx + 1
    operations.extend("delete" for _ in range(old_len - old_cursor))
    operations.extend("insert" for _ in range(new_len - new_cursor))
    return operations


def _increasing_anchors(candidates: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Select a deterministic LIS by new index from old-index-ordered candidates."""
    if not candidates:
        return []

    tails: list[int] = []
    predecessors = [-1] * len(candidates)
    for candidate_idx, (_, new_idx) in enumerate(candidates):
        low = 0
        high = len(tails)
        while low < high:
            midpoint = (low + high) // 2
            if candidates[tails[midpoint]][1] < new_idx:
                low = midpoint + 1
            else:
                high = midpoint
        if low:
            predecessors[candidate_idx] = tails[low - 1]
        if low == len(tails):
            tails.append(candidate_idx)
        else:
            tails[low] = candidate_idx

    result = []
    candidate_idx = tails[-1]
    while candidate_idx != -1:
        result.append(candidates[candidate_idx])
        candidate_idx = predecessors[candidate_idx]
    result.reverse()
    return result


def _positions_by_value(items: list[str], start: int, end: int) -> dict[str, list[int]]:
    positions: dict[str, list[int]] = {}
    for idx in range(start, end):
        positions.setdefault(items[idx], []).append(idx)
    return positions


_MATCH_PAIR_WORK_BUDGET = 1_000_000


def _hunt_szymanski_matches(
    old_items: list[str], new_positions: dict[str, list[int]]
) -> list[tuple[int, int]]:
    """Compute an exact deterministic LCS from all equal-position pairs."""
    candidates: list[tuple[int, int]] = []
    predecessors: list[int] = []
    tails: list[int] = []

    for old_idx, value in enumerate(old_items):
        for new_idx in reversed(new_positions.get(value, [])):
            candidate_idx = len(candidates)
            low = 0
            high = len(tails)
            while low < high:
                midpoint = (low + high) // 2
                if candidates[tails[midpoint]][1] < new_idx:
                    low = midpoint + 1
                else:
                    high = midpoint
            candidates.append((old_idx, new_idx))
            predecessors.append(tails[low - 1] if low else -1)
            if low == len(tails):
                tails.append(candidate_idx)
            else:
                tails[low] = candidate_idx

    matches = []
    candidate_idx = tails[-1]
    while candidate_idx != -1:
        matches.append(candidates[candidate_idx])
        candidate_idx = predecessors[candidate_idx]
    matches.reverse()
    return matches


def _exact_lcs_matches(old_items: list[str], new_items: list[str]) -> list[tuple[int, int]]:
    """Return exact LCS matches or raise before expanding an excessive match graph."""
    old_positions = _positions_by_value(old_items, 0, len(old_items))
    new_positions = _positions_by_value(new_items, 0, len(new_items))
    rank_candidates: list[tuple[int, int]] = []
    common_count_upper_bound = 0
    match_pair_count = 0

    for value, positions in old_positions.items():
        matching = new_positions.get(value)
        if not matching:
            continue
        common_count_upper_bound += min(len(positions), len(matching))
        match_pair_count += len(positions) * len(matching)
        rank_candidates.extend(zip(positions, matching, strict=False))

    rank_candidates.sort()
    rank_matches = _increasing_anchors(rank_candidates)
    # A common subsequence cannot use a value more often than its lower
    # occurrence count. Reaching that summed bound proves this LIS is an LCS.
    if len(rank_matches) == common_count_upper_bound or match_pair_count == len(rank_candidates):
        return rank_matches

    if match_pair_count > _MATCH_PAIR_WORK_BUDGET:
        raise DiffWorkLimitExceeded("exact paragraph diff work limit exceeded")

    return _hunt_szymanski_matches(old_items, new_positions)


def _diff_operations(old_items: list[str], new_items: list[str]) -> list[str]:
    """Build an exact deterministic edit script with bounded auxiliary memory."""
    operations: list[str] = []
    tasks: list[tuple] = [("segment", 0, len(old_items), 0, len(new_items))]

    while tasks:
        task = tasks.pop()
        if task[0] == "equal":
            operations.extend("equal" for _ in range(task[1]))
            continue

        _, old_start, old_end, new_start, new_end = task
        prefix_len = 0
        while (
            old_start + prefix_len < old_end
            and new_start + prefix_len < new_end
            and old_items[old_start + prefix_len] == new_items[new_start + prefix_len]
        ):
            prefix_len += 1
        if prefix_len:
            operations.extend("equal" for _ in range(prefix_len))
            old_start += prefix_len
            new_start += prefix_len

        suffix_len = 0
        while (
            old_start < old_end - suffix_len
            and new_start < new_end - suffix_len
            and old_items[old_end - 1 - suffix_len] == new_items[new_end - 1 - suffix_len]
        ):
            suffix_len += 1
        if suffix_len:
            tasks.append(("equal", suffix_len))
            old_end -= suffix_len
            new_end -= suffix_len

        old_len = old_end - old_start
        new_len = new_end - new_start
        if not old_len:
            operations.extend("insert" for _ in range(new_len))
            continue
        if not new_len:
            operations.extend("delete" for _ in range(old_len))
            continue

        old_segment = old_items[old_start:old_end]
        new_segment = new_items[new_start:new_end]
        if set(old_segment).isdisjoint(new_segment):
            operations.extend("delete" for _ in range(old_len))
            operations.extend("insert" for _ in range(new_len))
            continue

        segment_operations = _bounded_myers_operations(old_segment, new_segment)
        if segment_operations is not None:
            operations.extend(segment_operations)
            continue

        matches = _exact_lcs_matches(old_segment, new_segment)
        operations.extend(_operations_from_matches(old_len, new_len, matches))

    return operations


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

    operations = _diff_operations(mid_old, mid_new)

    old_cursor = 0
    new_cursor = 0
    block_start: tuple[int, int] | None = None

    def emit_block(old_start: int, new_start: int, old_end: int, new_end: int) -> None:
        old_len = old_end - old_start
        new_len = new_end - new_start
        paired = min(old_len, new_len)

        for offset in range(paired):
            source_idx = prefix + old_start + offset
            target_idx = prefix + new_start + offset
            replacement = {
                "type": "replace",
                "paraIdx": source_idx,
                "content": new_paras[target_idx],
                "fallbackDelimiter": new_delimiters[target_idx],
            }
            if old_delimiters[source_idx] != new_delimiters[target_idx]:
                replacement["delimiter"] = new_delimiters[target_idx]
            changes.append(replacement)
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
            if "fallbackDelimiter" in change:
                raise ValueError("fallbackDelimiter is only valid for replace changes")
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
        if "fallbackDelimiter" in change:
            if change_type != "replace":
                raise ValueError("fallbackDelimiter is only valid for replace changes")
            if not isinstance(change["fallbackDelimiter"], str):
                raise TypeError("fallbackDelimiter must be a string")


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
                if "fallbackDelimiter" in ch:
                    transformed_change["delimiter"] = ch["fallbackDelimiter"]
                elif "delimiter" in ch:
                    transformed_change["delimiter"] = ch["delimiter"]
            else:
                transformed_change = {
                    "type": "replace",
                    "paraIdx": target_idx,
                    "content": ch["content"],
                }
                if "delimiter" in ch:
                    transformed_change["delimiter"] = ch["delimiter"]
                if "fallbackDelimiter" in ch:
                    transformed_change["fallbackDelimiter"] = ch["fallbackDelimiter"]
            transformed.append(transformed_change)
        elif t == "delete" and idx not in deleted:
            transformed.append({"type": "delete", "paraIdx": target_idx})
        elif t == "delimiter" and idx not in deleted:
            transformed.append({**ch, "paraIdx": target_idx})

    return transformed
