import urllib.request
import urllib.parse
import json
import sys

# Force UTF-8 output
sys.stdout.reconfigure(encoding="utf-8")

# Properly encode the URL with Chinese characters
base_url = "http://localhost:8080/api/history"
params = {
    "file": "mount-0:/AI客服整体流程-日志查询版.md",
    "limit": "20",
    "_t": str(int(__import__("time").time())),
}
url = base_url + "?" + urllib.parse.urlencode(params)
print("Request URL:", url)

try:
    with urllib.request.urlopen(url) as resp:
        raw = resp.read()
        print("Response Content-Type:", resp.headers.get("Content-Type"))
        print("Response length:", len(raw))
        data = json.loads(raw.decode("utf-8"))
        versions = data.get("versions", [])
        print("versions count:", len(versions))
        for i, v in enumerate(versions):
            ts = v.get("timestamp", 0)
            author = v.get("authorName", v.get("author_name", "unknown"))
            changes = len(v.get("changes", []))
            content_len = v.get("contentLength", v.get("content_length", "?"))
            print(f"{i}: ts={ts} author={author} changes={changes} contentLength={content_len}")
except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
