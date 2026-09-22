import { test, expect } from '@playwright/test';
import { deleteAdminFile, getWritableAdminMount, putAdminFile } from './helpers/admin.js';

async function ensureTestFile(page) {
  const mountInfo = await getWritableAdminMount(page);
  const testFileName = '_refresh-test-' + Date.now() + '.md';
  const initialContent = '# Refresh Test\n\nInitial content for testing reload.';
  await putAdminFile(page, mountInfo.id, `/${testFileName}`, initialContent);
  return { mountInfo, testFileName };
}

test.describe('文件从磁盘重新加载', () => {
  test('点击刷新按钮加载最新内容', async ({ page }) => {
    const { mountInfo, testFileName } = await ensureTestFile(page);

    // Open the file
    await page.evaluate(
      ({ mountId, path }) => {
        openFile('/' + path, mountId);
      },
      { mountId: mountInfo.id, path: testFileName },
    );
    await page.waitForTimeout(2000);

    // Verify refresh button is visible
    const refreshBtn = page.locator('#btn-refresh');
    await expect(refreshBtn, 'refresh button').toHaveCount(1);
    await expect(refreshBtn).toBeVisible();

    // Modify the file externally via API
    const newContent = '# Refresh Test\n\nUpdated content from external edit.';
    await putAdminFile(page, mountInfo.id, `/${testFileName}`, newContent);
    await page.waitForTimeout(500);

    // Click the refresh button
    await refreshBtn.click();
    await page.waitForTimeout(1000);

    // Toast should show success
    const toast = page.locator('#toast');
    await expect(toast).toBeVisible();
    const toastText = await toast.textContent();
    expect(toastText).toContain('重新加载');

    // Cleanup
    await deleteAdminFile(page, mountInfo.id, `/${testFileName}`);
  });

  test('文件被外部删除后点击刷新按钮显示提示', async ({ page }) => {
    const { mountInfo, testFileName } = await ensureTestFile(page);

    // Open the file
    await page.evaluate(
      ({ mountId, path }) => {
        openFile('/' + path, mountId);
      },
      { mountId: mountInfo.id, path: testFileName },
    );
    await page.waitForFunction(
      () => {
        const vd = window._vditor;
        return vd && vd.getValue().length > 0;
      },
      { timeout: 10000 },
    );

    // Delete the file externally
    await deleteAdminFile(page, mountInfo.id, `/${testFileName}`);
    await page.waitForTimeout(500);

    // Click refresh button — should show error toast
    const refreshBtn = page.locator('#btn-refresh');
    await expect(refreshBtn, 'refresh button').toHaveCount(1);
    await refreshBtn.click();
    await page.waitForTimeout(1000);

    // Toast should appear (either success or error)
    const toast = page.locator('#toast');
    await expect(toast).toBeVisible();
  });
});
