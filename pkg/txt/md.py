"""Markdown processing utilities."""

from __future__ import annotations

import hashlib
import re

from nas_md.pkg.txt.str import norm_new_lines

MD_EXT = ".md"

OPEN_TAGS = {
    "*": "<i>",
    "**": "<b>",
    "_": "<i>",
    "__": "<b>",
}

CLOSE_TAGS = {
    "*": "</i>",
    "**": "</b>",
    "_": "</i>",
    "__": "</b>",
}

CHAT_TIMESTAMP_RE = re.compile(r"^`\d{2}:\d{2}` ")


def strip_chat_timestamp(s: str) -> str:
    return CHAT_TIMESTAMP_RE.sub("", s)


def add_header_and_text(existing_content: str, header: str, new_content: str) -> str:
    if header not in existing_content:
        if not existing_content:
            return f"{header}\n{new_content}"
        return f"{header}\n{new_content}\n\n{existing_content}"

    lines = existing_content.split("\n")
    header_index = -1
    for i, line in enumerate(lines):
        if line == header:
            header_index = i
            break

    if header_index == -1:
        return f"{header}\n{new_content}\n\n{existing_content}"

    insert_index = header_index + 1
    for i in range(header_index + 1, len(lines)):
        if lines[i].startswith("###"):
            insert_index = i
            break
        insert_index = i + 1

    new_lines = [*lines[:insert_index], new_content]
    if insert_index < len(lines) and lines[insert_index].strip():
        new_lines.append("")
    new_lines.extend(lines[insert_index:])
    return "\n".join(new_lines)


def incomplete_checklist_items(md: str) -> list[str]:
    items, is_completed = checklist_items(md)
    return [item for item in items if not is_completed[item]]


def checklist_items(md: str) -> tuple[list[str], dict[str, bool]]:
    items: list[str] = []
    is_completed: dict[str, bool] = {}
    for line in md.split("\n"):
        line = line.strip()
        if line.startswith("- [ ] "):
            item = line[6:]
            items.append(item)
            is_completed[item] = False
        elif line.startswith("- [x] "):
            item = line[6:]
            items.append(item)
            is_completed[item] = True
    return items, is_completed


def add_checklist_item(md: str, item: str, checked: bool) -> str:
    item = norm_new_lines(item).replace("\n", " ")
    md, _ = remove_checklist_item(md, item)
    lines = md.split("\n")

    if checked:
        lines.append("- [x] " + item)
    else:
        insert_index = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            if line.startswith("- [ ] "):
                insert_index = i
        if insert_index == len(lines):
            lines.append("- [ ] " + item)
        else:
            lines.insert(insert_index, "- [ ] " + item)

    return "\n".join(lines).strip()


def complete_checklist_item(md: str, item_hash: str) -> tuple[str, str]:
    found_item = ""
    lines = md.split("\n")
    found_index = -1
    for i, line in enumerate(lines):
        line = line.strip()
        if len(line) < 6:
            continue
        if line.startswith("- [ ] ") and _hash(line[6:]) == item_hash:
            found_item = line[6:]
            found_index = i
            break
    if found_index != -1:
        lines[found_index] = "- [x] " + found_item
    return "\n".join(lines), found_item


def remove_checklist_item(md: str, item_or_hash: str) -> tuple[str, str]:
    removed_item = ""
    lines = md.split("\n")
    new_lines = []
    for line in lines:
        line = line.strip()
        if len(line) < 6:
            new_lines.append(line)
            continue
        if _hash(line[6:]) == item_or_hash or line[6:] == item_or_hash:
            removed_item = line[6:]
            continue
        new_lines.append(line)
    return "\n".join(new_lines), removed_item


def remove_completed_checklist_items(md: str) -> tuple[str, str]:
    removed_md = ""
    lines = md.split("\n")
    new_lines = []
    for line in lines:
        line = line.strip()
        if len(line) < 6:
            new_lines.append(line)
            continue
        if line.startswith("- [x] "):
            removed_md += line + "\n"
            continue
        new_lines.append(line)
    return "\n".join(new_lines), removed_md


def checklist_item(md: str, item_or_hash: str) -> str:
    for line in md.split("\n"):
        line = line.strip()
        if len(line) < 6:
            continue
        if _hash(line[6:]) == item_or_hash or line[6:] == item_or_hash:
            return line[6:]
    return ""


