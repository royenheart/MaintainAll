import { test, expect, type Page } from '@playwright/test';
import sharp from 'sharp';
import { inspectOrbitLayout } from '../support/orbit-layout';

const native = (extra = '') =>
  `http://127.0.0.1:6006/iframe.html?id=explorations-rotary-directions--native-drum${extra}`;
const horizon = (fixed = true) =>
  `http://127.0.0.1:6006/iframe.html?id=explorations-orbit-study--selected-horizon&args=skipEntrance:true;startOpen:true${fixed ? '&capture=1' : ''}`;
async function frame(page: Page) {
  return sharp(await page.locator('canvas').screenshot())
    .removeAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
}

test('cards use scoped wheel input and retain keyboard navigation without arrow buttons', async ({
  page,
}) => {
  await page.goto(native());
  const deck = page.locator('.rotary-deck');
  await expect(deck).toHaveAttribute('data-card-index', '0');
  await expect(
    page.getByRole('button', { name: /^(Next|Previous) card$/ }),
  ).toHaveCount(0);
  await page.mouse.move(60, 70);
  await page.mouse.wheel(0, 300);
  await expect(deck).toHaveAttribute('data-card-index', '0');
  const card = await page.locator('.rotary-card-active').boundingBox();
  await page.mouse.move(card!.x + 80, card!.y + card!.height / 2);
  await page.mouse.wheel(0, 220);
  await expect(deck).toHaveAttribute('data-card-index', '1');
  await expect(deck).toHaveAttribute('data-moving', 'false');
  await page.mouse.wheel(0, -220);
  await expect(deck).toHaveAttribute('data-card-index', '0');
  await deck.press('End');
  await expect(
    page.getByRole('button', { name: 'Next scene', exact: true }),
  ).toBeVisible();
  await deck.press('Home');
  await expect(deck).toHaveAttribute('data-card-index', '0');
  await deck.press('ArrowDown');
  await expect(deck).toHaveAttribute('data-card-index', '1');
  await deck.press('Escape');
  await expect(page.locator('.orbit-disc')).toBeFocused();
  await expect(deck).toHaveCount(0);
});

test('playback appears inside hovered artwork, hides on leave, and remains keyboard accessible', async ({
  page,
}) => {
  await page.goto(native());
  const sound = page.locator('.orbit-sound');
  const disc = page.locator('.orbit-disc');
  await expect(sound).toBeEnabled();
  await page.mouse.move(20, 20);
  await expect(sound).toHaveCSS('opacity', '0');
  await disc.hover({ position: { x: 12, y: 50 } });
  await expect(sound).toHaveCSS('opacity', '1');
  const cover = await page.locator('.orbit-artwork').boundingBox();
  const play = await sound.boundingBox();
  expect(play!.width).toBeGreaterThanOrEqual(44);
  expect(
    Math.abs(play!.x + play!.width / 2 - cover!.x - cover!.width / 2),
  ).toBeLessThan(1);
  expect(
    Math.abs(play!.y + play!.height / 2 - cover!.y - cover!.height / 2),
  ).toBeLessThan(1);
  expect(play!.y + play!.height).toBeLessThan(cover!.y + cover!.height);
  await sound.click();
  await expect(page.locator('.orbit-wheel')).toHaveAttribute(
    'data-playing',
    'true',
  );
  await expect(
    page.getByRole('button', { name: 'Pause music', exact: true }),
  ).toBeVisible();
  await sound.click();
  await page.mouse.move(20, 20);
  await expect(sound).toHaveCSS('opacity', '0');
  await disc.focus();
  await page.keyboard.press('Tab');
  await expect(sound).toBeFocused();
  await expect(sound).toHaveCSS('opacity', '1');
  await page.keyboard.press('Space');
  await expect(page.locator('.orbit-wheel')).toHaveAttribute(
    'data-playing',
    'true',
  );
  await page.keyboard.press('Space');
  await expect.poll(() => page.evaluate(inspectOrbitLayout)).toEqual([]);
});

test.describe('touch input', () => {
  test.use({ hasTouch: true, viewport: { width: 390, height: 844 } });
  test('tapping the cover exposes playback and vertical pointer gestures change cards', async ({
    page,
  }) => {
    await page.goto(native('&args=startOpen:false'));
    await expect(page.locator('.orbit-sound')).toBeEnabled();
    await page.locator('.orbit-disc').tap({ position: { x: 12, y: 50 } });
    const deck = page.locator('.rotary-deck');
    await expect(deck).toBeVisible();
    await expect(page.locator('.orbit-sound')).toHaveCSS('opacity', '1');
    await page.locator('.orbit-sound').tap();
    await expect(page.locator('.orbit-wheel')).toHaveAttribute(
      'data-playing',
      'true',
    );
    await page.locator('.orbit-sound').tap();
    const stage = page.locator('.rotary-stage');
    await stage.dispatchEvent('pointerdown', {
      pointerId: 1,
      pointerType: 'touch',
      clientY: 160,
    });
    await stage.dispatchEvent('pointerup', {
      pointerId: 1,
      pointerType: 'touch',
      clientY: 90,
    });
    await expect(deck).toHaveAttribute('data-card-index', '1');
    await stage.dispatchEvent('pointerdown', {
      pointerId: 2,
      pointerType: 'touch',
      clientY: 160,
    });
    await stage.dispatchEvent('pointercancel', {
      pointerId: 2,
      pointerType: 'touch',
    });
    await stage.dispatchEvent('pointerup', {
      pointerId: 2,
      pointerType: 'touch',
      clientY: 90,
    });
    await expect(deck).toHaveAttribute('data-card-index', '1');
    await expect(deck).toHaveAttribute('data-moving', 'false');
    await expect.poll(() => page.evaluate(inspectOrbitLayout)).toEqual([]);
  });
});

