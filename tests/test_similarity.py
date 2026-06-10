"""Tests for pkg.txt.similarity - string similarity utilities."""

import pytest

from nas_md.pkg.txt.similarity import similar


class TestSimilar:
    def test_identical_strings(self):
        """Identical strings should have 100% similarity."""
        assert similar("hello", "hello") == 100

    def test_completely_different(self):
        """Completely different strings should have low similarity."""
        score = similar("abc", "xyz")
        assert score < 30

    def test_empty_strings(self):
        """Empty strings should return 0."""
        assert similar("", "") == 0
        assert similar("hello", "") == 0
        assert similar("", "hello") == 0

    def test_partial_match(self):
        """Partially matching strings should have moderate similarity."""
        score = similar("hello world", "hello there")
        assert 30 < score < 80

    def test_case_sensitive(self):
        """Similarity should be case-sensitive."""
        score = similar("Hello", "hello")
        assert score < 100

    def test_single_char(self):
        """Single character strings."""
        assert similar("a", "a") == 100
        assert similar("a", "b") == 0

    def test_substring(self):
        """Substring should have high similarity."""
        score = similar("hello", "hello world")
        assert score > 50

    def test_chinese_characters(self):
        """Chinese characters should work."""
        score = similar("你好世界", "你好中国")
        assert 20 < score < 80