def markdown_to_html(md: str) -> str:
    """Convert markdown to Telegram-supported HTML subset."""
    # Escape HTML first
    result = escape_html(md)

    # Protect code blocks and inline code with placeholders
    code_blocks = {}
    inline_codes = {}

    # Extract code blocks
    for i, m in enumerate(re.finditer(r"```(.*?)```", result, re.DOTALL)):
        placeholder = f"§CODEBLOCK{i}§"
        code_blocks[placeholder] = "<pre>" + m.group(1).strip() + "</pre>"
        result = result.replace(m.group(), placeholder)

    # Extract inline code
    for i, m in enumerate(re.finditer(r"`([^`]+)`", result)):
        placeholder = f"§INLINE{i}§"
        inline_codes[placeholder] = "<code>" + m.group(1) + "</code>"
        result = result.replace(m.group(), placeholder)

    # Convert headers (# -> <b>)
    result = re.sub(r"^#+\s*(.+)$", r"<b>\1</b>", result, flags=re.MULTILINE)

    # Convert bold (**text** or __text__)
    result = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", result)
    result = re.sub(r"__(.+?)__", r"<b>\1</b>", result)

    # Convert italic (*text* or _text_)
    result = re.sub(r"\*(.+?)\*", r"<i>\1</i>", result)
    result = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", result)

    # Restore code blocks and inline code
    for placeholder, code in code_blocks.items():
        result = result.replace(placeholder, code)
    for placeholder, code in inline_codes.items():
        result = result.replace(placeholder, code)

    return result


def _markdown_parser():
    """Parser combinator for markdown bold/italic."""
    text = _not_markdown()
    italic_no_bold = _or(
        _and(_open("*"), text, _close("*")),
        _and(_open("_"), text, _close("_")),
    )
    bold = _or(
        _and(_open("**"), _or(text, italic_no_bold), some=True),
        _and(_open("__"), _or(text, italic_no_bold), some=True),
    )
    italic = _or(
        _and(_open("*"), _or(text, bold), some=True),
        _and(_open("_"), _or(text, bold), some=True),
    )
    span = _or(bold, italic, text)
    return lambda input_str: _some(span)(input_str)


def _open(t: str):
    def parser(input_str: str) -> list[dict]:
        if input_str.startswith(t):
            return [{"consumed": OPEN_TAGS[t], "left": input_str[len(t) :]}]
        return []

    return parser


def _close(t: str):
    def parser(input_str: str) -> list[dict]:
        if input_str.startswith(t):
            return [{"consumed": CLOSE_TAGS[t], "left": input_str[len(t) :]}]
        return []

    return parser


def _or(*parsers):
    def combined(input_str: str) -> list[dict]:
        results = []
        for p in parsers:
            results.extend(p(input_str))
        return results

    return combined


def _and(*parsers, some: bool = False):
    def combined(input_str: str) -> list[dict]:
        results = [{"consumed": "", "left": input_str}]
        for p in parsers:
            new_results = []
            for r in results:
                for parsed in p(r["left"]):
                    if parsed["consumed"]:
                        new_results.append(
                            {"consumed": r["consumed"] + parsed["consumed"], "left": parsed["left"]}
                        )
            if not new_results:
                return []
            results = new_results
        return results

    return combined


def _some(parser):
    def combined(input_str: str) -> list[dict]:
        return _recursive(input_str, parser, 0)

    return combined


def _recursive(input_str: str, parser, depth: int) -> list[dict]:
    results = []
    empty = True
    for item in parser(input_str):
        if not item["consumed"]:
            continue
        empty = False
        for child in _recursive(item["left"], parser, depth + 1):
            results.append(
                {"consumed": item["consumed"] + child["consumed"], "left": child["left"]}
            )
    if empty and depth != 0:
        results.append({"consumed": "", "left": input_str})
    return results


def _not_markdown():
    def parser(input_str: str) -> list[dict]:
        for i, ch in enumerate(input_str):
            if ch == "*" or ch == "_":
                return [{"consumed": input_str[:i], "left": input_str[i:]}]
        if input_str:
            return [{"consumed": input_str, "left": ""}]
        return []

    return parser


def escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _hash(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()[:11]
