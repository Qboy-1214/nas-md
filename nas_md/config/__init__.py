"""Configuration module - loads from config.json, then environment variables override."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


def _find_project_root() -> Path:
    """Walk up from this file to find the project root (contains config.json or web/)."""
    p = Path(__file__).resolve().parent
    for _ in range(5):
        if (p / "config.json").exists() or (p / "web").is_dir():
            return p
        p = p.parent
    return Path(__file__).resolve().parent.parent.parent  # fallback


PROJECT_ROOT = _find_project_root()


@dataclass
class Config:
    """Server configuration loaded from config.json, overridden by environment variables."""

    working_dir: str = ""
    storage_dir: str = "./storage"
    bot_api_token: str = ""
    config_filename: str = "config.json"
    api_url: str = ""
    app_url: str = ""
    server_cert_dir: str = ""
    tokens_dir: str = "./tokens"
    tokens_salt: str = ""
    server_log_file: str = ""
    storage_quota_kb: int = 1024  # 1MB
    unlimited_quota_ids: str = ""
    mount_dirs: str = ""
    web_root: str = "./web"
    web_port: int = 8080
    web_host: str = "127.0.0.1"
    open_browser: bool = True

    def api_host(self) -> str:
        return _host_of(self.api_url)

    def app_host(self) -> str:
        return _host_of(self.app_url)

    def mount_dir_list(self) -> list[str]:
        if not self.mount_dirs:
            return []
        dirs = []
        # Semicolon is the primary separator (safe on all platforms, avoids
        # conflict with Windows drive letters and "name:path" format).
        # Fall back to comma if semicolon is not present and the string
        # doesn't look like a single "name:path" entry.
        raw = self.mount_dirs.strip()
        if ";" in raw:
            parts = raw.split(";")
        elif "," in raw:
            parts = raw.split(",")
        else:
            parts = [raw]
        for p in parts:
            p = p.strip()
            if not p:
                continue
            p_path = Path(p)
            if not p_path.is_absolute():
                p = str(Path(self.working_dir) / p)
            dirs.append(p)
        return dirs


def _host_of(raw_url: str) -> str:
    if not raw_url:
        return ""
    try:
        parsed = urlparse(raw_url)
        if parsed.hostname:
            return parsed.hostname
        # Fallback for URLs without scheme
        parsed = urlparse("https://" + raw_url)
        return parsed.hostname or ""
    except Exception:
        return ""


# Singleton server config
server_cfg = Config()


def load_bot_config() -> None:
    """Load configuration: config.json first, then environment variables override."""
    cfg = Config()

    # 1. Load from config.json
    config_path = PROJECT_ROOT / "config.json"
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                file_cfg = json.load(f)
            for key, value in file_cfg.items():
                if hasattr(cfg, key):
                    setattr(cfg, key, type(getattr(cfg, key))(value))
        except Exception:
            pass  # ignore malformed config

    # 2. Environment variables override config.json
    env_map = {
        "STORAGE_DIR": "storage_dir",
        "BOT_API_TOKEN": "bot_api_token",
        "CONFIG_FILENAME": "config_filename",
        "API_URL": "api_url",
        "APP_URL": "app_url",
        "CERT_DIR": "server_cert_dir",
        "TOKENS_DIR": "tokens_dir",
        "TOKENS_SALT": "tokens_salt",
        "LOG_FILE": "server_log_file",
        "STORAGE_QUOTA_KB": ("storage_quota_kb", int),
        "UNLIMITED_QUOTA_IDS": "unlimited_quota_ids",
        "MOUNT_DIRS": "mount_dirs",
        "WEB_ROOT": "web_root",
        "WEB_PORT": ("web_port", int),
        "WEB_HOST": "web_host",
    }
    for env_key, cfg_key in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            if isinstance(cfg_key, tuple):
                attr_name, conv = cfg_key
                setattr(cfg, attr_name, conv(val))
            else:
                setattr(cfg, cfg_key, val)

    # 3. Resolve relative paths against project root
    cfg.working_dir = str(PROJECT_ROOT)
    for attr in ("web_root", "storage_dir", "tokens_dir"):
        val = getattr(cfg, attr)
        if val and not Path(val).is_absolute():
            setattr(cfg, attr, str(PROJECT_ROOT / val))

    global server_cfg
    server_cfg = cfg
