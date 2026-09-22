import { writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { test, expect } from '@playwright/test';
import { deleteAdminFile, getWritableAdminMount, putAdminFile } from './helpers/admin.js';

test.describe('文件版本号驱动协同编辑', () => {
  test('服务器挂载：版本号机制正常运行不报错', async ({ page }) => {
    const mountInfo = await getWritableAdminMount(page);

    const mountEl = page.locator('.mount-name', { hasText: mountInfo.name });
    await mountEl.click();
    await page.waitForTimeout(2000);

    const fileEl = page.locator('.tree-item:not(.folder)').first();
    await expect(fileEl, 'server mount contains a file').toHaveCount(1);
    await fileEl.click();
    await page.waitForTimeout(2000);

    await expect(page.locator('#vditor')).toBeVisible();

    const errors = [];
    page.on('pageerror', (err) => errors.push(err.message));

    // Verify baseVersion is initialized
    const baseVersion = await page.evaluate(() => {
      return state.baseVersion;
    });
    expect(baseVersion).toBeGreaterThanOrEqual(0);

    await page.waitForTimeout(500);
    expect(errors.filter((e) => e.includes('poll') || e.includes('version'))).toHaveLength(0);

    await page.waitForTimeout(6000);
    expect(errors.filter((e) => e.includes('poll') || e.includes('version'))).toHaveLength(0);
  });

  test('服务器挂载：文件内容未变化时编辑器不刷新', async ({ page }) => {
    const mountInfo = await getWritableAdminMount(page);

    // Create a fresh test file
    const testFileName = '_poll-same-' + Date.now() + '.md';
    const content = '# Same Content Test\n\nThis content will not change.';
    await putAdminFile(page, mountInfo.id, `/${testFileName}`, content);

    // Reload and open via sidebar
    await page.reload();
    await page.waitForSelector('.mount-name', { timeout: 10000 });
    await page.waitForTimeout(1500);
    const mountEl = page.locator('.mount-name', { hasText: mountInfo.name });
    await mountEl.click();
    await page.waitForTimeout(2000);

    const fileEl = page.locator('.tree-item', { hasText: testFileName });
    await expect(fileEl, 'test file visible in tree').toHaveCount(1);
    await fileEl.click();
    await page.waitForTimeout(2000);

    await expect(page.locator('#vditor')).toBeVisible();
    const initialContent = await page.evaluate(() => window._vditor.getValue());

    // Write same content back
    await putAdminFile(page, mountInfo.id, `/${testFileName}`, initialContent);

    // Wait for poll — content should be unchanged
    await page.waitForTimeout(7000);
    const afterContent = await page.evaluate(() => window._vditor.getValue());
    expect(afterContent).toBe(initialContent);

    // Cleanup
    await deleteAdminFile(page, mountInfo.id, `/${testFileName}`);
  });

  test('dirty 编辑器延后外部更新并在保存时合并', async ({ page }) => {
    const mountInfo = await getWritableAdminMount(page);

    // Create a fresh test file
    const testFileName = '_poll-dirty-' + Date.now() + '.md';
    const content = '# Dirty Test\n\nContent before external change.';
    await putAdminFile(page, mountInfo.id, `/${testFileName}`, content);

    let previousAutoSave;
    try {
      // Reload and open via sidebar
      await page.reload();
      await page.waitForSelector('.mount-name', { timeout: 10000 });
      await page.waitForTimeout(1500);
      const mountEl = page.locator('.mount-name', { hasText: mountInfo.name });
      await mountEl.click();
      await page.waitForTimeout(2000);

      const fileEl = page.locator('.tree-item', { hasText: testFileName });
      await expect(fileEl, 'test file visible in tree').toHaveCount(1);
      await fileEl.click();
      await page.waitForFunction(() => window._vditor?.getValue().includes('Dirty Test'));
      const mountPath = await page.evaluate(
        (mountId) => window.state.mounts.find((mount) => mount.id === mountId)?.path,
        mountInfo.id,
      );
      expect(mountPath, 'writable admin mount exposes its test path').toBeTruthy();

      previousAutoSave = await page.evaluate(() => {
        const wasEnabled = window.state.autoSave;
        window.toggleAutoSave(false);
        window._vditor.setValue(`${window._vditor.getValue()}\n\nUNSAVED LOCAL`);
        window.onEditorInput();
        return wasEnabled;
      });
      await expect.poll(() => page.evaluate(() => window.state.dirty)).toBe(true);

      const before = await page.evaluate(() => {
        const fileKey = `${window.state.currentMountId}:${window.state.currentPath}`;
        return {
          editor: window._vditor.getValue(),
          baseVersion: window.state.baseVersion,
          baseContent: window.state.baseContent,
          originalContent: window._originalContent,
          lastSavedContent: window._lastSavedContent,
          fileVersion: window.state.fileVersions[fileKey],
          dirty: window.state.dirty,
        };
      });

      // Modify the file externally while the editor has a protected local draft.
      const externalContent = '## External while dirty\n\nShould merge after save';
      await writeFile(join(mountPath, testFileName), externalContent, 'utf8');

      await expect
        .poll(() => page.evaluate(() => window.state.pendingRemoteVersion), { timeout: 10000 })
        .toBeGreaterThan(before.baseVersion);
      await expect(page.locator('#toast')).toContainText('检测到远端更新，将在保存时自动合并');

      const deferred = await page.evaluate(() => {
        const fileKey = `${window.state.currentMountId}:${window.state.currentPath}`;
        return {
          editor: window._vditor.getValue(),
          baseVersion: window.state.baseVersion,
          baseContent: window.state.baseContent,
          originalContent: window._originalContent,
          lastSavedContent: window._lastSavedContent,
          fileVersion: window.state.fileVersions[fileKey],
          dirty: window.state.dirty,
          pendingRemoteVersion: window.state.pendingRemoteVersion,
        };
      });
      const { pendingRemoteVersion, ...deferredSnapshot } = deferred;
      expect(deferredSnapshot).toEqual(before);
      expect(pendingRemoteVersion).toBeGreaterThan(before.baseVersion);

      await page.evaluate(() => window.saveFile({ silent: true }));
      const saved = await page.evaluate(() => ({
        editor: window._vditor.getValue(),
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
        originalContent: window._originalContent,
        dirty: window.state.dirty,
        pendingRemoteVersion: window.state.pendingRemoteVersion,
      }));
      expect(saved.editor).toContain('External while dirty');
      expect(saved.editor).toContain('UNSAVED LOCAL');
      expect(saved.baseContent).toBe(saved.editor);
      expect(saved.originalContent).toBe(saved.editor);
      expect(saved.dirty).toBe(false);
      expect(saved.pendingRemoteVersion).toBeNull();
    } finally {
      if (previousAutoSave !== undefined) {
        await page.evaluate((enabled) => window.toggleAutoSave(enabled), previousAutoSave);
      }
      await deleteAdminFile(page, mountInfo.id, `/${testFileName}`);
    }
  });
});
