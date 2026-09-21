import { readFileSync } from 'node:fs';
import { test, expect } from '@playwright/test';
import { deleteAdminFile, getWritableAdminMount, putAdminFile } from './helpers/admin.js';

const paragraphSplitCases = JSON.parse(
  readFileSync(new URL('../fixtures/paragraph_split_cases.json', import.meta.url), 'utf8'),
);

function uniqueTestPath(stem) {
  return `/${stem}-${Date.now()}-${Math.random().toString(16).slice(2)}.md`;
}

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

test('undoing dirty local edits catches up to a deferred remote version', async ({ page }) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const setValues = [];
    const fetchCalls = [];
    const editor = {
      value: 'local-dirty',
      getValue() {
        return this.value;
      },
      setValue(value) {
        setValues.push(value);
        this.value = value;
      },
    };
    const originalGetFile = API.getFile;
    API.getFile = async (mountId, path) => {
      fetchCalls.push([mountId, path]);
      return { content: 'remote-v2', version: 2, mtime: 0 };
    };
    Object.assign(window.state, {
      currentMountId: 'mount-0',
      currentPath: '/dirty-undo.md',
      baseVersion: 1,
      baseContent: 'confirmed-v1',
      fileVersions: { 'mount-0:/dirty-undo.md': 1 },
      pendingRemoteVersion: null,
      autoSave: false,
    });
    window._vditor = editor;
    window._originalContent = 'confirmed-v1';
    window._lastSavedContent = 'confirmed-v1';
    window.markDirty();

    try {
      window.nasmdSync.handleRemoteEdit({
        type: 'remote_edit',
        mountId: 'mount-0',
        path: '/dirty-undo.md',
        newVersion: 2,
        authorId: 'remote',
        authorName: 'Remote',
        authorColor: '#f00',
        changes: [{ type: 'replace', paraIdx: 0, content: 'remote-v2' }],
      });
      const pendingBeforeUndo = window.state.pendingRemoteVersion;

      editor.value = 'confirmed-v1';
      window.onEditorInput();
      await new Promise((resolve) => setTimeout(resolve, 0));

      return {
        pendingBeforeUndo,
        fetchCalls,
        setValues,
        dirty: window.state.dirty,
        editor: editor.getValue(),
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
        originalContent: window._originalContent,
        fileVersion: window.state.fileVersions['mount-0:/dirty-undo.md'],
        pendingRemoteVersion: window.state.pendingRemoteVersion,
      };
    } finally {
      API.getFile = originalGetFile;
    }
  });

  expect(result).toEqual({
    pendingBeforeUndo: 2,
    fetchCalls: [['mount-0', '/dirty-undo.md']],
    setValues: ['remote-v2'],
    dirty: false,
    editor: 'remote-v2',
    baseVersion: 2,
    baseContent: 'remote-v2',
    originalContent: 'remote-v2',
    fileVersion: 2,
    pendingRemoteVersion: null,
  });
});

test('clean remote batching advances the editor and acknowledged baseline atomically', async ({
  page,
}) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const setValues = [];
    const fetchCalls = [];
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

    const originalGetFile = API.getFile;
    API.getFile = (mountId, path) => {
      fetchCalls.push([mountId, path]);
      return new Promise(() => {});
    };

    try {
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
        fetchCalls,
        setValues,
        editor: editor.getValue(),
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
        originalContent: window._originalContent,
        fileVersion: window.state.fileVersions['mount-0:/clean-remote.md'],
        pendingRemoteVersion: window.state.pendingRemoteVersion,
      };
    } finally {
      API.getFile = originalGetFile;
    }
  });

  expect(result).toEqual({
    fetchCalls: [['mount-0', '/clean-remote.md']],
    setValues: ['X\n\nA\n\nB'],
    editor: 'X\n\nA\n\nB',
    baseVersion: 8,
    baseContent: 'X\n\nA\n\nB',
    originalContent: 'X\n\nA\n\nB',
    fileVersion: 8,
    pendingRemoteVersion: 12,
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

test('offline save scopes its draft to the current mount for collaboration gating', async ({
  page,
}) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const path = '/shared-offline-draft.md';
    const draftContent = 'offline draft from mount A';
    const editor = {
      value: draftContent,
      getValue() {
        return this.value;
      },
      setValue(value) {
        this.value = value;
      },
    };
    const onlineDescriptor = Object.getOwnPropertyDescriptor(navigator, 'onLine');
    localStorage.removeItem(`nasmd_draft_${path}`);
    Object.assign(window.state, {
      currentMountId: 'mount-a',
      currentPath: path,
      mounts: [
        { id: 'mount-a', readonly: false },
        { id: 'mount-b', readonly: false },
      ],
      localMounts: {},
      remoteFile: null,
      baseVersion: 1,
      baseContent: 'mount-a-v1',
      fileVersions: {
        [`mount-a:${path}`]: 1,
        [`mount-b:${path}`]: 1,
      },
      pendingRemoteVersion: null,
      dirty: true,
      autoSave: false,
    });
    window._originalContent = 'mount-a-v1';
    window._lastSavedContent = 'mount-a-v1';
    window._vditor = editor;

    try {
      Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
      await window.saveFile();
      const draft = JSON.parse(localStorage.getItem(`nasmd_draft_${path}`));

      window.nasmdSync.handleRemoteEdit({
        type: 'remote_edit',
        mountId: 'mount-a',
        path,
        newVersion: 2,
        changes: [{ type: 'replace', paraIdx: 0, content: 'remote-a-v2' }],
      });
      const sameMount = {
        editor: editor.getValue(),
        pendingRemoteVersion: window.state.pendingRemoteVersion,
      };

      Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
      Object.assign(window.state, {
        currentMountId: 'mount-b',
        baseVersion: 1,
        baseContent: 'mount-b-v1',
        pendingRemoteVersion: null,
        dirty: false,
      });
      editor.value = 'mount-b-v1';
      window._originalContent = 'mount-b-v1';
      window._lastSavedContent = 'mount-b-v1';

      window.nasmdSync.handleRemoteEdit({
        type: 'remote_edit',
        mountId: 'mount-b',
        path,
        newVersion: 2,
        changes: [{ type: 'replace', paraIdx: 0, content: 'remote-b-v2' }],
      });
      await new Promise((resolve) => setTimeout(resolve, 400));

      return {
        draft,
        sameMount,
        otherMount: {
          editor: editor.getValue(),
          baseVersion: window.state.baseVersion,
          baseContent: window.state.baseContent,
          pendingRemoteVersion: window.state.pendingRemoteVersion,
        },
      };
    } finally {
      localStorage.removeItem(`nasmd_draft_${path}`);
      if (onlineDescriptor) {
        Object.defineProperty(navigator, 'onLine', onlineDescriptor);
      } else {
        delete navigator.onLine;
      }
    }
  });

  expect(result.draft).toMatchObject({
    mountId: 'mount-a',
    content: 'offline draft from mount A',
  });
  expect(result.sameMount).toEqual({
    editor: 'offline draft from mount A',
    pendingRemoteVersion: 2,
  });
  expect(result.otherMount).toEqual({
    editor: 'remote-b-v2',
    baseVersion: 2,
    baseContent: 'remote-b-v2',
    pendingRemoteVersion: null,
  });
});

