import { expect, test } from '@playwright/test';
import { inspectOrbitLayout } from '../support/orbit-layout';
import { inspectRotaryLayout } from '../support/rotary-layout';

test('diagonal links preserve containment, semantics and reverse interrupted hover', async ({
  page,
}) => {
  test.setTimeout(90000);
  await page.route('**/song/media/outer/**', (route) => route.abort());
  for (const rails of ['glide', 'tether', 'relay']) {
    for (const scene of ['cubes', 'horizon']) {
      await page.goto(
        `/preview/?scene=${scene}&rails=${rails}&finish=original&graphics=poster&skipIntro=1`,
      );
      await expect(page.locator('main')).toHaveAttribute(
        'data-details',
        'flow',
      );
      await page.evaluate(() => document.fonts.ready);
      await page.locator('.rotary-deck').press('ArrowDown');
      await page.locator('.rotary-deck').press('ArrowDown');
      await expect(page.locator('.rotary-deck')).toHaveAttribute(
        'data-moving',
        'false',
      );
      for (const size of [
        { width: 320, height: 320 },
        { width: 390, height: 844 },
        { width: 639, height: 450 },
        { width: 640, height: 450 },
        { width: 1440, height: 900 },
      ]) {
        await page.setViewportSize(size);
        await expect.poll(() => page.evaluate(inspectOrbitLayout)).toEqual([]);
        await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
        await expect
          .poll(() =>
            page.locator('.rotary-card-active').evaluate((card) => {
              const bounds = card.getBoundingClientRect();
              return [...card.querySelectorAll('.orbit-rail-axis')].every(
                (axis) => {
                  const r = axis.getBoundingClientRect();
                  return (
                    r.top >= bounds.top &&
                    r.bottom <= bounds.bottom &&
                    r.left >= bounds.left &&
                    r.right <= bounds.right
                  );
                },
              );
            }),
          )
          .toBe(true);
      }
      const link = page.getByRole('link', { name: 'GitHub', exact: true });
      await expect(link).toHaveCount(1);
      const label = link.locator('.orbit-rail-label').first();
      const moving = rails === 'tether' ? label.locator('span') : label;
      const before = await moving.evaluate(
        (node) => getComputedStyle(node).transform,
      );
      await link.hover();
      await expect
        .poll(() => moving.evaluate((node) => getComputedStyle(node).transform))
        .not.toBe(before);
      await page.mouse.move(10, 10);
      await expect
        .poll(() => moving.evaluate((node) => getComputedStyle(node).transform))
        .toBe(before);
      await link.focus();
      await expect
        .poll(() => moving.evaluate((node) => getComputedStyle(node).transform))
        .not.toBe(before);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await expect
        .poll(() => moving.evaluate((node) => getComputedStyle(node).transform))
        .toBe(before);
      await page.emulateMedia({ reducedMotion: 'no-preference' });
    }
  }
});
