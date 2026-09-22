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
  await expect
    .poll(async () => await page.evaluate(() => window._vditor.getValue().replace(/\n+$/, '')))
    .toBe(markdown);
  await expect.poll(async () => page.locator('.vditor-ir__preview svg').count()).toBe(1);
  await expect.poll(async () => page.locator('.mme-overlay-item').count()).toBe(1);
}

function fullscreenButton(page) {
  return page.locator('.mme-overlay-item .mme-toolbar [data-action="toggleFullscreen"]');
}

async function rejectNativeFullscreen(page) {
  await page.evaluate(() => {
    const overlay = document.querySelector('.mme-overlay-item');
    overlay.requestFullscreen = () => Promise.reject(new Error('fullscreen unavailable'));
  });
}

async function installNativeFullscreenStub(page) {
  await page.evaluate(() => {
    let fakeFullscreenElement = null;
    const requests = [];
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => fakeFullscreenElement,
    });
    const overlay = document.querySelector('.mme-overlay-item');
    overlay.requestFullscreen = async function () {
      requests.push(this);
      fakeFullscreenElement = this;
    };
    document.exitFullscreen = async () => {
      fakeFullscreenElement = null;
    };
    window.nativeFullscreenStub = {
      clear() {
        fakeFullscreenElement = null;
        document.dispatchEvent(new Event('fullscreenchange'));
      },
      requests,
    };
  });
}

test('Mermaid fallback fullscreen keeps the chart and existing controls usable', async ({
  page,
}) => {
  await prepareEditor(page);
  await rejectNativeFullscreen(page);

  const originalValue = await page.evaluate(() => window._vditor.getValue().replace(/\n+$/, ''));
  await fullscreenButton(page).click();
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('body')).toHaveClass(/mme-app-fullscreen/);
  await expect(page.locator('.mme-fullscreen-chart')).toHaveCount(0);
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
  await expect
    .poll(async () =>
      page.evaluate(() => {
        const svg = document.querySelector('.language-mermaid[data-mme-fullscreen="true"] svg');
        return Number(svg.style.transform.match(/scale\(([^)]+)\)/)[1]);
      }),
    )
    .toBeGreaterThan(fullscreenScaleBeforeZoom);
  await page.locator('[data-action="toggleTheme"]').first().click();
  await expect(page.locator('.language-mermaid svg').last()).toHaveAttribute('style', /invert/);

  await page.keyboard.press('Escape');
  await expect(page.locator('html')).not.toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('body')).not.toHaveClass(/mme-app-fullscreen/);
  await expect(page.locator('.language-mermaid[data-mme-fullscreen="true"]')).toHaveCount(0);
  expect(await page.evaluate(() => window._vditor.getValue().replace(/\n+$/, ''))).toBe(
    originalValue,
  );
});

test('Mermaid native fullscreen owns a cloned chart and the active controls', async ({ page }) => {
  await prepareEditor(page);
  await installNativeFullscreenStub(page);

  await fullscreenButton(page).click();
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('body')).not.toHaveClass(/mme-app-fullscreen/);
  const activeOverlay = page.locator('.mme-overlay-item[data-mme-fullscreen="true"]');
  await expect(activeOverlay).toBeVisible();
  await expect(activeOverlay.locator('.mme-fullscreen-chart svg')).toBeVisible();
  await expect(activeOverlay.locator('.mme-toolbar')).toBeVisible();
  await expect(page.locator('.vditor-ir__preview .mme-fullscreen-chart')).toHaveCount(0);
  expect(
    await page.evaluate(() => {
      const requestTarget = window.nativeFullscreenStub.requests[0];
      return {
        count: window.nativeFullscreenStub.requests.length,
        isOverlay: requestTarget?.matches('.mme-overlay-item') || false,
        ownsChart: !!requestTarget?.querySelector('.mme-fullscreen-chart svg'),
        ownsControls: !!requestTarget?.querySelector(
          '.mme-toolbar [data-action="toggleFullscreen"]',
        ),
      };
    }),
  ).toEqual({ count: 1, isOverlay: true, ownsChart: true, ownsControls: true });

  await page.evaluate(() => window.nativeFullscreenStub.clear());
  await expect(page.locator('html')).not.toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('.mme-fullscreen-chart')).toHaveCount(0);
  await expect(page.locator('.language-mermaid[data-mme-fullscreen="true"]')).toHaveCount(0);
});