test('offline save stays dirty and automatically submits after the browser reconnects', async ({
  context,
  page,
}) => {
  const mount = await getWritableAdminMount(page);
  const path = uniqueTestPath('collaboration-offline-reconnect');
  const base = 'server before offline';
  const changesRequests = [];
  await page.route(/\/api\/mounts\/[^/]+\/changes\?/, async (route) => {
    changesRequests.push(route.request().postDataJSON());
    await route.continue();
  });
  await putAdminFile(page, mount.id, path, base);

  try {
    await page.evaluate(async ({ mountId, filePath }) => window.openFile(filePath, mountId), {
      mountId: mount.id,
      filePath: path,
    });
    await page.waitForFunction(
      ({ mountId, filePath }) =>
        window.state.currentMountId === mountId &&
        window.state.currentPath === filePath &&
        window._vditor,
      { mountId: mount.id, filePath: path },
    );

    const acknowledged = await page.evaluate(() => ({
      baseVersion: window.state.baseVersion,
      baseContent: window.state.baseContent,
    }));
    const edited = await page.evaluate(() => {
      window.toggleAutoSave(false);
      window._vditor.setValue('edited while offline');
      window.onEditorInput();
      return window._vditor.getValue();
    });

    await context.setOffline(true);
    await page.evaluate(() => window.saveFile({ silent: true }));

    const offline = await page.evaluate((filePath) => {
      const draft = JSON.parse(localStorage.getItem(`nasmd_draft_${filePath}`));
      return {
        dirty: window.state.dirty,
        draft,
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
      };
    }, path);
    expect(offline.dirty).toBe(true);
    expect(offline.draft).toMatchObject({
      content: edited,
      mountId: mount.id,
      baseVersion: offline.baseVersion,
      baseContent: offline.baseContent,
    });
    expect(offline.draft.savedAt).toEqual(expect.any(Number));

    await context.setOffline(false);
    await expect.poll(() => changesRequests.length).toBeGreaterThan(0);
    await page.waitForFunction(
      (filePath) =>
        window.state.dirty === false && localStorage.getItem(`nasmd_draft_${filePath}`) === null,
      path,
    );
    const reconnected = await page.evaluate(
      (filePath) => ({
        dirty: window.state.dirty,
        editor: window._vditor.getValue(),
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
        originalContent: window._originalContent,
        draft: localStorage.getItem(`nasmd_draft_${filePath}`),
      }),
      path,
    );
    expect(reconnected).toMatchObject({
      dirty: false,
      draft: null,
    });
    expect(changesRequests[0]).toMatchObject({
      baseVersion: acknowledged.baseVersion,
      baseContent: acknowledged.baseContent,
      content: edited,
    });

    const response = await page.request.get(
      `/api/mounts/${mount.id}/file?path=${encodeURIComponent(path)}&_t=${Date.now()}`,
      { headers: { 'X-Admin': '1' } },
    );
    expect(response.ok()).toBe(true);
    expect(await response.text()).toBe(edited);
  } finally {
    await context.setOffline(false);
    await deleteAdminFile(page, mount.id, path);
  }
});

