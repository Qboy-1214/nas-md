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

async function waitForTestDocumentReady(page) {
  await expect(
    page.locator('.vditor-ir .vditor-reset p', { hasText: 'Paragraph 80.8:' }),
    'complete test document rendered in editor',
  ).toHaveCount(1, { timeout: 10000 });
}

async function scrollToBottom(page) {
  await getScrollTop(page);
  await page.waitForFunction(
    () => {
      const vd = window._vditor;
      if (!vd) return false;
      const mode = vd.getCurrentMode();
      const base =
        mode === 'sv'
          ? vd.vditor.sv.element
          : mode === 'wysiwyg'
            ? vd.vditor.wysiwyg.element
            : vd.vditor.ir.element;
      const el = mode === 'sv' ? base : base?.querySelector('.vditor-reset') || base;
      return Boolean(el && el.scrollHeight > el.clientHeight);
    },
    undefined,
    { timeout: 10000 },
  );
  await page.evaluate(() => {
    const vd = window._vditor;
    if (!vd) throw new Error('Vditor editor is unavailable');
    const mode = vd.getCurrentMode();
    const base =
      mode === 'sv'
        ? vd.vditor.sv.element
        : mode === 'wysiwyg'
          ? vd.vditor.wysiwyg.element
          : vd.vditor.ir.element;
    const el = mode === 'sv' ? base : base?.querySelector('.vditor-reset') || base;
    if (!el) throw new Error(`Vditor ${mode} scroll container is unavailable`);
    el.scrollTop = el.scrollHeight - el.clientHeight;
  });
}

async function placeCursorAtHeading(page, headingText) {
  await getScrollTop(page);
  await page.evaluate((expectedHeading) => {
    const vd = window._vditor;
    if (!vd) throw new Error('Vditor editor is unavailable');
    const mode = vd.getCurrentMode();
    const base =
      mode === 'sv'
        ? vd.vditor.sv.element
        : mode === 'wysiwyg'
          ? vd.vditor.wysiwyg.element
          : vd.vditor.ir.element;
    const el = mode === 'sv' ? base : base?.querySelector('.vditor-reset') || base;
    if (!el) throw new Error(`Vditor ${mode} scroll container is unavailable`);
    const heading = Array.from(el.querySelectorAll('h1, h2, h3, h4, h5, h6')).find((node) =>
      (node.innerText || node.textContent).includes(expectedHeading),
    );
    if (!heading) throw new Error(`Heading is unavailable: ${expectedHeading}`);
    const walker = document.createTreeWalker(heading, NodeFilter.SHOW_TEXT);
    let headingTextNode = walker.nextNode();
    while (headingTextNode && !headingTextNode.nodeValue.includes(expectedHeading)) {
      headingTextNode = walker.nextNode();
    }
    if (!headingTextNode) throw new Error(`Heading text is unavailable: ${expectedHeading}`);

    el.focus({ preventScroll: true });
    const selection = window.getSelection();
    const range = document.createRange();
    range.setStart(headingTextNode, Math.min(1, headingTextNode.nodeValue.length));
    range.collapse(true);
    selection.removeAllRanges();
    selection.addRange(range);

    const headingOffset = heading.getBoundingClientRect().top - el.getBoundingClientRect().top;
    el.scrollTop += headingOffset - el.clientHeight / 3;
  }, headingText);
  await expect.poll(() => getScrollTop(page), { timeout: 5000 }).toBeGreaterThan(0);
}

async function getScrollTop(page) {
  return page.evaluate(() => {
    const vd = window._vditor;
    if (!vd) throw new Error('Vditor editor is unavailable');
    const mode = vd.getCurrentMode();
    const base =
      mode === 'sv'
        ? vd.vditor.sv.element
        : mode === 'wysiwyg'
          ? vd.vditor.wysiwyg.element
          : vd.vditor.ir.element;
    const el = mode === 'sv' ? base : base?.querySelector('.vditor-reset') || base;
    if (!el) throw new Error(`Vditor ${mode} scroll container is unavailable`);
    return el.scrollTop;
  });
}

