import { expect, test } from '@playwright/test';
import { inspectRotaryLayout } from '../support/rotary-layout';
import { viewports } from '../support/viewports';

for (const scene of ['cubes', 'horizon']) {
  test(`${scene} keeps song progress inside the curved slot after resizing and navigation`, async ({
    page,
  }) => {
    await page.route('**/song/media/outer/**', (route) => route.abort());
    await page.goto(`/preview/?scene=${scene}&graphics=poster&skipIntro=1`);
    await page.evaluate(() => document.fonts.ready);
    const deck = page.getByRole('region', { name: 'Information slots' });
    await deck.press('ArrowDown');
    await expect(deck).toHaveAttribute('data-card-index', '1');
    await expect(deck).toHaveAttribute('data-moving', 'false');
    for (const { width, height } of viewports) {
      await page.setViewportSize({ width, height });
      await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
    }
    // Prove the silhouette oracle rejects the previously overflowing placement.
    const progress = page.getByRole('progressbar', { name: 'Song progress' });
    await progress.evaluate((bar) => {
      bar.style.left = '0px';
    });
    expect(await page.evaluate(inspectRotaryLayout)).toContain(
      'Song progress escapes the painted contour clearance',
    );
    await progress.evaluate((bar) => bar.style.removeProperty('left'));
    await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
    await deck.press('ArrowDown');
    await expect(deck).toHaveAttribute('data-card-index', '2');
    await expect(
      page
        .getByRole('button', { name: 'GitHub', exact: true })
        .locator('.elsewhere-mark'),
    ).toHaveAttribute('data-mark', 'editorial');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await deck.press('ArrowUp');
    await page.setViewportSize({ width: 320, height: 320 });
    await expect(deck).toHaveAttribute('data-card-index', '1');
    await expect(deck).toHaveAttribute('data-moving', 'false');
    await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
  });
}
