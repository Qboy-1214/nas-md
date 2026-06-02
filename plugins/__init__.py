"""Plugin system - world clock and other plugins."""

from __future__ import annotations

import time
from typing import Optional

TIME_FORMAT = "%d.%m.%Y %H:%M:%S"
DATE_FORMAT = "%d.%m.%Y"

LOCATION_NAMES = ["UTC", "MSK", "CY", "ME"]
LOCATIONS = {
    "UTC": "UTC",
    "CY": "Asia/Nicosia",
    "ME": "Europe/Podgorica",
    "BG": "Europe/Belgrade",
    "MSK": "Europe/Moscow",
}
LOCATION_ICONS = {
    "UTC": "🕰",
    "CY": "🏝",
    "ME": "⛰",
    "BG": "☕️",
    "MSK": "🔺",
}


class WorldClockPlugin:
    """Plugin that converts dates/timestamps to multiple timezones."""

    def can_handle(self, msg_text: str) -> bool:
        return self.parse_date(msg_text) is not None or \
               self.parse_time(msg_text) is not None or \
               self.parse_timestamp(msg_text) is not None

    def handle(self, msg_text: str) -> tuple[Optional[str], None]:
        t = self.parse_date(msg_text)
        if t is not None:
            return self._build_message(t, self._fmt_timestamp), None

        t = self.parse_time(msg_text)
        if t is not None:
            return self._build_message(t, self._fmt_timestamp), None

        t = self.parse_timestamp(msg_text)
        if t is not None:
            return self._build_message(t, self._fmt_time), None

        return "", None

    def parse_timestamp(self, message: str) -> Optional[float]:
        try:
            ts = int(message)
        except (ValueError, TypeError):
            return None
        if ts <= 999999:
            return None
        if ts > 9999999999999:
            return ts / 1000000  # microseconds
        elif ts > 9999999999:
            return ts / 1000  # milliseconds
        return float(ts)  # seconds

    def parse_time(self, message: str) -> Optional[float]:
        try:
            t = time.strptime(message.strip(), TIME_FORMAT)
            return time.mktime(t)
        except (ValueError, TypeError):
            return None

    def parse_date(self, message: str) -> Optional[float]:
        try:
            t = time.strptime(message.strip(), DATE_FORMAT)
            return time.mktime(t)
        except (ValueError, TypeError):
            return None

    def _build_message(self, t: float, formatter) -> str:
        parts = []
        for loc_name in LOCATION_NAMES:
            try:
                offset = time.timezone if time.localtime(t).tm_isdst == 0 else time.altzone
                local_t = t - offset
                formatted = formatter(local_t)
                parts.append(f"{LOCATION_ICONS[loc_name]} {formatted} {loc_name}")
            except Exception:
                pass
        return "\n".join(parts)

    def _fmt_time(self, t: float) -> str:
        return time.strftime(TIME_FORMAT, time.localtime(t))

    def _fmt_timestamp(self, t: float) -> str:
        return str(int(t))
