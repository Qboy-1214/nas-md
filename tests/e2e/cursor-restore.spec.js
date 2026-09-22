import { test, expect } from '@playwright/test';
import { deleteAdminFile, getWritableAdminMount, putAdminFile } from './helpers/admin.js';

async function ensureTestFile(page) {
  const mountInfo = await getWritableAdminMount(page);
  const testFileName = '_cursor-test-' + Date.now() + '.md';
  let content = '# Scroll Test Document\n\n';
  for (let i = 1; i <= 80; i++) {
    content += `## Section ${i}\n\n`;
    for (let j = 1; j <= 8; j++) {
      content += `Paragraph ${i}.${j}: Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.\n\n`;
    }
  }

  await putAdminFile(page, mountInfo.id, `/${testFileName}`, content);

  // Reload so tree picks up the file
  await page.reload();
  await page.waitForSelector('.mount-name', { timeout: 10000 });

  // Expand the mount
  const mountEl = page.locator('.mount-name', { hasText: mountInfo.name });
  await mountEl.click();
  await page.waitForTimeout(2000);

  return { mountInfo, testFileName };
}

async function scrollToBottom(page) {
  await page.evaluate(() => {
    const vd = window._vditor;
    if (!vd) return;
    const mode = vd.getCurrentMode();
    const el =
      mode === 'sv'
        ? vd.vditor.sv.element
        : mode === 'wysiwyg'
          ? vd.vditor.wysiwyg.element
          : vd.vditor.ir.element;
    if (!el) return;
    // Try direct scrollTop first
    const maxScroll = el.scrollHeight - el.clientHeight;
    if (maxScroll > 0) {
      el.scrollTop = maxScroll;
    } else {
      // Fallback: scroll last child into view
      const lastChild = el.querySelector('.vditor-reset') || el;
      if (lastChild) lastChild.scrollIntoView({ block: 'end' });
    }
  });
  await page.waitForTimeout(500);
}

async function getScrollTop(page) {
  return page.evaluate(() => {
    const vd = window._vditor;
    if (!vd) return 0;
    const mode = vd.getCurrentMode();
    const el =
      mode === 'sv'
        ? vd.vditor.sv.element
        : mode === 'wysiwyg'
          ? vd.vditor.wysiwyg.element
          : vd.vditor.ir.element;
    return el ? el.scrollTop : 0;
  });
}

