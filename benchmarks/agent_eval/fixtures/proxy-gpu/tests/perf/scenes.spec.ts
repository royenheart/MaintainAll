import { test, expect } from '@playwright/test';

test('collects frame intervals and verifies paused rendering and resource lifetime', async ({
  page,
}, testInfo) => {
  test.setTimeout(60000);
  await page.goto('/original/');
  await expect(page.locator('.scene-experience')).toHaveAttribute(
    'data-renderer',
    'webgl',
  );
  const sample = () =>
    page.evaluate(
      () =>
        new Promise<number[]>((resolve) => {
          const intervals: number[] = [];
          let previous = performance.now();
          const collect = (now: number) => {
            intervals.push(now - previous);
            previous = now;
            if (intervals.length === 90) resolve(intervals);
            else requestAnimationFrame(collect);
          };
          requestAnimationFrame(collect);
        }),
    );
  const cubes = await sample();
  await page.getByRole('button', { name: 'Switch scene' }).click();
  const horizon = await sample();
  const before = await page.evaluate(() => window.__sceneMetrics);
  for (let index = 0; index < 20; index++)
    await page.getByRole('button', { name: 'Switch scene' }).click();
  await expect
    .poll(async () => page.evaluate(() => window.__sceneMetrics?.scene))
    .toBe('horizon');
  const after = await page.evaluate(() => window.__sceneMetrics);
  expect(after!.geometries).toBeLessThanOrEqual(before!.geometries + 2);
  expect(after!.textures).toBeLessThanOrEqual(before!.textures + 1);
  await page.getByRole('button', { name: 'Pause animation' }).click();
  await page.waitForTimeout(200);
  const pausedFrames = await page.evaluate(() => window.__sceneMetrics!.frames);
  await page.waitForTimeout(300);
  expect(await page.evaluate(() => window.__sceneMetrics!.frames)).toBe(
    pausedFrames,
  );
  await page.getByRole('button', { name: 'Resume animation' }).click();
  await expect
    .poll(async () => page.evaluate(() => window.__sceneMetrics!.frames))
    .toBeGreaterThan(pausedFrames);
  const summarize = (values: number[]) => {
    const sorted = [...values].sort((a, b) => a - b);
    return {
      count: values.length,
      p50: sorted[44],
      p95: sorted[85],
      max: sorted[89],
    };
  };
  await testInfo.attach('frame-metrics.json', {
    body: JSON.stringify(
      {
        environment: 'Headless Chromium; not a real-device GPU benchmark',
        cubes: summarize(cubes),
        horizon: summarize(horizon),
        before,
        after,
      },
      null,
      2,
    ),
    contentType: 'application/json',
  });
});
