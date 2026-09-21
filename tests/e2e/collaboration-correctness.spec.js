import { readFileSync } from 'node:fs';
import { test, expect } from '@playwright/test';

const paragraphSplitCases = JSON.parse(
  readFileSync(new URL('../fixtures/paragraph_split_cases.json', import.meta.url), 'utf8'),
);

test('paragraph contract matches the backend', async ({ page }) => {
  await page.goto('/admin');

  for (const testCase of paragraphSplitCases) {
    const paragraphs = await page.evaluate(
      (text) => window.nasmdDiff.splitParagraphs(text),
      testCase.text,
    );
    expect(paragraphs, testCase.name).toEqual(testCase.paragraphs);
  }
});

test('lossless parser reconstructs normalized input', async ({ page }) => {
  await page.goto('/admin');

  for (const testCase of paragraphSplitCases.filter((item) => item.delimiters)) {
    const result = await page.evaluate((text) => {
      const split = window.nasmdDiff.parseDocument(text);
      return {
        ...split,
        roundTrip:
          split.prefix +
          split.paragraphs.map((paragraph, idx) => paragraph + split.delimiters[idx]).join(''),
      };
    }, testCase.text);

    expect(result.prefix, testCase.name).toBe(testCase.prefix || '');
    expect(result.paragraphs, testCase.name).toEqual(testCase.paragraphs);
    expect(result.delimiters, testCase.name).toEqual(testCase.delimiters);
    expect(result.roundTrip, testCase.name).toBe(testCase.text);
  }
});

test('paragraph diff and apply round-trip exact content', async ({ page }) => {
  await page.goto('/admin');

  const cases = [
    ['delete-final-paragraph', 'A\n\nB\n\nC', 'A\n\nB'],
    ['add-trailing-newline', 'A\n\nB', 'A\n\nB\n'],
    ['change-blank-line-delimiter', 'A\n\nB', 'A\n\n\n\nB'],
    ['change-frontmatter-boundary', '---\ntitle: Doc\n---\nBody', '---\ntitle: Doc\n---\n\nBody'],
    ['empty-content', 'A', ''],
    ['leading-blank-content', '', '\nA'],
    ['delete-leading-blank-content', '\nA', ''],
    ['leading-whitespace-content', '', ' \nA'],
    ['single-newline-separator', 'A', 'A\nB'],
    ['whitespace-separator', 'A', 'A\n \nB'],
    ['delete-whitespace-separated-paragraph', 'A\n \nB', 'A'],
    ['blank-only-content', '', '\n'],
    ['delete-blank-only-content', '\n', ''],
    ['blank-only-whitespace-content', '', ' \n'],
    ['delete-blank-only-whitespace-content', ' \n', ''],
    ['multiple-blank-lines', '', '\n\n\n'],
    ['blank-prefix-to-frontmatter', '\n', '---\nx: y\n---\nA'],
  ];

  const results = await page.evaluate((roundTripCases) => {
    return roundTripCases.map(([name, base, target]) => {
      const changes = window.nasmdDiff.computeParagraphDiff(base, target);
      return [name, window.nasmdDiff.applyChangesLocally(base, changes)];
    });
  }, cases);

  expect(results).toEqual(cases.map(([name, , target]) => [name, target]));
});

test('paragraph diff operations match the backend contract', async ({ page }) => {
  await page.goto('/admin');

  const results = await page.evaluate(() => ({
    delimiterOnly: window.nasmdDiff.computeParagraphDiff('A\n\nB', 'A\n\n\nB'),
    multiReplace: window.nasmdDiff.computeParagraphDiff('A\n\nB', 'X\n\nY'),
    prefixMultiReplace: window.nasmdDiff.computeParagraphDiff('\nA\n\nB', ' \nX\n \nY'),
  }));

  expect(results).toEqual({
    delimiterOnly: [{ type: 'delimiter', paraIdx: 0, delimiter: '\n\n\n' }],
    multiReplace: [
      { type: 'replace', paraIdx: 0, content: 'X', fallbackDelimiter: '\n\n' },
      { type: 'replace', paraIdx: 1, content: 'Y', fallbackDelimiter: '' },
    ],
    prefixMultiReplace: [
      { type: 'prefix', content: ' \n' },
      {
        type: 'replace',
        paraIdx: 0,
        content: 'X',
        delimiter: '\n \n',
        fallbackDelimiter: '\n \n',
      },
      { type: 'replace', paraIdx: 1, content: 'Y', fallbackDelimiter: '' },
    ],
  });
});

