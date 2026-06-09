import subprocess, os, traceback

repo = r'd:\own project\nas-md'

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=repo, timeout=30)
    return r.stdout.strip(), r.stderr.strip(), r.returncode

results = []

try:
    # 1. Check status
    out, err, rc = run(['git', 'status', '--short'])
    results.append(f'=== STATUS (rc={rc}) ===')
    results.append(out if out else '(empty)')
    if err: results.append(f'ERR: {err}')

    # 2. Add files
    out, err, rc = run(['git', 'add', 'nas_md/webserver/__init__.py', 'web/app.js', 'web/app.css', 'storage/欢迎.md', 'eslint.config.js'])
    results.append(f'=== ADD (rc={rc}) ===')
    results.append(out if out else '(empty)')
    if err: results.append(f'ERR: {err}')

    # 3. Check staged
    out, err, rc = run(['git', 'diff', '--cached', '--stat'])
    results.append(f'=== CACHED DIFF (rc={rc}) ===')
    results.append(out if out else '(empty)')
    if err: results.append(f'ERR: {err}')

    # 4. Commit
    out, err, rc = run(['git', 'commit', '-m', 'fix: create permission for public host mounts, local mount support, tree refresh after create'])
    results.append(f'=== COMMIT (rc={rc}) ===')
    results.append(out if out else '(empty)')
    if err: results.append(f'ERR: {err}')

    # 5. New HEAD
    out, err, rc = run(['git', 'rev-parse', 'HEAD'])
    results.append(f'=== NEW HEAD (rc={rc}) ===')
    results.append(out if out else '(empty)')

    # 6. Push
    out, err, rc = run(['git', 'push', 'origin', 'main'])
    results.append(f'=== PUSH (rc={rc}) ===')
    results.append(out if out else '(empty)')
    if err: results.append(f'ERR: {err}')

except Exception as e:
    results.append(f'EXCEPTION: {e}')
    results.append(traceback.format_exc())

# Write results to a file we can read
result_path = os.path.join(repo, '_git_result.txt')
try:
    with open(result_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(results))
    print(f'Results written to {result_path}')
except Exception as e2:
    # Try writing to a simpler path
    try:
        with open(r'D:\_git_result.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(results))
        print(f'Results written to D:\\_git_result.txt')
    except Exception as e3:
        print(f'FAILED TO WRITE: {e2} / {e3}')
        # Last resort: print to stdout
        print('\n'.join(results))
