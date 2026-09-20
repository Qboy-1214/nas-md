import { test, expect } from '@playwright/test';

const markdown = `# Mermaid Fullscreen

\`\`\`mermaid
flowchart TD
  A --> B
\`\`\`

After the diagram`;

const twoMermaidMarkdown = `# Two Mermaid Blocks

\`\`\`mermaid
flowchart TD
  A --> B
\`\`\`

Between diagrams

\`\`\`mermaid
flowchart LR
  C --> D
\`\`\``;

async function prepareEditor(page) {
  await page.addInitScript(() => localStorage.clear());
  await page.route('**/api/events**', (route) => route.abort());
  await page.route('**/api/sync**', (route) => route.abort());
  await page.goto('/admin');
  await page.waitForFunction(() => window.state?.mounts?.some((mount) => mount.id === 'mount-0'));
  await page.evaluate(() => {
    window.state.autoSave = false;
    openFile('/mermaid-fullscreen.md', 'mount-0');
  });
  await page.waitForFunction(() => window.state?.currentPath === '/mermaid-fullscreen.md');
  await page.waitForSelector('.vditor-ir');
  await page.evaluate((value) => window._vditor.setValue(value), markdown);
  await expect.poll(async () => (await page.evaluate(() => window._vditor.getValue().replace(/\n+$/, '')))).toBe(
    markdown,
  );
  await expect.poll(async () => page.locator('.vditor-ir__preview svg').count()).toBe(1);
  await expect.poll(async () => page.locator('.mme-overlay-item').count()).toBe(1);
}

function fullscreenButton(page) {
  return page.locator('.mme-overlay-item .mme-toolbar [data-action="toggleFullscreen"]');
}

test('Mermaid fallback fullscreen keeps the chart and existing controls usable', async ({ page }) => {
  await prepareEditor(page);
  await page.evaluate(() => {
    document.documentElement.requestFullscreen = () => Promise.reject(new Error('fullscreen unavailable'));
  });

  const originalValue = await page.evaluate(() => window._vditor.getValue().replace(/\n+$/, ''));
  await fullscreenButton(page).click();
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('body')).toHaveClass(/mme-app-fullscreen/);
  await expect(page.locator('.language-mermaid[data-mme-fullscreen="true"]')).toBeVisible();
  await expect.poll(async () => page.locator('.vditor-ir__preview svg').count()).toBe(1);

  const codeArea = page.locator('.mme-code-area').first();
  await page.locator('[data-action="showCode"]').first().click();
  await expect(codeArea).toBeVisible();
  await expect(fullscreenButton(page)).toHaveAttribute('title', '退出全屏');
  await page.locator('[data-action="showChart"]').first().click();
  const fullscreenScaleBeforeZoom = await page.evaluate(() => {
    const svg = document.querySelector('.language-mermaid[data-mme-fullscreen="true"] svg');
    return Number(svg.style.transform.match(/scale\(([^)]+)\)/)[1]);
  });
  await page.locator('[data-action="zoomIn"]').first().click();
  await expect.poll(async () => page.evaluate(() => {
    const svg = document.querySelector('.language-mermaid[data-mme-fullscreen="true"] svg');
    return Number(svg.style.transform.match(/scale\(([^)]+)\)/)[1]);
  })).toBeGreaterThan(fullscreenScaleBeforeZoom);
  await page.locator('[data-action="toggleTheme"]').first().click();
  await expect(page.locator('.language-mermaid svg').last()).toHaveAttribute('style', /invert/);

  await page.keyboard.press('Escape');
  await expect(page.locator('html')).not.toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('body')).not.toHaveClass(/mme-app-fullscreen/);
  await expect(page.locator('.language-mermaid[data-mme-fullscreen="true"]')).toHaveCount(0);
  expect(await page.evaluate(() => window._vditor.getValue().replace(/\n+$/, ''))).toBe(originalValue);
});

