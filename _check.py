import subprocess, os
repo = r'd:\own project\nas-md'
out = os.path.join(repo, '_git_check.txt')
r = subprocess.run(['git', 'diff', '--stat'], capture_output=True, text=True, cwd=repo)
r2 = subprocess.run(['git', 'log', '--oneline', '-3'], capture_output=True, text=True, cwd=repo)
r3 = subprocess.run(['git', 'status', '--short'], capture_output=True, text=True, cwd=repo)
with open(out, 'w', encoding='utf-8') as f:
    f.write('=== DIFF ===\n')
    f.write(r.stdout[:2000])
    f.write(r.stderr[:500])
    f.write('\n=== LOG ===\n')
    f.write(r2.stdout[:500])
    f.write(r2.stderr[:500])
    f.write('\n=== STATUS ===\n')
    f.write(r3.stdout[:2000])
    f.write(r3.stderr[:500])
