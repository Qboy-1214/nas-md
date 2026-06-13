import { test, expect } from '@playwright/test';

test.describe('文件轮询检测外部修改', () => {
  test('服务器挂载：轮询机制正常运行不报错', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForSelector('.mount-name', { timeout: 10000 });

    // Find a writable mount
    const mountInfo = await page.evaluate(() => {
      const m = state.mounts.find((m) => !m.id.startsWith('builtin') && !m.readonly);
      if (!m) return null;
      return { id: m.id, name: m.name };
    });
    if (!mountInfo) {
      test.skip(true, 'No writable mount found');
      return;
    }

    // Expand mount and open first file
    const mountEl = page.locator('.mount-name', { hasText: mountInfo.name });
    await mountEl.click();
    await page.waitForTimeout(2000);

    const fileEl = page.locator('.tree-item:not(.folder)').first();
    if ((await fileEl.count()) === 0) {
      test.skip(true, 'No files found');
      return;
    }
    await fileEl.click();
    await page.waitForTimeout(2000);

    // Verify editor is visible
    await expect(page.locator('#vditor')).toBeVisible();

    // Call pollCurrentFile directly — should not throw
    const errors = [];
    page.on('pageerror', (err) => errors.push(err.message));
    await page.evaluate(() => pollCurrentFile());
    await page.waitForTimeout(500);

    // No JS errors from polling
    expect(errors.filter((e) => e.includes('poll'))).toHaveLength(0);

    // Wait for a full poll cycle (5s) — no crashes
    await page.waitForTimeout(6000);
    expect(errors.filter((e) => e.includes('poll'))).toHaveLength(0);
  });

  test('服务器挂载：文件内容未变化时编辑器不刷新', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForSelector('.mount-name', { timeout: 10000 });

    const mountInfo = await page.evaluate(() => {
      const m = state.mounts.find((m) => !m.id.startsWith('builtin') && !m.readonly);
      if (!m) return null;
      return { id: m.id, name: m.name };
    });
    if (!mountInfo) {
      test.skip(true, 'No writable mount found');
      return;
    }

    // Create a fresh test file
    const testFileName = '_poll-same-' + Date.now() + '.md';
    const content = '# Same Content Test\n\nThis content will not change.';
    await page.request.put(
      `/api/mounts/${mountInfo.id}/file?path=/${testFileName}`,
      { body: content }
    );

    // Reload and open via sidebar
    await page.reload();
    await page.waitForSelector('.mount-name', { timeout: 10000 });
    await page.waitForTimeout(1500);
    const mountEl = page.locator('.mount-name', { hasText: mountInfo.name });
    await mountEl.click();
    await page.waitForTimeout(2000);

    const fileEl = page.locator('.tree-item', { hasText: testFileName });
    if ((await fileEl.count()) === 0) {
      test.skip(true, 'File not visible in tree');
      return;
    }
    await fileEl.click();
    await page.waitForTimeout(2000);

    await expect(page.locator('#vditor')).toBeVisible();
    const initialContent = await page.evaluate(() => window._vditor.getValue());

    // Write same content back
    await page.request.put(
      `/api/mounts/${mountInfo.id}/file?path=/${testFileName}`,
      { body: initialContent }
    );

    // Wait for poll — content should be unchanged
    await page.waitForTimeout(7000);
    const afterContent = await page.evaluate(() => window._vditor.getValue());
    expect(afterContent).toBe(initialContent);

    // Cleanup
    await page.request.delete(
      `/api/mounts/${mountInfo.id}/file?path=/${testFileName}`
    );
  });

  test('轮询跳过有未保存修改的编辑器', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForSelector('.mount-name', { timeout: 10000 });

    const mountInfo = await page.evaluate(() => {
      const m = state.mounts.find((m) => !m.id.startsWith('builtin') && !m.readonly);
      if (!m) return null;
      return { id: m.id, name: m.name };
    });
    if (!mountInfo) {
      test.skip(true, 'No writable mount found');
      return;
    }

    // Create a fresh test file
    const testFileName = '_poll-dirty-' + Date.now() + '.md';
    const content = '# Dirty Test\n\nContent before external change.';
    await page.request.put(
      `/api/mounts/${mountInfo.id}/file?path=/${testFileName}`,
      { body: content }
    );

    // Reload and open via sidebar
    await page.reload();
    await page.waitForSelector('.mount-name', { timeout: 10000 });
    await page.waitForTimeout(1500);
    const mountEl = page.locator('.mount-name', { hasText: mountInfo.name });
    await mountEl.click();
    await page.waitForTimeout(2000);

    const fileEl = page.locator('.tree-item', { hasText: testFileName });
    if ((await fileEl.count()) === 0) {
      test.skip(true, 'File not visible in tree');
      return;
    }
    await fileEl.click();
    await page.waitForTimeout(2000);

    // Type to create unsaved changes
    const vditorInput = page.locator('.vditor-ir');
    await vditorInput.click();
    await page.keyboard.type('UNSAVED ');
    await page.waitForTimeout(500);

    const hasChanges = await page.evaluate(() => {
      return window._vditor.getValue() !== window._originalContent;
    });
    expect(hasChanges).toBe(true);

    // Modify file externally
    const externalContent = '## External while dirty\n\nShould not auto-update';
    await page.request.put(
      `/api/mounts/${mountInfo.id}/file?path=/${testFileName}`,
      { body: externalContent }
    );

    // Wait for poll — editor should NOT auto-update
    await page.waitForTimeout(7000);
    const contentResult = await page.evaluate(() => window._vditor.getValue());
    expect(contentResult).toContain('UNSAVED');
    expect(contentResult).not.toContain('External while dirty');

    // Cleanup
    await page.request.delete(
      `/api/mounts/${mountInfo.id}/file?path=/${testFileName}`
    );
  });
});
