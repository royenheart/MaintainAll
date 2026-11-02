import { expect, test, type Page } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { ORBIT_PIXEL_BUDGET } from '../../src/scenes/render-budget';

async function expectStopped(page: Page) {
  // A late media state or resize may invalidate one demand frame. Require a
  // settled idle interval, rather than rejecting that legitimate repaint.
  await expect
    .poll(async () => {
      const before = await page.evaluate(() => window.__orbitScene!);
      await page.waitForTimeout(500);
      const after = await page.evaluate(() => window.__orbitScene!);
      return {
        frames: after.frames - before.frames,
        time: after.time - before.time,
      };
    })
    .toEqual({ frames: 0, time: 0 });
}

test('standalone preview bounds pixels, skips invisible draws and suspends idle rendering', async ({
  page,
}) => {
  test.setTimeout(90000);
  await page.route('**/song/media/outer/**', (route) =>
    route.fulfill({
      path: fileURLToPath(
        new URL(
          '../../src/explorations/audio-fixtures/steady-tone.mp3',
          import.meta.url,
        ),
      ),
      contentType: 'audio/mpeg',
    }),
  );
  await page.addInitScript(() => {
    const NativeAudio = window.Audio;
    window.Audio = class extends NativeAudio {
      constructor() {
        super();
        this.loop = true;
      }
    };
  });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/preview/?scene=cubes&skipIntro=1');
  const root = page.locator('main');
  await expect(root).toHaveAttribute('data-renderer', 'webgl', {
    timeout: 30000,
  });
  const withinBudget = () =>
    page.evaluate(() => {
      const canvas = document.querySelector('canvas')!;
      return canvas.width * canvas.height;
    });
  await expect.poll(withinBudget).toBeLessThanOrEqual(ORBIT_PIXEL_BUDGET);
  await expectStopped(page);
  await page.locator('canvas').evaluate((node) => {
    node.dataset.original = 'true';
  });

  await page.setViewportSize({ width: 800, height: 500 });
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene?.calls))
    .toBe(3);
  await page.locator('.orbit-disc').click({ position: { x: 12, y: 50 } });
  await page.locator('.rotary-deck').press('End');
  await expect(page.locator('.orbit-transport-sound')).toBeEnabled();
  const play = page.getByRole('button', { name: 'Play music', exact: true });
  if (await play.isVisible()) await play.click();
  await expect(page.locator('.orbit-wheel')).toHaveAttribute(
    'data-playing',
    'true',
  );
  await page.getByRole('button', { name: 'Pause music', exact: true }).click();
  await expect(page.locator('.orbit-wheel')).toHaveAttribute(
    'data-playing',
    'false',
  );
  await expect(page.locator('.orbit-spectrum')).toHaveAttribute(
    'data-response',
    'rest',
  );
  const pausedFrame = await page.evaluate(() => window.__orbitScene!);
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene!.frames))
    .toBeGreaterThan(pausedFrame.frames + 2);
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene!.time))
    .toBeGreaterThan(pausedFrame.time);
  await expect(
    page.getByRole('button', { name: 'Pause background' }),
  ).toHaveCount(0);

  // Exercise the visibility handler deterministically, independently of the
  // headless browser's own background-tab scheduling policy.
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expectStopped(page);
  await page.evaluate(() => {
    Reflect.deleteProperty(document, 'visibilityState');
    document.dispatchEvent(new Event('visibilitychange'));
  });
  const before = await page.evaluate(() => window.__orbitScene!);
  await page.locator('.rotary-deck').press('End');
  await page.getByRole('button', { name: 'Next scene', exact: true }).click();
  await expect(root).toHaveAttribute('data-scene', 'horizon', {
    timeout: 20000,
  });
  await expect(root).toHaveAttribute('data-transitioning', 'false');
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene?.calls))
    .toBe(11);
  await expect.poll(withinBudget).toBeLessThanOrEqual(ORBIT_PIXEL_BUDGET);
  await page.locator('.orbit-disc').click({ position: { x: 12, y: 50 } });
  await page.locator('.rotary-deck').press('End');
  await page.getByRole('button', { name: 'Next scene', exact: true }).click();
  await expect(root).toHaveAttribute('data-scene', 'cubes', {
    timeout: 20000,
  });
  await expect(root).toHaveAttribute('data-transitioning', 'false');
  await expect(page.locator('canvas[data-original=true]')).toHaveCount(1);
  const after = await page.evaluate(() => window.__orbitScene!);
  expect(after.geometries).toBeLessThanOrEqual(before.geometries + 2);
  // The first horizon visit allocates the previously unused bloom pyramid.
  // Compare repeated warm cycles, not an unallocated cube-only target.
  expect(after.textures).toBeLessThanOrEqual(14);
  for (const scene of ['horizon', 'cubes']) {
    await page.locator('.orbit-disc').click({ position: { x: 12, y: 50 } });
    await page.locator('.rotary-deck').press('End');
    await page
      .getByRole('button', {
        name: 'Next scene',
        exact: true,
      })
      .click();
    await expect(root).toHaveAttribute('data-scene', scene, { timeout: 20000 });
    await expect(root).toHaveAttribute('data-transitioning', 'false');
  }
  const repeated = await page.evaluate(() => window.__orbitScene!);
  expect(repeated.geometries).toBeLessThanOrEqual(after.geometries);
  expect(repeated.textures).toBeLessThanOrEqual(after.textures + 1);
  await expect(page.locator('canvas[data-original=true]')).toHaveCount(1);
  await test.info().attach('standalone-render-budget.json', {
    body: JSON.stringify({ before, after, repeated }),
    contentType: 'application/json',
  });
});
