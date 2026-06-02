"""Worker module - scheduled task execution."""

from __future__ import annotations

import time
from typing import Optional

from nas_md.config import server_cfg
from nas_md.fs import FS, DIR_USER_ROOT, new_user_fs
from nas_md.userconfig import UserConfig

_now = time.time


class Worker:
    """Handles scheduled tasks like moving scheduled items and cleaning up completed tasks."""

    def __init__(self, tg, get_user_fs) -> None:
        self.tg = tg
        self.get_user_fs = get_user_fs

    def run(self) -> None:
        """Run all scheduled tasks."""
        self._run_schedules()
        self._cleanup_done()

    def _run_schedules(self) -> None:
        """Process scheduled tasks for all users."""
        # In the real implementation, this would iterate over all user directories
        pass

    def _cleanup_done(self) -> None:
        """Clean up old completed tasks."""
        pass


def new_worker(tg, get_user_fs) -> Worker:
    return Worker(tg, get_user_fs)
