import { expect, test } from '@playwright/test';
import { inspectOrbitLayout } from '../support/orbit-layout';
import { inspectRotaryLayout } from '../support/rotary-layout';

test('detail studies preserve reading, hit areas and contour geometry across both themes', async ({
  page,
}) => {
  test.setTimeout(180000);
  await page.route('**/song/media/outer/**', (route) => route.abort());
  for (const details of ['etch', 'flow', 'orbit']) {
    for (const scene of ['cubes', 'horizon']) {
      await page.goto(
        `/preview/?scene=${scene}&details=${details}&finish=original&graphics=poster&skipIntro=1`,
      );
      await expect(page.locator('main')).toHaveAttribute(
        'data-details',
        details,
      );
      await page.evaluate(() => document.fonts.ready);
      for (const size of [
        { width: 320, height: 568 },
        { width: 390, height: 400 },
        { width: 640, height: 450 },
        { width: 1440, height: 900 },
      ]) {
        await page.setViewportSize(size);
        await page.locator('.rotary-deck').press('Home');
        for (let index = 0; index < 4; index++) {
          await expect(page.locator('.rotary-deck')).toHaveAttribute(
            'data-moving',
            'false',
          );
          await expect
            .poll(() => page.evaluate(inspectOrbitLayout))
            .toEqual([]);
          await expect
            .poll(() => page.evaluate(inspectRotaryLayout))
            .toEqual([]);
          if (index < 3) await page.locator('.rotary-deck').press('ArrowDown');
        }
      }
      await page.locator('.rotary-deck').press('ArrowUp');
      await expect(page.locator('.rotary-deck')).toHaveAttribute(
        'data-moving',
        'false',
      );
      const link = page.getByRole('link', { name: 'Blog', exact: true });
      await link.focus();
      await expect(link).toBeFocused();
      const reading = await link.evaluate((node) => {
        const label = getComputedStyle(
          node.querySelector('.orbit-rail-label')!,
        );
        return {
          target: node.getBoundingClientRect().height,
          opacity: label.opacity,
        };
      });
      expect(reading.target).toBeGreaterThanOrEqual(44);
      expect(reading.opacity).toBe('1');
      // Rapid browsing cancels decorative entry without leaving partial glyphs.
      await page.locator('.rotary-deck').press('ArrowDown');
      await page.locator('.rotary-deck').press('ArrowUp');
      await page.locator('.rotary-deck').press('Home');
      await page.setViewportSize({ width: 360, height: 640 });
      await expect(page.locator('.rotary-deck')).toHaveAttribute(
        'data-moving',
        'false',
      );
      await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
    }
  }
});

test('detail feedback settles at idle and respects reduced motion and hidden pages', async ({
  page,
}) => {
  await page.route('**/song/media/outer/**', (route) => route.abort());
  for (const details of ['etch', 'flow', 'orbit']) {
    await page.goto(
      `/preview/?scene=horizon&details=${details}&finish=original&graphics=poster&skipIntro=1`,
    );
    await page.locator('.rotary-deck').press('ArrowDown');
    await page.locator('.rotary-deck').press('ArrowDown');
    const activeAnimations = () =>
      page
        .locator('.rotary-card-active')
        .evaluate(
          (node) =>
            node
              .getAnimations({ subtree: true })
              .filter((animation) => animation.playState === 'running').length,
        );
    await expect.poll(activeAnimations).toBe(0);
    await page.getByRole('link', { name: 'Blog', exact: true }).focus();
    await expect.poll(activeAnimations).toBe(0);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await expect(page.locator('main')).toHaveAttribute(
      'data-detail-motion',
      'off',
    );
    await page.locator('.rotary-deck').press('End');
    await expect.poll(activeAnimations).toBe(0);
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', {
        configurable: true,
        value: 'hidden',
      });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await expect(page.locator('main')).toHaveAttribute(
      'data-detail-motion',
      'off',
    );
    await expect.poll(activeAnimations).toBe(0);
    await page.evaluate(() => {
      Reflect.deleteProperty(document, 'visibilityState');
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await expect(page.locator('main')).toHaveAttribute(
      'data-detail-motion',
      'on',
    );
  }
});