test('Mermaid prefers native fullscreen and clears state on fullscreenchange', async ({ page }) => {
  await prepareEditor(page);
  await page.evaluate(() => {
    let fakeFullscreenElement = null;
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => fakeFullscreenElement,
    });
    document.documentElement.requestFullscreen = async () => {
      fakeFullscreenElement = document.documentElement;
    };
    document.exitFullscreen = async () => {
      fakeFullscreenElement = null;
    };
    window.clearFakeFullscreen = () => {
      fakeFullscreenElement = null;
      document.dispatchEvent(new Event('fullscreenchange'));
    };
  });

  await fullscreenButton(page).click();
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('body')).not.toHaveClass(/mme-app-fullscreen/);
  await expect(page.locator('.language-mermaid[data-mme-fullscreen="true"]')).toBeVisible();

  await page.evaluate(() => window.clearFakeFullscreen());
  await expect(page.locator('html')).not.toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('.language-mermaid[data-mme-fullscreen="true"]')).toHaveCount(0);
});

test('Mermaid fullscreen layout fits a mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await prepareEditor(page);
  await page.evaluate(() => {
    document.documentElement.requestFullscreen = () => Promise.reject(new Error('fullscreen unavailable'));
  });
  await fullscreenButton(page).click();
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await expect.poll(async () => page.locator('.mme-toolbar').first().boundingBox()).not.toBeNull();
  await expect.poll(async () => page.locator('.language-mermaid svg').last().boundingBox()).not.toBeNull();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});

test('Mermaid normal zoom keeps the chart center stable', async ({ page }) => {
  await prepareEditor(page);

  const centerBeforeZoom = await page.evaluate(() => {
    const rect = document.querySelector('.language-mermaid[data-mme-enhanced] svg').getBoundingClientRect();
    return { x: (rect.left + rect.right) / 2, y: (rect.top + rect.bottom) / 2 };
  });
  await page.locator('[data-action="zoomIn"]').first().click();
  await page.waitForTimeout(300);
  const centerAfterZoom = await page.evaluate(() => {
    const rect = document.querySelector('.language-mermaid[data-mme-enhanced] svg').getBoundingClientRect();
    return { x: (rect.left + rect.right) / 2, y: (rect.top + rect.bottom) / 2 };
  });
  expect(Math.abs(centerAfterZoom.x - centerBeforeZoom.x)).toBeLessThan(2);
  expect(Math.abs(centerAfterZoom.y - centerBeforeZoom.y)).toBeLessThan(2);
});

test('Fullscreen does not pollute Mermaid Undo and Redo', async ({ page }) => {
  await prepareEditor(page);
  await page.evaluate(() => {
    document.documentElement.requestFullscreen = () => Promise.reject(new Error('fullscreen unavailable'));
  });

  const originalValue = await page.evaluate(() => window._vditor.getValue().replace(/\n+$/, ''));
  const baselineSnapshot = await page.evaluate(() => window._vditor.vditor.undo.addCaret(window._vditor.vditor));
  const editedValue = `${originalValue}!`;
  await page.evaluate((value) => window._vditor.setValue(value), editedValue);
  await expect.poll(async () => page.evaluate(() => window._vditor.getValue())).toContain('After the diagram!');
  await expect.poll(async () => page.locator('.vditor-ir__preview svg').count()).toBe(1);
  await fullscreenButton(page).click();
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);

  await page.evaluate((baseline) => {
    const vditor = window._vditor.vditor;
    const current = vditor.undo.addCaret(vditor);
    window.fullscreenUndoPatch = vditor.undo.dmp.patch_make(current, baseline);
    vditor.undo.ir.lastText = current;
    vditor.undo.renderDiff(window.fullscreenUndoPatch, vditor, false);
  }, baselineSnapshot);
  await expect.poll(async () => page.evaluate(() => window._vditor.getValue().replace(/\n+$/, ''))).toBe(
    originalValue,
  );
  await expect.poll(async () => page.locator('.vditor-ir__preview svg').count()).toBe(1);
  expect(await page.locator('.vditor-ir .vditor-wysiwyg__block').count()).toBe(0);

  await page.evaluate(() => {
    const vditor = window._vditor.vditor;
    vditor.undo.renderDiff(window.fullscreenUndoPatch, vditor, true);
  });
  await expect.poll(async () => page.evaluate(() => window._vditor.getValue())).toContain('After the diagram!');
  await expect.poll(async () => page.locator('.vditor-ir__preview svg').count()).toBe(1);
  expect(await page.locator('.vditor-ir .vditor-wysiwyg__block').count()).toBe(0);
});