test('Mermaid native fullscreen keeps an ordinary chart centered inside the visible chart area', async ({
  page,
}) => {
  await prepareEditor(page);
  await installNativeFullscreenStub(page);

  await fullscreenButton(page).click();
  await expect(page.locator('.mme-fullscreen-chart svg')).toBeVisible();
  const geometry = await page.evaluate(() => {
    const chart = document.querySelector('.mme-fullscreen-chart');
    const svg = chart.querySelector('svg');
    const chartRect = chart.getBoundingClientRect();
    const svgRect = svg.getBoundingClientRect();
    return {
      chart: { left: chartRect.left, right: chartRect.right, width: chartRect.width },
      svg: { left: svgRect.left, right: svgRect.right, width: svgRect.width },
    };
  });

  expect(geometry.svg.left).toBeGreaterThanOrEqual(geometry.chart.left - 1);
  expect(geometry.svg.right).toBeLessThanOrEqual(geometry.chart.right + 1);
  expect(geometry.svg.width).toBeGreaterThan(100);
  expect(
    Math.abs(
      (geometry.svg.left + geometry.svg.right) / 2 -
        (geometry.chart.left + geometry.chart.right) / 2,
    ),
  ).toBeLessThan(2);
});

test('Mermaid native fullscreen overrides inline SVG limits before fitting a large chart', async ({
  page,
}) => {
  await prepareEditor(page);
  await page.evaluate(() => {
    const svg = document.querySelector('.language-mermaid[data-mme-enhanced] svg');
    svg.style.width = '2400px';
    svg.style.height = '1600px';
    svg.style.maxWidth = '17px';
  });
  await installNativeFullscreenStub(page);

  await fullscreenButton(page).click();
  await expect(page.locator('.mme-fullscreen-chart svg')).toBeVisible();
  const geometry = await page.evaluate(() => {
    const chart = document.querySelector('.mme-fullscreen-chart');
    const svg = chart.querySelector('svg');
    const chartRect = chart.getBoundingClientRect();
    const svgRect = svg.getBoundingClientRect();
    return {
      chart: {
        bottom: chartRect.bottom,
        height: chartRect.height,
        left: chartRect.left,
        right: chartRect.right,
        top: chartRect.top,
        width: chartRect.width,
      },
      computedMaxWidth: getComputedStyle(svg).maxWidth,
      svg: {
        bottom: svgRect.bottom,
        height: svgRect.height,
        left: svgRect.left,
        right: svgRect.right,
        top: svgRect.top,
        width: svgRect.width,
      },
    };
  });

  expect(geometry.computedMaxWidth).toBe('none');
  expect(geometry.svg.left).toBeGreaterThanOrEqual(geometry.chart.left - 1);
  expect(geometry.svg.right).toBeLessThanOrEqual(geometry.chart.right + 1);
  expect(geometry.svg.top).toBeGreaterThanOrEqual(geometry.chart.top - 1);
  expect(geometry.svg.bottom).toBeLessThanOrEqual(geometry.chart.bottom + 1);
  expect(geometry.svg.width).toBeGreaterThan(geometry.chart.width * 0.5);
  expect(
    Math.abs(
      (geometry.svg.left + geometry.svg.right) / 2 -
        (geometry.chart.left + geometry.chart.right) / 2,
    ),
  ).toBeLessThan(2);
});

test('Mermaid native fullscreen preserves state after exit rejection and allows retry', async ({
  page,
}) => {
  await prepareEditor(page);
  await page.evaluate(() => {
    let fakeFullscreenElement = null;
    let rejectExit = true;
    window.nativeRejectedExitCalls = 0;
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => fakeFullscreenElement,
    });
    const overlay = document.querySelector('.mme-overlay-item');
    overlay.requestFullscreen = async function () {
      fakeFullscreenElement = this;
    };
    document.exitFullscreen = async () => {
      window.nativeRejectedExitCalls += 1;
      if (rejectExit) throw new Error('native exit rejected');
      fakeFullscreenElement = null;
    };
    window.allowNativeExitRetry = () => {
      rejectExit = false;
    };
  });

  await fullscreenButton(page).click();
  await expect(page.locator('.mme-fullscreen-chart svg')).toBeVisible();
  await fullscreenButton(page).click();
  await expect.poll(async () => page.evaluate(() => window.nativeRejectedExitCalls)).toBe(1);

  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('.mme-overlay-item[data-mme-fullscreen="true"]')).toHaveCount(1);
  await expect(page.locator('.mme-fullscreen-chart svg')).toBeVisible();
  await expect(fullscreenButton(page)).toHaveAttribute('title', '退出全屏');

  await page.evaluate(() => window.allowNativeExitRetry());
  await fullscreenButton(page).click();
  await expect.poll(async () => page.evaluate(() => window.nativeRejectedExitCalls)).toBe(2);
  await expect(page.locator('html')).not.toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('.mme-fullscreen-chart')).toHaveCount(0);
});

