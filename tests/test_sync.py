"""Tests for sync module - LCS merge."""

from nas_md.sync import merge, _unique_graphemes, _group_consecutive_headers


class TestMerge:
    def test_both_empty(self):
        assert merge("", "") == ""

    def test_first_empty(self):
        assert merge("", "content") == "content"

    def test_second_empty(self):
        assert merge("content", "") == "content"

    def test_identical(self):
        assert merge("a\nb\nc", "a\nb\nc") == "a\nb\nc"

    def test_completely_different(self):
        result = merge("a\nb", "c\nd")
        assert "a" in result
        assert "b" in result
        assert "c" in result
        assert "d" in result

    def test_partial_overlap(self):
        result = merge("a\nb\nc", "b\nc\nd")
        assert "a" in result
        assert "b" in result
        assert "c" in result
        assert "d" in result

    def test_single_line(self):
        assert merge("hello", "hello") == "hello"

    def test_preserves_order(self):
        result = merge("a\nb\nc", "a\nb\nc")
        lines = result.split("\n")
        assert lines.index("a") < lines.index("b") < lines.index("c")

    def test_three_way_merge(self):
        """Test merging with common base."""
        branch1 = "line1\nline2\nline3\nadded1"
        branch2 = "line1\nline2\nline3\nadded2"
        result = merge(branch1, branch2)
        assert "line1" in result
        assert "added1" in result
        assert "added2" in result


class TestMergeEmojisInHeaders:
    def test_merge_emoji_headers(self):
        """Journal headers with different emojis should be merged."""
        h1 = "## 23 May, Friday"
        h2 = "## 23 May, Friday 🤸‍"
        h3 = "## 23 May, Friday 🤸‍🍽"
        s1 = f"{h1}\nContent A"
        s2 = f"{h2}\nContent B"
        s3 = f"{h3}\nContent C"
        result12 = merge(s1, s2)
        result123 = merge(result12, s3)
        # The headers should be merged
        assert "Content A" in result123
        assert "Content B" in result123
        assert "Content C" in result123


class TestUniqueGraphemes:
    def test_no_duplicates(self):
        assert _unique_graphemes("abc") == "abc"

    def test_with_duplicates(self):
        assert _unique_graphemes("aabbcc") == "abc"

    def test_empty(self):
        assert _unique_graphemes("") == ""

    def test_emojis(self):
        result = _unique_graphemes("🤸‍🤸‍🍽")
        assert "🤸‍" in result
        assert "🍽" in result


class TestGroupConsecutiveHeaders:
    def test_no_headers(self):
        result = _group_consecutive_headers(["text", "more text"])
        assert len(result) == 2
        assert result[0] == ["text"]

    def test_consecutive_headers(self):
        result = _group_consecutive_headers(
            [
                "## 23 May, Friday",
                "## 24 May, Saturday",
                "Some text",
            ]
        )
        assert len(result) == 2
        assert len(result[0]) == 2  # Two headers grouped
        assert result[1] == ["Some text"]

    def test_mixed(self):
        result = _group_consecutive_headers(
            [
                "## 1 January, Monday",
                "text",
                "## 2 January, Tuesday",
                "## 3 January, Wednesday",
                "more text",
            ]
        )
        assert len(result) == 4
        assert result[0] == ["## 1 January, Monday"]
        assert result[1] == ["text"]
        assert result[2] == ["## 2 January, Tuesday", "## 3 January, Wednesday"]
        assert result[3] == ["more text"]
