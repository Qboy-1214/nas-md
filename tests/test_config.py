"""Tests for config module."""

import os
import sys
from pathlib import Path
from unittest.mock import patch


from nas_md.config import Config


class TestConfig:
    def test_api_host(self):
        cfg = Config(api_url="https://api.telegram.org/bot123:ABC")
        assert cfg.api_host() == "api.telegram.org"

    def test_api_host_empty(self):
        cfg = Config()
        assert cfg.api_host() == ""

    def test_app_host(self):
        cfg = Config(app_url="https://app.example.com")
        assert cfg.app_host() == "app.example.com"

    def test_app_host_empty(self):
        cfg = Config()
        assert cfg.app_host() == ""

    def test_mount_dir_list_empty(self):
        cfg = Config()
        assert cfg.mount_dir_list() == []

    def test_mount_dir_list_single(self):
        cfg = Config(mount_dirs="/mnt/data")
        dirs = cfg.mount_dir_list()
        assert len(dirs) == 1
        assert dirs[0].replace("\\", "/").endswith("/mnt/data")

    def test_mount_dir_list_multiple(self):
        cfg = Config(mount_dirs="/mnt/a;/mnt/b")
        dirs = cfg.mount_dir_list()
        assert len(dirs) == 2

    def test_mount_dir_list_relative(self):
        cfg = Config(mount_dirs="data;backup", working_dir="/home/user")
        dirs = cfg.mount_dir_list()
        assert Path(dirs[0]).name == "data"
        assert Path(dirs[1]).name == "backup"
        # On Linux, these are absolute; on Windows, /home/user becomes \home\user
        if sys.platform != "win32":
            assert Path(dirs[0]).is_absolute()
            assert Path(dirs[1]).is_absolute()


class TestLoadBotConfig:
    @patch.dict(
        os.environ,
        {
            "STORAGE_DIR": "/tmp/storage",
            "BOT_API_TOKEN": "test-token",
            "API_URL": "https://api.telegram.org",
            "APP_URL": "https://app.example.com",
            "CONFIG_FILENAME": "myconfig.json",
            "CERT_DIR": "/certs",
            "TOKENS_DIR": "/tokens",
            "TOKENS_SALT": "salt",
            "LOG_FILE": "/var/log/app.log",
            "STORAGE_QUOTA_KB": "2048",
            "UNLIMITED_QUOTA_IDS": "123,456",
            "MOUNT_DIRS": "/a;/b",
        },
    )
    def test_load_all_env_vars(self):
        import importlib
        import nas_md.config as cfg_mod

        importlib.reload(cfg_mod)
        cfg_mod.load_bot_config()
        assert cfg_mod.server_cfg.bot_api_token == "test-token"
        assert cfg_mod.server_cfg.api_url == "https://api.telegram.org"
        assert cfg_mod.server_cfg.app_url == "https://app.example.com"
        assert cfg_mod.server_cfg.config_filename == "myconfig.json"
        assert cfg_mod.server_cfg.server_cert_dir == "/certs"
        # tokens_dir: on Windows /tokens gets resolved to D:\tokens by Path
        assert Path(cfg_mod.server_cfg.tokens_dir).name == "tokens"
        assert cfg_mod.server_cfg.tokens_salt == "salt"
        assert cfg_mod.server_cfg.server_log_file == "/var/log/app.log"
        assert cfg_mod.server_cfg.storage_quota_kb == 2048
        assert cfg_mod.server_cfg.unlimited_quota_ids == "123,456"
        assert cfg_mod.server_cfg.mount_dirs == "/a;/b"

    @patch.dict(os.environ, {}, clear=False)
    def test_load_defaults(self):
        import importlib
        import nas_md.config as cfg_mod

        importlib.reload(cfg_mod)
        cfg_mod.load_bot_config()
        # load_bot_config resolves relative paths to absolute paths
        assert cfg_mod.server_cfg.storage_dir.endswith("storage")
        assert Path(cfg_mod.server_cfg.storage_dir).is_absolute()
        assert cfg_mod.server_cfg.bot_api_token == ""
        assert cfg_mod.server_cfg.config_filename == "config.json"
