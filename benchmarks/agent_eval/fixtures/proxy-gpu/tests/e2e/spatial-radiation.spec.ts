import { expect, test } from '@playwright/test';
import sharp from 'sharp';

test('the shared radiation geometry can be inspected from above and the side, replayed and interrupted', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewportSize({ width: 960, height: 640 });
  await page.goto(
    'http://127.0.0.1:6006/iframe.html?id=explorations-spatial-radiation--world-space-fan',
  );
  await expect(page.locator('main')).toHaveAttribute('data-ready', 'true');
  const frames: Buffer[] = [];
  for (const view of ['Top view', 'Oblique view', 'Front view']) {
    await page.getByRole('button', { name: view, exact: true }).click();
    await expect(
      page.getByRole('button', { name: view, exact: true }),
    ).toHaveAttribute('aria-pressed', 'true');
    frames.push(
      await sharp(await page.locator('canvas').screenshot())
        .removeAlpha()
        .raw()
        .toBuffer(),
    );
  }
  for (let i = 1; i < frames.length; i++) {
    const meanChange =
      frames[i]!.reduce(
        (sum, value, index) => sum + Math.abs(value - frames[i - 1]![index]!),
        0,
      ) / frames[i]!.length;
    expect(meanChange).toBeGreaterThan(0.5);
  }
  await page.getByRole('button', { name: 'Compare short strands' }).click();
  await page.getByRole('button', { name: 'Show continuous strands' }).click();
  await page.getByRole('button', { name: 'Replay radiation' }).click();
  await expect(page.locator('main')).toHaveAttribute('data-playing', 'true');
  await page.getByRole('slider').fill('0.4');
  await expect(page.locator('main')).toHaveAttribute('data-playing', 'false');
  // Exercise drag-orbit against the same geometry, not a diagram of its paths.
  await page.mouse.move(500, 210);
  await page.mouse.down();
  await page.mouse.move(620, 260, { steps: 6 });
  await page.mouse.up();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('canvas')).toHaveCount(1);
  expect(await page.getByRole('slider').inputValue()).toBe('0.4');
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.getByRole('button', { name: 'Replay radiation' }).click();
  await expect(page.locator('main')).toHaveAttribute('data-playing', 'false');
  await expect(page.getByRole('slider')).toHaveValue('1');
  expect(errors).toEqual([]);
});