test('Mermaid native fullscreen clears preserved state when browser Escape exits', async ({
  page,
}) => {
  await prepareEditor(page);
  await page.evaluate(() => {
    let fakeFullscreenElement = null;
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => fakeFullscreenElement,
    });
    const overlay = document.querySelector('.mme-overlay-item');
    overlay.requestFullscreen = async function () {
      fakeFullscreenElement = this;
    };
    document.exitFullscreen = async () => {
      throw new Error('native exit rejected');
    };
    window.simulateNativeEscape = () => {
      fakeFullscreenElement = null;
      document.dispatchEvent(new Event('fullscreenchange'));
    };
  });

  await fullscreenButton(page).click();
  await fullscreenButton(page).click();
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await page.evaluate(() => window.simulateNativeEscape());

  await expect(page.locator('html')).not.toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('.mme-fullscreen-chart')).toHaveCount(0);
});

test('Mermaid aborts a block switch when the old native fullscreen cannot exit', async ({
  page,
}) => {
  await prepareEditor(page);
  await page.evaluate((value) => window._vditor.setValue(value), twoMermaidMarkdown);
  await expect.poll(async () => page.locator('.mme-overlay-item').count()).toBe(2);
  await page.evaluate(() => {
    let fakeFullscreenElement = null;
    window.rejectedSwitchEvents = [];
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => fakeFullscreenElement,
    });
    const overlays = document.querySelectorAll('.mme-overlay-item');
    overlays[0].requestFullscreen = async function () {
      window.rejectedSwitchEvents.push('request-a');
      fakeFullscreenElement = this;
    };
    overlays[1].requestFullscreen = async function () {
      window.rejectedSwitchEvents.push('request-b');
      fakeFullscreenElement = this;
    };
    document.exitFullscreen = async () => {
      window.rejectedSwitchEvents.push('reject-exit-a');
      throw new Error('native exit rejected');
    };
  });

  await fullscreenButton(page).first().click();
  await expect
    .poll(async () => page.evaluate(() => window.rejectedSwitchEvents))
    .toEqual(['request-a']);
  await page.evaluate(() => {
    document
      .querySelectorAll('.mme-overlay-item .mme-toolbar [data-action="toggleFullscreen"]')[1]
      .click();
  });

  await expect
    .poll(async () => page.evaluate(() => window.rejectedSwitchEvents))
    .toEqual(['request-a', 'reject-exit-a']);
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('.mme-overlay-item[data-mme-fullscreen="true"]')).toHaveAttribute(
    'data-mme-id',
    await page.locator('.mme-overlay-item').first().getAttribute('data-mme-id'),
  );
  await expect(page.locator('.mme-fullscreen-chart')).toHaveCount(1);
  await expect(page.locator('body')).not.toHaveClass(/mme-app-fullscreen/);
});

test('Mermaid source removal exits native fullscreen before clearing overlay state', async ({
  page,
}) => {
  await prepareEditor(page);
  await page.evaluate(() => {
    let fakeFullscreenElement = null;
    let finishExit;
    window.nativeExitEvents = [];
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => fakeFullscreenElement,
    });
    const overlay = document.querySelector('.mme-overlay-item');
    overlay.requestFullscreen = async function () {
      fakeFullscreenElement = this;
      window.nativeExitEvents.push('request');
    };
    document.exitFullscreen = () => {
      window.nativeExitEvents.push('exit');
      return new Promise((resolve) => {
        finishExit = () => {
          fakeFullscreenElement = null;
          resolve();
        };
      });
    };
    window.finishNativeExit = () => finishExit();
  });

  await fullscreenButton(page).click();
  await expect(page.locator('.mme-fullscreen-chart svg')).toBeVisible();
  await page.evaluate(() =>
    document.querySelector('.language-mermaid[data-mme-enhanced]').remove(),
  );

  await expect
    .poll(async () => page.evaluate(() => window.nativeExitEvents))
    .toEqual(['request', 'exit']);
  await expect(page.locator('.mme-overlay-item[data-mme-fullscreen="true"]')).toHaveCount(1);
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);

  await page.evaluate(() => window.finishNativeExit());
  await expect(page.locator('.mme-overlay-item')).toHaveCount(0);
  await expect(page.locator('.mme-fullscreen-chart')).toHaveCount(0);
  await expect(page.locator('html')).not.toHaveClass(/mme-fullscreen-active/);
});

