"""Configuration module - loads from environment variables and .env files."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class Config:
    """Server configuration loaded from environment variables."""

    working_dir: str = ""
    storage_dir: str = "./storage"
    bot_api_token: str = ""
    config_filename: str = "config.json"
    api_url: str = ""
    app_url: str = ""
    server_cert_dir: str = "/tmp"
    tokens_dir: str = "/tmp"
    tokens_salt: str = ""
    server_log_file: str = "/tmp/server.log"
    storage_quota_kb: int = 1024  # 1MB
    unlimited_quota_ids: str = ""
    mount_dirs: str = ""
    web_root: str = ""
    web_port: int = 8080

    def api_host(self) -> str:
        return _host_of(self.api_url)

    def app_host(self) -> str:
        return _host_of(self.app_url)

    def mount_dir_list(self) -> list[str]:
        if not self.mount_dirs:
            return []
        dirs = []
        for p in self.mount_dirs.split(":"):
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
    """Load configuration from environment variables into server_cfg."""
    cfg = Config()

    cfg.storage_dir = os.environ.get("STORAGE_DIR", cfg.storage_dir)
    cfg.bot_api_token = os.environ.get("BOT_API_TOKEN", cfg.bot_api_token)
    cfg.config_filename = os.environ.get("CONFIG_FILENAME", cfg.config_filename)
    cfg.api_url = os.environ.get("API_URL", cfg.api_url)
    cfg.app_url = os.environ.get("APP_URL", cfg.app_url)
    cfg.server_cert_dir = os.environ.get("CERT_DIR", cfg.server_cert_dir)
    cfg.tokens_dir = os.environ.get("TOKENS_DIR", cfg.tokens_dir)
    cfg.tokens_salt = os.environ.get("TOKENS_SALT", cfg.tokens_salt)
    cfg.server_log_file = os.environ.get("LOG_FILE", cfg.server_log_file)
    cfg.storage_quota_kb = int(os.environ.get("STORAGE_QUOTA_KB", cfg.storage_quota_kb))
    cfg.unlimited_quota_ids = os.environ.get("UNLIMITED_QUOTA_IDS", cfg.unlimited_quota_ids)
    cfg.mount_dirs = os.environ.get("MOUNT_DIRS", cfg.mount_dirs)
    cfg.web_root = os.environ.get("WEB_ROOT", cfg.web_root)
    cfg.web_port = int(os.environ.get("WEB_PORT", cfg.web_port))

    cfg.working_dir = os.getcwd()
    # Only resolve storage_dir if it's explicitly set via env var
    storage_dir_env = os.environ.get("STORAGE_DIR")
    if storage_dir_env and not Path(storage_dir_env).is_absolute():
        cfg.storage_dir = str(Path(cfg.working_dir) / storage_dir_env)
    elif not Path(cfg.storage_dir).is_absolute() and storage_dir_env is None:
        # Keep default relative path as-is
        pass

    global server_cfg
    server_cfg = cfg