test('a persisted offline draft reloads with its acknowledged baseline and submits on reconnect', async ({
  context,
  page,
}) => {
  const mount = await getWritableAdminMount(page);
  const path = uniqueTestPath('collaboration-draft-reload');
  const base = 'server before reload';
  const changesRequests = [];
  await page.route(/\/api\/mounts\/[^/]+\/changes\?/, async (route) => {
    changesRequests.push(route.request().postDataJSON());
    await route.continue();
  });
  await putAdminFile(page, mount.id, path, base);

  try {
    await page.evaluate(async ({ mountId, filePath }) => window.openFile(filePath, mountId), {
      mountId: mount.id,
      filePath: path,
    });
    await page.waitForFunction(
      ({ mountId, filePath }) =>
        window.state.currentMountId === mountId &&
        window.state.currentPath === filePath &&
        window._vditor,
      { mountId: mount.id, filePath: path },
    );
    const acknowledged = await page.evaluate(() => ({
      baseVersion: window.state.baseVersion,
      baseContent: window.state.baseContent,
    }));

    const edited = await page.evaluate((value) => {
      window.toggleAutoSave(false);
      window._vditor.setValue(value);
      window.onEditorInput();
      return window._vditor.getValue();
    }, 'draft restored after reload');
    await context.setOffline(true);
    await page.evaluate(() => window.saveFile({ silent: true }));
    const persistedDraft = await page.evaluate((filePath) => {
      const draft = JSON.parse(localStorage.getItem(`nasmd_draft_${filePath}`));
      window.state.currentPath = null;
      return draft;
    }, path);
    expect(persistedDraft).toMatchObject({
      content: edited,
      mountId: mount.id,
      baseVersion: acknowledged.baseVersion,
      baseContent: acknowledged.baseContent,
    });

    await context.setOffline(false);
    await page.reload();
    await page.waitForFunction(
      ({ mountId, filePath }) =>
        window.state.currentMountId === mountId &&
        window.state.currentPath === filePath &&
        window._vditor,
      { mountId: mount.id, filePath: path },
    );
    const restored = await page.evaluate(
      (filePath) => ({
        dirty: window.state.dirty,
        editor: window._vditor.getValue(),
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
        originalContent: window._originalContent,
        draft: JSON.parse(localStorage.getItem(`nasmd_draft_${filePath}`)),
      }),
      path,
    );
    expect(restored).toMatchObject({
      dirty: true,
      editor: edited,
      baseVersion: acknowledged.baseVersion,
      baseContent: acknowledged.baseContent,
      originalContent: acknowledged.baseContent,
      draft: {
        content: edited,
        mountId: mount.id,
        baseVersion: acknowledged.baseVersion,
        baseContent: acknowledged.baseContent,
      },
    });

    await page.evaluate(() => window._reinitEditor('sv'));
    await page.waitForFunction(
      (expectedContent) =>
        window._vditor &&
        window._vditor.getCurrentMode() === 'sv' &&
        window._vditor.getValue().includes(expectedContent),
      edited,
    );
    const afterModeSwitch = await page.evaluate(() => ({
      dirty: window.state.dirty,
      editor: window._vditor.getValue(),
      baseVersion: window.state.baseVersion,
      baseContent: window.state.baseContent,
      originalContent: window._originalContent,
    }));
    expect(afterModeSwitch).toMatchObject({
      dirty: true,
      baseVersion: acknowledged.baseVersion,
      baseContent: acknowledged.baseContent,
      originalContent: acknowledged.baseContent,
    });
    expect(afterModeSwitch.editor.replace(/\r\n/g, '\n').replace(/\n+$/, '')).toBe(
      edited.replace(/\r\n/g, '\n').replace(/\n+$/, ''),
    );

    await context.setOffline(true);
    await context.setOffline(false);
    await expect.poll(() => changesRequests.length).toBeGreaterThan(0);
    await page.waitForFunction(
      (filePath) =>
        window.state.dirty === false && localStorage.getItem(`nasmd_draft_${filePath}`) === null,
      path,
    );
    expect(changesRequests[0]).toMatchObject({
      baseVersion: acknowledged.baseVersion,
      baseContent: acknowledged.baseContent,
      content: afterModeSwitch.editor,
    });

    const response = await page.request.get(
      `/api/mounts/${mount.id}/file?path=${encodeURIComponent(path)}&_t=${Date.now()}`,
      { headers: { 'X-Admin': '1' } },
    );
    expect(response.ok()).toBe(true);
    expect(await response.text()).toBe(afterModeSwitch.editor);
  } finally {
    await context.setOffline(false);
    await deleteAdminFile(page, mount.id, path);
  }
});

test('a legacy draft reloads with the fetched server baseline', async ({ page }) => {
  const mount = await getWritableAdminMount(page);
  const path = uniqueTestPath('collaboration-legacy-draft-reload');
  const base = 'server baseline for legacy draft';
  const draftContent = 'legacy draft after reload';
  await putAdminFile(page, mount.id, path, base);

  try {
    await page.evaluate(async ({ mountId, filePath }) => window.openFile(filePath, mountId), {
      mountId: mount.id,
      filePath: path,
    });
    await page.waitForFunction(
      ({ mountId, filePath }) =>
        window.state.currentMountId === mountId &&
        window.state.currentPath === filePath &&
        window._vditor,
      { mountId: mount.id, filePath: path },
    );
    const acknowledged = await page.evaluate(
      ({ filePath, mountId, content }) => {
        window.toggleAutoSave(false);
        localStorage.setItem(
          `nasmd_draft_${filePath}`,
          JSON.stringify({ content, mountId, savedAt: Date.now() }),
        );
        return {
          baseVersion: window.state.baseVersion,
          baseContent: window.state.baseContent,
        };
      },
      { filePath: path, mountId: mount.id, content: draftContent },
    );

    await page.reload();
    await page.waitForFunction(
      ({ mountId, filePath }) =>
        window.state.currentMountId === mountId &&
        window.state.currentPath === filePath &&
        window._vditor,
      { mountId: mount.id, filePath: path },
    );
    const restored = await page.evaluate(
      (filePath) => ({
        dirty: window.state.dirty,
        editor: window._vditor.getValue(),
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
        originalContent: window._originalContent,
        draft: JSON.parse(localStorage.getItem(`nasmd_draft_${filePath}`)),
      }),
      path,
    );

    expect(restored).toMatchObject({
      dirty: true,
      baseVersion: acknowledged.baseVersion,
      baseContent: base,
      originalContent: base,
      draft: {
        content: draftContent,
        mountId: mount.id,
      },
    });
    expect(restored.editor.replace(/\r\n/g, '\n').replace(/\n+$/, '')).toBe(draftContent);
    expect(restored.draft).not.toHaveProperty('baseVersion');
    expect(restored.draft).not.toHaveProperty('baseContent');
  } finally {
    await deleteAdminFile(page, mount.id, path);
  }
});