test('Mermaid source removal waits for a pending native fullscreen request before cleanup', async ({
  page,
}) => {
  await prepareEditor(page);
  await page.evaluate(() => {
    let fakeFullscreenElement = null;
    let finishRequest;
    window.pendingNativeEvents = [];
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => fakeFullscreenElement,
    });
    const overlay = document.querySelector('.mme-overlay-item');
    overlay.requestFullscreen = function () {
      window.pendingNativeEvents.push('request');
      return new Promise((resolve) => {
        finishRequest = () => {
          fakeFullscreenElement = overlay;
          window.pendingNativeEvents.push('resolved');
          resolve();
        };
      });
    };
    document.exitFullscreen = async () => {
      window.pendingNativeEvents.push('exit');
      fakeFullscreenElement = null;
    };
    window.finishPendingNativeRequest = () => finishRequest();
  });

  await fullscreenButton(page).click();
  await expect
    .poll(async () => page.evaluate(() => window.pendingNativeEvents))
    .toEqual(['request']);
  await page.evaluate(() =>
    document.querySelector('.language-mermaid[data-mme-enhanced]').remove(),
  );
  await page.waitForTimeout(50);
  await expect(page.locator('.mme-overlay-item')).toHaveCount(1);
  await expect(page.locator('.mme-fullscreen-chart')).toHaveCount(1);

  await page.evaluate(() => window.finishPendingNativeRequest());
  await expect
    .poll(async () => page.evaluate(() => window.pendingNativeEvents))
    .toEqual(['request', 'resolved', 'exit']);
  await expect(page.locator('.mme-overlay-item')).toHaveCount(0);
  await expect(page.locator('.mme-fullscreen-chart')).toHaveCount(0);
  await expect(page.locator('html')).not.toHaveClass(/mme-fullscreen-active/);
});

test('Mermaid native fullscreen cancels one pending request without starting another', async ({
  page,
}) => {
  await prepareEditor(page);
  await page.evaluate(() => {
    let fakeFullscreenElement = null;
    let finishRequest;
    window.pendingNativeRequestCount = 0;
    window.pendingNativeExitCount = 0;
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => fakeFullscreenElement,
    });
    const overlay = document.querySelector('.mme-overlay-item');
    overlay.requestFullscreen = function () {
      window.pendingNativeRequestCount += 1;
      return new Promise((resolve) => {
        finishRequest = () => {
          fakeFullscreenElement = overlay;
          resolve();
        };
      });
    };
    document.exitFullscreen = async () => {
      window.pendingNativeExitCount += 1;
      fakeFullscreenElement = null;
    };
    window.finishPendingNativeRequest = () => finishRequest();
  });

  await fullscreenButton(page).click();
  await expect.poll(async () => page.evaluate(() => window.pendingNativeRequestCount)).toBe(1);
  await fullscreenButton(page).click();
  await page.waitForTimeout(50);
  expect(await page.evaluate(() => window.pendingNativeRequestCount)).toBe(1);
  await expect(page.locator('.mme-fullscreen-chart')).toHaveCount(1);

  await page.evaluate(() => window.finishPendingNativeRequest());
  await expect.poll(async () => page.evaluate(() => window.pendingNativeExitCount)).toBe(1);
  await expect(page.locator('.mme-fullscreen-chart')).toHaveCount(0);
  await expect(page.locator('html')).not.toHaveClass(/mme-fullscreen-active/);
});

test('Mermaid cancels a target entry while the previous native fullscreen is exiting', async ({
  page,
}) => {
  await prepareEditor(page);
  await page.evaluate((value) => window._vditor.setValue(value), twoMermaidMarkdown);
  await expect.poll(async () => page.locator('.mme-overlay-item').count()).toBe(2);
  await page.evaluate(() => {
    let fakeFullscreenElement = null;
    let finishExit;
    const exitPromise = new Promise((resolve) => {
      finishExit = () => {
        fakeFullscreenElement = null;
        window.switchNativeEvents.push('exit-resolved');
        resolve();
      };
    });
    window.switchNativeEvents = [];
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => fakeFullscreenElement,
    });
    const overlays = document.querySelectorAll('.mme-overlay-item');
    overlays[0].requestFullscreen = async function () {
      window.switchNativeEvents.push('request-a');
      fakeFullscreenElement = this;
    };
    overlays[1].requestFullscreen = async function () {
      window.switchNativeEvents.push('request-b');
      fakeFullscreenElement = this;
    };
    document.exitFullscreen = () => {
      window.switchNativeEvents.push('exit-a');
      return exitPromise;
    };
    window.finishSwitchNativeExit = finishExit;
  });

  await fullscreenButton(page).first().click();
  await expect
    .poll(async () => page.evaluate(() => window.switchNativeEvents))
    .toEqual(['request-a']);
  await page.evaluate(() => {
    const button = document.querySelectorAll(
      '.mme-overlay-item .mme-toolbar [data-action="toggleFullscreen"]',
    )[1];
    button.click();
    button.click();
  });

  await expect
    .poll(async () =>
      page.evaluate(() => window.switchNativeEvents.filter((event) => event === 'exit-a').length),
    )
    .toBe(1);
  await page.evaluate(() => window.finishSwitchNativeExit());
  await expect
    .poll(async () => page.evaluate(() => window.switchNativeEvents))
    .toEqual(['request-a', 'exit-a', 'exit-resolved']);
  await expect(page.locator('.mme-fullscreen-chart')).toHaveCount(0);
  await expect(page.locator('html')).not.toHaveClass(/mme-fullscreen-active/);
});

