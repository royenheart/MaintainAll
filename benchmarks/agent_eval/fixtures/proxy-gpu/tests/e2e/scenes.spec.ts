import { test, expect } from '@playwright/test';
import { inspectLayout } from '../support/layout';

test('graphics chunk failure preserves scene controls and content', async ({
  page,
}) => {
  await page.route('**/*SceneCanvas*.js', (route) => route.abort());
  await page.goto('/original/');
  await expect(page.locator('.scene-experience')).toHaveAttribute(
    'data-renderer',
    'fallback',
  );
  await page.getByRole('button', { name: 'Switch scene' }).click();
  await expect(page.locator('.scene-experience')).toHaveAttribute(
    'data-scene',
    'horizon',
  );
  await expect(page.locator('.scene-poster')).toBeVisible();
});

test('reduced motion keeps the scene still and controls accessible', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/original/?graphics=poster');
  await expect(page.locator('.scene-experience')).toHaveAttribute(
    'data-paused',
    'true',
  );
  await expect(
    page.getByRole('button', { name: 'Pause animation' }),
  ).toBeDisabled();
  await page.getByRole('button', { name: 'Switch scene' }).click();
  await expect
    .poll(async () => (await page.evaluate(inspectLayout)).issues)
    .toEqual([]);
});

test('real scenes render, pause, resize, and handle context loss', async ({
  page,
  browserName,
}, testInfo) => {
  test.skip(
    browserName !== 'chromium',
    'GPU smoke uses the available Chromium software renderer; other engines run layout and failure tests.',
  );
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/original/?capture=1');
  await expect(page.locator('.scene-experience')).toHaveAttribute(
    'data-renderer',
    'webgl',
  );
  await expect(page.locator('canvas')).toHaveCount(1);
  await expect(page.locator('.scene-canvas')).toHaveCSS('opacity', '1');
  for (const viewport of [
    { name: 'desktop', width: 1440, height: 900 },
    { name: 'phone', width: 390, height: 844 },
    { name: 'tablet', width: 768, height: 1024 },
  ]) {
    await page.setViewportSize(viewport);
    for (const scene of ['cubes', 'horizon']) {
      if (
        (await page.locator('.scene-experience').getAttribute('data-scene')) !==
        scene
      ) {
        await page.getByRole('button', { name: 'Switch scene' }).click();
      }
      await expect
        .poll(async () => page.evaluate(() => window.__sceneMetrics?.scene))
        .toBe(scene);
      await expect
        .poll(async () => (await page.evaluate(inspectLayout)).issues)
        .toEqual([]);
      await page.screenshot({
        path: testInfo.outputPath(`${scene}-${viewport.name}.png`),
      });
    }
  }
  for (let index = 0; index < 20; index++)
    await page.getByRole('button', { name: 'Switch scene' }).click();
  await expect(page.locator('canvas')).toHaveCount(1);
  expect(errors).toEqual([]);
  await page.locator('canvas').evaluate((canvas) => {
    canvas.dispatchEvent(new Event('webglcontextlost', { cancelable: true }));
  });
  await expect(page.locator('.scene-experience')).toHaveAttribute(
    'data-renderer',
    'fallback',
  );
});

test('unsupported WebGL falls back without losing navigation', async ({
  page,
}) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      this: HTMLCanvasElement,
      ...args: Parameters<typeof original>
    ) {
      if (String(args[0]).startsWith('webgl')) return null;
      return original.apply(this, args);
    } as typeof original;
  });
  await page.goto('/original/');
  await expect(page.locator('.scene-experience')).toHaveAttribute(
    'data-renderer',
    'fallback',
  );
  await expect(
    page.getByRole('link', { name: 'Blog', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Switch scene' }).click();
  await expect(page.locator('.scene-experience')).toHaveAttribute(
    'data-scene',
    'horizon',
  );
});