test('paragraph diff adversarial operations match the backend contract', async ({ page }) => {
  await page.goto('/admin');

  const results = await page.evaluate(() => {
    const paragraphs = Array.from({ length: 4000 }, (_, idx) => `paragraph-${idx}`);
    const sparseTarget = paragraphs.slice();
    sparseTarget[0] = 'first-edited';
    sparseTarget[sparseTarget.length - 1] = 'last-edited';
    const fallbackOld = Array.from({ length: 300 }, (_, idx) => `old-${idx}`)
      .concat(['ANCHOR'])
      .concat(Array.from({ length: 300 }, (_, idx) => `old-tail-${idx}`));
    const fallbackNew = Array.from({ length: 300 }, (_, idx) => `new-${idx}`)
      .concat(['ANCHOR'])
      .concat(Array.from({ length: 300 }, (_, idx) => `new-tail-${idx}`));
    return {
      insertionShift: window.nasmdDiff.computeParagraphDiff(
        'A\n\nB\n\nC\n\nD',
        'A\n\nX\n\nB\n\nC\n\nD',
      ),
      deletionShift: window.nasmdDiff.computeParagraphDiff(
        'A\n\nX\n\nB\n\nC\n\nD',
        'A\n\nB\n\nC\n\nD',
      ),
      repeated: window.nasmdDiff.computeParagraphDiff(
        'A\n\nX\n\nA\n\nY\n\nA',
        'A\n\nZ\n\nA\n\nY\n\nA',
      ),
      noCommon: window.nasmdDiff.computeParagraphDiff('A\n\nB', 'X\n\nY'),
      mixed: window.nasmdDiff.computeParagraphDiff(
        'A\n\nB\n\nC\n\nD\n\nE\n\nF',
        'A\n\nB2\n\nX\n\nD\n\nF\n\nG',
      ),
      sparseLarge: window.nasmdDiff.computeParagraphDiff(
        paragraphs.join('\n\n'),
        sparseTarget.join('\n\n'),
      ),
      hirschbergFallback: window.nasmdDiff.computeParagraphDiff(
        fallbackOld.join('\n\n'),
        fallbackNew.join('\n\n'),
      ),
    };
  });

  const hirschbergExpected = Array.from({ length: 300 }, (_, idx) => ({
    type: 'replace',
    paraIdx: idx,
    content: `new-${idx}`,
    fallbackDelimiter: '\n\n',
  })).concat(
    Array.from({ length: 300 }, (_, idx) => ({
      type: 'replace',
      paraIdx: idx + 301,
      content: `new-tail-${idx}`,
      fallbackDelimiter: idx === 299 ? '' : '\n\n',
    })),
  );

  expect(results).toEqual({
    insertionShift: [{ type: 'insert', paraIdx: 1, content: 'X', delimiter: '\n\n' }],
    deletionShift: [{ type: 'delete', paraIdx: 1 }],
    repeated: [{ type: 'replace', paraIdx: 1, content: 'Z', fallbackDelimiter: '\n\n' }],
    noCommon: [
      { type: 'replace', paraIdx: 0, content: 'X', fallbackDelimiter: '\n\n' },
      { type: 'replace', paraIdx: 1, content: 'Y', fallbackDelimiter: '' },
    ],
    mixed: [
      { type: 'replace', paraIdx: 1, content: 'B2', fallbackDelimiter: '\n\n' },
      { type: 'replace', paraIdx: 2, content: 'X', fallbackDelimiter: '\n\n' },
      { type: 'delete', paraIdx: 4 },
      { type: 'delimiter', paraIdx: 5, delimiter: '\n\n' },
      { type: 'insert', paraIdx: 6, content: 'G', delimiter: '' },
    ],
    sparseLarge: [
      { type: 'replace', paraIdx: 0, content: 'first-edited', fallbackDelimiter: '\n\n' },
      { type: 'replace', paraIdx: 3999, content: 'last-edited', fallbackDelimiter: '' },
    ],
    hirschbergFallback: hirschbergExpected,
  });
});

test('paragraph diff fallback operations match the backend anchor contract', async ({ page }) => {
  await page.goto('/admin');

  const results = await page.evaluate(() => {
    const reversedOld = Array.from({ length: 300 }, (_, idx) => `paragraph-${idx}`);
    const reversedNew = reversedOld.slice().reverse();
    const repeatedOld = Array.from({ length: 150 }, (_, idx) => `old-${idx}`)
      .concat(Array.from({ length: 300 }, (_, idx) => `REPEAT-${idx % 2 === 0 ? 'A' : 'B'}`))
      .concat(Array.from({ length: 150 }, (_, idx) => `old-tail-${idx}`));
    const repeatedNew = Array.from({ length: 150 }, (_, idx) => `new-${idx}`)
      .concat(Array.from({ length: 300 }, (_, idx) => `REPEAT-${idx % 2 === 0 ? 'A' : 'B'}`))
      .concat(Array.from({ length: 150 }, (_, idx) => `new-tail-${idx}`));
    const reversedBase = reversedOld.join('\n\n');
    const reversedTarget = reversedNew.join('\n\n');
    const repeatedBase = repeatedOld.join('\n\n');
    const repeatedTarget = repeatedNew.join('\n\n');
    const reversedChanges = window.nasmdDiff.computeParagraphDiff(reversedBase, reversedTarget);
    const repeatedChanges = window.nasmdDiff.computeParagraphDiff(repeatedBase, repeatedTarget);

    return {
      reversedChanges,
      reversedApplied: window.nasmdDiff.applyChangesLocally(reversedBase, reversedChanges),
      repeatedChanges,
      repeatedApplied: window.nasmdDiff.applyChangesLocally(repeatedBase, repeatedChanges),
    };
  });
  const reversedNew = Array.from({ length: 300 }, (_, idx) => `paragraph-${299 - idx}`);
  const expectedReversed = Array.from({ length: 299 }, (_, idx) => ({
    type: 'delete',
    paraIdx: idx,
  }))
    .concat([{ type: 'delimiter', paraIdx: 299, delimiter: '\n\n' }])
    .concat(
      Array.from({ length: 299 }, (_, offset) => {
        const idx = offset + 1;
        return {
          type: 'insert',
          paraIdx: 300,
          content: reversedNew[idx],
          delimiter: idx === 299 ? '' : '\n\n',
        };
      }),
    );
  const expectedRepeated = Array.from({ length: 150 }, (_, idx) => ({
    type: 'replace',
    paraIdx: idx,
    content: `new-${idx}`,
    fallbackDelimiter: '\n\n',
  })).concat(
    Array.from({ length: 150 }, (_, idx) => ({
      type: 'replace',
      paraIdx: idx + 450,
      content: `new-tail-${idx}`,
      fallbackDelimiter: idx === 149 ? '' : '\n\n',
    })),
  );

  expect(results.reversedChanges).toEqual(expectedReversed);
  expect(results.reversedApplied).toBe(reversedNew.join('\n\n'));
  expect(results.repeatedChanges).toEqual(expectedRepeated);
  expect(results.repeatedApplied).toBe(
    Array.from({ length: 150 }, (_, idx) => `new-${idx}`)
      .concat(Array.from({ length: 300 }, (_, idx) => `REPEAT-${idx % 2 === 0 ? 'A' : 'B'}`))
      .concat(Array.from({ length: 150 }, (_, idx) => `new-tail-${idx}`))
      .join('\n\n'),
  );
});

