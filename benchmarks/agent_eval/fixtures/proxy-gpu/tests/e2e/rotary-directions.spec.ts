import { test, expect } from '@playwright/test';
import { viewports } from '../support/viewports';
import { inspectOrbitLayout } from '../support/orbit-layout';
import { inspectRotaryLayout } from '../support/rotary-layout';

const stories = ['tangent-glass', 'velvet-drum', 'orbital-ribbon'];
const url = (story: string, extra = '') =>
  `http://127.0.0.1:6006/iframe.html?id=explorations-rotary-directions--${story}&args=graphics:poster${extra}`;

test('selected recordings enter the drum deck and retain adjacent-scene navigation', async ({
  page,
}) => {
  test.setTimeout(60000);
  await page.route('**/song/media/outer/**', (route) => route.abort());
  await page.setViewportSize({ width: 390, height: 400 });
  for (const scene of ['cubes', 'horizon']) {
    await page.goto(
      `http://127.0.0.1:6006/iframe.html?id=explorations-orbit-study--selected-${scene}&args=graphics:poster`,
    );
    const root = page.locator('main');
    await expect(root).toHaveAttribute('data-dock-design', 'drum');
    await expect(page.locator('.orbit-arrival')).toHaveCount(0);
    await expect(page.locator('.rotary-card-active')).toBeVisible();
    await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
    await expect(page.locator('.orbit-artwork')).toHaveAttribute(
      'aria-label',
      scene === 'cubes' ? 'Clair de Lune artwork' : 'Sanctuary artwork',
    );
    const count = Number(
      await page.locator('.rotary-deck').getAttribute('data-card-count'),
    );
    for (let i = 1; i < count; i++)
      await page.locator('.rotary-deck').press('ArrowDown');
    await page
      .getByRole('button', {
        name: 'Next scene',
        exact: true,
      })
      .click();
    await expect(root).toHaveAttribute(
      'data-scene',
      scene === 'cubes' ? 'horizon' : 'cubes',
    );
    await expect(root).toHaveAttribute('data-transitioning', 'false');
    await expect(root).toHaveAttribute('data-dock-design', 'drum');
    await page.locator('.orbit-disc').click({ position: { x: 12, y: 50 } });
    await expect(page.locator('.rotary-deck')).toHaveAttribute(
      'data-card-index',
      '0',
    );
    await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
    await expect.poll(() => page.evaluate(inspectOrbitLayout)).toEqual([]);
  }
});

test('the contour oracle detects a forced vertical text rail', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(url('tangent-glass'));
  await page.locator('.rotary-deck').press('ArrowDown');
  await expect(page.locator('.rotary-card-active')).toBeVisible();
  await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
  await page
    .locator('.rotary-card-active .orbit-ribbon-copy')
    .evaluate((copy) => {
      for (const line of copy.children)
        (line as HTMLElement).style.paddingLeft = '50px';
    });
  expect(await page.evaluate(inspectRotaryLayout)).toContain(
    'Text line does not follow the painted contour',
  );
});

for (const story of stories) {
  test(`${story}: every card fits the width and height matrix`, async ({
    page,
  }) => {
    test.setTimeout(120000);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.route('**/song/media/outer/**', (r) => r.abort());
    await page.goto(url(story));
    await expect(page.locator('.rotary-card-active')).toBeVisible();
    const sizes = [
      ...viewports,
      ...[638, 639, 640, 641].map((width) => ({ width, height: 600 })),
    ];
    for (const size of sizes) {
      await page.setViewportSize(size);
      const count = Number(
        await page.locator('.rotary-deck').getAttribute('data-card-count'),
      );
      for (let i = 0; i < count; i++) {
        await expect
          .poll(() => page.evaluate(inspectOrbitLayout), {
            message: `${story} ${size.width}x${size.height} card ${i}`,
          })
          .toEqual([]);
        await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
        if (i < count - 1)
          await page.locator('.rotary-deck').press('ArrowDown');
      }
      for (let i = 1; i < count; i++)
        await page.locator('.rotary-deck').press('ArrowUp');
    }
  });

  test(`${story}: circular motion, interruption, resize and reduced motion`, async ({
    page,
  }) => {
    test.setTimeout(60000);
    await page.route('**/song/media/outer/**', (r) => r.abort());
    await page.setViewportSize({ width: 960, height: 640 });
    await page.goto(url(story, ';cardDuration:0.85'));
    await expect(page.locator('.rotary-card-active')).toBeVisible();
    await page.evaluate(() => {
      const samples: { transform: string; opacity: string }[] = [];
      Object.assign(window, { rotarySamples: samples });
      document.querySelector('.rotary-deck')!.addEventListener(
        'keydown',
        () => {
          const until = performance.now() + 1200;
          const sample = () => {
            const style = getComputedStyle(
              document.querySelector('.rotary-card[data-position="1"]')!,
            );
            samples.push({
              transform: style.transform,
              opacity: style.opacity,
            });
            if (performance.now() < until) requestAnimationFrame(sample);
          };
          requestAnimationFrame(sample);
        },
        { once: true },
      );
    });
    await page.locator('.rotary-deck').press('ArrowDown');
    await expect(page.locator('.rotary-deck')).toHaveAttribute(
      'data-moving',
      'true',
    );
    await expect(page.locator('.rotary-deck')).toHaveAttribute(
      'data-moving',
      'false',
    );
    const samples = await page.evaluate(
      () =>
        (
          window as unknown as {
            rotarySamples: { transform: string; opacity: string }[];
          }
        ).rotarySamples,
    );
    expect(new Set(samples.map((s) => s.transform)).size).toBeGreaterThan(5);
    expect(
      samples.some(
        (s) =>
          s.transform.startsWith('matrix3d') &&
          Number(s.opacity) > 0.3 &&
          Number(s.opacity) < 0.9,
      ),
    ).toBe(true);
    for (let i = 0; i < 3; i++)
      await page.locator('.rotary-deck').press('ArrowDown');
    await page.locator('.rotary-deck').press('ArrowUp');
    await page.setViewportSize({ width: 390, height: 400 });
    await expect(page.locator('.rotary-deck')).toHaveAttribute(
      'data-moving',
      'false',
    );
    await expect(page.locator('.rotary-deck')).toHaveAttribute(
      'data-card-index',
      '3',
    );
    await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
    await expect.poll(() => page.evaluate(inspectOrbitLayout)).toEqual([]);
    await page.keyboard.press('Escape');
    await expect(page.locator('.orbit-disc')).toBeFocused();
    await page.locator('.orbit-disc').click({ position: { x: 12, y: 50 } });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.locator('.rotary-deck').press('ArrowDown');
    await expect(page.locator('.rotary-deck')).toHaveAttribute(
      'data-moving',
      'false',
    );
    await expect(page.locator('.rotary-card-active')).toHaveCSS(
      'transform',
      'none',
    );
    await expect.poll(() => page.evaluate(inspectRotaryLayout)).toEqual([]);
  });
}
