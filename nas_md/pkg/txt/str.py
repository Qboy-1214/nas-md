"""Text utility functions."""

from __future__ import annotations

import re


def i64(i: int) -> str:
    return str(i)


def ucfirst(s: str) -> str:
    if not s:
        return s
    return s[0].upper() + s[1:]


def lcfirst(s: str) -> str:
    if not s:
        return s
    return s[0].lower() + s[1:]


def substr(input_str: str, start: int, length: int) -> str:
    if start < 0 or length < 0:
        return ""
    as_runes = list(input_str)
    if start >= len(as_runes):
        return ""
    if start + length > len(as_runes):
        length = len(as_runes) - start
    return "".join(as_runes[start : start + length])


def emoji(emoji_str: str, s: str) -> str:
    if not emoji_str:
        return s
    # Custom prefixes to strip
    for prefix in ("WRK ", "UA ", "US ", "CY ", "HOB ", "SRB ", "PL "):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    return f"{emoji_str} {s}"


def norm_new_lines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def is_multiline(text: str) -> bool:
    text = norm_new_lines(text)
    lines = text.split("\n")
    return len(lines) > 1


def split_text_into_chunks(text: str, max_len: int) -> list[str]:
    text = text.strip()
    if max_len <= 0:
        return [text]
    if not text:
        return [""]
    chunks: list[str] = []
    runes = list(text)
    while len(runes) > max_len:
        split_index = -1
        sub_str = runes[:max_len]
        for i in range(len(sub_str) - 1, -1, -1):
            if sub_str[i] == "\n":
                split_index = i
                break
        if split_index == -1:
            for i in range(len(sub_str) - 1, -1, -1):
                if sub_str[i] == " ":
                    split_index = i
                    break
        if split_index == -1:
            split_index = max_len
        trimmed = "".join(runes[:split_index]).strip()
        if trimmed:
            chunks.append(trimmed)
        runes = list("".join(runes[split_index:]).strip())
    remaining = "".join(runes).strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def first_word(s: str) -> str:
    s = s.strip()
    # Match word characters (including Unicode) - equivalent to [^\s\p{P}]+
    m = re.match(r"[^\s!-/:-@\[-`{-~]+", s)
    if m:
        return m.group()
    return ""


def escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def strip_html_tags(s: str) -> str:
    return re.sub(r"<[^>]*>", "", s)


def replace_with_placeholders(
    text: str, regex: str, placeholder: str
) -> tuple[str, dict[str, str]]:
    placeholders: dict[str, str] = {}
    counter = 0

    def replacer(match: re.Match) -> str:
        nonlocal counter
        p = f"#{placeholder}{counter}#"
        placeholders[p] = match.group()
        counter += 1
        return p

    result = re.sub(regex, replacer, text, flags=re.DOTALL)
    return result, placeholders


def restore_from_placeholders(text: str, placeholders: dict[str, str]) -> str:
    for placeholder, original in placeholders.items():
        text = text.replace(placeholder, original)
    return text


def similar(str1: str, str2: str) -> int:
    """Returns similarity score in [0, 100]."""
    txt1, txt2 = list(str1), list(str2)
    if not txt1 or not txt2:
        return 0
    return similar_char(txt1, txt2) * 200 // (len(txt1) + len(txt2))


def similar_str(str1: list[str], str2: list[str]) -> tuple[int, int, int]:
    max_len, pos1, pos2 = 0, 0, 0
    len1, len2 = len(str1), len(str2)
    for p in range(len1):
        for q in range(len2):
            tmp = 0
            while p + tmp < len1 and q + tmp < len2 and str1[p + tmp] == str2[q + tmp]:
                tmp += 1
            if tmp > max_len:
                max_len, pos1, pos2 = tmp, p, q
    return max_len, pos1, pos2


def similar_char(str1: list[str], str2: list[str]) -> int:
    max_len, pos1, pos2 = similar_str(str1, str2)
    total = max_len
    if max_len != 0:
        if pos1 > 0 and pos2 > 0:
            total += similar_char(str1[:pos1], str2[:pos2])
        if pos1 + max_len < len(str1) and pos2 + max_len < len(str2):
            total += similar_char(str1[pos1 + max_len :], str2[pos2 + max_len :])
    return total
