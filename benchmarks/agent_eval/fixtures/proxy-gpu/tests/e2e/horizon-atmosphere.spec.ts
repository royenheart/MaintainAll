import { expect, test } from '@playwright/test';
import sharp from 'sharp';

const percentile = (values: number[], fraction: number) => {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor((sorted.length - 1) * fraction)]!;
};
const luma = (data: Buffer, pixel: number) =>
  data[pixel * 3]! * 0.2126 +
  data[pixel * 3 + 1]! * 0.7152 +
  data[pixel * 3 + 2]! * 0.0722;

test('nebular color stays behind the dark core and rounded rim swells replay deterministically', async ({
  page,
}) => {
  test.setTimeout(60000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route('**/song/media/outer/**', (route) => route.abort());
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const frames: Buffer[] = [];
  let radius = 0;
  let width = 0;
  let height = 0;
  for (const time of [12, 20, 12]) {
    await page.goto(
      `http://127.0.0.1:6006/iframe.html?id=explorations-orbit-study--selected-horizon&capture=1&sceneTime=${time}&args=skipEntrance:true`,
    );
    await expect(page.locator('main')).toHaveAttribute(
      'data-renderer',
      'webgl',
    );
    await expect
      .poll(() => page.evaluate(() => window.__orbitScene?.time))
      .toBe(time);
    const { data, info } = await sharp(
      await page.locator('canvas').screenshot({
        style: '.orbit-wheel { visibility: hidden !important; }',
      }),
    )
      .removeAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true });
    width = info.width;
    height = info.height;
    const profile = Array.from({ length: Math.floor(height * 0.4) }, (_, y) =>
      luma(data, y * width + Math.floor(width / 2)),
    );
    const peak = Math.max(...profile);
    radius = height / 2 - profile.indexOf(peak);
    expect(peak).toBeGreaterThan(180);
    expect(
      luma(data, Math.floor(height * 0.42) * width + Math.floor(width / 2)),
      'The backdrop must not fill the central shadow',
    ).toBeLessThan(15);

    const background: number[] = [];
    let warm = 0;
    let cool = 0;
    for (let y = 0; y < height * 0.4; y += 3) {
      for (let x = 0; x < width; x += 3) {
        if (Math.hypot(x - width / 2, y - height / 2) < radius * 1.38) continue;
        const pixel = y * width + x;
        background.push(luma(data, pixel));
        if (data[pixel * 3]! - data[pixel * 3 + 2]! > 8) warm++;
        if (data[pixel * 3 + 2]! - data[pixel * 3]! > 8) cool++;
      }
    }
    expect(
      percentile(background, 0.5),
      'Visible cloud background',
    ).toBeGreaterThan(7);
    expect(
      percentile(background, 0.9) - percentile(background, 0.1),
      'Cloud and dust have spatial structure instead of a flat wash',
    ).toBeGreaterThan(12);
    expect(percentile(background, 0.95)).toBeLessThan(peak * 0.5);
    expect(warm / background.length).toBeGreaterThan(0.025);
    expect(cool / background.length).toBeGreaterThan(0.06);
    frames.push(data);
  }

  // Normalize observed crest colors by their channel sum, so changing only
  // brightness cannot masquerade as distinct gold/copper material layers.
  const chroma: number[] = [];
  for (const fraction of [0.43, 0.5, 0.57]) {
    const x = Math.floor(width * fraction);
    for (let y = Math.ceil(height * 0.63); y < height * 0.91; y++) {
      const pixel = y * width + x;
      const value = luma(frames[1]!, pixel);
      if (
        value < 25 ||
        value <= luma(frames[1]!, pixel - width) ||
        value < luma(frames[1]!, pixel + width)
      )
        continue;
      const r = frames[1]![pixel * 3]!;
      const g = frames[1]![pixel * 3 + 1]!;
      const b = frames[1]![pixel * 3 + 2]!;
      chroma.push((r - g) / Math.max(r + g + b, 1));
    }
  }
  expect(chroma.length).toBeGreaterThan(20);
  expect(
    percentile(chroma, 0.9) - percentile(chroma, 0.1),
    'Foreground strands need distinct color layers, not only varied brightness',
  ).toBeGreaterThan(0.065);

  // Divide the observed outer arc into sectors, without reproducing the swell
  // locations or shader timing. Different sectors must change by different amounts.
  const sectors = Array.from({ length: 12 }, () => [] as number[]);
  for (let y = 0; y < height / 2; y++) {
    for (let x = 0; x < width; x++) {
      const distance = Math.hypot(x - width / 2, y - height / 2);
      if (distance < radius * 1.025 || distance > radius * 1.2) continue;
      const angle = Math.atan2(height / 2 - y, x - width / 2);
      const sector = Math.min(11, Math.floor((angle / Math.PI) * 12));
      const pixel = y * width + x;
      sectors[sector]!.push(
        Math.abs(luma(frames[0]!, pixel) - luma(frames[1]!, pixel)),
      );
    }
  }
  const changes = sectors.map((values) => percentile(values, 0.95));
  expect(Math.max(...changes), 'Visible local halo motion').toBeGreaterThan(25);
  expect(
    Math.max(...changes) / Math.min(...changes),
    'The entire halo must not flash in unison',
  ).toBeGreaterThan(1.8);

  // Follow both edges of the observed bright band. The outer emitting mantle
  // must rise while its inner edge stays anchored around the black region.
  const contour = (data: Buffer) => {
    const inner: number[] = [];
    const outer: number[] = [];
    // Desktop Safari captures at DPR 2; compare geometry in CSS pixels.
    const scale = width / 1440;
    for (let index = 0; index < 96; index++) {
      const angle = 0.35 + (index / 95) * 2.44;
      const start = Math.floor(radius * 0.85);
      const scan: number[] = [];
      for (let distance = start; distance < radius * 1.2; distance++) {
        const x = Math.round(width / 2 + Math.cos(angle) * distance);
        const y = Math.round(height / 2 - Math.sin(angle) * distance);
        scan.push(luma(data, y * width + x));
      }
      const threshold = Math.max(...scan) * 0.55;
      inner.push(
        (start + scan.findIndex((value) => value > threshold)) / scale,
      );
      outer.push(
        (start + scan.findLastIndex((value) => value > threshold)) / scale,
      );
    }
    return { inner, outer };
  };
  const first = contour(frames[0]!);
  const second = contour(frames[1]!);
  const displacement = first.outer.map((value, index) =>
    Math.abs(value - second.outer[index]!),
  );
  expect(
    Math.max(...displacement),
    'The outer mantle must protrude',
  ).toBeGreaterThan(6);
  expect(
    displacement.filter((value) => value > 4).length,
    'A rounded shoulder spans multiple samples',
  ).toBeGreaterThan(5);
  // A brightness threshold also follows the fine halo texture by a few pixels;
  // the local protrusions must exceed that background variation substantially.
  expect(percentile(displacement, 0.5)).toBeLessThan(4);
  for (let index = 0; index < first.inner.length; index++)
    expect(
      Math.abs(first.inner[index]! - second.inner[index]!),
      'The shadow must not expand beneath a luminous bulge',
    ).toBeLessThan(3);
  for (const curve of [first.outer, second.outer])
    for (let index = 1; index < curve.length; index++)
      expect(
        Math.abs(curve[index]! - curve[index - 1]!),
        'No isolated spike in the contour',
      ).toBeLessThan(7);

  let replayDifference = 0;
  for (let i = 0; i < frames[0]!.length; i++)
    replayDifference += Math.abs(frames[0]![i]! - frames[2]![i]!);
  expect(replayDifference / frames[0]!.length).toBeLessThan(0.1);
  expect(errors).toEqual([]);
});
