import json
import sys

path = r'd:\own project\nas-md\storage\.version_history\mount-0__AI客服整体流程-日志查询版.md.json'
with open(path, 'r', encoding='utf-8') as f:
    d = json.load(f)

versions = d['versions']
print(f'Total versions: {len(versions)}')
for i, v in enumerate(versions):
    ts = v.get('timestamp', 0)
    author = v.get('author_name', 'unknown')
    changes = len(v.get('changes', []))
    print(f'{i}: ts={ts:.0f} author={author} changes={changes}')