test('repeated rotation preserves the longest common block and remote edits', async ({ page }) => {
  await page.goto('/admin');

  const result = await page.evaluate(() => {
    const oldParagraphs = new Array(300).fill('A').concat(new Array(129).fill('B'));
    const newParagraphs = new Array(129).fill('B').concat(new Array(300).fill('A'));
    const remoteParagraphs = oldParagraphs.slice();
    remoteParagraphs[150] = 'A-REMOTE';
    const base = oldParagraphs.join('\n\n');
    const target = newParagraphs.join('\n\n');
    const remote = remoteParagraphs.join('\n\n');
    const changes = window.nasmdDiff.computeParagraphDiff(base, target);
    return {
      changes,
      applied: window.nasmdDiff.applyChangesLocally(base, changes),
      rebased: window.nasmdDiff.rebaseContent(base, target, remote),
    };
  });
  const expectedChanges = Array.from({ length: 129 }, () => ({
    type: 'insert',
    paraIdx: 0,
    content: 'B',
    delimiter: '\n\n',
  }))
    .concat([{ type: 'delimiter', paraIdx: 299, delimiter: '' }])
    .concat(
      Array.from({ length: 129 }, (_, offset) => ({ type: 'delete', paraIdx: offset + 300 })),
    );
  const expectedRebase = new Array(129)
    .fill('B')
    .concat(new Array(150).fill('A'))
    .concat(['A-REMOTE'])
    .concat(new Array(149).fill('A'))
    .join('\n\n');

  expect(result.changes).toEqual(expectedChanges);
  expect(result.applied).toBe(
    new Array(129).fill('B').concat(new Array(300).fill('A')).join('\n\n'),
  );
  expect(result.rebased).toBe(expectedRebase);
});

test('paragraph diff reports typed work-limit exhaustion', async ({ page }) => {
  await page.goto('/admin');

  const result = await page.evaluate(() => {
    const oldParagraphs = new Array(600)
      .fill('A')
      .concat(new Array(600).fill('B'))
      .concat(new Array(600).fill('C'));
    const newParagraphs = new Array(600)
      .fill('B')
      .concat(new Array(600).fill('C'))
      .concat(new Array(600).fill('A'));
    try {
      window.nasmdDiff.computeParagraphDiff(oldParagraphs.join('\n\n'), newParagraphs.join('\n\n'));
      return { threw: false };
    } catch (error) {
      return {
        threw: true,
        name: error.name,
        code: error.code,
        typed: error instanceof window.nasmdDiff.DiffWorkLimitError,
      };
    }
  });

  expect(result).toEqual({
    threw: true,
    name: 'DiffWorkLimitError',
    code: 'DIFF_WORK_LIMIT_EXCEEDED',
    typed: true,
  });
});

test('paragraph diff rejects a 998787-pair match graph before allocating it', async ({ page }) => {
  await page.goto('/admin');

  const result = await page.evaluate(() => {
    const repetitions = 577;
    const oldParagraphs = new Array(repetitions)
      .fill('A')
      .concat(new Array(repetitions).fill('B'))
      .concat(new Array(repetitions).fill('C'));
    const newParagraphs = new Array(repetitions)
      .fill('B')
      .concat(new Array(repetitions).fill('C'))
      .concat(new Array(repetitions).fill('A'));
    try {
      const changes = window.nasmdDiff.computeParagraphDiff(
        oldParagraphs.join('\n\n'),
        newParagraphs.join('\n\n'),
      );
      return { threw: false, changesLength: changes.length };
    } catch (error) {
      return {
        threw: true,
        name: error.name,
        code: error.code,
        typed: error instanceof window.nasmdDiff.DiffWorkLimitError,
      };
    }
  });

  expect(3 * 577 * 577).toBe(998787);
  expect(result).toEqual({
    threw: true,
    name: 'DiffWorkLimitError',
    code: 'DIFF_WORK_LIMIT_EXCEEDED',
    typed: true,
  });
});

