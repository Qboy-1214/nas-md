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

  test('轮询跳过有未保存修改的编辑器', async ({ page }) => {
    const mountInfo = await getWritableAdminMount(page);

    // Create a fresh test file
    const testFileName = '_poll-dirty-' + Date.now() + '.md';
    const content = '# Dirty Test\n\nContent before external change.';
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
    await putAdminFile(page, mountInfo.id, `/${testFileName}`, externalContent);

    // Wait for poll — editor should NOT auto-update
    await page.waitForTimeout(7000);
    const contentResult = await page.evaluate(() => window._vditor.getValue());
    expect(contentResult).toContain('UNSAVED');
    expect(contentResult).not.toContain('External while dirty');

    // Cleanup
    await deleteAdminFile(page, mountInfo.id, `/${testFileName}`);
  });
});
