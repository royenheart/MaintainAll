import { expect, test, type Page } from '@playwright/test';
import sharp from 'sharp';
import { viewports } from '../support/viewports';
import { inspectOrbitLayout } from '../support/orbit-layout';

const lab = (name = 'gather-and-form', capture = true) =>
  `http://127.0.0.1:6006/iframe.html?id=explorations-scene-formation--${name}${capture ? '&capture=1' : ''}`;
const scene = (name: string, args = '') =>
  `http://127.0.0.1:6006/iframe.html?id=explorations-orbit-study--${name}&args=${args}`;
async function ready(page: Page) {
  await expect(page.locator('.formation-study')).toHaveAttribute(
    'data-ready',
    'true',
  );
}
async function progress(
  page: Page,
  value: number,
  key: 'blend' | 'entrance' = 'blend',
) {
  await page.getByRole('slider').fill(String(value));
  await expect
    .poll(() => page.evaluate((key) => window.__orbitScene?.[key], key))
    .toBe(value);
}
async function frame(page: Page) {
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
  a.reduce((sum, value, i) => sum + Math.abs(value - b[i]!), 0) / a.length;
async function lastCard(page: Page) {
  await page.locator('.orbit-disc').click({ position: { x: 12, y: 50 } });
  await page.locator('.rotary-deck').press('End');
  await expect(
    page.getByRole('button', { name: 'Next scene', exact: true }),
  ).toBeVisible();
}

test('the intermediate image is a geometric transformation and reverse scrubbing retraces it', async ({
  page,
}) => {
  await page.setViewportSize({ width: 960, height: 640 });
  await page.goto(lab());
  await ready(page);
  const first = await frame(page);
  await progress(page, 0.55);
  const middle = await frame(page);
  await progress(page, 1);
  const last = await frame(page);
  // A crossfade can only lie on the segment between the two endpoint images.
  // Measure distance from every blend on that segment, independently of shader equations.
  const errors = Array.from({ length: 21 }, (_, step) => {
    const mix = step / 20;
    let error = 0;
    for (let i = 0; i < first.data.length; i++)
      error += Math.abs(
        middle.data[i]! - first.data[i]! * (1 - mix) - last.data[i]! * mix,
      );
    return error / first.data.length;
  });
  expect(Math.min(...errors)).toBeGreaterThan(12);
  await progress(page, 0.55);
  expect(difference(middle.data, (await frame(page)).data)).toBeLessThan(0.05);
  await progress(page, 0);
  expect(difference(first.data, (await frame(page)).data)).toBeLessThan(0.05);
  expect(await page.locator('canvas').count()).toBe(1);
});

test('the horizon traces at its final size and the foreground forms progressively', async ({
  page,
}) => {
  await page.setViewportSize({ width: 960, height: 640 });
  await page.goto(lab('horizon-arrival'));
  await ready(page);
  await progress(page, 0.6, 'entrance');
  const forming = await frame(page);
  await progress(page, 1, 'entrance');
  const final = await frame(page);
  const crest = (data: Buffer, row: number) => {
    let maximum = -1,
      position = -1;
    for (
      let x = Math.floor(final.info.width * 0.2);
      x < final.info.width * 0.49;
      x++
    ) {
      const index = (row * final.info.width + x) * 3;
      const light = data[index]! + data[index + 1]! + data[index + 2]!;
      if (light > maximum) {
        maximum = light;
        position = x;
      }
    }
    return position;
  };
  for (const fraction of [0.28, 0.36, 0.44]) {
    const row = Math.floor(final.info.height * fraction);
    expect(
      Math.abs(crest(forming.data, row) - crest(final.data, row)),
    ).toBeLessThanOrEqual(2);
  }
  // The already traced edge stays put while new foreground material reaches the bottom.
  const lower = Math.floor(final.info.height * 0.85) * final.info.width * 3;
  expect(
    difference(forming.data.subarray(lower), final.data.subarray(lower)),
  ).toBeGreaterThan(8);
  await progress(page, 0, 'entrance');
  expect(difference((await frame(page)).data, final.data)).toBeGreaterThan(20);
});

test('cube arrival fills the scene through falling accumulation stages', async ({
  page,
}) => {
  await page.setViewportSize({ width: 640, height: 480 });
  await page.goto(lab('cube-arrival'));
  await ready(page);
  const stages: Buffer[] = [];
  for (const value of [0, 0.3, 0.6, 1]) {
    await progress(page, value, 'entrance');
    stages.push((await frame(page)).data);
  }
  for (let i = 1; i < stages.length; i++)
    expect(difference(stages[i - 1]!, stages[i]!)).toBeGreaterThan(12);
});

test('live playback supports pause, reverse interruption and cleanup on unmount', async ({
  page,
}) => {
  test.setTimeout(45000);
  await page.setViewportSize({ width: 640, height: 480 });
  await page.goto(lab('gather-and-form', false));
  await ready(page);
  await page.getByRole('button', { name: 'Play forward' }).click();
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene?.blend ?? 0))
    .toBeGreaterThan(0.2);
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  const paused = await page.getByRole('slider').inputValue();
  const frames = await page.evaluate(() => window.__orbitScene!.frames);
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene!.frames))
    .toBeGreaterThan(frames + 3);
  expect(await page.getByRole('slider').inputValue()).toBe(paused);
  await page.getByRole('button', { name: 'Play reverse' }).click();
  await expect
    .poll(async () => Number(await page.getByRole('slider').inputValue()))
    .toBeLessThan(Number(paused));
  await page.getByRole('button', { name: 'Unmount scene' }).click();
  await expect(page.locator('canvas')).toHaveCount(0);
  await expect(page.locator('main')).toHaveAttribute('data-playing', 'false');
  await page.getByRole('button', { name: 'Mount scene' }).click();
  await expect(page.locator('canvas')).toHaveCount(1);
  await ready(page);
  await expect(page.getByText('Graphics unavailable')).toHaveCount(0);
});