test('stale save sends its base content and preserves disjoint remote and local edits', async ({
  page,
}) => {
  const mount = await getWritableAdminMount(page);
  const path = uniqueTestPath('collaboration-stale-merge');
  const base = 'A\n\nB';
  const remote = 'A-remote\n\nB';
  const changesRequests = [];
  await page.route(/\/api\/mounts\/[^/]+\/changes\?/, async (route) => {
    changesRequests.push(route.request().postDataJSON());
    await route.continue();
  });
  await putAdminFile(page, mount.id, path, base);

  try {
    await page.evaluate(async ({ mountId, filePath }) => window.openFile(filePath, mountId), {
      mountId: mount.id,
      filePath: path,
    });
    await page.waitForFunction(() => window._vditor && window.state.currentPath !== null);
    const submittedBase = await page.evaluate(() => window.state.baseContent);
    const submittedVersion = await page.evaluate(() => window.state.baseVersion);

    await page.evaluate(() => {
      window.toggleAutoSave(false);
      window._vditor.setValue('A\n\nB-local');
      window.onEditorInput();
    });
    const submittedContent = await page.evaluate(() => window._vditor.getValue());
    await putAdminFile(page, mount.id, path, remote);
    await page.evaluate(() => window.saveFile({ silent: true }));

    const client = await page.evaluate(
      (filePath) => ({
        dirty: window.state.dirty,
        editor: window._vditor.getValue(),
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
        draft: localStorage.getItem(`nasmd_draft_${filePath}`),
      }),
      path,
    );
    const response = await page.request.get(
      `/api/mounts/${mount.id}/file?path=${encodeURIComponent(path)}&_t=${Date.now()}`,
      { headers: { 'X-Admin': '1' } },
    );
    const server = await response.text();
    const normalizedServer = server.replace(/\r\n/g, '\n').replace(/\n+$/, '');

    expect(submittedBase.replace(/\r\n/g, '\n').replace(/\n+$/, '')).toBe(base);
    expect(submittedVersion).toBeGreaterThanOrEqual(1);
    expect(changesRequests).toHaveLength(1);
    expect(changesRequests[0]).toMatchObject({
      baseVersion: submittedVersion,
      baseContent: submittedBase,
      content: submittedContent,
    });
    expect(normalizedServer).toBe('A-remote\n\nB-local');
    expect(client.dirty).toBe(false);
    expect(client.editor.replace(/\r\n/g, '\n').replace(/\n+$/, '')).toBe(normalizedServer);
    expect(client.baseContent.replace(/\r\n/g, '\n').replace(/\n+$/, '')).toBe(normalizedServer);
    expect(client.draft).toBeNull();
    expect(client.baseVersion).toBeGreaterThan(submittedVersion);
  } finally {
    await deleteAdminFile(page, mount.id, path);
  }
});

test('resync rebuilds the baseline, retains the rebased draft, and retries with that baseline', async ({
  page,
}) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const path = '/resync-retry.md';
    const base = 'A\n\nB';
    const local = 'A\n\nB-local';
    const remote = 'A-remote\n\nB';
    const rebased = 'A-remote\n\nB-local';
    const calls = [];
    let resolveRetry;
    const retryResponse = new Promise((resolve) => {
      resolveRetry = resolve;
    });
    const originalSubmitChanges = API.submitChanges;
    API.submitChanges = async (...args) => {
      calls.push({
        baseVersion: args[2],
        content: args[7],
        baseContent: args[8],
      });
      if (calls.length === 1) {
        return {
          applied: false,
          merged: false,
          resyncRequired: true,
          newVersion: 8,
          content: remote,
        };
      }
      return retryResponse;
    };
    localStorage.removeItem(`nasmd_draft_${path}`);
    Object.assign(window.state, {
      currentMountId: 'resync-mount',
      currentPath: path,
      mounts: [{ id: 'resync-mount', readonly: false }],
      localMounts: {},
      remoteFile: null,
      baseVersion: 7,
      baseContent: base,
      fileVersions: { [`resync-mount:${path}`]: 7 },
      pendingRemoteVersion: 8,
      dirty: true,
      autoSave: true,
    });
    window._originalContent = base;
    window._lastSavedContent = base;
    window._vditor = {
      value: local,
      getValue() {
        return this.value;
      },
      setValue(value) {
        this.value = value;
      },
    };

    try {
      await window.saveFile({ silent: true });
      const draft = JSON.parse(localStorage.getItem(`nasmd_draft_${path}`));
      const afterResync = {
        dirty: window.state.dirty,
        editor: window._vditor.getValue(),
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
        originalContent: window._originalContent,
        pendingRemoteVersion: window.state.pendingRemoteVersion,
        draft,
      };

      const deadline = Date.now() + 5000;
      while (calls.length < 2 && Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 20));
      }
      resolveRetry({ applied: true, merged: false, newVersion: 9, content: rebased });
      const cleanDeadline = Date.now() + 5000;
      while (window.state.dirty && Date.now() < cleanDeadline) {
        await new Promise((resolve) => setTimeout(resolve, 20));
      }
      await new Promise((resolve) => setTimeout(resolve, 50));

      return {
        calls,
        afterResync,
        final: {
          dirty: window.state.dirty,
          editor: window._vditor.getValue(),
          baseVersion: window.state.baseVersion,
          baseContent: window.state.baseContent,
          draft: localStorage.getItem(`nasmd_draft_${path}`),
        },
      };
    } finally {
      API.submitChanges = originalSubmitChanges;
      window.toggleAutoSave(false);
      localStorage.removeItem(`nasmd_draft_${path}`);
    }
  });

  expect(result.calls).toEqual([
    { baseVersion: 7, content: 'A\n\nB-local', baseContent: 'A\n\nB' },
    { baseVersion: 8, content: 'A-remote\n\nB-local', baseContent: 'A-remote\n\nB' },
  ]);
  expect(result.afterResync).toMatchObject({
    dirty: true,
    editor: 'A-remote\n\nB-local',
    baseVersion: 8,
    baseContent: 'A-remote\n\nB',
    originalContent: 'A-remote\n\nB',
    pendingRemoteVersion: null,
    draft: {
      content: 'A-remote\n\nB-local',
      mountId: 'resync-mount',
      baseVersion: 8,
      baseContent: 'A-remote\n\nB',
    },
  });
  expect(result.final).toEqual({
    dirty: false,
    editor: 'A-remote\n\nB-local',
    baseVersion: 9,
    baseContent: 'A-remote\n\nB-local',
    draft: null,
  });
});