test('dirty remote events preserve the acknowledged baseline and retain the version high-water', async ({
  page,
}) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const editor = {
      value: 'local-dirty',
      getValue() {
        return this.value;
      },
      setValue(value) {
        this.value = value;
      },
    };
    Object.assign(window.state, {
      currentMountId: 'mount-0',
      currentPath: '/dirty-remote.md',
      baseVersion: 7,
      baseContent: 'confirmed-v7',
      fileVersions: { 'mount-0:/dirty-remote.md': 7 },
      pendingRemoteVersion: null,
      autoSave: false,
    });
    window._vditor = editor;
    window._originalContent = 'confirmed-v7';
    window._lastSavedContent = 'confirmed-v7';
    window.markDirty();

    const acknowledged = () => ({
      editor: editor.getValue(),
      baseVersion: window.state.baseVersion,
      baseContent: window.state.baseContent,
      originalContent: window._originalContent,
      fileVersion: window.state.fileVersions['mount-0:/dirty-remote.md'],
    });
    const before = acknowledged();

    window.nasmdSync.handleRemoteEdit({
      type: 'remote_edit',
      mountId: 'mount-0',
      path: '/dirty-remote.md',
      newVersion: 9,
      authorId: 'remote',
      authorName: 'Remote',
      authorColor: '#f00',
      changes: [{ type: 'replace', paraIdx: 0, content: 'REMOTE' }],
    });
    window.nasmdSync.handleExternalReload({
      type: 'external_reload',
      mountId: 'mount-0',
      path: '/dirty-remote.md',
      newVersion: 8,
      content: 'external-v8',
    });
    await new Promise((resolve) => setTimeout(resolve, 400));

    return {
      before,
      after: acknowledged(),
      pendingRemoteVersion: window.state.pendingRemoteVersion,
    };
  });

  expect(result.after).toEqual(result.before);
  expect(result.pendingRemoteVersion).toBe(9);
});

test('clean remote batching advances the editor and acknowledged baseline atomically', async ({
  page,
}) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const setValues = [];
    const editor = {
      value: 'transient-editor-value',
      getValue() {
        return this.value;
      },
      setValue(value) {
        setValues.push(value);
        this.value = value;
      },
    };
    Object.assign(window.state, {
      currentMountId: 'mount-0',
      currentPath: '/clean-remote.md',
      baseVersion: 7,
      baseContent: 'A\n\nB',
      fileVersions: { 'mount-0:/clean-remote.md': 7 },
      pendingRemoteVersion: 12,
      dirty: false,
    });
    window._vditor = editor;
    window._originalContent = 'A\n\nB';
    window._lastSavedContent = 'A\n\nB';

    window.nasmdSync.handleRemoteEdit({
      type: 'remote_edit',
      mountId: 'mount-0',
      path: '/clean-remote.md',
      newVersion: 8,
      authorId: 'remote',
      authorName: 'Remote',
      authorColor: '#f00',
      changes: [{ type: 'insert', paraIdx: 0, content: 'X' }],
    });
    await new Promise((resolve) => setTimeout(resolve, 400));

    return {
      setValues,
      editor: editor.getValue(),
      baseVersion: window.state.baseVersion,
      baseContent: window.state.baseContent,
      originalContent: window._originalContent,
      fileVersion: window.state.fileVersions['mount-0:/clean-remote.md'],
      pendingRemoteVersion: window.state.pendingRemoteVersion,
    };
  });

  expect(result).toEqual({
    setValues: ['X\n\nA\n\nB'],
    editor: 'X\n\nA\n\nB',
    baseVersion: 8,
    baseContent: 'X\n\nA\n\nB',
    originalContent: 'X\n\nA\n\nB',
    fileVersion: 8,
    pendingRemoteVersion: null,
  });
});

test('clean remote pending version starts empty and resets after an explicit file switch', async ({
  page,
}) => {
  await page.goto('/admin');
  await page.waitForFunction(() => window.state?.mounts?.some((mount) => mount.id === 'mount-0'));

  expect(await page.evaluate(() => window.state.pendingRemoteVersion)).toBeNull();
  await page.evaluate(async () => {
    window.state.pendingRemoteVersion = 99;
    await window.openFile('/mermaid-fullscreen.md', 'mount-0');
  });

  expect(await page.evaluate(() => window.state.currentPath)).toBe('/mermaid-fullscreen.md');
  expect(await page.evaluate(() => window.state.pendingRemoteVersion)).toBeNull();
});

test('save keeps an over-budget document dirty without submitting changes', async ({ page }) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const baseParagraphs = new Array(600)
      .fill('A')
      .concat(new Array(600).fill('B'))
      .concat(new Array(600).fill('C'));
    const localParagraphs = new Array(600)
      .fill('B')
      .concat(new Array(600).fill('C'))
      .concat(new Array(600).fill('A'));
    const base = baseParagraphs.join('\n\n');
    const local = localParagraphs.join('\n\n');
    const path = '/work-limit.md';
    let submitCalls = 0;
    const originalSubmitChanges = API.submitChanges;
    API.submitChanges = async () => {
      submitCalls++;
      return { applied: true, newVersion: 8, content: local };
    };
    localStorage.removeItem(`nasmd_draft_${path}`);
    Object.assign(window.state, {
      currentMountId: 'work-limit',
      currentPath: path,
      mounts: [{ id: 'work-limit', readonly: false }],
      localMounts: {},
      remoteFile: null,
      baseVersion: 7,
      baseContent: base,
      dirty: true,
      autoSave: false,
    });
    window._originalContent = base;
    window._vditor = { getValue: () => local };

    try {
      await window.saveFile();
      const draft = JSON.parse(localStorage.getItem(`nasmd_draft_${path}`));
      return {
        submitCalls,
        dirty: window.state.dirty,
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
        editorContent: window._vditor.getValue(),
        draftContent: draft?.content,
      };
    } finally {
      API.submitChanges = originalSubmitChanges;
    }
  });

  expect(result.submitCalls).toBe(0);
  expect(result.dirty).toBe(true);
  expect(result.baseVersion).toBe(7);
  expect(result.baseContent).not.toBe(result.editorContent);
  expect(result.draftContent).toBe(result.editorContent);
});

