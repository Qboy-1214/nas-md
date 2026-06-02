"""Sync module - file synchronization with LCS merge, fslog, and token auth."""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
import unicodedata
from typing import Optional
from urllib.parse import quote as url_quote, unquote as url_unquote

from nas_md.config import server_cfg

HEADER_RE = re.compile(r'^(#{2,4}) \d+ \w+, \w+')


# ── Merge (LCS-based) ────────────────────────────────────────────────

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
    i = 0
    while i < len(s):
        j = i + 1
        while j < len(s) and unicodedata.combining(s[j]):
            j += 1
        cluster = s[i:j]
        if cluster not in result:
            result += cluster
        i = j
    return result


# ── FSLog (file system operation log) ────────────────────────────────

_RENAME_OP = "ren"
_DELETE_OP = "del"
_log_lock = threading.RLock()


def _log_path() -> str:
    """Return the path to the fslog file."""
    working_dir = getattr(server_cfg, 'working_dir', '.')
    return os.path.join(working_dir, "fslog")


def log_rename(timestamp: int, old_path: str, new_path: str) -> None:
    """Log a rename operation to the fslog."""
    with _log_lock:
        try:
            with open(_log_path(), 'a') as f:
                record = f"{timestamp} {_RENAME_OP} {url_quote(old_path, safe='')} {url_quote(new_path, safe='')}\n"
                f.write(record)
                f.flush()
                os.fsync(f.fileno())
        except OSError:
            pass


def log_delete(timestamp: int, filepath: str) -> None:
    """Log a delete operation to the fslog."""
    with _log_lock:
        try:
            with open(_log_path(), 'a') as f:
                record = f"{timestamp} {_DELETE_OP} {url_quote(filepath, safe='')}\n"
                f.write(record)
                f.flush()
                os.fsync(f.fileno())
        except OSError:
            pass


def renames_log(user_id: int, after_timestamp: int) -> dict:
    """Read the renames log. Returns {new_path: old_path} for entries after the given timestamp."""
    with _log_lock:
        result = {}
        try:
            log_file = open(_log_path(), 'r')
        except OSError:
            return result

        try:
            storage_dir = getattr(server_cfg, 'storage_dir', './storage')
            user_prefix = os.path.join(storage_dir, str(user_id)) + "/"

            for line in log_file:
                line = line.strip()
                parts = line.split(" ", 3)
                if len(parts) != 4:
                    continue
                try:
                    timestamp = int(parts[0])
                except ValueError:
                    continue
                op = parts[1]
                if op != _RENAME_OP:
                    continue
                if timestamp < after_timestamp:
                    continue
                old_path = url_unquote(parts[2])
                new_path = url_unquote(parts[3])
                if not old_path.startswith(user_prefix) or not new_path.startswith(user_prefix):
                    continue
                old_path = old_path[len(user_prefix):]
                new_path = new_path[len(user_prefix):]
                result[new_path] = old_path
        finally:
            log_file.close()

        return result


def deletes_log(user_id: int, after_timestamp: int) -> dict:
    """Read the deletes log. Returns {path: deleted_at_timestamp} for entries after the given timestamp."""
    with _log_lock:
        result = {}
        try:
            log_file = open(_log_path(), 'r')
        except OSError:
            return result

        try:
            storage_dir = getattr(server_cfg, 'storage_dir', './storage')
            user_prefix = os.path.join(storage_dir, str(user_id)) + "/"

            for line in log_file:
                line = line.strip()
                parts = line.split(" ", 2)
                if len(parts) != 3:
                    continue
                try:
                    timestamp = int(parts[0])
                except ValueError:
                    continue
                op = parts[1]
                if op != _DELETE_OP:
                    continue
                if timestamp < after_timestamp:
                    continue
                filepath = url_unquote(parts[2])
                if not filepath.startswith(user_prefix):
                    continue
                filepath = filepath[len(user_prefix):]
                if filepath not in result or timestamp > result[filepath]:
                    result[filepath] = timestamp
        finally:
            log_file.close()

        return result


# ── Token authentication ─────────────────────────────────────────────

TOKEN_LENGTH = 32
ONE_TIME_TOKEN_EXPIRATION = 600  # 10 minutes
BAN_FOR_INVALID_TOKEN = 600  # 10 minutes
AUTH_COOKIE_NAME = "token"
AUTH_COOKIE_MAX_AGE = 10 * 365 * 24 * 60 * 60  # ~10 years

_one_time_tokens: dict[str, dict] = {}
_tokens_lock = threading.RLock()
_blocked_ips: dict[str, float] = {}
_blocked_ips_lock = threading.RLock()


def gen_token() -> str:
    """Generate a cryptographically secure random token."""
    import secrets
    return secrets.token_hex(TOKEN_LENGTH)


def hash_token(token: str) -> str:
    """Hash a token with the server salt for storage."""
    salt = getattr(server_cfg, 'tokens_salt', '')
    h = hashlib.sha256()
    h.update((token + salt).encode('utf-8'))
    return h.hexdigest()


def gen_one_time_token(user_id: int) -> str:
    """Generate a one-time token for a user."""
    token = gen_token()
    with _tokens_lock:
        _one_time_tokens[token] = {
            "user_id": user_id,
            "expires_at": time.time() + ONE_TIME_TOKEN_EXPIRATION,
        }
    return token


def find_user_id(token: str) -> tuple:
    """Find user ID by token. Returns (user_id, found)."""
    tokens_dir = getattr(server_cfg, 'tokens_dir', '')
    if not tokens_dir:
        return 0, False

    hashed = hash_token(token)
    token_path = os.path.join(tokens_dir, hashed)
    try:
        with open(token_path, 'r') as f:
            data = f.read().strip()
        return int(data), True
    except (OSError, ValueError):
        return 0, False


def issue_new_permanent_token(one_time_token: str) -> tuple:
    """Exchange a one-time token for a permanent token. Returns (token, ok)."""
    with _tokens_lock:
        data = _one_time_tokens.get(one_time_token)
        if not data:
            return "", False
        if time.time() > data["expires_at"]:
            del _one_time_tokens[one_time_token]
            return "", False
        user_id = data["user_id"]
        del _one_time_tokens[one_time_token]

    token = gen_token()
    tokens_dir = getattr(server_cfg, 'tokens_dir', '')
    if not tokens_dir:
        return "", False

    os.makedirs(tokens_dir, exist_ok=True)
    hashed = hash_token(token)
    try:
        with open(os.path.join(tokens_dir, hashed), 'w') as f:
            f.write(str(user_id))
    except OSError:
        return "", False

    return token, True


def is_ip_blocked(ip: str) -> bool:
    """Check if an IP is currently blocked."""
    with _blocked_ips_lock:
        blocked_until = _blocked_ips.get(ip)
        if blocked_until and time.time() < blocked_until:
            return True
        return False


def block_ip(ip: str) -> None:
    """Block an IP for invalid token attempts."""
    with _blocked_ips_lock:
        _blocked_ips[ip] = time.time() + BAN_FOR_INVALID_TOKEN


def get_ip_from_remote_addr(remote_addr: str) -> str:
    """Extract IP from remote address (host:port)."""
    if ':' in remote_addr:
        host, _, port = remote_addr.rpartition(':')
        if host:
            return host
    return remote_addr
