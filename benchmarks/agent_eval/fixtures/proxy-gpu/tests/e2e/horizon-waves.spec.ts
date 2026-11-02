import { expect, test } from '@playwright/test';
import sharp from 'sharp';

const median = (values: number[]) =>
  [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)]!;

// Detect visible strand crests, independently of the shader's phase equation.
function strandCrests(
  data: Buffer,
  width: number,
  height: number,
  fraction: number,
) {
  const x = Math.floor(width * fraction);
  const profile = Array.from({ length: height }, (_, y) =>
    median(
      [-2, -1, 0, 1, 2].map((dx) => {
        const offset = (y * width + x + dx) * 3;
        return (
          data[offset]! * 0.2126 +
          data[offset + 1]! * 0.7152 +
          data[offset + 2]! * 0.0722
        );
      }),
    ),
  );
  const filtered = profile.map(
    (value, y) =>
      ((profile[y - 1] ?? value) + value * 2 + (profile[y + 1] ?? value)) / 4,
  );
  const window = Math.max(3, Math.round(height * 0.009));
  const crests: number[] = [];
  for (let y = Math.ceil(height * 0.6); y < height * 0.96; y++) {
    const value = filtered[y]!;
    if (value <= filtered[y - 1]! || value < filtered[y + 1]!) continue;
    const left = Math.min(...filtered.slice(y - window, y));
    const right = Math.min(...filtered.slice(y + 1, y + window + 1));
    if (value - Math.max(left, right) > 4) crests.push(y);
  }
  return crests;
}

test('foreground spacing grows with depth and wave crests visibly travel while the junction stays anchored', async ({
  page,
}) => {
  test.setTimeout(60000);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.route('**/song/media/outer/**', (route) => route.abort());
  const phases: number[][][] = [];
  for (const time of [12, 16, 20]) {
    await page.goto(
      `http://127.0.0.1:6006/iframe.html?id=explorations-orbit-study--selected-horizon&capture=1&sceneTime=${time}&args=skipEntrance:true;horizonDiagnostic:emission`,
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
    const columns = [0.4, 0.5, 0.6].map((fraction) =>
      strandCrests(data, info.width, info.height, fraction),
    );
    const ratios = columns.map((crests) => {
      const far: number[] = [];
      const near: number[] = [];
      for (let i = 1; i < crests.length; i++) {
        const center = (crests[i]! + crests[i - 1]!) / 2 / info.height;
        const interval = crests[i]! - crests[i - 1]!;
        if (center > 0.63 && center < 0.72) far.push(interval);
        if (center > 0.83 && center < 0.95) near.push(interval);
      }
      expect(far.length).toBeGreaterThanOrEqual(4);
      expect(near.length).toBeGreaterThanOrEqual(2);
      return median(near) / median(far);
    });
    expect(median(ratios), `Near/far spacing at time ${time}`).toBeGreaterThan(
      1.5,
    );
    phases.push(columns);
  }
  for (let column = 0; column < 3; column++) {
    const first = phases[0]![column]!;
    const second = phases[1]![column]!;
    const count = Math.min(first.length, second.length);
    expect(count).toBeGreaterThan(12);
    // The ordered inner crests stay put, making correspondence unambiguous.
    for (let index = 0; index < 3; index++)
      expect(Math.abs(second[index]! - first[index]!)).toBeLessThan(3);
    const travel = first
      .slice(6, count - 2)
      .map((y, index) => second[index + 6]! - y);
    expect(
      Math.max(...travel.map(Math.abs)),
      'A wave moves the surface, not only its brightness',
    ).toBeGreaterThan(12);
    expect(
      Math.max(...travel) - Math.min(...travel),
      'Depths move differently instead of shifting the entire disk',
    ).toBeGreaterThan(10);
  }
});
