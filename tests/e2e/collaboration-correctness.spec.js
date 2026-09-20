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
});
