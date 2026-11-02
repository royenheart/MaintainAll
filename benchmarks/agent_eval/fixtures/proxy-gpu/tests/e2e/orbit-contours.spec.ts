import { expect, test } from '@playwright/test';
import { inspectRotaryLayout } from '../support/rotary-layout';
import { inspectOrbitLayout } from '../support/orbit-layout';

const story = (name = 'native-drum', args = '') =>
  `http://127.0.0.1:6006/iframe.html?id=explorations-rotary-directions--${name}&args=${args}`;

test('the quiet deck orders identity, scene content, profile links and scene navigation', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route('**/song/media/outer/**', (route) => route.abort());
  for (const scene of ['cubes', 'horizon']) {
    await page.goto(
      story('velvet-drum', `initialScene:${scene};graphics:poster`),
    );
    const deck = page.locator('.rotary-deck');
    await expect(deck).toBeVisible();
    await expect(
      page.locator('.orbit-wheel-caption, .rotary-deck .orbit-card-navigation'),
    ).toHaveCount(0);
    const labels = await page
      .locator('.rotary-card')
      .evaluateAll((cards) =>
        cards.map((card) => card.getAttribute('aria-label')),
      );
    expect(labels.slice(0, 3)).toEqual([
      'A little about me',
      'Inside this scene',
      'On the turntable',
    ]);
    expect(labels.slice(-3)).toEqual(['Blog', 'GitHub', 'Beyond this scene']);
    expect(
      labels.slice(3, -3).every((label) => label?.startsWith('Listen on ')),
    ).toBe(true);
    await expect(page.locator('.rotary-card-active img')).toHaveAttribute(
      'alt',
      "RoyenHeart's avatar",
    );
    for (const label of labels) {
      await expect(page.getByRole('article')).toHaveAccessibleName(label!);
      await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
      await deck.press('ArrowDown');
    }
    await deck.press('Home');
    await expect(page.locator('.rotary-card-active h2')).toHaveText(
      'RoyenHeart',
    );
    await deck.press('Escape');
    await expect(deck).toHaveCount(0);
    await expect(page.locator('.orbit-disc')).toBeFocused();
    const footer = await page.locator('.orbit-footer').boundingBox();
    expect(footer!.x).toBeLessThanOrEqual(10);
    expect(
      page.viewportSize()!.height - footer!.y - footer!.height,
    ).toBeLessThanOrEqual(8);
    await expect.poll(() => page.evaluate(inspectOrbitLayout)).toEqual([]);
  }
});