test('an unchanged resync snapshot stops automatic retries', async ({ page }) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const path = '/unchanged-resync.md';
    const base = 'A\n\nB';
    const local = 'A\n\nB-local';
    const remote = 'A-remote\n\nB';
    const calls = [];
    const originalSubmitChanges = API.submitChanges;
    API.submitChanges = async (...args) => {
      calls.push({ baseVersion: args[2], baseContent: args[8] });
      return {
        applied: false,
        merged: false,
        resyncRequired: true,
        newVersion: 8,
        content: remote,
      };
    };
    localStorage.removeItem(`nasmd_draft_${path}`);
    Object.assign(window.state, {
      currentMountId: 'unchanged-resync-mount',
      currentPath: path,
      mounts: [{ id: 'unchanged-resync-mount', readonly: false }],
      localMounts: {},
      remoteFile: null,
      baseVersion: 7,
      baseContent: base,
      fileVersions: { [`unchanged-resync-mount:${path}`]: 7 },
      pendingRemoteVersion: null,
      dirty: true,
      autoSave: true,
    });
    window._originalContent = base;
    window._vditor = {
      value: local,
      getValue() {
        return this.value;
      },
      setValue(value) {
        this.value = value;
      },
    };

    try {
      await window.saveFile({ silent: true });
      const retryDeadline = Date.now() + 5000;
      while (calls.length < 2 && Date.now() < retryDeadline) {
        await new Promise((resolve) => setTimeout(resolve, 20));
      }
      await new Promise((resolve) => setTimeout(resolve, 1700));
      return {
        calls,
        dirty: window.state.dirty,
        editor: window._vditor.getValue(),
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
        draft: JSON.parse(localStorage.getItem(`nasmd_draft_${path}`)),
      };
    } finally {
      API.submitChanges = originalSubmitChanges;
      window.toggleAutoSave(false);
      localStorage.removeItem(`nasmd_draft_${path}`);
    }
  });

  expect(result.calls).toEqual([
    { baseVersion: 7, baseContent: 'A\n\nB' },
    { baseVersion: 8, baseContent: 'A-remote\n\nB' },
  ]);
  expect(result).toMatchObject({
    dirty: true,
    editor: 'A-remote\n\nB-local',
    baseVersion: 8,
    baseContent: 'A-remote\n\nB',
    draft: {
      content: 'A-remote\n\nB-local',
      mountId: 'unchanged-resync-mount',
      baseVersion: 8,
      baseContent: 'A-remote\n\nB',
    },
  });
});

test('a save transaction retries at most once across changing resync snapshots', async ({
  page,
}) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const path = '/bounded-resync.md';
    const calls = [];
    const originalSubmitChanges = API.submitChanges;
    API.submitChanges = async (...args) => {
      calls.push({ baseVersion: args[2], baseContent: args[8], content: args[7] });
      if (calls.length > 2) return new Promise(() => {});
      return {
        applied: false,
        merged: false,
        resyncRequired: true,
        newVersion: 7 + calls.length,
        content: `A-remote-${calls.length}\n\nB`,
      };
    };
    localStorage.removeItem(`nasmd_draft_${path}`);
    Object.assign(window.state, {
      currentMountId: 'bounded-resync-mount',
      currentPath: path,
      mounts: [{ id: 'bounded-resync-mount', readonly: false }],
      localMounts: {},
      remoteFile: null,
      baseVersion: 7,
      baseContent: 'A\n\nB',
      fileVersions: { [`bounded-resync-mount:${path}`]: 7 },
      pendingRemoteVersion: null,
      dirty: true,
      autoSave: false,
    });
    window._originalContent = 'A\n\nB';
    window._vditor = {
      value: 'A\n\nB-local',
      getValue() {
        return this.value;
      },
      setValue(value) {
        this.value = value;
      },
    };

    try {
      await window.saveFile({ silent: true });
      await new Promise((resolve) => setTimeout(resolve, 300));
      return {
        calls,
        dirty: window.state.dirty,
        editor: window._vditor.getValue(),
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
        draft: JSON.parse(localStorage.getItem(`nasmd_draft_${path}`)),
      };
    } finally {
      window.state.currentPath = null;
      API.submitChanges = originalSubmitChanges;
      localStorage.removeItem(`nasmd_draft_${path}`);
    }
  });

  expect(result.calls).toEqual([
    { baseVersion: 7, baseContent: 'A\n\nB', content: 'A\n\nB-local' },
    { baseVersion: 8, baseContent: 'A-remote-1\n\nB', content: 'A-remote-1\n\nB-local' },
  ]);
  expect(result).toMatchObject({
    dirty: true,
    editor: 'A-remote-2\n\nB-local',
    baseVersion: 9,
    baseContent: 'A-remote-2\n\nB',
    draft: {
      content: 'A-remote-2\n\nB-local',
      mountId: 'bounded-resync-mount',
      baseVersion: 9,
      baseContent: 'A-remote-2\n\nB',
    },
  });
});

test('applied save writes canonical server content back into a clean editor', async ({ page }) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const path = '/canonical-save.md';
    const base = 'A\n\nB';
    const submitted = 'A-local\n\nB';
    const canonical = 'A-local\n\n\nB';
    const originalSubmitChanges = API.submitChanges;
    API.submitChanges = async () => ({
      applied: true,
      merged: false,
      newVersion: 3,
      content: canonical,
    });
    localStorage.setItem(
      `nasmd_draft_${path}`,
      JSON.stringify({ content: submitted, mountId: 'canonical-mount', savedAt: Date.now() }),
    );
    Object.assign(window.state, {
      currentMountId: 'canonical-mount',
      currentPath: path,
      mounts: [{ id: 'canonical-mount', readonly: false }],
      localMounts: {},
      remoteFile: null,
      baseVersion: 2,
      baseContent: base,
      fileVersions: { [`canonical-mount:${path}`]: 2 },
      pendingRemoteVersion: null,
      dirty: true,
      autoSave: false,
    });
    window._originalContent = base;
    window._vditor = {
      value: submitted,
      getValue() {
        return this.value;
      },
      setValue(value) {
        this.value = value;
      },
    };

    try {
      await window.saveFile({ silent: true });
      return {
        dirty: window.state.dirty,
        editor: window._vditor.getValue(),
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
        originalContent: window._originalContent,
        fileVersion: window.state.fileVersions[`canonical-mount:${path}`],
        pendingRemoteVersion: window.state.pendingRemoteVersion,
        draft: localStorage.getItem(`nasmd_draft_${path}`),
      };
    } finally {
      API.submitChanges = originalSubmitChanges;
    }
  });

  expect(result).toEqual({
    dirty: false,
    editor: 'A-local\n\n\nB',
    baseVersion: 3,
    baseContent: 'A-local\n\n\nB',
    originalContent: 'A-local\n\n\nB',
    fileVersion: 3,
    pendingRemoteVersion: null,
    draft: null,
  });
});

