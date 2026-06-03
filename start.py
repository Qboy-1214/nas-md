#!/usr/bin/env python3
"""nas-md 一键启动脚本 - 兼容 Windows / Linux / macOS"""

import os
import sys
import subprocess
import webbrowser
import time
import threading
import signal
from pathlib import Path

# --- 配置 ---
BASE_DIR = Path(__file__).resolve().parent
WEB_PORT = int(os.environ.get("WEB_PORT", "8080"))
WEB_HOST = os.environ.get("WEB_HOST", "127.0.0.1")
MOUNT_DIRS = os.environ.get("MOUNT_DIRS", "")  # 分号分隔（跨平台安全，避免 Windows 盘符冲突）
OPEN_BROWSER_DELAY = 2  # 秒


def check_python():
    """检查 Python 版本"""
    ver = sys.version_info
    if ver < (3, 11):
        print(f"❌ 需要 Python 3.11+，当前版本 {ver.major}.{ver.minor}")
        sys.exit(1)
    print(f"✅ Python {sys.version.split()[0]}")


def check_deps():
    """检查并安装依赖（本项目纯 stdlib，仅做基础检查）"""
    # nas-md 核心功能只依赖 stdlib，无需 pip install
    # 如果未来有第三方依赖，在此添加
    print("✅ 依赖检查通过（纯 stdlib，无需安装）")


def setup_env():
    """设置环境变量默认值"""
    defaults = {
        "WEB_PORT": str(WEB_PORT),
        "WEB_HOST": WEB_HOST,
        "WEB_ROOT": str(BASE_DIR / "web"),
        "STORAGE_DIR": str(BASE_DIR / "storage"),
        "TOKENS_DIR": str(BASE_DIR / "tokens"),
        "MOUNT_DIRS": MOUNT_DIRS,
    }
    for key, value in defaults.items():
        if key not in os.environ and value:
            os.environ[key] = value


def print_banner():
    """打印启动横幅"""
    print("=" * 50)
    print("  nas-md - 个人知识管理系统")
    print("=" * 50)
    print(f"  访问地址: http://{WEB_HOST}:{WEB_PORT}")
    print(f"  静态文件: {os.environ.get('WEB_ROOT', '(none)')}")
    print(f"  挂载目录: {os.environ.get('MOUNT_DIRS') or '(none)'}")
    print(f"  存储目录: {os.environ.get('STORAGE_DIR', '(none)')}")
    print("=" * 50)
    print("  按 Ctrl+C 停止服务")
    print()


def open_browser():
    """延迟打开浏览器"""
    time.sleep(OPEN_BROWSER_DELAY)
    url = f"http://{WEB_HOST}:{WEB_PORT}"
    print(f"🌐 正在打开浏览器: {url}")
    webbrowser.open(url)


def run_server():
    """启动 web 服务器"""
    # 确保存储目录存在
    storage_dir = os.environ.get("STORAGE_DIR", str(BASE_DIR / "storage"))
    tokens_dir = os.environ.get("TOKENS_DIR", str(BASE_DIR / "tokens"))
    os.makedirs(storage_dir, exist_ok=True)
    os.makedirs(tokens_dir, exist_ok=True)

    # 设置 PYTHONPATH
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BASE_DIR)

    cmd = [
        sys.executable,
        "-m",
        "nas_md.cli",
        "web",
    ]

    print("🚀 启动服务...")
    print(f"> {' '.join(cmd)}")
    print()

    # 延迟打开浏览器
    threading.Thread(target=open_browser, daemon=True).start()

    proc = subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        env=env,
    )

    # 处理 Ctrl+C
    def signal_handler(sig, frame):
        print("\n⏹  正在停止服务...")
        proc.terminate()
        proc.wait(timeout=5)
        print("✅ 服务已停止")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, signal_handler)

    # 等待子进程
    try:
        proc.wait()
    except KeyboardInterrupt:
        signal_handler(None, None)


def main():
    check_python()
    check_deps()
    setup_env()
    print_banner()
    run_server()


if __name__ == "__main__":
    main()
