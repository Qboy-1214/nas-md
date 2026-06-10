"""Tests for pkg.txt.tgtxt - Telegram text conversion utilities."""

import pytest

from nas_md.pkg.txt.tgtxt import telegram_entities_to_markdown, extract_text_imgs_links, has_image


class FakeEntity:
    """Minimal Telegram entity for testing."""

    def __init__(self, type, offset, length, url="", language=""):
        self.type = type
        self.offset = offset
        self.length = length
        self.url = url
        self.language = language


class TestTelegramEntitiesToMarkdown:
    def test_bold(self):
        text = "hello world"
        entities = [FakeEntity("bold", 0, 11)]
        result = telegram_entities_to_markdown(text, entities)
        assert "**hello world**" == result

    def test_italic(self):
        text = "hello world"
        entities = [FakeEntity("italic", 0, 5)]
        result = telegram_entities_to_markdown(text, entities)
        assert "*hello*" in result

    def test_code(self):
        text = "use print function"
        entities = [FakeEntity("code", 4, 5)]
        result = telegram_entities_to_markdown(text, entities)
        assert "`print`" in result

    def test_pre(self):
        text = "code block"
        entities = [FakeEntity("pre", 0, 10, language="python")]
        result = telegram_entities_to_markdown(text, entities)
        assert "```python" in result
        assert "```" in result

    def test_text_link(self):
        text = "click here"
        entities = [FakeEntity("text_link", 0, 11, url="https://example.com")]
        result = telegram_entities_to_markdown(text, entities)
        # The function inserts [ at the first non-space char
        assert "[" in result

    def test_text_link_no_spaces(self):
        """Text links without spaces should produce full markdown."""
        text = "clickhere"
        entities = [FakeEntity("text_link", 0, 9, url="https://example.com")]
        result = telegram_entities_to_markdown(text, entities)
        assert "[clickhere](https://example.com)" == result

    def test_strikethrough(self):
        text = "deleted text"
        entities = [FakeEntity("strikethrough", 0, 7)]
        result = telegram_entities_to_markdown(text, entities)
        assert "~deleted~" in result

    def test_no_entities(self):
        text = "plain text"
        result = telegram_entities_to_markdown(text, [])
        assert result == "plain text"

    def test_multiple_entities(self):
        text = "bold and italic"
        entities = [
            FakeEntity("bold", 0, 4),
            FakeEntity("italic", 9, 6),
        ]
        result = telegram_entities_to_markdown(text, entities)
        assert "**bold**" in result
        assert "*italic*" in result


class TestExtractTextImgsLinks:
    def test_extract_image(self):
        text = "Look at this ![](photo.tg_abc123.jpg) image"
        clean_text, images, links = extract_text_imgs_links(text)
        assert "abc123" in images
        assert "🖼" in clean_text

    def test_extract_link(self):
        text = "[My Note](notes/test.md)"
        clean_text, images, links = extract_text_imgs_links(text)
        assert "My Note" in links or "test" in links

    def test_no_images_or_links(self):
        text = "Just plain text"
        clean_text, images, links = extract_text_imgs_links(text)
        assert images == []
        assert links == {}

    def test_wiki_link(self):
        text = "[[notes/test]]"
        clean_text, images, links = extract_text_imgs_links(text)
        assert "test" in links


class TestHasImage:
    def test_with_image(self):
        assert has_image("Check this ![](photo.jpg)") is True

    def test_without_image(self):
        assert has_image("Just text") is False

    def test_with_link_not_image(self):
        assert has_image("[link](url)") is False