test('an applied response preserves a newer in-flight pending version and starts clean catch-up', async ({
  page,
}) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const path = '/pending-during-save.md';
    let resolveSubmit;
    let resolveCatchUp;
    const submitResponse = new Promise((resolve) => {
      resolveSubmit = resolve;
    });
    const catchUpResponse = new Promise((resolve) => {
      resolveCatchUp = resolve;
    });
    const originalSubmitChanges = API.submitChanges;
    const originalGetFile = API.getFile;
    const getFileCalls = [];
    API.submitChanges = async () => submitResponse;
    API.getFile = async (...args) => {
      getFileCalls.push(args);
      return catchUpResponse;
    };
    localStorage.setItem(
      `nasmd_draft_${path}`,
      JSON.stringify({ content: 'local-v5', mountId: 'pending-save-mount', savedAt: Date.now() }),
    );
    Object.assign(window.state, {
      currentMountId: 'pending-save-mount',
      currentPath: path,
      mounts: [{ id: 'pending-save-mount', readonly: false }],
      localMounts: {},
      remoteFile: null,
      baseVersion: 4,
      baseContent: 'base-v4',
      fileVersions: { [`pending-save-mount:${path}`]: 4 },
      pendingRemoteVersion: null,
      dirty: true,
      autoSave: false,
    });
    window._originalContent = 'base-v4';
    window._vditor = {
      value: 'local-v5',
      getValue() {
        return this.value;
      },
      setValue(value) {
        this.value = value;
      },
    };

    try {
      const saving = window.saveFile({ silent: true });
      window.nasmdSync.handleRemoteEdit({
        type: 'remote_edit',
        mountId: 'pending-save-mount',
        path,
        newVersion: 9,
        changes: [{ type: 'replace', paraIdx: 0, content: 'event-v9' }],
      });
      resolveSubmit({ applied: true, merged: false, newVersion: 5, content: 'local-v5' });
      await saving;
      await new Promise((resolve) => setTimeout(resolve, 0));
      const afterApplied = {
        dirty: window.state.dirty,
        baseVersion: window.state.baseVersion,
        pendingRemoteVersion: window.state.pendingRemoteVersion,
        draft: localStorage.getItem(`nasmd_draft_${path}`),
        getFileCalls: getFileCalls.map(([mountId, filePath]) => [mountId, filePath]),
      };

      resolveCatchUp({ content: 'server-v9', version: 9, mtime: 0 });
      const deadline = Date.now() + 5000;
      while (window.state.baseVersion !== 9 && Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 20));
      }
      return {
        afterApplied,
        final: {
          dirty: window.state.dirty,
          editor: window._vditor.getValue(),
          baseVersion: window.state.baseVersion,
          baseContent: window.state.baseContent,
          pendingRemoteVersion: window.state.pendingRemoteVersion,
          draft: localStorage.getItem(`nasmd_draft_${path}`),
        },
      };
    } finally {
      API.submitChanges = originalSubmitChanges;
      API.getFile = originalGetFile;
      localStorage.removeItem(`nasmd_draft_${path}`);
    }
  });

  expect(result.afterApplied).toEqual({
    dirty: false,
    baseVersion: 5,
    pendingRemoteVersion: 9,
    draft: null,
    getFileCalls: [['pending-save-mount', '/pending-during-save.md']],
  });
  expect(result.final).toEqual({
    dirty: false,
    editor: 'server-v9',
    baseVersion: 9,
    baseContent: 'server-v9',
    pendingRemoteVersion: null,
    draft: null,
  });
});

test('manual save continues once for input typed in flight and clears the confirmed draft', async ({
  page,
}) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const path = '/in-flight-save.md';
    const base = 'A\n\nB';
    const submitted = 'A-local\n\nB';
    const canonical = 'A-local\n\nB-remote';
    const live = 'A-local\n\nB\n\nC-new';
    let resolveSubmit;
    const response = new Promise((resolve) => {
      resolveSubmit = resolve;
    });
    const calls = [];
    const originalSubmitChanges = API.submitChanges;
    API.submitChanges = async (...args) => {
      calls.push({ baseVersion: args[2], content: args[7], baseContent: args[8] });
      if (calls.length === 1) return response;
      return { applied: true, merged: false, newVersion: 6, content: args[7] };
    };
    localStorage.removeItem(`nasmd_draft_${path}`);
    Object.assign(window.state, {
      currentMountId: 'in-flight-mount',
      currentPath: path,
      mounts: [{ id: 'in-flight-mount', readonly: false }],
      localMounts: {},
      remoteFile: null,
      baseVersion: 4,
      baseContent: base,
      fileVersions: { [`in-flight-mount:${path}`]: 4 },
      pendingRemoteVersion: null,
      dirty: true,
      autoSave: false,
    });
    window._originalContent = base;
    window._vditor = {
      value: submitted,
      getValue() {
        return this.value;
      },
      setValue(value) {
        this.value = value;
      },
    };

    try {
      const saving = window.saveFile({ silent: true });
      while (!resolveSubmit) await new Promise((resolve) => setTimeout(resolve, 0));
      window._vditor.value = live;
      window.onEditorInput();
      resolveSubmit({ applied: true, merged: true, newVersion: 5, content: canonical });
      await saving;
      const deadline = Date.now() + 1000;
      while ((calls.length < 2 || window.state.dirty) && Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 20));
      }
      return {
        calls,
        dirty: window.state.dirty,
        editor: window._vditor.getValue(),
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
        originalContent: window._originalContent,
        pendingRemoteVersion: window.state.pendingRemoteVersion,
        draft: localStorage.getItem(`nasmd_draft_${path}`),
      };
    } finally {
      API.submitChanges = originalSubmitChanges;
      localStorage.removeItem(`nasmd_draft_${path}`);
    }
  });

  expect(result).toEqual({
    calls: [
      { baseVersion: 4, content: 'A-local\n\nB', baseContent: 'A\n\nB' },
      {
        baseVersion: 5,
        content: 'A-local\n\nB-remote\n\nC-new',
        baseContent: 'A-local\n\nB-remote',
      },
    ],
    dirty: false,
    editor: 'A-local\n\nB-remote\n\nC-new',
    baseVersion: 6,
    baseContent: 'A-local\n\nB-remote\n\nC-new',
    originalContent: 'A-local\n\nB-remote\n\nC-new',
    pendingRemoteVersion: null,
    draft: null,
  });
});

