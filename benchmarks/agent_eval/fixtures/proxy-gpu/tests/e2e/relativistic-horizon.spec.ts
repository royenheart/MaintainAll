import { test, expect, type Page } from '@playwright/test';
import sharp from 'sharp';

const url = (story: string, query = '') =>
  `http://127.0.0.1:6006/iframe.html?id=explorations-orbit-study--${story}${query}`;
async function pixels(page: Page) {
  const screenshot = await page.locator('canvas').screenshot();
  return sharp(screenshot)
    .removeAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
}
const difference = (a: Buffer, b: Buffer) => {
  let sum = 0;
  for (let i = 0; i < a.length; i++) sum += Math.abs(a[i]! - b[i]!);
  return sum / a.length;
};

test('optical postprocessing preserves the authored cube palette', async ({
  page,
}) => {
  await page.setViewportSize({ width: 640, height: 480 });
  const shots: Buffer[] = [];
  for (const renderer of ['baseline', 'relativistic']) {
    await page.goto(
      url('cubes-open', `&capture=1&args=horizonRenderer:${renderer}`),
    );
    await expect(page.locator('main')).toHaveAttribute(
      'data-renderer',
      'webgl',
    );
    shots.push((await pixels(page)).data);
  }
  // Linear alpha blending changes edge pixels; an unintended tone curve shifts the whole image.
  expect(difference(shots[0]!, shots[1]!)).toBeLessThan(6);
});

test('optical tables produce a dark capture region, two disk images and a working inclination control', async ({
  page,
}) => {
  test.setTimeout(45000);
  await page.setViewportSize({ width: 960, height: 640 });
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await page.goto(url('horizon-open', '&capture=1'));
  await expect(page.locator('main')).toHaveAttribute('data-renderer', 'webgl');
  const first = await pixels(page);
  const luminance = (x: number, y: number) => {
    const i =
      3 *
      (Math.round(y * first.info.height) * first.info.width +
        Math.round(x * first.info.width));
    return (
      0.2126 * first.data[i]! +
      0.7152 * first.data[i + 1]! +
      0.0722 * first.data[i + 2]!
    );
  };
  expect(luminance(0.5, 0.42)).toBeLessThan(15);
  expect(luminance(0.5, 0.2)).toBeGreaterThan(60);
  expect(luminance(0.5, 0.64)).toBeGreaterThan(60);
  await page.goto(url('horizon-open', '&capture=1&args=inclination:28'));
  await expect(page.locator('main')).toHaveAttribute('data-renderer', 'webgl');
  const tilted = await pixels(page);
  expect(difference(first.data, tilted.data)).toBeGreaterThan(10);
  await page.goto(url('horizon-open', '&capture=1'));
  await expect(page.locator('main')).toHaveAttribute('data-renderer', 'webgl');
  expect(difference(first.data, (await pixels(page)).data)).toBeLessThan(0.1);
  expect(errors).toEqual([]);
});

test('native runtime animates disk emission and keeps resources bounded after resize', async ({
  page,
}) => {
  await page.setViewportSize({ width: 640, height: 480 });
  await page.goto(url('horizon-open'));
  await expect(page.locator('main')).toHaveAttribute('data-renderer', 'webgl');
  const first = await pixels(page);
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene?.frames ?? 0))
    .toBeGreaterThan(15);
  expect(difference(first.data, (await pixels(page)).data)).toBeGreaterThan(
    0.05,
  );
  const resources = await page.evaluate(() => window.__orbitScene!.textures);
  for (const viewport of [
    { width: 390, height: 400 },
    { width: 768, height: 1024 },
    { width: 640, height: 480 },
  ]) {
    await page.setViewportSize(viewport);
    await expect
      .poll(() => page.evaluate(() => window.__orbitScene!.textures))
      .toBeLessThanOrEqual(resources + 2);
  }
  expect(await page.evaluate(() => window.__orbitScene!.calls)).toBeLessThan(
    30,
  );
});

test('invalid optical data falls back without losing the compact deck', async ({
  page,
}) => {
  await page.route('**/optics/deflection.dat*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/octet-stream',
      body: 'invalid optical data',
    }),
  );
  await page.goto(url('horizon-open'));
  await expect(page.locator('main')).toHaveAttribute(
    'data-renderer',
    'fallback',
  );
  await expect(page.locator('canvas')).toHaveCount(0);
  await page.getByRole('button', { name: 'Next card', exact: true }).click();
  await expect(
    page.getByRole('link', { name: 'Blog', exact: true }),
  ).toBeVisible();
});

test('late optical requests keep the live canvas instead of forcing the damaged fallback', async ({
  page,
}) => {
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route('**/optics/*.dat*', async (route) => {
    await pending;
    await route.continue().catch(() => {});
  });
  await page.clock.install();
  await page.goto(url('horizon-open'));
  await expect(page.locator('main')).toHaveAttribute(
    'data-renderer',
    'loading',
  );
  await page.clock.fastForward(46000);
  await expect(page.locator('main')).toHaveAttribute(
    'data-renderer',
    'loading',
  );
  await expect(page.locator('main')).toHaveAttribute(
    'data-graphics-slow',
    'true',
  );
  await expect(page.locator('canvas')).toHaveCount(1);
  release();
  await page.clock.fastForward(1000);
  await expect(page.locator('main')).toHaveAttribute('data-renderer', 'webgl');
  await expect(page.locator('canvas')).toHaveCount(1);
});
