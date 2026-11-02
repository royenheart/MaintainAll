import { expect, test } from '@playwright/test';
import { inspectOrbitLayout } from '../support/orbit-layout';
import { inspectRotaryLayout } from '../support/rotary-layout';

for (const finish of ['inset', 'nameplate', 'seam']) {
  test(`${finish} keeps every card usable across sizes, themes and interrupted feedback`, async ({
    page,
  }) => {
    test.setTimeout(120000);
    await page.route('**/song/media/outer/**', (route) => route.abort());
    for (const scene of ['cubes', 'horizon']) {
      await page.goto(
        `/preview/?scene=${scene}&finish=${finish}&graphics=poster&skipIntro=1`,
      );
      await expect(page.locator('main')).toHaveAttribute(
        'data-card-finish',
        finish,
      );
      await page.evaluate(() => document.fonts.ready);
      const deck = page.locator('.rotary-deck');
      for (const size of [
        { width: 320, height: 320 },
        { width: 390, height: 844 },
        { width: 639, height: 450 },
        { width: 640, height: 450 },
        { width: 768, height: 1024 },
        { width: 1440, height: 900 },
      ]) {
        await page.setViewportSize(size);
        await deck.press('Home');
        for (let card = 0; card < 4; card++) {
          await expect(deck).toHaveAttribute('data-moving', 'false');
          await expect
            .poll(() => page.evaluate(inspectOrbitLayout))
            .toEqual([]);
          await expect
            .poll(() => page.evaluate(inspectRotaryLayout))
            .toEqual([]);
          if (card === 2) {
            await expect
              .poll(() =>
                page.locator('.orbit-segment-label').evaluateAll((labels) =>
                  labels.every((label) => {
                    const r = label.getBoundingClientRect(),
                      link = label.closest('a')!.getBoundingClientRect();
                    return (
                      r.left >= link.left - 1 &&
                      r.right <= link.right + 1 &&
                      r.top >= link.top &&
                      r.bottom <= link.bottom
                    );
                  }),
                ),
              )
              .toBe(true);
          }
          if (card < 3) await deck.press('ArrowDown');
        }
      }
      await deck.press('Home');
      await deck.press('ArrowDown');
      await deck.press('ArrowDown');
      await expect(deck).toHaveAttribute('data-moving', 'false');
      const link = page.getByRole('button', { name: 'GitHub', exact: true });
      const label = link.locator('.orbit-segment-label');
      const paint = link.locator('.orbit-segment-paint');
      const normal = await label.evaluate(
        (node) => getComputedStyle(node).transform,
      );
      const hit = await link.boundingBox();
      await link.hover();
      if (finish === 'nameplate') {
        await expect
          .poll(() =>
            paint.evaluate((node) => getComputedStyle(node, '::after').display),
          )
          .toBe('none');
      } else
        await expect
          .poll(() =>
            paint.evaluate((node) =>
              Number(getComputedStyle(node, '::after').opacity),
            ),
          )
          .toBe(1);
      expect(await link.boundingBox()).toEqual(hit);
      if (finish === 'inset')
        await expect
          .poll(() =>
            label.evaluate((node) => getComputedStyle(node).transform),
          )
          .not.toBe(normal);
      await page.mouse.move(5, 5);
      await expect
        .poll(() => label.evaluate((node) => getComputedStyle(node).transform))
        .toBe(normal);
      await link.focus();
      if (finish === 'nameplate') {
        await expect
          .poll(() =>
            paint.evaluate((node) => getComputedStyle(node, '::after').display),
          )
          .toBe('none');
      } else
        await expect
          .poll(() =>
            paint.evaluate((node) =>
              Number(getComputedStyle(node, '::after').opacity),
            ),
          )
          .toBe(1);
      // Resize during a reversal, then verify the settled contour and controls.
      await deck.press('ArrowDown');
      await page.setViewportSize({ width: 390, height: 700 });
      await deck.press('ArrowUp');
      await expect(deck).toHaveAttribute('data-moving', 'false');
      await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await expect(page.locator('main')).toHaveAttribute(
        'data-detail-motion',
        'off',
      );
      await link.focus();
      await expect
        .poll(() => label.evaluate((node) => getComputedStyle(node).transform))
        .toBe('none');
      await expect.poll(() => page.evaluate(inspectOrbitLayout)).toEqual([]);
      await page.emulateMedia({ reducedMotion: 'no-preference' });
    }
  });
}
