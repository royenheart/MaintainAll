import { expect, test, type Page } from '@playwright/test';
import sharp from 'sharp';

async function open(page: Page, story: string, time = 12) {
  await page.goto(
    `http://127.0.0.1:6006/iframe.html?id=explorations-scene-formation--${story}&capture=1&sceneTime=${time}`,
  );
  await expect(page.locator('main')).toHaveAttribute('data-ready', 'true');
}
async function progress(page: Page, value: number, arrival = false) {
  await page.getByRole('slider').fill(String(value));
  await expect
    .poll(() =>
      page.evaluate(
        (arrival) => window.__orbitScene?.[arrival ? 'entrance' : 'blend'],
        arrival,
      ),
    )
    .toBe(value);
}
async function frame(page: Page) {
  return sharp(
    await page.locator('canvas').screenshot({
      scale: 'css',
      style: '.formation-controls { visibility: hidden; }',
    }),
  )
    .removeAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
}
const difference = (a: Buffer, b: Buffer) =>
  a.reduce((sum, value, i) => sum + Math.abs(value - b[i]!), 0) / a.length;

test('arrival enters through the top, accumulates below, and preserves the authored endpoint', async ({
  page,
}) => {
  await page.setViewportSize({ width: 800, height: 500 });
  await open(page, 'cube-arrival');
  await progress(page, 0.2, true);
  const first = await frame(page);
  await progress(page, 0.55, true);
  const piled = await frame(page);
  const detail = (data: Buffer, start: number, end: number) => {
    let sum = 0;
    let count = 0;
    for (let y = start; y < end; y++)
      for (let x = 1; x < first.info.width; x++) {
        const i = (y * first.info.width + x) * 3;
        sum += Math.abs(data[i]! - data[i - 3]!);
        count++;
      }
    return sum / count;
  };
  // A whole-scene fade would reveal the dense bottom pile immediately.
  expect(detail(first.data, 0, 150)).toBeGreaterThan(0.8);
  expect(detail(first.data, 300, 500)).toBeLessThan(0.1);
  expect(detail(piled.data, 300, 500)).toBeGreaterThan(1.5);
  await progress(page, 1, true);
  const settled = await frame(page);
  await open(page, 'layered-cube-arrival');
  await progress(page, 1, true);
  expect(difference(settled.data, (await frame(page)).data)).toBeLessThan(0.05);
});

test('all accretion paths preserve both endpoints and remain distinct during transport', async ({
  page,
}) => {
  test.setTimeout(60000);
  await page.setViewportSize({ width: 800, height: 500 });
  await open(page, 'gather-and-form');
  const cubes = await frame(page);
  await progress(page, 1);
  const horizon = await frame(page);
  const stages: Buffer[] = [];
  for (const story of [
    'split-accretion',
    'orbital-accretion',
    'cascade-accretion',
  ]) {
    await open(page, story);
    expect(difference(cubes.data, (await frame(page)).data)).toBeLessThan(0.05);
    await progress(page, 0.45);
    const middle = await frame(page);
    stages.push(middle.data);
    await progress(page, 1);
    expect(difference(horizon.data, (await frame(page)).data)).toBeLessThan(
      0.05,
    );
    await progress(page, 0.45);
    expect(difference(middle.data, (await frame(page)).data)).toBeLessThan(
      0.05,
    );
    await expect(page.locator('canvas')).toHaveCount(1);
  }
  for (let i = 0; i < stages.length; i++)
    for (let j = i + 1; j < stages.length; j++)
      expect(difference(stages[i]!, stages[j]!)).toBeGreaterThan(3);
});

test('the settled foreground moves with ambient time and capture replay remains deterministic', async ({
  page,
}) => {
  await page.setViewportSize({ width: 800, height: 500 });
  await open(page, 'horizon-arrival', 12);
  await progress(page, 1, true);
  const first = await frame(page);
  await open(page, 'horizon-arrival', 18);
  await progress(page, 1, true);
  const later = await frame(page);
  const foreground = Math.floor(first.info.height * 0.7) * first.info.width * 3;
  expect(
    difference(
      first.data.subarray(foreground),
      later.data.subarray(foreground),
    ),
  ).toBeGreaterThan(3);
  await open(page, 'horizon-arrival', 12);
  await progress(page, 1, true);
  expect(difference(first.data, (await frame(page)).data)).toBeLessThan(0.05);
});