test.describe('光标和滚动位置恢复', () => {
  test('滚动辅助函数在编辑器缺失时直接失败', async ({ page }) => {
    const results = await Promise.allSettled([scrollToBottom(page), getScrollTop(page)]);

    expect(results.map((result) => result.status)).toEqual(['rejected', 'rejected']);
    for (const result of results) {
      expect(result.reason.message).toContain('Vditor editor is unavailable');
    }
  });

  test('刷新页面后恢复滚动位置', async ({ page }) => {
    const { mountInfo, testFileName } = await ensureTestFile(page);

    try {
      const fileEl = page.locator('.tree-item', { hasText: testFileName });
      await expect(fileEl, 'test file visible in tree').toHaveCount(1);
      await fileEl.click();
      await waitForTestDocumentReady(page);

      // Scroll to bottom
      await scrollToBottom(page);
      const scrollBefore = await getScrollTop(page);
      expect(scrollBefore, 'test document must be scrollable').toBeGreaterThan(0);

      // Reload page
      await page.reload();
      await page.waitForSelector('.mount-name', { timeout: 10000 });

      // Wait for the saved file to be restored, including under a loaded full-suite server.
      await expect(page.locator('#breadcrumb'), 'file auto-restored after reload').toContainText(
        testFileName,
        { timeout: 15000 },
      );

      // Check scroll position restored
      await expect
        .poll(async () => Math.abs((await getScrollTop(page)) - scrollBefore), {
          timeout: 5000,
        })
        .toBeLessThan(200);
    } finally {
      await deleteAdminFile(page, mountInfo.id, `/${testFileName}`);
    }
  });

  test('刷新页面后恢复标题位置', async ({ page }) => {
    const { mountInfo, testFileName } = await ensureTestFile(page);

    const fileEl = page.locator('.tree-item', { hasText: testFileName });
    await expect(fileEl, 'test file visible in tree').toHaveCount(1);
    await fileEl.click();
    await waitForTestDocumentReady(page);

    // Put the cursor at a middle heading and persist the exact restore anchor.
    await placeCursorAtHeading(page, 'Section 40');
    const scrollBefore = await getScrollTop(page);
    expect(scrollBefore, 'test document must be scrollable').toBeGreaterThan(0);
    const savedPosition = await page.evaluate(() => {
      saveCursorScrollToStorage();
      return JSON.parse(localStorage.getItem('nasmd_cursor_pos'));
    });
    expect(savedPosition.headingText).toContain('Section 40');

    // Reload
    await page.reload();
    await page.waitForSelector('.mount-name', { timeout: 10000 });

    await expect(page.locator('#breadcrumb'), 'file auto-restored after reload').toContainText(
      testFileName,
      { timeout: 15000 },
    );
    await waitForTestDocumentReady(page);

    await expect
      .poll(async () => Math.abs((await getScrollTop(page)) - scrollBefore), {
        timeout: 5000,
      })
      .toBeLessThan(200);

    await deleteAdminFile(page, mountInfo.id, `/${testFileName}`);
  });

  test('切换文件时保存光标位置到 localStorage', async ({ page }) => {
    const { mountInfo, testFileName } = await ensureTestFile(page);

    const fileEl = page.locator('.tree-item', { hasText: testFileName });
    await expect(fileEl, 'test file visible in tree').toHaveCount(1);
    await fileEl.click();
    await waitForTestDocumentReady(page);

    // Place the cursor on a real heading so the persisted state has a meaningful anchor.
    await placeCursorAtHeading(page, 'Section 40');
    expect(await getScrollTop(page), 'test document must be scrollable').toBeGreaterThan(0);

    // Switch to another real file through the same UI path as a user.
    const otherFile = page.locator('.tree-item', { hasText: 'test-scroll.md' });
    await expect(otherFile, 'switch target visible in tree').toHaveCount(1);
    await otherFile.click();
    await expect(page.locator('#breadcrumb'), 'switch target opened').toContainText(
      'test-scroll.md',
    );

    // Check localStorage has cursor position
    const savedPos = await page.evaluate(() => localStorage.getItem('nasmd_cursor_pos'));
    expect(savedPos).not.toBeNull();
    const pos = JSON.parse(savedPos);
    expect(pos).toHaveProperty('scrollPercent');
    expect(pos.headingText).toContain('Section 40');

    await deleteAdminFile(page, mountInfo.id, `/${testFileName}`);
  });

  test('打开新文件时光标位于顶部', async ({ page }) => {
    const { mountInfo, testFileName } = await ensureTestFile(page);

    const fileEl = page.locator('.tree-item', { hasText: testFileName });
    await expect(fileEl, 'test file visible in tree').toHaveCount(1);
    await fileEl.click();
    await waitForTestDocumentReady(page);

    // Scroll to bottom
    await scrollToBottom(page);

    // Switch to a different real file.
    const otherFile = page.locator('.tree-item', { hasText: 'test-scroll.md' });
    await expect(otherFile, 'switch target visible in tree').toHaveCount(1);
    await otherFile.click();
    await expect(page.locator('#breadcrumb'), 'switch target opened').toContainText(
      'test-scroll.md',
    );

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
      await waitForTestDocumentReady(page);

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