test('Fullscreen removes a legacy inline Mermaid toolbar', async ({ page }) => {
  await prepareEditor(page);
  await page.evaluate(() => {
    const editor = document.querySelector('.vditor-ir');
    const legacyToolbar = document.createElement('div');
    legacyToolbar.className = 'mme-toolbar';
    legacyToolbar.setAttribute('data-mme-id', 'legacy-toolbar');
    const legacyCodeArea = document.createElement('div');
    legacyCodeArea.className = 'mme-code-area';
    editor.append(legacyToolbar, legacyCodeArea);
    document.documentElement.requestFullscreen = () => Promise.reject(new Error('fullscreen unavailable'));
  });

  await fullscreenButton(page).click();
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('.mme-overlay-item .mme-toolbar')).toHaveCount(1);
  await expect(page.locator('.mme-toolbar')).toHaveCount(1);
  await expect(page.locator('.mme-code-area')).toHaveCount(1);
});

test('Fullscreen hides other Mermaid toolbars in the same document', async ({ page }) => {
  await prepareEditor(page);
  await page.evaluate((value) => window._vditor.setValue(value), twoMermaidMarkdown);
  await expect.poll(async () => page.locator('.vditor-ir__preview svg').count()).toBe(2);
  await expect.poll(async () => page.locator('.mme-overlay-item').count()).toBe(2);
  await page.evaluate(() => {
    document.documentElement.requestFullscreen = () => Promise.reject(new Error('fullscreen unavailable'));
  });

  await fullscreenButton(page).first().click();
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('.mme-overlay-item:visible')).toHaveCount(1);
  await expect(page.locator('.mme-overlay-item[data-mme-fullscreen="true"]')).toHaveCount(1);
  await expect(page.locator('.mme-overlay-item:not([data-mme-fullscreen="true"])')).toBeHidden();
});