test('Mermaid does not enter fullscreen after the waiting target is removed', async ({ page }) => {
  await prepareEditor(page);
  await page.evaluate((value) => window._vditor.setValue(value), twoMermaidMarkdown);
  await expect.poll(async () => page.locator('.mme-overlay-item').count()).toBe(2);
  await page.evaluate(() => {
    let fakeFullscreenElement = null;
    let finishExit;
    window.removedTargetEvents = [];
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => fakeFullscreenElement,
    });
    const overlays = document.querySelectorAll('.mme-overlay-item');
    overlays[0].requestFullscreen = async function () {
      window.removedTargetEvents.push('request-a');
      fakeFullscreenElement = this;
    };
    overlays[1].requestFullscreen = async () => {
      window.removedTargetEvents.push('request-b');
      throw new Error('target removed');
    };
    document.exitFullscreen = () => {
      window.removedTargetEvents.push('exit-a');
      return new Promise((resolve) => {
        finishExit = () => {
          fakeFullscreenElement = null;
          window.removedTargetEvents.push('exit-resolved');
          resolve();
        };
      });
    };
    window.finishRemovedTargetExit = () => finishExit();
  });

  await fullscreenButton(page).first().click();
  await expect
    .poll(async () => page.evaluate(() => window.removedTargetEvents))
    .toEqual(['request-a']);
  await page.evaluate(() => {
    document
      .querySelectorAll('.mme-overlay-item .mme-toolbar [data-action="toggleFullscreen"]')[1]
      .click();
  });
  await expect
    .poll(async () => page.evaluate(() => window.removedTargetEvents))
    .toEqual(['request-a', 'exit-a']);
  await page.evaluate(() =>
    document.querySelectorAll('.language-mermaid[data-mme-enhanced]')[1].remove(),
  );
  await expect(page.locator('.mme-overlay-item')).toHaveCount(1);

  await page.evaluate(() => window.finishRemovedTargetExit());
  await expect
    .poll(async () => page.evaluate(() => window.removedTargetEvents))
    .toEqual(['request-a', 'exit-a', 'exit-resolved']);
  await expect(page.locator('.mme-fullscreen-chart')).toHaveCount(0);
  await expect(page.locator('html')).not.toHaveClass(/mme-fullscreen-active/);
});

test('Mermaid native fullscreen ignores stale cleanup after a newer session starts', async ({
  page,
}) => {
  await prepareEditor(page);
  await page.evaluate(() => {
    let fakeFullscreenElement = null;
    let resolveOldExit;
    window.nativeRequestCount = 0;
    window.nativeExitCount = 0;
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => fakeFullscreenElement,
    });
    const overlay = document.querySelector('.mme-overlay-item');
    overlay.requestFullscreen = async function () {
      window.nativeRequestCount += 1;
      fakeFullscreenElement = this;
    };
    document.exitFullscreen = () => {
      window.nativeExitCount += 1;
      return new Promise((resolve) => {
        resolveOldExit = resolve;
      });
    };
    window.finishOldNativeExit = () => resolveOldExit();
    window.dispatchNativeExit = () => {
      fakeFullscreenElement = null;
      document.dispatchEvent(new Event('fullscreenchange'));
    };
  });

  await fullscreenButton(page).click();
  await expect.poll(async () => page.evaluate(() => window.nativeRequestCount)).toBe(1);
  await fullscreenButton(page).click();
  await expect.poll(async () => page.evaluate(() => window.nativeExitCount)).toBe(1);
  await page.evaluate(() => window.dispatchNativeExit());
  await expect(page.locator('html')).not.toHaveClass(/mme-fullscreen-active/);

  await fullscreenButton(page).click();
  await expect.poll(async () => page.evaluate(() => window.nativeRequestCount)).toBe(2);
  await expect(page.locator('.mme-fullscreen-chart svg')).toBeVisible();
  await page.evaluate(() => window.finishOldNativeExit());
  await page.waitForTimeout(0);

  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('.mme-fullscreen-chart svg')).toBeVisible();
  await expect(fullscreenButton(page)).toHaveAttribute('title', '退出全屏');
});