test.describe('光标和滚动位置恢复', () => {
  test('刷新页面后恢复滚动位置', async ({ page }) => {
    const { mountInfo, testFileName } = await ensureTestFile(page);

    const fileEl = page.locator('.tree-item', { hasText: testFileName });
    await expect(fileEl, 'test file visible in tree').toHaveCount(1);
    await fileEl.click();
    await page.waitForFunction(
      () => {
        const vd = window._vditor;
        return vd && vd.getValue().length > 100;
      },
      { timeout: 10000 },
    );

    // Scroll to bottom
    await scrollToBottom(page);
    const scrollBefore = await getScrollTop(page);

    // Reload page
    await page.reload();
    await page.waitForSelector('.mount-name', { timeout: 10000 });
    await page.waitForTimeout(3000);

    // Verify same file is opened (breadcrumb or editor content)
    const breadcrumb = page.locator('#breadcrumb');
    const breadcrumbText = await breadcrumb.textContent();
    expect(breadcrumbText, 'file auto-restored after reload').toContain(testFileName);

    // Check scroll position restored (if scrollable)
    const scrollAfter = await getScrollTop(page);
    if (scrollBefore > 0) {
      expect(Math.abs(scrollAfter - scrollBefore)).toBeLessThan(200);
    }

    await deleteAdminFile(page, mountInfo.id, `/${testFileName}`);
  });

  test('刷新页面后恢复标题位置', async ({ page }) => {
    const { mountInfo, testFileName } = await ensureTestFile(page);

    const fileEl = page.locator('.tree-item', { hasText: testFileName });
    await expect(fileEl, 'test file visible in tree').toHaveCount(1);
    await fileEl.click();
    await page.waitForFunction(
      () => {
        const vd = window._vditor;
        return vd && vd.getValue().length > 100;
      },
      { timeout: 10000 },
    );

    // Scroll to middle
    await page.evaluate(() => {
      const vd = window._vditor;
      if (!vd) return;
      const el = vd.vditor.ir.element;
      el.scrollTop = (el.scrollHeight - el.clientHeight) / 2;
    });
    await page.waitForTimeout(500);
    const scrollBefore = await getScrollTop(page);

    // Reload
    await page.reload();
    await page.waitForSelector('.mount-name', { timeout: 10000 });
    await page.waitForTimeout(3000);

    const breadcrumbText = await page.locator('#breadcrumb').textContent();
    expect(breadcrumbText, 'file auto-restored after reload').toContain(testFileName);

    const scrollAfter = await getScrollTop(page);
    if (scrollBefore > 0) {
      expect(Math.abs(scrollAfter - scrollBefore)).toBeLessThan(200);
    }

    await deleteAdminFile(page, mountInfo.id, `/${testFileName}`);
  });

  test('切换文件时保存光标位置到 localStorage', async ({ page }) => {
    const { mountInfo, testFileName } = await ensureTestFile(page);

    const fileEl = page.locator('.tree-item', { hasText: testFileName });
    await expect(fileEl, 'test file visible in tree').toHaveCount(1);
    await fileEl.click();
    await page.waitForFunction(
      () => {
        const vd = window._vditor;
        return vd && vd.getValue().length > 100;
      },
      { timeout: 10000 },
    );

    // Scroll to middle
    await page.evaluate(() => {
      const vd = window._vditor;
      if (!vd) return;
      const el = vd.vditor.ir.element;
      el.scrollTop = (el.scrollHeight - el.clientHeight) / 2;
    });
    await page.waitForTimeout(500);

    // Switch to another file
    await page.evaluate(() => openFile('/欢迎.md', 'builtin-storage'));
    await page.waitForTimeout(1500);

    // Check localStorage has cursor position
    const savedPos = await page.evaluate(() => localStorage.getItem('nasmd_cursor_pos'));
    expect(savedPos).not.toBeNull();
    const pos = JSON.parse(savedPos);
    expect(pos).toHaveProperty('scrollPercent');
    expect(pos).toHaveProperty('headingText');

    await deleteAdminFile(page, mountInfo.id, `/${testFileName}`);
  });

  test('打开新文件时光标位于顶部', async ({ page }) => {
    const { mountInfo, testFileName } = await ensureTestFile(page);

    const fileEl = page.locator('.tree-item', { hasText: testFileName });
    await expect(fileEl, 'test file visible in tree').toHaveCount(1);
    await fileEl.click();
    await page.waitForFunction(
      () => {
        const vd = window._vditor;
        return vd && vd.getValue().length > 100;
      },
      { timeout: 10000 },
    );

    // Scroll to bottom
    await scrollToBottom(page);

    // Switch to a different file
    await page.evaluate(() => openFile('/欢迎.md', 'builtin-storage'));
    await page.waitForTimeout(1500);

    // New file should start at top
    const scrollTop = await getScrollTop(page);
    expect(scrollTop).toBeLessThan(50);

    await deleteAdminFile(page, mountInfo.id, `/${testFileName}`);
  });

  test('快速连续切换编辑模式不会运行过期恢复回调', async ({ page }) => {
    const { mountInfo, testFileName } = await ensureTestFile(page);

    try {
      const fileEl = page.locator('.tree-item', { hasText: testFileName });
      await expect(fileEl, 'test file visible in tree').toHaveCount(1);
      await fileEl.click();
      await page.waitForFunction(
        () => {
          const vd = window._vditor;
          return vd && vd.getValue().length > 100;
        },
        { timeout: 10000 },
      );

      const pageErrors = [];
      page.on('pageerror', (error) => pageErrors.push(error.message));

      await page.evaluate(() => setEditorMode('wysiwyg'));
      await page.waitForFunction(() => window._vditor?.getCurrentMode() === 'wysiwyg');
      await page.waitForTimeout(800);

      await page.evaluate(() => setEditorMode('ir'));
      await page.waitForFunction(() => window._vditor?.getCurrentMode() === 'ir');
      await page.waitForTimeout(2600);

      expect(pageErrors, 'superseded restore callbacks must not touch the new editor').toEqual([]);
      expect(await page.evaluate(() => window._vditor?.getCurrentMode())).toBe('ir');
    } finally {
      await deleteAdminFile(page, mountInfo.id, `/${testFileName}`);
    }
  });
});