test('Exiting fullscreen restores the chart transform from before fullscreen', async ({ page }) => {
  await prepareEditor(page);
  await page.evaluate(() => {
    document.documentElement.requestFullscreen = () => Promise.reject(new Error('fullscreen unavailable'));
  });

  const before = await page.evaluate(() => {
    const target = document.querySelector('.language-mermaid[data-mme-enhanced]');
    const svg = target.querySelector('svg');
    return {
      transform: svg.style.transform,
      transformOrigin: svg.style.transformOrigin,
      targetRect: target.getBoundingClientRect().toJSON(),
    };
  });

  await fullscreenButton(page).click();
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await page.locator('[data-action="zoomIn"]').first().click();
  await page.locator('[data-action="zoomIn"]').first().click();

  const chart = page.locator('.language-mermaid[data-mme-enhanced]').last();
  const box = await chart.boundingBox();
  const beforeDrag = await page.evaluate(() => {
    const transform = document.querySelector('.language-mermaid[data-mme-fullscreen="true"] svg').style.transform;
    const match = transform.match(/translate3d\(([-\d.]+)px, ([-\d.]+)px/);
    return { x: Number(match[1]), y: Number(match[2]) };
  });
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 450, box.y + box.height / 2 + 280, { steps: 5 });
  await page.mouse.up();
  const afterDrag = await page.evaluate(() => {
    const transform = document.querySelector('.language-mermaid[data-mme-fullscreen="true"] svg').style.transform;
    const match = transform.match(/translate3d\(([-\d.]+)px, ([-\d.]+)px/);
    return { x: Number(match[1]), y: Number(match[2]) };
  });
  expect(afterDrag.x).toBeCloseTo(beforeDrag.x + 450, 0);
  expect(afterDrag.y).toBeCloseTo(beforeDrag.y + 280, 0);

  await fullscreenButton(page).click();
  await expect(page.locator('html')).not.toHaveClass(/mme-fullscreen-active/);
  await page.waitForTimeout(100);

  const after = await page.evaluate(() => {
    const target = document.querySelector('.language-mermaid[data-mme-enhanced]');
    const svg = target.querySelector('svg');
    return {
      transform: svg.style.transform,
      transformOrigin: svg.style.transformOrigin,
      targetRect: target.getBoundingClientRect().toJSON(),
      svgRect: svg.getBoundingClientRect().toJSON(),
    };
  });
  expect(after.transform).toBe(before.transform);
  expect(after.transformOrigin).toBe(before.transformOrigin);
  expect(after.svgRect.left).toBeGreaterThanOrEqual(after.targetRect.left - 1);
  expect(after.svgRect.left).toBeLessThan(after.targetRect.right);
  expect(after.svgRect.top).toBeGreaterThanOrEqual(after.targetRect.top - 1);
});

test('Entering fullscreen resets an existing normal chart transform', async ({ page }) => {
  await prepareEditor(page);
  await page.evaluate(() => {
    document.documentElement.requestFullscreen = () => Promise.reject(new Error('fullscreen unavailable'));
  });

  await page.locator('[data-action="zoomIn"]').first().click();
  await page.locator('[data-action="zoomIn"]').first().click();
  const chart = page.locator('.language-mermaid[data-mme-enhanced]').last();
  const box = await chart.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 450, box.y + box.height / 2 + 280, { steps: 5 });
  await page.mouse.up();
  await expect(page.locator('.language-mermaid svg').last()).toHaveAttribute('style', /scale\(1\.5\)/);

  await fullscreenButton(page).click();
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await expect.poll(async () => page.evaluate(() => {
    const svg = document.querySelector('.language-mermaid[data-mme-fullscreen="true"] svg');
    const match = svg?.style.transform.match(/scale\(([^)]+)\)/);
    return match ? Number(match[1]) : NaN;
  })).toBeLessThan(1);
  await expect.poll(async () => page.evaluate(() => {
    const svg = document.querySelector('.language-mermaid[data-mme-fullscreen="true"] svg');
    const match = svg?.style.transform.match(/scale\(([^)]+)\)/);
    return match ? Number(match[1]) : NaN;
  })).toBeGreaterThan(0);

  const initialFullscreenView = await page.evaluate(() => {
    const target = document.querySelector('.language-mermaid[data-mme-fullscreen="true"]');
    const svg = target.querySelector('svg');
    return { target: target.getBoundingClientRect().toJSON(), svg: svg.getBoundingClientRect().toJSON() };
  });
  expect(initialFullscreenView.svg.left).toBeGreaterThanOrEqual(initialFullscreenView.target.left - 1);
  expect(initialFullscreenView.svg.top).toBeGreaterThanOrEqual(initialFullscreenView.target.top - 1);
  expect(initialFullscreenView.svg.right).toBeLessThanOrEqual(initialFullscreenView.target.right + 1);
  expect(initialFullscreenView.svg.bottom).toBeLessThanOrEqual(initialFullscreenView.target.bottom + 1);

  const centerBeforeZoom = await page.evaluate(() => {
    const rect = document.querySelector('.language-mermaid[data-mme-fullscreen="true"] svg').getBoundingClientRect();
    return { x: (rect.left + rect.right) / 2, y: (rect.top + rect.bottom) / 2 };
  });
  await page.locator('[data-action="zoomIn"]').first().click();
  await page.waitForTimeout(300);
  const centerAfterZoom = await page.evaluate(() => {
    const rect = document.querySelector('.language-mermaid[data-mme-fullscreen="true"] svg').getBoundingClientRect();
    return { x: (rect.left + rect.right) / 2, y: (rect.top + rect.bottom) / 2 };
  });
  expect(Math.abs(centerAfterZoom.x - centerBeforeZoom.x)).toBeLessThan(2);
  expect(Math.abs(centerAfterZoom.y - centerBeforeZoom.y)).toBeLessThan(2);

});