test('Mermaid native fullscreen controls use the clone and restore the prior view', async ({
  page,
}) => {
  await prepareEditor(page);

  await page.locator('[data-action="zoomIn"]').click();
  await page.evaluate(() => {
    const target = document.querySelector('.language-mermaid[data-mme-enhanced]');
    target.dispatchEvent(
      new MouseEvent('mousedown', { bubbles: true, button: 0, clientX: 20, clientY: 20 }),
    );
    document.dispatchEvent(
      new MouseEvent('mousemove', { bubbles: true, clientX: 85, clientY: 60 }),
    );
    document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
  });
  await page.locator('[data-action="toggleTheme"]').click();
  await page.locator('[data-action="showCode"]').click();
  const sourceBefore = await page.evaluate(() => {
    const svg = document.querySelector('.language-mermaid[data-mme-enhanced] svg');
    return {
      filter: svg.style.filter,
      opacity: svg.style.opacity,
      transform: svg.style.transform,
      transformOrigin: svg.style.transformOrigin,
    };
  });
  expect(sourceBefore.filter).toContain('invert');
  expect(sourceBefore.opacity).toBe('0');

  await installNativeFullscreenStub(page);
  await fullscreenButton(page).click();
  await expect(page.locator('.mme-fullscreen-chart svg')).toHaveCount(1);
  await expect(page.locator('.mme-fullscreen-chart')).toBeHidden();
  await expect(page.locator('.mme-code-area')).toBeVisible();
  await page.locator('[data-action="showChart"]').click();
  await expect(page.locator('.mme-fullscreen-chart')).toBeVisible();
  await expect(page.locator('.mme-fullscreen-chart svg')).toHaveCSS('opacity', '1');
  await page.locator('[data-action="toggleTheme"]').click();
  await page.locator('[data-action="zoomIn"]').click();
  await page.evaluate(() => {
    const sourceSvg = document.querySelector('.language-mermaid[data-mme-enhanced] svg');
    const fullscreenSvg = document.querySelector('.mme-fullscreen-chart svg');
    sourceSvg.setAttribute('data-download-source', 'source');
    fullscreenSvg.setAttribute('data-download-source', 'fullscreen');
    const originalSerialize = XMLSerializer.prototype.serializeToString;
    XMLSerializer.prototype.serializeToString = function (node) {
      window.nativeDownloadSource = node.getAttribute('data-download-source');
      return originalSerialize.call(this, node);
    };
    URL.createObjectURL = () => 'blob:native-fullscreen-test';
    URL.revokeObjectURL = () => {};
    HTMLAnchorElement.prototype.click = () => {};

    const chart = document.querySelector('.mme-fullscreen-chart');
    chart.dispatchEvent(
      new MouseEvent('mousedown', { bubbles: true, button: 0, clientX: 30, clientY: 30 }),
    );
    document.dispatchEvent(
      new MouseEvent('mousemove', { bubbles: true, clientX: 110, clientY: 95 }),
    );
    document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
  });
  await page.locator('[data-action="downloadSVG"]').click();

  expect(await page.evaluate(() => window.nativeDownloadSource)).toBe('fullscreen');
  expect(
    await page.evaluate(() => {
      const svg = document.querySelector('.language-mermaid[data-mme-enhanced] svg');
      return {
        filter: svg.style.filter,
        opacity: svg.style.opacity,
        transform: svg.style.transform,
        transformOrigin: svg.style.transformOrigin,
      };
    }),
  ).toEqual(sourceBefore);

  await fullscreenButton(page).click();
  await expect(page.locator('.mme-fullscreen-chart')).toHaveCount(0);
  await expect(page.locator('.mme-code-area')).toBeVisible();
  await expect(page.locator('[data-action="showCode"]')).toHaveClass(/active/);
  expect(
    await page.evaluate(() => {
      const svg = document.querySelector('.language-mermaid[data-mme-enhanced] svg');
      return {
        filter: svg.style.filter,
        opacity: svg.style.opacity,
        transform: svg.style.transform,
        transformOrigin: svg.style.transformOrigin,
      };
    }),
  ).toEqual(sourceBefore);
});

test('Mermaid fits a native fullscreen chart when code mode initially hides the clone', async ({
  page,
}) => {
  await prepareEditor(page);
  await page.evaluate(() => {
    const svg = document.querySelector('.language-mermaid[data-mme-enhanced] svg');
    svg.style.width = '2400px';
    svg.style.height = '1600px';
  });
  await page.locator('[data-action="showCode"]').click();
  await installNativeFullscreenStub(page);

  await fullscreenButton(page).click();
  await expect(page.locator('.mme-fullscreen-chart')).toBeHidden();
  await page.locator('[data-action="showChart"]').click();
  await expect(page.locator('.mme-fullscreen-chart')).toBeVisible();

  const fitted = await page.evaluate(() => {
    const chart = document.querySelector('.mme-fullscreen-chart');
    const svg = chart.querySelector('svg');
    const scale = Number(svg.style.transform.match(/scale\(([^)]+)\)/)[1]);
    const rect = svg.getBoundingClientRect();
    return {
      chartHeight: chart.clientHeight,
      chartWidth: chart.clientWidth,
      height: rect.height,
      scale,
      width: rect.width,
    };
  });
  expect(fitted.scale).toBeLessThan(1);
  expect(fitted.width).toBeLessThanOrEqual(fitted.chartWidth + 1);
  expect(fitted.height).toBeLessThanOrEqual(fitted.chartHeight + 1);
});

