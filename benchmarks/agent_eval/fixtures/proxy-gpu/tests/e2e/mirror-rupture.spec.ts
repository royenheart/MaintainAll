import { expect, test, type Page } from '@playwright/test';
import sharp from 'sharp';

const url = (story: string) =>
  `http://127.0.0.1:6006/iframe.html?id=explorations-scene-formation--${story}&capture=1`;
async function open(page: Page, story: string) {
  await page.goto(url(story));
  await expect(page.locator('main')).toHaveAttribute('data-ready', 'true');
}
async function release(page: Page, value: number) {
  const blend = +(1 - value).toFixed(3);
  await page.getByRole('slider').fill(String(blend));
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene!.blend))
    .toBe(blend);
}
async function pixels(page: Page) {
  return sharp(
    await page
      .locator('canvas')
      .screenshot({ style: '.formation-controls { visibility: hidden; }' }),
  )
    .removeAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
}
const difference = (a: Buffer, b: Buffer) =>
  a.reduce((sum, value, index) => sum + Math.abs(value - b[index]!), 0) /
  a.length;

test('upright wavefronts keep multiple parallel curves while propagating away from the center', async ({
  page,
}) => {
  await page.setViewportSize({ width: 960, height: 640 });
  await open(page, 'upright-waves');
  const distances: number[] = [];
  for (const q of [0.36, 0.48]) {
    await release(page, q);
    const {
      data,
      info: { width, height },
    } = await pixels(page);
    const light = (x: number, y: number) => {
      const offset = (y * width + x) * 3;
      return (data[offset]! + data[offset + 1]! + data[offset + 2]!) / 3;
    };
    let gx = 0,
      gy = 0,
      weightedDistance = 0,
      total = 0;
    for (let y = 1; y < height - 1; y++) {
      for (let x = 1; x < width - 1; x++) {
        const value = light(x, y);
        gx += Math.abs(value - light(x + 1, y));
        gy += Math.abs(value - light(x, y + 1));
        weightedDistance += value * Math.abs(x - width / 2);
        total += value;
      }
    }
    // Upright curves have predominantly horizontal image gradients.
    expect(gx / gy).toBeGreaterThan(4);
    distances.push(weightedDistance / total);
    for (const row of [0.3, 0.5, 0.7]) {
      let runs = 0,
        lit = false;
      for (let x = 0; x < width; x++) {
        const next = light(x, Math.floor(height * row)) > 45;
        if (next && !lit) runs++;
        lit = next;
      }
      expect(runs).toBeGreaterThanOrEqual(4);
      expect(runs).toBeLessThanOrEqual(10);
    }
  }
  expect(distances[1]! - distances[0]!).toBeGreaterThan(40);
});

for (const [complete, source] of [
  ['mirror-and-waves', 'mirror-surface'],
  ['radiating-mirror', 'radiating-surface'],
  ['streaming-mirror', 'streaming-surface'],
  ['glitch-and-fracture', 'glitch-surface'],
]) {
  test(`${complete}: fractured source moves without wave emission and retains both resting endpoints`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });
    await open(page, complete!);
    const rest = await pixels(page);
    await release(page, 1);
    const cubes = await pixels(page);
    await open(page, 'gather-and-form');
    expect(difference(cubes.data, (await pixels(page)).data)).toBeLessThan(
      0.08,
    );
    await release(page, 0);
    expect(difference(rest.data, (await pixels(page)).data)).toBeLessThan(0.08);
    await open(page, source!);
    const middle = complete === 'glitch-and-fracture' ? 0.82 : 0.36;
    await release(page, middle);
    const shattered = await pixels(page);
    // No added wave plane or destination cubes render in this diagnostic.
    // Background content above the rim must also change, not just the disk.
    const skyBytes =
      Math.floor(shattered.info.height * 0.17) * shattered.info.width * 3;
    expect(
      difference(
        rest.data.subarray(0, skyBytes),
        shattered.data.subarray(0, skyBytes),
      ),
    ).toBeGreaterThan(3);
    expect(difference(rest.data, shattered.data)).toBeGreaterThan(12);
    await release(page, 0);
    expect(difference(rest.data, (await pixels(page)).data)).toBeLessThan(0.08);
    await release(page, middle);
    expect(difference(shattered.data, (await pixels(page)).data)).toBeLessThan(
      0.08,
    );
  });

  test(`${complete}: panels resize without errors or accumulating resources`, async ({
    page,
  }) => {
    // Four software-WebGL resizes can exceed the suite's 30-second total budget.
    test.setTimeout(45000);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('console', (message) => {
      if (message.type() === 'error' && /shader|WebGL/i.test(message.text()))
        errors.push(message.text());
    });
    await page.setViewportSize({ width: 960, height: 640 });
    // Sample resource counts during normal playback. In demand mode the
    // diagnostic reports pre-render counts until the next requested frame.
    await page.goto(url(complete!).replace('&capture=1', ''));
    await expect(page.locator('main')).toHaveAttribute('data-ready', 'true');
    await release(page, 0.48);
    await page.locator('canvas').screenshot();
    const count = await page.evaluate(() => window.__orbitScene!.geometries);
    const textures = await page.evaluate(() => window.__orbitScene!.textures);
    for (const viewport of [
      { width: 390, height: 844 },
      { width: 768, height: 1024 },
      { width: 1280, height: 400 },
      { width: 960, height: 640 },
    ]) {
      await page.setViewportSize(viewport);
      await expect
        .poll(() => page.evaluate(() => window.__orbitScene!.geometries))
        .toBe(count);
      expect(await page.getByRole('slider').inputValue()).toBe('0.52');
      await expect
        .poll(() => page.evaluate(() => window.__orbitScene!.textures))
        .toBe(textures);
      await expect(page.locator('canvas')).toHaveCount(1);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    }
    expect(errors).toEqual([]);
  });

  test(`${complete}: reduced motion skips release and stops rendering`, async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await open(page, complete!);
    await page.getByRole('button', { name: 'Play reverse' }).click();
    await expect
      .poll(() => page.evaluate(() => window.__orbitScene!.blend))
      .toBe(0);
    await expect(page.locator('main')).toHaveAttribute('data-playing', 'false');
    const frames = await page.evaluate(() => window.__orbitScene!.frames);
    await page.waitForTimeout(250);
    expect(await page.evaluate(() => window.__orbitScene!.frames)).toBe(frames);
  });
}