test('both arrival prompts fit the width and height matrix without covering registration links', async ({
  page,
}) => {
  test.setTimeout(60000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('**/song/media/outer/**', (route) => route.abort());
  for (const name of ['selected-cubes', 'selected-horizon']) {
    await page.goto(scene(name));
    // A fresh 1920px software-GL scene measured 8.4s to finish preparation.
    // The controls must become ready before geometry checks, without a sleep.
    await expect(
      page.getByRole('button', { name: 'Enter quietly' }),
    ).toBeEnabled({ timeout: 15000 });
    await expect(page.locator('main')).toHaveAttribute(
      'data-renderer',
      'webgl',
    );
    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      await expect.poll(() => page.evaluate(inspectOrbitLayout)).toEqual([]);
    }
    await page.getByRole('button', { name: 'Enter quietly' }).click();
    await expect(page.locator('.orbit-wheel')).toBeVisible();
  }
});

test('selected scene navigation keeps one canvas through repeated input and in-flight resize', async ({
  page,
}) => {
  test.setTimeout(60000);
  await page.setViewportSize({ width: 960, height: 640 });
  await page.route('**/song/media/outer/**', (route) => route.abort());
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error' && message.text().includes('shader'))
      errors.push(message.text());
  });
  await page.goto(scene('selected-cubes', 'skipEntrance:true'));
  await expect(page.locator('main')).toHaveAttribute('data-renderer', 'webgl');
  const canvas = await page.locator('canvas').elementHandle();
  const resources = await page.evaluate(() => window.__orbitScene!.geometries);
  await lastCard(page);
  await page
    .getByRole('button', { name: 'Next scene', exact: true })
    .evaluate((node) => {
      for (let i = 0; i < 12; i++) (node as HTMLButtonElement).click();
    });
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene!.blend))
    .toBeGreaterThan(0.25);
  await page.setViewportSize({ width: 390, height: 400 });
  await expect(page.locator('main')).toHaveAttribute('data-scene', 'horizon', {
    timeout: 12000,
  });
  const warmedResources = await page.evaluate(
    () => window.__orbitScene!.geometries,
  );
  // The transient impulse plane uploads on its first visible frame.
  expect(warmedResources).toBeLessThanOrEqual(resources + 1);
  await expect.poll(() => page.evaluate(inspectOrbitLayout)).toEqual([]);
  await lastCard(page);
  await page
    .getByRole('button', { name: 'Previous scene', exact: true })
    .click();
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene!.blend))
    .toBeLessThan(0.8);
  await page.setViewportSize({ width: 768, height: 1024 });
  await expect(page.locator('main')).toHaveAttribute('data-scene', 'cubes', {
    timeout: 12000,
  });
  await expect.poll(() => page.evaluate(inspectOrbitLayout)).toEqual([]);
  expect(
    await canvas!.evaluate((node) => node === document.querySelector('canvas')),
  ).toBe(true);
  expect(await page.evaluate(() => window.__orbitScene!.geometries)).toBe(
    warmedResources,
  );
  expect(errors).toEqual([]);
});