test('Mermaid source removal releases source drag listeners', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  await prepareEditor(page);
  await page.evaluate(() => {
    const source = document.querySelector('.language-mermaid[data-mme-enhanced]');
    window.removedMermaidSource = source;
    source.dispatchEvent(
      new MouseEvent('mousedown', { bubbles: true, button: 0, clientX: 20, clientY: 20 }),
    );
    source.remove();
  });
  await expect(page.locator('.mme-overlay-item')).toHaveCount(0);

  expect(await page.evaluate(() => typeof window.removedMermaidSource._mmeDragPanCleanup)).toBe(
    'undefined',
  );
  await page.evaluate(() => {
    document.dispatchEvent(
      new MouseEvent('mousemove', { bubbles: true, clientX: 90, clientY: 70 }),
    );
    document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
  });
  await page.waitForTimeout(0);
  expect(pageErrors).toEqual([]);
});

test('Mermaid fullscreen layout fits a mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await prepareEditor(page);
  await rejectNativeFullscreen(page);
  await fullscreenButton(page).click();
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await expect.poll(async () => page.locator('.mme-toolbar').first().boundingBox()).not.toBeNull();
  await expect
    .poll(async () => page.locator('.language-mermaid svg').last().boundingBox())
    .not.toBeNull();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});

test('Mermaid normal zoom keeps the chart center stable', async ({ page }) => {
  await prepareEditor(page);

  const centerBeforeZoom = await page.evaluate(() => {
    const rect = document
      .querySelector('.language-mermaid[data-mme-enhanced] svg')
      .getBoundingClientRect();
    return { x: (rect.left + rect.right) / 2, y: (rect.top + rect.bottom) / 2 };
  });
  await page.locator('[data-action="zoomIn"]').first().click();
  await page.waitForTimeout(300);
  const centerAfterZoom = await page.evaluate(() => {
    const rect = document
      .querySelector('.language-mermaid[data-mme-enhanced] svg')
      .getBoundingClientRect();
    return { x: (rect.left + rect.right) / 2, y: (rect.top + rect.bottom) / 2 };
  });
  expect(Math.abs(centerAfterZoom.x - centerBeforeZoom.x)).toBeLessThan(2);
  expect(Math.abs(centerAfterZoom.y - centerBeforeZoom.y)).toBeLessThan(2);
});

test('Fullscreen does not pollute Mermaid Undo and Redo', async ({ page }) => {
  await prepareEditor(page);
  await rejectNativeFullscreen(page);

  const originalValue = await page.evaluate(() => window._vditor.getValue().replace(/\n+$/, ''));
  const baselineSnapshot = await page.evaluate(() =>
    window._vditor.vditor.undo.addCaret(window._vditor.vditor),
  );
  const editedValue = `${originalValue}!`;
  await page.evaluate((value) => window._vditor.setValue(value), editedValue);
  await expect
    .poll(async () => page.evaluate(() => window._vditor.getValue()))
    .toContain('After the diagram!');
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
  await expect
    .poll(async () => page.evaluate(() => window._vditor.getValue().replace(/\n+$/, '')))
    .toBe(originalValue);
  await expect.poll(async () => page.locator('.vditor-ir__preview svg').count()).toBe(1);
  expect(await page.locator('.vditor-ir .vditor-wysiwyg__block').count()).toBe(0);

  await page.evaluate(() => {
    const vditor = window._vditor.vditor;
    vditor.undo.renderDiff(window.fullscreenUndoPatch, vditor, true);
  });
  await expect
    .poll(async () => page.evaluate(() => window._vditor.getValue()))
    .toContain('After the diagram!');
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
  });
  await rejectNativeFullscreen(page);

  await fullscreenButton(page).click();
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('.mme-overlay-item .mme-toolbar')).toHaveCount(1);
  await expect(page.locator('.mme-toolbar')).toHaveCount(1);
  await expect(page.locator('.mme-code-area')).toHaveCount(1);
});

