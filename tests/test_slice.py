"""Tests for pkg/slice module."""

from nas_md.pkg.slice import chunk


class TestChunk:
    def test_empty(self):
        assert chunk([], 3) == []

    def test_single_chunk(self):
        assert chunk([1, 2, 3], 5) == [[1, 2, 3]]

    def test_exact_chunks(self):
        assert chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]

    def test_remainder(self):
        assert chunk([1, 2, 3], 2) == [[1, 2], [3]]

    def test_single_element(self):
        assert chunk([1], 1) == [[1]]

    def test_chunk_size_one(self):
        assert chunk([1, 2, 3], 1) == [[1], [2], [3]]

    def test_strings(self):
        result = chunk(["a", "b", "c", "d"], 3)
        assert result == [["a", "b", "c"], ["d"]]