test('manual save continuation is bounded when input also arrives during the continuation', async ({
  page,
}) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const path = '/bounded-in-flight-save.md';
    const calls = [];
    const resolvers = [];
    const originalSubmitChanges = API.submitChanges;
    API.submitChanges = async (...args) => {
      calls.push({ baseVersion: args[2], content: args[7], baseContent: args[8] });
      return new Promise((resolve) => resolvers.push(resolve));
    };
    localStorage.removeItem(`nasmd_draft_${path}`);
    Object.assign(window.state, {
      currentMountId: 'bounded-in-flight-mount',
      currentPath: path,
      mounts: [{ id: 'bounded-in-flight-mount', readonly: false }],
      localMounts: {},
      remoteFile: null,
      baseVersion: 1,
      baseContent: 'A',
      fileVersions: { [`bounded-in-flight-mount:${path}`]: 1 },
      pendingRemoteVersion: null,
      dirty: true,
      autoSave: false,
    });
    window._originalContent = 'A';
    window._vditor = {
      value: 'A-one',
      getValue() {
        return this.value;
      },
      setValue(value) {
        this.value = value;
      },
    };

    try {
      const firstSave = window.saveFile({ silent: true });
      while (resolvers.length < 1) await new Promise((resolve) => setTimeout(resolve, 0));
      window._vditor.value = 'A-one\n\nB-two';
      window.onEditorInput();
      resolvers[0]({ applied: true, merged: false, newVersion: 2, content: 'A-one' });
      await firstSave;

      const continuationDeadline = Date.now() + 500;
      while (resolvers.length < 2 && Date.now() < continuationDeadline) {
        await new Promise((resolve) => setTimeout(resolve, 20));
      }
      if (resolvers.length < 2) {
        return { calls, missingContinuation: true };
      }
      window._vditor.value = 'A-one\n\nB-two\n\nC-three';
      window.onEditorInput();
      resolvers[1]({
        applied: true,
        merged: false,
        newVersion: 3,
        content: 'A-one\n\nB-two',
      });
      await new Promise((resolve) => setTimeout(resolve, 200));
      return {
        calls,
        missingContinuation: false,
        dirty: window.state.dirty,
        editor: window._vditor.getValue(),
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
        draft: JSON.parse(localStorage.getItem(`nasmd_draft_${path}`)),
      };
    } finally {
      window.state.currentPath = null;
      API.submitChanges = originalSubmitChanges;
      localStorage.removeItem(`nasmd_draft_${path}`);
    }
  });

  expect(result).toMatchObject({
    missingContinuation: false,
    dirty: true,
    editor: 'A-one\n\nB-two\n\nC-three',
    baseVersion: 3,
    baseContent: 'A-one\n\nB-two',
    draft: {
      content: 'A-one\n\nB-two\n\nC-three',
      mountId: 'bounded-in-flight-mount',
      baseVersion: 3,
      baseContent: 'A-one\n\nB-two',
    },
  });
  expect(result.calls).toHaveLength(2);
});

test('an in-flight save response and continuation stay bound to their originating file', async ({
  page,
}) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const pathA = '/in-flight-a.md';
    const pathB = '/in-flight-b.md';
    let resolveSubmit;
    const response = new Promise((resolve) => {
      resolveSubmit = resolve;
    });
    const calls = [];
    const originalSubmitChanges = API.submitChanges;
    API.submitChanges = async (...args) => {
      calls.push({
        mountId: args[0],
        path: args[1],
        baseVersion: args[2],
        content: args[7],
        baseContent: args[8],
      });
      return response;
    };
    const editorA = {
      value: 'A-local',
      getValue() {
        return this.value;
      },
      setValue(value) {
        this.value = value;
      },
    };
    const editorB = {
      value: 'B-local',
      getValue() {
        return this.value;
      },
      setValue(value) {
        this.value = value;
      },
    };
    Object.assign(window.state, {
      currentMountId: 'mount-a',
      currentPath: pathA,
      mounts: [
        { id: 'mount-a', readonly: false },
        { id: 'mount-b', readonly: false },
      ],
      localMounts: {},
      remoteFile: null,
      baseVersion: 1,
      baseContent: 'A-base',
      fileVersions: { ['mount-a:' + pathA]: 1, ['mount-b:' + pathB]: 10 },
      pendingRemoteVersion: null,
      dirty: true,
      autoSave: false,
    });
    window._originalContent = 'A-base';
    window._vditor = editorA;

    try {
      const saving = window.saveFile({ silent: true });
      while (calls.length < 1) await new Promise((resolve) => setTimeout(resolve, 0));
      editorA.value = 'A-local\n\nA-new';
      window.onEditorInput();

      Object.assign(window.state, {
        currentMountId: 'mount-b',
        currentPath: pathB,
        baseVersion: 10,
        baseContent: 'B-base',
        pendingRemoteVersion: null,
        dirty: false,
      });
      window._originalContent = 'B-base';
      window._lastSavedContent = 'B-base';
      window._vditor = editorB;

      resolveSubmit({ applied: true, merged: false, newVersion: 2, content: 'A-local' });
      await saving;
      await new Promise((resolve) => setTimeout(resolve, 200));
      return {
        calls,
        currentMountId: window.state.currentMountId,
        currentPath: window.state.currentPath,
        dirty: window.state.dirty,
        editor: window._vditor.getValue(),
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
        originalContent: window._originalContent,
        draftA: JSON.parse(localStorage.getItem(`nasmd_draft_${pathA}`)),
        draftB: localStorage.getItem(`nasmd_draft_${pathB}`),
      };
    } finally {
      window.state.currentPath = null;
      API.submitChanges = originalSubmitChanges;
      localStorage.removeItem(`nasmd_draft_${pathA}`);
      localStorage.removeItem(`nasmd_draft_${pathB}`);
    }
  });

  expect(result).toEqual({
    calls: [
      {
        mountId: 'mount-a',
        path: '/in-flight-a.md',
        baseVersion: 1,
        content: 'A-local',
        baseContent: 'A-base',
      },
    ],
    currentMountId: 'mount-b',
    currentPath: '/in-flight-b.md',
    dirty: false,
    editor: 'B-local',
    baseVersion: 10,
    baseContent: 'B-base',
    originalContent: 'B-base',
    draftA: {
      content: 'A-local\n\nA-new',
      mountId: 'mount-a',
      baseVersion: 1,
      baseContent: 'A-base',
      savedAt: expect.any(Number),
    },
    draftB: null,
  });
});