test('Fullscreen hides other Mermaid toolbars in the same document', async ({ page }) => {
  await prepareEditor(page);
  await page.evaluate((value) => window._vditor.setValue(value), twoMermaidMarkdown);
  await expect
    .poll(async () => await page.evaluate(() => window._vditor.getValue().replace(/\n+$/, '')))
    .toBe(twoMermaidMarkdown);
  await expect.poll(async () => page.locator('.vditor-ir__preview svg').count()).toBe(2);
  await expect.poll(async () => page.locator('.mme-overlay-item').count()).toBe(2);
  await rejectNativeFullscreen(page);

  await fullscreenButton(page).first().click();
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await expect(page.locator('.mme-overlay-item:visible')).toHaveCount(1);
  await expect(page.locator('.mme-overlay-item[data-mme-fullscreen="true"]')).toHaveCount(1);
  await expect(page.locator('.mme-overlay-item:not([data-mme-fullscreen="true"])')).toBeHidden();
});

test('Exiting fullscreen restores the chart transform from before fullscreen', async ({ page }) => {
  await prepareEditor(page);
  await rejectNativeFullscreen(page);

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
    const transform = document.querySelector('.language-mermaid[data-mme-fullscreen="true"] svg')
      .style.transform;
    const match = transform.match(/translate3d\(([-\d.]+)px, ([-\d.]+)px/);
    return { x: Number(match[1]), y: Number(match[2]) };
  });
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 450, box.y + box.height / 2 + 280, { steps: 5 });
  await page.mouse.up();
  const afterDrag = await page.evaluate(() => {
    const transform = document.querySelector('.language-mermaid[data-mme-fullscreen="true"] svg')
      .style.transform;
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
  await rejectNativeFullscreen(page);

  await page.locator('[data-action="zoomIn"]').first().click();
  await page.locator('[data-action="zoomIn"]').first().click();
  const chart = page.locator('.language-mermaid[data-mme-enhanced]').last();
  const box = await chart.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 450, box.y + box.height / 2 + 280, { steps: 5 });
  await page.mouse.up();
  await expect(page.locator('.language-mermaid svg').last()).toHaveAttribute(
    'style',
    /scale\(1\.5\)/,
  );

  await fullscreenButton(page).click();
  await expect(page.locator('html')).toHaveClass(/mme-fullscreen-active/);
  await expect
    .poll(async () =>
      page.evaluate(() => {
        const svg = document.querySelector('.language-mermaid[data-mme-fullscreen="true"] svg');
        const match = svg?.style.transform.match(/scale\(([^)]+)\)/);
        return match ? Number(match[1]) : NaN;
      }),
    )
    .toBeLessThan(1);
  await expect
    .poll(async () =>
      page.evaluate(() => {
        const svg = document.querySelector('.language-mermaid[data-mme-fullscreen="true"] svg');
        const match = svg?.style.transform.match(/scale\(([^)]+)\)/);
        return match ? Number(match[1]) : NaN;
      }),
    )
    .toBeGreaterThan(0);

  const initialFullscreenView = await page.evaluate(() => {
    const target = document.querySelector('.language-mermaid[data-mme-fullscreen="true"]');
    const svg = target.querySelector('svg');
    return {
      target: target.getBoundingClientRect().toJSON(),
      svg: svg.getBoundingClientRect().toJSON(),
    };
  });
  expect(initialFullscreenView.svg.left).toBeGreaterThanOrEqual(
    initialFullscreenView.target.left - 1,
  );
  expect(initialFullscreenView.svg.top).toBeGreaterThanOrEqual(
    initialFullscreenView.target.top - 1,
  );
  expect(initialFullscreenView.svg.right).toBeLessThanOrEqual(
    initialFullscreenView.target.right + 1,
  );
  expect(initialFullscreenView.svg.bottom).toBeLessThanOrEqual(
    initialFullscreenView.target.bottom + 1,
  );

  const centerBeforeZoom = await page.evaluate(() => {
    const rect = document
      .querySelector('.language-mermaid[data-mme-fullscreen="true"] svg')
      .getBoundingClientRect();
    return { x: (rect.left + rect.right) / 2, y: (rect.top + rect.bottom) / 2 };
  });
  await page.locator('[data-action="zoomIn"]').first().click();
  await page.waitForTimeout(300);
  const centerAfterZoom = await page.evaluate(() => {
    const rect = document
      .querySelector('.language-mermaid[data-mme-fullscreen="true"] svg')
      .getBoundingClientRect();
    return { x: (rect.left + rect.right) / 2, y: (rect.top + rect.bottom) / 2 };
  });
  expect(Math.abs(centerAfterZoom.x - centerBeforeZoom.x)).toBeLessThan(2);
  expect(Math.abs(centerAfterZoom.y - centerBeforeZoom.y)).toBeLessThan(2);
});
