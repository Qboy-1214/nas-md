"""String similarity utilities."""

from __future__ import annotations


def similar(str1: str, str2: str) -> int:
    """Returns similarity score in [0, 100]."""
    txt1, txt2 = list(str1), list(str2)
    if not txt1 or not txt2:
        return 0
    return _similar_char(txt1, txt2) * 200 // (len(txt1) + len(txt2))


def _similar_str(str1: list[str], str2: list[str]) -> tuple[int, int, int]:
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


def _similar_char(str1: list[str], str2: list[str]) -> int:
    max_len, pos1, pos2 = _similar_str(str1, str2)
    total = max_len
    if max_len != 0:
        if pos1 > 0 and pos2 > 0:
            total += _similar_char(str1[:pos1], str2[:pos2])
        if pos1 + max_len < len(str1) and pos2 + max_len < len(str2):
            total += _similar_char(str1[pos1 + max_len:], str2[pos2 + max_len:])
    return total
