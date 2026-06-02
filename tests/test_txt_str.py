"""Tests for pkg/txt/str module."""

import pytest

from nas_md.pkg.txt.str import (
    i64, ucfirst, lcfirst, substr, emoji, norm_new_lines,
    is_multiline, split_text_into_chunks, first_word, escape_html,
    strip_html_tags, similar, similar_str, similar_char,
)


class TestI64:
    def test_positive(self):
        assert i64(42) == "42"

    def test_zero(self):
        assert i64(0) == "0"

    def test_negative(self):
        assert i64(-1) == "-1"


class TestUcfirst:
    def test_lowercase(self):
        assert ucfirst("hello") == "Hello"

    def test_already_upper(self):
        assert ucfirst("Hello") == "Hello"

    def test_empty(self):
        assert ucfirst("") == ""

    def test_single_char(self):
        assert ucfirst("a") == "A"


class TestLcfirst:
    def test_uppercase(self):
        assert lcfirst("Hello") == "hello"

    def test_empty(self):
        assert lcfirst("") == ""


class TestSubstr:
    def test_basic(self):
        assert substr("Hello World", 0, 5) == "Hello"

    def test_middle(self):
        assert substr("Hello World", 6, 5) == "World"

    def test_empty(self):
        assert substr("", 0, 5) == ""

    def test_start_beyond_length(self):
        assert substr("Hi", 5, 3) == ""

    def test_negative_start(self):
        assert substr("Hello", -1, 3) == ""

    def test_negative_length(self):
        assert substr("Hello", 0, -1) == ""

    def test_unicode(self):
        assert substr("Привет", 0, 2) == "Пр"


class TestEmoji:
    def test_basic(self):
        assert emoji("✅", "Done") == "✅ Done"

    def test_empty_emoji(self):
        assert emoji("", "Done") == "Done"

    def test_strip_prefix(self):
        assert emoji("➡️", "WRK Task") == "➡️ Task"
        assert emoji("➡️", "UA Task") == "➡️ Task"
        assert emoji("➡️", "US Task") == "➡️ Task"
        assert emoji("➡️", "CY Task") == "➡️ Task"
        assert emoji("➡️", "HOB Task") == "➡️ Task"
        assert emoji("➡️", "SRB Task") == "➡️ Task"
        assert emoji("➡️", "PL Task") == "➡️ Task"


class TestNormNewLines:
    def test_crlf(self):
        assert norm_new_lines("a\r\nb") == "a\nb"

    def test_cr(self):
        assert norm_new_lines("a\rb") == "a\nb"

    def test_lf_unchanged(self):
        assert norm_new_lines("a\nb") == "a\nb"


class TestIsMultiline:
    def test_single_line(self):
        assert not is_multiline("one line")

    def test_multiline(self):
        assert is_multiline("line1\nline2")

    def test_empty(self):
        assert not is_multiline("")


class TestSplitTextIntoChunks:
    def test_short_text(self):
        assert split_text_into_chunks("short", 100) == ["short"]

    def test_long_text(self):
        text = "a" * 200
        chunks = split_text_into_chunks(text, 100)
        assert all(len(c) <= 100 for c in chunks)

    def test_empty(self):
        assert split_text_into_chunks("", 100) == [""]

    def test_max_len_zero(self):
        assert split_text_into_chunks("text", 0) == ["text"]

    def test_newline_split(self):
        text = "a" * 50 + "\n" + "b" * 50
        chunks = split_text_into_chunks(text, 80)
        assert len(chunks) >= 1


class TestFirstWord:
    def test_simple(self):
        assert first_word("hello world") == "hello"

    def test_single_word(self):
        assert first_word("hello") == "hello"

    def test_empty(self):
        assert first_word("") == ""

    def test_leading_space(self):
        assert first_word("  hello") == "hello"


class TestEscapeHtml:
    def test_amp(self):
        assert escape_html("a & b") == "a &amp; b"

    def test_lt(self):
        assert escape_html("a < b") == "a &lt; b"

    def test_gt(self):
        assert escape_html("a > b") == "a &gt; b"

    def test_all(self):
        assert escape_html("<div>&</div>") == "&lt;div&gt;&amp;&lt;/div&gt;"


class TestStripHtmlTags:
    def test_basic(self):
        assert strip_html_tags("<b>bold</b>") == "bold"

    def test_nested(self):
        assert strip_html_tags("<div><p>text</p></div>") == "text"

    def test_no_tags(self):
        assert strip_html_tags("plain text") == "plain text"


class TestSimilar:
    def test_identical(self):
        assert similar("hello", "hello") == 100

    def test_completely_different(self):
        score = similar("abc", "xyz")
        assert score < 50

    def test_empty(self):
        assert similar("", "hello") == 0
        assert similar("hello", "") == 0

    def test_partial(self):
        score = similar("hello", "helo")
        assert 50 < score <= 100
