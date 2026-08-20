"""Performance optimization tests for nas-md webserver.

Covers: ETag / 304, Gzip compression, Cache-Control headers, SSE bypass.
"""

import gzip
import io
import os
import shutil
import socket
import tempfile
import threading
import time

import pytest

from nas_md.webserver import (
    MountManager,
    MountHTTPHandler,
    _compute_etag,
    _compress,
    _create_server,
    serve,
)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url: str, headers: dict | None = None) -> tuple[int, dict]:
    """Send GET request, return (status, headers_dict)."""
    import urllib.request

    try:
        req = urllib.request.Request(url)
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, {}


@pytest.fixture
def perf_web_root():
    d = tempfile.mkdtemp(prefix="nasmd_perf_")
    # index.html
    with open(os.path.join(d, "index.html"), "w") as f:
        f.write("<html><body>app</body></html>")
    # A large-ish JS file (>512 bytes)
    js_dir = os.path.join(d, "lib")
    os.makedirs(js_dir, exist_ok=True)
    with open(os.path.join(js_dir, "big.js"), "wb") as f:
        f.write(b"x" * 2000)
    # A small JS file (<512 bytes)
    with open(os.path.join(js_dir, "small.js"), "wb") as f:
        f.write(b"tiny")
    # Empty file (edge case for ETag)
    with open(os.path.join(d, "empty.txt"), "wb") as f:
        pass
    # Second empty file (different name, same content → should get same ETag via size)
    with open(os.path.join(d, "empty2.txt"), "wb") as f:
        pass
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def perf_server(perf_web_root):
    port = _find_free_port()
    from nas_md.webserver import MountEntry

    # Create multiple mounts with long names/paths so /api/mounts JSON response exceeds 512 bytes
    mounts = [
        MountEntry(
            f"mount-{i:02d}",
            f"Custom-Mounted-Directory-Name-With-Long-Description-String-Number-{i:02d}",
            os.path.join(perf_web_root, f"dir_with_a_very_long_path_name_{i:02d}"),
            public=True,
        )
        for i in range(12)
    ]
    mgr = MountManager([])
    mgr.mounts = mounts
    MountHTTPHandler.mount_manager = mgr
    MountHTTPHandler.web_root = perf_web_root
    MountHTTPHandler.search_dirs = []
    server = _create_server("127.0.0.1", port, MountHTTPHandler, cert_dir="")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ---- _compute_etag unit tests ----


class TestComputeETag:
    def test_returns_weak_etag_format(self, perf_web_root):
        path = os.path.join(perf_web_root, "lib", "big.js")
        etag = _compute_etag(path)
        assert etag is not None
        assert etag.startswith('W/"')
        assert etag.endswith('"')
        # Format: W/"<12-char-hex>-<size>"
        inner = etag[3:-1]
        parts = inner.rsplit("-", 1)
        assert len(parts) == 2
        assert len(parts[0]) == 12  # sha1 prefix
        assert parts[1].isdigit()  # size

    def test_different_files_different_etag(self, perf_web_root):
        p1 = os.path.join(perf_web_root, "lib", "big.js")
        p2 = os.path.join(perf_web_root, "empty.txt")
        assert _compute_etag(p1) != _compute_etag(p2)

    def test_empty_files_differ_by_size(self, perf_web_root):
        """Two zero-byte files have same hash but both size 0 → same ETag."""
        p1 = os.path.join(perf_web_root, "empty.txt")
        p2 = os.path.join(perf_web_root, "empty2.txt")
        assert _compute_etag(p1) == _compute_etag(p2)

    def test_nonexistent_file_returns_none(self):
        assert _compute_etag("/nonexistent/path/file.txt") is None


# ---- _compress unit tests ----


class TestCompress:
    def test_small_data_not_compressed(self):
        data, compressed = _compress(b"tiny", "text/plain")
        assert not compressed
        assert data == b"tiny"

    def test_large_data_is_compressed(self):
        data = b"a" * 1000
        result, compressed = _compress(data, "text/plain")
        assert compressed
        assert result != data
        # Verify round-trip
        decompressed = gzip.decompress(result)
        assert decompressed == data

    def test_image_types_skipped(self):
        data, compressed = _compress(b"x" * 1000, "image/png")
        assert not compressed

    def test_font_types_skipped(self):
        data, compressed = _compress(b"x" * 1000, "font/woff2")
        assert not compressed

    def test_event_stream_skipped(self):
        data, compressed = _compress(b"x" * 1000, "text/event-stream")
        assert not compressed

    def test_json_compressed(self):
        data = b'{"key": "' + b"x" * 600 + b'"}'
        result, compressed = _compress(data, "application/json")
        assert compressed
        assert gzip.decompress(result) == data

    def test_skipped_when_no_accept_gzip(self):
        """When handler explicitly signals no Accept-Encoding, compression must be skipped."""

        class FakeHandler:
            headers = {"Accept-Encoding": ""}

        data = b"x" * 1000
        result, compressed = _compress(data, "text/plain", handler=FakeHandler())
        assert not compressed
        assert result == data


# ---- Integration tests ----


class TestStaticCacheHeaders:
    def test_lib_file_has_long_cache(self, perf_server):
        status, headers = _get(f"{perf_server}/lib/big.js")
        assert status == 200
        cc = headers.get("cache-control", "")
        assert "max-age=2592000" in cc
        assert "etag" in headers

    def test_non_lib_file_has_no_cache(self, perf_server):
        status, headers = _get(f"{perf_server}/index.html")
        assert status == 200
        cc = headers.get("cache-control", "")
        assert "no-cache" in cc
        assert "etag" in headers

    def test_etag_304_on_match(self, perf_server):
        # First request: get ETag
        status1, headers1 = _get(f"{perf_server}/index.html")
        assert status1 == 200
        etag = headers1.get("etag", "")
        assert etag

        # Second request with If-None-Match
        status2, _ = _get(f"{perf_server}/index.html", headers={"If-None-Match": etag})
        assert status2 == 304


class TestGzipInResponses:
    def test_large_js_compressed_with_accept_gzip(self, perf_server):
        status, headers = _get(f"{perf_server}/lib/big.js", headers={"Accept-Encoding": "gzip"})
        assert status == 200
        assert headers.get("content-encoding") == "gzip"

    def test_large_js_not_compressed_without_accept_gzip(self, perf_server):
        status, headers = _get(f"{perf_server}/lib/big.js")
        assert status == 200
        assert "content-encoding" not in headers

    def test_small_js_not_compressed(self, perf_server):
        status, headers = _get(f"{perf_server}/lib/small.js", headers={"Accept-Encoding": "gzip"})
        assert status == 200
        assert "content-encoding" not in headers


class TestSendJsonGzip:
    def test_json_response_compressed(self, perf_server):
        status, headers = _get(f"{perf_server}/api/mounts", headers={"Accept-Encoding": "gzip"})
        assert status == 200
        # _send_json now calls _compress; response should be gzip-encoded
        assert headers.get("content-encoding") == "gzip"

    def test_json_response_no_cache(self, perf_server):
        status, headers = _get(f"{perf_server}/api/mounts")
        assert status == 200
        cc = headers.get("cache-control", "")
        assert "no-store" in cc


class TestSSENotCompressed:
    """SSE should not be gzip-compressed by _compress, and _send_json is not used for SSE."""

    def test_sse_content_type_excluded(self):
        data, compressed = _compress(b"x" * 1000, "text/event-stream")
        assert not compressed
        assert data == b"x" * 1000
