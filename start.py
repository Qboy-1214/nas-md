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
MOUNT_DIRS = os.environ.get("MOUNT_DIRS", "")  # 留空，由用户通过前端打开目录
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
        "TOKENS_DIR": str(BASE_DIR / "tokens"),  # Telegram Bot 令牌存储（Web 模式未使用）
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

    mount_dirs = os.environ.get("MOUNT_DIRS", "")
    print(f"  挂载目录: {mount_dirs or '(none)'}")
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


def check_port(host: str, port: int) -> bool:
    """检查端口是否已被占用"""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.settimeout(1)
            s.connect((host, port))
            return True  # 端口已被占用
        except OSError:
            return False  # 端口可用


def kill_port_process(port: int) -> bool:
    """杀掉占用指定端口的进程"""
    import subprocess

    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pids = set()
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                if parts:
                    pids.add(int(parts[-1]))
        if pids:
            for pid in pids:
                try:
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], timeout=3)
                    print(f"  已终止占用端口 {port} 的进程 (PID: {pid})")
                except Exception:
                    pass
            return True
    except Exception:
        pass
    return False


def run_server():
    """启动 web 服务器"""
    # 确保存储目录存在
    storage_dir = os.environ.get("STORAGE_DIR", str(BASE_DIR / "storage"))
    tokens_dir = os.environ.get("TOKENS_DIR", str(BASE_DIR / "tokens"))  # Telegram Bot（Web 模式未使用）
    os.makedirs(storage_dir, exist_ok=True)
    os.makedirs(tokens_dir, exist_ok=True)

    # 检查端口是否已被占用
    if check_port(WEB_HOST, WEB_PORT):
        print(f"⚠️  端口 {WEB_PORT} 已被占用")
        answer = input("   是否终止占用进程并继续？(y/N) ").strip().lower()
        if answer == "y":
            if kill_port_process(WEB_PORT):
                import time

                time.sleep(1)  # 等待端口释放
                if check_port(WEB_HOST, WEB_PORT):
                    print(f"❌ 端口 {WEB_PORT} 仍被占用，无法启动")
                    sys.exit(1)
            else:
                print("❌ 无法终止占用端口的进程")
                sys.exit(1)
        else:
            print("已取消启动")
            sys.exit(0)

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

    # Windows: 使用 CREATE_NEW_PROCESS_GROUP 以便可靠终止子进程
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000200  # CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        env=env,
        **kwargs,
    )

    def _kill_proc():
        """确保子进程被终止"""
        if sys.platform == "win32":
            # Windows: taskkill 杀掉整个进程树
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                timeout=5,
                capture_output=True,
            )
        else:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    # 处理 Ctrl+C
    def signal_handler(sig, frame):
        print("\n⏹  正在停止服务...")
        _kill_proc()
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
