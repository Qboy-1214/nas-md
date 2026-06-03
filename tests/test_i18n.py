"""Tests for i18n module."""

import json
import os
import tempfile


from nas_md.i18n import add_emoji, emoji, load_emoji_file


class TestLoadEmojiFile:
    def test_load_valid_file(self):
        data = {"🏃": ["running", "run"], "📚": ["reading", "book"]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            load_emoji_file(f.name)
            assert emoji("running") == "🏃"
            assert emoji("book") == "📚"
        os.unlink(f.name)

    def test_load_missing_file(self):
        load_emoji_file("/nonexistent/emojis.json")
        assert emoji("anything") == ""


class TestEmoji:
    def test_direct_match(self):
        data = {"🏃": ["running"]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            load_emoji_file(f.name)
            assert emoji("running") == "🏃"
        os.unlink(f.name)

    def test_plural_match(self):
        data = {"📚": ["book"]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            load_emoji_file(f.name)
            assert emoji("books") == "📚"
        os.unlink(f.name)

    def test_singular_match(self):
        data = {"📚": ["books"]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            load_emoji_file(f.name)
            assert emoji("book") == "📚"
        os.unlink(f.name)

    def test_word_match(self):
        data = {"🏃": ["running"]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            load_emoji_file(f.name)
            assert emoji("I love running") == "🏃"
        os.unlink(f.name)

    def test_no_match(self):
        data = {"🏃": ["running"]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            load_emoji_file(f.name)
            assert emoji("swimming") == ""
        os.unlink(f.name)


class TestAddEmoji:
    def test_adds_emoji(self):
        data = {"🏃": ["running"]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            load_emoji_file(f.name)
            assert add_emoji("running") == "🏃 running"
        os.unlink(f.name)

    def test_no_emoji(self):
        data = {"🏃": ["running"]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            load_emoji_file(f.name)
            assert add_emoji("swimming") == "swimming"
        os.unlink(f.name)