test('the limb has a thin upper crest, dark core and foreground emission reaching the bottom', async ({
  page,
}) => {
  test.setTimeout(60000);
  await page.route('**/song/media/outer/**', (route) => route.abort());
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  for (const size of [
    { width: 960, height: 640 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(size);
    await page.goto(horizon());
    await expect(page.locator('main')).toHaveAttribute(
      'data-renderer',
      'webgl',
    );
    await expect(page.locator('main')).toHaveAttribute(
      'data-horizon-treatment',
      'limb',
    );
    const { data, info } = await frame(page);
    const luminance = (x: number, y: number) => {
      const i = (Math.floor(y) * info.width + Math.floor(x)) * 3;
      return 0.2126 * data[i]! + 0.7152 * data[i + 1]! + 0.0722 * data[i + 2]!;
    };
    const profile = Array.from(
      { length: Math.floor(info.height * 0.46) },
      (_, y) =>
        [-4, -2, 0, 2, 4].reduce(
          (sum, dx) => sum + luminance(info.width / 2 + dx, y),
          0,
        ) / 5,
    );
    const peak = Math.max(...profile);
    expect(peak).toBeGreaterThan(160);
    expect(profile.filter((value) => value > peak * 0.75).length).toBeLessThan(
      info.height * 0.04,
    );
    expect(luminance(info.width * 0.5, info.height * 0.42)).toBeLessThan(15);
    // Infer the radius from the rendered crest, independently of shader constants.
    const radius = info.height / 2 - profile.indexOf(peak);
    const outerBand =
      [-1, 0, 1].reduce(
        (sum, dy) =>
          sum +
          luminance(
            info.width / 2,
            profile.indexOf(peak) - radius * 0.058 + dy,
          ),
        0,
      ) / 3;
    expect(outerBand, 'A distinct, dimmer outer glow').toBeGreaterThan(
      peak * 0.29,
    );
    expect(outerBand).toBeLessThan(peak * 0.7);
    const firstFilament = (x: number) => {
      for (
        let y = Math.ceil(info.height / 2 + radius * 0.07);
        y < info.height / 2 + radius * 0.45;
        y++
      ) {
        const value = luminance(x, y);
        if (
          value > 65 &&
          value >= luminance(x, y - 1) &&
          value > luminance(x, y + 1)
        )
          return y;
      }
      throw new Error('The inner foreground filament is missing');
    };
    const centerBand = firstFilament(info.width / 2);
    const leftBand = firstFilament(info.width / 2 - radius * 0.18);
    const rightBand = firstFilament(info.width / 2 + radius * 0.18);
    expect(
      centerBand - Math.min(leftBand, rightBand),
      'The disk must not rise into an isolated central cusp',
    ).toBeGreaterThan(-radius * 0.02);
    // Track a bright, connected ridge and require it to turn into the disk.
    // Merely lighting the original circle allowed the rejected vertical crossing.
    for (const side of [-1, 1]) {
      let ridgeX = info.width / 2 + side * radius;
      const reach = Math.max(4, Math.ceil(radius * 0.025));
      for (let step = 0; step <= 28; step++) {
        const y = info.height / 2 + radius * 0.19 * (step / 28);
        let brightest = -1;
        let nextX = ridgeX;
        for (let x = Math.round(ridgeX) - reach; x <= ridgeX + reach; x++) {
          const value = luminance(x, y);
          if (value > brightest) {
            brightest = value;
            nextX = x;
          }
        }
        expect(
          brightest,
          `Broken turning ridge at ${side}, ${step}`,
        ).toBeGreaterThan(125);
        ridgeX = nextX;
      }
      const circularX = radius * Math.sqrt(1 - 0.19 ** 2);
      const inwardTurn = circularX - Math.abs(ridgeX - info.width / 2);
      expect(
        inwardTurn,
        `The ${side} rim must bend into the foreground`,
      ).toBeGreaterThan(radius * 0.035);
    }
    // Material continuity is tested separately in horizon-flow.spec.ts.
    // The previous flat-veil contrast oracle rejected valid directional texture
    // while allowing a disconnected lower edge, so it is no longer applicable.
    let bottom = 0,
      count = 0;
    for (let y = Math.floor(info.height * 0.94); y < info.height * 0.985; y++)
      for (let x = Math.floor(info.width * 0.22); x < info.width * 0.68; x++) {
        bottom += luminance(x, y);
        count++;
      }
    expect(bottom / count).toBeGreaterThan(4);
  }
  await page.setViewportSize({ width: 640, height: 480 });
  await page.goto(horizon(false));
  await expect(page.locator('main')).toHaveAttribute('data-renderer', 'webgl');
  const first = await frame(page);
  const initial = await page.evaluate(() => window.__orbitScene!.frames);
  await expect
    .poll(() => page.evaluate(() => window.__orbitScene!.frames))
    .toBeGreaterThan(initial + 15);
  const second = await frame(page);
  let change = 0;
  for (let i = 0; i < first.data.length; i++)
    change += Math.abs(first.data[i]! - second.data[i]!);
  expect(change / first.data.length).toBeGreaterThan(0.05);
  expect(errors).toEqual([]);
});
