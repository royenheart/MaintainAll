import { expect, test, type Page } from '@playwright/test';
import sharp from 'sharp';

const url = (story: string) =>
  `http://127.0.0.1:6006/iframe.html?id=explorations-scene-formation--${story}&capture=1`;
async function open(page: Page, story: string) {
  await page.goto(url(story));
  await expect(page.locator('main')).toHaveAttribute('data-ready', 'true');
}
async function release(page: Page, q: number) {
  const blend = +(1 - q).toFixed(3);
  await page.getByRole('slider').fill(String(blend));
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene!.blend))
    .toBe(blend);
}
async function pixels(page: Page) {
  return sharp(
    await page.locator('canvas').screenshot({
      style: '.formation-controls { visibility: hidden; }',
    }),
  )
    .removeAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
}
const difference = (a: Buffer, b: Buffer) =>
  a.reduce((sum, value, i) => sum + Math.abs(value - b[i]!), 0) / a.length;

test('corruption starts locally and spreads across the source without retreating', async ({
  page,
}) => {
  await page.setViewportSize({ width: 800, height: 600 });
  await open(page, 'glitch-field');
  let previous: Buffer | undefined;
  const coverage: number[] = [];
  for (const q of [0.12, 0.28, 0.52]) {
    await release(page, q);
    const { data } = await pixels(page);
    let lit = 0,
      retreat = 0;
    for (let i = 0; i < data.length; i += 3) {
      if (data[i]! > 100) lit++;
      if (previous && previous[i]! > 100 && data[i]! < 80) retreat++;
    }
    coverage.push(lit / (data.length / 3));
    expect(retreat / (data.length / 3)).toBeLessThan(0.005);
    previous = data;
  }
  expect(coverage[0]).toBeGreaterThan(0.001);
  expect(coverage[0]).toBeLessThan(0.1);
  expect(coverage[1]! - coverage[0]!).toBeGreaterThan(0.15);
  expect(coverage[2]).toBeGreaterThan(0.95);
});

test('source silhouette, sky and rings distort and lose sharpness before any panes separate', async ({
  page,
}) => {
  test.setTimeout(60000);
  await page.setViewportSize({ width: 800, height: 600 });
  await open(page, 'glitch-surface');
  const rest = await pixels(page);
  await release(page, 0.58);
  const blurred = await pixels(page);
  const skyBytes =
    Math.floor(blurred.info.height * 0.17) * blurred.info.width * 3;
  expect(
    difference(
      rest.data.subarray(0, skyBytes),
      blurred.data.subarray(0, skyBytes),
    ),
  ).toBeGreaterThan(2);
  let changedVoid = 0;
  for (let y = 70; y < 350; y++)
    for (let x = 230; x < 570; x++) {
      const i = (y * blurred.info.width + x) * 3;
      const black = (data: Buffer) =>
        Math.max(data[i]!, data[i + 1]!, data[i + 2]!) < 8;
      if (black(rest.data) !== black(blurred.data)) changedVoid++;
    }
  expect(changedVoid).toBeGreaterThan(2500);
  await open(page, 'glitch-sharp');
  await release(page, 0.58);
  const sharpFrame = await pixels(page);
  const verticalDetail = (data: Buffer) => {
    let detail = 0;
    const row = blurred.info.width * 3;
    for (
      let i = row * Math.floor(blurred.info.height * 0.7);
      i < data.length - row;
      i += 3
    )
      detail += Math.abs(data[i]! - data[i + row]!);
    return detail;
  };
  expect(
    verticalDetail(blurred.data) / verticalDetail(sharpFrame.data),
  ).toBeLessThan(0.85);
  await open(page, 'glitch-and-fracture');
  await release(page, 0.58);
  // The destination is completely occluded while the source is still connected.
  expect(difference(blurred.data, (await pixels(page)).data)).toBeLessThan(0.1);
  await release(page, 0.82);
  const broken = await pixels(page);
  await open(page, 'glitch-surface');
  await release(page, 0.82);
  expect(difference(broken.data, (await pixels(page)).data)).toBeGreaterThan(
    20,
  );
});