test('a failed save spanning editor reinitialization retains its draft and baseline', async ({
  page,
}) => {
  const mount = await getWritableAdminMount(page);
  const path = uniqueTestPath('collaboration-reinit-failure');
  await putAdminFile(page, mount.id, path, 'server-base');

  try {
    await page.evaluate(async ({ mountId, filePath }) => window.openFile(filePath, mountId), {
      mountId: mount.id,
      filePath: path,
    });
    await page.waitForFunction(
      ({ mountId, filePath }) =>
        window.state.currentMountId === mountId &&
        window.state.currentPath === filePath &&
        window._vditor,
      { mountId: mount.id, filePath: path },
    );

    const result = await page.evaluate(async (filePath) => {
      let rejectSubmit;
      const calls = [];
      const originalSubmitChanges = API.submitChanges;
      API.submitChanges = async (...args) => {
        calls.push({ baseVersion: args[2], content: args[7], baseContent: args[8] });
        return new Promise((_resolve, reject) => {
          rejectSubmit = reject;
        });
      };
      localStorage.removeItem(`nasmd_draft_${filePath}`);
      window.toggleAutoSave(false);
      const acknowledged = {
        baseVersion: window.state.baseVersion,
        baseContent: window.state.baseContent,
      };
      window._vditor.setValue('local-draft');
      window.onEditorInput();

      try {
        const saving = window.saveFile({ silent: true });
        while (!rejectSubmit) await new Promise((resolve) => setTimeout(resolve, 0));
        window._reinitEditor('sv');
        const deadline = Date.now() + 3000;
        while (
          (!window._vditor || window._vditor.getCurrentMode() !== 'sv') &&
          Date.now() < deadline
        ) {
          await new Promise((resolve) => setTimeout(resolve, 20));
        }
        const editor = window._vditor.getValue();
        rejectSubmit(new Error('network failed after mode switch'));
        await saving;
        return {
          acknowledged,
          calls,
          editor,
          dirty: window.state.dirty,
          baseVersion: window.state.baseVersion,
          baseContent: window.state.baseContent,
          originalContent: window._originalContent,
          draft: JSON.parse(localStorage.getItem(`nasmd_draft_${filePath}`)),
        };
      } finally {
        API.submitChanges = originalSubmitChanges;
        localStorage.removeItem(`nasmd_draft_${filePath}`);
      }
    }, path);

    expect(result.calls).toHaveLength(1);
    expect(result).toMatchObject({
      dirty: true,
      baseVersion: result.acknowledged.baseVersion,
      baseContent: result.acknowledged.baseContent,
      originalContent: result.acknowledged.baseContent,
      draft: {
        content: result.editor,
        mountId: mount.id,
        baseVersion: result.acknowledged.baseVersion,
        baseContent: result.acknowledged.baseContent,
        savedAt: expect.any(Number),
      },
    });
  } finally {
    await deleteAdminFile(page, mount.id, path);
  }
});

test('network and invalid save responses retain dirty content and its draft', async ({ page }) => {
  await page.goto('/admin');

  const result = await page.evaluate(async () => {
    const originalSubmitChanges = API.submitChanges;
    const results = [];
    const cases = [
      ['network', async () => Promise.reject(new TypeError('network unavailable'))],
      ['invalid', async () => ({ applied: true, newVersion: 'invalid', content: null })],
      [
        'contradictory',
        async () => ({
          applied: true,
          resyncRequired: true,
          newVersion: 12,
          content: 'contradictory-server',
        }),
      ],
    ];

    try {
      for (const [name, responder] of cases) {
        const path = `/${name}-save-response.md`;
        const base = `${name}-base`;
        const local = `${name}-local`;
        API.submitChanges = responder;
        localStorage.removeItem(`nasmd_draft_${path}`);
        Object.assign(window.state, {
          currentMountId: `${name}-mount`,
          currentPath: path,
          mounts: [{ id: `${name}-mount`, readonly: false }],
          localMounts: {},
          remoteFile: null,
          baseVersion: 11,
          baseContent: base,
          fileVersions: { [`${name}-mount:${path}`]: 11 },
          pendingRemoteVersion: null,
          dirty: true,
          autoSave: false,
        });
        window._originalContent = base;
        window._vditor = {
          value: local,
          getValue() {
            return this.value;
          },
          setValue(value) {
            this.value = value;
          },
        };

        await window.saveFile({ silent: true });
        results.push({
          name,
          dirty: window.state.dirty,
          editor: window._vditor.getValue(),
          baseVersion: window.state.baseVersion,
          baseContent: window.state.baseContent,
          draft: JSON.parse(localStorage.getItem(`nasmd_draft_${path}`)),
        });
        localStorage.removeItem(`nasmd_draft_${path}`);
      }
    } finally {
      API.submitChanges = originalSubmitChanges;
    }
    return results;
  });

  expect(result).toEqual([
    {
      name: 'network',
      dirty: true,
      editor: 'network-local',
      baseVersion: 11,
      baseContent: 'network-base',
      draft: expect.objectContaining({
        content: 'network-local',
        mountId: 'network-mount',
        baseVersion: 11,
        baseContent: 'network-base',
      }),
    },
    {
      name: 'invalid',
      dirty: true,
      editor: 'invalid-local',
      baseVersion: 11,
      baseContent: 'invalid-base',
      draft: expect.objectContaining({
        content: 'invalid-local',
        mountId: 'invalid-mount',
        baseVersion: 11,
        baseContent: 'invalid-base',
      }),
    },
    {
      name: 'contradictory',
      dirty: true,
      editor: 'contradictory-local',
      baseVersion: 11,
      baseContent: 'contradictory-base',
      draft: expect.objectContaining({
        content: 'contradictory-local',
        mountId: 'contradictory-mount',
        baseVersion: 11,
        baseContent: 'contradictory-base',
      }),
    },
  ]);
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
