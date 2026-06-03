"""Shared test fixtures."""

import sys
import os

import pytest


def pytest_sessionstart(session):
    msg = f"sys.path={sys.path[:5]}"
    print(f"\nDEBUG: {msg}", flush=True)


@pytest.fixture
def tmp_dir():
    """Create a temporary directory that is cleaned up after the test."""
    import tempfile
    import shutil

    d = tempfile.mkdtemp(prefix="filesmd_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)