test('save keeps the local draft dirty when the server reports a write failure', async ({
  page,
}) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const path = '/write-failure.md';
    const base = 'before';
    const local = 'after';
    const originalRequest = API.request;
    API.request = async () =>
      new Response(
        JSON.stringify({
          applied: false,
          merged: false,
          newVersion: 7,
          content: base,
          errorCode: 'write_failed',
          message: 'Unable to save file',
        }),
        { status: 500, headers: { 'Content-Type': 'application/json' } },
      );
    localStorage.removeItem(`nasmd_draft_${path}`);
    Object.assign(window.state, {
      currentMountId: 'write-failure',
      currentPath: path,
      mounts: [{ id: 'write-failure', readonly: false }],
      localMounts: {},
      remoteFile: null,
      baseVersion: 7,
      baseContent: base,
      dirty: true,
      autoSave: false,
    });
    window._originalContent = base;
    window._vditor = { getValue: () => local };

    try {
      await window.saveFile();
      const draft = JSON.parse(localStorage.getItem(`nasmd_draft_${path}`));
      return {
        dirty: window.state.dirty,
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
        draftContent: draft?.content,
      };
    } finally {
      API.request = originalRequest;
    }
  });

  expect(result).toEqual({
    dirty: true,
    baseVersion: 7,
    baseContent: 'before',
    draftContent: 'after',
  });
});

test('new-file flow shows only failure when PUT returns 500', async ({ page }) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const originalRequest = API.request;
    const toast = document.getElementById('toast');
    const messages = [];
    const observer = new MutationObserver(() => messages.push(toast.textContent));
    observer.observe(toast, { childList: true, characterData: true, subtree: true });

    let finishRequest;
    const requestFinished = new Promise((resolve) => {
      finishRequest = resolve;
    });
    API.request = async () => {
      finishRequest();
      return new Response(
        JSON.stringify({ errorCode: 'write_failed', message: 'Unable to save file' }),
        { status: 500, headers: { 'Content-Type': 'application/json' } },
      );
    };
    window.state.mounts = [{ id: 'write-failure', readonly: false }];
    document.getElementById('new-file-name').value = 'failed-create';

    try {
      confirmNewFile();
      await requestFinished;
      await new Promise((resolve) => setTimeout(resolve, 0));
      return { messages, finalToast: toast.textContent };
    } finally {
      observer.disconnect();
      API.request = originalRequest;
    }
  });

  expect(result.finalToast).toBe('创建失败');
  expect(result.messages).toContain('创建失败');
  expect(result.messages).not.toContain('已创建');
});

