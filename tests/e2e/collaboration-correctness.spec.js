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

test('paragraph contract preserves frontmatter delimiters', async ({ page }) => {
  await page.goto('/admin');

  for (const testCase of paragraphSplitCases.filter((item) => item.delimiters)) {
    const result = await page.evaluate((text) => {
      const split = window.nasmdDiff.splitParagraphsWithDelims(text);
      return {
        ...split,
        roundTrip: split.paragraphs
          .map((paragraph, idx) => paragraph + split.delimiters[idx])
          .join(''),
      };
    }, testCase.text);

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
  ];

  const results = await page.evaluate((roundTripCases) => {
    return roundTripCases.map(([name, base, target]) => {
      const changes = window.nasmdDiff.computeParagraphDiff(base, target);
      return [name, window.nasmdDiff.applyChangesLocally(base, changes)];
    });
  }, cases);

  expect(results).toEqual(cases.map(([name, , target]) => [name, target]));
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
    ]);

    expect(results).toEqual([
      [{ type: 'replace', paraIdx: 3, content: 'C-local' }],
      [{ type: 'replace', paraIdx: 1, content: 'C-local' }],
      [{ type: 'insert', paraIdx: 1, content: 'B-local' }],
      [],
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
          'delete-with-delimiter',
          () =>
            window.nasmdDiff.transformParagraphChanges(
              [{ type: 'delete', paraIdx: 0, delimiter: '' }],
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
      ['delete-with-delimiter', true],
      ['invalid-accumulated-change', true],
      ['unsafe-change-index', true],
    ]);
  });
});