test('real audio drives overlapping closed contours and pause settles to rest', async ({
  page,
}) => {
  await page.goto(story());
  const ring = page.locator('.orbit-spectrum');
  const paths = ring.locator('path');
  await expect(ring).toHaveAttribute('data-form', 'contours');
  await expect(paths).toHaveCount(4);
  await expect(ring.locator('line')).toHaveCount(0);
  const rest = await paths.evaluateAll((nodes) =>
    nodes.map((node) => node.getAttribute('d')),
  );
  await page.locator('.orbit-disc').hover({ position: { x: 12, y: 50 } });
  await expect(page.locator('.orbit-sound')).toBeEnabled();
  await page.locator('.orbit-sound').click();
  await expect
    .poll(async () => Number(await ring.getAttribute('data-energy')))
    .toBeGreaterThan(0.2);
  const moving = await paths.evaluateAll((nodes) =>
    nodes.map((node) => node.getAttribute('d')),
  );
  expect(new Set(moving).size).toBe(4);
  expect(moving).not.toEqual(rest);
  await expect
    .poll(async () => paths.first().getAttribute('d'))
    .not.toBe(moving[0]);
  const geometry = await paths.evaluateAll((nodes) =>
    nodes.map((node) => {
      const path = node as SVGPathElement;
      const length = path.getTotalLength();
      const angular = new Array<number>(32).fill(0);
      const errors = new Array<number>(32).fill(Infinity);
      const radii = Array.from({ length: 512 }, (_, index) => {
        const point = path.getPointAtLength((length * index) / 512);
        const angle =
          (Math.atan2(point.y - 100, point.x - 100) + Math.PI * 2) %
          (Math.PI * 2);
        const bin = Math.min(31, Math.floor((angle / (Math.PI * 2)) * 32));
        const error = Math.abs(angle - ((bin + 0.5) / 32) * Math.PI * 2);
        const radius = Math.hypot(point.x - 100, point.y - 100);
        if (error < errors[bin]!) {
          errors[bin] = error;
          angular[bin] = radius;
        }
        return radius;
      });
      return {
        min: Math.min(...radii),
        max: Math.max(...radii),
        closed: path.getAttribute('d')!.endsWith('Z'),
        angular,
      };
    }),
  );
  for (const curve of geometry) {
    expect(curve.closed).toBe(true);
    expect(curve.min).toBeGreaterThan(81);
    expect(curve.max).toBeLessThan(99);
    expect(curve.max - curve.min).toBeGreaterThan(1);
  }
  // Layers exchange inner/outer ordering at matched angles, establishing crossings.
  expect(Math.max(...geometry.map((curve) => curve.min))).toBeLessThan(
    Math.min(...geometry.map((curve) => curve.max)),
  );
  for (let index = 1; index < geometry.length; index++) {
    const difference = geometry[index]!.angular.map(
      (radius, angle) => radius - geometry[index - 1]!.angular[angle]!,
    );
    expect(Math.max(...difference)).toBeGreaterThan(0.15);
    expect(Math.min(...difference)).toBeLessThan(-0.15);
  }
  await page.locator('.orbit-sound').click();
  await expect
    .poll(async () => Number(await ring.getAttribute('data-energy')))
    .toBe(0);
  await expect
    .poll(async () =>
      paths.evaluateAll((nodes) => nodes.map((node) => node.getAttribute('d'))),
    )
    .toEqual(rest);
});

test('silent playback and reduced motion keep the contour ring still', async ({
  page,
}) => {
  for (const silent of [true, false]) {
    await page.emulateMedia({
      reducedMotion: silent ? 'no-preference' : 'reduce',
    });
    await page.goto(story(silent ? 'silent-drum' : 'native-drum'));
    const paths = page.locator('.orbit-spectrum path');
    await expect(paths).toHaveCount(4);
    const rest = await paths.evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute('d')),
    );
    await page.locator('.orbit-disc').hover({ position: { x: 12, y: 50 } });
    await expect(page.locator('.orbit-sound')).toBeEnabled();
    await page.locator('.orbit-sound').click();
    await expect(page.locator('.orbit-wheel')).toHaveAttribute(
      'data-playing',
      'true',
    );
    // The progress text establishes that the real media clock has advanced.
    await page.locator('.rotary-deck').press('ArrowDown');
    await page.locator('.rotary-deck').press('ArrowDown');
    await expect(page.getByRole('progressbar')).toHaveAttribute(
      'aria-label',
      /Song progress: 0:0[1-9]/,
    );
    expect(
      await paths.evaluateAll((nodes) =>
        nodes.map((node) => node.getAttribute('d')),
      ),
    ).toEqual(rest);
    await expect(page.locator('.orbit-spectrum')).toHaveAttribute(
      'data-energy',
      /^0(?:\.0+)?$/,
    );
    if (!silent) {
      await page.emulateMedia({ reducedMotion: 'no-preference' });
      await expect
        .poll(async () =>
          Number(
            await page.locator('.orbit-spectrum').getAttribute('data-energy'),
          ),
        )
        .toBeGreaterThan(0.2);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await expect
        .poll(async () =>
          paths.evaluateAll((nodes) =>
            nodes.map((node) => node.getAttribute('d')),
          ),
        )
        .toEqual(rest);
    }
  }
});
