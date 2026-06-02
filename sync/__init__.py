"""Sync module - file synchronization with LCS merge."""

from __future__ import annotations

import re
import unicodedata

HEADER_RE = re.compile(r'^(#{2,4}) \d+ \w+, \w+')


def merge(s1: str, s2: str) -> str:
    """Merge two strings by identifying longest common subsequences of lines."""
    if not s1:
        return s2
    if not s2:
        return s1

    lines1 = s1.split("\n")
    lines2 = s2.split("\n")

    # DP table for LCS
    lcs = [[0] * (len(lines2) + 1) for _ in range(len(lines1) + 1)]
    for i in range(1, len(lines1) + 1):
        for j in range(1, len(lines2) + 1):
            if lines1[i - 1] == lines2[j - 1]:
                lcs[i][j] = lcs[i - 1][j - 1] + 1
            else:
                lcs[i][j] = max(lcs[i - 1][j], lcs[i][j - 1])

    result = _backtrack(lines1, lines2, lcs, len(lines1), len(lines2))
    result = _merge_emojis_in_headers(result)
    return "\n".join(result)


def _backtrack(lines1: list[str], lines2: list[str], lcs: list[list[int]], i: int, j: int) -> list[str]:
    if i == 0 and j == 0:
        return []
    if i == 0:
        return _backtrack(lines1, lines2, lcs, i, j - 1) + [lines2[j - 1]]
    if j == 0:
        return _backtrack(lines1, lines2, lcs, i - 1, j) + [lines1[i - 1]]
    if lines1[i - 1] == lines2[j - 1]:
        return _backtrack(lines1, lines2, lcs, i - 1, j - 1) + [lines1[i - 1]]
    if lcs[i - 1][j] > lcs[i][j - 1]:
        return _backtrack(lines1, lines2, lcs, i - 1, j) + [lines1[i - 1]]
    return _backtrack(lines1, lines2, lcs, i, j - 1) + [lines2[j - 1]]


def _merge_emojis_in_headers(lines: list[str]) -> list[str]:
    """Merge consecutive journal headers that differ only by emoji."""
    result: list[str] = []
    groups = _group_consecutive_headers(lines)
    for group in groups:
        if len(group) == 1:
            result.append(group[0])
            continue
        # Match trailing non-word, non-space chars (emojis)
        emoji_re = re.compile(r' [^\w\s!-/:-@\[-`{-~]+$')
        date = emoji_re.sub("", group[0])
        prefix_same = True
        for line in group:
            emojis = emoji_re.search(line)
            emojis_str = emojis.group() if emojis else ""
            if date + emojis_str != line:
                prefix_same = False
                break
        if not prefix_same:
            result.extend(group)
            continue
        found_emojis = ""
        for line in group:
            emojis = emoji_re.search(line)
            if emojis:
                found_emojis += emojis.group().strip()
        if found_emojis:
            found_emojis = " " + _unique_graphemes(found_emojis)
        result.append(date + found_emojis)
    return result


def _group_consecutive_headers(lines: list[str]) -> list[list[str]]:
    groups: list[list[str]] = []
    i = 0
    while i < len(lines):
        if HEADER_RE.match(lines[i]):
            group: list[str] = []
            while i < len(lines) and HEADER_RE.match(lines[i]):
                group.append(lines[i])
                i += 1
            groups.append(group)
        else:
            groups.append([lines[i]])
            i += 1
    return groups


def _unique_graphemes(s: str) -> str:
    """Return string with unique grapheme clusters, preserving order."""
    result = ""
    # Use unicodedata to iterate grapheme clusters
    i = 0
    while i < len(s):
        # Find end of current grapheme cluster
        j = i + 1
        while j < len(s) and unicodedata.combining(s[j]):
            j += 1
        cluster = s[i:j]
        if cluster not in result:
            result += cluster
        i = j
    return result
