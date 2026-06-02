"""Telegram text conversion utilities."""

from __future__ import annotations

import re

from nas_md.pkg.txt.str import norm_new_lines

IMG_PATTERN = r'!\[.*?\]\(.*?\)'


def telegram_entities_to_markdown(text: str, message_entities: list) -> str:
    """Convert plain text with Telegram entities (UTF-16 offsets) to CommonMark Markdown."""
    input_runes = list(norm_new_lines(text))
    insertions: dict[int, str] = {}
    no_escape: set[int] = set()

    def stop_escape(e):
        for i in range(e.offset, e.offset + e.length):
            no_escape.add(i)

    for e in message_entities:
        before = ""
        after = ""
        eat_newlines = False

        if e.type == "bold":
            before, after = "**", "**"
        elif e.type == "italic":
            before, after = "*", "*"
        elif e.type == "underline":
            before, after = "__", "__"
        elif e.type == "strikethrough":
            before, after = "~", "~"
        elif e.type == "code":
            before, after = "`", "`"
            stop_escape(e)
        elif e.type == "pre":
            lang = getattr(e, 'language', '') or ""
            before, after = f"```{lang}\n", "\n```"
            eat_newlines = True
            stop_escape(e)
        elif e.type == "text_link":
            before, after = "[", f"]({e.url})"
        elif e.type == "url":
            stop_escape(e)
            continue
        else:
            continue

        is_open = False
        spaces_to_eat = 0
        entity_runes = input_runes[e.offset:e.offset + e.length]
        for offset, c in enumerate(entity_runes):
            if c == "\n" and not eat_newlines and is_open:
                pos = (e.offset + offset) - spaces_to_eat
                insertions[pos] = insertions.get(pos, "") + after
                is_open = False
                spaces_to_eat = 0
                continue
            if c.isspace():
                spaces_to_eat += 1
                continue
            if not is_open:
                pos = e.offset + offset
                insertions[pos] = insertions.get(pos, "") + before
                is_open = True
            spaces_to_eat = 0
        if is_open:
            pos = (e.offset + e.length) - spaces_to_eat
            insertions[pos] = insertions.get(pos, "") + after

    output: list[str] = []
    utf16_pos = 0
    for c in input_runes:
        output.append(insertions.get(utf16_pos, ""))
        output.append(c)
        # UTF-16 encoding: BMP chars = 1 code unit, supplementary = 2
        cp = ord(c)
        if cp > 0xFFFF:
            utf16_pos += 2
        else:
            utf16_pos += 1
    output.append(insertions.get(utf16_pos, ""))

    return "".join(output)


def extract_text_imgs_links(text: str) -> tuple[str, list[str], dict[str, str]]:
    """Extract images and links from text, returning clean text, image IDs, and links."""
    links: dict[str, str] = {}

    img_regexp = re.compile(r'!\[.*?\]\(.*?tg_([^.]+)\..*?\)')
    link_regexp = re.compile(r'\[.*?\]\((.+?)\)')
    wiki_link_regexp = re.compile(r'\[\[(.+?)\]\]')

    # Eat links from lines containing only links
    text = norm_new_lines(text)
    lines = text.split("\n")
    processed_lines = []
    for line in lines:
        trimmed = line.strip()
        if link_regexp.match(trimmed) and link_regexp.match(trimmed).group(0) == trimmed:
            m = link_regexp.search(line)
            if m:
                content = m.group(1)
                parts = content.split("|", 1)
                link_path = parts[0]
                link_label = link_path.rsplit("/", 1)[-1]
                if link_label.endswith(".md"):
                    link_label = link_label[:-3]
                links[link_label] = link_path
        elif wiki_link_regexp.match(trimmed) and wiki_link_regexp.match(trimmed).group(0) == trimmed:
            m = wiki_link_regexp.search(line)
            if m:
                content = m.group(1)
                parts = content.split("|", 1)
                link_path = parts[0] + ".md"
                link_label = link_path.rsplit("/", 1)[-1]
                if link_label.endswith(".md"):
                    link_label = link_label[:-3]
                links[link_label] = link_path
        else:
            processed_lines.append(line)
    text = "\n".join(processed_lines)

    # Process images
    images: list[str] = []
    def img_replacer(m):
        images.append(m.group(1))
        return "🖼"
    text = img_regexp.sub(img_replacer, text)

    # Process inline links
    def link_replacer(m):
        content = m.group(1)
        parts = content.split("|", 1)
        link_path = parts[0]
        link_label = link_path.rsplit("/", 1)[-1]
        if link_label.endswith(".md"):
            link_label = link_label[:-3]
        links[link_label] = link_path
        return f"`{link_label}`"
    text = link_regexp.sub(link_replacer, text)
    text = wiki_link_regexp.sub(link_replacer, text)

    return text.strip(), images, links


def has_image(msg: str) -> bool:
    return bool(re.search(IMG_PATTERN, msg))
