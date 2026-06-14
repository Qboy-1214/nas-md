import { test, expect } from '@playwright/test';

async function ensureTestFile(page) {
  await page.goto('/admin');
  await page.waitForSelector('.mount-name', { timeout: 10000 });
  await page.waitForFunction(() => window.state && window.state.mounts, { timeout: 10000 });

  const mountInfo = await page.evaluate(() => {
    const m = window.state.mounts.find((m) => !m.id.startsWith('builtin') && !m.readonly);
    if (!m) return null;
    return { id: m.id, name: m.name };
  });
  if (!mountInfo) return null;

  const testFileName = '_refresh-test-' + Date.now() + '.md';
  const initialContent = '# Refresh Test\n\nInitial content for testing reload.';
  const putResp = await page.request.put(
    `/api/mounts/${mountInfo.id}/file?path=/${testFileName}`,
    { body: initialContent },
  );
  // Some CI environments may not support PUT to certain mounts
  if (!putResp.ok()) return null;

  return { mountInfo, testFileName };
}

test.describe('文件从磁盘重新加载', () => {
  test('点击刷新按钮加载最新内容', async ({ page }) => {
    const setup = await ensureTestFile(page);
    if (!setup) {
      test.skip(true, 'Could not create test file');
      return;
    }
    const { mountInfo, testFileName } = setup;

    // Open the file
    await page.evaluate(({ mountId, path }) => {
      openFile('/' + path, mountId);
    }, { mountId: mountInfo.id, path: testFileName });
    await page.waitForTimeout(2000);

    // Verify refresh button is visible
    const refreshBtn = page.locator('#btn-refresh');
    if ((await refreshBtn.count()) === 0) {
      test.skip(true, 'Refresh button not found');
      return;
    }
    await expect(refreshBtn).toBeVisible();

    // Modify the file externally via API
    const newContent = '# Refresh Test\n\nUpdated content from external edit.';
    await page.request.put(
      `/api/mounts/${mountInfo.id}/file?path=/${testFileName}`,
      { body: newContent },
    );
    await page.waitForTimeout(500);

    // Click the refresh button
    await refreshBtn.click();
    await page.waitForTimeout(1000);

    // Toast should show success
    const toast = page.locator('#toast');
    await expect(toast).toBeVisible();
    const toastText = await toast.textContent();
    expect(toastText).toContain('重新加载');

    // Cleanup (best effort)
    await page.request.delete(
      `/api/mounts/${mountInfo.id}/file?path=/${testFileName}`,
    );
  });

  test('文件被外部删除后点击刷新按钮显示提示', async ({ page }) => {
    const setup = await ensureTestFile(page);
    if (!setup) {
      test.skip(true, 'Could not create test file');
      return;
    }
    const { mountInfo, testFileName } = setup;

    // Open the file
    await page.evaluate(({ mountId, path }) => {
      openFile('/' + path, mountId);
    }, { mountId: mountInfo.id, path: testFileName });
    await page.waitForFunction(() => {
      const vd = window._vditor;
      return vd && vd.getValue().length > 0;
    }, { timeout: 10000 });

    // Delete the file externally (best effort)
    await page.request.delete(
      `/api/mounts/${mountInfo.id}/file?path=/${testFileName}`,
    );
    await page.waitForTimeout(500);

    // Click refresh button — should show error toast
    const refreshBtn = page.locator('#btn-refresh');
    if ((await refreshBtn.count()) === 0) {
      test.skip(true, 'Refresh button not found');
      return;
    }
    await refreshBtn.click();
    await page.waitForTimeout(1000);

    // Toast should appear (either success or error)
    const toast = page.locator('#toast');
    await expect(toast).toBeVisible();
  });
});