test('server import flow shows only failure when PUT returns 500', async ({ page }) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const originalRequest = API.request;
    const toast = document.getElementById('toast');
    const messages = [];
    const observer = new MutationObserver(() => messages.push(toast.textContent));
    observer.observe(toast, { childList: true, characterData: true, subtree: true });

    let finishPut;
    const putFinished = new Promise((resolve) => {
      finishPut = resolve;
    });
    API.request = async (_path, options = {}) => {
      if (options.method === 'PUT') {
        finishPut();
        return new Response(
          JSON.stringify({ errorCode: 'write_failed', message: 'Unable to save file' }),
          { status: 500, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response('', { status: 404 });
    };

    Object.assign(window.state, {
      mounts: [{ id: 'write-failure', readonly: false }],
      localMounts: {},
      _fileOpInProgress: false,
    });
    setupDragDrop();
    const target = document.createElement('div');
    target.dataset.dropMount = 'write-failure';
    target.dataset.dropPath = '/';
    document.getElementById('file-tree').appendChild(target);
    const transfer = new DataTransfer();
    transfer.items.add(new File(['content'], 'failed-import.md', { type: 'text/markdown' }));

    try {
      target.dispatchEvent(new DragEvent('drop', { bubbles: true, dataTransfer: transfer }));
      await putFinished;
      while (window.state._fileOpInProgress) {
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
      await new Promise((resolve) => setTimeout(resolve, 0));
      return { messages, finalToast: toast.textContent };
    } finally {
      observer.disconnect();
      API.request = originalRequest;
      target.remove();
    }
  });

  expect(result.finalToast).toBe('导入失败');
  expect(result.messages).toContain('导入失败');
  expect(result.messages).not.toContain('已导入: failed-import.md');
});

test('large paragraph fallback remains within the browser main-thread budget', async ({ page }) => {
  await page.goto('/admin');

  const results = await page.evaluate(() => {
    const measureOneAnchor = (size) => {
      const anchorIdx = Math.floor(size / 2);
      const oldParagraphs = Array.from({ length: size }, (_, idx) => `old-${idx}`);
      const newParagraphs = Array.from({ length: size }, (_, idx) => `new-${idx}`);
      oldParagraphs[anchorIdx] = 'SHARED-ANCHOR';
      newParagraphs[anchorIdx] = 'SHARED-ANCHOR';
      const base = oldParagraphs.join('\n\n');
      const target = newParagraphs.join('\n\n');
      const started = performance.now();
      const changes = window.nasmdDiff.computeParagraphDiff(base, target);
      const elapsed = performance.now() - started;
      return {
        elapsed,
        exact: window.nasmdDiff.applyChangesLocally(base, changes) === target,
        anchorPreserved: !changes.some(
          (change) =>
            change.paraIdx === anchorIdx && (change.type === 'replace' || change.type === 'delete'),
        ),
      };
    };

    const reversedOld = Array.from({ length: 4000 }, (_, idx) => `paragraph-${idx}`);
    const reversedNew = reversedOld.slice().reverse();
    const reversedBase = reversedOld.join('\n\n');
    const reversedTarget = reversedNew.join('\n\n');
    let started = performance.now();
    const reversedChanges = window.nasmdDiff.computeParagraphDiff(reversedBase, reversedTarget);
    const reversedElapsed = performance.now() - started;
    const reversedChangedSources = new Set(
      reversedChanges
        .filter((change) => change.type === 'replace' || change.type === 'delete')
        .map((change) => change.paraIdx),
    );

    const repeatedOld = Array.from({ length: 1000 }, (_, idx) => `old-${idx}`)
      .concat(Array.from({ length: 2000 }, (_, idx) => `REPEAT-${idx % 2 === 0 ? 'A' : 'B'}`))
      .concat(Array.from({ length: 1000 }, (_, idx) => `old-tail-${idx}`));
    const repeatedNew = Array.from({ length: 1000 }, (_, idx) => `new-${idx}`)
      .concat(Array.from({ length: 2000 }, (_, idx) => `REPEAT-${idx % 2 === 0 ? 'A' : 'B'}`))
      .concat(Array.from({ length: 1000 }, (_, idx) => `new-tail-${idx}`));
    const repeatedBase = repeatedOld.join('\n\n');
    const repeatedTarget = repeatedNew.join('\n\n');
    started = performance.now();
    const repeatedChanges = window.nasmdDiff.computeParagraphDiff(repeatedBase, repeatedTarget);
    const repeatedElapsed = performance.now() - started;
    const repeatedAnchorsPreserved = !repeatedChanges.some(
      (change) =>
        change.paraIdx >= 1000 &&
        change.paraIdx < 3000 &&
        (change.type === 'replace' || change.type === 'delete'),
    );

    return {
      oneAnchor: [1000, 2000, 4000, 8000].map(measureOneAnchor),
      reversed: {
        elapsed: reversedElapsed,
        exact:
          window.nasmdDiff.applyChangesLocally(reversedBase, reversedChanges) === reversedTarget,
        preservedCount: 4000 - reversedChangedSources.size,
      },
      repeated: {
        elapsed: repeatedElapsed,
        exact:
          window.nasmdDiff.applyChangesLocally(repeatedBase, repeatedChanges) === repeatedTarget,
        anchorsPreserved: repeatedAnchorsPreserved,
      },
    };
  });

  expect(results.oneAnchor.every((result) => result.exact && result.anchorPreserved)).toBe(true);
  expect(results.reversed.exact).toBe(true);
  expect(results.reversed.preservedCount).toBe(1);
  expect(results.repeated.exact).toBe(true);
  expect(results.repeated.anchorsPreserved).toBe(true);
  expect(results.oneAnchor[3].elapsed).toBeLessThan(750);
  expect(results.oneAnchor[3].elapsed).toBeLessThan(results.oneAnchor[2].elapsed * 3.5 + 100);
  expect(results.reversed.elapsed).toBeLessThan(2000);
  expect(results.repeated.elapsed).toBeLessThan(2000);
});

test('non-Markdown whitespace has stable diff coordinates', async ({ page }) => {
  await page.goto('/admin');

  const cases = [
    ['next-line', '\u0085'],
    ['no-break-space', '\u00a0'],
    ['vertical-tab', '\u000b'],
    ['byte-order-mark', '\ufeff'],
  ];
  const results = await page.evaluate((whitespaceCases) => {
    return whitespaceCases.map(([name, character]) => {
      const base = `${character}\nA`;
      const target = `${character}\nB`;
      const changes = window.nasmdDiff.computeParagraphDiff(base, target);
      return {
        name,
        target,
        changes,
        applied: window.nasmdDiff.applyChangesLocally(base, changes),
      };
    });
  }, cases);

  expect(results).toEqual(
    cases.map(([name, character]) => {
      const target = `${character}\nB`;
      return {
        name,
        target,
        changes: [{ type: 'replace', paraIdx: 0, content: target, fallbackDelimiter: '' }],
        applied: target,
      };
    }),
  );
});

test.describe('rebase', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/admin');
  });

  test('transforms paragraph coordinates like the backend', async ({ page }) => {
    const results = await page.evaluate(() => [
      window.nasmdDiff.transformParagraphChanges(
        [{ type: 'replace', paraIdx: 2, content: 'C-local' }],
        [{ type: 'insert', paraIdx: 0, content: 'HEADER' }],
        3,
      ),
      window.nasmdDiff.transformParagraphChanges(
        [{ type: 'prefix', content: '\n', operationId: 'local-prefix-1' }],
        [
          { type: 'prefix', content: ' \n' },
          { type: 'insert', paraIdx: 0, content: 'HEADER' },
        ],
        3,
      ),
      window.nasmdDiff.transformParagraphChanges(
        [{ type: 'replace', paraIdx: 2, content: 'C-local' }],
        [{ type: 'delete', paraIdx: 0 }],
        3,
      ),
      window.nasmdDiff.transformParagraphChanges(
        [{ type: 'replace', paraIdx: 1, content: 'B-local' }],
        [{ type: 'delete', paraIdx: 1 }],
        3,
      ),
      window.nasmdDiff.transformParagraphChanges(
        [{ type: 'delete', paraIdx: 1 }],
        [{ type: 'delete', paraIdx: 1 }],
        3,
      ),
      window.nasmdDiff.transformParagraphChanges(
        [
          {
            type: 'delimiter',
            paraIdx: 1,
            delimiter: '\n',
            operationId: 'local-format-1',
          },
        ],
        [{ type: 'insert', paraIdx: 0, content: 'HEADER' }],
        3,
      ),
    ]);

    expect(results).toEqual([
      [{ type: 'replace', paraIdx: 3, content: 'C-local' }],
      [{ type: 'prefix', content: '\n', operationId: 'local-prefix-1' }],
      [{ type: 'replace', paraIdx: 1, content: 'C-local' }],
      [{ type: 'insert', paraIdx: 1, content: 'B-local' }],
      [],
      [
        {
          type: 'delimiter',
          paraIdx: 2,
          delimiter: '\n',
          operationId: 'local-format-1',
        },
      ],
    ]);
  });

  test('preserves a local edit across an earlier remote insertion', async ({ page }) => {
    const result = await page.evaluate(() => {
      const base = 'A\n\nB\n\nC';
      const local = 'A\n\nB\n\nC-local';
      const remote = 'HEADER\n\nA\n\nB\n\nC';
      return window.nasmdDiff.rebaseContent(base, local, remote);
    });

    expect(result).toBe('HEADER\n\nA\n\nB\n\nC-local');
  });

  test('preserves a stale exact delimiter edit across a remote paragraph edit', async ({
    page,
  }) => {
    const result = await page.evaluate(() => {
      const base = 'A\n\nB\n\nC';
      const local = 'A\n\nB\n\nC\n';
      const remote = 'A-remote\n\nB\n\nC';
      return window.nasmdDiff.rebaseContent(base, local, remote);
    });

    expect(result).toBe('A-remote\n\nB\n\nC\n');
  });

  test('delimiter-only rebases preserve remote paragraph text', async ({ page }) => {
    const results = await page.evaluate(() => [
      window.nasmdDiff.rebaseContent('A\n\nB', 'A\n\n\nB', 'A-remote\n\nB'),
      window.nasmdDiff.rebaseContent('A\n\nB\n\nC', 'A\n\nB', 'A\n\nB-remote\n\nC'),
    ]);

    expect(results).toEqual(['A-remote\n\n\nB', 'A\n\nB-remote']);
  });

  test('replace rebases preserve or override delimiters according to intent', async ({ page }) => {
    const results = await page.evaluate(() => ({
      remoteDelimiterThenLocalText: window.nasmdDiff.rebaseContent(
        'A\n\nB',
        'A-local\n\nB',
        'A-remote\n\n\nB',
      ),
      deletedReplaceUsesFallback: window.nasmdDiff.rebaseContent('A\n \nB', 'A-local\n \nB', 'B'),
      explicitLocalDelimiterWins: window.nasmdDiff.rebaseContent(
        'A\n\nB',
        'A-local\n \nB',
        'A-remote\n\n\nB',
      ),
    }));

    expect(results).toEqual({
      remoteDelimiterThenLocalText: 'A-local\n\n\nB',
      deletedReplaceUsesFallback: 'A-local\n \nB',
      explicitLocalDelimiterWins: 'A-local\n \nB',
    });
  });

  test('lossless formatting rebases preserve remote paragraph text', async ({ page }) => {
    const results = await page.evaluate(() => [
      window.nasmdDiff.rebaseContent('A', '\nA', 'A-remote'),
      window.nasmdDiff.rebaseContent('A\n\nB', 'A\n \nB', 'A-remote\n\nB'),
    ]);

    expect(results).toEqual(['\nA-remote', 'A-remote\n \nB']);
  });

  test('handles batched remote changes in base coordinates', async ({ page }) => {
    const results = await page.evaluate(() => ({
      multipleInserts: window.nasmdDiff.rebaseContent(
        'A\n\nB\n\nC',
        'A\n\nB-local\n\nC',
        'X\n\nA\n\nB\n\nY\n\nC',
      ),
      adjacentDeletes: window.nasmdDiff.rebaseContent(
        'A\n\nB\n\nC\n\nD',
        'A\n\nB\n\nC-local\n\nD',
        'A\n\nD',
      ),
      mixedInsertDelete: window.nasmdDiff.rebaseContent(
        'A\n\nB\n\nC\n\nD',
        'A-local\n\nB\n\nC\n\nD',
        'X\n\nA\n\nC\n\nD',
      ),
      sameIndexInsertOrder: window.nasmdDiff.rebaseContent(
        'A\n\nB',
        'A\n\nL1\n\nL2\n\nB',
        'A\n\nR1\n\nR2\n\nB',
      ),
    }));

    expect(results).toEqual({
      multipleInserts: 'X\n\nA\n\nB-local\n\nY\n\nC',
      adjacentDeletes: 'A\n\nC-local\n\nD',
      mixedInsertDelete: 'X\n\nA-local\n\nC\n\nD',
      sameIndexInsertOrder: 'A\n\nR1\n\nR2\n\nL1\n\nL2\n\nB',
    });
  });

  test('preserves delimiters for trailing and empty-document inserts', async ({ page }) => {
    const results = await page.evaluate(() => ({
      append: window.nasmdDiff.rebaseContent('A', 'A\n\nB', 'A'),
      empty: window.nasmdDiff.rebaseContent('', 'B', ''),
    }));

    expect(results).toEqual({
      append: 'A\n\nB',
      empty: 'B',
    });
  });

  test('rejects invalid and oversized paragraph coordinates', async ({ page }) => {
    const results = await page.evaluate(() => {
      const invalidCalls = [
        ['base-count-type', () => window.nasmdDiff.transformParagraphChanges([], [], '3')],
        ['negative-base-count', () => window.nasmdDiff.transformParagraphChanges([], [], -1)],
        [
          'unsafe-base-count',
          () => window.nasmdDiff.transformParagraphChanges([], [], Number.MAX_SAFE_INTEGER + 1),
        ],
        [
          'negative-index',
          () =>
            window.nasmdDiff.transformParagraphChanges(
              [{ type: 'replace', paraIdx: -1, content: 'X' }],
              [],
              1,
            ),
        ],
        [
          'insert-past-end',
          () =>
            window.nasmdDiff.transformParagraphChanges(
              [{ type: 'insert', paraIdx: 2, content: 'X' }],
              [],
              1,
            ),
        ],
        [
          'replace-at-end',
          () =>
            window.nasmdDiff.transformParagraphChanges(
              [{ type: 'replace', paraIdx: 1, content: 'X' }],
              [],
              1,
            ),
        ],
        [
          'unknown-type',
          () =>
            window.nasmdDiff.transformParagraphChanges([{ type: 'unknown', paraIdx: 0 }], [], 1),
        ],
        [
          'non-string-content',
          () =>
            window.nasmdDiff.transformParagraphChanges(
              [{ type: 'insert', paraIdx: 0, content: 7 }],
              [],
              1,
            ),
        ],
        [
          'non-string-delimiter',
          () =>
            window.nasmdDiff.transformParagraphChanges(
              [{ type: 'replace', paraIdx: 0, content: 'X', delimiter: 7 }],
              [],
              1,
            ),
        ],
        [
          'non-string-fallback-delimiter',
          () =>
            window.nasmdDiff.transformParagraphChanges(
              [{ type: 'replace', paraIdx: 0, content: 'X', fallbackDelimiter: 7 }],
              [],
              1,
            ),
        ],
        [
          'insert-with-fallback-delimiter',
          () =>
            window.nasmdDiff.transformParagraphChanges(
              [{ type: 'insert', paraIdx: 0, content: 'X', fallbackDelimiter: '' }],
              [],
              1,
            ),
        ],
        [
          'delete-with-delimiter',
          () =>
            window.nasmdDiff.transformParagraphChanges(
              [{ type: 'delete', paraIdx: 0, delimiter: '' }],
              [],
              1,
            ),
        ],
        [
          'delimiter-change-missing-delimiter',
          () =>
            window.nasmdDiff.transformParagraphChanges([{ type: 'delimiter', paraIdx: 0 }], [], 1),
        ],
        [
          'delimiter-change-with-content',
          () =>
            window.nasmdDiff.transformParagraphChanges(
              [{ type: 'delimiter', paraIdx: 0, delimiter: '\n', content: 'X' }],
              [],
              1,
            ),
        ],
        [
          'prefix-change-missing-content',
          () => window.nasmdDiff.transformParagraphChanges([{ type: 'prefix' }], [], 1),
        ],
        [
          'prefix-change-non-string-content',
          () => window.nasmdDiff.transformParagraphChanges([{ type: 'prefix', content: 7 }], [], 1),
        ],
        [
          'prefix-change-with-index',
          () =>
            window.nasmdDiff.transformParagraphChanges(
              [{ type: 'prefix', content: '\n', paraIdx: 0 }],
              [],
              1,
            ),
        ],
        [
          'prefix-change-with-delimiter',
          () =>
            window.nasmdDiff.transformParagraphChanges(
              [{ type: 'prefix', content: '\n', delimiter: '' }],
              [],
              1,
            ),
        ],
        [
          'invalid-accumulated-change',
          () =>
            window.nasmdDiff.transformParagraphChanges([], [{ type: 'delete', paraIdx: -1 }], 1),
        ],
        [
          'unsafe-change-index',
          () =>
            window.nasmdDiff.transformParagraphChanges(
              [{ type: 'insert', paraIdx: Number.MAX_SAFE_INTEGER + 1, content: 'X' }],
              [],
              Number.MAX_SAFE_INTEGER,
            ),
        ],
      ];

      return invalidCalls.map(([name, call]) => {
        try {
          call();
          return [name, false];
        } catch {
          return [name, true];
        }
      });
    });

    expect(results).toEqual([
      ['base-count-type', true],
      ['negative-base-count', true],
      ['unsafe-base-count', true],
      ['negative-index', true],
      ['insert-past-end', true],
      ['replace-at-end', true],
      ['unknown-type', true],
      ['non-string-content', true],
      ['non-string-delimiter', true],
      ['non-string-fallback-delimiter', true],
      ['insert-with-fallback-delimiter', true],
      ['delete-with-delimiter', true],
      ['delimiter-change-missing-delimiter', true],
      ['delimiter-change-with-content', true],
      ['prefix-change-missing-content', true],
      ['prefix-change-non-string-content', true],
      ['prefix-change-with-index', true],
      ['prefix-change-with-delimiter', true],
      ['invalid-accumulated-change', true],
      ['unsafe-change-index', true],
    ]);
  });
});
