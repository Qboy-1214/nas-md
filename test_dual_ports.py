"""测试 HTTP 与 HTTPS 双端口服务运行脚本。

在后台并发启动 nas-md 服务，并分别向 HTTP(8080) 和 HTTPS(8443) 发起请求以校验连接。
"""

import os
import ssl
import sys
import time
import urllib.request
import multiprocessing
from pathlib import Path

# 设置编码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def run_server(tmp_dir):
    """在子进程中启动服务器"""
    os.environ["WEB_PORT"] = "8080"
    os.environ["HTTPS_PORT"] = "8443"
    os.environ["WEB_HOST"] = "127.0.0.1"

    from nas_md.webserver import serve

    web_dir = Path(tmp_dir) / "web"
    web_dir.mkdir(parents=True, exist_ok=True)
    (web_dir / "index.html").write_text("<h1>NAS-MD Test</h1>", encoding="utf-8")

    storage_dir = Path(tmp_dir) / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    serve(
        mount_dirs=[],
        public_mount_dirs=[],
        public_mount_names=set(),
        web_root=str(web_dir),
        port=8080,
        https_port=8443,
        host="127.0.0.1",
        storage_dir=str(storage_dir),
    )


def test_ports():
    """测试 HTTP 与 HTTPS 访问"""
    import tempfile

    print("=" * 50)
    print("开始双端口联调测试...")
    print("=" * 50)

    with tempfile.TemporaryDirectory() as tmp_dir:
        # 启动服务器子进程
        server_process = multiprocessing.Process(target=run_server, args=(tmp_dir,), daemon=True)
        server_process.start()

        # 等待服务器初始化
        print("正在等待服务器启动与 SSL 证书生成 (3秒)...")
        time.sleep(3)

        http_url = "http://127.0.0.1:8080/"
        https_url = "https://127.0.0.1:8443/"

        # 忽略自签名证书校验
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        success = True

        # 1. 测试 HTTP 端口
        print("\n[1/2] 测试 HTTP 端口 (http://127.0.0.1:8080)...")
        try:
            req = urllib.request.Request(http_url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                print(f"  ✓ HTTP 响应状态码: {resp.status}")
                print(f"  ✓ HTTP 响应头 Content-Type: {resp.headers.get('Content-Type')}")
                body = resp.read().decode("utf-8")
                print(f"  ✓ HTTP 内容校验: {'NAS-MD Test' in body}")
        except Exception as e:
            print(f"  ✗ HTTP 请求失败: {e}")
            success = False

        # 2. 测试 HTTPS 端口
        print("\n[2/2] 测试 HTTPS 端口 (https://127.0.0.1:8443)...")
        try:
            req = urllib.request.Request(https_url)
            with urllib.request.urlopen(req, context=ssl_context, timeout=5) as resp:
                print(f"  ✓ HTTPS 响应状态码: {resp.status}")
                print(f"  ✓ HTTPS 响应头 Content-Type: {resp.headers.get('Content-Type')}")
                body = resp.read().decode("utf-8")
                print(f"  ✓ HTTPS 内容校验: {'NAS-MD Test' in body}")
        except Exception as e:
            print(f"  ✗ HTTPS 请求失败: {e}")
            success = False

        # 停止子进程
        print("\n正在停止测试服务器...")
        server_process.terminate()
        server_process.join(timeout=2)

        print("\n" + "=" * 50)
        if success:
            print("🎉 测试通过！HTTP 和 HTTPS 双端口均能正常响应。")
        else:
            print("❌ 测试失败！未全部分别成功访问两个端口。")
        print("=" * 50)


if __name__ == "__main__":
    test_ports()
