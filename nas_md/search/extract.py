"""Content extractors for structured objects from Markdown files."""

from __future__ import annotations

import re
from typing import Any

import yaml


def extract_frontmatter(content: str) -> dict[str, Any] | None:
    """Extract YAML frontmatter from Markdown content.

    Returns parsed dict if frontmatter exists, None otherwise.
    Silently returns None on parse errors.
    """
    if not content.startswith("---"):
        return None
    end = content.find("---", 3)
    if end == -1:
        return None
    yaml_str = content[3:end].strip()
    if not yaml_str:
        return None
    try:
        result = yaml.safe_load(yaml_str)
        if isinstance(result, dict):
            return result
        return None
    except yaml.YAMLError:
        return None


def _strip_frontmatter(content: str) -> str:
    """Return content with frontmatter block removed."""
    if not content.startswith("---"):
        return content
    end = content.find("---", 3)
    if end == -1:
        return content
    return content[end + 3 :].lstrip("\n")


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def extract_headings(content: str) -> list[dict]:
    """Extract headings from Markdown content.

    Returns list of {"level": 1-6, "text": str, "line_number": int}.
    Skips headings inside frontmatter block.
    """
    body = _strip_frontmatter(content)
    fm_lines = 0
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            fm_lines = content[: end + 3].count("\n")

    results = []
    for match in _HEADING_RE.finditer(body):
        level = len(match.group(1))
        text = match.group(2).strip()
        line_number = body[: match.start()].count("\n") + fm_lines + 1
        results.append({"level": level, "text": text, "line_number": line_number})
    return results


# Match #tag: word chars (including CJK unicode), hyphens, underscores
# Must be at start of line or after whitespace/punctuation
_TAG_RE = re.compile(r"(?:^|[\s(\[{,;])(#([\w\u4e00-\u9fff][\w\u4e00-\u9fff\-_]*))", re.UNICODE)

# Common false positives to skip
_TAG_SKIP = frozenset({"#", "##", "###", "####", "#####", "######"})


def extract_tags(content: str, frontmatter: dict[str, Any] | None = None) -> list[dict]:
    """Extract tags from Markdown content and frontmatter.

    Returns list of {"name": str, "source": "body"|"frontmatter"}.
    Deduplicates: if same tag appears in both, keeps frontmatter source.
    """
    body = _strip_frontmatter(content)
    # Remove code blocks to avoid false positives
    body_no_code = re.sub(r"```[\s\S]*?```", "", body)
    body_no_code = re.sub(r"`[^`]+`", "", body_no_code)
    # Remove headings to avoid matching ## etc
    body_no_code = re.sub(r"^#{1,6}\s+.*$", "", body_no_code, flags=re.MULTILINE)

    tags: dict[str, str] = {}  # name -> source

    # Extract from body
    for match in _TAG_RE.finditer(body_no_code):
        full = match.group(1)
        name = match.group(2)
        if full in _TAG_SKIP:
            continue
        if name not in tags:
            tags[name] = "body"

    # Extract from frontmatter (overrides body source)
    if frontmatter:
        fm_tags = frontmatter.get("tags", [])
        if isinstance(fm_tags, str):
            fm_tags = [t.strip() for t in fm_tags.split(",")]
        if isinstance(fm_tags, list):
            for t in fm_tags:
                t = str(t).strip().lstrip("#")
                if t:
                    tags[t] = "frontmatter"

    return [{"name": name, "source": source} for name, source in sorted(tags.items())]


_TASK_RE = re.compile(r"^(\s*)[-*]\s+\[([ xX])\]\s+(.+)$", re.MULTILINE)


def extract_tasks(content: str) -> list[dict]:
    """Extract task items from Markdown content.

    Returns list of {"content": str, "done": 0|1, "line_number": int}.
    """
    body = _strip_frontmatter(content)
    fm_lines = 0
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            fm_lines = content[: end + 3].count("\n")

    results = []
    for match in _TASK_RE.finditer(body):
        indent = match.group(1)
        checkbox = match.group(2).lower()
        text = match.group(3).strip()
        done = 1 if checkbox == "x" else 0
        # Count newlines before the match start, adjusting for indent whitespace
        line_number = body[: match.start() + len(indent)].count("\n") + fm_lines + 1
        results.append({"content": text, "done": done, "line_number": line_number})
    return results
