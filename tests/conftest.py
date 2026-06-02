"""Shared test fixtures."""

import pytest
import tempfile
import shutil


@pytest.fixture
def tmp_dir():
    """Create a temporary directory that is cleaned up after the test."""
    d = tempfile.mkdtemp(prefix="filesmd_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)