test('arrival gates the wheel and context loss during formation retains quiet entry', async ({
  page,
}) => {
  await page.route('**/song/media/outer/**', (route) => route.abort());
  await page.goto(scene('selected-horizon'));
  await expect(page.locator('main')).toHaveAttribute('data-renderer', 'webgl');
  await expect(page.locator('.orbit-wheel')).toHaveCount(0);
  await expect(page.locator('.orbit-quiet')).toBeDisabled();
  await page
    .locator('canvas')
    .evaluate((node) =>
      node.dispatchEvent(new Event('webglcontextlost', { cancelable: true })),
    );
  await expect(page.locator('main')).toHaveAttribute(
    'data-renderer',
    'fallback',
  );
  await page.getByRole('button', { name: 'Enter quietly' }).click();
  await expect(page.locator('.orbit-wheel')).toBeVisible();
  await lastCard(page);
  await page.getByRole('button', { name: 'Next scene', exact: true }).click();
  await expect(page.locator('main')).toHaveAttribute('data-scene', 'cubes');
});

test('reduced motion settles both sequences immediately without a running render loop', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(lab());
  await ready(page);
  await page.getByRole('button', { name: 'Play forward' }).click();
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene!.blend))
    .toBe(1);
  await expect(page.locator('main')).toHaveAttribute('data-playing', 'false');
  const frames = await page.evaluate(() => window.__orbitScene!.frames);
  await page.waitForTimeout(250);
  expect(await page.evaluate(() => window.__orbitScene!.frames)).toBe(frames);
});

test('forceful collapse and rupture have distinct energy sequences and preserve both resting scenes', async ({
  page,
}) => {
  test.setTimeout(45000);
  await page.setViewportSize({ width: 800, height: 600 });
  await page.goto(lab());
  await ready(page);
  const cubes = await frame(page);
  await progress(page, 1);
  const horizon = await frame(page);
  await page.goto(lab('collapse-and-rupture'));
  await ready(page);
  await progress(page, 0.55);
  const inward = await frame(page);
  await progress(page, 1);
  expect(difference(horizon.data, (await frame(page)).data)).toBeLessThan(0.05);
  await page.getByRole('button', { name: 'Play reverse' }).click();
  await page.getByRole('button', { name: 'Pause', exact: true }).click();
  await progress(page, 0.78);
  const breakout = await frame(page);
  const centerLight = (data: Buffer) => {
    let sum = 0,
      count = 0;
    for (
      let y = Math.floor(breakout.info.height * 0.41);
      y < breakout.info.height * 0.51;
      y++
    ) {
      for (
        let x = Math.floor(breakout.info.width * 0.46);
        x < breakout.info.width * 0.54;
        x++
      ) {
        const offset = (y * breakout.info.width + x) * 3;
        sum +=
          data[offset]! * 0.2126 +
          data[offset + 1]! * 0.7152 +
          data[offset + 2]! * 0.0722;
        count++;
      }
    }
    return sum / count;
  };
  expect(centerLight(horizon.data)).toBeLessThan(5);
  expect(centerLight(breakout.data)).toBeGreaterThan(100);
  await progress(page, 0.55);
  expect(difference(inward.data, (await frame(page)).data)).toBeGreaterThan(10);
  expect(await page.evaluate(() => window.__orbitScene!.direction)).toBe(-1);
  await progress(page, 0);
  expect(difference(cubes.data, (await frame(page)).data)).toBeLessThan(0.05);
  await expect(page.locator('canvas')).toHaveCount(1);
});

test('rupture moves the original rim and disk with added particles and flash removed', async ({
  page,
}) => {
  await page.setViewportSize({ width: 960, height: 640 });
  await page.goto(lab('rupture-material'));
  await ready(page);
  const original = await frame(page);
  await progress(page, 0.78);
  const transported = await frame(page);
  const leftCrest = (data: Buffer, row: number) => {
    let strongest = 0,
      position = -1;
    for (
      let x = Math.floor(original.info.width * 0.08);
      x < original.info.width * 0.49;
      x++
    ) {
      const index = (row * original.info.width + x) * 3;
      const light = data[index]! + data[index + 1]! + data[index + 2]!;
      if (light > strongest) {
        strongest = light;
        position = x;
      }
    }
    return position;
  };
  for (const y of [0.3, 0.36, 0.42]) {
    const row = Math.floor(original.info.height * y);
    const before = leftCrest(original.data, row);
    const after = leftCrest(transported.data, row);
    expect(before - after).toBeGreaterThan(12);
    // A brightness-only mutation cannot satisfy the spatial displacement oracle.
    const dimmed = Buffer.from(
      original.data.map((value) => Math.round(value * 0.55)),
    );
    expect(Math.abs(leftCrest(dimmed, row) - before)).toBeLessThanOrEqual(2);
  }
  await progress(page, 0.56);
  expect(difference(original.data, (await frame(page)).data)).toBeGreaterThan(
    20,
  );
  await expect(page.locator('main')).toHaveAttribute(
    'data-expression',
    'force',
  );
});
